"""Canonical models for Meraki VPN exclusion rules."""
from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuleCategory(StrEnum):
    CUSTOM = "custom"
    MAJOR_APPLICATION = "majorApplications"
    APPLICATION = "applications"


class ChangeKind(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    REMOVED = "removed"


class RuleSource(BaseModel):
    cidr: str | None = None
    port: str | None = None
    vlan_id: str | None = Field(default=None, alias="vlanId")
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def one_location(self) -> "RuleSource":
        if self.cidr and self.vlan_id:
            raise ValueError("source cannot contain both cidr and vlanId")
        return self


class VpnExclusionRule(BaseModel):
    category: RuleCategory
    order: int = 0
    protocol: str = "any"
    destination: str | None = None
    port: str = "any"
    application_id: str | None = None
    name: str | None = None
    source: RuleSource | None = None
    action: str = "upsert"
    origin: str | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("protocol")
    @classmethod
    def protocol_supported(cls, value: str) -> str:
        value = value.strip().lower() or "any"
        if value not in {"any", "dns", "icmp", "tcp", "udp"}:
            raise ValueError("protocol must be any, dns, icmp, tcp, or udp")
        return value

    @field_validator("action")
    @classmethod
    def action_supported(cls, value: str) -> str:
        value = value.strip().lower() or "upsert"
        if value not in {"upsert", "remove"}:
            raise ValueError("action must be upsert or remove")
        return value

    @model_validator(mode="after")
    def required_fields(self) -> "VpnExclusionRule":
        if self.category == RuleCategory.CUSTOM and not self.destination:
            raise ValueError("custom rule requires destination")
        if self.category != RuleCategory.CUSTOM and not self.application_id:
            raise ValueError("application rule requires application id")
        if self.protocol == "dns" and self.destination and "/" in self.destination:
            raise ValueError("DNS destination must be a hostname")
        return self

    def normalized_dict(self) -> dict[str, Any]:
        from rules.normalizer import normalize_rule

        return normalize_rule(self)

    def fingerprint(self) -> str:
        raw = json.dumps(self.normalized_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def api_dict(self) -> dict[str, Any]:
        normalized = self.normalized_dict()
        if self.category == RuleCategory.CUSTOM:
            data: dict[str, Any] = {
                "protocol": normalized["protocol"],
                "destination": normalized["destination"],
                "port": normalized["port"],
            }
        else:
            data = {
                "id": normalized["application_id"],
                "name": (self.name or "").strip(),
            }
            if normalized["protocol"] != "any" or self.source:
                data["protocol"] = normalized["protocol"]
        if normalized.get("source"):
            data["source"] = normalized["source"]
        return data


class RuleSet(BaseModel):
    rules: list[VpnExclusionRule] = Field(default_factory=list)
    mode: str = "merge"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        value = value.lower()
        if value not in {"merge", "replace"}:
            raise ValueError("mode must be merge or replace")
        return value

    def payload(self) -> dict[str, list[dict[str, Any]]]:
        result = {"custom": [], "majorApplications": [], "applications": []}
        for rule in sorted(self.rules, key=lambda item: item.order):
            if rule.action != "remove":
                result[rule.category.value].append(rule.api_dict())
        return result

    def fingerprint(self) -> str:
        raw = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

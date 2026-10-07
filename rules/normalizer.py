"""Normalization functions used by validation and duplicate detection."""
from __future__ import annotations

import ipaddress
import re
from typing import Any

from rules.models import VpnExclusionRule


def normalize_port(value: str | None) -> str:
    value = (value or "any").strip().lower()
    if value in {"", "0", "*"}:
        return "any"
    if re.fullmatch(r"\d+", value):
        number = int(value)
        if not 1 <= number <= 65535:
            raise ValueError(f"port {number} is outside 1-65535")
        return str(number)
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", value)
    if match:
        start, end = map(int, match.groups())
        if not (1 <= start <= end <= 65535):
            raise ValueError(f"invalid port range {value}")
        return f"{start}-{end}"
    if value != "any":
        raise ValueError(f"invalid port {value}")
    return value


def normalize_destination(protocol: str, value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower().rstrip(".")
    if protocol == "dns":
        if not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
            value,
        ):
            raise ValueError(f"invalid DNS hostname {value}")
        return value
    if value in {"any", "*"}:
        return "any"
    return str(ipaddress.ip_network(value, strict=False))


def normalize_rule(rule: VpnExclusionRule) -> dict[str, Any]:
    source = None
    if rule.source:
        source = {}
        if rule.source.cidr:
            source["cidr"] = str(
                ipaddress.ip_network(rule.source.cidr.strip(), strict=False)
            )
        if rule.source.port:
            source["port"] = normalize_port(rule.source.port)
        if rule.source.vlan_id:
            source["vlanId"] = rule.source.vlan_id.strip()
        source = source or None
    return {
        "category": rule.category.value,
        "protocol": rule.protocol.lower(),
        "destination": normalize_destination(rule.protocol, rule.destination),
        "port": normalize_port(rule.port),
        "application_id": (
            rule.application_id.strip().lower() if rule.application_id else None
        ),
        "source": source,
    }

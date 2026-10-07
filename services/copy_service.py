"""Multi-network VPN exclusion copy service for V1.

Uses existing compare() and update_rules() so proven logic is never duplicated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from meraki_client.client_v1 import MerakiVpnClientV1
from rules.comparer import compare
from rules.models import ChangeKind, RuleSet, VpnExclusionRule


@dataclass(slots=True)
class RuleStatus:
    rule: VpnExclusionRule
    status: Literal["new", "exists", "invalid"]
    detail: str = ""


@dataclass(slots=True)
class NetworkCopyPreview:
    network_id: str
    network_name: str
    rule_statuses: list[RuleStatus] = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return sum(s.status == "new" for s in self.rule_statuses)

    @property
    def exists_count(self) -> int:
        return sum(s.status == "exists" for s in self.rule_statuses)

    @property
    def invalid_count(self) -> int:
        return sum(s.status == "invalid" for s in self.rule_statuses)

    @property
    def has_new_rules(self) -> bool:
        return self.new_count > 0


@dataclass(slots=True)
class CopyResult:
    network_id: str
    network_name: str
    success: bool
    rules_added: int = 0
    rules_skipped: int = 0
    error: str = ""


class CopyService:
    """Previews and executes copying selected VPN exclusion rules across networks."""

    def __init__(self, client: MerakiVpnClientV1) -> None:
        self.client = client

    def preview(
        self,
        organization_id: str,
        selected_rules: list[VpnExclusionRule],
        destination_networks: list[dict[str, Any]],
    ) -> list[NetworkCopyPreview]:
        """Return per-destination status for each selected rule without making changes."""
        previews: list[NetworkCopyPreview] = []
        for network in destination_networks:
            existing = self.client.get_rules(organization_id, network["id"])
            existing_fps = {r.fingerprint() for r in existing.rules}
            statuses: list[RuleStatus] = []
            for rule in selected_rules:
                try:
                    fp = rule.fingerprint()
                    if fp in existing_fps:
                        statuses.append(
                            RuleStatus(rule=rule, status="exists", detail="Already present — will be skipped")
                        )
                    else:
                        statuses.append(
                            RuleStatus(rule=rule, status="new", detail="Will be added")
                        )
                except Exception as exc:
                    statuses.append(
                        RuleStatus(rule=rule, status="invalid", detail=str(exc))
                    )
            previews.append(
                NetworkCopyPreview(
                    network_id=network["id"],
                    network_name=network["name"],
                    rule_statuses=statuses,
                )
            )
        return previews

    def execute(
        self,
        organization_id: str,
        selected_rules: list[VpnExclusionRule],
        destination_networks: list[dict[str, Any]],
        progress: Callable[[str], None] | None = None,
    ) -> list[CopyResult]:
        """Apply selected rules to all destination networks using merge mode."""
        results: list[CopyResult] = []
        proposed = RuleSet(rules=selected_rules, mode="merge")
        for network in destination_networks:
            if progress:
                progress(f"Copying to {network['name']}…")
            try:
                existing = self.client.get_rules(organization_id, network["id"])
                comparison = compare(existing, proposed)
                if comparison.has_blockers:
                    results.append(
                        CopyResult(
                            network_id=network["id"],
                            network_name=network["name"],
                            success=False,
                            error="Rules contain invalid or duplicate entries — no changes made.",
                        )
                    )
                    continue
                added = comparison.count(ChangeKind.NEW)
                skipped = comparison.count(ChangeKind.UNCHANGED)
                if added == 0:
                    results.append(
                        CopyResult(
                            network_id=network["id"],
                            network_name=network["name"],
                            success=True,
                            rules_added=0,
                            rules_skipped=skipped,
                        )
                    )
                    continue
                self.client.update_rules(network["id"], comparison.final)
                results.append(
                    CopyResult(
                        network_id=network["id"],
                        network_name=network["name"],
                        success=True,
                        rules_added=added,
                        rules_skipped=skipped,
                    )
                )
            except Exception as exc:
                results.append(
                    CopyResult(
                        network_id=network["id"],
                        network_name=network["name"],
                        success=False,
                        error=str(exc),
                    )
                )
        return results

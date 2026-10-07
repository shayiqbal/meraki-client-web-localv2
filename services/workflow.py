"""Mandatory dry-run, drift detection, and independent network deployment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from meraki_client.client import MerakiVpnClient
from rules.comparer import Comparison, compare
from rules.models import ChangeKind, RuleSet


class DriftDetected(RuntimeError):
    """The live VPN exclusion configuration changed after dry run."""


@dataclass(slots=True)
class DryRun:
    organization_id: str
    network_id: str
    network_name: str
    existing_fingerprint: str
    comparison: Comparison

    @property
    def change_count(self) -> int:
        return sum(
            item.kind in {ChangeKind.NEW, ChangeKind.UPDATED, ChangeKind.REMOVED}
            for item in self.comparison.changes
        )


class WorkflowService:
    def __init__(self, client: MerakiVpnClient) -> None:
        self.client = client

    def dry_run(
        self,
        organization_id: str,
        networks: list[dict],
        proposed: RuleSet,
        progress: Callable[[str], None] | None = None,
    ) -> list[DryRun]:
        results: list[DryRun] = []
        for network in networks:
            if progress:
                progress(f"Reading {network['name']}…")
            existing = self.client.get_rules(organization_id, network["id"])
            comparison = compare(existing, proposed)
            results.append(
                DryRun(
                    organization_id=organization_id,
                    network_id=network["id"],
                    network_name=network["name"],
                    existing_fingerprint=existing.fingerprint(),
                    comparison=comparison,
                )
            )
        return results

    def deploy(
        self,
        dry_run: DryRun,
        allow_drift: bool = False,
    ) -> dict:
        current = self.client.get_rules(dry_run.organization_id, dry_run.network_id)
        if current.fingerprint() != dry_run.existing_fingerprint and not allow_drift:
            raise DriftDetected(
                f"{dry_run.network_name} changed after dry run. Run dry run again."
            )
        if dry_run.comparison.has_blockers:
            raise ValueError("Deployment is blocked by invalid or duplicate rules.")
        return self.client.update_rules(
            dry_run.network_id, dry_run.comparison.final
        )

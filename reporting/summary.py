"""Deployment summary model and CSV/JSON exports."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class NetworkResult:
    network_id: str
    network_name: str
    success: bool
    created: int = 0
    removed: int = 0
    unchanged: int = 0
    skipped: int = 0
    invalid: int = 0
    retries: int = 0
    error: str = ""


@dataclass(slots=True)
class DeploymentSummary:
    organization_id: str
    organization_name: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str = ""
    networks: list[NetworkResult] = field(default_factory=list)

    def finish(self) -> None:
        self.ended_at = datetime.now(UTC).isoformat()

    def totals(self) -> dict[str, int]:
        fields = ("created", "removed", "unchanged", "skipped", "invalid", "retries")
        return {name: sum(getattr(item, name) for item in self.networks) for name in fields}

    def as_dict(self) -> dict:
        data = asdict(self)
        data["totals"] = self.totals()
        data["successful_networks"] = sum(item.success for item in self.networks)
        data["failed_networks"] = sum(not item.success for item in self.networks)
        return data

    def export_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")

    def export_csv(self, path: Path) -> None:
        columns = list(NetworkResult.__dataclass_fields__)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(asdict(item) for item in self.networks)

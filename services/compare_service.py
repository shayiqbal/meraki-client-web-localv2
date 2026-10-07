"""Network configuration comparison service for V1.

Compares a source network against one or more targets across three categories:
VPN exclusion rules, MX appliance SSIDs, and basic network settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from meraki_client.client_v1 import MerakiVpnClientV1


Status = Literal["match", "missing", "different", "na"]


@dataclass(slots=True)
class Cell:
    status: Status
    detail: str = ""  # shown in table tooltip / detail column


@dataclass
class CompareRow:
    """One item (rule / SSID / setting) with a status cell per target network."""
    label: str
    source_display: str
    cells: dict[str, Cell] = field(default_factory=dict)  # network_id → Cell


@dataclass
class CompareReport:
    source_network: dict[str, Any]
    target_networks: list[dict[str, Any]]
    vpn_rules: list[CompareRow]
    ssids: list[CompareRow]
    settings: list[CompareRow]


class CompareService:
    def __init__(self, client: MerakiVpnClientV1) -> None:
        self.client = client

    def compare(
        self,
        organization_id: str,
        source_network: dict[str, Any],
        target_networks: list[dict[str, Any]],
        progress: Callable[[str], None] | None = None,
    ) -> CompareReport:
        src_id = source_network["id"]

        if progress:
            progress(f"Reading source: {source_network['name']}…")
        src_rules = self.client.get_rules(organization_id, src_id)
        src_ssids = self._safe_ssids(src_id)
        src_settings = self._safe_settings(src_id)
        src_net_info = self._safe_network(src_id)

        target_data: dict[str, dict] = {}
        for net in target_networks:
            if progress:
                progress(f"Reading: {net['name']}…")
            target_data[net["id"]] = {
                "rules": self.client.get_rules(organization_id, net["id"]),
                "ssids": self._safe_ssids(net["id"]),
                "settings": self._safe_settings(net["id"]),
                "net_info": self._safe_network(net["id"]),
            }

        return CompareReport(
            source_network=source_network,
            target_networks=target_networks,
            vpn_rules=self._compare_rules(src_rules, target_networks, target_data),
            ssids=self._compare_ssids(src_ssids, target_networks, target_data),
            settings=self._compare_settings(
                src_settings, src_net_info, target_networks, target_data
            ),
        )

    # ── VPN exclusion rules ────────────────────────────────────────────────

    @staticmethod
    def _compare_rules(src_rules, targets, target_data) -> list[CompareRow]:
        rows: list[CompareRow] = []
        src_fps = {r.fingerprint(): r for r in src_rules.rules}

        for rule in sorted(src_rules.rules, key=lambda r: r.order):
            fp = rule.fingerprint()
            label = rule.destination or rule.name or rule.application_id or "—"
            display = f"[{rule.category.value}] {rule.protocol}  {label}  :{rule.port}"
            cells: dict[str, Cell] = {}
            for net in targets:
                t_rules = target_data[net["id"]]["rules"]
                t_fps = {r.fingerprint() for r in t_rules.rules}
                cells[net["id"]] = (
                    Cell("match", "Match")
                    if fp in t_fps
                    else Cell("missing", "Missing")
                )
            rows.append(CompareRow(label=label, source_display=display, cells=cells))

        # Also flag rules present on targets but NOT in source
        all_source_fps = set(src_fps.keys())
        extra_fps: dict[str, set] = {}
        for net in targets:
            t_rules = target_data[net["id"]]["rules"]
            for r in t_rules.rules:
                fp = r.fingerprint()
                if fp not in all_source_fps:
                    extra_fps.setdefault(fp, set()).add(net["id"])

        for fp, net_ids in extra_fps.items():
            # Recover rule from the first target that has it
            sample_rule = None
            for net in targets:
                if net["id"] in net_ids:
                    for r in target_data[net["id"]]["rules"].rules:
                        if r.fingerprint() == fp:
                            sample_rule = r
                            break
                if sample_rule:
                    break
            if not sample_rule:
                continue
            label = sample_rule.destination or sample_rule.name or "—"
            display = (
                f"[{sample_rule.category.value}] {sample_rule.protocol}  {label}  "
                f":{sample_rule.port}  ← extra (not in source)"
            )
            cells = {}
            for net in targets:
                cells[net["id"]] = (
                    Cell("different", "Extra — not in source")
                    if net["id"] in net_ids
                    else Cell("na", "—")
                )
            rows.append(CompareRow(label=f"[EXTRA] {label}", source_display=display, cells=cells))

        return rows

    # ── MX appliance SSIDs ─────────────────────────────────────────────────

    @staticmethod
    def _compare_ssids(src_ssids, targets, target_data) -> list[CompareRow]:
        rows: list[CompareRow] = []

        if not src_ssids:
            # Source has no wireless SSIDs — mark all targets as N/A
            cells: dict[str, Cell] = {
                net["id"]: Cell("na", "Source network has no wireless SSIDs")
                for net in targets
            }
            rows.append(CompareRow(
                label="Wireless SSIDs",
                source_display="Not available (no wireless on source)",
                cells=cells,
            ))
            return rows

        src_by_num = {s.get("number", i): s for i, s in enumerate(src_ssids)}

        for num, src in sorted(src_by_num.items()):
            name = src.get("name") or f"SSID {num}"
            enabled = src.get("enabled", False)
            auth = src.get("authMode", "open")
            display = f"[{num}] {name}  enabled={enabled}  auth={auth}"
            cells: dict[str, Cell] = {}
            for net in targets:
                t_ssids = target_data[net["id"]]["ssids"]
                t_by_num = {s.get("number", i): s for i, s in enumerate(t_ssids)}
                t = t_by_num.get(num)
                if t is None:
                    cells[net["id"]] = Cell("na", "SSID slot not available")
                elif (
                    t.get("name") == src.get("name")
                    and t.get("enabled") == src.get("enabled")
                    and t.get("authMode") == src.get("authMode")
                ):
                    cells[net["id"]] = Cell("match", "Name, enabled state and auth mode match")
                else:
                    diffs = []
                    if t.get("name") != src.get("name"):
                        diffs.append(f"name: '{t.get('name')}'")
                    if t.get("enabled") != src.get("enabled"):
                        diffs.append(f"enabled: {t.get('enabled')}")
                    if t.get("authMode") != src.get("authMode"):
                        diffs.append(f"auth: {t.get('authMode')}")
                    cells[net["id"]] = Cell("different", "; ".join(diffs))
            rows.append(CompareRow(label=name, source_display=display, cells=cells))
        return rows

    # ── Basic settings ─────────────────────────────────────────────────────

    @staticmethod
    def _compare_settings(src_settings, src_net_info, targets, target_data) -> list[CompareRow]:
        rows: list[CompareRow] = []

        items = [
            ("Time Zone",        src_net_info.get("timeZone", "—")),
            ("Tags",             ", ".join(src_net_info.get("tags") or []) or "(none)"),
            ("Notes",            (src_net_info.get("notes") or "").strip() or "(none)"),
            ("Client Tracking",  src_settings.get("clientTrackingMethod", "—")),
            ("Deployment Mode",  src_settings.get("deploymentMode", "—")),
        ]

        for label, src_val in items:
            cells: dict[str, Cell] = {}
            for net in targets:
                t_settings = target_data[net["id"]]["settings"]
                t_net_info = target_data[net["id"]]["net_info"]
                if label == "Time Zone":
                    t_val = t_net_info.get("timeZone", "—")
                elif label == "Tags":
                    t_val = ", ".join(t_net_info.get("tags") or []) or "(none)"
                elif label == "Notes":
                    t_val = (t_net_info.get("notes") or "").strip() or "(none)"
                elif label == "Client Tracking":
                    t_val = t_settings.get("clientTrackingMethod", "—")
                else:
                    t_val = t_settings.get("deploymentMode", "—")
                if t_val == src_val:
                    cells[net["id"]] = Cell("match", t_val)
                else:
                    cells[net["id"]] = Cell("different", f"→ {t_val}")
            rows.append(CompareRow(label=label, source_display=src_val, cells=cells))
        return rows

    # ── Safe API calls ─────────────────────────────────────────────────────

    def _safe_ssids(self, network_id: str) -> list[dict[str, Any]]:
        try:
            return self.client.get_appliance_ssids(network_id)
        except Exception:
            return []

    def _safe_settings(self, network_id: str) -> dict[str, Any]:
        try:
            return self.client.get_appliance_settings(network_id)
        except Exception:
            return {}

    def _safe_network(self, network_id: str) -> dict[str, Any]:
        try:
            return self.client.get_network(network_id)
        except Exception:
            return {}

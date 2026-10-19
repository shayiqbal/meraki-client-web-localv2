"""Network configuration comparison service for V1.

Compares a source network against one or more targets across three categories:
VPN exclusion rules, MX appliance SSIDs, and basic network settings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from meraki_client.client_v1 import MerakiVpnClientV1
from rules.models import RuleSet


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
        src_rules = self._safe_rules(organization_id, src_id)
        src_ssids, src_ssid_errors = self._read_ssids(src_id)
        src_settings = self._safe_settings(src_id)
        src_net_info = self._safe_network(src_id)

        target_data: dict[str, dict] = {}
        for net in target_networks:
            if progress:
                progress(f"Reading: {net['name']}…")
            target_ssids, target_ssid_errors = self._read_ssids(net["id"])
            target_data[net["id"]] = {
                "rules": self._safe_rules(organization_id, net["id"]),
                "ssids": target_ssids,
                "ssid_errors": target_ssid_errors,
                "settings": self._safe_settings(net["id"]),
                "net_info": self._safe_network(net["id"]),
            }

        return CompareReport(
            source_network=source_network,
            target_networks=target_networks,
            vpn_rules=self._compare_rules(src_rules, target_networks, target_data),
            ssids=self._compare_ssids(
                src_ssids, src_ssid_errors, target_networks, target_data
            ),
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

    # ── MX and Dashboard wireless SSIDs ────────────────────────────────────

    _SSID_FIELDS = (
        ("name", "name"),
        ("enabled", "enabled"),
        ("authMode", "auth"),
        ("defaultVlanId", "VLAN"),
        ("encryptionMode", "encryption"),
        ("visible", "visible"),
    )

    @staticmethod
    def _ssid_key(ssid: dict[str, Any]) -> tuple[str, str]:
        """SSID names, not numbered slots, identify equivalent configurations."""
        return (
            ssid["ssidSource"],
            (ssid.get("name") or "").strip().casefold(),
        )

    @staticmethod
    def _is_dashboard_placeholder_ssid(ssid: dict[str, Any]) -> bool:
        """Dashboard returns unused slots as disabled 'Unconfigured SSID N' records."""
        return (
            ssid.get("ssidSource") == "Dashboard Wi-Fi"
            and not ssid.get("enabled")
            and bool(re.fullmatch(r"Unconfigured SSID \d+", ssid.get("name") or ""))
        )

    @staticmethod
    def _compare_ssids(src_ssids, src_errors, targets, target_data) -> list[CompareRow]:
        rows: list[CompareRow] = []

        if not src_ssids:
            source_detail = (
                "Could not read source SSIDs: " + "; ".join(src_errors)
                if src_errors
                else "No Dashboard Wi-Fi or MX SSIDs configured on source"
            )
            cells: dict[str, Cell] = {
                net["id"]: Cell("na", source_detail)
                for net in targets
            }
            rows.append(CompareRow(
                label="Wireless SSIDs",
                source_display=source_detail,
                cells=cells,
            ))
            return rows

        src_by_name = {CompareService._ssid_key(ssid): ssid for ssid in src_ssids}

        for (ssid_source, name_key), src in sorted(src_by_name.items()):
            name = src.get("name") or "Unnamed SSID"
            enabled = src.get("enabled", False)
            auth = src.get("authMode", "open")
            display = f"enabled={enabled}; auth={auth}; VLAN={src.get('defaultVlanId', '—')}"
            cells: dict[str, Cell] = {}
            for net in targets:
                t_ssids = target_data[net["id"]]["ssids"]
                t_errors = target_data[net["id"]]["ssid_errors"]
                t_by_name = {
                    CompareService._ssid_key(ssid): ssid for ssid in t_ssids
                }
                t = t_by_name.get((ssid_source, name_key))
                if not t_ssids and t_errors:
                    cells[net["id"]] = Cell(
                        "na", "Could not read target SSIDs: " + "; ".join(t_errors)
                    )
                elif t is None:
                    cells[net["id"]] = Cell("missing", "SSID name is missing")
                else:
                    diffs = [
                        f"{label}: {t.get(field, '—')}"
                        for field, label in CompareService._SSID_FIELDS
                        if (
                            CompareService._ssid_key(t) != CompareService._ssid_key(src)
                            if field == "name"
                            else t.get(field) != src.get(field)
                        )
                    ]
                    cells[net["id"]] = (
                        Cell("match", "SSID settings match")
                        if not diffs
                        else Cell("different", "; ".join(diffs))
                    )
            rows.append(CompareRow(
                label=f"{name} [{ssid_source}]",
                source_display=display,
                cells=cells,
            ))

        source_keys = set(src_by_name)
        extra_keys: dict[tuple[str, str], set[str]] = {}
        extra_ssids: dict[tuple[str, str], dict[str, Any]] = {}
        for net in targets:
            for ssid in target_data[net["id"]]["ssids"]:
                key = CompareService._ssid_key(ssid)
                if key not in source_keys:
                    extra_keys.setdefault(key, set()).add(net["id"])
                    extra_ssids.setdefault(key, ssid)

        for (ssid_source, _), network_ids in sorted(extra_keys.items()):
            ssid = extra_ssids[(ssid_source, _)]
            name = ssid.get("name") or "Unnamed SSID"
            display = "Extra SSID, not in source"
            cells = {
                net["id"]: (
                    Cell("different", "Extra SSID name not in source")
                    if net["id"] in network_ids
                    else Cell("na", "Not present on this target")
                )
                for net in targets
            }
            rows.append(CompareRow(
                label=f"[EXTRA] {name} [{ssid_source}]",
                source_display=display,
                cells=cells,
            ))
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

    def _safe_rules(self, organization_id: str, network_id: str) -> RuleSet:
        try:
            return self.client.get_rules(organization_id, network_id)
        except Exception:
            return RuleSet()

    def _read_ssids(self, network_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        ssids: list[dict[str, Any]] = []
        errors: list[str] = []
        for source, reader in (
            ("Dashboard Wi-Fi", self.client.get_wireless_ssids),
            ("MX", self.client.get_appliance_ssids),
        ):
            try:
                records = ({**ssid, "ssidSource": source} for ssid in reader(network_id) or [])
                ssids.extend(ssid for ssid in records if not self._is_dashboard_placeholder_ssid(ssid))
            except Exception as exc:
                errors.append(f"{source}: {exc}")
        return ssids, errors

    def _safe_ssids(self, network_id: str) -> list[dict[str, Any]]:
        """Backward-compatible helper for callers that only need SSID records."""
        return self._read_ssids(network_id)[0]

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

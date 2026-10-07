"""Network creation and template-based cloning service for V1."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from meraki_client.client_v1 import MerakiVpnClientV1
from rules.models import RuleSet


@dataclass
class CloneableConfig:
    """Configuration snapshot read from a template network.

    Only items that are safe to duplicate across networks are captured here.
    Values that must be unique per network (subnets, IP addresses, PSKs) are not copied.
    """
    vpn_exclusions: RuleSet = field(default_factory=RuleSet)
    tags: list[str] = field(default_factory=list)
    static_routes: list[dict[str, Any]] = field(default_factory=list)
    l3_firewall_rules: list[dict[str, Any]] = field(default_factory=list)
    l7_firewall_rules: list[dict[str, Any]] = field(default_factory=list)
    ssids: list[dict[str, Any]] = field(default_factory=list)
    appliance_settings: dict[str, Any] = field(default_factory=dict)
    group_policies: list[dict[str, Any]] = field(default_factory=list)
    source_product_types: list[str] = field(default_factory=list)
    source_timezone: str = "America/Los_Angeles"


@dataclass
class CreateNetworkOptions:
    name: str
    timezone: str
    notes: str = ""
    copy_tags: bool = True
    copy_vpn_exclusions: bool = True
    copy_static_routes: bool = False
    copy_l3_firewall: bool = False
    copy_l7_firewall: bool = False
    copy_ssids: bool = False
    copy_network_settings: bool = False
    copy_group_policies: bool = False
    # slot_number → PSK string (only for PSK-mode SSIDs; empty string = skip)
    ssid_psks: dict = field(default_factory=dict)


@dataclass
class CreateNetworkResult:
    success: bool = False
    network_id: str = ""
    network_name: str = ""
    error: str = ""
    steps: list[tuple[str, bool, str]] = field(default_factory=list)

    def add_step(self, label: str, ok: bool, detail: str = "") -> None:
        self.steps.append((label, ok, detail))

    @property
    def all_steps_ok(self) -> bool:
        return all(ok for _, ok, _ in self.steps)


class NetworkService:
    """Creates new MX networks and optionally applies configuration from a template."""

    def __init__(self, client: MerakiVpnClientV1) -> None:
        self.client = client

    def get_cloneable_config(
        self,
        organization_id: str,
        source_network: dict[str, Any],
    ) -> CloneableConfig:
        """Read all cloneable settings from the source network in one pass."""
        network_id = source_network["id"]
        config = CloneableConfig(
            tags=list(source_network.get("tags") or []),
            source_product_types=list(source_network.get("productTypes") or ["appliance"]),
            source_timezone=source_network.get("timeZone") or "America/Los_Angeles",
        )
        config.vpn_exclusions = self.client.get_rules(organization_id, network_id)
        try:
            config.static_routes = self.client.get_appliance_static_routes(network_id)
        except Exception:
            config.static_routes = []
        try:
            l3 = self.client.get_appliance_firewall_l3_rules(network_id)
            config.l3_firewall_rules = l3.get("rules", [])
        except Exception:
            config.l3_firewall_rules = []
        try:
            l7 = self.client.get_appliance_firewall_l7_rules(network_id)
            config.l7_firewall_rules = l7.get("rules", [])
        except Exception:
            config.l7_firewall_rules = []
        try:
            config.ssids = self.client.get_appliance_ssids(network_id) or []
        except Exception:
            config.ssids = []
        try:
            config.appliance_settings = self.client.get_appliance_settings(network_id) or {}
        except Exception:
            config.appliance_settings = {}
        try:
            config.group_policies = self.client.get_group_policies(network_id) or []
        except Exception:
            config.group_policies = []
        return config

    def create_and_configure(
        self,
        organization_id: str,
        options: CreateNetworkOptions,
        config: CloneableConfig,
        progress: Callable[[str], None] | None = None,
    ) -> CreateNetworkResult:
        """Create the network then apply each selected config item in sequence.

        A failure in any optional step does NOT roll back the network creation.
        The result contains the outcome of every individual step.
        """
        result = CreateNetworkResult()

        if progress:
            progress(f"Creating network '{options.name}'…")
        try:
            new_net = self.client.create_network(
                organization_id,
                name=options.name,
                product_types=config.source_product_types,
                timezone=options.timezone,
                notes=options.notes,
                tags=config.tags if options.copy_tags else None,
            )
            result.network_id = new_net["id"]
            result.network_name = new_net.get("name", options.name)
            result.success = True
            result.add_step("Create network", True, f"Network ID: {new_net['id']}")
        except Exception as exc:
            result.error = f"Network creation failed: {exc}"
            result.add_step("Create network", False, str(exc))
            return result

        if options.copy_tags and config.tags:
            result.add_step("Copy tags", True, f"{len(config.tags)} tag(s) applied")

        if options.copy_vpn_exclusions:
            rule_count = len(config.vpn_exclusions.rules)
            if rule_count:
                if progress:
                    progress("Applying VPN exclusion rules…")
                try:
                    self.client.update_rules(result.network_id, config.vpn_exclusions)
                    result.add_step(
                        "Copy VPN exclusions", True, f"{rule_count} rule(s) applied"
                    )
                except Exception as exc:
                    result.add_step("Copy VPN exclusions", False, str(exc))
            else:
                result.add_step("Copy VPN exclusions", True, "Source has no exclusions")

        if options.copy_static_routes and config.static_routes:
            if progress:
                progress("Copying static routes…")
            copied = 0
            errors: list[str] = []
            for route in config.static_routes:
                try:
                    self.client.create_appliance_static_route(
                        result.network_id,
                        name=route.get("name", ""),
                        subnet=route.get("subnet", ""),
                        gateway_ip=route.get("gatewayIp", ""),
                    )
                    copied += 1
                except Exception as exc:
                    errors.append(str(exc))
            ok = len(errors) == 0
            detail = f"{copied}/{len(config.static_routes)} copied"
            if errors:
                detail += f"; {len(errors)} failed"
            result.add_step("Copy static routes", ok, detail)

        if options.copy_l3_firewall and config.l3_firewall_rules:
            if progress:
                progress("Applying L3 firewall rules…")
            try:
                # Exclude the generated "Default rule" from the API response
                rules = [
                    r for r in config.l3_firewall_rules
                    if str(r.get("comment", "")).lower() != "default rule"
                ]
                if rules:
                    self.client.update_appliance_firewall_l3_rules(result.network_id, rules)
                result.add_step(
                    "Copy L3 firewall rules", True, f"{len(rules)} rule(s) applied"
                )
            except Exception as exc:
                result.add_step("Copy L3 firewall rules", False, str(exc))

        if options.copy_l7_firewall and config.l7_firewall_rules:
            if progress:
                progress("Applying L7 firewall rules…")
            try:
                self.client.update_appliance_firewall_l7_rules(
                    result.network_id, config.l7_firewall_rules
                )
                result.add_step(
                    "Copy L7 firewall rules",
                    True,
                    f"{len(config.l7_firewall_rules)} rule(s) applied",
                )
            except Exception as exc:
                result.add_step("Copy L7 firewall rules", False, str(exc))

        if options.copy_ssids and config.ssids:
            if progress:
                progress("Copying SSID settings…")
            copied = 0
            psks_set = 0
            errors: list[str] = []
            _SAFE_SSID_FIELDS = {
                "name", "enabled", "authMode", "encryptionMode",
                "wpaEncryptionMode", "visible", "defaultVlanId",
            }
            for ssid in config.ssids:
                number = ssid.get("number")
                if number is None:
                    continue
                kwargs = {k: v for k, v in ssid.items() if k in _SAFE_SSID_FIELDS}
                if not kwargs:
                    continue
                # Inject PSK if the user provided one for this slot
                psk = (options.ssid_psks or {}).get(number, "").strip()
                if psk and ssid.get("authMode") == "psk":
                    kwargs["psk"] = psk
                    psks_set += 1
                try:
                    self.client.update_appliance_ssid(result.network_id, number, **kwargs)
                    copied += 1
                except Exception as exc:
                    errors.append(f"SSID {number}: {exc}")
            ok = len(errors) == 0
            detail = f"{copied}/{len(config.ssids)} SSID slot(s) configured"
            if psks_set:
                detail += f", {psks_set} PSK(s) set"
            skipped_psks = sum(
                1 for s in config.ssids
                if s.get("authMode") == "psk"
                and not (options.ssid_psks or {}).get(s.get("number"), "").strip()
            )
            if skipped_psks:
                detail += f"  ({skipped_psks} PSK(s) skipped — update manually in dashboard)"
            if errors:
                detail += f"; {len(errors)} failed"
            result.add_step("Copy SSID settings", ok, detail)

        if options.copy_network_settings and config.appliance_settings:
            if progress:
                progress("Applying network settings…")
            _SAFE_SETTINGS_FIELDS = {"clientTrackingMethod", "deploymentMode"}
            kwargs = {
                k: v for k, v in config.appliance_settings.items()
                if k in _SAFE_SETTINGS_FIELDS and v
            }
            if kwargs:
                try:
                    self.client.update_appliance_settings(result.network_id, **kwargs)
                    result.add_step(
                        "Copy network settings", True,
                        ", ".join(f"{k}={v}" for k, v in kwargs.items()),
                    )
                except Exception as exc:
                    result.add_step("Copy network settings", False, str(exc))
            else:
                result.add_step("Copy network settings", True, "No applicable settings on source")

        if options.copy_group_policies and config.group_policies:
            if progress:
                progress("Copying group policies…")
            added = 0
            skipped = 0
            errors: list[str] = []
            existing = self.client.get_group_policies(result.network_id)
            existing_names = {(p.get("name") or "").strip().lower() for p in existing}
            for policy in config.group_policies:
                name_key = (policy.get("name") or "").strip().lower()
                if not name_key:
                    continue
                if name_key in existing_names:
                    skipped += 1
                    continue
                try:
                    self.client.create_group_policy(result.network_id, policy)
                    added += 1
                except Exception as exc:
                    errors.append(f"{policy.get('name', '?')}: {exc}")
            ok = len(errors) == 0
            detail = f"{added} added, {skipped} already existed"
            if errors:
                detail += f"; {len(errors)} failed"
            result.add_step("Copy group policies", ok, detail)

        return result

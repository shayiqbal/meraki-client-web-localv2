"""Extended Meraki client with network creation and configuration cloning for V1."""
from __future__ import annotations

from typing import Any

import requests

from meraki_client.client import MerakiVpnClient
from meraki_client.exceptions import MerakiClientError


class MerakiVpnClientV1(MerakiVpnClient):
    """Extends the base client with network management operations.

    All base VPN-exclusion methods are inherited unchanged.
    """

    # ── Network management ─────────────────────────────────────────────────

    def get_network(self, network_id: str) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.networks.getNetwork(network_id),
            "get network",
            network_id=network_id,
        )

    def create_network(
        self,
        organization_id: str,
        name: str,
        product_types: list[str],
        timezone: str = "America/Los_Angeles",
        notes: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "name": name.strip(),
            "productTypes": product_types,
            "timeZone": timezone,
        }
        if notes.strip():
            kwargs["notes"] = notes.strip()
        if tags:
            kwargs["tags"] = tags
        return self._call(
            lambda: self.dashboard.organizations.createOrganizationNetwork(
                organization_id, **kwargs
            ),
            "create network",
            organization_id=organization_id,
            name=name,
        )

    def update_network(self, network_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.networks.updateNetwork(network_id, **kwargs),
            "update network",
            network_id=network_id,
        )

    # ── Devices ────────────────────────────────────────────────────────────

    def get_network_devices(self, network_id: str) -> list[dict[str, Any]]:
        """All devices claimed into a network.

        Each item carries ``serial``, ``name``, ``model``, ``mac``, ``address``,
        ``lat``, ``lng``, ``notes``, ``tags`` and ``networkId``.
        """
        return self._call(
            lambda: self.dashboard.networks.getNetworkDevices(network_id),
            "list network devices",
            network_id=network_id,
        )

    def get_device(self, serial: str) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.devices.getDevice(serial),
            "get device",
            serial=serial,
        )

    def update_device_address(
        self,
        serial: str,
        address: str,
        move_map_marker: bool = True,
    ) -> dict[str, Any]:
        """Set a device's physical address and reposition its dashboard map marker.

        Deliberately narrow: only ``address`` and ``moveMapMarker`` are ever sent
        to ``PUT /devices/{serial}``. The Meraki SDK builds the request body from
        the keyword arguments it receives, so no other device attribute (name,
        tags, notes, floor plan, switch profile) can be altered by this call.

        ``lat``/``lng`` are intentionally *never* sent: the Meraki API documents
        ``moveMapMarker`` as "Only applies when lat and lng are not specified",
        so including them would suppress geocoding and leave the map marker where
        it was.
        """
        return self._call(
            lambda: self.dashboard.devices.updateDevice(
                serial,
                address=address,
                moveMapMarker=move_map_marker,
            ),
            "update device address",
            serial=serial,
        )

    # ── Appliance static routes ────────────────────────────────────────────

    def get_appliance_static_routes(self, network_id: str) -> list[dict[str, Any]]:
        return self._call(
            lambda: self.dashboard.appliance.getNetworkApplianceStaticRoutes(network_id),
            "get static routes",
            network_id=network_id,
        )

    def create_appliance_static_route(
        self,
        network_id: str,
        name: str,
        subnet: str,
        gateway_ip: str,
    ) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.appliance.createNetworkApplianceStaticRoute(
                network_id,
                name=name,
                subnet=subnet,
                gatewayIp=gateway_ip,
            ),
            "create static route",
            network_id=network_id,
        )

    # ── Appliance firewall rules ───────────────────────────────────────────

    def get_appliance_firewall_l3_rules(self, network_id: str) -> dict[str, Any]:
        try:
            return self._call(
                lambda: self.dashboard.appliance.getNetworkApplianceFirewallL3FirewallRules(
                    network_id
                ),
                "get L3 firewall rules",
                network_id=network_id,
            )
        except MerakiClientError:
            return {"rules": []}

    def update_appliance_firewall_l3_rules(
        self,
        network_id: str,
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.appliance.updateNetworkApplianceFirewallL3FirewallRules(
                network_id, rules=rules
            ),
            "update L3 firewall rules",
            network_id=network_id,
        )

    def get_appliance_firewall_l7_rules(self, network_id: str) -> dict[str, Any]:
        try:
            return self._call(
                lambda: self.dashboard.appliance.getNetworkApplianceFirewallL7FirewallRules(
                    network_id
                ),
                "get L7 firewall rules",
                network_id=network_id,
            )
        except MerakiClientError:
            return {"rules": []}

    def update_appliance_firewall_l7_rules(
        self,
        network_id: str,
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call(
            lambda: self.dashboard.appliance.updateNetworkApplianceFirewallL7FirewallRules(
                network_id, rules=rules
            ),
            "update L7 firewall rules",
            network_id=network_id,
        )

    def get_appliance_ssids(self, network_id: str) -> list[dict[str, Any]]:
        return self._call(
            lambda: self.dashboard.appliance.getNetworkApplianceSsids(network_id),
            "get appliance SSIDs",
            network_id=network_id,
        )

    def get_wireless_ssids(self, network_id: str) -> list[dict[str, Any]]:
        return self._call(
            lambda: self.dashboard.wireless.getNetworkWirelessSsids(network_id),
            "get wireless SSIDs",
            network_id=network_id,
        )

    def update_appliance_ssid(
        self, network_id: str, number: int | str, **kwargs: Any
    ) -> dict[str, Any]:
        """Update a single MX SSID slot (name, enabled, authMode, etc.)."""
        return self._call(
            lambda: self.dashboard.appliance.updateNetworkApplianceSsid(
                network_id, str(number), **kwargs
            ),
            "update appliance SSID",
            network_id=network_id,
            number=number,
        )

    def get_appliance_settings(self, network_id: str) -> dict[str, Any]:
        try:
            return self._call(
                lambda: self.dashboard.appliance.getNetworkApplianceSettings(network_id),
                "get appliance settings",
                network_id=network_id,
            )
        except MerakiClientError:
            return {}

    def update_appliance_settings(
        self, network_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Update appliance settings (clientTrackingMethod, deploymentMode, etc.)."""
        return self._call(
            lambda: self.dashboard.appliance.updateNetworkApplianceSettings(
                network_id, **kwargs
            ),
            "update appliance settings",
            network_id=network_id,
        )

    # ── Network syslog servers ─────────────────────────────────────────────

    # The organization roles endpoint returns current camel-case enum values,
    # while the (deprecated but still write-capable) per-network endpoint
    # accepts the corresponding legacy labels.
    _SYSLOG_ROLE_LABELS = {
        "wirelessEventLog": "Wireless event log",
        "applianceEventLog": "Appliance event log",
        "switchEventLog": "Switch event log",
        "airMarshalEvents": "Air Marshal events",
        "flows": "Flows",
        "urls": "URLs",
        "idsAlerts": "IDS alerts",
        "securityEvents": "Security events",
        "applianceIpfilter": "Appliance IP filter",
        "switchIpfilter": "Switch IP filter",
    }

    def get_network_syslog_servers(self, network_id: str) -> dict[str, Any]:
        """Return a network's configuration from Meraki's syslog API."""
        return self._syslog_request("GET", f"/networks/{network_id}/syslogServers")

    def update_network_syslog_servers(
        self, network_id: str, servers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace a network's complete syslog server list."""
        legacy_servers = [
            {
                **server,
                "roles": [self._SYSLOG_ROLE_LABELS.get(role, role) for role in server.get("roles", [])],
            }
            for server in servers
        ]
        return self._syslog_request(
            "PUT", f"/networks/{network_id}/syslogServers", {"servers": legacy_servers}
        )

    def get_organization_syslog_roles(self, organization_id: str) -> dict[str, Any]:
        """Return every network's available syslog roles across all pages.

        The byNetwork endpoint paginates via a ``Link`` header. Fetching only
        the first page would silently report zero supported roles for any
        network beyond it, which made Copy Syslog treat every role -
        including Air Marshal - as unsupported for large organizations.
        """
        items: list[Any] = []
        path = f"/organizations/{organization_id}/devices/syslog/servers/roles/byNetwork?perPage=1000"
        while path:
            body, link_header = self._syslog_page("GET", path)
            page_items = body.get("items", []) if isinstance(body, dict) else body
            items.extend(page_items or [])
            path = self._next_page_path(link_header)
        return {"items": items}

    def _syslog_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call the current syslog endpoint not yet exposed by the pinned SDK."""
        body, _ = self._syslog_page(method, path, payload)
        return body

    def _syslog_page(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], str]:
        """Call a syslog endpoint and also return its raw Link header for pagination."""
        headers = {"Authorization": f"Bearer {self.settings.api_key}", "X-Cisco-Meraki-API-Key": self.settings.api_key, "Content-Type": "application/json"}
        captured: dict[str, str] = {}

        def _do() -> dict[str, Any]:
            response = requests.request(method, f"https://api.meraki.com/api/v1{path}", json=payload, headers=headers, timeout=30)
            if response.status_code == 429:
                raise MerakiClientError("Rate-limited by Meraki. Retrying…")
            if not response.ok:
                raise MerakiClientError(f"syslog request failed: HTTP {response.status_code} — {response.text[:200]}")
            response_headers = getattr(response, "headers", None)
            captured["link"] = response_headers.get("Link", "") if response_headers else ""
            return response.json()

        body = self._call(_do, f"{method.lower()} syslog servers", path=path)
        return body, captured.get("link", "")

    @staticmethod
    def _next_page_path(link_header: str) -> str | None:
        """Extract the relative 'next' page path from a Meraki Link header."""
        if not link_header:
            return None
        for part in link_header.split(","):
            segment = part.strip()
            if "next" not in segment.split(";", 1)[-1]:
                continue
            start, end = segment.find("<"), segment.find(">")
            if start == -1 or end == -1:
                continue
            url = segment[start + 1:end]
            return url.removeprefix("https://api.meraki.com/api/v1")
        return None

    # ── Group policies ─────────────────────────────────────────────────────────

    def get_group_policies(self, network_id: str) -> list[dict[str, Any]]:
        """Return all group policies defined on a network."""
        return self._call(
            lambda: self.dashboard.networks.getNetworkGroupPolicies(network_id),
            "get group policies",
            network_id=network_id,
        )

    @staticmethod
    def _group_policy_payload(policy_data: dict[str, Any]) -> dict[str, Any]:
        """Only forward documented writable Group Policy attributes to Meraki."""
        writable = {
            "bandwidth", "firewallAndTrafficShaping", "scheduling", "vlanTagging",
            "splashAuthSettings", "contentFiltering", "bonjourForwarding",
        }
        return {key: value for key, value in policy_data.items() if key in writable}

    def create_group_policy(
        self,
        network_id: str,
        policy_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a group policy on a network.

        ``groupPolicyId`` is stripped from *policy_data* before the call —
        Meraki assigns its own ID per network.
        """
        name = policy_data.get("name", "")
        kwargs = self._group_policy_payload(policy_data)
        return self._call(
            lambda: self.dashboard.networks.createNetworkGroupPolicy(
                network_id, name, **kwargs
            ),
            "create group policy",
            network_id=network_id,
        )

    def update_group_policy(
        self,
        network_id: str,
        group_policy_id: str,
        policy_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace all writable settings on an existing network-local policy."""
        kwargs = self._group_policy_payload(policy_data)
        name = policy_data.get("name")
        if name:
            kwargs["name"] = name
        return self._call(
            lambda: self.dashboard.networks.updateNetworkGroupPolicy(
                network_id, group_policy_id, **kwargs
            ),
            "update group policy",
            network_id=network_id,
            group_policy_id=group_policy_id,
        )

    def delete_group_policy(self, network_id: str, group_policy_id: str) -> None:
        """Delete a policy created by the current session's rollback-able operation."""
        self._call(
            lambda: self.dashboard.networks.deleteNetworkGroupPolicy(network_id, group_policy_id),
            "delete group policy",
            network_id=network_id,
            group_policy_id=group_policy_id,
        )

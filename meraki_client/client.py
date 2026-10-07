"""Narrow Meraki SDK wrapper for VPN exclusions only."""
from __future__ import annotations

import logging
from typing import Any

import meraki
import requests as _requests

from config.settings import Settings
from meraki_client.exceptions import (
    AuthenticationError,
    CompatibilityError,
    MerakiClientError,
)
from meraki_client.retry import RetryPolicy, status_code
from rules.models import RuleCategory, RuleSet, RuleSource, VpnExclusionRule

_MERAKI_BASE = "https://api.meraki.com/api/v1"


class MerakiVpnClient:
    def __init__(
        self,
        settings: Settings,
        logger: logging.Logger,
        dashboard: Any | None = None,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.logger = logger
        self.dashboard = dashboard or meraki.DashboardAPI(
            api_key=settings.api_key,
            suppress_logging=True,
            print_console=False,
            wait_on_rate_limit=False,
            # The SDK treats zero as "perform zero HTTP attempts" and later
            # dereferences a None response. One attempt disables SDK-level
            # retries while allowing this client's RetryPolicy to control them.
            maximum_retries=1,
        )
        self.retries = 0
        self.retry = RetryPolicy(
            max_retries=settings.max_retries,
            base_seconds=settings.retry_base_seconds,
            on_retry=self._on_retry,
        )

    def _on_retry(self, exc: BaseException, attempt: int, delay: float) -> None:
        self.retries += 1
        self.logger.warning(
            "Meraki API retry action=%s attempt=%s delay_seconds=%s status=%s",
            "retry", attempt, delay, status_code(exc),
            extra={
                "context": {
                    "action": "retry",
                    "retry_count": attempt,
                    "delay_seconds": delay,
                    "status": status_code(exc),
                }
            },
        )

    def _call(self, operation: Any, action: str, **context: Any) -> Any:
        try:
            return self.retry.run(operation)
        except Exception as exc:
            code = status_code(exc)
            self.logger.error(
                "Meraki API operation failed action=%s status=%s",
                action, code,
                extra={"context": {"action": action, **context, "status": code}},
            )
            if code in {401, 403}:
                raise AuthenticationError(
                    "Meraki rejected the API key or the account lacks permission."
                ) from exc
            if code == 429:
                raise MerakiClientError(
                    f"{action} is temporarily rate-limited by Meraki for this "
                    "organization. Close other Meraki tools, wait a few minutes, "
                    "then click Load networks once."
                ) from exc
            raise MerakiClientError(f"{action} failed") from exc

    def organizations(self) -> list[dict[str, Any]]:
        return self._call(
            self.dashboard.organizations.getOrganizations, "list organizations"
        )

    def all_networks(self, organization_id: str) -> list[dict[str, Any]]:
        """Every network in the organization, unfiltered by product type.

        ``networks()`` narrows the result to appliance networks because the VPN
        exclusion features only apply to MX. Device-level features (addresses,
        inventory) need wireless/switch/camera networks too, so they use this.
        """
        return self._call(
            lambda: self.dashboard.organizations.getOrganizationNetworks(
                organization_id, total_pages="all"
            ),
            "list networks",
            organization_id=organization_id,
        )

    def networks(self, organization_id: str) -> list[dict[str, Any]]:
        """Appliance-capable networks only (used by the VPN exclusion features)."""
        return [
            item
            for item in self.all_networks(organization_id)
            if "appliance" in item.get("productTypes", [])
            or item.get("type") in {"appliance", "combined"}
        ]

    def _organization_rules(
        self, organization_id: str, network_id: str
    ) -> dict[str, Any]:
        response = self._call(
            lambda: self.dashboard.appliance.getOrganizationApplianceTrafficShapingVpnExclusionsByNetwork(
                organization_id, total_pages="all", networkIds=[network_id]
            ),
            "read VPN exclusions",
            organization_id=organization_id,
            network_id=network_id,
        )
        items = response.get("items", response) if isinstance(response, dict) else response
        for item in items:
            if item.get("networkId") == network_id:
                return item
        return {
            "networkId": network_id,
            "custom": [],
            "majorApplications": [],
            "applications": [],
        }

    @staticmethod
    def to_ruleset(data: dict[str, Any]) -> RuleSet:
        rules: list[VpnExclusionRule] = []
        for category in RuleCategory:
            for item in data.get(category.value, []) or []:
                source = item.get("source")
                rules.append(
                    VpnExclusionRule(
                        category=category,
                        order=len(rules),
                        protocol=item.get("protocol", "any"),
                        destination=item.get("destination"),
                        port=item.get("port", "any"),
                        application_id=item.get("id"),
                        name=item.get("name"),
                        source=RuleSource.model_validate(source) if source else None,
                    )
                )
        return RuleSet(rules=rules, metadata={
            "networkId": data.get("networkId"),
            "networkName": data.get("networkName"),
        })

    def get_rules(
        self, organization_id: str, network_id: str
    ) -> RuleSet:
        return self.to_ruleset(self._organization_rules(organization_id, network_id))

    def update_rules(self, network_id: str, rules: RuleSet) -> dict[str, Any]:
        payload = rules.payload()
        has_apps = bool(payload["applications"])

        if has_apps and not self.settings.early_access:
            raise CompatibilityError(
                "NBAR application exclusions require early-access support. "
                "Set MERAKI_ENABLE_EARLY_ACCESS=true after enabling the feature in Meraki."
            )

        if has_apps and self.settings.early_access:
            # The Meraki Python SDK does not include 'applications' in its
            # body_params for this endpoint, so it silently drops the array.
            # Bypass the SDK and use a direct HTTP PUT so all three arrays are sent.
            return self._update_rules_direct(network_id, payload)

        # SDK path — no applications rules, safe to use SDK wrapper
        kwargs: dict[str, Any] = {
            "custom": payload["custom"],
            "majorApplications": payload["majorApplications"],
        }
        try:
            return self._call(
                lambda: self.dashboard.appliance.updateNetworkApplianceTrafficShapingVpnExclusions(
                    network_id, **kwargs
                ),
                "update VPN exclusions",
                network_id=network_id,
            )
        except MerakiClientError as exc:
            if not isinstance(exc.__cause__, TypeError):
                raise
            raise CompatibilityError(
                "The installed Meraki SDK does not accept early-access application rules. "
                "Upgrade the meraki package or disable early access."
            ) from exc

    def _update_rules_direct(self, network_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """PUT /networks/{id}/appliance/trafficShaping/vpnExclusions directly.

        Used when the payload includes an 'applications' (NBAR) array because
        the Meraki Python SDK silently drops that field from the request body.
        """
        url = f"{_MERAKI_BASE}/networks/{network_id}/appliance/trafficShaping/vpnExclusions"
        headers = {
            "Content-Type": "application/json",
            "X-Cisco-Meraki-API-Key": self.settings.api_key,
        }

        def _do() -> dict[str, Any]:
            resp = _requests.put(url, json=payload, headers=headers, timeout=30)
            if resp.status_code in {401, 403}:
                raise AuthenticationError(
                    "Meraki rejected the API key or the account lacks permission."
                )
            if resp.status_code == 429:
                raise MerakiClientError("Rate-limited by Meraki. Retrying…")
            if not resp.ok:
                raise MerakiClientError(f"update VPN exclusions failed: HTTP {resp.status_code}")
            return resp.json()

        return self.retry.run(_do)

"""Preview and bulk-update network syslog server configurations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meraki_client.client_v1 import MerakiVpnClientV1


UPDATE_MODES = {"replace", "merge"}


@dataclass(slots=True)
class SyslogPreview:
    network_id: str
    network_name: str
    status: str
    detail: str
    current_servers: list[dict[str, Any]]
    proposed_servers: list[dict[str, Any]]


@dataclass(slots=True)
class SyslogResult:
    network_id: str
    network_name: str
    success: bool
    status: str
    server_count: int = 0
    error: str = ""


def normalize_servers(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize the minimal payload accepted by Meraki.

    A server is unique by host and UDP port. Duplicate rows are combined so an
    operator can safely select roles in more than one row without accidentally
    replacing a previous role selection.
    """
    if not servers:
        raise ValueError("Add at least one syslog server.")

    normalized: dict[tuple[str, int], dict[str, Any]] = {}
    for index, server in enumerate(servers, start=1):
        host = str(server.get("host") or "").strip()
        raw_port = server.get("port")
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise ValueError(f"Server {index}: port must be a whole number.") from None
        if not host:
            raise ValueError(f"Server {index}: host or IP address is required.")
        if not 1 <= port <= 65535:
            raise ValueError(f"Server {index}: port must be between 1 and 65535.")

        roles = sorted({str(role).strip() for role in server.get("roles") or [] if str(role).strip()})
        if not roles:
            raise ValueError(f"Server {index}: select at least one event role.")
        key = (host.casefold(), port)
        if key not in normalized:
            normalized[key] = {"host": host, "port": port, "roles": roles}
        else:
            normalized[key]["roles"] = sorted(set(normalized[key]["roles"]) | set(roles))
    return list(normalized.values())


def clean_servers(servers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize a Dashboard response to fields safe to send back on update."""
    cleaned: list[dict[str, Any]] = []
    for server in servers or []:
        host = str(server.get("host") or "").strip()
        port = server.get("port")
        roles = [str(role).strip() for role in server.get("roles") or [] if str(role).strip()]
        if host and port is not None and roles:
            cleaned.append({
                "host": host,
                "port": int(port),
                "roles": sorted(set(roles)),
                **({"transportProtocol": server["transportProtocol"]} if server.get("transportProtocol") else {}),
                **({"encryption": server["encryption"]} if server.get("encryption") else {}),
            })
    return sorted(cleaned, key=lambda server: (server["host"].casefold(), server["port"]))


def merge_servers(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine configured and entered destinations by host/port, unioning roles."""
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for server in clean_servers(existing) + additions:
        key = (server["host"].casefold(), server["port"])
        if key not in merged:
            merged[key] = {**server, "roles": list(server["roles"])}
        else:
            merged[key]["roles"] = sorted(set(merged[key]["roles"]) | set(server["roles"]))
    return sorted(merged.values(), key=lambda server: (server["host"].casefold(), server["port"]))


class SyslogService:
    def __init__(self, client: MerakiVpnClientV1) -> None:
        self.client = client

    def list_networks(self, organization_id: str) -> list[dict[str, Any]]:
        networks = self.client.all_networks(organization_id)
        return sorted(networks, key=lambda network: (network.get("name") or "").casefold())

    def list_roles(self, organization_id: str) -> list[dict[str, str]]:
        """Return the union of current API-supported role values and labels."""
        response = self.client.get_organization_syslog_roles(organization_id)
        items = response.get("items", response) if isinstance(response, dict) else response
        roles: dict[str, str] = {}
        for item in items or []:
            for role in item.get("available", []) or []:
                if isinstance(role, dict) and role.get("value"):
                    roles[str(role["value"])] = str(role.get("name") or role["value"])
        return [{"value": value, "label": label} for value, label in sorted(roles.items(), key=lambda item: item[1].casefold())]

    def preview(
        self,
        networks: list[dict[str, Any]],
        servers: list[dict[str, Any]],
        mode: str,
    ) -> list[SyslogPreview]:
        desired = normalize_servers(servers)
        self._validate_mode(mode)
        previews: list[SyslogPreview] = []
        for network in networks:
            network_id = network.get("id", "")
            name = network.get("name") or network_id or "(unnamed network)"
            if not network_id:
                previews.append(SyslogPreview("", name, "invalid", "Network has no ID.", [], []))
                continue
            try:
                current = clean_servers((self.client.get_network_syslog_servers(network_id) or {}).get("servers"))
                proposed = desired if mode == "replace" else merge_servers(current, desired)
                status = "unchanged" if proposed == current else "update"
                detail = "Already configured as requested." if status == "unchanged" else "Syslog configuration will be updated."
                previews.append(SyslogPreview(network_id, name, status, detail, current, proposed))
            except Exception as exc:
                previews.append(SyslogPreview(network_id, name, "unavailable", str(exc), [], []))
        return previews

    def execute(
        self,
        networks: list[dict[str, Any]],
        servers: list[dict[str, Any]],
        mode: str,
    ) -> list[SyslogResult]:
        # Re-read each network so merge mode does not remove a destination added
        # after preview. This also makes execution safe after a long review.
        previews = self.preview(networks, servers, mode)
        results: list[SyslogResult] = []
        for preview in previews:
            if preview.status == "unavailable":
                results.append(SyslogResult(preview.network_id, preview.network_name, False, "unavailable", error=preview.detail))
                continue
            if preview.status == "invalid":
                results.append(SyslogResult(preview.network_id, preview.network_name, False, "invalid", error=preview.detail))
                continue
            if preview.status == "unchanged":
                results.append(SyslogResult(preview.network_id, preview.network_name, True, "unchanged", len(preview.current_servers)))
                continue
            try:
                response = self.client.update_network_syslog_servers(preview.network_id, preview.proposed_servers) or {}
                final = clean_servers(response.get("servers", preview.proposed_servers))
                results.append(SyslogResult(preview.network_id, preview.network_name, True, "updated", len(final)))
            except Exception as exc:
                results.append(SyslogResult(preview.network_id, preview.network_name, False, "failed", error=str(exc)))
        return results

    @staticmethod
    def _validate_mode(mode: str) -> None:
        if mode not in UPDATE_MODES:
            raise ValueError("Update mode must be 'replace' or 'merge'.")

from __future__ import annotations

import unittest

from services.syslog_service import SyslogService, merge_servers, normalize_servers


class FakeClient:
    _SYSLOG_ROLE_LABELS = {"applianceEventLog": "Appliance event log"}

    def __init__(self) -> None:
        self.settings = {
            "one": [{"host": "old.example", "port": 514, "roles": ["Flows"]}],
            "two": [{"host": "log.example", "port": 514, "roles": ["URLs"]}],
        }
        self.updated: list[tuple[str, list[dict]]] = []

    def get_network_syslog_servers(self, network_id: str) -> dict:
        if network_id == "unsupported":
            raise RuntimeError("Not supported")
        return {"servers": self.settings.get(network_id, [])}

    def update_network_syslog_servers(self, network_id: str, servers: list[dict]) -> dict:
        self.updated.append((network_id, servers))
        self.settings[network_id] = servers
        return {"servers": servers}


class SyslogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.service = SyslogService(self.client)  # type: ignore[arg-type]
        self.networks = [{"id": "one", "name": "One"}, {"id": "two", "name": "Two"}]
        self.new_server = [{"host": "log.example", "port": 514, "roles": ["Security events"]}]

    def test_normalize_combines_duplicate_host_port_roles(self) -> None:
        servers = normalize_servers([
            {"host": "LOG.example", "port": "514", "roles": ["Flows"]},
            {"host": "log.example", "port": 514, "roles": ["URLs"]},
        ])
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["roles"], ["Flows", "URLs"])

    def test_replace_preview_uses_exact_entered_list(self) -> None:
        preview = self.service.preview(self.networks, self.new_server, "replace")
        self.assertTrue(all(item.proposed_servers == self.new_server for item in preview))

    def test_merge_retains_old_server_and_unions_matching_roles(self) -> None:
        merged = merge_servers(
            [{"host": "log.example", "port": 514, "roles": ["Flows"]}],
            self.new_server,
        )
        self.assertEqual(merged[0]["roles"], ["Flows", "Security events"])

    def test_execute_keeps_going_when_a_network_is_unsupported(self) -> None:
        results = self.service.execute(
            self.networks + [{"id": "unsupported", "name": "Unsupported"}],
            self.new_server,
            "replace",
        )
        self.assertEqual([result.success for result in results], [True, True, False])
        self.assertEqual(len(self.client.updated), 2)

    def test_list_roles_excludes_roles_unsupported_by_network_write_api(self) -> None:
        self.client.get_organization_syslog_roles = lambda _org: {"items": [{
            "available": [
                {"value": "applianceEventLog", "name": "Appliance Event Log"},
                {"value": "applianceIpfilter", "name": "Appliance IP Filter"},
            ]
        }]}  # type: ignore[attr-defined]

        self.assertEqual(self.service.list_roles("org"), {
            "roles": [{"value": "applianceEventLog", "label": "Appliance Event Log"}],
            "by_network": {},
            "labels_by_network": {},
        })

    def test_copy_preview_replaces_only_compatible_destinations(self) -> None:
        self.client.settings["source"] = [{"host": "log.example", "port": 514, "roles": ["Appliance event log"]}]
        self.client.get_organization_syslog_roles = lambda _org: {"items": [
            {"network": {"id": "target"}, "available": [{"value": "applianceEventLog", "name": "Appliance Event Log"}]},
            {"network": {"id": "incompatible"}, "available": []},
        ]}  # type: ignore[attr-defined]
        previews = self.service.copy_preview("org", {"id": "source", "name": "Source"}, [
            {"id": "target", "name": "Target"}, {"id": "incompatible", "name": "Incompatible"},
        ])
        self.assertEqual([item.status for item in previews], ["update", "incompatible"])


if __name__ == "__main__":
    unittest.main()

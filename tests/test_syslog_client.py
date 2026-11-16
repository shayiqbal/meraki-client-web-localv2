from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from config.settings import Settings
from meraki_client.client_v1 import MerakiVpnClientV1


class _Response:
    status_code = 200
    ok = True

    def json(self) -> dict:
        return {"servers": []}


class _PagedResponse:
    status_code = 200
    ok = True

    def __init__(self, body: dict, link: str = "") -> None:
        self._body = body
        self.headers = {"Link": link} if link else {}

    def json(self) -> dict:
        return self._body


class SyslogClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MerakiVpnClientV1(
            Settings(api_key="test-key", max_retries=0),
            logging.getLogger("test-syslog-client"),
            dashboard=object(),
        )

    @patch("meraki_client.client_v1.requests.request", return_value=_Response())
    def test_reads_syslog_from_documented_network_endpoint(self, request) -> None:
        self.client.get_network_syslog_servers("N_123")

        request.assert_called_once_with(
            "GET",
            "https://api.meraki.com/api/v1/networks/N_123/syslogServers",
            json=None,
            headers={
                "Authorization": "Bearer test-key",
                "X-Cisco-Meraki-API-Key": "test-key",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    @patch("meraki_client.client_v1.requests.request", return_value=_Response())
    def test_updates_syslog_at_documented_network_endpoint(self, request) -> None:
        servers = [{"host": "log.example", "port": 514, "roles": ["applianceEventLog"]}]
        self.client.update_network_syslog_servers("N_123", servers)

        self.assertEqual(request.call_args.args[:2], (
            "PUT", "https://api.meraki.com/api/v1/networks/N_123/syslogServers"
        ))
        self.assertEqual(request.call_args.kwargs["json"], {
            "servers": [{"host": "log.example", "port": 514, "roles": ["Appliance event log"]}]
        })

    def test_get_organization_syslog_roles_follows_pagination_link(self) -> None:
        """A network beyond the first page must not be reported as role-less."""
        page_one = _PagedResponse(
            {"items": [{"network": {"id": "n1"}, "available": [{"value": "applianceEventLog", "name": "Appliance Event Log"}]}]},
            link='<https://api.meraki.com/api/v1/organizations/123/devices/syslog/servers/roles/byNetwork?perPage=1000&startingAfter=abc>; rel=next',
        )
        page_two = _PagedResponse(
            {"items": [{"network": {"id": "n2"}, "available": [{"value": "airMarshalEvents", "name": "Air Marshal Events"}]}]},
            link="",
        )
        with patch("meraki_client.client_v1.requests.request", side_effect=[page_one, page_two]) as request:
            result = self.client.get_organization_syslog_roles("123")

        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].args[1], "https://api.meraki.com/api/v1/organizations/123/devices/syslog/servers/roles/byNetwork?perPage=1000&startingAfter=abc")
        network_ids = [item["network"]["id"] for item in result["items"]]
        self.assertEqual(network_ids, ["n1", "n2"])


if __name__ == "__main__":
    unittest.main()

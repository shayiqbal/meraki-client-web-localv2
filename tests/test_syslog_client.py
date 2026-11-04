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


if __name__ == "__main__":
    unittest.main()

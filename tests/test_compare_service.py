from __future__ import annotations

from services.compare_service import CompareService


def test_compare_ssids_detects_varying_ssid_settings():
    source_ssids = [{
        "number": 1,
        "name": "Staff",
        "enabled": True,
        "authMode": "psk",
        "defaultVlanId": 20,
        "encryptionMode": "wpa",
        "visible": True,
    }]
    targets = [{"id": "target", "name": "Target"}]
    target_data = {
        "target": {"ssids": [{
            "number": 1,
            "name": "Staff",
            "enabled": True,
            "authMode": "psk",
            "defaultVlanId": 30,
            "encryptionMode": "wep",
            "visible": False,
        }]}
    }

    rows = CompareService._compare_ssids(
        [{**ssid, "ssidSource": "MX"} for ssid in source_ssids], [], targets,
        {"target": {"ssids": [{**ssid, "ssidSource": "MX"} for ssid in target_data["target"]["ssids"]], "ssid_errors": []}},
    )

    assert rows[0].cells["target"].status == "different"
    assert rows[0].cells["target"].detail == "VLAN: 30; encryption: wep; visible: False"


def test_compare_ssids_ignores_psk_but_matches_other_settings():
    source_ssids = [{
        "number": 1,
        "name": "Staff",
        "enabled": True,
        "authMode": "psk",
        "defaultVlanId": 20,
        "encryptionMode": "wpa",
        "visible": True,
        "psk": "source-secret",
    }]
    targets = [{"id": "target", "name": "Target"}]
    target_data = {"target": {"ssids": [{
        **source_ssids[0],
        "psk": "target-secret",
    }]}}

    rows = CompareService._compare_ssids(
        [{**ssid, "ssidSource": "MX"} for ssid in source_ssids], [], targets,
        {"target": {"ssids": [{**ssid, "ssidSource": "MX"} for ssid in target_data["target"]["ssids"]], "ssid_errors": []}},
    )

    assert rows[0].cells["target"].status == "match"


def test_safe_ssids_combines_mx_and_wireless_ssids():
    class Client:
        def get_appliance_ssids(self, network_id):
            return [{"number": 0, "name": "MX SSID"}]

        def get_wireless_ssids(self, network_id):
            return [{"number": 0, "name": "MR SSID"}]

    ssids = CompareService(Client())._safe_ssids("network")

    assert ssids == [
        {"number": 0, "name": "MR SSID", "ssidSource": "Dashboard Wi-Fi"},
        {"number": 0, "name": "MX SSID", "ssidSource": "MX"},
    ]


def test_read_ssids_reports_dashboard_wifi_errors_instead_of_no_ssids():
    class Client:
        def get_appliance_ssids(self, network_id):
            return []

        def get_wireless_ssids(self, network_id):
            raise RuntimeError("Meraki denied access")

    ssids, errors = CompareService(Client())._read_ssids("network")

    assert ssids == []
    assert errors == ["Dashboard Wi-Fi: Meraki denied access"]


def test_read_ssids_excludes_unused_dashboard_slots_but_keeps_real_disabled_ssids():
    class Client:
        def get_appliance_ssids(self, network_id):
            return []

        def get_wireless_ssids(self, network_id):
            return [
                {"number": 10, "name": "Unconfigured SSID 10", "enabled": False},
                {"number": 11, "name": "Closed for maintenance", "enabled": False},
            ]

    ssids, errors = CompareService(Client())._read_ssids("network")

    assert errors == []
    assert ssids == [{
        "number": 11,
        "name": "Closed for maintenance",
        "enabled": False,
        "ssidSource": "Dashboard Wi-Fi",
    }]


def test_compare_ssids_matches_names_regardless_of_slot_and_reports_extras():
    source_ssids = [{
        "number": 1, "name": "Staff", "enabled": True, "authMode": "psk",
        "ssidSource": "Dashboard Wi-Fi",
    }]
    targets = [{"id": "target", "name": "Target"}]
    target_data = {"target": {"ssid_errors": [], "ssids": [
        {"number": 8, "name": " staff ", "enabled": True, "authMode": "psk", "ssidSource": "Dashboard Wi-Fi"},
        {"number": 1, "name": "Guest", "enabled": True, "authMode": "open", "ssidSource": "Dashboard Wi-Fi"},
    ]}}

    rows = CompareService._compare_ssids(source_ssids, [], targets, target_data)

    assert rows[0].cells["target"].status == "match"
    assert rows[1].label == "[EXTRA] Guest [Dashboard Wi-Fi]"
    assert rows[1].cells["target"].status == "different"


def test_compare_ssids_reports_missing_names():
    source_ssids = [{
        "number": 1, "name": "Staff", "enabled": True, "authMode": "psk",
        "ssidSource": "Dashboard Wi-Fi",
    }]
    targets = [{"id": "target", "name": "Target"}]
    target_data = {"target": {"ssid_errors": [], "ssids": []}}

    rows = CompareService._compare_ssids(source_ssids, [], targets, target_data)

    assert rows[0].cells["target"].status == "missing"
    assert rows[0].cells["target"].detail == "SSID name is missing"

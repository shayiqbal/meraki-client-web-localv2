from __future__ import annotations

from copy import deepcopy

from rules.models import RuleCategory, RuleSet, VpnExclusionRule
from services.copy_service import CopyService
from services.device_address_service import DeviceAddressService


def _rule(destination: str = "10.0.0.0/8") -> VpnExclusionRule:
    return VpnExclusionRule(category=RuleCategory.CUSTOM, destination=destination)


class RuleClient:
    def __init__(self) -> None:
        self.rules = {"target": RuleSet(rules=[_rule("192.168.0.0/16")])}
        self.updated: list[tuple[str, RuleSet]] = []

    def get_rules(self, organization_id, network_id):
        return self.rules[network_id]

    def update_rules(self, network_id, rules):
        self.updated.append((network_id, rules))
        self.rules[network_id] = rules


def test_copy_service_previews_existing_and_new_rules_then_merges_new_rule():
    client = RuleClient()
    service = CopyService(client)
    existing, new = _rule("192.168.0.0/16"), _rule()
    targets = [{"id": "target", "name": "Target"}]

    preview = service.preview("org", [existing, new], targets)
    result = service.execute("org", [existing, new], targets)

    assert [status.status for status in preview[0].rule_statuses] == ["exists", "new"]
    assert result[0].success
    assert result[0].rules_added == 1
    assert result[0].rules_skipped == 1
    assert len(client.updated) == 1


class DeviceClient:
    def __init__(self) -> None:
        self.updated: list[tuple[str, str, bool]] = []

    def update_device_address(self, serial, address, move_map_marker):
        self.updated.append((serial, address, move_map_marker))
        return {"serial": serial, "address": address}

    def get_device(self, serial):
        return {"serial": serial, "address": "123 Main St", "lat": 1, "lng": 2}


def test_device_address_preview_and_update_verify_marker_without_unrelated_writes():
    client = DeviceClient()
    service = DeviceAddressService(client)
    devices = [
        {"serial": "change", "name": "Change", "address": "Old", "lat": 1, "lng": 2},
        {"serial": "remap", "name": "Remap", "address": "123 Main St", "lat": 0, "lng": 0},
        {"serial": "same", "name": "Same", "address": "123 Main St", "lat": 1, "lng": 2},
    ]

    preview = service.preview(devices, "123 Main St")
    result = service.update_one(deepcopy(devices[0]), "123 Main St")

    assert [item.status for item in preview.devices] == ["change", "remap", "unchanged"]
    assert preview.update_count == 2
    assert result.success and result.verified
    assert client.updated == [("change", "123 Main St", True)]


def test_device_address_update_reports_per_device_failure():
    class FailingClient(DeviceClient):
        def update_device_address(self, serial, address, move_map_marker):
            raise RuntimeError("Meraki write failed")

    result = DeviceAddressService(FailingClient()).update_one(
        {"serial": "device", "name": "Device"}, "123 Main St"
    )

    assert not result.success
    assert result.error == "Meraki write failed"

from __future__ import annotations

from rules.models import RuleCategory, RuleSet, VpnExclusionRule
from services.network_service import CloneableConfig, CreateNetworkOptions, NetworkService
from services.workflow import DriftDetected, WorkflowService


def _rule(destination: str) -> VpnExclusionRule:
    return VpnExclusionRule(category=RuleCategory.CUSTOM, destination=destination)


class WorkflowClient:
    def __init__(self) -> None:
        self.rules = {"target": RuleSet(rules=[_rule("10.0.0.0/8")])}
        self.updated = []

    def get_rules(self, organization_id, network_id):
        return self.rules[network_id]

    def update_rules(self, network_id, rules):
        self.updated.append((network_id, rules))
        self.rules[network_id] = rules
        return {"ok": True}


def test_workflow_dry_run_deploy_and_drift_protection():
    client = WorkflowClient()
    service = WorkflowService(client)
    proposed = RuleSet(rules=[_rule("192.168.0.0/16")])
    dry_run = service.dry_run("org", [{"id": "target", "name": "Target"}], proposed)[0]

    assert dry_run.change_count == 1
    service.deploy(dry_run)
    assert client.updated[0][0] == "target"

    client.rules["target"] = RuleSet(rules=[_rule("172.16.0.0/12")])
    try:
        service.deploy(dry_run)
    except DriftDetected:
        pass
    else:
        raise AssertionError("deployment must reject changed destination rules")


class NetworkClient:
    def __init__(self) -> None:
        self.calls = []

    def create_network(self, organization_id, **kwargs):
        self.calls.append(("create_network", kwargs))
        return {"id": "new", "name": kwargs["name"]}

    def update_rules(self, network_id, rules): self.calls.append(("rules", network_id, rules))
    def create_appliance_static_route(self, network_id, **kwargs): self.calls.append(("route", network_id, kwargs))
    def update_appliance_firewall_l3_rules(self, network_id, rules): self.calls.append(("l3", network_id, rules))
    def update_appliance_firewall_l7_rules(self, network_id, rules): self.calls.append(("l7", network_id, rules))
    def update_appliance_ssid(self, network_id, number, **kwargs): self.calls.append(("ssid", network_id, number, kwargs))
    def update_appliance_settings(self, network_id, **kwargs): self.calls.append(("settings", network_id, kwargs))
    def get_group_policies(self, network_id): return []
    def create_group_policy(self, network_id, policy): self.calls.append(("policy", network_id, policy))


def test_network_creation_copies_selected_safe_configuration_only():
    client = NetworkClient()
    config = CloneableConfig(
        vpn_exclusions=RuleSet(rules=[_rule("10.0.0.0/8")]),
        tags=["template"],
        static_routes=[{"name": "Route", "subnet": "10.2.0.0/16", "gatewayIp": "10.0.0.1"}],
        l3_firewall_rules=[{"comment": "Default rule"}, {"policy": "deny", "comment": "Block"}],
        l7_firewall_rules=[{"policy": "deny", "type": "host", "value": "example.com"}],
        ssids=[{"number": 1, "name": "Staff", "enabled": True, "authMode": "psk", "psk": "never-copy"}],
        appliance_settings={"clientTrackingMethod": "MAC address", "ignored": "no"},
        group_policies=[{"name": "Staff"}],
        source_product_types=["appliance"],
    )
    options = CreateNetworkOptions(
        name="New Network", timezone="America/Chicago", copy_static_routes=True,
        copy_l3_firewall=True, copy_l7_firewall=True, copy_ssids=True,
        copy_network_settings=True, copy_group_policies=True, ssid_psks={1: "new-secret"},
    )

    result = NetworkService(client).create_and_configure("org", options, config)

    assert result.success and result.all_steps_ok
    assert [step[0] for step in result.steps] == [
        "Create network", "Copy tags", "Copy VPN exclusions", "Copy static routes",
        "Copy L3 firewall rules", "Copy L7 firewall rules", "Copy SSID settings",
        "Copy network settings", "Copy group policies",
    ]
    l3_call = next(call for call in client.calls if call[0] == "l3")
    assert l3_call[2] == [{"policy": "deny", "comment": "Block"}]
    ssid_call = next(call for call in client.calls if call[0] == "ssid")
    assert ssid_call[3] == {"name": "Staff", "enabled": True, "authMode": "psk", "psk": "new-secret"}
    settings_call = next(call for call in client.calls if call[0] == "settings")
    assert settings_call[2] == {"clientTrackingMethod": "MAC address"}


def test_network_creation_returns_failure_without_partial_configuration_when_create_fails():
    class FailingClient(NetworkClient):
        def create_network(self, organization_id, **kwargs):
            raise RuntimeError("Meraki create failed")

    result = NetworkService(FailingClient()).create_and_configure(
        "org", CreateNetworkOptions(name="New", timezone="America/Chicago"), CloneableConfig()
    )

    assert not result.success
    assert result.steps == [("Create network", False, "Meraki create failed")]

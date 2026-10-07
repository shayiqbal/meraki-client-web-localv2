from __future__ import annotations

from copy import deepcopy

from services.group_policy_service import GroupPolicyCopyService


class FakeClient:
    def __init__(self) -> None:
        self.networks = {
            "source": {"id": "source", "name": "Source"},
            "target": {"id": "target", "name": "Target"},
        }
        self.policies = {
            "source": [{
                "groupPolicyId": "source-policy", "name": "Staff",
                "bandwidth": {"settings": "custom"},
                "firewallAndTrafficShaping": {"settings": "custom", "l3FirewallRules": [{"policy": "deny"}]},
            }],
            "target": [{
                "groupPolicyId": "target-policy", "name": "Staff",
                "bandwidth": {"settings": "network default"},
                "firewallAndTrafficShaping": {"settings": "custom", "l3FirewallRules": [{"policy": "allow"}]},
            }],
        }

    def get_network(self, network_id):
        return self.networks[network_id]

    def get_group_policies(self, network_id):
        return deepcopy(self.policies[network_id])

    def create_group_policy(self, network_id, policy):
        created = deepcopy(policy)
        created["groupPolicyId"] = "created-policy"
        self.policies[network_id].append(created)
        return deepcopy(created)

    def update_group_policy(self, network_id, policy_id, policy):
        for index, existing in enumerate(self.policies[network_id]):
            if existing["groupPolicyId"] == policy_id:
                updated = deepcopy(policy)
                updated["groupPolicyId"] = policy_id
                self.policies[network_id][index] = updated
                return deepcopy(updated)
        raise AssertionError("unknown policy")

    def delete_group_policy(self, network_id, policy_id):
        self.policies[network_id] = [p for p in self.policies[network_id] if p["groupPolicyId"] != policy_id]


def test_skip_mode_reports_conflict_without_writing():
    client = FakeClient()
    service = GroupPolicyCopyService(client)

    plan = service.dry_run("source", ["source-policy"], ["target"], "skip")

    assert plan["items"][0]["action"] == "conflict"
    assert client.policies["target"][0]["bandwidth"]["settings"] == "network default"


def test_overwrite_replaces_all_writable_settings_and_rolls_back():
    client = FakeClient()
    service = GroupPolicyCopyService(client)
    plan = service.dry_run("source", ["source-policy"], ["target"], "overwrite")

    assert plan["items"][0]["action"] == "overwrite"
    operation = service.execute(plan, allow_overwrite=True)
    target = client.policies["target"][0]
    assert target["groupPolicyId"] == "target-policy"
    assert target["bandwidth"]["settings"] == "custom"
    assert target["firewallAndTrafficShaping"]["l3FirewallRules"] == [{"policy": "deny"}]

    results = service.rollback(operation)
    assert results == [{"network_id": "target", "action": "rolled_back", "success": True, "error": ""}]
    assert client.policies["target"][0]["bandwidth"]["settings"] == "network default"


def test_execute_blocks_drift_after_dry_run():
    client = FakeClient()
    service = GroupPolicyCopyService(client)
    plan = service.dry_run("source", ["source-policy"], ["target"], "overwrite")
    client.policies["target"][0]["bandwidth"] = {"settings": "custom", "bandwidthLimits": {"limitUp": 1}}

    operation = service.execute(plan, allow_overwrite=True)

    assert operation["results"][0]["action"] == "blocked_by_drift"
    assert not operation["results"][0]["success"]


def test_rollback_uses_actual_post_update_state_for_drift_protection():
    client = FakeClient()
    service = GroupPolicyCopyService(client)
    plan = service.dry_run("source", ["source-policy"], ["target"], "overwrite")
    operation = service.execute(plan, allow_overwrite=True)

    # The service re-reads Meraki's applied configuration before recording rollback data.
    assert operation["changes"][0]["after_fingerprint"]
    assert service.rollback(operation)[0]["success"]

"""Safe Group Policy dry-run, overwrite, drift detection, and session rollback."""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from meraki_client.client_v1 import MerakiVpnClientV1

ConflictMode = Literal["skip", "overwrite"]
PLAN_TTL = timedelta(minutes=30)


def _name_key(policy: dict[str, Any]) -> str:
    return (policy.get("name") or "").strip().lower()


def _payload(policy: dict[str, Any]) -> dict[str, Any]:
    writable = {
        "name", "bandwidth", "firewallAndTrafficShaping", "scheduling", "vlanTagging",
        "splashAuthSettings", "contentFiltering",
    }
    return {key: value for key, value in policy.items() if key in writable}


def _fingerprint(policy: dict[str, Any]) -> str:
    encoded = json.dumps(_payload(policy), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(_payload(before)) | set(_payload(after)) if _payload(before).get(key) != _payload(after).get(key))


def _policy_by_id(client: MerakiVpnClientV1, network_id: str, group_policy_id: str) -> dict[str, Any] | None:
    return next(
        (policy for policy in client.get_group_policies(network_id)
         if policy.get("groupPolicyId") == group_policy_id),
        None,
    )


@dataclass(slots=True)
class GroupPolicyCopyService:
    client: MerakiVpnClientV1

    def dry_run(
        self,
        source_network_id: str,
        selected_policy_ids: list[str],
        destination_network_ids: list[str],
        conflict_mode: ConflictMode,
    ) -> dict[str, Any]:
        if conflict_mode not in {"skip", "overwrite"}:
            raise ValueError("Invalid conflict mode.")
        if not selected_policy_ids or not destination_network_ids:
            raise ValueError("Select at least one policy and one destination network.")
        if source_network_id in destination_network_ids:
            raise ValueError("The source network cannot also be a destination.")
        if len(set(destination_network_ids)) != len(destination_network_ids):
            raise ValueError("Destination networks must be unique.")

        source = self.client.get_network(source_network_id)
        source_policies = self.client.get_group_policies(source_network_id)
        requested = set(selected_policy_ids)
        selected = [policy for policy in source_policies if policy.get("groupPolicyId") in requested]
        if len(selected) != len(requested):
            raise ValueError("One or more selected policies no longer exists on the source network.")
        keys = [_name_key(policy) for policy in selected]
        if not all(keys) or len(set(keys)) != len(keys):
            raise ValueError("Selected policies must have unique, non-empty names.")

        items: list[dict[str, Any]] = []
        for destination_id in destination_network_ids:
            destination = self.client.get_network(destination_id)
            existing = self.client.get_group_policies(destination_id)
            by_name = {_name_key(policy): policy for policy in existing}
            for policy in selected:
                current = by_name.get(_name_key(policy))
                action = "create"
                changed_fields: list[str] = []
                if current:
                    changed_fields = _changed_fields(current, policy)
                    if not changed_fields:
                        action = "unchanged"
                    elif conflict_mode == "overwrite":
                        action = "overwrite"
                    else:
                        action = "conflict"
                items.append({
                    "network_id": destination_id,
                    "network_name": destination["name"],
                    "source_policy": _payload(policy),
                    "source_policy_id": policy["groupPolicyId"],
                    "destination_policy_id": current.get("groupPolicyId") if current else None,
                    "destination_before": _payload(current) if current else None,
                    "destination_fingerprint": _fingerprint(current) if current else None,
                    "action": action,
                    "changed_fields": changed_fields,
                })
        return {
            "plan_id": secrets.token_urlsafe(24),
            "created_at": datetime.now(UTC),
            "source_network_name": source["name"],
            "conflict_mode": conflict_mode,
            "items": items,
        }

    def execute(self, plan: dict[str, Any], allow_overwrite: bool) -> dict[str, Any]:
        if datetime.now(UTC) - plan["created_at"] > PLAN_TTL:
            raise ValueError("Dry run expired. Run it again before making changes.")
        if plan["conflict_mode"] == "overwrite" and not allow_overwrite:
            raise ValueError("Explicit overwrite confirmation is required.")

        operation = {"operation_id": secrets.token_urlsafe(24), "changes": [], "results": []}
        for item in plan["items"]:
            action = item["action"]
            result = {"network_id": item["network_id"], "network_name": item["network_name"], "policy_name": item["source_policy"]["name"], "action": action, "success": True, "error": ""}
            try:
                current = next((policy for policy in self.client.get_group_policies(item["network_id"])
                                if _name_key(policy) == _name_key(item["source_policy"])), None)
                current_fp = _fingerprint(current) if current else None
                if current_fp != item["destination_fingerprint"]:
                    result.update(action="blocked_by_drift", success=False, error="Destination policy changed after dry run.")
                elif action == "create":
                    created = self.client.create_group_policy(item["network_id"], item["source_policy"])
                    actual = _policy_by_id(self.client, item["network_id"], created["groupPolicyId"])
                    if not actual:
                        raise RuntimeError("Created policy could not be verified.")
                    operation["changes"].append({"kind": "created", "network_id": item["network_id"], "group_policy_id": created["groupPolicyId"], "after_fingerprint": _fingerprint(actual)})
                elif action == "overwrite":
                    self.client.update_group_policy(item["network_id"], item["destination_policy_id"], item["source_policy"])
                    actual = _policy_by_id(self.client, item["network_id"], item["destination_policy_id"])
                    if not actual:
                        raise RuntimeError("Updated policy could not be verified.")
                    operation["changes"].append({"kind": "overwritten", "network_id": item["network_id"], "group_policy_id": item["destination_policy_id"], "before": item["destination_before"], "after_fingerprint": _fingerprint(actual)})
            except Exception:
                result.update(success=False, action="failed", error="Meraki could not apply this policy.")
            operation["results"].append(result)
        return operation

    def rollback(self, operation: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for change in reversed(operation["changes"]):
            result = {"network_id": change["network_id"], "action": "rolled_back", "success": True, "error": ""}
            try:
                current = _policy_by_id(self.client, change["network_id"], change["group_policy_id"])
                if not current or _fingerprint(current) != change["after_fingerprint"]:
                    result.update(action="blocked_by_drift", success=False, error="Policy changed after this operation.")
                elif change["kind"] == "created":
                    self.client.delete_group_policy(change["network_id"], change["group_policy_id"])
                else:
                    self.client.update_group_policy(change["network_id"], change["group_policy_id"], change["before"])
            except Exception:
                result.update(action="failed", success=False, error="Meraki could not roll back this policy.")
            results.append(result)
        return results

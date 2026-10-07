"""Group Policy read, dry-run, execute, and session-only rollback endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.group_policy_service import GroupPolicyCopyService
from webapp.session import make_client, require_csrf, require_session

router = APIRouter(tags=["group_policies"])


class GroupPolicyDryRunRequest(BaseModel):
    source_network_id: str = Field(min_length=1)
    selected_policy_ids: list[str] = Field(min_length=1)
    destination_network_ids: list[str] = Field(min_length=1)
    conflict_mode: Literal["skip", "overwrite"] = "skip"


class ExecuteRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    allow_overwrite: bool = False


class RollbackRequest(BaseModel):
    operation_id: str = Field(min_length=1)


@router.get("/group-policies")
def list_group_policies(network_id: str = Query(...), session=Depends(require_session)) -> list:
    try:
        return make_client(session).get_group_policies(network_id)
    except Exception:
        raise HTTPException(502, "Could not load Group Policies from Meraki.")


@router.post("/group-policies/dry-run")
def gp_dry_run(body: GroupPolicyDryRunRequest, session=Depends(require_csrf)) -> dict:
    try:
        plan = GroupPolicyCopyService(make_client(session)).dry_run(
            body.source_network_id,
            body.selected_policy_ids,
            body.destination_network_ids,
            body.conflict_mode,
        )
        session["group_policy_plans"][plan["plan_id"]] = plan
        return _public_plan(plan)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(502, "Could not complete the Group Policy dry run.")


@router.post("/group-policies/execute")
def gp_execute(body: ExecuteRequest, session=Depends(require_csrf)) -> dict:
    plan = session["group_policy_plans"].pop(body.plan_id, None)
    if not plan:
        raise HTTPException(409, "Dry run is missing, expired, or already used. Run it again.")
    try:
        operation = GroupPolicyCopyService(make_client(session)).execute(plan, body.allow_overwrite)
        session["group_policy_operations"][operation["operation_id"]] = operation
        return operation
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/group-policies/rollback")
def gp_rollback(body: RollbackRequest, session=Depends(require_csrf)) -> dict:
    operation = session["group_policy_operations"].get(body.operation_id)
    if not operation:
        raise HTTPException(409, "Rollback data is unavailable. It exists only for this active session.")
    results = GroupPolicyCopyService(make_client(session)).rollback(operation)
    return {"operation_id": body.operation_id, "results": results}


def _public_plan(plan: dict) -> dict:
    return {
        "plan_id": plan["plan_id"],
        "source_network_name": plan["source_network_name"],
        "conflict_mode": plan["conflict_mode"],
        "items": [{
            "network_id": item["network_id"],
            "network_name": item["network_name"],
            "policy_name": item["source_policy"]["name"],
            "action": item["action"],
            "changed_fields": item["changed_fields"],
        } for item in plan["items"]],
    }

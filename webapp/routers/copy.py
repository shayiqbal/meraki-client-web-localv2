"""Copy Rules router — preview and execute multi-network rule copy."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rules.models import RuleSet, VpnExclusionRule
from services.copy_service import CopyService
from webapp.session import make_client, require_csrf

router = APIRouter(tags=["copy"])


def _rule_dict(r: VpnExclusionRule) -> dict:
    return {
        "category": r.category.value,
        "protocol": r.protocol,
        "destination": r.destination,
        "port": r.port,
        "application_id": r.application_id,
        "name": r.name,
        "action": r.action,
        "order": r.order,
    }


class CopyRequest(BaseModel):
    org_id: str
    selected_rules: list[dict[str, Any]]
    destination_networks: list[dict[str, Any]]


@router.post("/copy/preview")
def copy_preview(body: CopyRequest, session=Depends(require_csrf)) -> list:
    try:
        rules = [VpnExclusionRule(**r) for r in body.selected_rules]
        svc = CopyService(make_client(session))
        previews = svc.preview(body.org_id, rules, body.destination_networks)
        return [
            {
                "network_id": p.network_id,
                "network_name": p.network_name,
                "new_count": p.new_count,
                "exists_count": p.exists_count,
                "invalid_count": p.invalid_count,
                "rule_statuses": [
                    {"status": s.status, "detail": s.detail, "rule": _rule_dict(s.rule)}
                    for s in p.rule_statuses
                ],
            }
            for p in previews
        ]
    except Exception:
        raise HTTPException(502, "Could not load source rules from Meraki.")


@router.post("/copy/execute")
def copy_execute(body: CopyRequest, session=Depends(require_csrf)) -> list:
    try:
        rules = [VpnExclusionRule(**r) for r in body.selected_rules]
        svc = CopyService(make_client(session))
        results = svc.execute(body.org_id, rules, body.destination_networks)
        return [
            {
                "network_id": r.network_id,
                "network_name": r.network_name,
                "success": r.success,
                "rules_added": r.rules_added,
                "rules_skipped": r.rules_skipped,
                "error": r.error,
            }
            for r in results
        ]
    except Exception:
        raise HTTPException(502, "Could not complete the rules copy.")

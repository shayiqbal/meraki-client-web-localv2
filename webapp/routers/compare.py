"""Compare Networks router."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.compare_service import CompareService
from webapp.session import make_client, require_csrf

router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    org_id: str
    source_network: dict[str, Any]
    target_networks: list[dict[str, Any]]


@router.post("/compare")
def compare_networks(body: CompareRequest, session=Depends(require_csrf)) -> dict:
    if not body.target_networks:
        raise HTTPException(400, "Select at least one target network.")
    try:
        svc = CompareService(make_client(session))
        report = svc.compare(body.org_id, body.source_network, body.target_networks)

        def cell_dict(c) -> dict:
            return {"status": c.status, "detail": c.detail}

        def row_dict(r) -> dict:
            return {
                "label": r.label,
                "source_display": r.source_display,
                "cells": {nid: cell_dict(c) for nid, c in r.cells.items()},
            }

        return {
            "source_network": report.source_network,
            "target_networks": report.target_networks,
            "vpn_rules": [row_dict(r) for r in report.vpn_rules],
            "ssids": [row_dict(r) for r in report.ssids],
            "settings": [row_dict(r) for r in report.settings],
        }
    except Exception:
        raise HTTPException(502, "Could not compare the selected networks.")

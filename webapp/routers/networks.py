"""Networks router — organizations and network lists."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from webapp.session import make_client, require_session

router = APIRouter(tags=["networks"])


@router.get("/orgs")
def list_orgs(session=Depends(require_session)) -> list:
    try:
        return make_client(session).organizations()
    except Exception:
        raise HTTPException(502, "Could not load organizations from Meraki.")


@router.get("/networks")
def list_networks(
    org_id: str = Query(...),
    session=Depends(require_session),
) -> list:
    try:
        return make_client(session).networks(org_id)
    except Exception:
        raise HTTPException(502, "Could not load networks from Meraki.")

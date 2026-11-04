"""Syslog Servers router — preview and update configurations across networks."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.syslog_service import SyslogService
from webapp.session import make_client, require_csrf, require_session

router = APIRouter(tags=["syslog"])


class SyslogServer(BaseModel):
    host: str
    port: int
    roles: list[str]


class SyslogRequest(BaseModel):
    networks: list[dict[str, Any]]
    servers: list[SyslogServer]
    mode: Literal["replace", "merge"]


def _service(session) -> SyslogService:
    return SyslogService(make_client(session))


@router.get("/syslog/networks")
def list_syslog_networks(org_id: str = Query(...), session=Depends(require_session)) -> list:
    try:
        return _service(session).list_networks(org_id)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/syslog/roles")
def list_syslog_roles(org_id: str = Query(...), session=Depends(require_session)) -> list[dict[str, str]]:
    """Role values are product-specific, so obtain them from the current API."""
    try:
        return _service(session).list_roles(org_id)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/syslog/preview")
def preview_syslog(body: SyslogRequest, session=Depends(require_csrf)) -> list[dict]:
    if not body.networks:
        raise HTTPException(400, "Select at least one network.")
    try:
        previews = _service(session).preview(
            body.networks, [server.model_dump() for server in body.servers], body.mode
        )
        return [
            {
                "network_id": preview.network_id,
                "network_name": preview.network_name,
                "status": preview.status,
                "detail": preview.detail,
                "current_servers": preview.current_servers,
                "proposed_servers": preview.proposed_servers,
            }
            for preview in previews
        ]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/syslog/execute")
def execute_syslog(body: SyslogRequest, session=Depends(require_csrf)) -> list[dict]:
    if not body.networks:
        raise HTTPException(400, "Select at least one network.")
    try:
        results = _service(session).execute(
            body.networks, [server.model_dump() for server in body.servers], body.mode
        )
        return [
            {
                "network_id": result.network_id,
                "network_name": result.network_name,
                "success": result.success,
                "status": result.status,
                "server_count": result.server_count,
                "error": result.error,
            }
            for result in results
        ]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))

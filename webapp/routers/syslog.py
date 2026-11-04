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


class SyslogCopyRequest(BaseModel):
    org_id: str
    source: dict[str, Any]
    destinations: list[dict[str, Any]]


def _service(session) -> SyslogService:
    return SyslogService(make_client(session))


@router.get("/syslog/networks")
def list_syslog_networks(org_id: str = Query(...), session=Depends(require_session)) -> list:
    try:
        return _service(session).list_networks(org_id)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/syslog/roles")
def list_syslog_roles(org_id: str = Query(...), session=Depends(require_session)) -> dict[str, Any]:
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


def _copy_result(result) -> dict:
    return {"network_id": result.network_id, "network_name": result.network_name, "success": result.success, "status": result.status, "server_count": result.server_count, "error": result.error}


def _copy_preview(preview) -> dict:
    return {"network_id": preview.network_id, "network_name": preview.network_name, "status": preview.status, "detail": preview.detail, "current_servers": preview.current_servers, "proposed_servers": preview.proposed_servers}


@router.post("/syslog/copy/preview")
def preview_syslog_copy(body: SyslogCopyRequest, session=Depends(require_csrf)) -> list[dict]:
    if not body.destinations:
        raise HTTPException(400, "Select at least one destination network.")
    try:
        return [_copy_preview(preview) for preview in _service(session).copy_preview(body.org_id, body.source, body.destinations)]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/syslog/copy/execute")
def execute_syslog_copy(body: SyslogCopyRequest, session=Depends(require_csrf)) -> list[dict]:
    if not body.destinations:
        raise HTTPException(400, "Select at least one destination network.")
    try:
        return [_copy_result(result) for result in _service(session).copy_execute(body.org_id, body.source, body.destinations)]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))

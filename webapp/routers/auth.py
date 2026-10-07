"""Auth router — API key login / logout."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from config.settings import Settings
from meraki_client.client_v1 import MerakiVpnClientV1
from meraki_client.exceptions import AuthenticationError
from webapp.session import require_csrf, require_session

router = APIRouter(tags=["auth"])
log = logging.getLogger("webapp.auth")


class LoginRequest(BaseModel):
    api_key: str


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "API key is required.")
    try:
        client = MerakiVpnClientV1(
            settings=Settings(api_key=key),
            logger=log,
        )
        orgs = client.organizations()
    except AuthenticationError:
        raise HTTPException(401, "Invalid API key — Meraki rejected authentication.")
    except Exception:
        raise HTTPException(502, "Could not reach Meraki. Try again later.")

    sid = request.app.state.create_session(key)
    response.set_cookie(
        "gmm_session", sid, httponly=True, samesite="strict", secure=False,
        max_age=2 * 60 * 60, path="/",
    )
    return {"orgs": orgs, "csrf_token": request.app.state.get_session(sid)["csrf_token"]}


@router.get("/csrf")
def csrf(session=Depends(require_session)) -> dict:
    return {"csrf_token": session["csrf_token"]}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session=Depends(require_csrf),
) -> dict:
    sid = request.cookies.get("gmm_session")
    if sid:
        request.app.state.delete_session(sid)
    response.delete_cookie("gmm_session", path="/", samesite="strict")
    return {"ok": True}

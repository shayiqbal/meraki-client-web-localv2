"""Auth router — API key login / logout."""
from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from webapp.session import require_csrf, require_session

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    api_key: str


def validate_api_key(api_key: str) -> list[dict]:
    """Validate credentials with one bounded HTTPS call before opening a session."""
    try:
        response = requests.get(
            "https://api.meraki.com/api/v1/organizations",
            headers={"X-Cisco-Meraki-API-Key": api_key},
            timeout=(5, 15),
        )
    except requests.Timeout as exc:
        raise HTTPException(504, "Meraki did not respond within 15 seconds. Check your VPN, proxy, firewall, and internet connection.") from exc
    except requests.RequestException as exc:
        raise HTTPException(502, "Could not reach Meraki. Check your VPN, proxy, firewall, and internet connection.") from exc
    if response.status_code in {401, 403}:
        raise HTTPException(401, "Invalid API key or insufficient Meraki permissions.")
    if not response.ok:
        raise HTTPException(502, "Meraki could not validate the API key. Try again later.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(502, "Meraki returned an invalid validation response.") from exc
    if not isinstance(payload, list):
        raise HTTPException(502, "Meraki returned an unexpected validation response.")
    return payload


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "API key is required.")
    orgs = validate_api_key(key)

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

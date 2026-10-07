"""Meraki Config Manager - Web Application Entry Point."""
from __future__ import annotations

import logging
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure parent directory is on path so existing modules are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Session store ──────────────────────────────────────────────────────────────
_sessions: dict[str, dict[str, Any]] = {}
SESSION_TIMEOUT_HOURS = 2
SESSION_ABSOLUTE_HOURS = 8


def create_session(api_key: str) -> str:
    sid = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    _sessions[sid] = {
        "api_key": api_key,
        "created": now,
        "last_accessed": now,
        "client": None,          # cached MerakiVpnClientV1 — created once, reused
        "dry_runs": {},          # network_id -> DryRun
        "clone_configs": {},     # network_id -> CloneableConfig
        "csrf_token": secrets.token_urlsafe(32),
        "group_policy_plans": {},
        "group_policy_operations": {},
    }
    return sid


def get_session(sid: str | None) -> dict[str, Any] | None:
    if not sid:
        return None
    s = _sessions.get(sid)
    if not s:
        return None
    now = datetime.now(UTC)
    if (
        now - s["last_accessed"] > timedelta(hours=SESSION_TIMEOUT_HOURS)
        or now - s["created"] > timedelta(hours=SESSION_ABSOLUTE_HOURS)
    ):
        _sessions.pop(sid, None)
        return None
    s["last_accessed"] = now
    return s


def delete_session(sid: str) -> None:
    _sessions.pop(sid, None)


# ── FastAPI app ────────────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://cdn.jsdelivr.net; "
            "font-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Require an in-memory CSRF token for every authenticated state change."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/api/login":
            session = get_session(request.cookies.get("gmm_session"))
            token = request.headers.get("X-CSRF-Token")
            if not session:
                return JSONResponse(status_code=401, content={"detail": "Session expired. Please log in again."})
            if not token or not secrets.compare_digest(session["csrf_token"], token):
                return JSONResponse(status_code=403, content={"detail": "Invalid security token. Refresh the page and try again."})
        return await call_next(request)


app = FastAPI(title="Meraki Config Manager V2", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

_BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        return JSONResponse(status_code=exc.status_code, content={"detail": "Meraki request failed. Try again later."})
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = str(uuid.uuid4())
    logging.getLogger("webapp").error("Unhandled request error id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Request failed. Try again or contact support.", "request_id": request_id},
    )

# Attach session helpers to app state for routers
app.state.create_session = create_session
app.state.get_session = get_session
app.state.delete_session = delete_session

# ── Routers ────────────────────────────────────────────────────────────────────
from webapp.routers import auth, compare, copy, devices, exclusions, group_policies, network_mgmt, networks  # noqa: E402

app.include_router(auth.router, prefix="/api")
app.include_router(networks.router, prefix="/api")
app.include_router(exclusions.router, prefix="/api")
app.include_router(copy.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.include_router(network_mgmt.router, prefix="/api")
app.include_router(group_policies.router, prefix="/api")
app.include_router(devices.router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


if __name__ == "__main__":
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=8000, reload=False)

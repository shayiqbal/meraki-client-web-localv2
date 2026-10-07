from __future__ import annotations

from pathlib import Path

import requests
from fastapi.testclient import TestClient

from webapp.app import _sessions, app


def test_security_headers_and_cookie_session(monkeypatch):
    monkeypatch.setattr("webapp.routers.auth.validate_api_key", lambda key: [{"id": "org", "name": "Org"}])
    client = TestClient(app)

    response = client.post("/api/login", json={"api_key": "fake-api-key"})

    assert response.status_code == 200
    assert "session_id" not in response.json()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "gmm_session" not in response.text
    assert response.json()["csrf_token"]
    homepage = client.get("/")
    assert homepage.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in homepage.headers
    assert homepage.headers["cache-control"] == "no-store, private"
    assert homepage.headers["pragma"] == "no-cache"


def test_csrf_blocks_unsafe_requests_without_token():
    client = TestClient(app)
    response = client.post("/api/logout")
    assert response.status_code == 401
    assert client.post("/api/exclusions/dry-run", json={}).status_code == 401


def test_every_authenticated_post_route_declares_csrf_protection():
    root = Path(__file__).parents[1] / "webapp" / "routers"
    for path in root.glob("*.py"):
        if path.name == "auth.py":
            continue
        source = path.read_text()
        post_offsets = [match.start() for match in __import__("re").finditer(r"@router\.post", source)]
        for offset in post_offsets:
            next_offset = source.find("@router.", offset + 1)
            endpoint = source[offset:next_offset if next_offset >= 0 else len(source)]
            assert "Depends(require_csrf)" in endpoint, f"{path.name} has a POST without route-level CSRF"


def test_logout_removes_the_in_memory_api_key(monkeypatch):
    monkeypatch.setattr("webapp.routers.auth.validate_api_key", lambda key: [])
    client = TestClient(app)
    response = client.post("/api/login", json={"api_key": "test-api-key-only-in-memory"})
    csrf = response.json()["csrf_token"]
    sid = client.cookies.get("gmm_session")
    assert _sessions[sid]["api_key"] == "test-api-key-only-in-memory"

    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert sid not in _sessions


def test_source_has_no_browser_or_disk_credential_storage():
    root = Path(__file__).parents[1]
    assert not (root / "auth" / "profile_store.py").exists()
    client_code = (root / "webapp" / "static" / "app.js").read_text()
    assert "localStorage" not in client_code
    assert "sessionStorage" not in client_code
    assert "X-Session-ID" not in client_code


def test_frontend_dependency_integrity_hashes_are_exact():
    template = (Path(__file__).parents[1] / "webapp" / "templates" / "index.html").read_text()
    assert "sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" in template
    assert "sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" in template
    assert "sha384-l8f0VcPi/M1iHPv8egOnY/15TDwqgbOR1anMIJWvU6nLRgZVLTLSaNqi/TOoT5Fh" in template


def test_frontend_api_requests_have_a_timeout():
    client_code = (Path(__file__).parents[1] / "webapp" / "static" / "app.js").read_text()
    assert "AbortController" in client_code
    assert "Login timed out" in client_code


def test_login_has_a_visible_bounded_validation_state():
    root = Path(__file__).parents[1]
    client_code = (root / "webapp" / "static" / "app.js").read_text()
    template = (root / "webapp" / "templates" / "index.html").read_text()
    assert "Validating API key with Meraki" in client_code
    assert "/api/login', { api_key: this.apiKey }, 20000" in client_code
    assert "loginStatus" in template


def test_login_validation_has_a_bounded_direct_meraki_request():
    source = (Path(__file__).parents[1] / "webapp" / "routers" / "auth.py").read_text()
    assert '"https://api.meraki.com/api/v1/organizations"' in source
    assert "timeout=(5, 15)" in source


def test_login_surfaces_invalid_key_and_timeout_errors(monkeypatch):
    def invalid_key(*args, **kwargs):
        class Response:
            status_code = 401
            ok = False
        return Response()

    monkeypatch.setattr("webapp.routers.auth.requests.get", invalid_key)
    client = TestClient(app)
    invalid = client.post("/api/login", json={"api_key": "not-valid"})
    assert invalid.status_code == 401
    assert "Invalid API key" in invalid.json()["detail"]

    monkeypatch.setattr(
        "webapp.routers.auth.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()),
    )
    timeout = client.post("/api/login", json={"api_key": "not-valid"})
    assert timeout.status_code == 504
    assert "15 seconds" in timeout.json()["detail"]


def test_build_52_is_visible_on_login_page():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Meraki Config Manager V2" in response.text
    assert "Build 52" in response.text

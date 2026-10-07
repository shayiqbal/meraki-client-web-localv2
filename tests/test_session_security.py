from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from webapp.app import _sessions, app


def test_security_headers_and_cookie_session(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def organizations(self):
            return [{"id": "org", "name": "Org"}]

    monkeypatch.setattr("webapp.routers.auth.MerakiVpnClientV1", Client)
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
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def organizations(self):
            return []

    monkeypatch.setattr("webapp.routers.auth.MerakiVpnClientV1", Client)
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

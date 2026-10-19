from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE = (ROOT / "webapp" / "templates" / "index.html").read_text()
APP_JS = (ROOT / "webapp" / "static" / "app.js").read_text()
ROUTERS = "\n".join(path.read_text() for path in (ROOT / "webapp" / "routers").glob("*.py"))


def test_all_template_click_handlers_are_defined():
    calls = set(re.findall(r'@click(?:\.prevent)?="([A-Za-z_$][\w$]*)\(', TEMPLATE))
    defined = set(re.findall(r'^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(', APP_JS, re.MULTILINE))

    assert calls <= defined, f"Template handlers missing from app.js: {sorted(calls - defined)}"


def test_frontend_api_endpoints_have_registered_routes():
    paths = set(re.findall(r"this\.api\('[A-Z]+', '(/api/[^'?`]+)", APP_JS))
    registered = set(re.findall(r'@router\.(?:get|post|put|delete)\("([^"?]+)', ROUTERS))

    missing = {path for path in paths if path.removeprefix("/api") not in registered}
    assert not missing, f"Frontend calls unregistered API routes: {sorted(missing)}"


def test_source_selection_uses_authenticated_read_endpoint_without_csrf_requirement():
    assert "copySelectSource(network)" in APP_JS
    assert "/api/exclusions?org_id=${this.selectedOrgId}&network_id=${network.id}" in APP_JS
    exclusions = (ROOT / "webapp" / "routers" / "exclusions.py").read_text()
    endpoint = exclusions[exclusions.index('@router.get("/exclusions")'):exclusions.index('# ── POST import file')]
    assert "Depends(require_session)" in endpoint
    assert "Depends(require_csrf)" not in endpoint

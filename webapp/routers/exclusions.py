"""VPN Exclusions router — view, import, dry-run, deploy."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from rules.models import RuleSet, VpnExclusionRule
from rules.parser import ImportValidationError, parse_file
from services.workflow import DriftDetected, WorkflowService
from webapp.session import make_client, require_csrf, require_session

router = APIRouter(tags=["exclusions"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _rule_dict(r: VpnExclusionRule) -> dict:
    return {
        "category": r.category.value,
        "protocol": r.protocol,
        "destination": r.destination,
        "port": r.port,
        "application_id": r.application_id,
        "name": r.name,
        "action": r.action,
        "order": r.order,
    }


def _ruleset_dict(rs: RuleSet) -> dict:
    return {
        "rules": [_rule_dict(r) for r in rs.rules],
        "mode": rs.mode,
        "metadata": rs.metadata,
    }


# ── GET current rules ──────────────────────────────────────────────────────────

@router.get("/exclusions")
def get_exclusions(
    org_id: str = Query(...),
    network_id: str = Query(...),
    session=Depends(require_csrf),
) -> dict:
    try:
        return _ruleset_dict(make_client(session).get_rules(org_id, network_id))
    except Exception:
        raise HTTPException(502, "Could not load VPN exclusions from Meraki.")


# ── POST import file ───────────────────────────────────────────────────────────

@router.post("/exclusions/import")
async def import_rules(
    file: UploadFile = File(...),
    session=Depends(require_csrf),
) -> dict:
    filename = file.filename or "upload.csv"
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Uploaded file exceeds the 5 MB limit.")
    suffix = Path(filename).suffix.lower() or ".csv"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        ruleset = parse_file(tmp_path)
        return _ruleset_dict(ruleset)
    except ImportValidationError:
        raise HTTPException(400, "The uploaded file contains invalid rules.")
    except Exception:
        raise HTTPException(400, "Could not parse the uploaded file.")
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


# ── POST dry-run ───────────────────────────────────────────────────────────────

class DryRunRequest(BaseModel):
    org_id: str
    network_id: str
    network_name: str
    proposed_rules: list[dict[str, Any]]
    mode: str = "merge"


@router.post("/exclusions/dry-run")
def dry_run(body: DryRunRequest, session=Depends(require_csrf)) -> dict:
    try:
        rules = [VpnExclusionRule(**r) for r in body.proposed_rules]
        proposed = RuleSet(rules=rules, mode=body.mode)
        workflow = WorkflowService(make_client(session))
        drs = workflow.dry_run(
            body.org_id,
            [{"id": body.network_id, "name": body.network_name}],
            proposed,
        )
        dr = drs[0]
        session["dry_runs"][body.network_id] = dr
        changes = [
            {"kind": c.kind.value, "rule": _rule_dict(c.rule), "detail": c.detail}
            for c in dr.comparison.changes
        ]
        return {
            "network_id": dr.network_id,
            "network_name": dr.network_name,
            "change_count": dr.change_count,
            "has_blockers": dr.comparison.has_blockers,
            "changes": changes,
        }
    except (ValueError, TypeError):
        raise HTTPException(400, "The proposed rules are invalid.")
    except Exception:
        raise HTTPException(502, "Could not complete the VPN exclusion dry run.")


# ── POST deploy ────────────────────────────────────────────────────────────────

class DeployRequest(BaseModel):
    network_id: str


@router.post("/exclusions/deploy")
def deploy(body: DeployRequest, session=Depends(require_csrf)) -> dict:
    dr = session["dry_runs"].get(body.network_id)
    if not dr:
        raise HTTPException(400, "No dry run found. Run a dry run first.")
    if dr.comparison.has_blockers:
        raise HTTPException(400, "Deployment blocked by invalid or duplicate rules.")
    try:
        workflow = WorkflowService(make_client(session))
        result = workflow.deploy(dr)
        session["dry_runs"].pop(body.network_id, None)
        return {"ok": True, "result": result}
    except DriftDetected:
        raise HTTPException(409, "The network changed after dry run. Run it again before deployment.")
    except Exception:
        raise HTTPException(502, "Could not deploy VPN exclusions.")

"""New Network wizard router."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.network_service import (
    CloneableConfig,
    CreateNetworkOptions,
    NetworkService,
)
from rules.models import RuleSet, VpnExclusionRule
from webapp.session import make_client, require_csrf

router = APIRouter(tags=["network_mgmt"])


class CloneConfigRequest(BaseModel):
    org_id: str
    source_network: dict[str, Any]


@router.post("/network/clone-config")
def get_clone_config(body: CloneConfigRequest, session=Depends(require_csrf)) -> dict:
    try:
        svc = NetworkService(make_client(session))
        config = svc.get_cloneable_config(body.org_id, body.source_network)
        # Store in session for create step
        session["clone_configs"][body.source_network["id"]] = config
        return {
            "source_id": body.source_network["id"],
            "source_name": body.source_network.get("name", ""),
            "vpn_exclusion_count": len(config.vpn_exclusions.rules),
            "tags": config.tags,
            "static_route_count": len(config.static_routes),
            "l3_rule_count": len(config.l3_firewall_rules),
            "l7_rule_count": len(config.l7_firewall_rules),
            "ssid_count": len([s for s in config.ssids if s.get("enabled")]),
            "ssids": [
                {
                    "number": s.get("number"),
                    "name": s.get("name"),
                    "enabled": s.get("enabled"),
                    "authMode": s.get("authMode"),
                }
                for s in config.ssids
            ],
            "group_policy_count": len(config.group_policies),
            "has_appliance_settings": bool(config.appliance_settings),
            "source_timezone": config.source_timezone,
        }
    except Exception:
        raise HTTPException(502, "Could not load clone settings from Meraki.")


class CreateNetworkRequest(BaseModel):
    org_id: str
    source_network_id: str
    name: str
    timezone: str
    notes: str = ""
    copy_tags: bool = True
    copy_vpn_exclusions: bool = True
    copy_static_routes: bool = False
    copy_l3_firewall: bool = False
    copy_l7_firewall: bool = False
    copy_ssids: bool = False
    copy_network_settings: bool = False
    copy_group_policies: bool = False
    ssid_psks: dict[str, str] = {}


@router.post("/network/create")
def create_network(body: CreateNetworkRequest, session=Depends(require_csrf)) -> dict:
    config: CloneableConfig | None = session["clone_configs"].get(body.source_network_id)
    if not config:
        raise HTTPException(400, "Clone config not loaded. Fetch the clone config first.")
    try:
        options = CreateNetworkOptions(
            name=body.name,
            timezone=body.timezone,
            notes=body.notes,
            copy_tags=body.copy_tags,
            copy_vpn_exclusions=body.copy_vpn_exclusions,
            copy_static_routes=body.copy_static_routes,
            copy_l3_firewall=body.copy_l3_firewall,
            copy_l7_firewall=body.copy_l7_firewall,
            copy_ssids=body.copy_ssids,
            copy_network_settings=body.copy_network_settings,
            copy_group_policies=body.copy_group_policies,
            ssid_psks={int(k): v for k, v in body.ssid_psks.items()},
        )
        svc = NetworkService(make_client(session))
        result = svc.create_and_configure(body.org_id, options, config)
        session["clone_configs"].pop(body.source_network_id, None)
        return {
            "success": result.success,
            "network_id": result.network_id,
            "network_name": result.network_name,
            "error": result.error,
            "steps": [
                {"label": label, "ok": ok, "detail": detail}
                for label, ok, detail in result.steps
            ],
        }
    except Exception:
        raise HTTPException(502, "Could not create the network.")

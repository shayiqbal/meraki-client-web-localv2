"""Devices router — list devices and bulk-update their physical address / map marker.

The update endpoint is deliberately **per device**. The browser loops over the
selected devices and calls it once each, which gives live progress and
guarantees that a failure on one device can never abort the remaining ones.
A device-level failure is returned as HTTP 200 with ``success: false`` so the
client loop is never interrupted by an error status.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.device_address_service import DeviceAddressService
from webapp.session import make_client, require_csrf, require_session

router = APIRouter(tags=["devices"])


class AddressPreviewRequest(BaseModel):
    devices: list[dict[str, Any]]
    new_address: str


class DeviceUpdateRequest(BaseModel):
    device: dict[str, Any]
    new_address: str


def _service(session) -> DeviceAddressService:
    return DeviceAddressService(make_client(session))


@router.get("/all-networks")
def list_all_networks(
    org_id: str = Query(...),
    session=Depends(require_session),
) -> list:
    """Every network in the org, including wireless/switch/camera-only ones.

    ``/api/networks`` is filtered to appliance networks for the VPN features;
    device addressing needs the full list.
    """
    try:
        return _service(session).list_networks(org_id)
    except Exception:
        raise HTTPException(502, "Could not load available networks.")


@router.get("/devices")
def list_devices(
    network_id: str = Query(...),
    session=Depends(require_session),
) -> list:
    try:
        return _service(session).list_devices(network_id)
    except Exception:
        raise HTTPException(502, "Could not load devices from Meraki.")


@router.post("/devices/address/preview")
def preview_address(
    body: AddressPreviewRequest,
    session=Depends(require_csrf),
) -> dict:
    """Read-only summary of the pending change. Makes no Meraki write calls."""
    if not body.new_address.strip():
        raise HTTPException(400, "A new address is required.")
    if not body.devices:
        raise HTTPException(400, "Select at least one device.")
    try:
        preview = _service(session).preview(body.devices, body.new_address)
        return {
            "new_address": preview.new_address,
            "total_count": preview.total_count,
            "change_count": preview.change_count,
            "remap_count": preview.remap_count,
            "unchanged_count": preview.unchanged_count,
            "update_count": preview.update_count,
            "devices": [
                {
                    "serial": d.serial,
                    "name": d.name,
                    "model": d.model,
                    "mac": d.mac,
                    "current_address": d.current_address,
                    "current_lat": d.current_lat,
                    "current_lng": d.current_lng,
                    "new_address": d.new_address,
                    "status": d.status,
                    "detail": d.detail,
                    "will_change": d.will_change,
                }
                for d in preview.devices
            ],
        }
    except Exception:
        raise HTTPException(502, "Could not update the selected devices.")


@router.post("/devices/address/update-one")
def update_one_address(
    body: DeviceUpdateRequest,
    session=Depends(require_csrf),
) -> dict:
    """Update a single device's address and map marker, then verify it.

    Always responds 200 — per-device failure is reported in the body so the
    browser's sequential loop continues with the remaining devices.
    """
    if not body.new_address.strip():
        raise HTTPException(400, "A new address is required.")
    result = _service(session).update_one(body.device, body.new_address)
    return {
        "serial": result.serial,
        "name": result.name,
        "model": result.model,
        "success": result.success,
        "old_address": result.old_address,
        "new_address": result.new_address,
        "lat": result.lat,
        "lng": result.lng,
        "verified": result.verified,
        "verify_note": result.verify_note,
        "error": result.error,
    }

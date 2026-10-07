"""Bulk device physical-address / map-marker update service.

Applies one site address to many devices in a network using the Meraki
``PUT /devices/{serial}`` endpoint.

Why the write is exactly ``{"address": ..., "moveMapMarker": true}``:

* The Meraki API documents ``moveMapMarker`` as *"Whether or not to set the
  latitude and longitude of a device based on the new address. **Only applies
  when lat and lng are not specified.**"* — so ``lat``/``lng`` must be omitted
  for the dashboard map marker to follow the new address.
* The Meraki Python SDK builds the request body purely from the keyword
  arguments it is given, so omitting every other field guarantees that no
  unrelated device configuration (name, tags, notes, floor plan, switch
  profile) is touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from meraki_client.client_v1 import MerakiVpnClientV1


def device_label(device: dict[str, Any]) -> str:
    """Best available human name for a device — Meraki leaves ``name`` blank often."""
    return (
        (device.get("name") or "").strip()
        or (device.get("mac") or "").strip()
        or (device.get("serial") or "").strip()
        or "(unnamed device)"
    )


def _norm(address: str | None) -> str:
    """Compare addresses case- and whitespace-insensitively."""
    return " ".join((address or "").split()).casefold()


def has_map_position(lat: Any, lng: Any) -> bool:
    """Whether a device has a real map marker on the dashboard.

    Meraki reports an unplaced marker as ``0.0, 0.0`` (null island) as well as
    ``None``, so both must count as "no position". Treating 0,0 as valid would
    make the tool skip devices whose address is set but whose marker was never
    placed — exactly the case this feature exists to fix.
    """
    if lat is None or lng is None:
        return False
    try:
        return not (float(lat) == 0.0 and float(lng) == 0.0)
    except (TypeError, ValueError):
        return False


@dataclass(slots=True)
class DeviceAddressPreview:
    serial: str
    name: str
    model: str
    mac: str
    current_address: str
    current_lat: float | None
    current_lng: float | None
    new_address: str
    status: str  # "change" | "remap" | "unchanged"
    detail: str = ""

    @property
    def will_change(self) -> bool:
        """``remap`` devices are still submitted — their marker needs placing."""
        return self.status in {"change", "remap"}


@dataclass(slots=True)
class BulkAddressPreview:
    new_address: str
    devices: list[DeviceAddressPreview]

    @property
    def change_count(self) -> int:
        return sum(d.status == "change" for d in self.devices)

    @property
    def remap_count(self) -> int:
        """Address already correct, but the map marker is missing."""
        return sum(d.status == "remap" for d in self.devices)

    @property
    def unchanged_count(self) -> int:
        return sum(d.status == "unchanged" for d in self.devices)

    @property
    def update_count(self) -> int:
        """Devices that will actually be written to (change + remap)."""
        return sum(d.will_change for d in self.devices)

    @property
    def total_count(self) -> int:
        return len(self.devices)


@dataclass(slots=True)
class DeviceAddressResult:
    serial: str
    name: str
    model: str
    success: bool
    old_address: str = ""
    new_address: str = ""
    lat: float | None = None
    lng: float | None = None
    verified: bool = False
    verify_note: str = ""
    error: str = ""


class DeviceAddressService:
    """Lists devices, previews an address change, and applies it device by device."""

    def __init__(self, client: MerakiVpnClientV1) -> None:
        self.client = client

    # ── Read ───────────────────────────────────────────────────────────────

    def list_networks(self, organization_id: str) -> list[dict[str, Any]]:
        """Every network in the org — not just appliance networks.

        Devices needing an address are just as often APs, switches or cameras,
        so the appliance-only filter used by the VPN features is not applied.
        """
        networks = self.client.all_networks(organization_id)
        return sorted(networks, key=lambda n: (n.get("name") or "").casefold())

    def list_devices(self, network_id: str) -> list[dict[str, Any]]:
        devices = self.client.get_network_devices(network_id)
        return sorted(devices, key=lambda d: device_label(d).casefold())

    # ── Preview ────────────────────────────────────────────────────────────

    def preview(
        self,
        devices: list[dict[str, Any]],
        new_address: str,
    ) -> BulkAddressPreview:
        """Read-only summary of what the bulk update would do. Makes no API calls."""
        address = new_address.strip()
        return BulkAddressPreview(
            new_address=address,
            devices=[self._preview_row(d, address) for d in devices],
        )

    @staticmethod
    def _preview_row(device: dict[str, Any], address: str) -> DeviceAddressPreview:
        lat, lng = device.get("lat"), device.get("lng")
        same_address = _norm(device.get("address")) == _norm(address)
        placed = has_map_position(lat, lng)

        if not same_address:
            status, detail = "change", "Address will be updated"
        elif not placed:
            # Address is already right but the marker was never placed (Meraki
            # reports this as 0,0 or null). Re-sending the address with
            # moveMapMarker lets Meraki geocode it and drop the pin.
            status, detail = "remap", "Address already correct — map marker will be placed"
        else:
            status, detail = "unchanged", "No change needed"

        return DeviceAddressPreview(
            serial=device.get("serial", ""),
            name=device_label(device),
            model=device.get("model", "") or "",
            mac=device.get("mac", "") or "",
            current_address=(device.get("address") or "").strip(),
            current_lat=lat,
            current_lng=lng,
            new_address=address,
            status=status,
            detail=detail,
        )

    # ── Write ──────────────────────────────────────────────────────────────

    def update_one(
        self,
        device: dict[str, Any],
        new_address: str,
        verify: bool = True,
    ) -> DeviceAddressResult:
        """Update a single device. Never raises — failures come back on the result.

        This is the unit of isolation: callers loop over it so that one bad
        device can never abort the rest of the batch.
        """
        serial = device.get("serial", "")
        name = device_label(device)
        model = device.get("model", "") or ""
        old_address = (device.get("address") or "").strip()
        address = new_address.strip()

        if not serial:
            return DeviceAddressResult(
                serial="", name=name, model=model, success=False,
                old_address=old_address, new_address=address,
                error="Device has no serial number.",
            )
        if not address:
            return DeviceAddressResult(
                serial=serial, name=name, model=model, success=False,
                old_address=old_address, new_address=address,
                error="New address is empty.",
            )

        try:
            response = self.client.update_device_address(
                serial, address, move_map_marker=True
            ) or {}
        except Exception as exc:
            return DeviceAddressResult(
                serial=serial, name=name, model=model, success=False,
                old_address=old_address, new_address=address, error=str(exc),
            )

        result = DeviceAddressResult(
            serial=serial,
            name=device_label({**device, **response}),
            model=model or (response.get("model") or ""),
            success=True,
            old_address=old_address,
            new_address=(response.get("address") or address).strip(),
            lat=response.get("lat"),
            lng=response.get("lng"),
        )

        if verify:
            self._verify(result, address)
        else:
            result.verified = True
            result.verify_note = "Verification skipped."
        return result

    def _verify(self, result: DeviceAddressResult, requested_address: str) -> None:
        """Independently re-read the device to confirm address and map marker.

        A failed verification is *not* a failed update — the write returned 200.
        Meraki's geocoding can lag, so this is reported as a note.
        """
        try:
            fresh = self.client.get_device(result.serial) or {}
        except Exception as exc:
            result.verify_note = f"Could not re-read device to verify: {exc}"
            return

        live_address = (fresh.get("address") or "").strip()
        lat, lng = fresh.get("lat"), fresh.get("lng")
        result.new_address = live_address or result.new_address
        if lat is not None:
            result.lat = lat
        if lng is not None:
            result.lng = lng

        if _norm(live_address) != _norm(requested_address):
            result.verify_note = (
                f"Address on dashboard reads '{live_address}' after update."
            )
        elif not has_map_position(lat, lng):
            result.verify_note = (
                "Address saved, but Meraki has not geocoded a map position yet."
            )
        else:
            result.verified = True
            result.verify_note = f"Address and map marker confirmed ({lat}, {lng})."

    def execute(
        self,
        devices: list[dict[str, Any]],
        new_address: str,
        progress: Callable[[str], None] | None = None,
        on_result: Callable[[DeviceAddressResult], None] | None = None,
        verify: bool = True,
    ) -> list[DeviceAddressResult]:
        """Apply *new_address* to every device in *devices*.

        Each device is isolated: a failure is recorded and the loop continues.
        *on_result* is invoked after each device so callers can stream progress.
        """
        results: list[DeviceAddressResult] = []
        total = len(devices)
        for index, device in enumerate(devices, start=1):
            if progress:
                progress(f"Updating {index} of {total} — {device_label(device)}…")
            result = self.update_one(device, new_address, verify=verify)
            results.append(result)
            if on_result:
                on_result(result)
        return results

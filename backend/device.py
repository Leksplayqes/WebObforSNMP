"""Endpoints related to device metadata and SNMP proxy initialisation."""
from __future__ import annotations

import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends

from MainConnectFunc import equpimentV7, get_device_info
from unit_tests.SnmpV7alarm import setSFP_Mode, alarmplusmaslcnctSTM, alarmplusmask

from .config import ensure_config, json_input, json_set
from .logs import add_log
from backend.services.models import DeviceInfoRequest, ViaviSettings, ViaviUnitSettings
from .services.tunnels import TunnelManagerError, TunnelService, get_tunnel_service

router = APIRouter(tags=["device"])


def _save_viavi_unit(unit_name: str, unit: ViaviUnitSettings | None) -> None:
    if unit is None:
        return
    base = ["VIAVIcontrol", "settings", unit_name]
    if unit.ipaddr is not None:
        json_set(base + ["ipaddr"], unit.ipaddr)
    if unit.port is not None:
        json_set(base + ["port"], int(unit.port))
    if unit.typeofport is not None:
        tp = unit.typeofport
        if tp.Port1 is not None:
            json_set(base + ["typeofport", "Port1"], tp.Port1)
        if tp.Port2 is not None:
            json_set(base + ["typeofport", "Port2"], tp.Port2)


def _save_viavi_settings(settings: ViaviSettings) -> None:
    _save_viavi_unit("NumOne", settings.NumOne)
    _save_viavi_unit("NumTwo", settings.NumTwo)


@router.post("/device/info")
async def device_info(
        req: DeviceInfoRequest,
        tunnel_service: TunnelService = Depends(get_tunnel_service),
) -> Dict[str, Any]:
    try:
        ensure_config()
    except Exception as exc:
        add_log(f"ensure_config failed: {exc}", "ERROR")

    try:
        if req.ip_address:
            json_set(["CurrentEQ", "ipaddr"], req.ip_address)
        json_set(["CurrentEQ", "pass"], req.password or "")
    except Exception as exc:
        add_log(f"json_set (ip/pass) failed: {exc}", "ERROR")

    ip = req.ip_address
    password = req.password or ""
    username = "admin"

    lease_key = "device-info"

    def _run_proxy() -> None:
        try:
            lease = tunnel_service.reserve(
                lease_key,
                "device",
                ip=ip,
                username=username,
                password=password,
                ttl=15.0,
                track=True,
            )
            add_log(
                f"SNMP tunnel ready at {lease.host}:{lease.port} for {ip}",
                "INFO",
            )
        except TunnelManagerError as exc:
            add_log(f"SNMP tunnel reservation failed: {exc}", "ERROR")

    threading.Thread(target=_run_proxy, daemon=True).start()

    try:
        if req.viavi is not None:
            _save_viavi_settings(req.viavi)
    except Exception as exc:
        add_log(f"save_viavi_to_json failed: {exc}", "ERROR")

    try:
        if req.loopback is not None:
            payload = {k: v for k, v in req.loopback.model_dump().items() if v is not None}
            if payload:
                json_input(["CurrentEQ", "loopback"], payload)
    except Exception as exc:
        add_log(f"save loopback failed: {exc}", "ERROR")

    try:
        await get_device_info()
    except Exception as exc:
        add_log(f"Get_device_info failed: {exc}", "ERROR")
    try:
        await equpimentV7()
    except Exception as exc:
        add_log(f"EqupimentV7 failed: {exc}", "ERROR")
    finally:
        try:
            tunnel_service.release(lease_key)
            add_log("SNMP tunnel for device/info is close")
        except TunnelManagerError as exc:
            add_log("Failed to release SNMP tunnel fo device/info")
    data = ensure_config()
    current = (data or {}).get("CurrentEQ", {}) or {}

    return {
        "name": current.get("name") or "",
        "ipaddr": current.get("ipaddr") or req.ip_address,
        "slots_dict": current.get("slots_dict") or {},
        "viavi": (data or {}).get("VIAVIcontrol", {}).get("settings", {}),
        "loopback": current.get("loopback", {}),
    }


@router.post("/device/unmask", summary="Размаскирование аварий")
async def run_unmask(req: DeviceInfoRequest, tunnel_service: TunnelService = Depends(get_tunnel_service)):
    ip = req.ip_address
    password = req.password or ""
    username = "admin"

    lease_key = "unmask alarm"

    def _run_proxy() -> None:
        try:
            lease = tunnel_service.reserve(
                lease_key,
                "unmask",
                ip=ip,
                username=username,
                password=password,
                ttl=900.0,
                track=True,
            )
            add_log(
                f"SNMP tunnel ready at {lease.host}:{lease.port} for {ip}",
                "INFO",
            )
        except TunnelManagerError as exc:
            add_log(f"SNMP tunnel reservation failed: {exc}", "ERROR")

    threading.Thread(target=_run_proxy, daemon=True).start()
    try:
        await alarmplusmask()
        await alarmplusmaslcnctSTM()
        await setSFP_Mode()

    except Exception as exc:
        add_log(f"Unmask is failed: {exc}", "ERROR")


__all__ = ["router"]

"""Endpoints related to device metadata and SNMP proxy initialisation."""
from __future__ import annotations
import threading
from typing import Any, Dict
import sys
from fastapi import APIRouter, Depends

from MainConnectFunc import equpimentV7, get_device_info, oidsSNMP
from unit_tests.SnmpV7alarm import setSFP_Mode, alarmplusmaslcnctSTM, alarmplusmask

from .config import ensure_config, json_input, json_set
from .logs import add_log
from backend.services.models import DeviceInfoRequest, ViaviSettings, ViaviUnitSettings, UpgradeRequestImg, \
    UpgradeRequestBlock
from .services.tunnels import TunnelManagerError, TunnelService, get_tunnel_service
from device_upgrade.slot_update import *

router = APIRouter(tags=["device"])

upgrade_state = {
    "log": "",
    "is_running": False
}


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


def _save_device_to_registry(data: Dict[str, Any], req: DeviceInfoRequest) -> None:
    ip = req.ip_address
    if not ip:
        return
    current = (data or {}).get("CurrentEQ", {}) or {}
    payload: Dict[str, Any] = {
        "name": current.get("name") or "",
        "ipaddr": ip,
        "pass": req.password or "",
        "slots_dict": current.get("slots_dict") or {},
        "loopback": current.get("loopback") or {},
        "snmp_type": current.get("snmp_type") or "",
        "active_slots": current.get("active_slots") or {},
    }
    json_set(["Devices", ip], payload)


def _update_img_by_type():
    dev = oidsSNMP()["name"]
    if dev == "OSM-KMv3":
        pass
    elif dev == "OSM-Kv7":
        pass


def _update_block_fpga(request_data):
    global upgrade_state

    data_dict = request_data.model_dump()
    commands = block_update_by_dev(data_dict.get("block_type"), data_dict.get("slots"))
    try:
        for chunk in ssh_exec_commands(commands):
            upgrade_state["log"] += chunk

            sys.stdout.write(chunk)
            sys.stdout.flush()

    except Exception as e:
        upgrade_state["log"] += f"\n[SSH ERROR]: {str(e)}\n"
    finally:
        upgrade_state["is_running"] = False


def _run_img_upgrade_logic(request_data):
    global upgrade_state
    data = request_data.model_dump()
    image_type = data.get("image")

    command = image_update_by_dev(image_type)

    upgrade_state["is_running"] = True
    upgrade_state["log"] = f"🚀 Запуск обновления образа ({image_type})...\n"

    try:
        for chunk in ssh_exec_commands([command], timeout_seconds=1800):
            upgrade_state["log"] += chunk
            sys.stdout.write(chunk)
            sys.stdout.flush()
    except Exception as e:
        upgrade_state["log"] += f"\n[ERROR]: {str(e)}\n"
    finally:
        upgrade_state["is_running"] = False


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
                await json_input(["CurrentEQ", "loopback"], payload)
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
    try:
        _save_device_to_registry(data, req)
    except Exception as exc:
        add_log(f"save device in registry failed: {exc}", "ERROR")
    devices = (ensure_config() or {}).get("Devices", {}) or {}

    return {
        "name": current.get("name") or "",
        "ipaddr": current.get("ipaddr") or req.ip_address,
        "slots_dict": current.get("slots_dict") or {},
        "viavi": (data or {}).get("VIAVIcontrol", {}).get("settings", {}),
        "loopback": current.get("loopback", {}),
        "devices": devices,
    }


@router.post("/firmware/upgrade/img")
async def upgrade_firmware_img(request_data: UpgradeRequestImg):
    # Запускаем в фоне
    threading.Thread(target=_run_img_upgrade_logic, args=(request_data,), daemon=True).start()
    return {"status": "success"}


@router.get("/firmware/upgrade/log")
async def get_upgrade_log():
    # Возвращаем словарь с обязательным полем "status"
    return {
        "status": "success",
        "log": upgrade_state["log"],
        "is_running": upgrade_state["is_running"]}


@router.post("/firmware/upgrade/block")
async def upgrade_firmware_block(request_data: UpgradeRequestBlock):
    def _run_upgrade():
        upgrade_state["is_running"] = True
        upgrade_state["log"] = "Начало процесса прошивки...\n"
        _update_block_fpga(request_data)
        upgrade_state["is_running"] = False

    threading.Thread(target=_run_upgrade, daemon=True).start()
    return {"status": "success"}


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

"""State management helpers for the Streamlit frontend."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from MainConnectFunc import json_input
from frontend.constants import DEFAULT_API_BASE_URL, STATE_FILE

DEVICE_PROFILES_FILE = Path("CurrentEQ.yaml")


def _default_viavi_config() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Return a fresh empty Viavi configuration structure."""

    return {
        "NumOne": {"ipaddr": "", "typeofport": {"Port1": "", "Port2": ""}},
        "NumTwo": {"ipaddr": "", "typeofport": {"Port1": "", "Port2": ""}},
    }


def _default_selected_tests_map() -> Dict[str, List[str]]:
    """Return the default storage for alarm and sync test selections."""

    return {"alarm": [], "sync": [], "stat": [], "comm": [], "other": []}


def _normalise_snmp_type(value: Any) -> str:
    raw = "" if value is None else str(value).strip()
    if not raw:
        return "SnmpV2"
    key = raw.lower().replace("_", "").replace("-", "")
    if key in {"snmpv3", "snmp3", "v3"} or key.endswith("v3") or key.endswith("3"):
        return "SnmpV3"
    if key in {"snmpv2", "snmpv2c", "snmp2", "v2", "v2c"} or key.endswith("v2") or key.endswith("2"):
        return "SnmpV2"
    return raw


def _load_device_profiles_payload() -> Dict[str, Any]:
    """Read the local Streamlit device-profile registry.

    The file is named CurrentEQ.yaml for backwards compatibility, but the
    existing frontend stores JSON in it.
    """

    if not DEVICE_PROFILES_FILE.exists():
        return {"selected_device_id": "", "devices": {}}
    try:
        payload = json.loads(DEVICE_PROFILES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"selected_device_id": "", "devices": {}}

    if isinstance(payload, dict) and isinstance(payload.get("devices"), dict):
        return payload

    current = payload.get("CurrentEQ") if isinstance(payload, dict) else None
    if isinstance(current, dict) and current.get("ipaddr"):
        return {"selected_device_id": str(current.get("ipaddr")), "devices": {str(current.get("ipaddr")): current}}

    return {"selected_device_id": "", "devices": {}}


def _get_profile_by_ip(ip: str) -> Dict[str, Any]:
    ip = str(ip or "").strip()
    if not ip:
        return {}
    payload = _load_device_profiles_payload()
    devices = payload.get("devices") if isinstance(payload, dict) else {}
    profile = devices.get(ip) if isinstance(devices, dict) else None
    return copy.deepcopy(profile) if isinstance(profile, dict) else {}


def _write_device_profiles_payload(payload: Dict[str, Any]) -> None:
    try:
        DEVICE_PROFILES_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # State persistence should not break UI rendering.
        return


def _normalise_viavi_config(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return _default_viavi_config()

    # Some snapshots may contain the whole VIAVIcontrol block.
    if isinstance(value.get("settings"), dict):
        value = value.get("settings") or {}

    out: Dict[str, Any] = {}
    for name, raw in value.items():
        if not isinstance(raw, dict):
            continue
        typeof = raw.get("typeofport") or {}
        if not isinstance(typeof, dict):
            typeof = {}
        out[str(name)] = {
            "ipaddr": str(raw.get("ipaddr", "") or ""),
            "port": raw.get("port", 8006),
            "typeofport": {
                "Port1": str(typeof.get("Port1", "") or ""),
                "Port2": str(typeof.get("Port2", "") or ""),
            },
        }

    return out or _default_viavi_config()


def _viavi_index_from_name(name: str) -> int | str:
    suffix = str(name).replace("Num", "", 1)
    return {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}.get(suffix, suffix)


def _sync_viavi_widget_keys(viavi: Dict[str, Any]) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("viavi") and (key.endswith("_ip") or key.endswith("_port1") or key.endswith("_port2")):
            st.session_state.pop(key, None)

    for node_name, node_data in viavi.items():
        idx = _viavi_index_from_name(node_name)
        typeof = node_data.get("typeofport") or {}
        st.session_state[f"viavi{idx}_ip"] = node_data.get("ipaddr", "") or ""
        st.session_state[f"viavi{idx}_port1"] = typeof.get("Port1", "") or ""
        st.session_state[f"viavi{idx}_port2"] = typeof.get("Port2", "") or ""

    st.session_state["viavi_count"] = max(1, min(5, len(viavi)))


def _normalise_wiring_rows(rows: Any) -> List[Dict[str, str]]:
    if not isinstance(rows, list):
        return []
    cleaned: List[Dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        dev_slot = item.get("dev_slot") or item.get("dut_slot", "")
        dev_port = item.get("dev_port") or item.get("dut_port", "")
        dev_interface = item.get("dev_interface") or item.get("dut_interface", "")
        cleaned.append(
            {
                "viavi_device": str(item.get("viavi_device", "") or ""),
                "viavi_port": str(item.get("viavi_port", "") or ""),
                "viavi_interface": str(item.get("viavi_interface", "") or ""),
                "dev_slot": str(dev_slot or ""),
                "dev_port": str(dev_port or ""),
                "dev_interface": str(dev_interface or ""),
                "cable_id": str(item.get("cable_id", "") or ""),
            }
        )
    return cleaned


def _reset_slot_checkboxes(slots: Dict[str, Any], active_slots: Dict[str, Any]) -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith("chk_"):
            st.session_state.pop(key, None)

    for slot_id in (slots or {}).keys():
        st.session_state[f"chk_{slot_id}"] = str(slot_id) in {str(k) for k in active_slots.keys()}


def _apply_device_profile_to_session(profile: Dict[str, Any], ip: str) -> None:
    """Atomically apply all device-scoped UI settings from a profile.

    Without this, loading a profile changes only ip/pass/snmp fields and leaves
    stale slots_dict, active_slots, VIAVI and wiring from the previously selected
    device in Streamlit session_state.
    """

    profile = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    ip = str(profile.get("ipaddr") or ip or "").strip()
    password = profile.get("pass", profile.get("password", "")) or ""
    snmp_type = _normalise_snmp_type(profile.get("snmp_type"))
    slots = profile.get("slots_dict") if isinstance(profile.get("slots_dict"), dict) else {}
    loopback = profile.get("loopback") if isinstance(profile.get("loopback"), dict) else {}
    active_slots = profile.get("active_slots") if isinstance(profile.get("active_slots"), dict) else {}
    viavi = _normalise_viavi_config(profile.get("viavi_config") or profile.get("viavi") or profile.get("VIAVIcontrol"))
    wiring = _normalise_wiring_rows(profile.get("wiring") or profile.get("viavi_wiring"))

    device_info = copy.deepcopy(profile)
    device_info["ipaddr"] = ip
    device_info["pass"] = password
    device_info["password"] = password
    device_info["snmp_type"] = snmp_type
    device_info["slots_dict"] = slots
    device_info["loopback"] = loopback
    device_info["active_slots"] = active_slots

    st.session_state["device_info"] = device_info
    st.session_state["ip_address_input"] = ip
    st.session_state["password_input"] = password
    st.session_state["snmp_type_select"] = snmp_type
    st.session_state["active_slots"] = active_slots
    st.session_state["saved_loopback"] = loopback
    st.session_state["slot_loopback"] = loopback.get("slot")
    st.session_state["port_loopback"] = loopback.get("port")
    st.session_state["viavi_config"] = viavi
    st.session_state["wiring"] = wiring

    _sync_viavi_widget_keys(viavi)
    _reset_slot_checkboxes(slots, active_slots)


def _build_minimal_device_info_from_inputs(ip: str, snmp_type: str, password: str) -> Dict[str, Any]:
    loopback = {}
    if st.session_state.get("slot_loopback") is not None:
        loopback["slot"] = st.session_state.get("slot_loopback")
    if st.session_state.get("port_loopback") is not None:
        loopback["port"] = st.session_state.get("port_loopback")
    return {
        "name": "",
        "ipaddr": ip,
        "pass": password,
        "password": password,
        "snmp_type": snmp_type,
        "slots_dict": {},
        "loopback": loopback,
        "active_slots": {},
    }


def _sync_device_info_from_inputs() -> None:
    """Keep device_info aligned with the currently selected profile/form values."""

    ip = str(st.session_state.get("ip_address_input", "") or "").strip()
    snmp_type = _normalise_snmp_type(st.session_state.get("snmp_type_select"))
    password = str(st.session_state.get("password_input", "") or "")
    device_info = st.session_state.get("device_info")
    current_ip = ""
    if isinstance(device_info, dict):
        current_ip = str(device_info.get("ipaddr") or "").strip()

    # If the selected IP changed, do not mutate the previous device_info in
    # place. Load the complete saved profile or create a clean minimal snapshot.
    if ip and current_ip and current_ip != ip:
        profile = _get_profile_by_ip(ip)
        if profile:
            _apply_device_profile_to_session(profile, ip)
            return
        st.session_state["device_info"] = _build_minimal_device_info_from_inputs(ip, snmp_type, password)
        st.session_state["active_slots"] = {}
        st.session_state["wiring"] = []
        _reset_slot_checkboxes({}, {})
        return

    if ip and not isinstance(device_info, dict):
        profile = _get_profile_by_ip(ip)
        if profile:
            _apply_device_profile_to_session(profile, ip)
        else:
            st.session_state["device_info"] = _build_minimal_device_info_from_inputs(ip, snmp_type, password)
        return

    if not isinstance(device_info, dict):
        return

    if ip:
        device_info["ipaddr"] = ip
    device_info["snmp_type"] = snmp_type
    device_info["pass"] = password
    device_info["password"] = password

    loopback = device_info.get("loopback")
    if not isinstance(loopback, dict):
        loopback = {}
    if st.session_state.get("slot_loopback") is not None:
        loopback["slot"] = st.session_state.get("slot_loopback")
    if st.session_state.get("port_loopback") is not None:
        loopback["port"] = st.session_state.get("port_loopback")
    if loopback:
        device_info["loopback"] = loopback

    active_slots = st.session_state.get("active_slots")
    if isinstance(active_slots, dict):
        device_info["active_slots"] = active_slots

    st.session_state["device_info"] = device_info


def _persist_current_profile_snapshot() -> None:
    ip = str(st.session_state.get("ip_address_input", "") or "").strip()
    if not ip:
        return

    payload = _load_device_profiles_payload()
    devices = payload.setdefault("devices", {})
    if not isinstance(devices, dict):
        devices = {}
        payload["devices"] = devices

    device_info = st.session_state.get("device_info") if isinstance(st.session_state.get("device_info"), dict) else {}
    current = copy.deepcopy(devices.get(ip, {})) if isinstance(devices.get(ip), dict) else {}
    current.update(copy.deepcopy(device_info))
    current["ipaddr"] = ip
    current["pass"] = str(st.session_state.get("password_input", "") or current.get("pass", "") or "")
    current["password"] = current["pass"]
    current["snmp_type"] = _normalise_snmp_type(st.session_state.get("snmp_type_select") or current.get("snmp_type"))
    current["slots_dict"] = device_info.get("slots_dict") if isinstance(device_info.get("slots_dict"), dict) else current.get("slots_dict", {})
    current["loopback"] = device_info.get("loopback") if isinstance(device_info.get("loopback"), dict) else {
        "slot": st.session_state.get("slot_loopback"),
        "port": st.session_state.get("port_loopback"),
    }
    current["active_slots"] = st.session_state.get("active_slots", {}) or {}
    current["viavi_config"] = copy.deepcopy(st.session_state.get("viavi_config") or _default_viavi_config())
    current["wiring"] = _normalise_wiring_rows(st.session_state.get("wiring") or [])

    devices[ip] = current
    payload["selected_device_id"] = ip
    _write_device_profiles_payload(payload)


def initialize_session_state() -> None:
    """Populate frequently used keys in :mod:`streamlit.session_state`."""
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)
    st.session_state.setdefault("device_info", None)
    st.session_state.setdefault("ip_address_input", "")
    st.session_state.setdefault("password_input", "")
    st.session_state.setdefault("snmp_type_select", "SnmpV2")
    st.session_state.setdefault("test_type_radio", "alarm")
    st.session_state.setdefault("selected_tests", [])
    st.session_state.setdefault("selected_test_labels", [])
    st.session_state.setdefault("selected_tests_by_type", _default_selected_tests_map())
    st.session_state.setdefault("current_job_id", None)
    st.session_state.setdefault("viavi_config", _default_viavi_config())
    st.session_state.setdefault("wiring", [])
    st.session_state.setdefault("active_slots", {})


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state() -> None:
    _sync_device_info_from_inputs()
    asyncio.run(json_input(["CurrentEQ", "loopback", "slot"], st.session_state.get("slot_loopback", "")))
    asyncio.run(json_input(["CurrentEQ", "loopback", "port"], st.session_state.get("port_loopback", "")))
    state = {
        "api_base_url": st.session_state.get("api_base_url", DEFAULT_API_BASE_URL),
        "device_info": st.session_state.get("device_info"),
        "ip_address_input": st.session_state.get("ip_address_input", ""),
        "password_input": st.session_state.get("password_input", ""),
        "snmp_type_select": st.session_state.get("snmp_type_select", "SnmpV2"),
        "test_type_radio": st.session_state.get("test_type_radio", "alarm"),
        "viavi_count": st.session_state.get("viavi_count", 1),
        "viavi_config": st.session_state.get("viavi_config", _default_viavi_config()),
        "wiring": st.session_state.get("wiring", []),
        "slot_loopback": st.session_state.get("slot_loopback"),
        "port_loopback": st.session_state.get("port_loopback"),
        "selected_tests": st.session_state.get("selected_tests"),
        "selected_test_labels": st.session_state.get("selected_test_labels"),
        "selected_tests_by_type": st.session_state.get(
            "selected_tests_by_type", _default_selected_tests_map()
        ),
        "selected_test_labels_by_type": st.session_state.get(
            "selected_test_labels_by_type", _default_selected_tests_map()
        ),
        "active_slots": st.session_state.get("active_slots", {}),
        "current_job_id": st.session_state.get("current_job_id"),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    _persist_current_profile_snapshot()


def on_slot_change():
    dev = st.session_state.get("device_info", {})
    slots = dev.get("slots_dict", {})
    st.session_state["active_slots"] = {
        slot_id: slot_name
        for slot_id, slot_name in slots.items()
        if st.session_state.get(f"chk_{slot_id}")}
    save_state()
    asyncio.run(json_input(["CurrentEQ", 'active_slots'], new_value=st.session_state["active_slots"]))


def apply_state() -> None:
    saved = load_state()
    if not saved:
        return

    # 1. Загрузка стандартных полей
    for key in [
        "api_base_url",
        "device_info",
        "ip_address_input",
        "password_input",
        "snmp_type_select",
        "test_type_radio",
        "slot_loopback",
        "port_loopback",
        "current_job_id",
        "active_slots"
    ]:
        if key in saved:
            st.session_state[key] = saved[key]

    # 2. Восстановление количества вкладок VIAVI
    st.session_state["viavi_count"] = saved.get("viavi_count", 1)

    # 3. Динамическая загрузка конфигурации VIAVI
    viavi_saved = saved.get("viavi_config", {})
    viavi_final = _normalise_viavi_config(viavi_saved)
    _sync_viavi_widget_keys(viavi_final)
    st.session_state["viavi_config"] = viavi_final

    # 4. Загрузка тестов (оригинальная логика)
    tests_by_type = _default_selected_tests_map()
    saved_tests_by_type = saved.get("selected_tests_by_type")
    if isinstance(saved_tests_by_type, dict):
        for key, value in saved_tests_by_type.items():
            if key in tests_by_type and isinstance(value, list):
                tests_by_type[key] = [item for item in value if isinstance(item, str)]
    elif isinstance(saved.get("selected_tests"), list):
        tests_by_type[saved.get("test_type_radio", "alarm")] = [
            item for item in saved.get("selected_tests", []) if isinstance(item, str)
        ]
    st.session_state["selected_tests_by_type"] = tests_by_type

    labels_by_type = _default_selected_tests_map()
    saved_labels_by_type = saved.get("selected_test_labels_by_type")
    if isinstance(saved_labels_by_type, dict):
        for key, value in saved_labels_by_type.items():
            if key in labels_by_type and isinstance(value, list):
                labels_by_type[key] = [item for item in value if isinstance(item, str)]
    elif isinstance(saved.get("selected_test_labels"), list):
        labels_by_type[saved.get("test_type_radio", "alarm")] = [
            item for item in saved.get("selected_test_labels", [])
            if isinstance(item, str)
        ]
    st.session_state["selected_test_labels_by_type"] = labels_by_type

    current_type = st.session_state.get("test_type_radio", "alarm")
    st.session_state["selected_tests"] = tests_by_type.get(current_type, [])
    st.session_state["selected_test_labels"] = labels_by_type.get(current_type, [])

    # 5. Загрузка Wiring (оригинальная логика)
    st.session_state["wiring"] = _normalise_wiring_rows(saved.get("wiring", []))

    # 6. Активные слоты (оригинальная логика)
    active_slots = st.session_state.get("active_slots", {})
    dev = st.session_state.get("device_info")
    if dev and isinstance(dev.get("slots_dict"), dict):
        _reset_slot_checkboxes(dev["slots_dict"], active_slots)


def on_change() -> None:
    save_state()


def viavi_sync_from_widgets() -> None:
    viavi = {}
    count = st.session_state.get("viavi_count", 1)
    num_map = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}

    for i in range(1, count + 1):
        suffix = num_map.get(i, str(i))
        key_name = f"Num{suffix}"
        viavi[key_name] = {
            "ipaddr": st.session_state.get(f"viavi{i}_ip", ""),
            "typeofport": {
                "Port1": st.session_state.get(f"viavi{i}_port1", ""),
                "Port2": st.session_state.get(f"viavi{i}_port2", ""),
            }
        }
        asyncio.run(json_input(["VIAVIcontrol", "settings", key_name, "ipaddr"], viavi[key_name]["ipaddr"]))
        asyncio.run(json_input(["VIAVIcontrol", "settings", key_name, "typeofport", "Port1"],
                               viavi[key_name]["typeofport"]["Port1"]))
        asyncio.run(json_input(["VIAVIcontrol", "settings", key_name, "typeofport", "Port2"],
                               viavi[key_name]["typeofport"]["Port2"]))
    st.session_state["viavi_config"] = viavi
    save_state()

"""State management helpers for the Streamlit frontend."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import streamlit as st
from MainConnectFunc import CURRENT_EQ_YAML_PATH, json_input
from frontend.constants import DEFAULT_API_BASE_URL, STATE_FILE

try:
    import yaml
except ImportError:  # optional dependency
    yaml = None


def _trim(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_snmp_type(value: Any) -> str:
    raw = _trim(value)
    if not raw:
        return "SnmpV2"
    key = raw.lower().replace("_", "").replace("-", "")
    if key in {"snmpv3", "snmp3", "v3"} or key.endswith("v3") or key.endswith("3"):
        return "SnmpV3"
    if key in {"snmpv2", "snmpv2c", "snmp2", "v2", "v2c"} or key.endswith("v2") or key.endswith("2"):
        return "SnmpV2"
    return raw


def _load_current_eq_profiles() -> Dict[str, Dict[str, Any]]:
    """Read saved device profiles from CurrentEQ.yaml.

    The file is YAML in normal operation, but JSON is accepted as a fallback
    because older versions wrote JSON-compatible content into the same file.
    """
    if not CURRENT_EQ_YAML_PATH.exists():
        return {}

    try:
        text = CURRENT_EQ_YAML_PATH.read_text(encoding="utf-8")
    except Exception:
        return {}

    if not text.strip():
        return {}

    data: Any = None
    if yaml is not None:
        try:
            data = yaml.safe_load(text) or {}
        except Exception:
            data = None

    if data is None:
        try:
            data = json.loads(text)
        except Exception:
            data = {}

    if not isinstance(data, dict):
        return {}

    profiles = data.get("devices")
    if not isinstance(profiles, dict):
        profiles = {}

    # Backward compatibility with the old single-profile shape:
    # CurrentEQ:
    #   ipaddr: ...
    legacy_profile = data.get("CurrentEQ")
    if isinstance(legacy_profile, dict):
        legacy_ip = _trim(legacy_profile.get("ipaddr"))
        if legacy_ip and legacy_ip not in profiles:
            profiles[legacy_ip] = legacy_profile

    return {str(k): v for k, v in profiles.items() if isinstance(v, dict)}


def _profile_to_device_info(profile_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    device_info = dict(profile)
    profile_ip = _trim(device_info.get("ipaddr")) or _trim(profile_id)
    if profile_ip:
        device_info["ipaddr"] = profile_ip
    device_info["snmp_type"] = _normalise_snmp_type(device_info.get("snmp_type"))
    return device_info


def _sync_loaded_profile_from_yaml() -> None:
    """Keep Streamlit widget state and device_info aligned after profile load.

    The configuration page writes ip/password/snmp_type when the user clicks
    "Загрузить профиль". Before this fix, device_info could still contain the
    previous device and then the UI/test launcher used that stale IP.
    """
    selected_profile = _trim(st.session_state.get("selected_device_profile"))
    if not selected_profile:
        return

    profiles = _load_current_eq_profiles()
    profile = profiles.get(selected_profile)
    if not isinstance(profile, dict):
        return

    profile_ip = _trim(profile.get("ipaddr")) or selected_profile
    current_ip = _trim(st.session_state.get("ip_address_input"))

    # Do not override manual edits. Sync only when the current IP already
    # matches the loaded profile or the selected profile id.
    if current_ip and current_ip not in {profile_ip, selected_profile}:
        return

    device_info = _profile_to_device_info(selected_profile, profile)
    st.session_state["device_info"] = device_info
    st.session_state["ip_address_input"] = profile_ip
    st.session_state["password_input"] = _trim(device_info.get("pass"))
    st.session_state["snmp_type_select"] = _normalise_snmp_type(device_info.get("snmp_type"))

    loopback = device_info.get("loopback")
    if isinstance(loopback, dict):
        if "slot" in loopback:
            st.session_state["slot_loopback"] = loopback.get("slot")
        if "port" in loopback:
            st.session_state["port_loopback"] = loopback.get("port")
        st.session_state["saved_loopback"] = loopback

    active_slots = device_info.get("active_slots")
    if isinstance(active_slots, dict):
        st.session_state["active_slots"] = active_slots


def _default_viavi_config() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Return a fresh empty Viavi configuration structure."""

    return {
        "NumOne": {"ipaddr": "", "typeofport": {"Port1": "", "Port2": ""}},
        "NumTwo": {"ipaddr": "", "typeofport": {"Port1": "", "Port2": ""}},
    }


def _default_selected_tests_map() -> Dict[str, List[str]]:
    """Return the default storage for alarm and sync test selections."""

    return {"alarm": [], "sync": [], "stat": [], "comm": [], "other": []}


def initialize_session_state() -> None:
    """Populate frequently used keys in :mod:`streamlit.session_state`."""
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)
    st.session_state.setdefault("device_info", None)
    st.session_state.setdefault("ip_address_input", "")
    st.session_state.setdefault("password_input", "")
    st.session_state.setdefault("snmp_type_select", "SnmpV2")
    st.session_state.setdefault("selected_device_profile", "")
    st.session_state.setdefault("test_type_radio", "alarm")
    st.session_state.setdefault("selected_tests", [])
    st.session_state.setdefault("selected_test_labels", [])
    st.session_state.setdefault("selected_tests_by_type", _default_selected_tests_map())
    st.session_state.setdefault("current_job_id", None)
    st.session_state.setdefault("viavi_config", _default_viavi_config())
    st.session_state.setdefault("wiring", [], )
    st.session_state.setdefault("active_slots", {})


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state() -> None:
    _sync_loaded_profile_from_yaml()
    asyncio.run(json_input(["CurrentEQ", "loopback", "slot"], st.session_state.get("slot_loopback", "")))
    asyncio.run(json_input(["CurrentEQ", "loopback", "port"], st.session_state.get("port_loopback", "")))
    state = {
        "api_base_url": st.session_state.get("api_base_url", DEFAULT_API_BASE_URL),
        "device_info": st.session_state.get("device_info"),
        "ip_address_input": st.session_state.get("ip_address_input", ""),
        "password_input": st.session_state.get("password_input", ""),
        "snmp_type_select": st.session_state.get("snmp_type_select", "SnmpV2"),
        "selected_device_profile": st.session_state.get("selected_device_profile", ""),
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
        "active_slots": st.session_state.get("active_slots", {}),
        "current_job_id": st.session_state.get("current_job_id"),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


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
        "selected_device_profile",
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
    viavi_final = {}
    # Маппинг для обратной совместимости имен
    num_map_inv = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

    if isinstance(viavi_saved, dict):
        for node_name, node_data in viavi_saved.items():
            if not isinstance(node_data, dict):
                continue

            # Определяем индекс для ключей session_state (из NumOne -> 1, из Num3 -> 3)
            suffix = node_name.replace("Num", "")
            idx = num_map_inv.get(suffix, suffix)

            # Извлекаем данные прибора
            ip = node_data.get("ipaddr", "") or ""
            typeofport_saved = node_data.get("typeofport", {})
            p1 = typeofport_saved.get("Port1", "") or ""
            p2 = typeofport_saved.get("Port2", "") or ""

            # Сохраняем в общую структуру
            viavi_final[node_name] = {
                "ipaddr": ip,
                "typeofport": {"Port1": p1, "Port2": p2}
            }

            # Наполняем session_state для связи с виджетами во вкладках
            st.session_state[f"viavi{idx}_ip"] = ip
            st.session_state[f"viavi{idx}_port1"] = p1
            st.session_state[f"viavi{idx}_port2"] = p2

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
    wiring_saved = saved.get("wiring", [])
    if isinstance(wiring_saved, list):
        wiring_clean = []
        for item in wiring_saved:
            if not isinstance(item, dict):
                continue
            dev_slot = item.get("dev_slot") or item.get("dut_slot", "")
            dev_port = item.get("dev_port") or item.get("dut_port", "")
            dev_interface = item.get("dev_interface") or item.get("dut_interface", "")

            wiring_clean.append({
                "viavi_device": str(item.get("viavi_device", "") or ""),
                "viavi_port": str(item.get("viavi_port", "") or ""),
                "viavi_interface": str(item.get("viavi_interface", "") or ""),
                "dev_slot": str(dev_slot or ""),
                "dev_port": str(dev_port or ""),
                "dev_interface": str(dev_interface or ""),
                "cable_id": str(item.get("cable_id", "") or ""),
            })
        st.session_state["wiring"] = wiring_clean
    else:
        st.session_state["wiring"] = []

    # 6. Активные слоты (оригинальная логика)
    active_slots = st.session_state.get("active_slots", {})
    dev = st.session_state.get("device_info")
    if dev and isinstance(dev.get("slots_dict"), dict):
        for slot_id in dev["slots_dict"].keys():
            st.session_state[f"chk_{slot_id}"] = str(slot_id) in active_slots


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

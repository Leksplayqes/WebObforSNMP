"""State management helpers for the Streamlit frontend."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import streamlit as st
from MainConnectFunc import json_input
from pathlib import Path
from frontend.constants import DEFAULT_API_BASE_URL, STATE_FILE


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
    st.session_state.setdefault("test_type_radio", "alarm")
    st.session_state.setdefault("selected_tests", [])
    st.session_state.setdefault("selected_test_labels", [])
    st.session_state.setdefault("selected_tests_by_type", _default_selected_tests_map())
    st.session_state.setdefault("current_job_id", None)
    st.session_state.setdefault("viavi_config", _default_viavi_config())
    st.session_state.setdefault("wiring", [], )
    st.session_state.setdefault("active_slots", {})


def _state_file_for_device(device_key: str | None = None) -> Path:
    if not device_key:
        return STATE_FILE
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(device_key))
    return STATE_FILE.with_name(f"{STATE_FILE.stem}_{safe}{STATE_FILE.suffix}")


def load_state(device_key: str | None = None) -> Dict[str, Any]:
    state_file = _state_file_for_device(device_key)
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(device_key: str | None = None) -> None:
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
        "active_slots": st.session_state.get("active_slots", {}),
        "current_job_id": st.session_state.get("current_job_id"),
    }
    _state_file_for_device(device_key).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def on_slot_change():
    dev = st.session_state.get("device_info", {})
    slots = dev.get("slots_dict", {})
    st.session_state["active_slots"] = {
        slot_id: slot_name
        for slot_id, slot_name in slots.items()
        if st.session_state.get(f"chk_{slot_id}")}
    save_state()


def apply_state(device_key: str | None = None) -> None:
    saved = load_state(device_key)
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

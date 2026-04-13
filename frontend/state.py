"""State management helpers for the Streamlit frontend."""
from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st
from MainConnectFunc import json_input
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


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state() -> None:
    json_input(["CurrentEQ", "loopback", "slot"], st.session_state.get("slot_loopback", ""))
    json_input(["CurrentEQ", "loopback", "port"], st.session_state.get("port_loopback", ""))
    state = {
        "api_base_url": st.session_state.get("api_base_url", DEFAULT_API_BASE_URL),
        "device_info": st.session_state.get("device_info"),
        "ip_address_input": st.session_state.get("ip_address_input", ""),
        "password_input": st.session_state.get("password_input", ""),
        "snmp_type_select": st.session_state.get("snmp_type_select", "SnmpV2"),
        "test_type_radio": st.session_state.get("test_type_radio", "alarm"),
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
    json_input(["CurrentEQ", 'active_slots'], new_value=st.session_state["active_slots"])


def apply_state() -> None:
    saved = load_state()
    if not saved:
        return

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

    viavi_saved = saved.get("viavi_config")
    viavi = _default_viavi_config()
    if isinstance(viavi_saved, dict):
        for node in ("NumOne", "NumTwo"):
            node_saved = viavi_saved.get(node)
            if not isinstance(node_saved, dict):
                continue
            viavi[node]["ipaddr"] = node_saved.get("ipaddr", "") or ""
            typeofport_saved = node_saved.get("typeofport")
            if isinstance(typeofport_saved, dict):
                for port in ("Port1", "Port2"):
                    viavi[node]["typeofport"][port] = typeofport_saved.get(port, "") or ""

    st.session_state["viavi_config"] = viavi
    st.session_state["viavi1_ip"] = viavi["NumOne"]["ipaddr"]
    st.session_state["viavi1_port1"] = viavi["NumOne"]["typeofport"]["Port1"]
    st.session_state["viavi1_port2"] = viavi["NumOne"]["typeofport"]["Port2"]
    st.session_state["viavi2_ip"] = viavi["NumTwo"]["ipaddr"]
    st.session_state["viavi2_port1"] = viavi["NumTwo"]["typeofport"]["Port1"]
    st.session_state["viavi2_port2"] = viavi["NumTwo"]["typeofport"]["Port2"]

    wiring_saved = saved.get("wiring", [])

    if isinstance(wiring_saved, list):
        wiring_clean = []
        for item in wiring_saved:
            if not isinstance(item, dict):
                continue
            dev_slot = item.get("dev_slot")
            dev_port = item.get("dev_port")
            dev_interface = item.get("dev_interface")
            if dev_slot is None and "dut_slot" in item:
                dev_slot = item.get("dut_slot")
            if dev_port is None and "dut_port" in item:
                dev_port = item.get("dut_port")
            if dev_interface is None and "dut_interface" in item:
                dev_interface = item.get("dut_interface")

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
    active_slots = st.session_state.get("active_slots", {})
    dev = st.session_state.get("device_info")
    if dev and isinstance(dev.get("slots_dict"), dict):
        for slot_id in dev["slots_dict"].keys():
            st.session_state[f"chk_{slot_id}"] = str(slot_id) in active_slots


def on_change() -> None:
    save_state()


def viavi_sync_from_widgets() -> None:
    viavi = st.session_state.setdefault("viavi_config", _default_viavi_config())
    viavi["NumOne"]["ipaddr"] = st.session_state.get("viavi1_ip", "")
    viavi["NumOne"]["typeofport"]["Port1"] = st.session_state.get("viavi1_port1", "")
    viavi["NumOne"]["typeofport"]["Port2"] = st.session_state.get("viavi1_port2", "")
    viavi["NumTwo"]["ipaddr"] = st.session_state.get("viavi2_ip", "")
    viavi["NumTwo"]["typeofport"]["Port1"] = st.session_state.get("viavi2_port1", "")
    viavi["NumTwo"]["typeofport"]["Port2"] = st.session_state.get("viavi2_port2", "")

    json_input(["VIAVIcontrol", "settings", "NumOne", "ipaddr"],
               st.session_state.get("viavi1_ip", ""))
    json_input(["VIAVIcontrol", "settings", "NumTwo", "ipaddr"],
               st.session_state.get("viavi2_ip", ""))
    json_input(["VIAVIcontrol", "settings", "NumOne", "typeofport", "Port1"],
               st.session_state.get("viavi1_port1", ""))
    json_input(["VIAVIcontrol", "settings", "NumOne", "typeofport", "Port2"],
               st.session_state.get("viavi1_port2", ""))
    json_input(["VIAVIcontrol", "settings", "NumTwo", "typeofport", "Port1"],
               st.session_state.get("viavi2_port1", ""))
    json_input(["VIAVIcontrol", "settings", "NumTwo", "typeofport", "Port2"],
               st.session_state.get("viavi2_port2", ""))
    save_state()


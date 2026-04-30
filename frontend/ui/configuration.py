from __future__ import annotations

import asyncio
import time

from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from backend.device import upgrade_firmware_img, upgrade_firmware_block, upgrade_state
from api import BackendApiClient, BackendApiError, normalise_nodeids
from MainConnectFunc import oids, json_input, oidsSNMP, ssh_exec_commands
from state import on_change, save_state, viavi_sync_from_widgets, on_slot_change, apply_state
from device_upgrade.slot_update import block_update_by_dev

# ------------------------------- Constants -------------------------------

PORT_OPTIONS = ["", "STM-1", "STM-4", "STM-16", "STM-64"]

LOOPBACK_SLOTS: List[int] = [3, 4, 5, 6, 7, 8, 11, 12, 13, 14]
LOOPBACK_PORTS: List[int] = [1, 2, 3, 4, 5, 6, 7, 8]


# ------------------------------- Helpers -------------------------------

def _trim(v: object) -> str:
    return "" if v is None else str(v).strip()


def _flash(message: str, level: str = "success", seconds: int = 3) -> None:
    placeholder = st.empty()
    fn = getattr(placeholder, level, None)
    if callable(fn):
        fn(message)
    else:
        placeholder.write(message)
    time.sleep(max(0, int(seconds)))
    placeholder.empty()


def _safe_index(options: List[str], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def _is_valid_ip_like(ip: str) -> bool:
    ip = _trim(ip)
    if not ip or "." not in ip:
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    return all(0 <= n <= 255 for n in nums)


def _normalise_iface_label(v: str) -> str:
    v = _trim(v)
    if not v:
        return ""
    aliases = {
        "STM16": "STM-16",
        "STM-16M": "STM-16",
        "STM 16": "STM-16",
        "STM4": "STM-4",
        "STM 4": "STM-4",
        "STM1": "STM-1",
        "STM 1": "STM-1",
        "ETH1000": "Eth1000",
        "ETH 1000": "Eth1000",
        "1GE": "GE",
        "GIGE": "GE",
        "STM-64M": "STM-64",
        "STM-64": "STM-64",
        "STM64M": "STM-64",
        "STM64": "STM-64",
        "GIGABITETHERNET": "GE",
    }
    key = v.replace(" ", "").replace("_", "").upper()
    return aliases.get(key, v)


def interfaces_compatible(viavi_iface: str, dev_iface: str) -> bool:
    v = _normalise_iface_label(viavi_iface)
    d = _normalise_iface_label(dev_iface)
    if not v or not d:
        return True

    if d == "STM-1/4/16" and v in {"STM-1", "STM-4", "STM-16", "STM-16M"}:
        return True
    if v == "STM-1/4/16" and d in {"STM-1", "STM-4", "STM-16", "STM-16M"}:
        return True
    if {v, d} & {"STM-1/4"} and {v, d} & {"STM-1", "STM-4"}:
        return True

    if {v, d} <= {"Eth1000", "GE"}:
        return True

    return v == d


def _build_loopback_from_state() -> Dict[str, int]:
    saved = st.session_state.get("saved_loopback") or {}
    slot = saved.get("slot")
    port = saved.get("port")

    if slot is None:
        slot = LOOPBACK_SLOTS[0] if LOOPBACK_SLOTS else 0
    if port is None:
        port = LOOPBACK_PORTS[0] if LOOPBACK_PORTS else 0

    return {"slot": int(slot), "port": int(port)}


def _parse_slotlabel(label: str) -> Tuple[str, str]:
    s = _trim(label)
    if not s:
        return "", ""
    if "-" not in s:
        return s, ""
    slot, iface = s.split("-", 1)
    return _trim(slot), _trim(iface)


def _get_quant_port_map() -> Dict[str, int]:
    try:
        data = oids()["blockOID"]

    except Exception as e:
        st.error(f"oids() error: {e}")
        return {}

    if not isinstance(data, dict):
        return {}
    qp = data.get("quantPort", {}) or {}
    out: Dict[str, int] = {}
    for k, v in qp.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue

    return out


def build_dev_slot_models(device_info: Dict) -> List[Dict[str, str]]:
    di = device_info or {}
    slots: Dict[str, str] = di.get("slots_dict") or {}
    quant = _get_quant_port_map()
    out: List[Dict[str, str]] = []
    for slot, iface in slots.items():
        slot_s = _trim(slot)
        iface_s = _trim(iface)
        if not slot_s or not iface_s:
            continue

        iface_key = iface_s.strip()
        n_ports = quant.get(iface_key, quant.get(_normalise_iface_label(iface_key), 1))
        try:
            n_ports_int = int(n_ports)
        except Exception:
            n_ports_int = 1
        if n_ports_int < 1:
            n_ports_int = 1

        out.append(
            {
                "slot": slot_s,
                "iface": iface_s,
                "label": f"{slot_s}-{iface_s}",
                "n_ports": str(n_ports_int),
            }
        )

    def _key(x: Dict[str, str]) -> Tuple[int, str]:
        try:
            s = int(x.get("slot") or 10 ** 9)
        except Exception:
            s = 10 ** 9
        return (s, x.get("label", ""))

    return sorted(out, key=_key)


def _collect_viavi_ports_for_binding() -> List[Dict[str, str]]:
    viavi_cfg = st.session_state.get("viavi_config") or {}
    out: List[Dict[str, str]] = []
    for dev_name, dev in viavi_cfg.items():
        ip = _trim(dev.get("ipaddr"))
        port_num = int(dev.get("port", 8006) or 8006)
        typeof = dev.get("typeofport") or {}
        for port_name, iface in typeof.items():
            iface_s = _trim(iface)
            if ip and iface_s:
                out.append(
                    {
                        "device": dev_name,
                        "port": port_name,
                        "iface": iface_s,
                        "ip": ip,
                        "tcp_port": port_num,
                    }
                )
    return out


def _migrate_wiring_rows_to_dev(rows: List[dict]) -> List[dict]:
    out: List[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        rr = dict(r)

        if "dut_slot" in rr and "dev_slot" not in rr:
            rr["dev_slot"] = rr.pop("dut_slot")
        if "dut_port" in rr and "dev_port" not in rr:
            rr["dev_port"] = rr.pop("dut_port")
        if "dut_interface" in rr and "dev_interface" not in rr:
            rr["dev_interface"] = rr.pop("dut_interface")

        if "dut_target" in rr:
            rr.pop("dut_target", None)

        out.append(rr)
    return out


def _validate_wiring(df: "pd.DataFrame", slot_models: List[Dict[str, str]]) -> List[str]:
    errors: List[str] = []
    if df is None or df.empty:
        return errors

    x = df.copy()

    for col in [
        "viavi_device",
        "viavi_port",
        "viavi_interface",
        "dev_interface",
        "dev_slot",
        "dev_port",
        "cable_id",
    ]:
        if col not in x.columns:
            x[col] = ""

    for col in [
        "viavi_device",
        "viavi_port",
        "viavi_interface",
        "dev_interface",
        "dev_slot",
        "dev_port",
        "cable_id",
    ]:
        x[col] = x[col].fillna("").astype(str).str.strip()
    x = x[
        ~(
                (x["viavi_device"] == "")
                & (x["viavi_port"] == "")
                & (x["dev_slot"] == "")
                & (x["dev_port"] == "")
                & (x["cable_id"] == "")
        )
    ]

    iface_by_slot: Dict[str, str] = {str(sm["slot"]): str(sm["iface"]) for sm in (slot_models or [])}
    max_ports_by_slot: Dict[str, int] = {}
    for sm in slot_models or []:
        try:
            max_ports_by_slot[str(sm["slot"])] = int(sm.get("n_ports", "1") or 1)
        except Exception:
            max_ports_by_slot[str(sm["slot"])] = 1

    used_viavi = x[(x["viavi_device"] != "") & (x["viavi_port"] != "")]
    if not used_viavi.empty:
        dup = used_viavi.groupby(["viavi_device", "viavi_port"]).size()
        dup = dup[dup > 1]
        for (d, p), cnt in dup.items():
            errors.append(f"VIAVI {d}/{p} привязан {cnt} раз(а). Один VIAVI-порт можно привязать только один раз.")

    used_dev = x[(x["dev_slot"] != "") & (x["dev_port"] != "")]
    if not used_dev.empty:
        dup = used_dev.groupby(["dev_slot", "dev_port"]).size()
        dup = dup[dup > 1]
        for (s, p), cnt in dup.items():
            errors.append(
                f"DEV слот {s} порт {p} привязан {cnt} раз(а). Один DEV-порт можно привязать только один раз.")

    for idx, row in x.iterrows():
        vdev, vport = row["viavi_device"], row["viavi_port"]
        dslot, dport = row["dev_slot"], row["dev_port"]

        if (vdev or vport) and (not dslot or not dport):
            errors.append(f"Строка {idx + 1}: выбран VIAVI-порт, но DEV не заполнен полностью (dev_slot/dev_port).")
            continue
        if (dslot or dport) and (not vdev or not vport):
            errors.append(
                f"Строка {idx + 1}: выбран DEV-порт, но VIAVI не заполнен полностью (viavi_device/viavi_port).")
            continue
        if not (vdev and vport and dslot and dport):
            continue

        try:
            pnum = int(str(dport))
        except Exception:
            errors.append(f"Строка {idx + 1}: DEV port должен быть числом.")
            continue

        maxp = max_ports_by_slot.get(str(dslot))
        if maxp is not None and not (1 <= pnum <= maxp):
            errors.append(f"Строка {idx + 1}: DEV port {pnum} вне диапазона 1..{maxp} для слота {dslot}.")
        vi = row.get("viavi_interface", "")
        di = row.get("dev_interface", "") or iface_by_slot.get(str(dslot), "")
        if vi and di and not interfaces_compatible(vi, di):
            errors.append(f"Строка {idx + 1}: несовместимые интерфейсы VIAVI '{vi}' ↔ DEV '{di}'.")

    return errors


# ------------------------------- Wiring UI -------------------------------

@st.fragment
def render_wiring_configuration() -> None:
    st.subheader("Привязка портов (VIAVI ↔ DEV)")
    if "wiring" not in st.session_state:
        cfg = st.session_state.get("config") or {}
        persisted = (cfg.get("VIAVIcontrol") or {}).get("wiring", [])
        st.session_state["wiring"] = _migrate_wiring_rows_to_dev(list(persisted) if persisted else [])
    else:
        st.session_state["wiring"] = _migrate_wiring_rows_to_dev(st.session_state.get("wiring") or [])

    # Wizard widget keys
    st.session_state.setdefault("_w_sel_viavi", "")
    st.session_state.setdefault("_w_sel_dev_slotlabel", "")
    st.session_state.setdefault("_w_sel_dev_port", "")
    st.session_state.setdefault("_w_cable_id", "")
    st.session_state.setdefault("_w_last_add_error", None)

    viavi_ports = _collect_viavi_ports_for_binding()
    dev_info = st.session_state.get("device_info") or {}
    slot_models = build_dev_slot_models(dev_info) if dev_info else []

    if not viavi_ports:
        _flash("Сначала заполните IP Viavi и типы портов (вкладки Viavi №1 / Viavi №2).", "info")
        return
    if not slot_models:
        _flash(
            "Сначала нажмите ‘Проверить подключение’, чтобы прочитать слоты устройства и сформировать список DEV слотов/портов.",
            "info")
        return

    v_choices = [f"{p['device']}/{p['port']} ({p['iface']})" for p in viavi_ports]
    v_map = {choice: p for choice, p in zip(v_choices, viavi_ports)}

    slot_labels = [sm["label"] for sm in slot_models]
    iface_by_slotlabel: Dict[str, str] = {sm["label"]: sm["iface"] for sm in slot_models}
    max_ports_by_slotlabel: Dict[str, int] = {}
    for sm in slot_models:
        try:
            max_ports_by_slotlabel[sm["label"]] = int(sm.get("n_ports", "1") or 1)
        except Exception:
            max_ports_by_slotlabel[sm["label"]] = 1
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    with c1:
        sel_viavi = st.selectbox("VIAVI порт", options=[""] + v_choices, key="_w_sel_viavi")
    with c2:
        sel_slotlabel = st.selectbox("DEV slot", options=[""] + slot_labels, key="_w_sel_dev_slotlabel")
    with c3:
        maxp = max_ports_by_slotlabel.get(sel_slotlabel, 0) if sel_slotlabel else 0
        port_opts = [""] + [str(i) for i in range(1, maxp + 1)] if maxp else [""]
        sel_port = st.selectbox("DEV port", options=port_opts, key="_w_sel_dev_port")
    with c4:
        cable_id = st.text_input("Cable ID", value="", key="_w_cable_id")

    def _on_add_wiring_row() -> None:
        sel_viavi_cb = st.session_state.get("_w_sel_viavi", "")
        sel_slotlabel_cb = st.session_state.get("_w_sel_dev_slotlabel", "")
        sel_port_cb = _trim(st.session_state.get("_w_sel_dev_port", ""))
        cable_id_cb = _trim(st.session_state.get("_w_cable_id", ""))

        if not sel_viavi_cb or not sel_slotlabel_cb or not sel_port_cb:
            return

        vp = v_map[sel_viavi_cb]
        slot_only, iface = _parse_slotlabel(sel_slotlabel_cb)
        if not iface:
            iface = _trim(iface_by_slotlabel.get(sel_slotlabel_cb, ""))

        wiring = st.session_state.get("wiring", [])
        viavi_key = (vp["device"], vp["port"])
        dev_key = (slot_only, sel_port_cb)

        if any((r.get("viavi_device"), r.get("viavi_port")) == viavi_key for r in wiring):
            st.session_state["_w_last_add_error"] = (
                f"VIAVI {viavi_key[0]}/{viavi_key[1]} уже привязан. "
                f"Выберите другой VIAVI порт или удалите существующую строку."
            )
            return
        if any((str(r.get("dev_slot")), str(r.get("dev_port"))) == dev_key for r in wiring):
            st.session_state["_w_last_add_error"] = (
                f"DEV слот {dev_key[0]} порт {dev_key[1]} уже привязан. "
                f"Выберите другой DEV port или удалите существующую строку."
            )
            return

        st.session_state.pop("_w_last_add_error", None)

        st.session_state["wiring"].append(
            {
                "viavi_device": vp["device"],
                "viavi_port": vp["port"],
                "viavi_interface": _normalise_iface_label(vp["iface"]),
                "dev_interface": _normalise_iface_label(iface),
                "dev_slot": slot_only,
                "dev_port": sel_port_cb,
                "cable_id": cable_id_cb,
            }
        )

        st.session_state["_w_sel_viavi"] = ""
        st.session_state["_w_sel_dev_slotlabel"] = ""
        st.session_state["_w_sel_dev_port"] = ""
        st.session_state["_w_cable_id"] = ""

    if st.session_state.get("_w_last_add_error"):
        _flash(st.session_state["_w_last_add_error"], "warning")
        st.session_state["_w_last_add_error"] = ""

    can_add = bool(sel_viavi) and bool(sel_slotlabel) and bool(_trim(sel_port))
    st.button("➕ Добавить строку", disabled=not can_add, width='stretch', on_click=_on_add_wiring_row)

    df = pd.DataFrame(st.session_state["wiring"])
    if df.empty:
        df = pd.DataFrame(
            [{
                "viavi_device": "",
                "viavi_port": "",
                "viavi_interface": "",
                "dev_interface": "",
                "dev_slot": "",
                "dev_port": "",
                "cable_id": "",
            }]
        )

    viavi_lookup = {(p["device"], p["port"]): p["iface"] for p in viavi_ports}
    iface_by_slot = {str(sm["slot"]): str(sm["iface"]) for sm in slot_models}
    slot_only_options = [""] + [str(sm["slot"]) for sm in slot_models]

    edited = st.data_editor(
        df,
        width='stretch',
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "viavi_device": st.column_config.TextColumn("VIAVI device", help="Напр. NumTwo"),
            "viavi_port": st.column_config.TextColumn("VIAVI port", help="Напр. Port1"),
            "viavi_interface": st.column_config.TextColumn("VIAVI iface", disabled=True),

            # Requested order in table:
            "dev_interface": st.column_config.TextColumn("DEV iface", disabled=True),
            "dev_slot": st.column_config.SelectboxColumn(
                "DEV slot",
                options=slot_only_options,
                help="Только номер слота, напр. 17",
            ),
            "dev_port": st.column_config.TextColumn("DEV port", help="Номер порта (валидируется по quantPort)."),

            "cable_id": st.column_config.TextColumn("Cable ID", help="Опционально: маркировка кабеля"),
        },
    )

    # Normalize
    for col in ["viavi_device", "viavi_port", "dev_slot", "dev_port"]:
        edited[col] = edited.get(col, "").fillna("").astype(str).str.strip()

    # Autopopulate interfaces
    edited["viavi_interface"] = [
        _trim(viavi_lookup.get((d, p), "")) for d, p in zip(edited["viavi_device"], edited["viavi_port"])
    ]
    edited["dev_interface"] = [_trim(iface_by_slot.get(sl, "")) for sl in edited["dev_slot"]]

    errors = _validate_wiring(edited, slot_models)

    a, b = st.columns([1, 1])
    with a:
        if st.button("💾 Сохранить привязки", width='stretch', disabled=bool(errors)):
            st.session_state["wiring"] = edited.to_dict(orient="records")
            cfg = st.session_state.get("config")
            if isinstance(cfg, dict):
                cfg.setdefault("VIAVIcontrol", {})
                cfg["VIAVIcontrol"]["wiring"] = st.session_state["wiring"]
            save_state()
            asyncio.run((json_input(["VIAVIcontrol", 'wiring'], new_value=st.session_state["wiring"])))
            _flash("Привязки сохранены.", "success")
    with b:
        if st.button("🧹 Очистить привязки", width='stretch'):
            st.session_state["wiring"] = []
            asyncio.run(json_input(["VIAVIcontrol", 'wiring'], new_value=[]))
            save_state()

    if errors:
        st.write("❌ Найдены ошибки в привязках:")
        for e in errors:
            st.write(f"• {e}")


# ------------------------------- Tests selection helpers -------------------------------

def _get_test_maps(catalogs, test_type: str) -> Tuple[Dict[str, str], str]:
    if test_type == "alarm":
        return catalogs.alarm_tests, "tests_ms_alarm"
    elif test_type == "stat":
        return catalogs.stat_tests, "tests_ms_stat"
    elif test_type == "comm":
        return catalogs.comm_tests, "tests_ms_comm"
    elif test_type == "other":
        return catalogs.other_tests, "tests_ms_other"
    return catalogs.sync_tests, "tests_ms_sync"


def _sync_selected_tests(test_type: str, selected_labels: List[str], test_map: Dict[str, str]) -> None:
    tests_by_type = st.session_state.setdefault("selected_tests_by_type",
                                                {"alarm": [], "sync": [], "stat": [], "comm": [], "other": []})
    labels_by_type = st.session_state.setdefault("selected_test_labels_by_type",
                                                 {"alarm": [], "sync": [], "stat": [], "comm": [], "other": []})

    selected_nodeids = [test_map[label] for label in selected_labels]
    labels_by_type[test_type] = selected_labels
    tests_by_type[test_type] = selected_nodeids

    st.session_state["selected_test_labels"] = selected_labels
    st.session_state["selected_tests"] = selected_nodeids


# ------------------------------- Main render -------------------------------

def render_configuration(client: BackendApiClient) -> None:
    st.header("Конфигурация тестирования")

    col1, col2, col3 = st.columns([1.35, 1.25, 0.85], gap="large")

    with col1:
        st.subheader("Основные настройки")
        known_devices = st.session_state.get("known_devices") or {}
        device_options = [""] + sorted(known_devices.keys())
        selected_device = st.selectbox(
            "**Сетевое устройство (вкладка/контекст)**",
            device_options,
            key="current_device_ip",
            help="Для каждого устройства сохраняется свой ui_state_<ip>.json и отдельный рабочий контекст.",
        )
        loaded_key = st.session_state.get("loaded_device_key", "")
        if selected_device and selected_device != loaded_key:
            save_state(device_key=loaded_key or None)
            apply_state(device_key=selected_device)
            st.session_state["loaded_device_key"] = selected_device
            st.rerun()
        if selected_device and st.button("Переключить активное устройство", use_container_width=True):
            try:
                res = client.select_device(selected_device)
            except BackendApiError as exc:
                _flash(f"Не удалось переключить устройство: {exc}", "error")
            else:
                if res.get("success"):
                    st.session_state["device_info"] = res.get("device", {})
                    st.session_state["ip_address_input"] = selected_device
                    st.session_state["loaded_device_key"] = selected_device
                    save_state(device_key=selected_device)
                    _flash(f"Активное устройство: {selected_device}", "success")
                else:
                    _flash(res.get("error") or "Не удалось переключить устройство.", "error")

        device = st.session_state.get("device_info") or {}
        ip_default = device.get("ipaddr") or st.session_state.get("ip_address_input", "")
        ip = st.text_input(
            "**IP адрес устройства**",
            value=ip_default,
            key="ip_address_input",
            on_change=on_change,
            placeholder="например: 10.0.0.1",
        )

        snmp = st.selectbox(
            "**Тип SNMP**",
            ["SnmpV2", "SnmpV3"],
            key="snmp_type_select",
            on_change=on_change,
        )

        pw: Optional[str]
        if snmp == "SnmpV3":
            pw = st.text_input(
                "**Пароль SNMPv3**",
                type="password",
                key="password_input",
                on_change=on_change,
                placeholder="обязателен для SNMPv3",
            )
        else:
            st.session_state.setdefault("password_input", "")
            pw = None

        if st.button("Проверить подключение", width='stretch'):
            viavi_sync_from_widgets()
            loopback = _build_loopback_from_state()
            viavi_cfg = st.session_state.get("viavi_config", {}) or {}
            with st.spinner("Подключаемся к устройству и читаем информацию..."):
                try:
                    info = client.fetch_device_info(
                        ip=_trim(ip),
                        password=_trim(pw) if pw is not None else None,
                        snmp_type=snmp,
                        viavi={k: v for k, v in viavi_cfg.items() if v},
                        loopback={k: v for k, v in loopback.items() if v},
                    )
                except BackendApiError as exc:
                    _flash(f"Не удалось получить информацию об устройстве: {exc}", "error")
                else:
                    st.session_state["device_info"] = info.model_dump()
                    st.session_state["known_devices"] = getattr(info, "devices", {}) or {}
                    st.session_state["current_device_ip"] = _trim(ip)
                    st.session_state["loaded_device_key"] = _trim(ip)
                    if getattr(info, "viavi", None):
                        st.session_state["viavi_config"] = info.viavi
                    if getattr(info, "loopback", None):
                        st.session_state["saved_loopback"] = info.loopback
                    save_state(device_key=_trim(ip))
                    _flash("Устройство успешно проверено.", "success")
        can_unmask = _is_valid_ip_like(ip)
        if st.button("Включить анализ портов", disabled=not can_unmask, width='stretch'):
            with st.spinner("Включаем анализ портов (SNMPv3)..."):
                try:
                    client.run_port_unmask(ip=_trim(ip), password=_trim(pw) if pw else "", snmp_type=snmp)
                except BackendApiError as exc:
                    _flash(f"Не удалось включить анализ портов: {exc}", "error")
                else:
                    _flash("Анализ портов включён.", "success")
        nodeids = normalise_nodeids(st.session_state.get("selected_tests") or [])
        dev = st.session_state.get("device_info")
        if st.button("🚀 Запустить тесты", width='stretch'):
            if dev is None:
                _flash("Сначала проверьте устройство (кнопка ‘Проверить подключение’).", "error")
                st.stop()

            payload = {
                "test_type": st.session_state.get("test_type_radio", "alarm"),
                "selected_tests": nodeids,
                "settings": {
                    "target_device_ip": _trim(ip),
                },
            }

            with st.spinner("Запускаем тесты..."):
                try:
                    resp = client.run_tests(payload)
                except BackendApiError as exc:
                    _flash(f"Не удалось запустить тесты: {exc}", "error")
                else:
                    if getattr(resp, "success", False) and getattr(resp, "job_id", None):
                        st.session_state["current_job_id"] = resp.job_id
                        _flash(f"Тесты запущены. job_id = {resp.job_id}", "success")
                        save_state()
                    else:
                        _flash(getattr(resp, "error", None) or "Не удалось запустить тесты.", "error")
        st.markdown("---")
        st.subheader("Конфигурация тестов")

        with st.spinner("Загружаем каталог тестов..."):
            try:
                catalogs = client.get_test_catalogs()
            except BackendApiError as exc:
                _flash(f"Не удалось загрузить каталог тестов: {exc}", "error")
                catalogs = None

        if catalogs is None:
            st.stop()

        test_type = st.radio(
            "**Тип тестов**",
            ["alarm", "sync", "stat", "comm", "other"],
            format_func=lambda x: {
                "alarm": "Alarm Tests",
                "sync": "Sync Tests",
                "stat": "Statistic Tests",
                "comm": "Commutation Tests",
                "other": "Other Tests"
            }.get(x, x),
            horizontal=True,
            key="test_type_radio",
            on_change=on_change,
        )

        test_map, multiselect_key = _get_test_maps(catalogs, test_type)

        labels_by_type = st.session_state.setdefault("selected_test_labels_by_type",
                                                     {"alarm": [], "sync": [], "stat": [], "comm": [], "other": []})
        session_labels = labels_by_type.get(test_type, [])

        available_labels = list(test_map.keys())
        default_labels = [label for label in session_labels if label in available_labels]

        selected_labels = st.multiselect(
            "Выберите тесты:",
            options=available_labels,
            default=default_labels,
            on_change=on_change,
            key=multiselect_key,
        )

        _sync_selected_tests(test_type=test_type, selected_labels=selected_labels, test_map=test_map)
        save_state()

        if selected_labels:
            st.caption(f"Выбрано тестов: {len(selected_labels)}")

    if "viavi_count" not in st.session_state:
        saved_config = st.session_state.get("viavi_config", {})
        st.session_state.viavi_count = len(saved_config) if saved_config else 1

    with col2:
        st.subheader("Управление VIAVI и Loopback")

        # Инициализация счетчика, если он отсутствует
        if "viavi_count" not in st.session_state:
            st.session_state.viavi_count = 1

        # Динамическое создание вкладок
        viavi_tabs_names = [f"**Viavi №{i + 1}**" for i in range(st.session_state.viavi_count)]
        all_tabs = st.tabs(viavi_tabs_names + ["**Loopback**"])

        # Отрисовка вкладок VIAVI
        for i in range(st.session_state.viavi_count):
            num = i + 1
            with all_tabs[i]:
                st.text_input(
                    f"**IP Viavi №{num}**",
                    value=st.session_state.get(f"viavi{num}_ip", ""),
                    key=f"viavi{num}_ip",
                    on_change=viavi_sync_from_widgets,
                )
                p1, p2 = st.columns(2)
                with p1:
                    st.selectbox(
                        "Port 1",
                        PORT_OPTIONS,
                        index=_safe_index(PORT_OPTIONS, st.session_state.get(f"viavi{num}_port1", "")),
                        key=f"viavi{num}_port1",
                        on_change=viavi_sync_from_widgets,
                    )
                with p2:
                    st.selectbox(
                        "Port 2",
                        PORT_OPTIONS,
                        index=_safe_index(PORT_OPTIONS, st.session_state.get(f"viavi{num}_port2", "")),
                        key=f"viavi{num}_port2",
                        on_change=viavi_sync_from_widgets,
                    )

        with all_tabs[-1]:
            lb1, lb2 = st.columns(2)
            with lb1:
                st.selectbox("**Слот с loopback**", LOOPBACK_SLOTS, key="slot_loopback", on_change=on_change)
            with lb2:
                st.selectbox("**Порт с loopback**", LOOPBACK_PORTS, key="port_loopback", on_change=on_change)

        add_col, del_col = st.columns(2)
        with add_col:
            if st.button("➕ Добавить",disabled=st.session_state.viavi_count == 5, use_container_width=True):
                st.session_state.viavi_count += 1
                save_state()
                st.rerun()
        with del_col:
            if st.button("➖ Удалить", disabled=st.session_state.viavi_count <= 1, use_container_width=True):
                num = st.session_state.viavi_count
                st.session_state.pop(f"viavi{num}_ip", None)
                st.session_state.pop(f"viavi{num}_port1", None)
                st.session_state.pop(f"viavi{num}_port2", None)

                st.session_state.viavi_count -= 1
                save_state()
                st.rerun()

        save_state()
        st.markdown("---")
        render_wiring_configuration()
        st.markdown("---")

    with col3:
        st.subheader("Статус устройства")
        dev = st.session_state.get("device_info")

        def centered_box(text):
            st.markdown(
                f"""
                <div style="
                    background-color: #e6f4ea; 
                    color: #1e7e34; 
                    padding: 10px; 
                    border-radius: 8px; 
                    text-align: center; 
                    font-weight: bold; 
                    margin-bottom: 10px;
                    font-size: 1.1rem;
                ">
                    {text}
                </div>
                """,
                unsafe_allow_html=True
            )

        centered_box(dev.get('name') or '—')
        centered_box(dev.get('ipaddr') or '—')
        slots = dev.get("slots_dict") or {}
        if slots:
            st.write("---")
            st.markdown("##### Выберите блоки для тестов:")
            selected_slots = {}
            s_col1, s_col2 = st.columns(2)

            for i, (slot_id, slot_name) in enumerate(slots.items()):
                target_col = s_col1 if i % 2 == 0 else s_col2
                with target_col:
                    is_selected = st.checkbox(
                        label=f"{slot_id} ({slot_name})",
                        value=True,
                        key=f"chk_{slot_id}",
                        on_change=on_slot_change
                    )
                    if is_selected:
                        selected_slots[slot_id] = slot_name
            st.session_state["active_slots"] = selected_slots
        st.write("---")
        st.markdown("##### Прошивка образа и блоков")
        b1, b2 = st.columns(2)
        start_update = False
        with b1:
            img_options = [None, "archive", "current"]
            current_val = st.session_state.get("image_upgrade", None)

            try:
                start_index = img_options.index(current_val)
            except ValueError:
                start_index = 0

            st.selectbox(
                "Image",
                options=img_options,
                index=start_index,
                key="image_upgrade"
            )

            if st.button("UPD IMG", key="img_upd_start"):
                payload = {"image": st.session_state.get("image_upgrade")}
                client.upgrade_firmware_img(payload)
                st.session_state.show_upgrade_log = True
                st.rerun()
        with b2:
            st.selectbox("Block", [None, "all", "slots"],
                         index=_safe_index([None, "all", "slots"], st.session_state.get("block_upgrade", "")),
                         key="block_upgrade")
            st.multiselect("Выберите блоки",
                           options=[f"{k}: {v}" for k, v in
                                    st.session_state.get("device_info", {}).get("slots_dict", {}).items()],
                           default=None, key="block_choose")
            if st.button("UPD BLOCK", key="block_upd_start"):
                payload = {
                    "block_type": st.session_state.get("block_upgrade"),
                    "slots": st.session_state.get("block_choose")
                }
                client.upgrade_firmware_block(payload)
                st.session_state.show_upgrade_log = True
                st.rerun()
        if st.session_state.get("show_upgrade_log"):
            st.divider()

            status_data = client.get_upgrade_status()
            current_log = status_data.get("log", "Ожидание данных...")
            is_running = status_data.get("is_running", False)

            st.write("###  Консоль процесса:")

            with st.container(height=500, border=True):
                st.code(current_log, language="bash")

            if is_running:

                time.sleep(2)
                st.rerun()
            else:
                st.success("✅ Процесс прошивки завершен!")
                if st.button("Очистить и закрыть консоль", key="close_log_btn"):
                    st.session_state.show_upgrade_log = False
                    st.rerun()

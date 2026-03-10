from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import pandas as pd

from frontend.api import BackendApiClient, BackendApiError

MAX_PAGE_ROWS = 30
ROW_HEIGHT = 34
LOCAL_TZ = ZoneInfo("Europe/Moscow")


def _format_ts(ts: Any) -> tuple[str, str]:
    if ts is None or ts == "":
        return "-", "-"

    dt: datetime | None = None

    try:
        ts_s = str(ts).strip()
        if ts_s.isdigit() and len(ts_s) >= 13:
            # миллисекунды
            ts_f = float(ts_s) / 1000.0
        else:
            ts_f = float(ts_s)
        dt = datetime.fromtimestamp(ts_f, tz=timezone.utc).astimezone(LOCAL_TZ)
    except Exception:
        dt = None

    if dt is None and isinstance(ts, str):
        try:
            dt0 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt0.tzinfo is None:
                dt0 = dt0.replace(tzinfo=timezone.utc)
            dt = dt0.astimezone(LOCAL_TZ)
        except Exception:
            return str(ts), "-"

    if dt is None:
        return str(ts), "-"

    now = datetime.now(tz=LOCAL_TZ)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 0:
        ago = ("сейчас")
    elif seconds < 60:
        ago = f"{seconds}s назад"
    elif seconds < 3600:
        ago = f"{seconds // 60}m назад"
    elif seconds < 86400:
        ago = f"{seconds // 3600}h назад"
    else:
        ago = f"{seconds // 86400}d назад"

    return dt.strftime("%Y-%m-%d %H:%M:%S"), ago


def _truncate(val: Any, max_len: int = 80) -> str:
    s = str(val) if val is not None else ""
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _guess_kv_line(line: str) -> tuple[str | None, str | None]:
    if not isinstance(line, str):
        return None, None
    if "=" in line:
        k, v = line.split("=", 1)
        return k.strip() or None, v.strip()
    if ":" in line:
        k, v = line.split(":", 1)
        return k.strip() or None, v.strip()
    return None, None


def _extract_preview(var_binds: List[Dict[str, Any]] | None, limit: int = 3, compact: bool = True) -> str:
    if not var_binds:
        return ""

    parts: List[str] = []
    for vb in var_binds[:limit]:
        oid = vb.get("oid", "")
        val = vb.get("value", "")
        val_s = _truncate(val, 40) if compact else str(val)
        parts.append(f"{oid}={val_s}")
    return "; ".join(parts)


def _build_varbind_rows(
        processed_lines: List[str],
        var_binds: List[Dict[str, Any]],
        compact: bool,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    n = max(len(processed_lines), len(var_binds))
    for i in range(n):
        pl = processed_lines[i] if i < len(processed_lines) else ""
        oid = str(var_binds[i].get("oid", "")) if i < len(var_binds) else ""
        val_raw = var_binds[i].get("value", "") if i < len(var_binds) else ""
        val = _truncate(val_raw) if compact else str(val_raw)
        rows.append({"processed_line": pl, "oid": oid, "value": val})
    return rows


def _events_to_rows(events: List[Dict[str, Any]], compact: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for i, e in enumerate(events):
        # В разных версиях бэка поле времени может называться по-разному.
        ts_val = (
                e.get("ts")
                or e.get("timestamp")
                or e.get("received_ts")
                or e.get("received_at")
                or e.get("time")
                or e.get("date")
        )
        time_str, ago = _format_ts(ts_val)
        var_binds = e.get("var_binds") or []
        rows.append(
            {
                "idx": i,
                "time": time_str,
                "ago": ago,
                "trap_oid": e.get("snmp_trap_oid"),
                "binds": len(var_binds),
                "preview": _extract_preview(var_binds, limit=3, compact=compact),
            }
        )
    return rows


def render_traps(client: BackendApiClient) -> None:
    st.subheader("TRAP listener")
    st.markdown("---")

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
    with b1:
        if st.button("Start", width='stretch'):
            client.traps_start()
    with b2:
        if st.button("Stop", width='stretch'):
            client.traps_stop()
    with b3:
        try:
            status = client.traps_status()
            running = bool(status.get("running"))
            pid = status.get("pid")
            st.markdown(f"Статус: {'🟢 RUNNING' if running else '🔴 STOPPED'}  \n**PID:** {pid}")
        except BackendApiError as exc:
            st.error(f"Не удалось получить статус: {exc}")
            running = False
    with b4:
        limit = st.number_input("Лимит событий", min_value=10, max_value=5000, value=200, step=10)

    st.markdown("---")

    def _render() -> None:
        try:
            events = client.traps_events(limit=int(limit), order="desc")
        except BackendApiError as exc:
            st.error(f"Не удалось загрузить события: {exc}")
            return

        events = [
            e
            for e in events
            if isinstance(e, dict)
               and isinstance(e.get("processed_lines"), list)
               and len(e.get("processed_lines")) > 0
        ]

        if not events:
            st.info("Пока нет TRAP-сообщений.")
            return

        flt = st.text_input("Фильтр по OID / preview", value="", key="traps_flt")

        rows = _events_to_rows(events, compact=True)
        df = pd.DataFrame(rows)

        if flt:
            mask = (
                    df["trap_oid"].astype(str).str.contains(flt, case=False, na=False)
                    | df["preview"].astype(str).str.contains(flt, case=False, na=False)
            )
            df = df[mask]

        col1, col2 = st.columns([2, 3])

        with col1:
            st.markdown("### Пакеты с TRAP")

            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(sortable=True, resizable=True)
            gb.configure_column("idx", header_name="№", width=50, pinned="left")
            gb.configure_column("time", header_name="Время", width=200)
            # 'Давно' = сколько времени прошло с момента события (ago)
            gb.configure_column("ago", header_name="Давно", width=110)
            gb.configure_column("trap_oid", header_name="OID", width=300)
            gb.configure_column("binds", header_name="VarBinds", width=90)
            gb.configure_column("preview", header_name="Preview", width=420)
            gb.configure_selection("single", use_checkbox=False)
            grid_options = gb.build()

            grid = AgGrid(
                df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                allow_unsafe_jscode=False,
                domLayout="normal",
                height=580,
                key="traps_events_grid",
            )

            selected_rows = grid.get("selected_rows")
            if isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict("records")
            elif not isinstance(selected_rows, list):
                selected_rows = []

            if selected_rows:
                st.session_state.trap_selected_idx = int(selected_rows[0].get("idx", 0))

        with col2:
            if df.empty:
                st.warning("По фильтру ничего не найдено")
                return

            sel_idx = int(st.session_state.get("trap_selected_idx", 0))
            if sel_idx >= len(events):
                sel_idx = len(events) - 1

            selected_event = events[sel_idx]
            st.markdown("### Детали TRAP")

            # Tabs
            tab_vb, tab_raw = st.tabs(["VarBinds", "Raw JSON"])

            with tab_vb:
                details = _build_varbind_rows(
                    selected_event.get("processed_lines") or [],
                    selected_event.get("var_binds") or [],
                    compact=True,
                )
                st.dataframe(details, width='stretch', hide_index=True)
            with tab_raw:
                raw_json = json.dumps(selected_event, ensure_ascii=False, indent=2)
                st.code(raw_json, language="json")
                st.download_button(
                    "⬇ Скачать JSON",
                    raw_json,
                    file_name=f"trap_{sel_idx}.json",
                    mime="application/json",
                )

    try:
        running = bool(client.traps_status().get("running"))
    except Exception:
        running = False

    if hasattr(st, "fragment"):
        if running:
            @st.fragment(run_every="2s")
            def _frag():
                _render()
        else:
            @st.fragment
            def _frag():
                _render()

        _frag()
    else:
        _render()

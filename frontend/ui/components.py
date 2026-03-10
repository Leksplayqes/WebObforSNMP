"""Reusable UI pieces shared across multiple pages."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional

from backend.logs import add_log  # noqa: F401  (может использоваться в других местах)
import pandas as pd
import streamlit as st

from pydantic import BaseModel


def _format_ts(ts: Optional[float]) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _to_dict(record: Any) -> Dict[str, Any]:
    if isinstance(record, BaseModel):
        return record.model_dump()
    if hasattr(record, "to_dict") and callable(getattr(record, "to_dict")):
        try:
            return record.to_dict()
        except Exception:
            return dict(record)
    return dict(record)




def _effective_run_status(raw: dict) -> str:
    try:
        rid = raw.get("id") or raw.get("id_") or raw.get("job_id") or raw.get("jobId")
        overrides = st.session_state.get("runs_status_override", {})  # type: ignore[attr-defined]
        if rid and isinstance(overrides, dict) and str(rid) in overrides:
            return str(overrides[str(rid)] or "")
    except Exception:
        pass

    payload = (raw.get("payload") or {})
    summary = (payload.get("summary") or {})
    status = summary.get("status") or raw.get("status") or ""
    return str(status)
def _describe_record(record: Dict[str, Any]) -> str:
    payload = record.get("payload") or {}
    summary = payload.get("summary") or {}
    total = summary.get("total")
    passed = summary.get("passed")
    failed = summary.get("failed")
    skipped = summary.get("skipped")
    status = summary.get("status")
    if status in ("queued", "running", "in_progress", "started"):
        return f"Статус: {status}"
    if total is None:
        return ""
    return f"Пройдено: {passed}, Провалено: {failed}, Пропущено: {skipped} из {total}"


_TYPE_STYLES: dict[str, dict[str, str]] = {
    "smoke": {"bg": "#E6F4EA", "fg": "#137333"},
    "regress": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "load": {"bg": "#FEF7E0", "fg": "#B26A00"},
    "e2e": {"bg": "#FCE8E6", "fg": "#C5221F"},
}

_STATUS_STYLES: dict[str, dict[str, str]] = {
    "running": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "queued": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "in_progress": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "started": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "completed": {"bg": "#E6F4EA", "fg": "#137333"},
    "success": {"bg": "#E6F4EA", "fg": "#137333"},
    "passed":{"bg": "#E6F4EA", "fg": "#137333"},
    "stopped":{"bg": "#FCE8E6", "fg": "#C5221F"},
    "failed": {"bg": "#FCE8E6", "fg": "#C5221F"},
    "fail": {"bg": "#FCE8E6", "fg": "#C5221F"},
}

_CASE_STATUS_STYLES: dict[str, dict[str, str]] = {
    "pass": {"bg": "#E6F4EA", "fg": "#137333"},
    "passed": {"bg": "#E6F4EA", "fg": "#137333"},
    "fail": {"bg": "#FCE8E6", "fg": "#C5221F"},
    "failed": {"bg": "#FCE8E6", "fg": "#C5221F"},
    "error": {"bg": "#FCE8E6", "fg": "#C5221F"},
    "skip": {"bg": "#FEF7E0", "fg": "#B26A00"},
    "skipped": {"bg": "#FEF7E0", "fg": "#B26A00"},
    "running": {"bg": "#E8F0FE", "fg": "#1A73E8"},
    "in_progress": {"bg": "#E8F0FE", "fg": "#1A73E8"},
}


def _style_runs_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:

    def _norm(v: Any) -> str:
        return str(v).strip().lower() if v is not None else ""

    def style_type_cell(v: Any) -> str:
        key = _norm(v)
        stl = _TYPE_STYLES.get(key)
        if not stl:
            return ""
        return f"background-color: {stl['bg']}; color: {stl['fg']}; font-weight: 600;"

    def style_status_cell(v: Any) -> str:
        key = _norm(v)
        stl = _STATUS_STYLES.get(key)
        if not stl:
            return ""
        return f"background-color: {stl['bg']}; color: {stl['fg']}; font-weight: 600;"

    styler = df.style
    if "Тип" in df.columns:
        styler = styler.map(style_type_cell, subset=["Тип"])
    if "Статус" in df.columns:
        styler = styler.map(style_status_cell, subset=["Статус"])

    styler = styler.set_properties(**{"white-space": "nowrap"})
    return styler


def _cases_to_df(cases: Any) -> pd.DataFrame:
    if cases is None:
        return pd.DataFrame()

    if isinstance(cases, pd.DataFrame):
        df = cases.copy()
    elif isinstance(cases, dict):
        df = pd.DataFrame([cases])
    elif isinstance(cases, (list, tuple)):
        normalized = []
        for item in cases:
            if isinstance(item, BaseModel):
                normalized.append(item.model_dump())
            elif isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "model_dump"):
                try:
                    normalized.append(item.model_dump())
                except Exception:
                    normalized.append(getattr(item, "__dict__", {"value": str(item)}))
            else:
                normalized.append(getattr(item, "__dict__", {"value": str(item)}))
        df = pd.DataFrame(normalized)
    else:
        df = pd.DataFrame([{"value": str(cases)}])

    rename_map = {}
    if "status" in df.columns and "Статус" not in df.columns:
        rename_map["status"] = "Статус"
    if "name" in df.columns and "Название" not in df.columns:
        rename_map["name"] = "Название"
    if "case" in df.columns and "Название" not in df.columns:
        rename_map["case"] = "Название"
    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def style_cases_table(cases: Any) -> pd.io.formats.style.Styler:

    df = _cases_to_df(cases)

    def _norm(v: Any) -> str:
        return str(v).strip().lower() if v is not None else ""

    def style_status_cell(v: Any) -> str:
        key = _norm(v)
        stl = _CASE_STATUS_STYLES.get(key)
        if not stl:
            return ""
        return f"background-color: {stl['bg']}; color: {stl['fg']}; font-weight: 600;"

    styler = df.style
    if "Статус" in df.columns:
        styler = styler.map(style_status_cell, subset=["Статус"])

    styler = styler.set_properties(**{"white-space": "nowrap"})
    return styler


def _extract_selected_rows(event: Any) -> list[int]:
    if event is None:
        return []
    try:
        sel = getattr(event, "selection", None)
        rows = getattr(sel, "rows", None)
        if rows is not None:
            return list(rows)
    except Exception:
        pass
    try:
        if isinstance(event, dict):
            sel = event.get("selection") or {}
            rows = sel.get("rows") or []
            return list(rows)
    except Exception:
        pass
    return []


def _render_runs_list_once(
        records: Iterable[Any],
        *,
        key_prefix: str,
        title: Optional[str] = None,
        empty_message: str = "Нет запусков",
) -> Optional[Any]:
    prepared: list[tuple[Dict[str, Any], Any]] = []
    for rec in records:
        data = _to_dict(rec)
        if not data.get("id"):
            continue
        prepared.append((data, rec))

    prepared.sort(key=lambda x: x[0].get("started_at") or 0, reverse=True)

    if title:
        st.subheader(title)
    if not prepared:
        st.info(empty_message)
        return None

    rows: list[dict[str, Any]] = []
    ids_in_order: list[str] = []

    for raw, _ in prepared:
        payload = raw.get("payload") or {}
        summary = payload.get("summary") or {}
        duration = summary.get("duration") or 0

        run_id = str(raw.get("id"))
        ids_in_order.append(run_id)

        rows.append(
            {
                "Название": payload.get("title") if payload.get("title") else run_id,
                "Тип": raw.get("type"),
                # Требование: статус в таблице запусков всегда ЗАГЛАВНЫМИ
                "Статус": str(_effective_run_status(raw)).upper(),
                "Начало": _format_ts(raw.get("started_at") or payload.get("started")),
                "Конец": _format_ts(raw.get("finished_at") or payload.get("finished")),
                "Длительность, c": duration,
                "Описание": _describe_record(raw),
            }
        )

    df = pd.DataFrame(rows).reset_index(drop=True)

    selected_key = f"{key_prefix}_selected"

    # Рисуем таблицу с кликом по строке (если Streamlit поддерживает selection).
    try:
        event = st.dataframe(
            _style_runs_table(df),
            width="stretch",
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key=f"{key_prefix}_runs_table",
        )
        sel_rows = _extract_selected_rows(event)
        if sel_rows:
            idx = int(sel_rows[0])
            if 0 <= idx < len(ids_in_order):
                st.session_state[selected_key] = ids_in_order[idx]
    except TypeError:
        st.dataframe(_style_runs_table(df), width="stretch", hide_index=True)

    if selected_key not in st.session_state and ids_in_order:
        st.session_state[selected_key] = ids_in_order[0]

    selected_id = st.session_state.get(selected_key)

    for raw, original in prepared:
        if str(raw.get("id")) == str(selected_id):
            return original

    return None


def render_runs_list(
        records: Optional[Iterable[Any]] = None,
        *,
        key_prefix: str,
        title: Optional[str] = None,
        empty_message: str = "Нет запусков",
        fetch_records: Optional[Callable[[], Iterable[Any]]] = None,
        refresh_every: str = "10s",
        refresh_enabled_key: Optional[str] = None,
) -> Optional[Any]:
    """Render runs table and return the selected entry (selection via row click)."""

    if fetch_records is None:
        if records is None:
            records = []
        return _render_runs_list_once(records, key_prefix=key_prefix, title=title, empty_message=empty_message)

    selected_holder: dict[str, Optional[Any]] = {"selected": None}

    if refresh_enabled_key and not st.session_state.get(refresh_enabled_key, False):
        base = list(records) if records is not None else []
        selected_holder["selected"] = _render_runs_list_once(
            base,
            key_prefix=key_prefix,
            title=title,
            empty_message=empty_message,
        )
        return selected_holder["selected"]

    if hasattr(st, "fragment"):
        @st.fragment(run_every=refresh_every)
        def _runs_fragment():
            try:
                fresh_records = fetch_records()
            except Exception as exc:
                st.error(f"Не удалось обновить список запусков: {exc}")
                selected_holder["selected"] = None
                return
            selected_holder["selected"] = _render_runs_list_once(
                fresh_records,
                key_prefix=key_prefix,
                title=title,
                empty_message=empty_message,
            )

        _runs_fragment()
        return selected_holder["selected"]

    try:
        fresh_records = fetch_records()
    except Exception as exc:
        st.error(f"Не удалось загрузить список запусков: {exc}")
        return None
    return _render_runs_list_once(fresh_records, key_prefix=key_prefix, title=title, empty_message=empty_message)




def render_runs_table_readonly(
        records: Optional[Iterable[Any]] = None,
        *,
        key_prefix: str,
        title: Optional[str] = None,
        empty_message: str = "Нет запусков",
        fetch_records: Optional[Callable[[], Iterable[Any]]] = None,
        refresh_every: str = "5s",
) -> None:
    """Render a runs table WITHOUT selection (no click / double-click).

    Use this when the page uses a separate control (e.g., selectbox) to pick a run.
    If fetch_records is provided and Streamlit supports fragments, the table will
    be refreshed periodically.
    """

    def _render(recs: Iterable[Any]) -> None:
        prepared: list[dict[str, Any]] = []
        for rec in recs:
            raw = _to_dict(rec)
            if not raw.get("id"):
                continue
            prepared.append(raw)

        prepared.sort(key=lambda x: x.get("started_at") or 0, reverse=True)

        if title:
            st.subheader(title)
        if not prepared:
            st.info(empty_message)
            return

        rows: list[dict[str, Any]] = []
        for raw in prepared:
            payload = raw.get("payload") or {}
            summary = payload.get("summary") or {}
            duration = summary.get("duration") or 0

            run_id = str(raw.get("id"))
            rows.append(
                {
                    "Название": payload.get("title") if payload.get("title") else run_id,
                    "Тип": raw.get("type"),
                    "Статус": str(_effective_run_status(raw)).upper(),
                    "Начало": _format_ts(raw.get("started_at") or payload.get("started")),
                    "Конец": _format_ts(raw.get("finished_at") or payload.get("finished")),
                    "Длительность, c": duration,
                    "Описание": _describe_record(raw),
                }
            )

        import pandas as pd
        df = pd.DataFrame(rows).reset_index(drop=True)
        st.dataframe(_style_runs_table(df), width="stretch", hide_index=True, key=f"{key_prefix}_runs_table_ro")

    # No polling
    if fetch_records is None:
        _render(records or [])
        return

    # Polling
    if hasattr(st, "fragment"):
        @st.fragment(run_every=refresh_every)
        def _runs_ro_fragment():
            try:
                fresh = fetch_records()
            except Exception as exc:
                st.error(f"Не удалось обновить список запусков: {exc}")
                return
            _render(fresh)

        _runs_ro_fragment()
        return

    # Fallback w/o fragments
    try:
        fresh = fetch_records()
    except Exception as exc:
        st.error(f"Не удалось загрузить список запусков: {exc}")
        _render(records or [])
        return
    _render(fresh)


# Alias for older code/new results page
render_runs_table = render_runs_table_readonly


# Backwards compatible export list

all = ["render_runs_list", "render_runs_table_readonly", "render_runs_table", "style_cases_table"]

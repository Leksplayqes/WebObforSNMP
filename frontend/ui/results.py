"""Widgets showing test run progress and results."""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from frontend.api import BackendApiClient, BackendApiError
from frontend.ui.components import render_runs_table, style_cases_table

ACTIVE_STATUSES = {"running", "in_progress", "started", "pending", "queued"}


def _as_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)  # type: ignore[arg-type]
    except Exception:
        return getattr(obj, "__dict__", {}) or {}


def _get_id(rec: Any) -> str:
    raw = _as_dict(rec)
    return str(raw.get("id") or raw.get("id_") or getattr(rec, "id", "") or getattr(rec, "id_", ""))


def _pick_ts(rec: Any) -> int:
    raw = _as_dict(rec)
    payload = raw.get("payload") or {}
    ts = raw.get("started_at") or payload.get("started") or raw.get("created_at")
    try:
        v = pd.to_datetime(ts, utc=True, errors="coerce")
        return int(v.value) if pd.notna(v) else 0
    except Exception:
        return 0


def _run_label(rec: Any) -> str:
    if rec is None:
        return ""
    raw = _as_dict(rec)
    payload = raw.get("payload") or {}
    summary = (payload.get("summary") or {}) if isinstance(payload, dict) else {}
    status = (summary.get("status") or raw.get("status") or "").upper()
    started = raw.get("started_at") or payload.get("started") or raw.get("created_at") or ""
    name = raw.get("name") or raw.get("title") or raw.get("test_name") or ""
    jid = _get_id(rec)
    left = name if name else jid
    return f"{left} | {started} | {status}"


def _is_active_status(status: str) -> bool:
    return (status or "").strip().lower() in ACTIVE_STATUSES


def render_results(client: BackendApiClient) -> None:
    """Main Results page.

    This version:
      - stop button is next to the test selectbox (in history block)
      - history table auto-refreshes every 5 seconds
      - details refresh every 5 seconds only while run is active
    """

    # Session keys
    sel_key = "results_selected_job_id"
    cache_jobs_key = "results_cached_jobs"
    cache_detail_key = "results_cached_detail"
    live_enabled_key = "results_live_refresh_enabled"

    # Status overrides: allow the upper table to reflect the freshest status we learn
    # from get_test_status() even if list_test_jobs() lags (optional; harmless).
    if "runs_status_override" not in st.session_state:
        st.session_state["runs_status_override"] = {}

    if cache_jobs_key not in st.session_state:
        st.session_state[cache_jobs_key] = []
    if cache_detail_key not in st.session_state:
        st.session_state[cache_detail_key] = None
    if live_enabled_key not in st.session_state:
        st.session_state[live_enabled_key] = False

    def _apply_status_overrides(jobs: List[Any]) -> List[Any]:
        overrides: Dict[str, str] = st.session_state.get("runs_status_override", {}) or {}
        if not overrides:
            return jobs
        for rec in jobs:
            jid = _get_id(rec)
            if not jid:
                continue
            ov = overrides.get(str(jid))
            if not ov:
                continue
            try:
                if isinstance(rec, dict):
                    rec["status"] = ov
                else:
                    setattr(rec, "status", ov)
            except Exception:
                pass
        return jobs

    st.subheader("История тестов")

    # --- History block (poll list_test_jobs) ---
    @st.fragment(run_every="5s")
    def _history_fragment() -> None:
        # Always try to refresh history; on error fall back to cached jobs.
        try:
            jobs, _limits = client.list_test_jobs()
        except BackendApiError as exc:
            st.error(f"Не удалось загрузить историю тестов: {exc}")
            jobs = st.session_state.get(cache_jobs_key, []) or []

        jobs_sorted = sorted(jobs, key=_pick_ts, reverse=True)
        jobs_cached = _apply_status_overrides(jobs_sorted)
        st.session_state[cache_jobs_key] = jobs_cached

        id_to_rec: Dict[str, Any] = {_get_id(r): r for r in jobs_cached if _get_id(r)}
        ids = list(id_to_rec.keys())

        if not ids:
            st.info("Пока нет ни одного теста.")
            render_runs_table(jobs_cached, key_prefix="tests", title=None, empty_message="Пока нет ни одного теста.")
            return

        # selection default: keep previous if still exists, otherwise pick the newest
        if sel_key not in st.session_state or str(st.session_state.get(sel_key) or "") not in ids:
            st.session_state[sel_key] = ids[0]

        c1, c2 = st.columns([8, 2])

        with c1:
            st.selectbox(
                "Выбранный тест",
                options=ids,
                format_func=lambda jid: _run_label(id_to_rec.get(str(jid))),
                key=sel_key,
            )

        selected_id = str(st.session_state.get(sel_key) or "")
        selected_rec = id_to_rec.get(selected_id)
        selected_status = (getattr(selected_rec, "status", "") or "")
        stop_disabled = not _is_active_status(selected_status)

        with c2:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button(
                    "🛑 Остановить",
                    key=f"stop_test_button__{selected_id}",
                    width="stretch",
                    disabled=stop_disabled,
            ):
                with st.spinner("Останавливаем тест..."):
                    try:
                        resp = client.stop_test(selected_id)
                    except BackendApiError as exc:
                        st.error(f"Ошибка остановки теста: {exc}")
                    else:
                        if getattr(resp, "success", False):
                            st.success("Тест остановлен.")
                            # Force live refresh of details right after stop.
                            st.session_state[live_enabled_key] = True
                            st.rerun()
                        else:
                            st.warning(getattr(resp, "error", None) or "Не удалось остановить тест")

        render_runs_table(jobs_cached, key_prefix="tests", title=None, empty_message="Пока нет ни одного теста.")

    _history_fragment()

    st.divider()

    # --- Live details block (refresh every 5s only while active) ---
    @st.fragment(run_every="2s")
    def _details_fragment() -> None:
        jid = str(st.session_state.get(sel_key) or "")
        if not jid:
            st.info("Выбери тест в списке выше.")
            return

        # If selection changed, force one backend fetch for details
        prev_sel_key = sel_key + "__prev"
        prev = str(st.session_state.get(prev_sel_key) or "")
        if jid != prev:
            st.session_state[prev_sel_key] = jid
            st.session_state[cache_detail_key] = None
            st.session_state[live_enabled_key] = True

        live_enabled = bool(st.session_state.get(live_enabled_key, False))

        # If live refresh disabled, show cached detail (no backend calls)
        if not live_enabled:
            cached = st.session_state.get(cache_detail_key)
            if cached is None:
                # For old runs we still want to show details; fetch once.
                live_enabled = True
                st.session_state[live_enabled_key] = True
            else:
                _render_detail_from_cache(cached)
                return

        # Live refresh enabled -> call backend
        try:
            record = client.get_test_status(jid)
        except BackendApiError as exc:
            st.error(f"Не удалось получить состояние теста: {exc}")
            return

        # Update override map so history can reflect the freshest status.
        try:
            st.session_state["runs_status_override"][str(jid)] = getattr(record, "status", "") or ""
        except Exception:
            pass

        cached = {
            "record": record,
            "status": getattr(record, "status", "") or "",
            "payload": getattr(record, "payload", None),
        }
        st.session_state[cache_detail_key] = cached

        _render_record_detail(record)

        # Disable live refresh when run is not active anymore
        status = (getattr(record, "status", "") or "").lower()
        st.session_state[live_enabled_key] = _is_active_status(status)

    def _render_detail_from_cache(cached: dict) -> None:
        record = cached.get("record")
        if record is None:
            return
        _render_record_detail(record)

    def _render_record_detail(record: Any) -> None:
        payload = getattr(record, "payload", None)
        summary = None
        if payload is not None:
            summary = getattr(payload, "summary", None)

        total = getattr(summary, "total", None) if summary is not None else None
        expected_total = getattr(payload, "expected_total", None) if payload is not None else None
        expected_total = expected_total if expected_total is not None else total

        passed = getattr(summary, "passed", 0) if summary is not None else 0
        failed = getattr(summary, "failed", 0) if summary is not None else 0
        skipped = getattr(summary, "skipped", None) if summary is not None else None
        if skipped is None and summary is not None:
            skipped = getattr(summary, "xfailed", None)
        skipped = skipped if skipped is not None else 0

        p = int(passed or 0)
        f = int(failed or 0)
        s = int(skipped or 0)
        done = p + f + s

        if expected_total and isinstance(expected_total, int) and expected_total > 0:
            st.progress(min(done / expected_total, 1.0))
            st.caption(f"Всего: {expected_total} — {p}✅ / {f}❌ / {s}⏭️ (готово {done}/{expected_total})")
        else:
            st.caption(f"Всего: ? — {p}✅ / {f}❌ / {s}⏭️")

        cases = getattr(payload, "cases", None) if payload is not None else None
        if cases:
            df = style_cases_table(cases)
            st.dataframe(df, width="stretch")
        else:
            st.caption("Нет данных по кейсам.")

    _details_fragment()

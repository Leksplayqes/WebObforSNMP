"""Sidebar widgets for quick actions and exports.

Lead-review changes:
- Removed fragile HTML/CSS injection; use Streamlit-native controls (link_button / markdown link fallback).
- Replaced invalid Streamlit params (width='stretch') with use_container_width.
- Deduplicated export rendering logic.
- Added small resilience improvements (sorting, id extraction).
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import streamlit as st
from pydantic import BaseModel

from frontend.api import BackendApiClient, BackendApiError


def _extract_job_id(record) -> Optional[str]:
    if isinstance(record, BaseModel):
        return getattr(record, "id", None)
    if isinstance(record, dict):
        return record.get("id")
    return getattr(record, "id", None)


def _render_link_button(label: str, url: str) -> None:
    """Prefer Streamlit-native link_button, fallback to markdown link."""
    if hasattr(st, "link_button"):
        # Streamlit >= 1.22 (roughly). If your version doesn't have it, markdown still works.
        st.link_button(label, url, use_container_width=True)
    else:
        st.markdown(f"[{label}]({url})")


def _render_export_section(
    title: str,
    empty_hint: str,
    select_label: str,
    button_label: str,
    records: Iterable,
    build_url,
    selectbox_key: str,
) -> None:
    st.subheader(title)

    job_ids: List[str] = []
    for r in records or []:
        job_id = _extract_job_id(r)
        if job_id:
            job_ids.append(str(job_id))

    # Basic UX: show most recent first if ids are time-sortable; otherwise keep stable.
    job_ids = list(dict.fromkeys(job_ids))  # de-dup preserving order

    if not job_ids:
        st.info(empty_hint)
        st.button(button_label, disabled=True, use_container_width=True)
        return

    selected = st.selectbox(select_label, job_ids, key=selectbox_key)
    url = build_url(selected)
    _render_link_button(button_label, url)


def sidebar_ui(client: BackendApiClient, api_base: str) -> None:
    st.markdown("")
    st.subheader("Тесты / утилиты")

    # ----------------- EXPORT: TEST JOBS -----------------
    try:
        records, _ = client.list_test_jobs()
    except BackendApiError as exc:
        st.warning(f"Не удалось загрузить список тестов: {exc}")
        records = []

    _render_export_section(
        title="Экспорт результатов тестов",
        empty_hint="Пока нет сохранённых тестов.",
        select_label="Выберите тест (job_id) для экспорта:",
        button_label="📊 Открыть экспорт результатов (JSON)",
        records=records,
        build_url=lambda job_id: f"{api_base.rstrip('/')}/tests/jobfile?job_id={job_id}",
        selectbox_key="sidebar_export_job_id",
    )

    st.markdown("---")

    # ----------------- EXPORT: UTILITY JOBS -----------------
    try:
        util_records, _ = client.list_util_jobs()
    except BackendApiError as exc:
        st.warning(f"Не удалось загрузить список утилит: {exc}")
        util_records = []

    _render_export_section(
        title="Экспорт результатов утилит",
        empty_hint="Пока нет запусков утилит.",
        select_label="Выберите запуск утилиты (job_id) для экспорта:",
        button_label="📊 Открыть экспорт утилиты (JSON)",
        records=util_records,
        build_url=lambda job_id: f"{api_base.rstrip('/')}/utilities/{job_id}/json",
        selectbox_key="sidebar_export_utility_job_id",
    )

    st.markdown("---")

"""Entry point assembling the modular Streamlit frontend."""
from __future__ import annotations

import os
import sys
import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api import BackendApiClient
from constants import BUTTON_STYLE, DEFAULT_API_BASE_URL, PAGE_CONFIG, TEST_CONFIG_STYLE
from state import apply_state
from ui import render_configuration, render_results, render_utils, sidebar_ui
from ui.traps import render_traps
from ui.vnc import render_vnc

st.set_page_config(**PAGE_CONFIG)
st.markdown(BUTTON_STYLE, unsafe_allow_html=True)
st.markdown(TEST_CONFIG_STYLE, unsafe_allow_html=True)
st.markdown("""
    <style>
    /* Сам текст внутри вкладок */
    .stTabs [data-baseweb="tab"] span {
        font-size: 20px !important;
        font-weight: 700 !important;
    }

    /* Дополнительно: убрать нежелательное увеличение от padding */
    .stTabs [data-baseweb="tab"] {
        padding-left: 12px !important;
        padding-right: 12px !important;
    }
    </style>
""", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(layout="wide")
    apply_state()

    api_base = st.session_state.get("api_base_url", DEFAULT_API_BASE_URL)
    client = BackendApiClient(api_base)

    # ========= SIDEBAR =========
    with st.sidebar:
        st.header("Результаты")
        sidebar_ui(client, api_base)

    # ========= MAIN CONTENT =========
    tab_titles = ["Конфигурация", "Результаты", "Утилиты", "ТРАПы", "VIAVI VNC"]
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        render_configuration(client)
    with tabs[1]:
        render_results(client)
    with tabs[2]:
        render_utils(client)
    with tabs[3]:
        render_traps(client)
    with tabs[4]:
        render_vnc()


if __name__ == "__main__":
    main()

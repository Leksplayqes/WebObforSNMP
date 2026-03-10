"""Constants shared across the Streamlit frontend modules."""
from pathlib import Path

PAGE_CONFIG = {
    "page_title": "OSM-K Tester System",
    "page_icon": "🛠️",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

BUTTON_STYLE = """
 <style>
 div.stButton > button:first-child {background-color: #800000; color: white;font-weight: bold;}
 div.stButton > button:first-child:hover {background-color: #560319;}
 </style>
"""
TEST_CONFIG_STYLE = """
<style>

/* Текст выбранного radio */
div[role="radiogroup"] label[data-baseweb="radio"] p {
    font-weight: 500;
}

/* ===== Multiselect: выбранные тесты (чипы) ===== */
span[data-baseweb="tag"] {
    background-color: #ee5858 !important;
    color: white !important;
    font-weight: 500;
    border-radius: 6px;
}

/* Hover для чипов */
span[data-baseweb="tag"]:hover {
    background-color: #560319 !important;
}

/* Крестик удаления */
span[data-baseweb="tag"] svg {
    color: white !important;
}

</style>
"""
DEFAULT_API_BASE_URL = "http://192.168.72.55:8000"

STATE_FILE = Path(__file__).resolve().parent.parent / "ui_state.json"

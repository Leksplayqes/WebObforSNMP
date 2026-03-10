import subprocess
import streamlit as st
import streamlit.components.v1 as components
import time

WEBSOCKIFY_PORT = 5901
NOVNC_DIR = r"C:\Users\mikhailov_gs.SUPERTEL\Documents\noVNC-1.7.0-beta\noVNC"


def _flash_message(msg_type: str, message: str, duration: int = 3):
    """Показывает сообщение на несколько секунд"""
    msg_box = st.empty()
    if msg_type == "success":
        msg_box.success(message)
    elif msg_type == "warning":
        msg_box.warning(message)
    elif msg_type == "error":
        msg_box.error(message)
    elif msg_type == "info":
        msg_box.info(message)
    time.sleep(duration)
    msg_box.empty()


def _start_websockify(target_ip_port: str):
    if "websockify_proc" not in st.session_state or st.session_state.websockify_proc.poll() is not None:
        try:
            command = [
                "websockify",
                str(WEBSOCKIFY_PORT),
                target_ip_port,
                "--web", NOVNC_DIR
            ]
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            st.session_state.websockify_proc = proc
            _flash_message("success", f"Vnc запущен для {target_ip_port}")
        except Exception as e:
            _flash_message("error", f"Ошибка запуска vnc: {e}")
    else:
        _flash_message("info", "VNC запуcпущен.")


def _stop_websockify():
    proc = st.session_state.get("websockify_proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            _flash_message("success", "VNC остановлен.")
        except Exception as e:
            _flash_message("error", f"Ошибка при остановке VNC: {e}")
    else:
        _flash_message("warning", "VNC уже не активен.")


def render_vnc():
    st.markdown("## Подключение к VIAVI")

    viavi_ip = st.session_state.get("viavi1_ip", "").strip()

    if not viavi_ip:
        _flash_message("warning", "IP-адрес VIAVI не задан. Укажите его во вкладке 'Конфигурация'.")
        return

    target = f"{viavi_ip}:5900"

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Подключиться"):
            _start_websockify(target)
    with col2:
        if st.button("Отключиться"):
            _stop_websockify()

    proc = st.session_state.get("websockify_proc")
    if proc and proc.poll() is None:
        host = "192.168.72.55"
        vnc_url = f"http://{host}:{WEBSOCKIFY_PORT}/vnc.html?autoconnect=true&host={host}&port={WEBSOCKIFY_PORT}"
        components.iframe(vnc_url, height=720, width=1024)
    else:
        st.info("VNC не запущен. Нажмите «Подключиться».")
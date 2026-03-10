import socket
import time
import contextlib
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterable, List

from MainConnectFunc import oidsVIAVI, json_input

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT_SEC = 3
RECV_BUF = 4096
WAIT_AFTER_EXIT_SEC = 0.3
WAIT_AFTER_LAUNCH_SEC = 30


# ====================== МОДЕЛЬ ПОРТА VIAVI ======================

@dataclass(frozen=True)
class ViaviPort:
    device_name: str
    ipaddr: str
    ctrl_port: int
    port_name: str
    port_type: str


# ====================== НИЗКОУРОВНЕВЫЕ ФУНКЦИИ ======================

def create_socket_connection(ipaddr: str, port: int) -> Optional[socket.socket]:
    if not ipaddr or not port:
        return None
    try:
        client = socket.socket()
        client.settimeout(SOCKET_TIMEOUT_SEC)
        client.connect((ipaddr, port))
        client.send(b"*REM VISIBLE FULL\n")
        return client
    except (socket.error, ConnectionError, TimeoutError) as exc:
        logger.warning("[VIAVI] Connection error to %s:%s: %s", ipaddr, port, exc)
        return None


def close_socket_connection(client: socket.socket) -> None:
    try:
        client.send(b":SESS:END\n")
    except Exception:
        pass
    try:
        client.close()
    except Exception:
        pass


def _send_line(client: socket.socket, line: str) -> None:
    client.send(line.encode("utf-8") + b"\n")


def _recv_str(client: socket.socket, buf: int = RECV_BUF) -> str:
    try:
        data = client.recv(buf)
        return data.decode(errors="ignore").strip()
    except socket.timeout:
        return ""
    except Exception:
        return ""


@contextlib.contextmanager
def viavi_connection(ipaddr: str, port: int):
    client = create_socket_connection(ipaddr, port)
    try:
        yield client
    finally:
        if client:
            close_socket_connection(client)


@contextlib.contextmanager
def viavi_port_connection(vp: ViaviPort):
    with viavi_connection(vp.ipaddr, vp.ctrl_port) as client:
        yield client


# ====================== РАБОТА С КОНФИГОМ VIAVI ======================

def _viavi_config() -> Dict[str, Any]:
    cfg = oidsVIAVI()
    return cfg if isinstance(cfg, dict) else {}


def iter_viavi_ports() -> Iterable[ViaviPort]:
    cfg = _viavi_config()
    settings = cfg.get("settings", {})
    if not isinstance(settings, dict):
        return

    for device_name, device_cfg in settings.items():
        if not isinstance(device_cfg, dict):
            continue

        ip = device_cfg.get("ipaddr")
        ctrl_port_raw = device_cfg.get("port", 0)
        try:
            ctrl_port = int(ctrl_port_raw or 0)
        except (TypeError, ValueError):
            ctrl_port = 0

        typeofport = device_cfg.get("typeofport", {})
        if not ip or not ctrl_port or not isinstance(typeofport, dict):
            continue

        for port_name, port_type in typeofport.items():
            if not port_type:
                continue
            yield ViaviPort(
                device_name=str(device_name),
                ipaddr=str(ip),
                ctrl_port=ctrl_port,
                port_name=str(port_name),
                port_type=str(port_type),
            )


def find_port_by_device_and_port(device_name: str, port_name: str) -> Optional[ViaviPort]:
    for vp in iter_viavi_ports():
        if vp.device_name == device_name and vp.port_name == port_name:
            return vp
    return None


def find_ports_by_type(port_type: str) -> List[ViaviPort]:
    t = str(port_type)
    return [vp for vp in iter_viavi_ports() if vp.port_type == t]


def set_viavi_port_type(device_name: str, port_name: str, new_type: str) -> Optional[ViaviPort]:
    try:
        json_input(
            ["VIAVIcontrol", "settings", device_name, "typeofport", port_name],
            str(new_type),
        )
    except Exception as exc:
        logger.error("[VIAVI] Failed to update port type: %s", exc)
        return None
    return find_port_by_device_and_port(device_name, port_name)


# ====================== ПРИЛОЖЕНИЯ / ВЫБОР ИНСТАНСА ======================

def _resolve_app_name(port_type: str, vc: str) -> Optional[str]:
    cfg = _viavi_config()
    testappl = cfg.get("testappl", {})
    if not isinstance(testappl, dict):
        return None
    port_apps = testappl.get(str(port_type), {})
    if not isinstance(port_apps, dict):
        return None
    return port_apps.get(vc)


def _installed_apps(client: socket.socket) -> List[str]:
    client.send(b":SYST:APPL:CAPP?\n")
    raw = _recv_str(client)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _base_from_app_name(app_name: str) -> str:
    name = (app_name or "").strip()

    return name


def _family_base(base: str) -> str:
    """База 'семейства' приложения, чтобы понять, что на порту уже запущен STM16, но другой VC.
    Для STM-конфигов вида ...Vc4Tu12Vc12 -> семейство это ...Vc4
    """
    b = (base or "").strip()
    return b.split("Tu", 1)[0] if "Tu" in b else b


def _port_sort_key(vp: ViaviPort):
    try:
        return int(vp.port_name)
    except ValueError:
        return vp.port_name


def _select_app_by_port(vp, apps):
    kill_port = vp.port_name[-1:]
    for i in apps:
        if i[-1] == kill_port:
            return i


def _select_app_instance_for_port(
        installed_apps: List[str],
        base: str,
        vp: Optional[ViaviPort],
        port_type: str,
) -> Optional[str]:
    matches = [a for a in installed_apps if base and (base in a) and vp.port_name[-1:] == a[-1]]
    matches.sort()
    if not matches:
        return None

    if vp is None:
        return None

    same_type_ports = [p for p in iter_viavi_ports() if p.device_name == vp.device_name and p.port_type == port_type]
    same_type_ports.sort(key=_port_sort_key)
    if len(same_type_ports) <= 1:
        return matches[0]
    try:
        idx = [p.port_name for p in same_type_ports].index(vp.port_name)
    except ValueError:
        idx = 0
    if idx >= len(matches) and matches[0][-1:] == vp.port_name[-1:]:
        return matches[0]
    return matches[idx]


def select_application(client: socket.socket, port_type: str, vc: str, vp: Optional[ViaviPort]) -> Optional[str]:
    app_name = _resolve_app_name(port_type, vc)
    if not app_name:
        logger.warning("[VIAVI] No app mapping for port_type=%s vc=%s", port_type, vc)
        return None

    base = _base_from_app_name(app_name)
    apps = _installed_apps(client)

    selected = _select_app_instance_for_port(apps, base, vp, port_type)
    if not selected:
        return None

    _send_line(client, f":SYST:APPL:SEL {selected}")
    client.send(b":SESS:CREATE\n")
    client.send(b":SESS:START\n")
    return selected


# ====================== УДАЛЕНИЕ ТЕСТА ТОЛЬКО НА ОДНОМ ПОРТУ ======================

def VIAVI_clearTest_by_port(
        *,
        device_name: str,
        port_name: str
) -> None:
    vp = find_port_by_device_and_port(device_name, port_name)
    with viavi_port_connection(vp) as client:
        if not client:
            return
        apps = _installed_apps(client)
        selected = _select_app_by_port(vp, apps)
        if not selected:
            return
        try:
            _send_line(client, f":SYST:APPL:SEL {selected}")
            client.send(b":Exit\n")
            time.sleep(WAIT_AFTER_EXIT_SEC)
        except Exception as exc:
            logger.warning("[VIAVI] clearTest_by_port error on %s.%s: %s", vp.device_name, vp.port_name, exc)


# ====================== SECOND STAGE: НА ОДНОМ ИЛИ НА ВСЕХ ======================

def VIAVI_secndStage(
        vc: str,
        *,
        device_name: Optional[str] = None,
        port_name: Optional[str] = None,
) -> None:
    ports = list(iter_viavi_ports())
    if device_name and port_name:
        ports = [p for p in ports if p.device_name == device_name and p.port_name == port_name]

    if not ports:
        logger.warning("[VIAVI] secndStage: no ports matched (device=%s port=%s)", device_name, port_name)
        return

    for vp in ports:
        app_name = _resolve_app_name(vp.port_type, vc)
        if not app_name:
            logger.warning("[VIAVI] secndStage: no app mapping for %s/%s on %s.%s",
                           vp.port_type, vc, vp.device_name, vp.port_name)
            continue

        desired_base = _base_from_app_name(app_name)
        fam_base = _family_base(desired_base)

        with viavi_port_connection(vp) as client:
            if not client:
                continue

            apps = _installed_apps(client)

            if _select_app_instance_for_port(apps, desired_base, vp, vp.port_type):
                selected = select_application(client, vp.port_type, vc, vp)
                if selected:
                    client.send(b":OUTPUT:OPTIC ON\n")
                continue

            current = _select_app_instance_for_port(apps, fam_base, vp, vp.port_type)

            if current:
                if desired_base not in current:
                    try:
                        _send_line(client, f":SYST:APPL:SEL {current}")
                        client.send(b":Exit\n")
                        time.sleep(WAIT_AFTER_EXIT_SEC)
                        apps = _installed_apps(client)
                    except Exception as exc:
                        logger.warning("[VIAVI] secndStage: Exit error on %s.%s: %s", vp.device_name, vp.port_name, exc)

        with viavi_port_connection(vp) as client:
            if not client:
                continue
            try:
                VIAVI_clearTest_by_port(device_name=device_name, port_name=port_name)
                _send_line(client, f":SYST:APPL:LAUN {app_name} {vp.port_name[-1:]}")
            except Exception as exc:
                logger.warning("[VIAVI] secndStage: LAUN error on %s.%s: %s", vp.device_name, vp.port_name, exc)
                continue

        time.sleep(WAIT_AFTER_LAUNCH_SEC)

        with viavi_port_connection(vp) as client:
            if not client:
                continue
            selected = select_application(client, vp.port_type, vc, vp)
            if not selected:
                apps = _installed_apps(client)
                logger.warning("[VIAVI] secndStage: app not running for %s/%s on %s.%s. CAPP?=%s",
                               vp.port_type, vc, vp.device_name, vp.port_name, apps)
                continue
            client.send(b":OUTPUT:OPTIC ON\n")



# ====================== КОМАНДЫ УПРАВЛЕНИЯ / ЧТЕНИЯ ======================

def _resolve_viavi_port(block: str, device_name: Optional[str], port_name: Optional[str]) -> Optional[ViaviPort]:
    if device_name and port_name:
        return find_port_by_device_and_port(device_name, port_name)
    ports = find_ports_by_type(block)
    return ports[0] if ports else None


def VIAVI_set_command(
        block: str,
        command: str,
        value: str = "",
        vc: str = "vc-4",
        device_name: Optional[str] = None,
        port_name: Optional[str] = None,
) -> None:
    vp = _resolve_viavi_port(block, device_name, port_name)
    if not vp:
        logger.warning("[VIAVI] set_command: port not resolved block=%s device=%s port=%s", block, device_name,
                       port_name)
        return

    with viavi_port_connection(vp) as client:
        if not client:
            return
        selected = select_application(client, block, vc, vp)
        if not selected:
            logger.warning("[VIAVI] set_command: app not running for %s/%s on %s.%s", block, vc, vp.device_name,
                           vp.port_name)
            return
        cmd = f"{command} {value}".strip()
        _send_line(client, cmd)


def VIAVI_get_command(
        block: str,
        command: str,
        vc: str = "vc-4",
        device_name: Optional[str] = None,
        port_name: Optional[str] = None,
) -> str:
    vp = _resolve_viavi_port(block, device_name, port_name)
    if not vp:
        logger.warning("[VIAVI] get_command: port not resolved block=%s device=%s port=%s", block, device_name,
                       port_name)
        return "-"

    with viavi_port_connection(vp) as client:
        if not client:
            return "-"
        selected = select_application(client, block, vc, vp)
        if not selected:
            logger.warning("[VIAVI] get_command: app not running for %s/%s on %s.%s", block, vc, vp.device_name,
                           vp.port_name)
            return "-"
        _send_line(client, command)
        return _recv_str(client) or "-"





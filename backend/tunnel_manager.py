"""Thread-safe tunnel manager with per-owner SNMP-over-SSH proxies."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from snmpsubsystem import ProxyController


class TunnelManagerError(RuntimeError):
    """Base error for tunnel manager failures."""


class TunnelPortsBusyError(TunnelManagerError):
    """Raised when all configured fixed ports are already in use."""


class TunnelConfigurationError(TunnelManagerError):
    """Raised when the requested tunnel cannot be configured."""


@dataclass
class LeaseInfo:
    owner_id: str
    owner_kind: str
    port: int
    created_at: float
    expires_at: float
    ttl: float
    device_ip: str
    username: str
    last_heartbeat: float

    def as_dict(self) -> Dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "owner_kind": self.owner_kind,
            "port": self.port,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "ttl": self.ttl,
            "device_ip": self.device_ip,
            "username": self.username,
            "last_heartbeat": self.last_heartbeat,
        }


class TunnelLease:
    """Lightweight handle for a reserved tunnel lease."""

    def __init__(self, manager: "TunnelManager", owner_id: str) -> None:
        self._manager = manager
        self.owner_id = owner_id
        self._released = False

    @property
    def info(self) -> LeaseInfo:
        info = self._manager._leases.get(self.owner_id)
        if not info:
            raise TunnelManagerError(f"lease {self.owner_id!r} is not active")
        return info

    @property
    def port(self) -> int:
        return self.info.port

    @property
    def host(self) -> str:
        return self._manager.listen_host

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._manager.release(self.owner_id)

    def renew(self, ttl: Optional[float] = None) -> None:
        self._manager.heartbeat(self.owner_id, ttl=ttl)


class TunnelManager:
    """Manage isolated SNMP-over-SSH proxies.

    Старое поведение держало один общий ProxyController на весь backend. Это
    ломало параллельные тесты: второй job закрывал или перенастраивал proxy
    первого job. Теперь каждый owner_id получает собственный ProxyController и
    собственный UDP port. Если в конфиге порт равен 0, ОС выдаёт свободный
    ephemeral port, поэтому параллельные job не конфликтуют.
    """

    def __init__(
            self,
            controller: Optional[ProxyController] = None,
            *,
            listen_host: str = "127.0.0.1",
            ports: Optional[Iterable[int]] = None,
            default_ttl: float = 600.0,
            cleanup_interval: float = 30.0,
    ) -> None:
        # controller оставлен в сигнатуре для обратной совместимости, но для
        # изоляции job создаётся отдельный ProxyController на каждый owner_id.
        self._initial_controller = controller
        self.listen_host = listen_host
        self._ports = self._normalise_ports(ports)
        self._default_ttl = float(default_ttl)
        self._cleanup_interval = float(cleanup_interval)

        self._lock = threading.RLock()
        self._leases: Dict[str, LeaseInfo] = {}
        self._controllers: Dict[str, ProxyController] = {}
        self._targets: Dict[str, tuple[str, str, str]] = {}

        self._stop_event = threading.Event()
        self._janitor = threading.Thread(target=self._janitor_loop, daemon=True)
        self._janitor.start()

    # -------------------- helpers --------------------
    @staticmethod
    def _normalise_ports(ports: Optional[Iterable[int]]) -> List[int]:
        if ports is None:
            return [1161]
        result: List[int] = []
        for p in ports:
            p_int = int(p)
            # 0 means "let OS choose a free port". Keep a single 0 entry;
            # it can be reused for every new independent ProxyController.
            if p_int == 0:
                if 0 not in result:
                    result.append(0)
                continue
            if p_int not in result:
                result.append(p_int)
        if not result:
            raise TunnelManagerError("no ports configured for TunnelManager")
        return result

    @staticmethod
    def _controller_udp_alive(controller: Optional[ProxyController]) -> bool:
        if controller is None or controller.proxy is None:
            return False
        return controller.proxy.transport is not None

    def _janitor_loop(self) -> None:
        """Periodically remove expired leases and stop only their proxies."""
        while not self._stop_event.wait(self._cleanup_interval):
            try:
                self._cleanup_expired()
            except Exception:
                pass

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._janitor.is_alive():
            self._janitor.join(timeout=1.0)
        with self._lock:
            for owner_id in list(self._controllers.keys()):
                self._close_owner_locked(owner_id)
            self._leases.clear()
            self._targets.clear()

    def _select_port_locked(self) -> int:
        # Dynamic port mode: every ProxyController can ask the OS for a free port.
        if 0 in self._ports:
            return 0

        used_ports = {info.port for info in self._leases.values()}
        for port in self._ports:
            if port not in used_ports:
                return port
        raise TunnelPortsBusyError("no free SNMP tunnel ports")

    def _close_owner_locked(self, owner_id: str) -> None:
        controller = self._controllers.pop(owner_id, None)
        self._targets.pop(owner_id, None)
        if controller is not None:
            try:
                controller.close()
            except Exception:
                pass
            try:
                controller.dispose()
            except Exception:
                pass

    def _start_owner_controller_locked(
            self,
            owner_id: str,
            *,
            ip: str,
            username: str,
            password: str,
    ) -> int:
        self._close_owner_locked(owner_id)
        listen_port = self._select_port_locked()
        controller = ProxyController()
        controller.start(
            ip=ip,
            username=username,
            password=password,
            listen_host=self.listen_host,
            listen_port=listen_port,
        )
        if controller.proxy is None or controller.proxy.transport is None:
            try:
                controller.dispose()
            except Exception:
                pass
            raise TunnelConfigurationError("SNMP proxy did not start")

        real_port = int(controller.proxy.listen_addr[1])
        self._controllers[owner_id] = controller
        self._targets[owner_id] = (ip, username, password)
        return real_port

    # -------------------- public API --------------------
    def lease(
            self,
            owner_id: str,
            owner_kind: str,
            *,
            ip: str,
            username: str,
            password: str,
            ttl: Optional[float] = None,
    ) -> TunnelLease:
        if not owner_id:
            raise TunnelManagerError("owner_id is required")

        now = time.time()
        ttl_value = float(ttl) if ttl is not None else self._default_ttl
        target = (ip, username, password)

        with self._lock:
            self._cleanup_expired_locked(now)

            info = self._leases.get(owner_id)
            controller = self._controllers.get(owner_id)
            if info and self._targets.get(owner_id) == target and self._controller_udp_alive(controller):
                port = info.port
            else:
                port = self._start_owner_controller_locked(
                    owner_id,
                    ip=ip,
                    username=username,
                    password=password,
                )

            if info:
                info.port = port
                info.ttl = ttl_value
                info.expires_at = now + ttl_value
                info.device_ip = ip
                info.username = username
                info.last_heartbeat = now
            else:
                info = LeaseInfo(
                    owner_id=owner_id,
                    owner_kind=owner_kind,
                    port=port,
                    created_at=now,
                    expires_at=now + ttl_value,
                    ttl=ttl_value,
                    device_ip=ip,
                    username=username,
                    last_heartbeat=now,
                )
                self._leases[owner_id] = info

        return TunnelLease(self, owner_id)

    def heartbeat(self, owner_id: str, ttl: Optional[float] = None) -> None:
        ttl_value = float(ttl) if ttl is not None else None
        now = time.time()
        with self._lock:
            info = self._leases.get(owner_id)
            if not info:
                return
            if ttl_value is not None:
                info.ttl = ttl_value
            info.expires_at = now + info.ttl
            info.last_heartbeat = now

    def release(self, owner_id: str) -> None:
        """Release only the requested owner's proxy."""
        with self._lock:
            self._leases.pop(owner_id, None)
            self._close_owner_locked(owner_id)

    # -------------------- diagnostics --------------------
    def active_leases(self) -> List[Dict[str, object]]:
        with self._lock:
            self._cleanup_expired_locked(time.time())
            return [info.as_dict() for info in self._leases.values()]

    def tunnel_alive(self) -> bool:
        with self._lock:
            return any(self._controller_udp_alive(controller) for controller in self._controllers.values())

    # -------------------- internal cleanup --------------------
    def _cleanup_expired(self) -> None:
        with self._lock:
            self._cleanup_expired_locked(time.time())

    def _cleanup_expired_locked(self, now: float) -> None:
        expired = [key for key, info in self._leases.items() if info.expires_at <= now]
        for key in expired:
            self._leases.pop(key, None)
            self._close_owner_locked(key)


all = [
    "TunnelManager",
    "TunnelLease",
    "TunnelManagerError",
    "TunnelPortsBusyError",
    "TunnelConfigurationError",
    "LeaseInfo",
]

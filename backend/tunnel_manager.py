"""Thread-safe tunnel manager with simple lease tracking for SNMP-over-SSH."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from snmpsubsystem import ProxyController


class TunnelManagerError(RuntimeError):
    """Base error for tunnel manager failures."""


class TunnelPortsBusyError(TunnelManagerError):
    """Raised when all configured ports are already in use."""


class TunnelConfigurationError(TunnelManagerError):
    """Raised when the requested tunnel conflicts with the active configuration."""


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
    """Keep a single ProxyController + simple lease registry.

    * один ProxyController на менеджер;
    * один UDP-порт (по умолчанию 1161);
    * при смене IP (другое устройство) текущий туннель закрывается
      и поднимается заново уже для нового ip.
    """

    def __init__(
            self,
            controller: ProxyController,
            *,
            listen_host: str = "127.0.0.1",
            ports: Optional[Iterable[int]] = None,
            default_ttl: float = 600.0,
            cleanup_interval: float = 30.0,
    ) -> None:
        self._controller = controller
        self.listen_host = listen_host
        self._ports = self._normalise_ports(ports)
        self._default_ttl = float(default_ttl)
        self._cleanup_interval = float(cleanup_interval)

        self._lock = threading.RLock()
        self._leases: Dict[str, LeaseInfo] = {}
        self._active_port: Optional[int] = None
        # (ip, username, password) для текущего SSH-туннеля
        self._current_target: Optional[Tuple[str, str, str]] = None

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
            if p_int not in result:
                result.append(p_int)
        if not result:
            raise TunnelManagerError("no ports configured for TunnelManager")
        return result

    def _janitor_loop(self) -> None:
        """Periodically remove expired leases and stop tunnel if nobody uses it."""
        while not self._stop_event.wait(self._cleanup_interval):
            try:
                self._cleanup_expired()
            except Exception:
                pass

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._janitor.is_alive():
            self._janitor.join(timeout=1.0)

        # -------------------- core controller logic --------------------

    def _select_port(self) -> int:
        """Простой выбор порта: переиспользуем существующий, иначе первый из списка."""
        if self._active_port is not None:
            return self._active_port
        if not self._ports:
            raise TunnelPortsBusyError("no ports available for SNMP tunnel")
        self._active_port = self._ports[0]
        return self._active_port

    def _ensure_controller(self, ip: str, username: str, password: str) -> int:
        """Гарантировать, что запущен proxy для указанного устройства."""
        proxy = self._controller.proxy

        if proxy is not None:
            # Проверяем, жив ли процесс snmp-подсистемы.
            try:
                proc_alive = proxy._proc_alive()
            except Exception:
                proc_alive = False

            if proc_alive and self._current_target == (ip, username, password):
                # То же устройство — просто переиспользуем.
                port = proxy.listen_addr[1]
                self._active_port = port
                return port

            # Здесь либо устройство ДРУГОЕ, либо процесс уже умер.
            # В любом случае текущий proxy нам больше не нужен.
            self._controller.close()
            # ⬇⬇⬇ КРИТИЧЕСКИЙ МОМЕНТ: стираем ссылку на старый proxy,
            # чтобы .start(...) создал новый SnmpSshProxy с НОВЫМ ip.
            self._controller.proxy = None
            self._active_port = None
            self._current_target = None

        # Поднимаем новый proxy под новое устройство.
        port = self._select_port()
        self._controller.start(
            ip=ip,
            username=username,
            password=password,
            listen_host=self.listen_host,
            listen_port=port,
        )
        self._active_port = port
        self._current_target = (ip, username, password)
        return port

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

        with self._lock:
            self._cleanup_expired_locked(now)
            port = self._ensure_controller(ip, username, password)

            info = self._leases.get(owner_id)
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
        """Явно освободить аренду; при последней — закрыть туннель."""
        with self._lock:
            removed = self._leases.pop(owner_id, None)
            if not removed:
                return
            if not self._leases:
                self._controller.close()
                self._controller.proxy = None
                self._active_port = None
                self._current_target = None

        # -------------------- diagnostics --------------------

    def active_leases(self) -> List[Dict[str, object]]:
        with self._lock:
            self._cleanup_expired_locked(time.time())
            return [info.as_dict() for info in self._leases.values()]

    def tunnel_alive(self) -> bool:
        proxy = self._controller.proxy
        if proxy is None:
            return False
        try:
            return proxy._proc_alive()
        except Exception:
            return False

        # -------------------- internal cleanup --------------------

    def _cleanup_expired(self) -> None:
        self._cleanup_expired_locked(time.time())

    def _cleanup_expired_locked(self, now: float) -> None:
        expired = [key for key, info in self._leases.items() if info.expires_at <= now]
        if not expired:
            return
        for key in expired:
            self._leases.pop(key, None)
        if not self._leases:
            self._controller.close()
            self._controller.proxy = None
            self._active_port = None
            self._current_target = None

    all = [
        "TunnelManager",
        "TunnelLease",
        "TunnelManagerError",
        "TunnelPortsBusyError",
        "TunnelConfigurationError",
        "LeaseInfo",
    ]

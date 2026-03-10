"""Tunnel management service that encapsulates proxy state."""
from __future__ import annotations

import threading
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from snmpsubsystem import ProxyController

from ..config import DEFAULT_TUNNEL_PORTS, get_tunnel_ports
from ..tunnel_manager import (
    TunnelConfigurationError,
    TunnelLease,
    TunnelManager,
    TunnelManagerError,
    TunnelPortsBusyError,
)


def _configured_ports() -> List[int]:
    """Return list of UDP ports to use for SNMP-over-SSH tunnels."""
    try:
        ports = get_tunnel_ports()
    except Exception:
        # Если конфиг не задан/сломался — используем дефолт.
        ports = list(DEFAULT_TUNNEL_PORTS)
    return list(ports)


class TunnelService:
    """Обёртка над TunnelManager + ProxyController.

    * один ProxyController на процесс;
    * один TunnelManager на процесс;
    * registry отслеживаемых lease'ов по owner_id.
    """

    def __init__(
            self,
            *,
            controller: Optional[ProxyController] = None,
            ports: Optional[Iterable[int]] = None,
    ) -> None:
        self._controller = controller or ProxyController()
        self._manager = TunnelManager(self._controller, ports=ports or _configured_ports())
        self._lock = threading.RLock()
        # owner_id -> TunnelLease (последний полученный для этого owner_id)
        self._tracked: Dict[str, TunnelLease] = {}

    # ---------------- Lease management ----------------
    def reserve(
            self,
            owner_id: str,
            owner_kind: str,
            *,
            ip: str,
            username: str,
            password: str,
            ttl: Optional[float] = None,
            track: bool = False,
    ) -> TunnelLease:
        """Получить/обновить аренду туннеля.

        ВАЖНО: TunnelManager.lease уже умеет обновлять lease по тому
        же owner_id. Нам не нужно руками "освобождать" предыдущий lease
        для того же owner_id — это как раз ломало работу.
        """
        lease = self._manager.lease(
            owner_id,
            owner_kind,
            ip=ip,
            username=username,
            password=password,
            ttl=ttl,
        )

        if track:
            # Просто запоминаем последнюю аренду для owner_id.
            # previous.release() НЕ вызываем, иначе мы сами себе
            # гасим туннель.
            with self._lock:
                self._tracked[owner_id] = lease

        return lease

    def release(self, owner_id: str) -> None:
        """Явно освободить аренду по owner_id."""
        with self._lock:
            lease = self._tracked.pop(owner_id, None)

        if lease is not None:
            # Это в конечном итоге вызовет TunnelManager.release(owner_id)
            lease.release()
        else:
            # На всякий случай попробуем отпустить напрямую в менеджере.
            try:
                self._manager.release(owner_id)
            except TunnelManagerError:
                # Если его там уже нет — ничего страшного.
                pass

    def heartbeat(self, owner_id: str, ttl: Optional[float] = None) -> None:
        """Продлить TTL существующей аренды."""
        self._manager.heartbeat(owner_id, ttl=ttl)

    # ---------------- Diagnostics ----------------
    def tunnel_alive(self) -> bool:
        """Жив ли snmp-over-ssh процесс."""
        return self._manager.tunnel_alive()

    def describe(self) -> List[Dict[str, object]]:
        """JSON-friendly описание всех активных арен."""
        return self._manager.active_leases()

    # ---------------- Accessors ----------------
    @property
    def manager(self) -> TunnelManager:
        return self._manager


@lru_cache(maxsize=1)
def get_tunnel_service() -> TunnelService:
    """Вернуть *общий* TunnelService на весь процесс.

    Благодаря lru_cache(maxsize=1) у нас:
    * один общий ProxyController;
    * один общий TunnelManager;
    * один общий pool портов.
    """
    return TunnelService()


all = [
    "TunnelService",
    "get_tunnel_service",
    "TunnelManagerError",
    "TunnelPortsBusyError",
    "TunnelConfigurationError",
    "TunnelLease",
]

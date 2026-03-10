"""Compatibility wrappers around the tunnel service."""
from __future__ import annotations

from typing import Dict, List, Optional

from .services import (
    TunnelConfigurationError,
    TunnelLease,
    TunnelManagerError,
    TunnelPortsBusyError,
    TunnelService,
    get_tunnel_service,
)


def _service() -> TunnelService:
    return get_tunnel_service()


def reserve_tunnel(
    owner_id: str,
    owner_kind: str,
    *,
    ip: str,
    username: str,
    password: str,
    ttl: Optional[float] = None,
    track: bool = False,
) -> TunnelLease:
    return _service().reserve(
        owner_id,
        owner_kind,
        ip=ip,
        username=username,
        password=password,
        ttl=ttl,
        track=track,
    )


def release_tunnel(owner_id: str) -> None:
    _service().release(owner_id)


def heartbeat_tunnel(owner_id: str, ttl: Optional[float] = None) -> None:
    _service().heartbeat(owner_id, ttl=ttl)


def tunnel_alive() -> bool:
    return _service().tunnel_alive()


def describe_tunnels() -> List[Dict[str, object]]:
    return _service().describe()


__all__ = [
    "TunnelManagerError",
    "TunnelPortsBusyError",
    "TunnelConfigurationError",
    "TunnelLease",
    "reserve_tunnel",
    "release_tunnel",
    "heartbeat_tunnel",
    "tunnel_alive",
    "describe_tunnels",
]

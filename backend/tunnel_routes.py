"""Endpoints exposing tunnel manager diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .config import get_tunnel_ports
from backend.services.models import TunnelStatusEnvelope, TunnelStatusResponse
from .services import TunnelService, get_tunnel_service

router = APIRouter(prefix="/tunnels", tags=["tunnels"])


@router.get("", summary="List active SNMP tunnels", response_model=TunnelStatusEnvelope)
def list_tunnels(service: TunnelService = Depends(get_tunnel_service)) -> TunnelStatusEnvelope:
    status = TunnelStatusResponse(
        alive=service.tunnel_alive(),
        configured_ports=get_tunnel_ports(),
        leases=service.describe(),
    )
    return TunnelStatusEnvelope(status="success", data=status)


__all__ = ["router"]


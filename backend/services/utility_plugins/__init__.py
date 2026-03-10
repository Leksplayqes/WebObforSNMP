from __future__ import annotations

from ..utilities_core import UtilityRegistry

from .check_conf import CheckConfUtility
from .check_hash import CheckHashUtility
from .fpga_reload import FpgaReloadUtility


def register_all(registry: UtilityRegistry) -> None:
    registry.register(CheckConfUtility())
    registry.register(CheckHashUtility())
    registry.register(FpgaReloadUtility())


__all__ = ["register_all"]

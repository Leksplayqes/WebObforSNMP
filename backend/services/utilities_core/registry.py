"""Utility registry with optional auto-discovery."""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Iterable, List, Optional

from .base import UtilityBase


class UtilityRegistry:
    def __init__(self) -> None:
        self._by_id: Dict[str, UtilityBase] = {}

    def register(self, util: UtilityBase) -> None:
        uid = util.meta.id
        if uid in self._by_id:
            raise RuntimeError(f"Utility already registered: {uid}")
        self._by_id[uid] = util

    def get(self, utility_id: str) -> Optional[UtilityBase]:
        return self._by_id.get(utility_id)

    def list(self) -> List[UtilityBase]:
        return list(self._by_id.values())

    def discover(self, package: str) -> None:
        """Import all modules in a package to allow them to self-register."""
        pkg = importlib.import_module(package)
        for _, modname, ispkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            if ispkg:
                continue
            importlib.import_module(modname)

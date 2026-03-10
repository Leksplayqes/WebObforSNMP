from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel

from checkFunctions.check_hash import compare_directories_by_hash

from ..models import CheckHashParameters
from ..utilities_core import UtilityBase, UtilityContext, UtilityError, UtilityMeta


class CheckHashOutput(BaseModel):
    result: Dict[str, Any]


class CheckHashUtility(UtilityBase):
    meta = UtilityMeta(
        id="check_hash",
        title="Сравнение директорий по хэшу (check_hash)",
        description="Сравнивает две директории по содержимому (hash).",
        tags=("fs", "hash"),
        requires_tunnel=False,
    )
    InputModel = CheckHashParameters
    OutputModel = CheckHashOutput

    def run(self, ctx: UtilityContext, params: CheckHashParameters) -> CheckHashOutput:
        try:
            res = compare_directories_by_hash(params.dir1, params.dir2)
            return CheckHashOutput(result=res)
        except Exception as exc:
            raise UtilityError("CHECK_HASH_FAILED", str(exc), retryable=False) from exc

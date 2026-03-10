from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel

from checkFunctions.fpga_reload import fpga_reload

from ..models import FpgaReloadParameters
from ..utilities_core import UtilityBase, UtilityContext, UtilityError, UtilityMeta
import inspect

class FpgaReloadOutput(BaseModel):
    result: Dict[str, Any]


class FpgaReloadUtility(UtilityBase):
    meta = UtilityMeta(
        id="fpga_reload",
        title="Перезагрузка FPGA (fpga_reload)",
        description="Запускает fpga_reload с прогрессом по попыткам.",
        tags=("fpga", "ssh"),
        requires_tunnel=True,
        default_timeout_sec=1800.0,
    )
    InputModel = FpgaReloadParameters
    OutputModel = FpgaReloadOutput

    def run(self, ctx: UtilityContext, params: FpgaReloadParameters) -> FpgaReloadOutput:
        owner_id = f"utils:{ctx.job_id}"
        entries: List[dict] = []
        try:
            ctx.tunnel_service.reserve(
                owner_id=owner_id,
                owner_kind="utils",
                ip=params.ip,
                username="admin",
                password=params.password or "",
                ttl=1800.0,
                track=True,
            )

            def progress_cb(attempt: int, entry: dict, all_entries: List[dict]) -> None:
                ctx.report(
                    result={"attempts": attempt, "entries": all_entries},
                    summary={
                        "status": "running",
                        "total": params.max_attempts,
                        "message": f"Попытка {attempt}/{params.max_attempts}",
                    },
                )

            kwargs = {
                "ip": params.ip,
                "password": params.password or "",
                "slot": params.slot,
                "max_attempts": params.max_attempts,
            }
            if "progress_cb" in inspect.signature(fpga_reload).parameters:
                kwargs["progress_cb"] = progress_cb

            res = fpga_reload(**kwargs)
            return FpgaReloadOutput(result=res)

        except Exception as exc:
            raise UtilityError("FPGA_RELOAD_FAILED", str(exc), retryable=False) from exc
        finally:
            try:
                ctx.tunnel_service.release(owner_id)
            except Exception:
                pass

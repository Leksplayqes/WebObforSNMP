from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel

from checkFunctions.check_conf import check_conf

from ..models import CheckConfParameters
from ..tunnels import TunnelConfigurationError, TunnelManagerError, TunnelPortsBusyError
from ..utilities_core import UtilityBase, UtilityContext, UtilityError, UtilityMeta


class CheckConfOutput(BaseModel):
    result: Dict[str, Any]


class CheckConfUtility(UtilityBase):
    meta = UtilityMeta(
        id="check_conf",
        title="Проверка конфигурации (check_conf)",
        description="Запускает check_conf на удаленном устройстве с прогрессом.",
        tags=("conf", "ssh"),
        requires_tunnel=True,
        default_timeout_sec=1800.0,
    )
    InputModel = CheckConfParameters
    OutputModel = CheckConfOutput

    def run(self, ctx: UtilityContext, params: CheckConfParameters) -> CheckConfOutput:
        owner_id = f"utils:{ctx.job_id}"
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

            def progress_cb(iteration: int, total: int, iter_result: dict, summary_dict: dict) -> None:
                ctx.report(
                    result=summary_dict,
                    summary={
                        "status": "running",
                        "total": total,
                        "message": f"Итерация {iteration}/{total}: {iter_result.get('status')}",
                    },
                )

            res = check_conf(
                ip=params.ip,
                password=params.password or "",
                iterations=params.iterations,
                delay_between=params.delay,
                progress_cb=progress_cb,
            )
            return CheckConfOutput(result=res)

        except (TunnelPortsBusyError, TunnelConfigurationError, TunnelManagerError) as exc:
            raise UtilityError("TUNNEL", f"Ошибка туннеля: {exc}", retryable=True) from exc
        except Exception as exc:
            raise UtilityError("CHECK_CONF_FAILED", str(exc), retryable=False) from exc
        finally:
            try:
                ctx.tunnel_service.release(owner_id)
            except Exception:
                pass

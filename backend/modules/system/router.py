"""健康檢查、系統狀態、背景工作、Prometheus 指標。

- `/healthz`（公開）：程序存活，不洩漏任何資訊。
- `/readyz`（公開）：資料庫可寫且 migration 到位就是 200，否則 503；只回摘要（不含路徑與細節）。
- `/api/system/status`（登入）：完整明細，每個功能是否可用與原因（導覽灰掉用，原因只帶相對路徑）。
- `/metrics`（qc 以上或 API key）：Prometheus 文字格式。
"""

from core import anomaly_training, audit, health, jobs, metrics
from core.auth import Principal, require_login, require_role
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

router = APIRouter(tags=["系統"])
_read = require_role("qc", allow_api_key=True)


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    summary = health.summary(health.compute_status())
    return JSONResponse(summary, status_code=200 if summary["ready"] else 503)


@router.get("/api/system/status")
def system_status(force: bool = False, _: Principal = Depends(require_login)):
    return health.compute_status(force)


@router.get("/metrics")
def prometheus_metrics(_: Principal = Depends(_read)):
    return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/api/jobs")
def list_jobs(kind: str | None = None, status: str | None = None, limit: int = 100, _: Principal = Depends(_read)):
    return jobs.list_jobs(kind, status, min(limit, 500))


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, principal: Principal = Depends(require_role("admin"))):
    """重試中斷或失敗的背景工作（目前只有異常檢測擬合），用已存的照片重新擬合成新版本。"""
    before = jobs.get_job(job_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"找不到工作 id={job_id}")
    try:
        updated = anomaly_training.retry_job(job_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    health.clear_cache()
    audit.record(
        principal.actor,
        "job.retry",
        "job",
        job_id,
        before={"status": before["status"], "attempts": before["attempts"]},
        after={"status": updated["status"], "name": updated["payload"].get("name")},
    )
    return updated

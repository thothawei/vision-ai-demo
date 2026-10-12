from core import audit, recipes
from core.auth import Principal, require_login, require_role
from core.inspection_log import (
    get_image_file_path,
    get_inspection,
    get_stats,
    is_image_expired,
    query_inspections,
    query_reviewed_since,
    to_csv,
    update_review,
)
from core.request_scope import IMAGE_ROLES
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/inspections", tags=["檢驗紀錄"])

# 唯讀端點：qc 以上的使用者，或系統對系統的 API key（ERP 輪詢）
_read = require_role("qc", allow_api_key=True)


@router.get("")
def list_inspections(
    module: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    work_order: str | None = None,
    part_no: str | None = None,
    lot_no: str | None = None,
    station: str | None = None,
    limit: int = 200,
    since_id: int | None = None,
    principal: Principal = Depends(require_login),
):
    """operator 只看得到自己建立的紀錄；qc、admin 與 API key 看全部。"""
    created_by = principal.actor if principal.kind == "user" and principal.role == "operator" else None
    return query_inspections(
        module,
        verdict,
        date_from,
        date_to,
        work_order,
        part_no,
        lot_no,
        station,
        limit,
        since_id,
        created_by=created_by,
    )


@router.get("/reviews")
def list_reviews(since: str, limit: int = 200, _: Principal = Depends(_read)):
    """給 ERP 抓「事後被改判」的紀錄：since 是 ISO 時間字串（例如 2026-09-24T00:00:00）。"""
    return query_reviewed_since(since, limit)


@router.get("/export.csv")
def export_csv(
    module: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    work_order: str | None = None,
    part_no: str | None = None,
    lot_no: str | None = None,
    station: str | None = None,
    limit: int = 10000,
    _: Principal = Depends(_read),
):
    records = query_inspections(
        module,
        verdict,
        date_from,
        date_to,
        work_order,
        part_no,
        lot_no,
        station,
        limit,
    )
    # 加 BOM 讓 Excel 直接開啟時中文不亂碼
    return Response(
        content="﻿" + to_csv(records),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inspections.csv"'},
    )


@router.get("/stats")
def stats(
    group_by: str = "module",
    date_from: str | None = None,
    date_to: str | None = None,
    module: str | None = None,
    scope: str = "step",
    _: Principal = Depends(_read),
):
    """scope=step（預設）：以單筆辨識為單位；scope=run：以配方檢驗為單位（group_by 改用 part／day／defect）。"""
    try:
        if scope == "run":
            return recipes.get_run_stats(group_by if group_by != "module" else "part", date_from, date_to)
        if scope != "step":
            raise ValueError(f"scope 只能是 step 或 run，目前是「{scope}」")
        return get_stats(group_by, date_from, date_to, module)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ReviewRequest(BaseModel):
    review_verdict: str = Field(..., description="OK 或 NG")
    reviewer: str | None = Field(None, deprecated=True, description="已忽略：複判人取自登入者")
    review_note: str | None = None


@router.patch("/{inspection_id}/review")
def review_inspection(
    inspection_id: int,
    body: ReviewRequest,
    principal: Principal = Depends(require_role("qc")),
):
    """複判人一律取自登入者；body 的 reviewer 欄位僅為相容舊客戶端而保留，會被忽略。"""
    before = get_inspection(inspection_id)
    try:
        updated = update_review(inspection_id, body.review_verdict, principal.name, body.review_note)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"找不到檢驗紀錄 id={inspection_id}")
    fields = ("review_verdict", "reviewer", "reviewed_at", "review_note")
    audit.record(
        principal.actor,
        "inspection.review",
        "inspection",
        inspection_id,
        before={k: before[k] for k in fields},
        after={k: updated[k] for k in fields},
    )
    return updated


@router.get("/{inspection_id}")
def get_one(inspection_id: int, _: Principal = Depends(_read)):
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"找不到檢驗紀錄 id={inspection_id}")
    return record


@router.get("/{inspection_id}/image")
def get_image(inspection_id: int, kind: str = "raw", _: Principal = Depends(_read)):
    if kind not in ("annotated", *IMAGE_ROLES):
        raise HTTPException(status_code=400, detail=f"kind 只能是 annotated 或 {'、'.join(IMAGE_ROLES)}")
    path = get_image_file_path(inspection_id, kind)
    if path is None and is_image_expired(inspection_id, kind):
        raise HTTPException(
            status_code=410, detail=f"id={inspection_id} 的 {kind} 圖片已依保存期限清理（紀錄本身保留）"
        )
    if path is None:
        raise HTTPException(status_code=404, detail=f"找不到 id={inspection_id} 的 {kind} 圖片")
    return FileResponse(path)

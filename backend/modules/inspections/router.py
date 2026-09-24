from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from core.inspection_log import (
    get_image_file_path,
    get_inspection,
    get_stats,
    query_inspections,
    to_csv,
    update_review,
)

router = APIRouter(prefix="/api/inspections", tags=["檢驗紀錄"])


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
):
    return query_inspections(
        module, verdict, date_from, date_to, work_order, part_no, lot_no, station, limit,
    )


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
):
    records = query_inspections(
        module, verdict, date_from, date_to, work_order, part_no, lot_no, station, limit,
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
):
    try:
        return get_stats(group_by, date_from, date_to, module)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ReviewRequest(BaseModel):
    review_verdict: str = Field(..., description="OK 或 NG")
    reviewer: str | None = None
    review_note: str | None = None


@router.patch("/{inspection_id}/review")
def review_inspection(inspection_id: int, body: ReviewRequest):
    try:
        updated = update_review(inspection_id, body.review_verdict, body.reviewer, body.review_note)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"找不到檢驗紀錄 id={inspection_id}")
    return updated


@router.get("/{inspection_id}")
def get_one(inspection_id: int):
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"找不到檢驗紀錄 id={inspection_id}")
    return record


@router.get("/{inspection_id}/image")
def get_image(inspection_id: int, kind: str = "raw"):
    if kind not in ("raw", "annotated"):
        raise HTTPException(status_code=400, detail="kind 只能是 raw 或 annotated")
    path = get_image_file_path(inspection_id, kind)
    if path is None:
        raise HTTPException(status_code=404, detail=f"找不到 id={inspection_id} 的 {kind} 圖片")
    return FileResponse(path)

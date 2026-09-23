from fastapi import APIRouter
from fastapi.responses import Response

from core.inspection_log import query_inspections, to_csv

router = APIRouter(prefix="/api/inspections", tags=["檢驗紀錄"])


@router.get("")
def list_inspections(
    module: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
):
    return query_inspections(module, verdict, date_from, date_to, limit)


@router.get("/export.csv")
def export_csv(
    module: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10000,
):
    records = query_inspections(module, verdict, date_from, date_to, limit)
    # 加 BOM 讓 Excel 直接開啟時中文不亂碼
    return Response(
        content="﻿" + to_csv(records),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inspections.csv"'},
    )

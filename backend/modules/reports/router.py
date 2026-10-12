"""品質日報／週報（JSON、Excel、可列印 HTML）。qc 以上，或系統對系統的 API key（唯讀）。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from core import reports
from core.auth import Principal, require_role

router = APIRouter(prefix="/api/reports", tags=["報表"])


@router.get("/summary")
def summary(period: str = "day", on_date: date | None = Query(None, alias="date"), format: str = "json",
            _: Principal = Depends(require_role("qc", allow_api_key=True))):
    """period=day|week；date＝基準日（預設今天；週報是包含該日的那一週，週一到週日）；format=json|xlsx|html。"""
    if format not in ("json", "xlsx", "html"):
        raise HTTPException(status_code=400, detail=f"format 只能是 json、xlsx 或 html，目前是「{format}」")
    try:
        report = reports.build_report(period, on_date or date.today())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if format == "xlsx":
        name = f"report-{period}-{report['date_from']}.xlsx"
        return Response(reports.to_xlsx(report),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    if format == "html":
        return HTMLResponse(reports.to_html(report))
    return report

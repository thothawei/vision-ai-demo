"""統計製程管制：特性清單與管制圖。qc 以上，或系統對系統的 API key（唯讀）。"""

from core import spc, spc_service
from core.auth import Principal, require_role
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/spc", tags=["SPC"], dependencies=[Depends(require_role("qc", allow_api_key=True))])


@router.get("/characteristics")
def characteristics(part_no: str | None = None):
    """可做 SPC 的（料號，特性）清單；料號為空的量測，`part_no` 值是 `__none__`。"""
    return spc_service.list_characteristics(part_no)


@router.get("")
def analyze(
    characteristic: str,
    part_no: str | None = None,
    chart: str = "xbar_r",
    subgroup_size: int = Query(5, ge=2, le=10),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    station: str | None = None,
    run_length: int = Query(spc.DEFAULT_RUN_LENGTH, ge=5, le=12),
    _: Principal = Depends(require_role("qc", allow_api_key=True)),
):
    """X̄-R（chart=xbar_r，子群大小 2–10）或 I-MR（chart=imr）；回傳管制界限、Cp／Cpk、Western Electric 規則觸發點。"""
    try:
        return spc_service.analyze(
            part_no, characteristic, chart, subgroup_size, date_from, date_to, station, run_length
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

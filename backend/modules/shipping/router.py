from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.shipping.service import check_shipping_label

router = APIRouter(prefix="/api/shipping", tags=["M12 出貨標籤 vs 工單比對"])


@router.post("/check-label", response_model=InspectionResult)
def check_label(
    file: UploadFile = File(...),
    expected_part_no: str | None = None,
    expected_lot_no: str | None = None,
    expected_quantity: int | None = None,
):
    """預期值優先順序：這裡帶的參數 > 追溯資訊 header（X-Part-No/X-Lot-No）。"""
    return check_shipping_label(file.file.read(), expected_part_no, expected_lot_no, expected_quantity)

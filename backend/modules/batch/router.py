from fastapi import APIRouter, File, Form, UploadFile

from core.batch_dispatch import run_batch

router = APIRouter(prefix="/api/batch", tags=["Phase 11 批次上傳"])


@router.post("/{action}")
def batch(
    action: str,
    files: list[UploadFile] = File(...),
    mode: str | None = None,
    category: str | None = None,
    expected_count: int | None = None,
    min_area_ratio: float | None = None,
    marker_size_mm: float | None = None,
    target_length_mm: float | None = None,
    target_width_mm: float | None = None,
    tolerance_mm: float | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_angle: float | None = None,
    max_angle: float | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    zone: str | None = Form(None),
    expected_part_no: str | None = None,
    expected_lot_no: str | None = None,
    expected_quantity: int | None = None,
):
    """整批共用同一組額外參數（例如同一台攝影機拍的危險區域照片共用同一個 zone），
    不是每張各自設定。單張失敗不會讓整批中斷，見 core/batch_dispatch.run_batch()。"""
    params = {
        "mode": mode, "category": category, "expected_count": expected_count,
        "min_area_ratio": min_area_ratio, "marker_size_mm": marker_size_mm,
        "target_length_mm": target_length_mm, "target_width_mm": target_width_mm,
        "tolerance_mm": tolerance_mm, "min_value": min_value, "max_value": max_value,
        "min_angle": min_angle, "max_angle": max_angle, "center_x": center_x,
        "center_y": center_y, "zone": zone,
        "expected_part_no": expected_part_no, "expected_lot_no": expected_lot_no,
        "expected_quantity": expected_quantity,
    }
    items = [(f.filename or "unnamed", f.file.read()) for f in files]
    return run_batch(action, items, params)

import json

from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult, ModuleError
from modules.colordiff.service import DEFAULT_THRESHOLD, check_color_difference

router = APIRouter(prefix="/api/color", tags=["M11 烤漆/陽極色差 ΔE"])


@router.post("/check", response_model=InspectionResult)
def check(
    file: UploadFile = File(...),
    ref_rect: str | None = None,
    ref_lab: str | None = None,
    measure_rect: str = "",
    threshold: float = DEFAULT_THRESHOLD,
):
    """ref_rect/measure_rect：JSON 字串 [x1,y1,x2,y2]（正規化座標 0~1）；ref_lab：JSON 字串 [L,a,b]。"""
    try:
        ref_rect_list = json.loads(ref_rect) if ref_rect else None
        ref_lab_list = json.loads(ref_lab) if ref_lab else None
        measure_rect_list = json.loads(measure_rect) if measure_rect else None
    except json.JSONDecodeError:
        raise ModuleError("ref_rect/ref_lab/measure_rect 要是合法 JSON", 400)
    return check_color_difference(file.file.read(), ref_rect_list, ref_lab_list, measure_rect_list, threshold)

from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.nameplate.service import read_gauge, read_nameplate, read_seven_segment

router = APIRouter(prefix="/api/nameplate", tags=["M7 銘牌／儀表讀值"])


@router.post("/read", response_model=InspectionResult)
def nameplate(file: UploadFile = File(...)):
    return read_nameplate(file.file.read())


@router.post("/seven-segment", response_model=InspectionResult)
def seven_segment(file: UploadFile = File(...)):
    return read_seven_segment(file.file.read())


@router.post("/gauge", response_model=InspectionResult)
def gauge(
    file: UploadFile = File(...),
    min_value: float = 0,
    max_value: float = 100,
    min_angle: float = 135,
    max_angle: float = 45,
    center_x: float | None = None,
    center_y: float | None = None,
):
    """角度慣例：0 度＝3 點鐘方向，順時針遞增（見 core/gauge.py 說明）。
    center_x/center_y 是正規化座標（0~1）；不給就自動找圓心。"""
    return read_gauge(file.file.read(), min_value, max_value, min_angle, max_angle, center_x, center_y)

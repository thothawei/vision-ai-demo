from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.measure.service import count_parts, measure_part

router = APIRouter(prefix="/api/measure", tags=["M2 計數與尺寸量測"])


@router.post("/count", response_model=InspectionResult)
def count(
    file: UploadFile = File(...),
    expected_count: int | None = None,
    min_area_ratio: float = 0.0005,
):
    return count_parts(file.file.read(), expected_count, min_area_ratio)


@router.post("/measure", response_model=InspectionResult)
def measure(
    file: UploadFile = File(...),
    marker_size_mm: float = 30.0,
    target_length_mm: float | None = None,
    target_width_mm: float | None = None,
    tolerance_mm: float = 1.0,
):
    return measure_part(file.file.read(), marker_size_mm, target_length_mm, target_width_mm, tolerance_mm)

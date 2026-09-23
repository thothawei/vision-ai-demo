from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.anomaly.service import inspect_part

router = APIRouter(prefix="/api/anomaly", tags=["M3 外觀瑕疵異常檢測"])


@router.post("/inspect", response_model=InspectionResult)
def inspect(file: UploadFile = File(...), category: str = "metal_nut"):
    return inspect_part(file.file.read(), category)

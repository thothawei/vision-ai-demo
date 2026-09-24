from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core import anomaly_training
from core.schemas import InspectionResult, ModuleError
from modules.anomaly.service import inspect_part, list_all_categories

router = APIRouter(prefix="/api/anomaly", tags=["M3 外觀瑕疵異常檢測"])


@router.post("/inspect", response_model=InspectionResult)
def inspect(file: UploadFile = File(...), category: str = "metal_nut"):
    return inspect_part(file.file.read(), category)


@router.get("/categories/all")
def all_categories():
    """給前端下拉選單：內建示範類別 + 已擬合完成的自訂類別。"""
    return {"categories": list_all_categories()}


@router.post("/categories")
def create_category(
    name: str,
    good_zip: UploadFile = File(...),
    defect_zip: UploadFile | None = File(None),
):
    """上傳良品照片 zip（必要，>=15 張）+ NG 照片 zip（可選），排隊背景擬合。
    同時只允許一個擬合工作，其餘排隊；用 GET /categories/{name}/status 查進度。"""
    try:
        return anomaly_training.enqueue_category(
            name, good_zip.file.read(), defect_zip.file.read() if defect_zip else None,
        )
    except ModuleError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/categories")
def list_categories():
    return anomaly_training.list_custom_categories()


@router.get("/categories/{name}/status")
def category_status(name: str):
    status = anomaly_training.get_status(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"找不到類別「{name}」")
    return status


@router.get("/categories/{name}/scores")
def category_scores(name: str):
    try:
        return anomaly_training.get_scores(name)
    except ModuleError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


class ThresholdRequest(BaseModel):
    threshold: float = Field(..., description="異常分數 >= 這個值就判 NG")


@router.patch("/categories/{name}/threshold")
def update_threshold(name: str, body: ThresholdRequest):
    try:
        return anomaly_training.set_threshold(name, body.threshold)
    except ModuleError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

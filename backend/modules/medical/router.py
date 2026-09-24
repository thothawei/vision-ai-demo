from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.medical.service import check_packaging, classify_pneumonia_demo

router = APIRouter(prefix="/api/medical", tags=["M8 醫療相關辨識"])


@router.post("/packaging-check", response_model=InspectionResult)
def packaging_check(file: UploadFile = File(...)):
    """比對 GS1 UDI 條碼跟印刷文字上的批號/效期是否一致（GMP 追溯用途）。"""
    return check_packaging(file.file.read())


@router.post("/pneumonia-demo", response_model=InspectionResult)
def pneumonia_demo(file: UploadFile = File(...)):
    """PneumoniaMNIST 教學展示分類。僅供技術展示，非醫療診斷用途。"""
    return classify_pneumonia_demo(file.file.read())

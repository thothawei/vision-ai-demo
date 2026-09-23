from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.general.service import describe_image

router = APIRouter(prefix="/api/general", tags=["M9 開放式辨識"])


# 用 def（非 async）讓阻塞的模型推論跑在 threadpool，不卡住 event loop
@router.post("/describe", response_model=InspectionResult)
def describe(file: UploadFile = File(...)):
    return describe_image(file.file.read())

from fastapi import APIRouter, File, Form, UploadFile

from core.schemas import InspectionResult
from modules.safety.service import detect_intrusion, detect_ppe

router = APIRouter(prefix="/api/safety", tags=["M5 工安：危險區域入侵 / PPE"])


@router.post("/intrusion", response_model=InspectionResult)
def intrusion(file: UploadFile = File(...), zone: str | None = Form(None)):
    """zone：JSON 字串，正規化座標（0~1）多邊形頂點，例如 '[[0.1,0.1],[0.5,0.1],[0.5,0.9]]'；不給就只做人員偵測。"""
    return detect_intrusion(file.file.read(), zone)


@router.post("/ppe", response_model=InspectionResult)
def ppe(file: UploadFile = File(...)):
    """安全帽偵測；資料集只有 helmet/head 兩類，沒有反光背心。"""
    return detect_ppe(file.file.read())

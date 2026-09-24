from fastapi import APIRouter, File, Form, UploadFile

from core.schemas import InspectionResult
from modules.safety.service import (
    DEFAULT_MAX_DURATION_S,
    DEFAULT_SAMPLE_INTERVAL_S,
    detect_intrusion,
    detect_intrusion_video,
    detect_ppe,
    detect_ppe_video,
)

router = APIRouter(prefix="/api/safety", tags=["M5 工安：危險區域入侵 / PPE"])


@router.post("/intrusion", response_model=InspectionResult)
def intrusion(file: UploadFile = File(...), zone: str | None = Form(None)):
    """zone：JSON 字串，正規化座標（0~1）多邊形頂點，例如 '[[0.1,0.1],[0.5,0.1],[0.5,0.9]]'；不給就只做人員偵測。"""
    return detect_intrusion(file.file.read(), zone)


@router.post("/ppe", response_model=InspectionResult)
def ppe(file: UploadFile = File(...)):
    """安全帽偵測；資料集只有 helmet/head 兩類，沒有反光背心。"""
    return detect_ppe(file.file.read())


@router.post("/video", response_model=InspectionResult)
def intrusion_video(
    file: UploadFile = File(...),
    zone: str | None = Form(None),
    sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
):
    """短影片逐幀抽樣做危險區域入侵偵測，每 sample_interval_s 秒抽一幀，最多處理 max_duration_s 秒。
    檢驗紀錄只寫一筆彙總（含違規時間點清單），不是每幀一筆。"""
    return detect_intrusion_video(file.file.read(), zone, sample_interval_s, max_duration_s)


@router.post("/ppe/video", response_model=InspectionResult)
def ppe_video(
    file: UploadFile = File(...),
    sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
):
    """短影片逐幀抽樣做安全帽偵測，同上。"""
    return detect_ppe_video(file.file.read(), sample_interval_s, max_duration_s)

from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.defect.service import detect_pcb_defects

router = APIRouter(prefix="/api/defect", tags=["M6 監督式瑕疵偵測"])


@router.post("/pcb", response_model=InspectionResult)
def pcb(file: UploadFile = File(...)):
    return detect_pcb_defects(file.file.read())

from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.docs.service import extract_document

router = APIRouter(prefix="/api/docs", tags=["M4 製造文件結構化"])


@router.post("/extract", response_model=InspectionResult)
def extract(file: UploadFile = File(...), mode: str = "ocr"):
    return extract_document(file.file.read(), mode)

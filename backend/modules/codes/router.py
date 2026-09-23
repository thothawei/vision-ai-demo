from fastapi import APIRouter, File, UploadFile

from core.schemas import InspectionResult
from modules.codes.service import decode_codes

router = APIRouter(prefix="/api/codes", tags=["M1 追溯碼辨識"])


@router.post("/decode", response_model=InspectionResult)
def decode(file: UploadFile = File(...)):
    return decode_codes(file.file.read())

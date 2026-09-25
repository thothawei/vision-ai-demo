import json

from fastapi import APIRouter, File, Form, UploadFile

from core.schemas import InspectionResult, ModuleError
from modules.assembly.service import get_golden_sample, inspect_assembly, list_golden_samples, save_golden_sample

router = APIRouter(prefix="/api/assembly", tags=["M10 組裝防呆／黃金樣本比對"])


@router.post("/golden-samples")
def create_golden_sample(part_no: str, file: UploadFile = File(...), rois: str = Form(...)):
    """rois：JSON 字串，正規化座標（0~1）的矩形陣列，例如 '[[0.1,0.1,0.2,0.2], ...]'。"""
    try:
        roi_list = json.loads(rois)
    except json.JSONDecodeError:
        raise ModuleError("rois 不是合法 JSON", 400)
    return save_golden_sample(part_no, file.file.read(), roi_list)


@router.get("/golden-samples")
def list_samples():
    return list_golden_samples()


@router.get("/golden-samples/{part_no}")
def get_sample(part_no: str):
    return get_golden_sample(part_no)


@router.post("/inspect", response_model=InspectionResult)
def inspect(part_no: str, file: UploadFile = File(...)):
    return inspect_assembly(part_no, file.file.read())

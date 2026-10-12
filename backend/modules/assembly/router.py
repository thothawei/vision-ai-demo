import json

from core import audit
from core.auth import Principal, require_role
from core.schemas import InspectionResult, ModuleError
from fastapi import APIRouter, Depends, File, Form, UploadFile

from modules.assembly.service import get_golden_sample, inspect_assembly, list_golden_samples, save_golden_sample

router = APIRouter(prefix="/api/assembly", tags=["M10 組裝防呆／黃金樣本比對"])


@router.post("/golden-samples")
def create_golden_sample(
    part_no: str,
    file: UploadFile = File(...),
    rois: str = Form(...),
    principal: Principal = Depends(require_role("admin")),
):
    """rois：JSON 字串，正規化座標（0~1）的矩形陣列，例如 '[[0.1,0.1,0.2,0.2], ...]'。"""
    try:
        roi_list = json.loads(rois)
    except json.JSONDecodeError:
        raise ModuleError("rois 不是合法 JSON", 400)
    try:
        before = {"rois": get_golden_sample(part_no)["rois"]}  # 覆寫既有黃金樣本時留下舊的 ROI
    except ModuleError:
        before = None
    result = save_golden_sample(part_no, file.file.read(), roi_list)
    audit.record(
        principal.actor,
        "golden_sample.update" if before else "golden_sample.create",
        "golden_sample",
        part_no,
        before=before,
        after={"rois": roi_list},
    )
    return result


@router.get("/golden-samples")
def list_samples():
    return list_golden_samples()


@router.get("/golden-samples/{part_no}")
def get_sample(part_no: str):
    return get_golden_sample(part_no)


@router.post("/inspect", response_model=InspectionResult)
def inspect(part_no: str, file: UploadFile = File(...)):
    return inspect_assembly(part_no, file.file.read())

"""POST /api/batch/{action} 批次上傳；動作與參數驗證來自 core/registry.py（未知參數回 422）。"""

from core import registry
from core.batch_dispatch import run_batch
from core.schemas import ModuleError
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

router = APIRouter(prefix="/api/batch", tags=["批次上傳"])


@router.post("/{action}")
async def batch(action: str, request: Request):
    """整批共用同一組額外參數（例如同一台攝影機拍的危險區域照片共用同一個 zone），
    參數可放 query 或 form 欄位；空字串視為沒給。單張失敗不會讓整批中斷。"""
    spec = registry.get_action(action)
    if spec is None or not spec.batchable:
        raise ModuleError(f"action 只能是 {registry.batch_action_names()} 其中之一，目前是「{action}」", 400)

    form = await request.form()
    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    if not uploads:
        return JSONResponse(status_code=422, content={"detail": "缺少 files 欄位（至少一個檔案）"})

    raw = dict(request.query_params)
    for key, value in form.multi_items():
        if key != "files" and isinstance(value, str):
            raw[key] = value
    raw = {k: v for k, v in raw.items() if v != ""}

    if spec.params is None:
        if raw:
            return JSONResponse(status_code=422, content={"detail": f"{action} 不接受額外參數：{sorted(raw)}"})
        params = None
    else:
        try:
            params = spec.params.model_validate(raw)
        except ValidationError as e:
            return JSONResponse(status_code=422, content={"detail": e.errors(include_url=False, include_context=False)})

    items = [(f.filename or "unnamed", await f.read()) for f in uploads]
    return await run_in_threadpool(run_batch, action, items, params)

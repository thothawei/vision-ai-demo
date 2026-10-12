"""模型登錄：查看版本與指標、切換（回滾）啟用版本。權重只能由伺服器端腳本登錄，這裡不提供上傳。"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from core import audit, model_catalog, model_registry
from core.auth import Principal, require_role

router = APIRouter(prefix="/api/models", tags=["模型登錄"])
logger = logging.getLogger("vision.model")
_read = require_role("qc", allow_api_key=True)


def _public(version: dict) -> dict:
    """不把伺服器上的絕對路徑露給前端（登錄時存的相對路徑就夠辨識）。"""
    return {k: v for k, v in version.items() if k != "weights_abs"}


def _model(model_id: str) -> dict:
    versions = model_registry.list_versions(model_id)
    if not versions:
        raise HTTPException(status_code=404, detail=f"找不到模型「{model_id}」（還沒登錄過任何版本）")
    return {"model_id": model_id, "catalog": model_catalog.describe(model_id), "versions": [_public(v) for v in versions]}


@router.get("")
def list_models(_: Principal = Depends(_read)):
    return [{**{k: v for k, v in m.items() if k != "versions"}, "versions": [_public(v) for v in m["versions"]]}
            for m in model_registry.list_models()]


@router.get("/{model_id}")
def get_model(model_id: str, _: Principal = Depends(_read)):
    return _model(model_id)


@router.post("/{model_id}/versions/{version}/activate")
def activate(model_id: str, version: int, principal: Principal = Depends(require_role("admin"))):
    """切換啟用版本（回滾用）。啟用前先確認該版本的權重檔存在、sha256 相符，避免回滾到壞掉的版本。"""
    target = model_registry.get_version(model_id, version)
    if target is None:
        raise HTTPException(status_code=404, detail=f"找不到模型 {model_id} 的版本 v{version}")
    if target["status"] == "active":
        return _public(target)
    path = Path(target["weights_abs"])
    if not path.is_file():
        raise HTTPException(status_code=422, detail=f"v{version} 的權重檔不存在：{target['weights_path']}，不能啟用")
    if model_registry.sha256_file(path) != target["sha256"]:
        raise HTTPException(status_code=422, detail=f"v{version} 的權重檔 SHA-256 與登錄不符（被更動或損毀），不能啟用")
    previous, current = model_registry.activate_version(model_id, version)
    audit.record(principal.actor, "model.activate", "model", model_id,
                 before={"version": previous["version"] if previous else None}, after={"version": version})
    return _public(current)

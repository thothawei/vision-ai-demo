"""批次上傳（`POST /api/batch/{action}`）的執行核心。動作清單與參數模型來自 `core/registry.py`。"""

from pydantic import BaseModel

from core import registry, request_scope
from core.schemas import ModuleError


def run_batch(action: str, files: list[tuple[str, bytes]], params: BaseModel | None) -> dict:
    """逐檔呼叫對應動作，單檔失敗不中斷整批；回傳彙總 + 每檔結果。
    整批共用同一組額外參數（不是每張各自設定）。"""
    spec = registry.get_action(action)
    if spec is None or not spec.batchable:
        raise ModuleError(f"action 只能是 {registry.batch_action_names()} 其中之一，目前是「{action}」", 400)

    results = []
    counts = {"OK": 0, "NG": 0, "INFO": 0}
    failed = 0
    for filename, image_bytes in files:
        request_scope.reset_images()  # 每張圖各自存圖，不要沿用上一張留下的 role
        try:
            result = spec.handler(image_bytes, params)
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
            results.append({"filename": filename, "status": "ok", "result": result})
        except ModuleError as e:
            failed += 1
            results.append({"filename": filename, "status": "error", "error": e.message})
        except Exception as e:  # noqa: BLE001 — 單張的未預期錯誤不該讓整批中斷
            failed += 1
            results.append({"filename": filename, "status": "error", "error": str(e)})

    return {
        "action": action,
        "total": len(files),
        "ok": counts["OK"],
        "ng": counts["NG"],
        "info": counts["INFO"],
        "failed": failed,
        "results": results,
    }

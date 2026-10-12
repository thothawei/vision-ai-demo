"""M3 外觀瑕疵異常檢測（Anomalib PatchCore，非監督：只需要良品照片就能擬合）。

推論用 anomalib 匯出的 TorchInferencer（scripts/train_anomaly.py 產生），
一次載入後常駐記憶體（依 category 各自快取），不必每次都重建 Lightning 模組。

Phase 12：新增自訂類別（`core/anomaly_training.py` 背景擬合），`is_valid_category()`／
`list_all_categories()` 把內建三個示範類別跟使用者自訂類別合併起來給前端下拉選單用。
門檻判定：類別有 `threshold.json`（自訂類別一定有）就用 `pred_score >= threshold`；
沒有（內建三個示範類別，Phase 3 沿用至今）就用匯出時烤進權重的 `pred_label`，
行為完全不變，不會因為 Phase 12 而影響既有三個類別的判定結果。
"""

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from core import model_registry
from core.image_io import bgr_to_data_url, load_image
from core.inspection_log import record_result
from core.logging_setup import log_model_load
from core.schemas import InspectionResult, ModuleError

MODULE = "anomaly"

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "anomaly"
CATEGORIES = ["metal_nut", "screw", "tile"]

_cache = model_registry.VersionedCache()


def _custom_category_names() -> set[str]:
    from core import anomaly_training

    return {c["name"] for c in anomaly_training.list_custom_categories() if c.get("status") == "done"}


def list_all_categories() -> list[str]:
    """內建示範類別 + 已擬合完成的自訂類別，給前端下拉選單／驗證用。"""
    return [*CATEGORIES, *sorted(_custom_category_names())]


def is_valid_category(category: str) -> bool:
    return category in CATEGORIES or category in _custom_category_names()


def _load_threshold(category: str) -> float | None:
    """門檻跟著「目前啟用的版本」走（每次擬合的距離分數尺度不同，回滾版本時門檻要一起回滾）。"""
    threshold_path = model_registry.active_anomaly_root(category, MODELS_DIR / category) / "threshold.json"
    if not threshold_path.exists():
        return None
    return json.loads(threshold_path.read_text())["threshold"]


def inspect_part(image_bytes: bytes, category: str) -> InspectionResult:
    if not is_valid_category(category):
        raise ModuleError(
            f"category「{category}」不存在，目前可用：{list_all_categories()}",
            400,
        )

    started = time.perf_counter()
    image = load_image(image_bytes)

    inferencer = _get_inferencer(category)
    prediction = inferencer.predict(image)

    score = float(prediction.pred_score)
    threshold = _load_threshold(category)
    is_anomalous = (score >= threshold) if threshold is not None else bool(prediction.pred_label)
    annotated = _draw_heatmap(image, prediction.anomaly_map)

    verdict = "NG" if is_anomalous else "OK"
    item = {
        "類別": category,
        "異常分數": round(score, 4),
        "判定": "異常" if is_anomalous else "正常",
    }
    if threshold is not None:
        item["使用門檻"] = round(threshold, 4)
    return record_result(MODULE, verdict, [item], "anomalib-patchcore", started, bgr_to_data_url(annotated))


def invalidate_cache(category: str) -> None:
    """類別有新版本或切換版本後可呼叫，丟掉記憶體裡的舊推論器（快取本來就以版本為鍵，這只是提早釋放）。"""
    _cache.drop(f"anomaly-{category}")


def _load_inferencer(path, category: str):
    from anomalib.deploy import TorchInferencer

    # anomalib 的 TorchInferencer 預設拒絕 unpickle（可能執行任意程式碼的資安風險）。
    # 這裡載入的是本機訓練、經模型登錄驗證過 sha256 的權重，不是下載來路不明的檔案，可信任；
    # 所以權重只能由伺服器端腳本登錄，網頁不提供上傳。只在載入時開啟，不動全域環境。
    os.environ["TRUST_REMOTE_CODE"] = "1"
    with log_model_load(f"anomaly-patchcore:{category}"):
        return TorchInferencer(path=path, device="cpu")


def _get_inferencer(category: str):
    resolved = model_registry.resolve(
        f"anomaly-{category}",
        MODELS_DIR / category / "weights" / "torch" / "model.pt",
        f"找不到 {category} 的異常檢測模型，請先執行 "
        f"`python scripts/train_anomaly.py --category {category}` 擬合並匯出",
    )
    return _cache.get(resolved, lambda path: _load_inferencer(path, category))


def _draw_heatmap(image, anomaly_map: torch.Tensor) -> np.ndarray:
    """把異常熱力圖疊在原圖上（紅色越深代表越異常）。"""
    heat = anomaly_map.squeeze().detach().cpu().numpy()
    heat = heat - heat.min()
    if heat.max() > 0:
        heat = heat / heat.max()
    heat_u8 = (heat * 255).astype(np.uint8)

    base = np.array(image)[:, :, ::-1].copy()  # RGB -> BGR
    heat_resized = cv2.resize(heat_u8, (base.shape[1], base.shape[0]))
    colored = cv2.applyColorMap(heat_resized, cv2.COLORMAP_JET)
    return cv2.addWeighted(base, 0.6, colored, 0.4, 0)

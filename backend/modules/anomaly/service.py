"""M3 外觀瑕疵異常檢測（Anomalib PatchCore，非監督：只需要良品照片就能擬合）。

推論用 anomalib 匯出的 TorchInferencer（scripts/train_anomaly.py 產生），
一次載入後常駐記憶體（依 category 各自快取），不必每次都重建 Lightning 模組。
"""

import os
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from core.image_io import bgr_to_data_url, load_image
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "anomaly"

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "anomaly"
CATEGORIES = ["metal_nut", "screw", "tile"]

_inferencers: dict[str, object] = {}


def inspect_part(image_bytes: bytes, category: str) -> InspectionResult:
    if category not in CATEGORIES:
        raise ModuleError(f"category 只能是 {CATEGORIES} 其中之一，目前是「{category}」", 400)

    started = time.perf_counter()
    image = load_image(image_bytes)

    inferencer = _get_inferencer(category)
    prediction = inferencer.predict(image)

    score = float(prediction.pred_score)
    is_anomalous = bool(prediction.pred_label)
    annotated = _draw_heatmap(image, prediction.anomaly_map)

    verdict = "NG" if is_anomalous else "OK"
    item = {
        "類別": category,
        "異常分數": round(score, 4),
        "判定": "異常" if is_anomalous else "正常",
    }
    return record_result(MODULE, verdict, [item], "anomalib-patchcore", started, bgr_to_data_url(annotated))


def _get_inferencer(category: str):
    if category not in _inferencers:
        from anomalib.deploy import TorchInferencer

        weights_path = MODELS_DIR / category / "weights" / "torch" / "model.pt"
        if not weights_path.exists():
            raise ModuleError(
                f"找不到 {category} 的異常檢測模型，請先執行 "
                f"`python scripts/train_anomaly.py --category {category}` 擬合並匯出",
                503,
            )
        # anomalib 的 TorchInferencer 預設拒絕 unpickle（可能執行任意程式碼的資安風險）。
        # 這裡載入的是 scripts/train_anomaly.py 在本機訓練、自己匯出的權重，不是下載來路不明
        # 的檔案，可信任；只在載入這個模組期間開啟，不動全域環境。
        os.environ["TRUST_REMOTE_CODE"] = "1"
        _inferencers[category] = TorchInferencer(path=weights_path, device="cpu")
    return _inferencers[category]


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

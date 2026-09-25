"""M11 烤漆/陽極色差 ΔE（CIELAB + CIEDE2000，免訓練）。

使用者框「標準色區」（或直接輸入標準 Lab 值）與「量測區」，各自裁切後算平均 Lab，
用 skimage 的 deltaE_ciede2000 算色差，超過門檻判不合格。
"""

import time

import cv2
import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "colordiff"
DEFAULT_THRESHOLD = 3.0  # ΔE00：業界常見「肉眼可辨但不算嚴重瑕疵」的邊界，可調整


def _crop_normalized(rgb: np.ndarray, rect: list[float]) -> np.ndarray:
    if len(rect) != 4:
        raise ModuleError("ROI 要是 [x1,y1,x2,y2]（正規化座標 0~1）", 400)
    h, w = rgb.shape[:2]
    x1, y1, x2, y2 = rect
    px1, py1, px2, py2 = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
    if px2 <= px1 or py2 <= py1:
        raise ModuleError("ROI 範圍不合法（x2/y2 要大於 x1/y1）", 400)
    return rgb[py1:py2, px1:px2]


def _mean_lab(rgb_region: np.ndarray) -> np.ndarray:
    lab = rgb2lab(rgb_region.astype(np.float64) / 255.0)
    return lab.reshape(-1, 3).mean(axis=0)


def _rect_to_px(rect: list[float], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    return int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)


def check_color_difference(
    image_bytes: bytes,
    ref_rect: list[float] | None,
    ref_lab: list[float] | None,
    measure_rect: list[float],
    threshold: float = DEFAULT_THRESHOLD,
) -> InspectionResult:
    if not ref_rect and not ref_lab:
        raise ModuleError("要提供 ref_rect（標準色區）或 ref_lab（標準 Lab 值）其中一個", 400)
    if not measure_rect:
        raise ModuleError("要提供 measure_rect（量測區）", 400)

    started = time.perf_counter()
    image = load_image(image_bytes)
    rgb = np.array(image)

    measured_lab = _mean_lab(_crop_normalized(rgb, measure_rect))

    if ref_rect:
        reference_lab = _mean_lab(_crop_normalized(rgb, ref_rect))
        ref_source = "標準色區"
    else:
        if len(ref_lab) != 3:
            raise ModuleError("ref_lab 要是 [L, a, b] 三個數字", 400)
        reference_lab = np.array(ref_lab, dtype=np.float64)
        ref_source = "手動輸入 Lab"

    delta_e = float(deltaE_ciede2000(reference_lab, measured_lab))
    verdict = "NG" if delta_e > threshold else "OK"

    bgr = to_bgr(image)
    annotated = bgr.copy()
    h, w = bgr.shape[:2]
    if ref_rect:
        rx1, ry1, rx2, ry2 = _rect_to_px(ref_rect, w, h)
        cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (255, 140, 0), 2)
        cv2.putText(annotated, "標準", (rx1, max(ry1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 140, 0), 2, cv2.LINE_AA)
    mx1, my1, mx2, my2 = _rect_to_px(measure_rect, w, h)
    color = (0, 140, 255) if verdict == "OK" else (0, 0, 255)
    cv2.rectangle(annotated, (mx1, my1), (mx2, my2), color, 2)
    cv2.putText(annotated, f"dE={delta_e:.2f}", (mx1, max(my1 - 8, 15)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    item = {
        "標準來源": ref_source,
        "標準Lab": [round(float(v), 2) for v in reference_lab],
        "量測Lab": [round(float(v), 2) for v in measured_lab],
        "ΔE00": round(delta_e, 3),
        "門檻": threshold,
        "判定": "合格" if verdict == "OK" else "不合格",
    }
    return record_result(MODULE, verdict, [item], "skimage-ciede2000", started, bgr_to_data_url(annotated))

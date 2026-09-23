"""M5 工安：危險區域入侵偵測（免訓練）。

YOLO COCO 預訓練模型偵測人員 → 使用者在前端畫多邊形危險區域 → 判斷人員的腳底參考點是否落在區內。
Phase 2 只做單張圖片；短影片逐幀抽樣留到 Phase 5 跟 PPE 一起做（見 CLAUDE.md 待辦）。
"""

import json
import time
from pathlib import Path

import cv2
import numpy as np

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "safety"

WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "models" / "yolo" / "yolo11n.pt"
PERSON_CLASS_ID = 0
CONF_THRESHOLD = 0.4

_model = None


def _get_model():
    """延遲載入，缺權重時回傳清楚錯誤。"""
    global _model
    if _model is None:
        if not WEIGHTS_PATH.exists():
            raise ModuleError(
                f"找不到 YOLO 權重 {WEIGHTS_PATH}，請先執行："
                "`python -c \"from ultralytics import YOLO; YOLO('yolo11n.pt')\"` "
                f"再把下載到的 yolo11n.pt 搬到 {WEIGHTS_PATH}",
                503,
            )
        from ultralytics import YOLO

        _model = YOLO(str(WEIGHTS_PATH))
    return _model


def detect_intrusion(image_bytes: bytes, zone_json: str | None) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    zone_px = _parse_zone(zone_json, image.width, image.height) if zone_json else None

    persons = _detect_persons(bgr)
    for p in persons:
        p["是否入侵"] = bool(zone_px is not None and _point_in_zone(p["腳底參考點"], zone_px))

    annotated = _draw_annotations(bgr, persons, zone_px)

    if zone_px is None:
        verdict = "INFO"
    else:
        verdict = "NG" if any(p["是否入侵"] for p in persons) else "OK"

    result = [{"偵測到人數": len(persons), "危險區域": zone_px is not None, "明細": persons}]
    return record_result(MODULE, verdict, result, "yolo11n-coco", started, bgr_to_data_url(annotated))


def _detect_persons(bgr: np.ndarray) -> list[dict]:
    model = _get_model()
    results = model.predict(bgr, classes=[PERSON_CLASS_ID], conf=CONF_THRESHOLD, verbose=False)

    persons = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        persons.append({
            "信心度": round(float(box.conf[0]), 3),
            "邊界框": [round(x1), round(y1), round(x2), round(y2)],
            "腳底參考點": [round((x1 + x2) / 2), round(y2)],
        })
    return persons


def _parse_zone(zone_json: str, image_w: int, image_h: int) -> np.ndarray:
    """zone_json：正規化座標（0~1）的多邊形頂點陣列，例如 [[0.1,0.1],[0.5,0.1],[0.5,0.9]]。"""
    try:
        points = json.loads(zone_json)
    except json.JSONDecodeError:
        raise ModuleError("zone 不是合法 JSON，格式應為 [[x,y], ...]（正規化座標 0~1）", 400)

    if not isinstance(points, list) or len(points) < 3:
        raise ModuleError("zone 至少要有 3 個頂點才能構成區域", 400)

    try:
        pixel_points = [[round(x * image_w), round(y * image_h)] for x, y in points]
    except (TypeError, ValueError):
        raise ModuleError("zone 每個頂點必須是 [x, y] 數字座標", 400)

    return np.array(pixel_points, dtype=np.int32)


def _point_in_zone(point: list[int], zone_px: np.ndarray) -> bool:
    return cv2.pointPolygonTest(zone_px, (point[0], point[1]), False) >= 0


def _draw_annotations(bgr: np.ndarray, persons: list[dict], zone_px: np.ndarray | None) -> np.ndarray:
    canvas = bgr.copy()
    if zone_px is not None:
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [zone_px], (0, 0, 200))
        canvas = cv2.addWeighted(overlay, 0.25, canvas, 0.75, 0)
        cv2.polylines(canvas, [zone_px], isClosed=True, color=(0, 0, 200), thickness=2)

    for p in persons:
        color = (0, 0, 255) if p["是否入侵"] else (0, 200, 0)
        x1, y1, x2, y2 = p["邊界框"]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        label = f"person {p['信心度']:.2f}" + ("（入侵）" if p["是否入侵"] else "")
        cv2.putText(canvas, label, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        cv2.circle(canvas, tuple(p["腳底參考點"]), 4, color, -1)
    return canvas

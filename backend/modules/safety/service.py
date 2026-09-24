"""M5 工安：危險區域入侵偵測（免訓練）+ PPE 安全帽偵測（Phase 5 監督式訓練）。

危險區域入侵：YOLO COCO 預訓練模型偵測人員 → 使用者在前端畫多邊形危險區域 →
判斷人員的腳底參考點是否落在區內。

PPE：用 Hard Hat Workers 資料集（CC0 1.0）訓練的 YOLO 模型判斷有沒有戴安全帽。
這個資料集只有 helmet／head 兩類，沒有反光背心類別，是資料集本身的限制。

Phase 11：單張圖片與短影片共用「純偵測（吃 BGR ndarray）」的部分（`_detect_intrusion_on_bgr`／
`_detect_ppe_on_bgr`），影片逐幀抽樣呼叫同一份偵測邏輯，不重寫一份。
"""

import json
import os
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "safety"
PPE_MODULE = "ppe"

WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "models" / "yolo" / "yolo11n.pt"
PPE_WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "models" / "ppe" / "ppe_yolo11n" / "weights" / "best.pt"
PERSON_CLASS_ID = 0
CONF_THRESHOLD = 0.4

DEFAULT_SAMPLE_INTERVAL_S = 1.0
DEFAULT_MAX_DURATION_S = 60.0
VIDEO_THUMBNAIL_MAX_SIDE = 320

_model = None
_ppe_model = None


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


def _detect_intrusion_on_bgr(bgr: np.ndarray, zone_px: np.ndarray | None) -> tuple[list[dict], bool, np.ndarray]:
    """單張圖片與影片逐幀共用：回傳 (人員明細, 是否有人入侵, 標註圖)。"""
    persons = _detect_persons(bgr)
    for p in persons:
        p["是否入侵"] = bool(zone_px is not None and _point_in_zone(p["腳底參考點"], zone_px))
    annotated = _draw_annotations(bgr, persons, zone_px)
    return persons, any(p["是否入侵"] for p in persons), annotated


def detect_intrusion(image_bytes: bytes, zone_json: str | None) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    zone_px = _parse_zone(zone_json, image.width, image.height) if zone_json else None
    persons, any_intrusion, annotated = _detect_intrusion_on_bgr(bgr, zone_px)

    if zone_px is None:
        verdict = "INFO"
    else:
        verdict = "NG" if any_intrusion else "OK"

    result = [{"偵測到人數": len(persons), "危險區域": zone_px is not None, "明細": persons}]
    return record_result(MODULE, verdict, result, "yolo11n-coco", started, bgr_to_data_url(annotated))


def _max_video_mb() -> int:
    return int(os.environ.get("MAX_VIDEO_MB", "200"))


def _sample_video_frames(video_bytes: bytes, sample_interval_s: float, max_duration_s: float):
    """把影片寫到暫存檔（cv2.VideoCapture 沒辦法直接吃記憶體 bytes），
    每隔 sample_interval_s 秒抓一幀，最多抓到 max_duration_s 秒為止（影片長度上限）。"""
    max_mb = _max_video_mb()
    size_mb = len(video_bytes) / (1024 * 1024)
    if size_mb > max_mb:
        raise ModuleError(f"影片檔過大（{size_mb:.1f}MB），上限 {max_mb}MB", 413)
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(video_bytes)
        tmp.flush()
        cap = cv2.VideoCapture(tmp.name)
        if not cap.isOpened():
            raise ModuleError("無法讀取影片，請確認是合法的影片檔（mp4 等）", 400)
        try:
            t = 0.0
            while t <= max_duration_s:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if not ok:
                    break
                yield t, frame
                t += sample_interval_s
        finally:
            cap.release()


def _thumbnail_data_url(bgr: np.ndarray) -> str:
    h, w = bgr.shape[:2]
    scale = VIDEO_THUMBNAIL_MAX_SIDE / max(h, w)
    if scale < 1:
        bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)))
    return bgr_to_data_url(bgr)


def detect_intrusion_video(
    video_bytes: bytes,
    zone_json: str | None,
    sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
) -> InspectionResult:
    started = time.perf_counter()
    zone_px = None
    violations = []
    n_frames = 0
    representative_annotated = None
    first_violation_annotated = None

    for t, frame in _sample_video_frames(video_bytes, sample_interval_s, max_duration_s):
        n_frames += 1
        if zone_px is None and zone_json:
            zone_px = _parse_zone(zone_json, frame.shape[1], frame.shape[0])
        persons, any_intrusion, annotated = _detect_intrusion_on_bgr(frame, zone_px)
        representative_annotated = annotated
        if any_intrusion:
            violations.append({
                "時間秒": round(t, 1), "偵測到人數": len(persons), "標註圖": _thumbnail_data_url(annotated),
            })
            if first_violation_annotated is None:
                first_violation_annotated = annotated

    if n_frames == 0:
        raise ModuleError("影片讀不到任何幀，請確認檔案完整", 400)

    verdict = "NG" if violations else ("INFO" if zone_px is None else "OK")
    item = {
        "取樣幀數": n_frames, "取樣間隔秒": sample_interval_s, "影片秒數上限": max_duration_s,
        "危險區域": zone_px is not None, "違規時間點": violations,
    }
    final_annotated = first_violation_annotated if first_violation_annotated is not None else representative_annotated
    return record_result(MODULE, verdict, [item], "yolo11n-coco-video", started, bgr_to_data_url(final_annotated))


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


def _get_ppe_model():
    global _ppe_model
    if _ppe_model is None:
        if not PPE_WEIGHTS_PATH.exists():
            raise ModuleError(
                f"找不到 PPE 安全帽偵測權重 {PPE_WEIGHTS_PATH}，請先執行 "
                "`python scripts/prepare_hardhat.py` 準備資料，再訓練 "
                "`YOLO('yolo11n.pt').train(data='data/hardhat_yolo/data.yaml', ...)`（見 CLAUDE.md）",
                503,
            )
        from ultralytics import YOLO

        _ppe_model = YOLO(str(PPE_WEIGHTS_PATH))
    return _ppe_model


def _detect_ppe_on_bgr(bgr: np.ndarray) -> tuple[list[dict], int, np.ndarray]:
    """單張圖片與影片逐幀共用：回傳 (偵測明細, 未戴安全帽數, 標註圖)。"""
    model = _get_ppe_model()
    results = model.predict(bgr, conf=CONF_THRESHOLD, verbose=False)

    detections = []
    for box in results[0].boxes:
        cls_name = model.names[int(box.cls[0])]  # "helmet" 或 "head"
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "類型": "已戴安全帽" if cls_name == "helmet" else "未戴安全帽",
            "信心度": round(float(box.conf[0]), 3),
            "邊界框": [round(x1), round(y1), round(x2), round(y2)],
        })
    n_no_helmet = sum(1 for d in detections if d["類型"] == "未戴安全帽")
    annotated = _draw_ppe_annotations(bgr, detections)
    return detections, n_no_helmet, annotated


def detect_ppe(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    detections, n_no_helmet, annotated = _detect_ppe_on_bgr(bgr)
    verdict = "NG" if n_no_helmet > 0 else ("OK" if detections else "INFO")

    item = {"偵測到人頭數": len(detections), "未戴安全帽數": n_no_helmet, "明細": detections}
    return record_result(PPE_MODULE, verdict, [item], "yolo11n-hardhat", started, bgr_to_data_url(annotated))


def detect_ppe_video(
    video_bytes: bytes,
    sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
) -> InspectionResult:
    started = time.perf_counter()
    violations = []
    n_frames = 0
    representative_annotated = None
    first_violation_annotated = None

    for t, frame in _sample_video_frames(video_bytes, sample_interval_s, max_duration_s):
        n_frames += 1
        detections, n_no_helmet, annotated = _detect_ppe_on_bgr(frame)
        representative_annotated = annotated
        if n_no_helmet > 0:
            violations.append({
                "時間秒": round(t, 1), "未戴安全帽數": n_no_helmet, "標註圖": _thumbnail_data_url(annotated),
            })
            if first_violation_annotated is None:
                first_violation_annotated = annotated

    if n_frames == 0:
        raise ModuleError("影片讀不到任何幀，請確認檔案完整", 400)

    verdict = "NG" if violations else "OK"
    item = {
        "取樣幀數": n_frames, "取樣間隔秒": sample_interval_s, "影片秒數上限": max_duration_s,
        "違規時間點": violations,
    }
    final_annotated = first_violation_annotated if first_violation_annotated is not None else representative_annotated
    return record_result(PPE_MODULE, verdict, [item], "yolo11n-hardhat-video", started, bgr_to_data_url(final_annotated))


def _draw_ppe_annotations(bgr: np.ndarray, detections: list[dict]) -> np.ndarray:
    canvas = bgr.copy()
    for d in detections:
        color = (0, 200, 0) if d["類型"] == "已戴安全帽" else (0, 0, 255)
        x1, y1, x2, y2 = d["邊界框"]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, f"{d['類型']} {d['信心度']:.2f}", (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
    return canvas


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

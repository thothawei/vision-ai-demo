"""M6 監督式瑕疵偵測：PCB 表面瑕疵（open/short/mousebite/spur/copper/pin-hole）。

跟 M3（PatchCore，非監督、只需良品）不同，這裡是監督式：訓練時需要標註好瑕疵位置與類型的
NG 樣本（DeepPCB 資料集），換來的是「除了 OK/NG 還能講出是哪一種瑕疵、在哪個位置」。
權重由 scripts/train_pcb_defect.py（實際上是直接呼叫 ultralytics YOLO().train()，
見 CLAUDE.md）訓練，data/deeppcb_yolo/ 由 scripts/prepare_deeppcb.py 從官方資料轉換而來。
"""

import time
from pathlib import Path

import cv2
import numpy as np

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "defect"

WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "models" / "defect" / "pcb_yolo11n" / "weights" / "best.pt"
CONF_THRESHOLD = 0.4

_model = None

# DeepPCB 官方類別（英文代號 → 中文說明），對應 scripts/prepare_deeppcb.py 的 CLASS_NAMES 順序
CLASS_NAMES_ZH = {
    "open": "斷路 open",
    "short": "短路 short",
    "mousebite": "缺口 mousebite",
    "spur": "毛刺 spur",
    "copper": "多餘銅箔 spurious copper",
    "pin-hole": "針孔 pin-hole",
}


def _get_model():
    global _model
    if _model is None:
        if not WEIGHTS_PATH.exists():
            raise ModuleError(
                f"找不到 PCB 瑕疵偵測權重 {WEIGHTS_PATH}，請先執行 "
                "`python scripts/prepare_deeppcb.py` 準備資料，再訓練 "
                "`YOLO('yolo11n.pt').train(data='data/deeppcb_yolo/data.yaml', ...)`（見 CLAUDE.md）",
                503,
            )
        from ultralytics import YOLO

        _model = YOLO(str(WEIGHTS_PATH))
    return _model


def detect_pcb_defects(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    model = _get_model()
    results = model.predict(bgr, conf=CONF_THRESHOLD, verbose=False)

    defects = []
    for box in results[0].boxes:
        cls_name = model.names[int(box.cls[0])]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        defects.append({
            "瑕疵類型": CLASS_NAMES_ZH.get(cls_name, cls_name),
            "信心度": round(float(box.conf[0]), 3),
            "邊界框": [round(x1), round(y1), round(x2), round(y2)],
        })

    annotated = _draw_annotations(bgr, defects)
    verdict = "NG" if defects else "OK"
    item = {"偵測到瑕疵數": len(defects), "明細": defects}

    return record_result(MODULE, verdict, [item], "yolo11n-deeppcb", started, bgr_to_data_url(annotated))


def _draw_annotations(bgr: np.ndarray, defects: list[dict]) -> np.ndarray:
    canvas = bgr.copy()
    for d in defects:
        x1, y1, x2, y2 = d["邊界框"]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 0, 255), 2)
        label = f"{d['瑕疵類型']} {d['信心度']:.2f}"
        cv2.putText(canvas, label, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    return canvas

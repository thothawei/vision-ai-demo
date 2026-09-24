"""M7 銘牌／儀表讀值：銘牌 OCR+LLM 結構化、七段顯示器判讀、指針錶讀值。"""

import time

import cv2
from pydantic import ValidationError

from core import llm
from core.gauge import angle_to_value, detect_needle_angle, find_center
from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError
from core.seven_segment import decode as decode_seven_segment
from schemas.nameplate import Nameplate

MODULE = "nameplate"

NAMEPLATE_PROMPT_TEMPLATE = """以下是從一張機台銘牌（nameplate）OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請整理成這個結構的 JSON（只回傳 JSON，不要多餘文字）：

{{
  "廠牌": "...", "型號": "...", "序號": "...", "製造日期": "...", "電壓": "..."
}}

原文中找不到的欄位填空字串 ""，不要自己編造。內容只能照抄原文，不能翻譯或改寫。

原始 OCR 文字如下：
---
{ocr_text}
---
"""


def read_nameplate(image_bytes: bytes) -> InspectionResult:
    from core import ocr as rapid_ocr

    started = time.perf_counter()
    image = load_image(image_bytes)

    ocr_text = rapid_ocr.extract_text(image)
    if not ocr_text.strip():
        raise ModuleError("OCR 沒有擷取到任何文字，請確認銘牌文字清楚可讀", 422)

    raw, engine = llm.generate_json(NAMEPLATE_PROMPT_TEMPLATE.format(ocr_text=ocr_text))
    try:
        model = Nameplate.model_validate(raw)
        item = model.model_dump()
        verdict = "OK"
    except ValidationError as e:
        item = {"_驗證錯誤": [{"欄位": ".".join(str(p) for p in err["loc"]), "問題": err["msg"]} for err in e.errors()],
                "LLM原始回傳": raw}
        verdict = "NG"
    item["_ocr原始文字"] = ocr_text

    return record_result(MODULE, verdict, [item], f"rapidocr+{engine}", started)


def read_seven_segment(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    text, details = decode_seven_segment(bgr)
    if not text:
        raise ModuleError("畫面中找不到七段顯示器的數字，請確認對比明顯、數字清楚", 422)

    annotated = _draw_seven_segment_boxes(bgr, details)
    has_unknown = "?" in text
    verdict = "NG" if has_unknown else "OK"
    item = {"讀值": text, "明細": details}
    if has_unknown:
        item["備註"] = "有字元判讀不出來（顯示為 ?），可能對比不夠或數字被遮擋"

    return record_result(MODULE, verdict, [item], "opencv-sevenseg", started, bgr_to_data_url(annotated))


def _draw_seven_segment_boxes(bgr, details: list[dict]):
    canvas = bgr.copy()
    for d in details:
        x, y, w, h = d["位置"]
        color = (0, 0, 255) if d["判讀"] == "?" else (0, 200, 0)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
        cv2.putText(canvas, d["判讀"], (x, max(y - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return canvas


def read_gauge(
    image_bytes: bytes,
    min_value: float,
    max_value: float,
    min_angle: float,
    max_angle: float,
    center_x: float | None,
    center_y: float | None,
) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    if center_x is not None and center_y is not None:
        cx, cy = center_x * image.width, center_y * image.height
        r = min(image.width, image.height) * 0.45
    else:
        found = find_center(gray)
        if found is None:
            raise ModuleError(
                "自動找不到錶面圓心，請用 center_x/center_y 參數手動指定（正規化座標 0~1）", 422
            )
        cx, cy, r = found

    angle, needle_len = detect_needle_angle(bgr, cx, cy, r)
    value = angle_to_value(angle, min_angle, max_angle, min_value, max_value)

    annotated = _draw_gauge_annotation(bgr, cx, cy, r, angle, needle_len)
    item = {
        "讀值": round(value, 2),
        "指針角度": round(angle, 1),
        "圓心": [round(cx), round(cy)],
        "半徑": round(r),
        "校正範圍": f"{min_value}~{max_value}（角度 {min_angle}~{max_angle}）",
    }
    return record_result(MODULE, "INFO", [item], "opencv-hough", started, bgr_to_data_url(annotated))


def _draw_gauge_annotation(bgr, cx: float, cy: float, r: float, angle: float, needle_len: float):
    import math

    canvas = bgr.copy()
    cv2.circle(canvas, (round(cx), round(cy)), round(r), (0, 200, 0), 2)
    cv2.circle(canvas, (round(cx), round(cy)), 5, (0, 0, 255), -1)
    end_x = cx + needle_len * math.cos(math.radians(angle))
    end_y = cy + needle_len * math.sin(math.radians(angle))
    cv2.line(canvas, (round(cx), round(cy)), (round(end_x), round(end_y)), (0, 0, 255), 3)
    return canvas

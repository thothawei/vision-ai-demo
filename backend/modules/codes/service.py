"""M1 追溯碼辨識：QR / 條碼 / DataMatrix / GS1 UDI。

zxing-cpp 對 GS1 條碼會自動輸出 (AI)值 的人類可讀格式（TextMode.HRI，預設值），
不需要自己處理 FNC1 分隔符號；這裡只需要解析 (AI)值 這個既有格式即可。
"""

import re
import time
from datetime import date, datetime

import cv2
import numpy as np
import zxingcpp

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult

MODULE = "codes"

# 常見 GS1 Application Identifier；只列本專案用得到的幾個，不是完整清單
GS1_AI_NAMES = {
    "01": "GTIN",
    "10": "批號",
    "17": "效期",
    "21": "序號",
}
EXPIRING_SOON_DAYS = 30


def decode_codes(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    barcodes = zxingcpp.read_barcodes(bgr)
    items = [describe_barcode(b) for b in barcodes]

    annotated = _draw_annotations(bgr, items)
    verdict = "NG" if any(i["效期狀態"] == "已過期" for i in items) else ("INFO" if not items else "OK")

    return record_result(MODULE, verdict, items, "zxing-cpp", started, bgr_to_data_url(annotated))


def describe_barcode(barcode: zxingcpp.Barcode) -> dict:
    is_gs1 = barcode.content_type == zxingcpp.ContentType.GS1
    gs1_fields = _parse_gs1(barcode.text) if is_gs1 else {}
    expiry_status, expiry_date = _check_expiry(gs1_fields.get("17"))

    item = {
        "類型": str(barcode.format),
        "內容": barcode.text,
        "是否為GS1": is_gs1,
        "四角座標": [[p.x, p.y] for p in (
            barcode.position.top_left, barcode.position.top_right,
            barcode.position.bottom_right, barcode.position.bottom_left,
        )],
        "效期狀態": expiry_status,
    }
    if gs1_fields:
        item["GS1欄位"] = {GS1_AI_NAMES.get(ai, ai): val for ai, val in gs1_fields.items()}
    if expiry_date:
        item["效期"] = expiry_date.isoformat()
    return item


def _parse_gs1(text: str) -> dict:
    """從 zxing-cpp 輸出的 (AI)值(AI)值... 格式解析出 {AI: 值}。"""
    return dict(re.findall(r"\((\d{2,4})\)([^(]*)", text))


def _check_expiry(raw_yymmdd: str | None) -> tuple[str, date | None]:
    """GS1 (17) 效期是 YYMMDD；沒有日期就回傳「不適用」，不猜測。"""
    if not raw_yymmdd or len(raw_yymmdd) != 6 or not raw_yymmdd.isdigit():
        return "不適用", None

    try:
        # GS1 規則：年份 00-50 → 20xx，51-99 → 19xx；製造業場景幾乎不會遇到後者
        yy, mm, dd = int(raw_yymmdd[:2]), int(raw_yymmdd[2:4]), int(raw_yymmdd[4:6])
        year = 2000 + yy if yy <= 50 else 1900 + yy
        # GS1 允許 dd=00 代表「當月最後一天」
        if dd == 0:
            next_month = date(year + (mm // 12), mm % 12 + 1, 1)
            expiry = next_month.fromordinal(next_month.toordinal() - 1)
        else:
            expiry = date(year, mm, dd)
    except ValueError:
        return "格式錯誤", None

    days_left = (expiry - date.today()).days
    if days_left < 0:
        return "已過期", expiry
    if days_left <= EXPIRING_SOON_DAYS:
        return "即將到期", expiry
    return "正常", expiry


_STATUS_COLOR_BGR = {
    "已過期": (0, 0, 255),
    "即將到期": (0, 200, 255),
    "格式錯誤": (0, 0, 255),
}
_DEFAULT_COLOR_BGR = (0, 200, 0)


def _draw_annotations(bgr: np.ndarray, items: list[dict]) -> np.ndarray:
    canvas = bgr.copy()
    for item in items:
        pts = np.array(item["四角座標"], dtype=np.int32)
        color = _STATUS_COLOR_BGR.get(item["效期狀態"], _DEFAULT_COLOR_BGR)
        cv2.polylines(canvas, [pts], isClosed=True, color=color, thickness=3)
        label = item["類型"]
        if item["效期狀態"] not in ("不適用",):
            label += f" / {item['效期狀態']}"
        cv2.putText(canvas, label, (pts[0][0], max(pts[0][1] - 10, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return canvas

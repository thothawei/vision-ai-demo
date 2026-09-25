"""M12 出貨標籤 vs 工單比對：出貨前檢核標籤上的料號/數量/批號是否貼錯。

重用 M1 的條碼解析（`describe_barcode`）跟 M4/M7 的 OCR→LLM 結構化模式：
RapidOCR 讀印刷文字 → LLM 整理成 {料號, 數量, 批號} → 跟「預期值」比對。

預期值來源優先順序：明確帶的 query 參數 > Phase 9 追溯資訊（X-Part-No/X-Lot-No header）。
批號如果標籤上也有 GS1 條碼，優先信任條碼解出來的 AI(10)（比 OCR 讀印刷字更精準）；
料號/數量沒有 GS1 標準對應欄位可以信任，一律用 OCR/LLM 抽取的值。
"""

import re
import time

import zxingcpp
from pydantic import ValidationError

from core import context, llm
from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError
from modules.codes.service import describe_barcode
from schemas.shipping_label import ShippingLabel

MODULE = "shipping"

LABEL_PROMPT_TEMPLATE = """以下是從一張出貨標籤 OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請整理成這個結構的 JSON（只回傳 JSON，不要多餘文字）：

{{
  "料號": "...", "數量": "...", "批號": "..."
}}

原文中找不到的欄位填空字串 ""，不要自己編造。內容只能照抄原文，不能翻譯或改寫。

原始 OCR 文字如下：
---
{ocr_text}
---
"""


def _normalize_code(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().upper()


def _extract_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def _compare(expected: str | None, actual: str | None) -> bool | None:
    """兩邊都有值才比對；有一邊缺值回 None（沒辦法比對，不是「不一致」）。"""
    if expected is None or actual is None:
        return None
    return expected == actual


def check_shipping_label(
    image_bytes: bytes,
    expected_part_no: str | None,
    expected_lot_no: str | None,
    expected_quantity: int | None,
) -> InspectionResult:
    from core import ocr as rapid_ocr

    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    # 預期值優先順序：明確帶的參數 > Phase 9 追溯資訊（trace header）
    trace = context.get_trace()
    expected_part_no = expected_part_no or trace.get("part_no")
    expected_lot_no = expected_lot_no or trace.get("lot_no")

    ocr_text = rapid_ocr.extract_text(image)
    if not ocr_text.strip():
        raise ModuleError("OCR 沒有擷取到任何文字，請確認標籤文字清楚可讀", 422)

    raw, llm_engine = llm.generate_json(LABEL_PROMPT_TEMPLATE.format(ocr_text=ocr_text))
    try:
        label = ShippingLabel.model_validate(raw)
    except ValidationError as e:
        item = {
            "_驗證錯誤": [{"欄位": ".".join(str(p) for p in err["loc"]), "問題": err["msg"]} for err in e.errors()],
            "LLM原始回傳": raw, "_ocr原始文字": ocr_text,
        }
        return record_result(MODULE, "NG", [item], f"zxing-cpp+rapidocr+{llm_engine}", started, bgr_to_data_url(bgr))

    # 批號：標籤上如果也有 GS1 條碼，優先信任條碼解出來的值（比 OCR 讀印刷字精準）
    barcodes = zxingcpp.read_barcodes(bgr)
    gs1_items = [describe_barcode(b) for b in barcodes if b.content_type == zxingcpp.ContentType.GS1]
    barcode_lot_no = gs1_items[0].get("GS1欄位", {}).get("批號") if gs1_items else None
    actual_lot_no = _normalize_code(barcode_lot_no) or _normalize_code(label.批號)

    actual_part_no = _normalize_code(label.料號)
    actual_quantity = _extract_int(label.數量)

    part_no_match = _compare(_normalize_code(expected_part_no), actual_part_no)
    lot_no_match = _compare(_normalize_code(expected_lot_no), actual_lot_no)
    quantity_match = _compare(expected_quantity, actual_quantity)

    checks = [("料號", part_no_match), ("批號", lot_no_match), ("數量", quantity_match)]
    mismatches = [name for name, ok in checks if ok is False]
    any_compared = any(ok is not None for _, ok in checks)

    if mismatches:
        verdict = "NG"
    elif any_compared:
        verdict = "OK"
    else:
        verdict = "INFO"  # 沒有任何預期值可比對（沒帶追溯資訊也沒手動輸入），純粹讀出標籤內容

    item = {
        "標籤料號": label.料號 or None, "預期料號": expected_part_no, "料號一致": part_no_match,
        "標籤批號": actual_lot_no, "批號來源": "條碼" if barcode_lot_no else ("OCR" if label.批號 else None),
        "預期批號": expected_lot_no, "批號一致": lot_no_match,
        "標籤數量": actual_quantity, "預期數量": expected_quantity, "數量一致": quantity_match,
        "問題": mismatches if mismatches else None,
        "_ocr原始文字": ocr_text,
    }
    engine = f"zxing-cpp+rapidocr+{llm_engine}"
    return record_result(MODULE, verdict, [item], engine, started, bgr_to_data_url(bgr))

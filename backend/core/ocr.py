"""RapidOCR 文字擷取 + RapidTable 表格結構辨識（延遲載入、常駐記憶體）。

Phase 4 用 RapidOCR 取代 Tesseract 當主要 OCR 引擎（原因見 docs/licenses.md 的
PaddleOCR 評估紀錄：py3.11 環境下 PaddleOCR 的相依解析會被拖回舊版）；
Tesseract 保留當比較選項（core/tesseract_ocr.py）。
"""

import numpy as np
from PIL import Image

_ocr_engine = None
_table_engine = None


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _get_table_engine():
    global _table_engine
    if _table_engine is None:
        from rapid_table import RapidTable

        _table_engine = RapidTable()
    return _table_engine


def extract_text(image: Image.Image) -> str:
    """回傳依讀取順序（由上而下）串接的純文字，一行一個偵測框。"""
    result = _get_ocr_engine()(np.array(image))
    if not result.txts:
        return ""
    return "\n".join(result.txts)


def extract_text_and_table(image: Image.Image) -> tuple[str, str | None]:
    """回傳 (純文字, 表格 HTML 或 None)。表格辨識抓不到表格結構時回傳 None，不硬塞假表格。"""
    arr = np.array(image)
    ocr_result = _get_ocr_engine()(arr)
    if not ocr_result.txts:
        return "", None

    text = "\n".join(ocr_result.txts)

    try:
        table_result = _get_table_engine()(arr, ocr_results=[(ocr_result.boxes, ocr_result.txts, ocr_result.scores)])
        html = table_result.pred_htmls[0] if table_result.pred_htmls else None
    except Exception:
        # 表格辨識是輔助資訊，失敗時退回純文字，不讓整個請求失敗
        html = None

    return text, html

"""M4 製造文件結構化（Phase 1：沿用原本的 Tesseract 兩段式與端到端模式，改走 LLM 抽象層）。

Phase 4 會改成 RapidOCR + 預定義文件 schema + Pydantic 驗證。
"""

import time

import pytesseract

from core import llm
from core.image_io import load_image
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "docs"

STRUCTURE_PROMPT_TEMPLATE = """以下是從一份文件 OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請判斷這是什麼類型的文件（例如：工單、出貨單、檢驗報告、報價單、發票、名片、一般文件），
並把內容整理成結構化 JSON，只回傳 JSON，格式如下：

{{
  "文件類型": "判斷出的文件類型",
  "欄位": {{ "依文件類型自行決定欄位名稱與值，例如出貨單就是 單號/客戶/日期/品項/總額" }},
  "原始文字": "保留清理過的原始文字，供人工核對"
}}

數字與編號只能照抄原文，原文沒有的欄位不要自己編。

原始 OCR 文字如下：
---
{ocr_text}
---
"""

END_TO_END_PROMPT = """這是一份文件或表單的圖片。請直接判斷文件類型，並把內容整理成結構化 JSON，
只回傳 JSON，格式如下：

{
  "文件類型": "判斷出的文件類型",
  "欄位": { "依文件類型自行決定欄位名稱與值" },
  "原始文字": "你在圖片中讀到的完整文字"
}

數字與編號只能照抄圖片上的內容，看不到的欄位不要自己編。
"""


def extract_document(image_bytes: bytes, mode: str) -> InspectionResult:
    if mode not in ("ocr", "end_to_end"):
        raise ModuleError(f"mode 只能是 ocr 或 end_to_end，目前是「{mode}」", 400)

    started = time.perf_counter()
    image = load_image(image_bytes)

    if mode == "end_to_end":
        result, engine = llm.generate_json(END_TO_END_PROMPT, image)
        return record_result(MODULE, "INFO", [result], engine, started)

    ocr_text = pytesseract.image_to_string(image, lang="chi_tra+eng")
    if not ocr_text.strip():
        raise ModuleError("OCR 沒有擷取到任何文字，建議改用端到端模式", 422)

    result, engine = llm.generate_json(STRUCTURE_PROMPT_TEMPLATE.format(ocr_text=ocr_text))
    result["_ocr原始文字"] = ocr_text
    return record_result(MODULE, "INFO", [result], f"tesseract+{engine}", started)

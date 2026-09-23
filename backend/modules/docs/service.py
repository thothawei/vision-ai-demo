"""M4 製造文件結構化。

三種模式：
- ocr（預設）：RapidOCR 擷取文字（+ 表格結構），LLM 只做「文字 → JSON」
- tesseract：跟 ocr 相同流程，只是 OCR 引擎換成 Tesseract，留著跟 RapidOCR 比較準確度
- end_to_end：圖片直接丟給 LLM，跳過 OCR，沒有獨立的 OCR 原文可以核對數字來源

工單／出貨單／進料檢驗報告有嚴格的 Pydantic schema（backend/schemas/documents.py）：
LLM 給的數字都要附上「這是從原文哪裡抄的」，service 層會去比對這段原文是否真的存在於
OCR 文字裡，比對不到就標記「來源可疑」，不會照單全收把 LLM 可能捏造的數字當真。
Pydantic 驗證失敗時回傳完整的錯誤欄位列表，不會硬塞預設值掩蓋問題。
"""

import time

from pydantic import ValidationError

from core import llm
from core.image_io import load_image
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError
from schemas.documents import DOC_TYPE_SCHEMAS, STRICT_DOC_TYPES

MODULE = "docs"

CLASSIFY_PROMPT_TEMPLATE = """以下是從一份文件 OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請判斷這是什麼類型的文件，只能從這幾種裡面選一個：工單、出貨單、進料檢驗報告、報價單、名片、其他。
只回傳 JSON：{{"文件類型": "你的判斷"}}

原始 OCR 文字如下：
---
{ocr_text}
---
"""

FREEFORM_PROMPT_TEMPLATE = """以下是從一份「{doc_type}」文件 OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請把內容整理成結構化 JSON，只回傳 JSON，格式如下：

{{
  "文件類型": "{doc_type}",
  "欄位": {{ "依文件類型自行決定欄位名稱與值" }},
  "原始文字": "保留清理過的原始文字，供人工核對"
}}

數字與編號只能照抄原文，原文沒有的欄位不要自己編。

原始 OCR 文字如下：
---
{ocr_text}
---
"""

FREEFORM_END_TO_END_PROMPT = """這是一份文件或表單的圖片。請直接判斷文件類型，並把內容整理成結構化 JSON，
只回傳 JSON，格式如下：

{
  "文件類型": "判斷出的文件類型",
  "欄位": { "依文件類型自行決定欄位名稱與值" },
  "原始文字": "你在圖片中讀到的完整文字"
}

數字與編號只能照抄圖片上的內容，看不到的欄位不要自己編。
"""

_STRICT_SCHEMA_INSTRUCTIONS = {
    "工單": """{
  "工單號": "...", "料號": "...", "品名": "...",
  "數量": {"值": 數字, "原文片段": "這個數字在原文中對應的片段，逐字照抄"},
  "開工日": "...", "完工日": "...", "製程站別": "..."
}""",
    "出貨單": """{
  "單號": "...", "客戶": "...", "日期": "...",
  "品項": [
    {"料號": "...", "品名": "...",
     "數量": {"值": 數字, "原文片段": "逐字照抄"},
     "單價": {"值": 數字, "原文片段": "逐字照抄"}}
  ],
  "總額": {"值": 數字, "原文片段": "逐字照抄"}
}""",
    "進料檢驗報告": """{
  "供應商": "...", "料號": "...", "批號": "...",
  "抽樣數": {"值": 數字, "原文片段": "逐字照抄"},
  "不良數": {"值": 數字, "原文片段": "逐字照抄"},
  "判定": "合格 或 不合格"
}""",
}

STRICT_PROMPT_FROM_TEXT_TEMPLATE = """以下是從一份「{doc_type}」OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
{table_section}
請把內容整理成符合這個結構的 JSON（只回傳 JSON，不要多餘文字）：
{schema_example}

規則：
1. 所有數字欄位（如數量、單價、總額、抽樣數、不良數）都要用 {{"值": 數字, "原文片段": "..."}} 的格式，
   "原文片段" 必須是原文中真實存在的一小段文字，逐字照抄，不能自己編造或改寫。
2. 原文中找不到的欄位，文字欄位填空字串 ""，數字欄位的「原文片段」也填空字串 ""，不要瞎猜。
3. 「判定」欄位只能是「合格」或「不合格」，原文有寫不良數大於 0 或明確標示不合格才填「不合格」。

原始 OCR 文字如下：
---
{ocr_text}
---
"""

STRICT_PROMPT_FROM_IMAGE_TEMPLATE = """這是一份「{doc_type}」文件的圖片。請把內容整理成符合這個結構的 JSON
（只回傳 JSON，不要多餘文字）：
{schema_example}

規則：
1. 所有數字欄位都要用 {{"值": 數字, "原文片段": "..."}} 的格式，"原文片段" 是你在圖片上實際看到的文字，逐字照抄。
2. 圖片上看不到的欄位，文字欄位填空字串 ""，數字欄位的「原文片段」也填空字串 ""，不要瞎猜。
3. 「判定」欄位只能是「合格」或「不合格」。
"""


def extract_document(image_bytes: bytes, mode: str) -> InspectionResult:
    if mode not in ("ocr", "tesseract", "end_to_end"):
        raise ModuleError(f"mode 只能是 ocr、tesseract 或 end_to_end，目前是「{mode}」", 400)

    started = time.perf_counter()
    image = load_image(image_bytes)

    if mode == "end_to_end":
        return _extract_end_to_end(image, started)
    return _extract_via_ocr(image, mode, started)


def _extract_via_ocr(image, mode: str, started: float) -> InspectionResult:
    table_html = None
    if mode == "tesseract":
        from core import tesseract_ocr

        ocr_text = tesseract_ocr.extract_text(image)
        ocr_engine_name = "tesseract"
    else:
        from core import ocr as rapid_ocr

        ocr_text, table_html = rapid_ocr.extract_text_and_table(image)
        ocr_engine_name = "rapidocr"

    if not ocr_text.strip():
        raise ModuleError("OCR 沒有擷取到任何文字，建議改用端到端模式", 422)

    doc_type, _ = _classify_from_text(ocr_text)

    if doc_type in STRICT_DOC_TYPES:
        item, extract_engine = _extract_strict_from_text(doc_type, ocr_text, table_html)
    else:
        result, extract_engine = llm.generate_json(
            FREEFORM_PROMPT_TEMPLATE.format(doc_type=doc_type, ocr_text=ocr_text)
        )
        result["_ocr原始文字"] = ocr_text
        item = result

    verdict = "NG" if item.get("_驗證錯誤") else "OK"
    engine = f"{ocr_engine_name}+{extract_engine}"
    return record_result(MODULE, verdict, [item], engine, started)


def _extract_end_to_end(image, started: float) -> InspectionResult:
    doc_type, _ = _classify_from_image(image)

    if doc_type in STRICT_DOC_TYPES:
        item, extract_engine = _extract_strict_from_image(doc_type, image)
    else:
        item, extract_engine = llm.generate_json(FREEFORM_END_TO_END_PROMPT, image)

    verdict = "NG" if item.get("_驗證錯誤") else "OK"
    return record_result(MODULE, verdict, [item], extract_engine, started)


def _classify_from_text(ocr_text: str) -> tuple[str, str]:
    result, engine = llm.generate_json(CLASSIFY_PROMPT_TEMPLATE.format(ocr_text=ocr_text))
    return result.get("文件類型", "其他"), engine


def _classify_from_image(image) -> tuple[str, str]:
    result, engine = llm.generate_json(
        '這是一份文件的圖片。判斷這是什麼類型的文件，只能從這幾種裡面選一個：'
        '工單、出貨單、進料檢驗報告、報價單、名片、其他。只回傳 JSON：{"文件類型": "你的判斷"}',
        image,
    )
    return result.get("文件類型", "其他"), engine


def _extract_strict_from_text(doc_type: str, ocr_text: str, table_html: str | None) -> tuple[dict, str]:
    table_section = (
        f"以下是版面分析抓到的表格結構（HTML，可能不完全準確，只當輔助參考）：\n{table_html}\n"
        if table_html else ""
    )
    prompt = STRICT_PROMPT_FROM_TEXT_TEMPLATE.format(
        doc_type=doc_type,
        table_section=table_section,
        schema_example=_STRICT_SCHEMA_INSTRUCTIONS[doc_type],
        ocr_text=ocr_text,
    )
    raw, engine = llm.generate_json(prompt)
    return _validate_and_check_sources(doc_type, raw, ocr_text), engine


def _extract_strict_from_image(doc_type: str, image) -> tuple[dict, str]:
    prompt = STRICT_PROMPT_FROM_IMAGE_TEMPLATE.format(
        doc_type=doc_type, schema_example=_STRICT_SCHEMA_INSTRUCTIONS[doc_type]
    )
    raw, engine = llm.generate_json(prompt, image)
    # 端到端模式沒有獨立的 OCR 原文可以核對「原文片段」是否真實存在，這裡誠實標記，不假裝驗證過
    return _validate_and_check_sources(doc_type, raw, source_text=None), engine


def _validate_and_check_sources(doc_type: str, raw: dict, source_text: str | None) -> dict:
    schema_cls = DOC_TYPE_SCHEMAS[doc_type]
    try:
        model = schema_cls.model_validate(raw)
    except ValidationError as e:
        return {
            "文件類型": doc_type,
            "_驗證錯誤": [{"欄位": ".".join(str(p) for p in err["loc"]), "問題": err["msg"]} for err in e.errors()],
            "LLM原始回傳": raw,
        }

    item = {"文件類型": doc_type, **model.model_dump()}
    _annotate_source_verification(item, source_text)
    return item


def _annotate_source_verification(node, source_text: str | None):
    """遞迴走過結構，幫每個 {值, 原文片段} 加一個「來源驗證」欄位。"""
    if isinstance(node, dict):
        if set(node.keys()) == {"值", "原文片段"}:
            snippet = node["原文片段"]
            if source_text is None:
                node["來源驗證"] = "無法驗證（端到端模式沒有獨立 OCR 原文）"
            elif not snippet:
                node["來源驗證"] = "LLM 未提供原文片段"
            elif snippet in source_text:
                node["來源驗證"] = "OK：原文中找得到這段文字"
            else:
                node["來源驗證"] = "可疑：原文中找不到這段文字，數字可能是 LLM 捏造的"
            return
        for v in node.values():
            _annotate_source_verification(v, source_text)
    elif isinstance(node, list):
        for v in node:
            _annotate_source_verification(v, source_text)

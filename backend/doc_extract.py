"""文件/圖檔轉結構化資料：Tesseract OCR 擷取文字 + Gemini 整理成 JSON。
也提供「端到端模式」：直接把圖片丟給 Gemini 辨識（跳過 OCR），適合手寫或複雜版面。
"""

import io
import json
import os

import pytesseract
from google import genai
from google.genai import types
from PIL import Image

MODEL_NAME = "gemini-3.6-flash"

STRUCTURE_PROMPT_TEMPLATE = """以下是從一份文件 OCR 掃描出來的原始文字，可能包含雜訊或斷行錯誤。
請判斷這是什麼類型的文件（例如：發票、收據、名片、表格、一般文件），
並把內容整理成結構化 JSON，只回傳 JSON（不要 markdown code fence），格式如下：

{{
  "文件類型": "判斷出的文件類型",
  "欄位": {{ "依文件類型自行決定欄位名稱與值，例如發票就是 品項/單價/數量/總金額/日期" }},
  "原始文字": "保留清理過的原始文字，供人工核對"
}}

原始 OCR 文字如下：
---
{ocr_text}
---
"""

END_TO_END_PROMPT = """這是一份文件或表單的圖片。請直接判斷文件類型，並把內容整理成結構化 JSON，
只回傳 JSON（不要 markdown code fence），格式如下：

{
  "文件類型": "判斷出的文件類型",
  "欄位": { "依文件類型自行決定欄位名稱與值" },
  "原始文字": "你在圖片中讀到的完整文字"
}
"""


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY，請在 .env 設定")
    return genai.Client(api_key=api_key)


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"文件類型": "解析失敗", "欄位": {}, "原始文字": text}


def extract_via_ocr(image_bytes: bytes) -> dict:
    """兩段式：Tesseract 先擷取文字，再交給 Gemini 結構化。"""
    image = Image.open(io.BytesIO(image_bytes))
    ocr_text = pytesseract.image_to_string(image, lang="chi_tra+eng")

    if not ocr_text.strip():
        return {"文件類型": "無法辨識", "欄位": {}, "原始文字": "OCR 沒有擷取到任何文字，建議改用端到端模式"}

    client = _get_client()
    prompt = STRUCTURE_PROMPT_TEMPLATE.format(ocr_text=ocr_text)
    response = client.models.generate_content(model=MODEL_NAME, contents=[prompt])

    result = _parse_json_response(response.text)
    result["_ocr原始文字"] = ocr_text
    return result


def extract_end_to_end(image_bytes: bytes, mime_type: str) -> dict:
    """端到端模式：圖片直接丟給 Gemini，跳過 Tesseract。"""
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            END_TO_END_PROMPT,
        ],
    )
    return _parse_json_response(response.text)

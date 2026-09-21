"""街景照片通用辨識：丟一張照片給 Gemini，回傳開放式的「這是什麼」結果。"""

import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.6-flash"

SCAN_PROMPT = """你是一個街景照片辨識助手。仔細觀察這張照片，回答「這是什麼」。

請用繁體中文回覆，並且只回傳一個 JSON 物件（不要加 markdown code fence），格式如下：

{
  "主要物件": "照片中最主要的東西是什麼（例如店名、建築物名稱、商品名稱、物種等）",
  "類別": "大分類，例如：招牌店面、建築物、商品、動植物、交通工具、其他",
  "詳細描述": "更完整的描述，包含看到的文字、品牌、特徵等",
  "信心程度": "高／中／低，以及簡短說明為何"
}

如果照片中有多個明顯物件，"主要物件" 選最顯眼或最可能是使用者想問的那個，"詳細描述" 裡再補充其他物件。
"""


def scan_image(image_bytes: bytes, mime_type: str) -> dict:
    """呼叫 Gemini 辨識圖片內容，回傳解析後的 dict。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY，請在 .env 設定")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            SCAN_PROMPT,
        ],
    )

    return _parse_json_response(response.text)


def _parse_json_response(text: str) -> dict:
    """Gemini 有時會包 markdown code fence，這裡去掉再解析。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"主要物件": "解析失敗", "類別": "-", "詳細描述": text, "信心程度": "-"}

"""LLM 抽象層：LLM_ENGINE=ollama（預設，本機離線）或 gemini（免費層備援）。

模組只呼叫 generate_json()，不需要知道底層是哪個引擎。
"""

import json
import os

from PIL import Image

from core.image_io import resize_max, to_jpeg_bytes
from core.schemas import ModuleError

DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
# 送進 LLM 前的最長邊；太大只會拖慢本機推論，對辨識幫助有限
MAX_IMAGE_SIDE = 1600


def current_engine() -> str:
    engine = os.environ.get("LLM_ENGINE", "ollama").strip().lower()
    if engine not in ("ollama", "gemini"):
        raise ModuleError(f"LLM_ENGINE 只能是 ollama 或 gemini，目前是「{engine}」")
    return engine


def generate_json(prompt: str, image: Image.Image | None = None) -> tuple[dict, str]:
    """送出 prompt（可附一張圖），回傳 (解析後的 JSON dict, 引擎名稱)。"""
    image_bytes = to_jpeg_bytes(resize_max(image, MAX_IMAGE_SIDE)) if image else None

    if current_engine() == "gemini":
        text, engine_name = _call_gemini(prompt, image_bytes)
    else:
        text, engine_name = _call_ollama(prompt, image_bytes)

    return parse_json_text(text), engine_name


def parse_json_text(text: str) -> dict:
    """模型有時會包 markdown code fence，去掉再解析；解析失敗就明確報錯，不硬塞假資料。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ModuleError(f"LLM 回傳的不是合法 JSON，前 200 字：{text[:200]}", 502)
    if not isinstance(data, dict):
        raise ModuleError(f"LLM 回傳的 JSON 不是物件：{text[:200]}", 502)
    return data


def _call_ollama(prompt: str, image_bytes: bytes | None) -> tuple[str, str]:
    import ollama

    model = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    message = {"role": "user", "content": prompt}
    if image_bytes:
        message["images"] = [image_bytes]

    client = ollama.Client(timeout=float(os.environ.get("OLLAMA_TIMEOUT", "300")))
    try:
        response = client.chat(
            model=model,
            messages=[message],
            format="json",
            think=False,
            options={"temperature": 0},
            keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE", "5m"),
        )
    except ConnectionError:
        raise ModuleError("無法連到 Ollama，請確認已執行 `ollama serve`（或開啟 Ollama App）", 503)
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise ModuleError(f"Ollama 找不到模型 {model}，請先執行 `ollama pull {model}`", 503)
        raise ModuleError(f"Ollama 錯誤：{e.error}", 502)

    return response.message.content or "", f"ollama:{model}"


def _call_gemini(prompt: str, image_bytes: bytes | None) -> tuple[str, str]:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ModuleError("LLM_ENGINE=gemini 但缺少 GEMINI_API_KEY，請在 .env 設定")

    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    contents: list = [prompt]
    if image_bytes:
        contents.insert(0, types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    try:
        response = genai.Client(api_key=api_key).models.generate_content(model=model, contents=contents)
    except APIError as e:
        # 免費層 RPM=5 / RPD=20，配額錯誤要讓使用者看得到真正原因
        raise ModuleError(f"Gemini API 錯誤：{e.message}", 502)

    return response.text or "", f"gemini:{model}"

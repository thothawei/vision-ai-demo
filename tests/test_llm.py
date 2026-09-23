"""LLM 抽象層：引擎切換、JSON 解析、連線失敗時的錯誤訊息（不需要真的有模型）。"""

import pytest
from PIL import Image

from core import llm
from core.schemas import ModuleError


def test_parse_json_strips_code_fence():
    assert llm.parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize("text", ["不是 JSON", "[1, 2]"])
def test_parse_json_rejects_invalid_instead_of_faking(text):
    with pytest.raises(ModuleError) as e:
        llm.parse_json_text(text)
    assert e.value.status_code == 502


def test_invalid_engine(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "openai")
    with pytest.raises(ModuleError, match="只能是 ollama 或 gemini"):
        llm.generate_json("hi")


def test_ollama_unreachable_gives_clear_message(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # 沒有服務的埠
    with pytest.raises(ModuleError, match="ollama serve") as e:
        llm.generate_json("hi", Image.new("RGB", (10, 10)))
    assert e.value.status_code == 503


def test_ollama_missing_model_gives_pull_hint(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "no-such-model-xyz:1b")
    try:
        with pytest.raises(ModuleError, match="ollama pull no-such-model-xyz:1b"):
            llm.generate_json("hi")
    except ModuleError as e:
        if "ollama serve" in e.message:
            pytest.skip("本機 Ollama 沒有啟動")
        raise


def test_gemini_without_key(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ModuleError, match="GEMINI_API_KEY"):
        llm.generate_json("hi")

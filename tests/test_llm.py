"""LLM 抽象層：引擎切換、JSON 解析、連線失敗時的錯誤訊息（不需要真的有模型）。"""

import pytest
from core import llm
from core.schemas import ModuleError
from PIL import Image


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
    """Ollama 回 404（模型沒下載）要提示 pull 指令。用假 client，不依賴本機有沒有開 Ollama（CI 上沒有）。"""
    import ollama

    def fake_chat(self, *args, **kwargs):
        raise ollama.ResponseError("model not found", 404)

    monkeypatch.setenv("LLM_ENGINE", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "no-such-model-xyz:1b")
    monkeypatch.setattr(ollama.Client, "chat", fake_chat)
    with pytest.raises(ModuleError, match="ollama pull no-such-model-xyz:1b") as e:
        llm.generate_json("hi")
    assert e.value.status_code == 503


def test_gemini_without_key(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ModuleError, match="GEMINI_API_KEY"):
        llm.generate_json("hi")

"""實際呼叫本機 Ollama 的端到端測試：pytest -m live"""

import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")


def test_live_general_describe(client, ollama_env, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("sign.png", warning_sign_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    print("\n[M9 live]", body["engine"], body["elapsed_ms"], "ms", body["items"][0])
    assert body["engine"].startswith("ollama:")
    assert {"主要物件", "類別", "詳細描述", "信心程度"} <= set(body["items"][0])


@pytest.mark.parametrize("mode", ["ocr", "end_to_end"])
def test_live_docs_extract_work_order(client, ollama_env, work_order_png, mode):
    res = client.post("/api/docs/extract", params={"mode": mode},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print(f"\n[M4 live {mode}]", body["engine"], body["elapsed_ms"], "ms", item.get("文件類型"), item.get("欄位"))
    assert "文件類型" in item and "欄位" in item
    # 料號必須照抄原文，不能被模型改掉（工單號在 ocr 模式常被 Tesseract 誤讀，不拿它斷言）
    assert "SC-M6-20" in str(item["欄位"])

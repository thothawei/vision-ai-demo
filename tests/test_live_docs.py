"""M4 真的打本機 Ollama 跑完整兩段式流程（分類 + 結構化 + schema 驗證 + 來源核對）：pytest -m live"""

import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")


def test_live_work_order(client, ollama_env, work_order_png):
    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print("\n[M4 live 工單]", body["engine"], body["elapsed_ms"], "ms", item)
    assert item["文件類型"] == "工單"
    assert "驗證錯誤" not in str(item.get("_驗證錯誤", ""))
    # RapidOCR 對工單號讀取正確（不像 Tesseract 會把 0915 誤讀成 0215）
    assert item["工單號"] == "WO-2026-0915"
    assert item["數量"]["值"] == 5000
    assert item["數量"]["來源驗證"] == "OK：原文中找得到這段文字"


def test_live_shipping_order_with_table(client, ollama_env, shipping_order_png):
    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("so.png", shipping_order_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print("\n[M4 live 出貨單]", body["engine"], body["elapsed_ms"], "ms", item)
    assert item["文件類型"] == "出貨單"
    assert len(item["品項"]) == 2
    assert item["總額"]["值"] == 6500
    assert item["總額"]["來源驗證"] == "OK：原文中找得到這段文字"


def test_live_inspection_report(client, ollama_env, inspection_report_png):
    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("ir.png", inspection_report_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print("\n[M4 live 進料檢驗報告]", body["engine"], body["elapsed_ms"], "ms", item)
    assert item["文件類型"] == "進料檢驗報告"
    assert item["判定"] in ("合格", "不合格")
    assert item["抽樣數"]["值"] == 50
    assert item["不良數"]["值"] == 2

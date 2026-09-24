"""M8 醫療相關辨識：
- 包裝檢核：zxing-cpp + RapidOCR 真的跑，LLM 用假佇列
- 肺炎分類 demo：假模型（真實準確度見 CLAUDE.md 訓練紀錄，不在單元測試裡驗證）
"""

from datetime import date, timedelta


def test_packaging_match_gives_ok(client, fake_llm_queue, packaging_match_png):
    responses, calls = fake_llm_queue
    responses.append(({"批號": "LOT2026A", "效期": (date.today() + timedelta(days=200)).isoformat()},
                      "fake:model"))

    res = client.post("/api/medical/packaging-check", files={"file": ("p.png", packaging_match_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "medical_packaging"
    assert body["verdict"] == "OK"
    item = body["items"][0]
    assert item["批號一致"] is True
    assert item["效期一致"] is True
    assert item["問題"] is None
    assert calls[0]["has_image"] is False


def test_packaging_batch_mismatch_gives_ng(client, fake_llm_queue, packaging_match_png):
    responses, _ = fake_llm_queue
    responses.append(({"批號": "LOT9999X", "效期": (date.today() + timedelta(days=200)).isoformat()},
                      "fake:model"))

    res = client.post("/api/medical/packaging-check", files={"file": ("p.png", packaging_match_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    item = body["items"][0]
    assert item["批號一致"] is False
    assert item["效期一致"] is True
    assert item["問題"] == ["批號"]


def test_packaging_expiry_mismatch_gives_ng(client, fake_llm_queue, packaging_match_png):
    responses, _ = fake_llm_queue
    responses.append(({"批號": "LOT2026A", "效期": (date.today() + timedelta(days=999)).isoformat()},
                      "fake:model"))

    res = client.post("/api/medical/packaging-check", files={"file": ("p.png", packaging_match_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["效期一致"] is False


def test_packaging_no_printed_text_found_is_info(client, fake_llm_queue, packaging_match_png, monkeypatch):
    # RapidOCR 讀不到任何文字時（模擬），不該呼叫 LLM，也不該當成「不一致」
    monkeypatch.setattr("core.ocr.extract_text", lambda image: "")

    res = client.post("/api/medical/packaging-check", files={"file": ("p.png", packaging_match_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "INFO"
    assert body["items"][0]["印刷批號"] is None
    _, calls = fake_llm_queue
    assert calls == []


def test_packaging_no_barcode_found_rejected(client, warning_sign_png):
    res = client.post("/api/medical/packaging-check", files={"file": ("w.png", warning_sign_png, "image/png")})
    assert res.status_code == 422


def test_pneumonia_demo_returns_disclaimer(client, fake_pneumonia_model, warning_sign_png):
    res = client.post("/api/medical/pneumonia-demo", files={"file": ("x.png", warning_sign_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "medical_pneumonia_demo"
    assert body["verdict"] == "INFO"
    item = body["items"][0]
    assert item["警語"] == "僅供技術展示，非醫療診斷用途"
    assert item["分類"] == "pneumonia（肺炎樣態）"


def test_pneumonia_demo_missing_weights_gives_clear_error(client, warning_sign_png, monkeypatch, tmp_path):
    monkeypatch.setattr("modules.medical.service.WEIGHTS_PATH", tmp_path / "no_such.pt")
    res = client.post("/api/medical/pneumonia-demo", files={"file": ("x.png", warning_sign_png, "image/png")})

    assert res.status_code == 503
    assert "train_medmnist.py" in res.json()["detail"]

"""M9 開放式辨識、M4 文件結構化、檢驗紀錄的 API 測試（LLM 用假函式，不耗模型資源）。"""

from datetime import date

COMMON_KEYS = {"module", "verdict", "items", "annotated_image", "engine", "elapsed_ms", "inspection_id"}


def test_general_describe_returns_common_format_and_logs(client, fake_llm, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("sign.png", warning_sign_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == COMMON_KEYS
    assert body["module"] == "general"
    assert body["verdict"] == "INFO"
    assert body["engine"] == "fake:model"
    assert body["items"][0]["主要物件"] == "測試物件"
    assert fake_llm[0]["has_image"] is True

    logs = client.get("/api/inspections", params={"module": "general"}).json()
    assert [r["id"] for r in logs] == [body["inspection_id"]]
    assert logs[0]["summary"] == body["items"]


def test_docs_ocr_mode_passes_real_tesseract_text_to_llm(client, fake_llm, work_order_png):
    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "docs"
    assert body["engine"] == "tesseract+fake:model"
    # OCR 模式送給 LLM 的是文字，不是圖片；且 Tesseract 真的讀到了料號
    # （工單號 0915 常被 Tesseract 誤讀成 0215，屬已知限制，不拿它斷言）
    assert fake_llm[0]["has_image"] is False
    assert "SC-M6-20" in fake_llm[0]["prompt"]
    assert "SC-M6-20" in body["items"][0]["_ocr原始文字"]


def test_docs_end_to_end_sends_image(client, fake_llm, work_order_png):
    res = client.post("/api/docs/extract", params={"mode": "end_to_end"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.status_code == 200
    assert fake_llm[0]["has_image"] is True


def test_docs_blank_image_is_rejected_before_llm(client, fake_llm, blank_png):
    res = client.post("/api/docs/extract", files={"file": ("blank.png", blank_png, "image/png")})

    assert res.status_code == 422
    assert "端到端" in res.json()["detail"]
    assert fake_llm == []


def test_invalid_mode_empty_file_and_non_image(client, fake_llm, work_order_png):
    bad_mode = client.post("/api/docs/extract", params={"mode": "xyz"},
                           files={"file": ("wo.png", work_order_png, "image/png")})
    empty = client.post("/api/general/describe", files={"file": ("e.png", b"", "image/png")})
    not_image = client.post("/api/general/describe", files={"file": ("a.txt", b"hello", "text/plain")})

    assert bad_mode.status_code == 400
    assert empty.status_code == 400 and empty.json()["detail"] == "檔案是空的"
    assert not_image.status_code == 400 and "無法讀取圖片" in not_image.json()["detail"]
    assert fake_llm == []


def test_inspection_query_filters_and_csv(client):
    from core.inspection_log import log_inspection

    log_inspection("anomaly", "NG", "e", 10, [{"score": 0.9}])
    log_inspection("anomaly", "OK", "e", 11, [{"score": 0.1}])
    log_inspection("codes", "OK", "e", 12, [{"text": "中文"}])

    assert len(client.get("/api/inspections").json()) == 3
    ng = client.get("/api/inspections", params={"module": "anomaly", "verdict": "NG"}).json()
    assert [r["summary"] for r in ng] == [[{"score": 0.9}]]

    today = date.today().isoformat()
    assert len(client.get("/api/inspections", params={"date_from": today, "date_to": today}).json()) == 3
    assert client.get("/api/inspections", params={"date_to": "2000-01-01"}).json() == []

    csv_res = client.get("/api/inspections/export.csv", params={"module": "codes"})
    assert csv_res.headers["content-type"].startswith("text/csv")
    lines = csv_res.content.decode("utf-8").splitlines()
    assert lines[0].startswith("﻿id,created_at,module")
    assert len(lines) == 2 and "中文" in lines[1]

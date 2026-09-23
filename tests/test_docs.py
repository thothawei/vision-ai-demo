"""M4 製造文件結構化：RapidOCR 真的跑（本機快速模型），LLM 用假佇列（分類→結構化兩次呼叫）。

嚴格 schema（工單/出貨單/進料檢驗報告）的重點：
- Pydantic 驗證失敗要回傳錯誤欄位，不能硬塞
- 數字欄位的「原文片段」要拿去跟真實 OCR 文字核對，比對不到要標「可疑」
"""


def _queue(fake_llm_queue, doc_type: str, extract_payload: dict):
    responses, calls = fake_llm_queue
    responses.append(({"文件類型": doc_type}, "fake:classify"))
    responses.append((extract_payload, "fake:extract"))
    return calls


def test_work_order_valid_extraction_verifies_sources(client, fake_llm_queue, work_order_png):
    calls = _queue(fake_llm_queue, "工單", {
        "工單號": "WO-2026-0915", "料號": "SC-M6-20", "品名": "六角螺栓",
        "數量": {"值": 5000, "原文片段": "5000"},  # 真的在 OCR 文字裡
        "開工日": "2026-09-15", "完工日": "2026-09-20", "製程站別": "成型",
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "docs"
    assert body["verdict"] == "OK"
    assert body["engine"] == "rapidocr+fake:extract"
    item = body["items"][0]
    assert item["文件類型"] == "工單"
    assert item["數量"]["來源驗證"] == "OK：原文中找得到這段文字"
    # 第一次呼叫（分類）跟第二次呼叫（結構化）都是文字 prompt，不是圖片
    assert calls[0]["has_image"] is False
    assert calls[1]["has_image"] is False
    assert "工單" in calls[0]["prompt"]


def test_work_order_suspicious_source_is_flagged_not_trusted(client, fake_llm_queue, work_order_png):
    _queue(fake_llm_queue, "工單", {
        "工單號": "WO-2026-0915", "料號": "SC-M6-20", "品名": "六角螺栓",
        "數量": {"值": 99999, "原文片段": "這段文字根本不在原文裡"},
        "開工日": "2026-09-15", "完工日": "2026-09-20", "製程站別": "成型",
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    body = res.json()
    # 驗證只是標記可疑，schema 本身仍然合法，所以還是 OK；可疑訊息才是重點
    assert body["items"][0]["數量"]["來源驗證"].startswith("可疑")


def test_work_order_missing_required_field_gives_ng_with_error_detail(client, fake_llm_queue, work_order_png):
    _queue(fake_llm_queue, "工單", {
        "工單號": "WO-2026-0915",
        # 故意缺 料號/品名/數量/開工日/完工日/製程站別
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    item = body["items"][0]
    assert "_驗證錯誤" in item
    error_fields = {e["欄位"] for e in item["_驗證錯誤"]}
    assert {"料號", "品名", "數量", "開工日", "完工日", "製程站別"} <= error_fields
    # 沒有因為驗證失敗就硬塞假資料進去
    assert "料號" not in item or item.get("料號") is None


def test_shipping_order_with_table(client, fake_llm_queue, shipping_order_png):
    _queue(fake_llm_queue, "出貨單", {
        "單號": "SO-2026-0088", "客戶": "中科精密工業", "日期": "2026-09-22",
        "品項": [
            {"料號": "SC-M6-20", "品名": "六角螺栓",
             "數量": {"值": 1000, "原文片段": "1000"}, "單價": {"值": 5, "原文片段": "5"}},
        ],
        "總額": {"值": 6500, "原文片段": "6500"},
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("so.png", shipping_order_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "OK"
    item = body["items"][0]
    assert len(item["品項"]) == 1
    assert item["品項"][0]["數量"]["來源驗證"] == "OK：原文中找得到這段文字"
    assert item["總額"]["來源驗證"] == "OK：原文中找得到這段文字"


def test_inspection_report(client, fake_llm_queue, inspection_report_png):
    _queue(fake_llm_queue, "進料檢驗報告", {
        "供應商": "台中精密螺絲有限公司", "料號": "SC-M6-20", "批號": "LOT2026A",
        "抽樣數": {"值": 50, "原文片段": "50"}, "不良數": {"值": 2, "原文片段": "2"},
        "判定": "合格",
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("ir.png", inspection_report_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "OK"
    assert body["items"][0]["判定"] == "合格"


def test_inspection_report_invalid_verdict_value_rejected(client, fake_llm_queue, inspection_report_png):
    _queue(fake_llm_queue, "進料檢驗報告", {
        "供應商": "s", "料號": "p", "批號": "b",
        "抽樣數": {"值": 50, "原文片段": "50"}, "不良數": {"值": 2, "原文片段": "2"},
        "判定": "不確定",  # 只能是「合格」或「不合格」
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("ir.png", inspection_report_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert any(e["欄位"] == "判定" for e in body["items"][0]["_驗證錯誤"])


def test_freeform_type_skips_schema_validation(client, fake_llm_queue, work_order_png):
    _queue(fake_llm_queue, "報價單", {
        "文件類型": "報價單", "欄位": {"客戶": "測試客戶", "金額": "1000"},
    })

    res = client.post("/api/docs/extract", params={"mode": "ocr"},
                      files={"file": ("q.png", work_order_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "OK"
    assert body["items"][0]["文件類型"] == "報價單"
    assert "_ocr原始文字" in body["items"][0]


def test_end_to_end_sends_image_and_source_verification_is_not_applicable(client, fake_llm_queue, work_order_png):
    _queue(fake_llm_queue, "工單", {
        "工單號": "WO-2026-0915", "料號": "SC-M6-20", "品名": "六角螺栓",
        "數量": {"值": 5000, "原文片段": "5000"},
        "開工日": "2026-09-15", "完工日": "2026-09-20", "製程站別": "成型",
    })

    res = client.post("/api/docs/extract", params={"mode": "end_to_end"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    body = res.json()
    assert body["items"][0]["數量"]["來源驗證"] == "無法驗證（端到端模式沒有獨立 OCR 原文）"


def test_tesseract_mode_engine_name(client, fake_llm_queue, work_order_png):
    _queue(fake_llm_queue, "報價單", {"文件類型": "報價單", "欄位": {}})

    res = client.post("/api/docs/extract", params={"mode": "tesseract"},
                      files={"file": ("wo.png", work_order_png, "image/png")})

    assert res.json()["engine"].startswith("tesseract+")


def test_blank_image_rejected_before_llm(client, fake_llm_queue, blank_png):
    res = client.post("/api/docs/extract", files={"file": ("blank.png", blank_png, "image/png")})

    assert res.status_code == 422
    assert "端到端" in res.json()["detail"]
    _, calls = fake_llm_queue
    assert calls == []


def test_invalid_mode_rejected(client, work_order_png):
    res = client.post("/api/docs/extract", params={"mode": "xyz"},
                      files={"file": ("wo.png", work_order_png, "image/png")})
    assert res.status_code == 400

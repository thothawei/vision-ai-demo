"""M12 出貨標籤 vs 工單比對（LLM 用假佇列模擬，RapidOCR 真的跑）。"""

import io

from samples import make_samples


def _png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _post(client, image, params=None, headers=None):
    return client.post(
        "/api/shipping/check-label",
        params=params or {},
        headers=headers or {},
        files={"file": ("label.png", _png_bytes(image), "image/png")},
    )


def test_all_fields_match_is_ok(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS")

    res = _post(client, img, params={
        "expected_part_no": "SC-M6-20", "expected_lot_no": "LOT2026A", "expected_quantity": 5000,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "OK"
    item = body["items"][0]
    assert item["料號一致"] is True
    assert item["批號一致"] is True
    assert item["數量一致"] is True
    assert item["問題"] is None


def test_part_no_mismatch_is_ng(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS")

    res = _post(client, img, params={"expected_part_no": "SC-M8-30"})
    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["問題"] == ["料號"]


def test_quantity_mismatch_is_ng(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS")

    res = _post(client, img, params={"expected_quantity": 4000})
    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["問題"] == ["數量"]
    assert body["items"][0]["標籤數量"] == 5000


def test_no_expected_values_is_info(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS")

    res = _post(client, img)
    assert res.json()["verdict"] == "INFO"


def test_trace_header_used_as_expected_value_when_param_not_given(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT9999", quantity="5000 PCS")

    res = _post(client, img, headers={"X-Lot-No": "LOT9999"})
    body = res.json()
    assert body["items"][0]["預期批號"] == "LOT9999"
    assert body["items"][0]["批號一致"] is False  # 標籤上其實是 LOT2026A


def test_explicit_param_overrides_trace_header(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS")

    res = _post(client, img, params={"expected_lot_no": "LOT2026A"}, headers={"X-Lot-No": "LOT9999"})
    body = res.json()
    assert body["items"][0]["預期批號"] == "LOT2026A"
    assert body["items"][0]["批號一致"] is True


def test_barcode_lot_no_takes_priority_over_printed_text(client, fake_llm_queue):
    # LLM 讀到的印刷批號是 LOT2026A，但標籤上另外有個 GS1 條碼寫 LOT_BARCODE，應該以條碼為準
    fake_llm_queue[0].append(({"料號": "SC-M6-20", "數量": "5000 PCS", "批號": "LOT2026A"}, "fake:model"))
    img = make_samples.make_shipping_label(
        part_no="SC-M6-20", lot_no="LOT2026A", quantity="5000 PCS",
        with_barcode=True, barcode_lot_no="LOT_BARCODE",
    )

    res = _post(client, img, params={"expected_lot_no": "LOT_BARCODE"})
    body = res.json()
    assert body["items"][0]["標籤批號"] == "LOT_BARCODE"
    assert body["items"][0]["批號來源"] == "條碼"
    assert body["items"][0]["批號一致"] is True


def test_schema_validation_error_is_ng(client, fake_llm_queue):
    fake_llm_queue[0].append(({"料號": "SC-M6-20"}, "fake:model"))  # 缺 數量/批號 兩個必要欄位
    img = make_samples.make_shipping_label()

    res = _post(client, img)
    body = res.json()
    assert body["verdict"] == "NG"
    assert "_驗證錯誤" in body["items"][0]


def test_empty_file_rejected(client):
    res = client.post("/api/shipping/check-label", files={"file": ("e.png", b"", "image/png")})
    assert res.status_code == 400

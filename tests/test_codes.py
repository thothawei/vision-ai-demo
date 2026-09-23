"""M1 追溯碼辨識：GS1 DataMatrix 解析、效期判斷（已過期/即將到期/正常）。"""


def test_decode_gs1_valid(client, gs1_valid_png_fields):
    png, fields = gs1_valid_png_fields
    res = client.post("/api/codes/decode", files={"file": ("gs1.png", png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "codes"
    assert body["verdict"] == "OK"
    item = body["items"][0]
    assert item["是否為GS1"] is True
    assert item["效期狀態"] == "正常"
    assert item["GS1欄位"]["批號"] == fields["batch"]
    assert item["GS1欄位"]["序號"] == fields["serial"]
    assert item["效期"] == fields["expiry"].isoformat()
    assert len(item["四角座標"]) == 4
    assert body["annotated_image"].startswith("data:image/png;base64,")


def test_decode_gs1_expired_gives_ng(client, gs1_expired_png_fields):
    png, _ = gs1_expired_png_fields
    res = client.post("/api/codes/decode", files={"file": ("gs1.png", png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["效期狀態"] == "已過期"


def test_decode_gs1_expiring_soon(client, gs1_expiring_soon_png_fields):
    png, _ = gs1_expiring_soon_png_fields
    res = client.post("/api/codes/decode", files={"file": ("gs1.png", png, "image/png")})

    body = res.json()
    # 快到期但還沒過期：不是 NG（NG 只保留給真的過期）
    assert body["verdict"] != "NG"
    assert body["items"][0]["效期狀態"] == "即將到期"


def test_decode_no_barcode_found_is_info(client, blank_png):
    res = client.post("/api/codes/decode", files={"file": ("blank.png", blank_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "INFO"
    assert body["items"] == []


def test_decode_empty_file_rejected(client):
    res = client.post("/api/codes/decode", files={"file": ("e.png", b"", "image/png")})
    assert res.status_code == 400

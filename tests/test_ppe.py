"""M5 PPE 安全帽偵測：API 契約與 OK/NG 判定（假偵測結果，真實 mAP 見 CLAUDE.md 訓練紀錄）。"""


def test_no_helmet_detected_gives_ng(client, fake_ppe_detector, warning_sign_png):
    res = client.post("/api/safety/ppe", files={"file": ("p.png", warning_sign_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "ppe"
    assert body["verdict"] == "NG"
    item = body["items"][0]
    assert item["偵測到人頭數"] == 2
    assert item["未戴安全帽數"] == 1
    types = {d["類型"] for d in item["明細"]}
    assert types == {"已戴安全帽", "未戴安全帽"}


def test_missing_weights_gives_clear_error(client, warning_sign_png, monkeypatch, tmp_path):
    monkeypatch.setattr("modules.safety.service.PPE_WEIGHTS_PATH", tmp_path / "no_such.pt")
    res = client.post("/api/safety/ppe", files={"file": ("p.png", warning_sign_png, "image/png")})

    assert res.status_code == 503
    assert "prepare_hardhat.py" in res.json()["detail"]

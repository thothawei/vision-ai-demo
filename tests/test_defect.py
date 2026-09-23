"""M6 監督式 PCB 瑕疵偵測：API 契約與 OK/NG 判定（假偵測結果，真實 mAP 見 CLAUDE.md 訓練紀錄）。"""


def test_defect_found_gives_ng(client, fake_pcb_detector, warning_sign_png):
    res = client.post("/api/defect/pcb", files={"file": ("pcb.png", warning_sign_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "defect"
    assert body["verdict"] == "NG"
    assert body["engine"] == "yolo11n-deeppcb"
    item = body["items"][0]
    assert item["偵測到瑕疵數"] == 1
    assert "open" in item["明細"][0]["瑕疵類型"]
    assert body["annotated_image"].startswith("data:image/png;base64,")


def test_no_defect_gives_ok(client, fake_pcb_detector_no_defect, warning_sign_png):
    res = client.post("/api/defect/pcb", files={"file": ("pcb.png", warning_sign_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "OK"
    assert body["items"][0]["偵測到瑕疵數"] == 0


def test_missing_weights_gives_clear_error(client, warning_sign_png, monkeypatch, tmp_path):
    monkeypatch.setattr("modules.defect.service.WEIGHTS_PATH", tmp_path / "no_such.pt")
    res = client.post("/api/defect/pcb", files={"file": ("pcb.png", warning_sign_png, "image/png")})

    assert res.status_code == 503
    assert "prepare_deeppcb.py" in res.json()["detail"]

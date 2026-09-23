"""M3 異常檢測：API 契約與 OK/NG 判定（用假推論隔離 anomalib，真實 AUROC 見 test_live_anomaly.py）。"""


def test_ok_when_not_anomalous(client, fake_anomaly_inferencer, warning_sign_png):
    res = client.post("/api/anomaly/inspect", params={"category": "metal_nut"},
                      files={"file": ("i.png", warning_sign_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "anomaly"
    assert body["verdict"] == "OK"
    assert body["items"][0]["判定"] == "正常"
    assert body["engine"] == "anomalib-patchcore"
    assert body["annotated_image"].startswith("data:image/png;base64,")
    assert "metal_nut" in fake_anomaly_inferencer


def test_ng_when_anomalous(client, fake_anomaly_inferencer, warning_sign_png):
    res = client.post("/api/anomaly/inspect", params={"category": "metal_nut_ng"},
                      files={"file": ("i.png", warning_sign_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["判定"] == "異常"
    assert body["items"][0]["異常分數"] == 0.9


def test_invalid_category_rejected(client, fake_anomaly_inferencer, warning_sign_png):
    res = client.post("/api/anomaly/inspect", params={"category": "no_such_thing"},
                      files={"file": ("i.png", warning_sign_png, "image/png")})
    assert res.status_code == 400


def test_missing_weights_gives_clear_error(client, warning_sign_png, monkeypatch, tmp_path):
    # 沒有 fake_anomaly_inferencer：走真實的 _get_inferencer，指向不存在的權重路徑
    monkeypatch.setattr("modules.anomaly.service.MODELS_DIR", tmp_path)
    res = client.post("/api/anomaly/inspect", params={"category": "metal_nut"},
                      files={"file": ("i.png", warning_sign_png, "image/png")})

    assert res.status_code == 503
    assert "train_anomaly.py" in res.json()["detail"]

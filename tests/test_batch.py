"""Phase 11：POST /api/batch/{action} 批次上傳。"""


def test_batch_general_all_succeed(client, fake_llm, warning_sign_png):
    files = [("files", (f"{i}.png", warning_sign_png, "image/png")) for i in range(3)]
    res = client.post("/api/batch/general", files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "general"
    assert body["total"] == 3
    assert body["info"] == 3  # M9 一律 INFO
    assert body["failed"] == 0
    assert len(body["results"]) == 3
    assert all(r["status"] == "ok" for r in body["results"])
    assert [r["filename"] for r in body["results"]] == ["0.png", "1.png", "2.png"]


def test_batch_one_bad_file_does_not_abort_the_rest(client, fake_llm, warning_sign_png):
    files = [
        ("files", ("good1.png", warning_sign_png, "image/png")),
        ("files", ("bad.png", b"not an image", "image/png")),
        ("files", ("good2.png", warning_sign_png, "image/png")),
    ]
    res = client.post("/api/batch/general", files=files)
    body = res.json()
    assert body["total"] == 3
    assert body["failed"] == 1
    assert body["info"] == 2
    statuses = {r["filename"]: r["status"] for r in body["results"]}
    assert statuses == {"good1.png": "ok", "bad.png": "error", "good2.png": "ok"}
    bad = next(r for r in body["results"] if r["filename"] == "bad.png")
    assert "無法讀取圖片" in bad["error"]


def test_batch_unknown_action_returns_400(client, warning_sign_png):
    res = client.post("/api/batch/not-a-real-action", files=[("files", ("a.png", warning_sign_png, "image/png"))])
    assert res.status_code == 400


def test_batch_anomaly_requires_category(client, fake_anomaly_inferencer, warning_sign_png):
    missing = client.post("/api/batch/anomaly", files=[("files", ("a.png", warning_sign_png, "image/png"))])
    body = missing.json()
    assert body["failed"] == 1
    assert "category" in body["results"][0]["error"]

    ok = client.post(
        "/api/batch/anomaly", params={"category": "screw"},
        files=[("files", ("a.png", warning_sign_png, "image/png"))],
    )
    assert ok.json()["failed"] == 0


def test_batch_count_passes_shared_params_and_logs_each_inspection(client, screws_png):
    res = client.post(
        "/api/batch/count", params={"expected_count": 8},
        files=[("files", ("a.png", screws_png, "image/png")), ("files", ("b.png", screws_png, "image/png"))],
    )
    body = res.json()
    assert body["total"] == 2
    assert body["failed"] == 0
    inspection_ids = [r["result"]["inspection_id"] for r in body["results"]]
    logs = client.get("/api/inspections", params={"module": "measure"}).json()
    assert {log["id"] for log in logs} == set(inspection_ids)


def test_batch_intrusion_shares_zone_form_field(client, fake_person_detector, warning_sign_png):
    zone = '[[0.0,0.0],[1.0,0.0],[1.0,1.0],[0.0,1.0]]'
    res = client.post(
        "/api/batch/intrusion", data={"zone": zone},
        files=[("files", ("a.png", warning_sign_png, "image/png"))],
    )
    body = res.json()
    assert body["failed"] == 0
    assert body["results"][0]["result"]["verdict"] == "NG"  # 整張圖都算危險區域，一定入侵

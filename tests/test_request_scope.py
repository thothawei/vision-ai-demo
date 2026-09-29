"""Phase 17：請求範圍資料（多張圖 role）、request_id、日誌。"""

import io
import json
import logging

from samples import make_samples


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_assembly_saves_raw_and_golden_and_image_api_serves_both(admin_client, monkeypatch):
    client = admin_client  # 建立黃金樣本需要 admin
    monkeypatch.setenv("SAVE_IMAGES", "true")
    golden = _png(make_samples.make_assembly_scene())
    client.post("/api/assembly/golden-samples", params={"part_no": "p1"},
                data={"rois": json.dumps(make_samples.ASSEMBLY_ROIS)}, files={"file": ("g.png", golden, "image/png")})
    target = _png(make_samples.make_assembly_scene(missing_index=2))
    res = client.post("/api/assembly/inspect?part_no=p1", files={"file": ("t.png", target, "image/png")})
    inspection_id = res.json()["inspection_id"]

    record = client.get(f"/api/inspections/{inspection_id}").json()
    assert record["image_path"] is not None and record["annotated_path"] is not None
    assert set(record["images"]) == {"golden"}

    raw = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "raw"})
    golden_res = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "golden"})
    assert raw.status_code == golden_res.status_code == 200
    assert raw.content == target       # 存下來的是待測照片
    assert golden_res.content == golden  # 與黃金樣本，兩張不同

    bad = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "nonsense"})
    assert bad.status_code == 400
    assert client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "reference"}).status_code == 404


def test_single_image_modules_have_no_extra_images(client, fake_llm, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
    assert client.get(f"/api/inspections/{res.json()['inspection_id']}").json()["images"] == {}


def test_batch_each_image_keeps_its_own_raw(client, fake_llm, warning_sign_png, blank_png):
    """批次逐張處理：每筆紀錄存的都是自己那張，不會沿用上一張的圖。"""
    body = client.post("/api/batch/general", files=[
        ("files", ("a.png", warning_sign_png, "image/png")),
        ("files", ("b.png", blank_png, "image/png")),
    ]).json()
    ids = [r["result"]["inspection_id"] for r in body["results"]]
    contents = [client.get(f"/api/inspections/{i}/image", params={"kind": "raw"}).content for i in ids]
    assert contents == [warning_sign_png, blank_png]


def test_request_id_header_db_column_csv_and_log(client, fake_llm, warning_sign_png, caplog):
    with caplog.at_level(logging.INFO, logger="vision.http"):
        res = client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")},
                          headers={"X-Request-ID": "req-abc-123"})
    assert res.headers["X-Request-ID"] == "req-abc-123"
    record = client.get(f"/api/inspections/{res.json()['inspection_id']}").json()
    assert record["request_id"] == "req-abc-123"
    assert "request_id" in client.get("/api/inspections/export.csv").text.splitlines()[0].split(",")[-1]
    assert any("path=/api/general/describe" in r.getMessage() and "status=200" in r.getMessage()
               for r in caplog.records)


def test_request_id_generated_when_missing_or_malformed_and_present_on_401(client, warning_sign_png):
    generated = client.get("/api/modules").headers["X-Request-ID"]
    assert len(generated) == 16
    replaced = client.get("/api/modules", headers={"X-Request-ID": "bad id with spaces!"}).headers["X-Request-ID"]
    assert replaced != "bad id with spaces!"
    unauthorized = client.get("/api/inspections", headers={"X-API-Key": "wrong"})
    assert unauthorized.status_code == 401 and unauthorized.headers.get("X-Request-ID")


def test_app_logs_do_not_leak_api_key_or_image_bytes(client, fake_llm, warning_sign_png, caplog):
    """只檢查本專案自己的 logger（vision.*、core.*、modules.*）；httpx 測試用戶端與 PIL 的除錯日誌不算。
    注意：uvicorn 的 access log 會印完整網址，`?api_key=` 會出現在那裡（已知限制，見 known-limitations.md）。"""
    with caplog.at_level(logging.DEBUG):
        client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
        client.get("/api/inspections", params={"api_key": "test-key"})
    own = [r for r in caplog.records if r.name.startswith(("vision", "core", "modules"))]
    assert own, "應該至少有本專案的請求日誌"
    text = "\n".join(r.getMessage() for r in own)
    assert "test-key" not in text
    assert repr(warning_sign_png[:16]) not in text

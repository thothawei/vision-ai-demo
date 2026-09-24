"""Phase 9：舊 db migration、追溯 header、原圖/標註圖存檔、人工複判、看板統計。"""

import sqlite3
from urllib.parse import quote


def _make_legacy_db(path):
    """建一個只有 Phase 1-8 六個欄位的舊 schema db，模擬使用者升級前留下的檔案。"""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            module TEXT NOT NULL,
            verdict TEXT NOT NULL,
            engine TEXT NOT NULL,
            elapsed_ms INTEGER NOT NULL,
            summary_json TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json)"
        " VALUES ('2026-01-01T00:00:00', 'anomaly', 'NG', 'e', 10, '[{\"score\": 0.9}]')"
    )
    conn.commit()
    conn.close()


def test_legacy_db_auto_migrates_and_old_data_still_queryable(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    _make_legacy_db(db_path)
    monkeypatch.setenv("INSPECTION_DB", str(db_path))
    monkeypatch.setenv("INSPECTION_IMAGES_DIR", str(tmp_path / "images"))

    from core.inspection_log import query_inspections

    rows = query_inspections()
    assert len(rows) == 1
    row = rows[0]
    assert row["summary"] == [{"score": 0.9}]
    # 新欄位補上但是 NULL，不影響舊資料可查詢
    for col in ("work_order", "part_no", "lot_no", "station", "operator",
                "image_path", "annotated_path", "review_verdict", "reviewer", "reviewed_at", "review_note"):
        assert col in row
        assert row[col] is None

    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(inspections)").fetchall()}
    assert "work_order" in cols and "review_verdict" in cols
    conn.close()


def test_trace_headers_recorded_and_optional(client, fake_llm, warning_sign_png):
    res = client.post(
        "/api/general/describe",
        files={"file": ("sign.png", warning_sign_png, "image/png")},
        headers={
            "X-Work-Order": quote("WO-2026-0001"),
            "X-Part-No": quote("SC-M6-20"),
            "X-Lot-No": "LOT001",
            "X-Station": quote("AOI-01"),
            "X-Operator": quote("王小明"),
        },
    )
    assert res.status_code == 200
    inspection_id = res.json()["inspection_id"]

    record = client.get(f"/api/inspections/{inspection_id}").json()
    assert record["work_order"] == "WO-2026-0001"
    assert record["part_no"] == "SC-M6-20"
    assert record["lot_no"] == "LOT001"
    assert record["station"] == "AOI-01"
    assert record["operator"] == "王小明"

    # 不帶 header 也要正常，欄位為 NULL
    res2 = client.post("/api/general/describe", files={"file": ("sign.png", warning_sign_png, "image/png")})
    assert res2.status_code == 200
    record2 = client.get(f"/api/inspections/{res2.json()['inspection_id']}").json()
    assert record2["work_order"] is None


def test_filter_by_trace_fields(client, fake_llm, warning_sign_png):
    client.post("/api/general/describe", files={"file": ("a.png", warning_sign_png, "image/png")},
                headers={"X-Work-Order": "WO-1"})
    client.post("/api/general/describe", files={"file": ("b.png", warning_sign_png, "image/png")},
                headers={"X-Work-Order": "WO-2"})

    results = client.get("/api/inspections", params={"work_order": "WO-1"}).json()
    assert len(results) == 1
    assert results[0]["work_order"] == "WO-1"


def test_save_images_true_stores_raw_and_annotated_and_image_api_serves_them(client, fake_llm, warning_sign_png, monkeypatch):
    monkeypatch.setenv("SAVE_IMAGES", "true")
    res = client.post("/api/general/describe", files={"file": ("sign.png", warning_sign_png, "image/png")})
    inspection_id = res.json()["inspection_id"]

    record = client.get(f"/api/inspections/{inspection_id}").json()
    assert record["image_path"] is not None
    # M9 沒有標註圖（annotated_image 是 None），annotated_path 應為 None
    assert record["annotated_path"] is None

    img_res = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "raw"})
    assert img_res.status_code == 200
    assert img_res.content == warning_sign_png

    missing_res = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "annotated"})
    assert missing_res.status_code == 404


def test_save_images_false_does_not_store(client, fake_llm, warning_sign_png, monkeypatch):
    monkeypatch.setenv("SAVE_IMAGES", "false")
    res = client.post("/api/general/describe", files={"file": ("sign.png", warning_sign_png, "image/png")})
    inspection_id = res.json()["inspection_id"]

    record = client.get(f"/api/inspections/{inspection_id}").json()
    assert record["image_path"] is None
    assert record["annotated_path"] is None

    img_res = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "raw"})
    assert img_res.status_code == 404


def test_save_images_stores_annotated_when_module_provides_one(client, fake_pcb_detector, screws_png):
    res = client.post("/api/defect/pcb", files={"file": ("p.png", screws_png, "image/png")})
    inspection_id = res.json()["inspection_id"]
    record = client.get(f"/api/inspections/{inspection_id}").json()
    assert record["image_path"] is not None
    assert record["annotated_path"] is not None

    annotated_res = client.get(f"/api/inspections/{inspection_id}/image", params={"kind": "annotated"})
    assert annotated_res.status_code == 200
    assert annotated_res.headers["content-type"] == "image/png"


def test_review_endpoint_updates_and_rejects_invalid_verdict(client, fake_llm, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
    inspection_id = res.json()["inspection_id"]

    patched = client.patch(
        f"/api/inspections/{inspection_id}/review",
        json={"review_verdict": "NG", "reviewer": "李品檢", "review_note": "實際有瑕疵"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["review_verdict"] == "NG"
    assert body["reviewer"] == "李品檢"
    assert body["review_note"] == "實際有瑕疵"
    assert body["reviewed_at"] is not None

    invalid = client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "MAYBE"})
    assert invalid.status_code == 422

    not_found = client.patch("/api/inspections/999999/review", json={"review_verdict": "OK"})
    assert not_found.status_code == 404


def test_stats_yield_pareto_and_consistency(client):
    from core.inspection_log import log_inspection, update_review

    id_ok1 = log_inspection("anomaly", "OK", "e", 10, [{"類別": "screw", "判定": "正常"}])
    id_ng1 = log_inspection("anomaly", "NG", "e", 10, [{"類別": "screw", "判定": "異常"}])
    id_ng2 = log_inspection(
        "defect", "NG", "e", 10,
        [{"偵測到瑕疵數": 2, "明細": [{"瑕疵類型": "斷路 open"}, {"瑕疵類型": "短路 short"}]}],
    )
    log_inspection("defect", "NG", "e", 10, [{"偵測到瑕疵數": 1, "明細": [{"瑕疵類型": "斷路 open"}]}])
    log_inspection("general", "INFO", "e", 10, [{"主要物件": "x"}])

    # AI 判 NG 的 id_ng1 被人工改判 OK（誤判），一致率應反映不一致
    update_review(id_ng1, "OK", "王品檢", "AI 誤判，實際良品")
    update_review(id_ok1, "OK", "王品檢", "確認良品")

    stats = client.get("/api/inspections/stats", params={"group_by": "module"}).json()
    assert stats["total"] == 5
    assert stats["reviewed_count"] == 2
    assert stats["consistency_rate"] == 0.5  # id_ok1 一致、id_ng1 不一致
    # AI 良率：anomaly 2 筆 1 OK 1 NG = 0.5；final 良率：anomaly 2 筆都變 OK = 1.0（只看 anomaly 自己 group 內）
    anomaly_group = next(g for g in stats["groups"] if g["module"] == "anomaly")
    assert anomaly_group["total"] == 2
    assert anomaly_group["OK"] == 2  # 兩筆的最終判定都是 OK（一筆本來就 OK、一筆被複判成 OK）
    assert anomaly_group["NG"] == 0

    pareto = client.get("/api/inspections/stats", params={"group_by": "defect"}).json()
    labels = {g["label"]: g["count"] for g in pareto["groups"]}
    # 斷路 open 出現在兩筆 defect 紀錄，anomaly 的「判定=異常」也算一種缺陷類別
    assert labels["斷路 open"] == 2
    assert labels["短路 short"] == 1
    assert labels["外觀異常（screw）"] == 1
    total_defects = sum(labels.values())
    assert pareto["groups"][0]["label"] == "斷路 open"
    assert pareto["groups"][0]["pct"] == round(2 / total_defects * 100, 2)
    assert pareto["groups"][-1]["cum_pct"] == 100.0

    day_stats = client.get("/api/inspections/stats", params={"group_by": "day"}).json()
    assert sum(g["total"] for g in day_stats["groups"]) == 5

    bad_group_by = client.get("/api/inspections/stats", params={"group_by": "nonsense"})
    assert bad_group_by.status_code == 400


def test_csv_export_includes_new_columns(client, fake_llm, warning_sign_png):
    client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")},
                headers={"X-Work-Order": "WO-9"})
    csv_res = client.get("/api/inspections/export.csv")
    lines = csv_res.content.decode("utf-8").splitlines()
    header = lines[0].lstrip("﻿")
    assert "work_order" in header and "review_verdict" in header
    assert "WO-9" in lines[1]

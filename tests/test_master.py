"""Phase 19：主檔（料號、工單）與 ERP bulk-upsert、臨時檢驗標記。"""

from fastapi.testclient import TestClient


def _part(admin, part_no="SC-M6-20", **extra):
    res = admin.post("/api/master/parts", json={"part_no": part_no, "name": "六角螺栓", **extra})
    assert res.status_code == 201, res.text
    return res.json()


def _wo(admin, no="WO-1", part_no="SC-M6-20", **extra):
    return admin.post(
        "/api/master/work-orders", json={"work_order_no": no, "part_no": part_no, "quantity": 100, **extra}
    )


def test_part_and_work_order_crud_with_audit(admin_client):
    _part(admin_client)
    assert (
        admin_client.post(
            "/api/master/parts", json={"part_no": "SC-M6-20", "name": "改名", "spec": "M6x20"}
        ).status_code
        == 201
    )
    parts = admin_client.get("/api/master/parts").json()
    assert [(p["part_no"], p["name"], p["spec"]) for p in parts] == [("SC-M6-20", "改名", "M6x20")]

    res = _wo(admin_client, status="in_progress", lot_no="LOT9", start_date="2026-09-01")
    assert res.status_code == 201 and res.json()["lot_no"] == "LOT9"
    assert _wo(admin_client, quantity=0, status="done").status_code == 201  # 同工單號＝更新
    listed = admin_client.get("/api/master/work-orders").json()
    assert len(listed) == 1 and listed[0]["status"] == "done"

    actions = [e["action"] for e in admin_client.get("/api/audit").json()]
    assert "part.create" in actions and "part.update" in actions and actions.count("work_order.update") == 2
    update = next(e for e in admin_client.get("/api/audit", params={"action": "work_order.update"}).json())
    assert update["before"]["status"] == "in_progress" and update["after"]["status"] == "done"


def test_validation_errors(admin_client):
    _part(admin_client)
    assert admin_client.post("/api/master/parts", json={"part_no": "有 中文"}).status_code == 422
    assert _wo(admin_client, part_no="NOPE").status_code == 422  # 料號不在主檔
    assert _wo(admin_client, status="weird").status_code == 422
    assert _wo(admin_client, start_date="2026/09/01").status_code == 422
    assert _wo(admin_client, quantity=-1).status_code == 422
    assert (
        admin_client.post(
            "/api/master/work-orders", json={"work_order_no": "W", "part_no": "SC-M6-20", "bogus": 1}
        ).status_code
        == 422
    )


def test_only_admin_can_write_but_everyone_logged_in_can_read(admin_client, qc_client, operator_client, client):
    _part(admin_client)
    _wo(admin_client)
    for reader in (admin_client, qc_client, operator_client, client):  # client = API key
        assert reader.get("/api/master/parts").status_code == 200
        assert reader.get("/api/master/work-orders", params={"open_only": True}).status_code == 200
    for writer in (qc_client, operator_client, client):
        assert writer.post("/api/master/parts", json={"part_no": "X1"}).status_code == 403
        assert _wo(writer, no="WO-2").status_code == 403
    assert TestClient(admin_client.app).get("/api/master/parts").status_code == 401


def test_open_only_filters_finished_and_cancelled(admin_client):
    _part(admin_client)
    for no, status in (("A", "planned"), ("B", "in_progress"), ("C", "done"), ("D", "cancelled")):
        _wo(admin_client, no=no, status=status)
    assert {
        w["work_order_no"] for w in admin_client.get("/api/master/work-orders", params={"open_only": True}).json()
    } == {"A", "B"}


# --- ERP bulk-upsert ---


def _erp(api_client):
    """名為 erp 的 API key（conftest 的預設 key 就叫 erp）。"""
    return api_client


def test_bulk_upsert_from_erp_partial_success_and_idempotent(client, admin_client):
    parts = {"parts": [{"part_no": "P-1", "name": "一號"}, {"part_no": "P-2", "name": "二號"}]}
    res = client.post("/api/master/parts:bulk-upsert", json=parts)
    assert res.status_code == 200 and res.json()["created"] == ["P-1", "P-2"] and res.json()["errors"] == []

    orders = {
        "work_orders": [
            {"work_order_no": "WO-A", "part_no": "P-1", "quantity": 10, "status": "in_progress", "lot_no": "L1"},
            {"work_order_no": "WO-B", "part_no": "NOT-IN-MASTER", "quantity": 5},
            {"work_order_no": "WO-C", "part_no": "P-2", "quantity": 7, "status": "bad"},
        ]
    }
    body = client.post("/api/master/work-orders:bulk-upsert", json=orders).json()
    assert body["created"] == ["WO-A"] and body["updated"] == []
    assert [(e["index"], e["key"]) for e in body["errors"]] == [(1, "WO-B"), (2, "WO-C")]  # 各列各自失敗，不拖累其他列

    again = client.post("/api/master/work-orders:bulk-upsert", json=orders).json()
    assert again["created"] == [] and again["updated"] == ["WO-A"]  # 重推不會重複建立
    assert [w["work_order_no"] for w in admin_client.get("/api/master/work-orders").json()] == ["WO-A"]

    entry = admin_client.get("/api/audit", params={"action": "work_orders.bulk_upsert"}).json()[0]
    assert entry["actor"] == "api-key:erp"  # 最新一筆是第二次推送：沒有新增、更新 1 筆、2 列有誤
    assert (entry["after"]["created_count"], entry["after"]["updated_count"], entry["after"]["error_count"]) == (
        0,
        1,
        2,
    )


def test_bulk_upsert_rejects_other_keys_operators_and_unknown_fields(
    monkeypatch, client, qc_client, operator_client, admin_client
):
    from main import app

    monkeypatch.setenv("API_KEYS", "erp:erp-key,watcher:watch-key")
    watcher = TestClient(app, headers={"X-API-Key": "watch-key"})
    body = {"parts": [{"part_no": "P-9"}]}
    assert watcher.post("/api/master/parts:bulk-upsert", json=body).status_code == 403  # 只有 erp 這把可推主檔
    assert qc_client.post("/api/master/parts:bulk-upsert", json=body).status_code == 403
    assert operator_client.post("/api/master/parts:bulk-upsert", json=body).status_code == 403
    assert TestClient(app).post("/api/master/parts:bulk-upsert", json=body).status_code == 401
    assert admin_client.post("/api/master/parts:bulk-upsert", json=body).status_code == 200  # admin 也可以
    assert (
        TestClient(app, headers={"X-API-Key": "erp-key"})
        .post("/api/master/parts:bulk-upsert", json={"parts": [{"part_no": "P-8", "junk": 1}]})
        .status_code
        == 422
    )


# --- 臨時檢驗標記 ---


def test_adhoc_flag_marks_inspections_without_a_known_work_order(client, admin_client, fake_llm, warning_sign_png):
    _part(admin_client)
    _wo(admin_client, no="WO-REAL")
    files = {"file": ("s.png", warning_sign_png, "image/png")}
    ids = {}
    for label, headers in (
        ("none", {}),
        ("known", {"X-Work-Order": "WO-REAL"}),
        ("unknown", {"X-Work-Order": "WO-TYPO"}),
    ):
        ids[label] = client.post("/api/general/describe", files=files, headers=headers).json()["inspection_id"]
    flags = {label: admin_client.get(f"/api/inspections/{i}").json()["adhoc"] for label, i in ids.items()}
    assert flags == {"none": 1, "known": 0, "unknown": 1}

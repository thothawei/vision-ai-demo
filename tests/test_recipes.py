"""Phase 19：檢驗配方（版本不可變）、依配方執行、合併判定、run 統計。"""

import io
import json

import pytest

from core import recipes
from samples import make_samples


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def setup(admin_client, fake_anomaly_inferencer, measure_scene_png_marker):
    """料號 SC-M6-20、工單 WO-1，以及三步驟配方：追溯碼(main)、異常檢測 screw(main)、尺寸量測(scene)。"""
    admin_client.post("/api/master/parts", json={"part_no": "SC-M6-20", "name": "螺栓"})
    admin_client.post("/api/master/work-orders", json={"work_order_no": "WO-1", "part_no": "SC-M6-20",
                                                       "quantity": 10, "status": "in_progress", "lot_no": "LOT-A"})
    _, marker_mm = measure_scene_png_marker
    steps = [
        {"action": "codes", "label": "追溯碼"},
        {"action": "anomaly", "params": {"category": "screw"}, "label": "外觀"},
        {"action": "measure", "image_slot": "scene", "label": "尺寸",
         "params": {"marker_size_mm": marker_mm, "target_length_mm": 50, "tolerance_mm": 1.0}},
    ]
    res = admin_client.post("/api/recipes", json={"part_no": "SC-M6-20", "steps": steps, "note": "初版"})
    assert res.status_code == 201, res.text
    return admin_client, res.json()


def _run(session, main_png, scene_png, **fields):
    return session.post("/api/inspect/recipe", data={"work_order": "WO-1", **fields},
                        files={"main": ("m.png", main_png, "image/png"), "scene": ("s.png", scene_png, "image/png")})


def test_recipe_run_ok_creates_one_run_and_one_inspection_per_step(setup, gs1_valid_png_fields, measure_scene_png_marker):
    admin, recipe = setup
    assert recipe["version"] == 1 and recipe["is_active"] and recipe["slots"] == ["main", "scene"]
    main_png, _ = gs1_valid_png_fields
    scene_png, _ = measure_scene_png_marker

    res = _run(admin, main_png, scene_png)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["verdict"] == "OK" and body["reasons"] == [] and body["version"] == 1
    assert [s["action"] for s in body["steps"]] == ["codes", "anomaly", "measure"]
    assert [s["verdict"] for s in body["steps"]] == ["OK", "OK", "OK"]

    run = admin.get(f"/api/runs/{body['run_id']}").json()
    assert run["status"] == "done" and run["work_order"] == "WO-1" and run["lot_no"] == "LOT-A"  # 批號由工單帶入
    assert run["adhoc"] == 0 and run["created_by"] == "user:admin_test" and run["recipe_id"] == recipe["id"]
    ids = [s["inspection_id"] for s in run["steps"]]
    assert len(set(ids)) == 3
    for step_id, module in zip(ids, ("codes", "anomaly", "measure")):
        record = admin.get(f"/api/inspections/{step_id}").json()
        assert record["run_id"] == body["run_id"] and record["module"] == module
        assert record["work_order"] == "WO-1" and record["part_no"] == "SC-M6-20" and record["lot_no"] == "LOT-A"


def test_recipe_run_ng_when_any_inspection_step_is_ng(admin_client, setup, gs1_expired_png_fields, measure_scene_png_marker):
    admin, _ = setup
    expired_png, _ = gs1_expired_png_fields
    scene_png, _ = measure_scene_png_marker
    body = _run(admin, expired_png, scene_png).json()
    assert body["verdict"] == "NG"
    assert any("追溯碼" in r and "NG" in r for r in body["reasons"])
    assert [s["verdict"] for s in body["steps"]] == ["NG", "OK", "OK"]  # 其他步驟照常執行


def test_recipe_run_info_when_a_step_errors_or_cannot_judge_and_none_ng(setup, gs1_valid_png_fields, blank_png):
    admin, _ = setup
    main_png, _ = gs1_valid_png_fields
    body = _run(admin, main_png, blank_png).json()  # 量測圖沒有 ArUco 標記 → 該步驟出錯
    assert body["verdict"] == "INFO"
    measure_step = body["steps"][2]
    assert measure_step["status"] == "error" and "標記" in measure_step["error"]
    assert any("尺寸" in r for r in body["reasons"])
    assert body["steps"][0]["verdict"] == "OK"


def test_ng_beats_error_in_merged_verdict(setup, gs1_expired_png_fields, blank_png):
    admin, _ = setup
    expired_png, _ = gs1_expired_png_fields
    assert _run(admin, expired_png, blank_png).json()["verdict"] == "NG"


def test_combine_rules_directly():
    def step(pos, kind, verdict, status="ok", error=None):
        return {"position": pos, "action": "a", "label": "", "verdict_kind": kind, "verdict": verdict,
                "status": status, "error": error}

    assert recipes.combine([step(1, "inspection", "OK"), step(2, "inspection", "OK")])[0] == "OK"
    assert recipes.combine([step(1, "inspection", "OK"), step(2, "inspection", "NG")])[0] == "NG"
    assert recipes.combine([step(1, "inspection", "OK"), step(2, "inspection", "INFO")])[0] == "INFO"
    assert recipes.combine([step(1, "inspection", "OK"), step(2, "inspection", None, "error", "x")])[0] == "INFO"
    # info 類動作（現場照片辨識、指針錶）本來就不判 OK/NG，不影響合併判定
    assert recipes.combine([step(1, "inspection", "OK"), step(2, "info", "INFO")])[0] == "OK"
    assert recipes.combine([step(1, "info", "INFO", "error", "boom")])[0] == "INFO"  # 但出錯就是出錯
    assert recipes.combine([step(1, "inspection", "NG"), step(2, "inspection", None, "error", "x")])[0] == "NG"


def test_editing_creates_new_version_and_old_runs_keep_pointing_to_old_version(setup, gs1_valid_png_fields, measure_scene_png_marker):
    admin, v1 = setup
    main_png, _ = gs1_valid_png_fields
    scene_png, marker_mm = measure_scene_png_marker[0], measure_scene_png_marker[1]
    old_run = _run(admin, main_png, scene_png).json()

    # 新版本：量測目標改成 80mm（實際 50mm → 超差 NG）
    steps = [{"action": "measure", "image_slot": "scene",
              "params": {"marker_size_mm": marker_mm, "target_length_mm": 80, "tolerance_mm": 1.0}}]
    v2 = admin.post("/api/recipes", json={"part_no": "SC-M6-20", "steps": steps}).json()
    assert v2["version"] == 2 and v2["is_active"]
    assert admin.get(f"/api/recipes/{v1['id']}").json()["is_active"] is False  # 同一料號只有一個啟用版本

    assert admin.get(f"/api/recipes/{v1['id']}").json()["steps"][2]["params"]["target_length_mm"] == 50  # 舊版不變
    new_run = admin.post("/api/inspect/recipe", data={"work_order": "WO-1"},
                         files={"scene": ("s.png", scene_png, "image/png")}).json()
    assert new_run["version"] == 2 and new_run["verdict"] == "NG"
    assert admin.get(f"/api/runs/{old_run['run_id']}").json()["recipe_id"] == v1["id"]  # 舊 run 仍指向 v1

    # 回滾：重新啟用 v1
    assert admin.post(f"/api/recipes/{v1['id']}/activate").json()["is_active"] is True
    assert admin.get("/api/recipes/active", params={"part_no": "SC-M6-20"}).json()["version"] == 1
    versions = admin.get("/api/recipes", params={"part_no": "SC-M6-20"}).json()
    assert [(v["version"], v["is_active"], v["step_count"]) for v in versions] == [(2, False, 1), (1, True, 3)]


def test_recipe_validation(admin_client, fake_anomaly_inferencer):
    admin_client.post("/api/master/parts", json={"part_no": "P1"})
    def create(steps, part="P1"):
        return admin_client.post("/api/recipes", json={"part_no": part, "steps": steps})

    assert create([]).status_code == 422
    assert create([{"action": "codes"}], part="NOPE").status_code == 422  # 料號不在主檔
    assert create([{"action": "no_such_action"}]).status_code == 422
    assert create([{"action": "codes", "params": {"x": 1}}]).status_code == 422  # 動作不接受參數
    assert create([{"action": "count", "params": {"expected_cont": 3}}]).status_code == 422  # 未知參數
    assert create([{"action": "count", "params": {"expected_count": "abc"}}]).status_code == 422
    assert create([{"action": "anomaly"}]).status_code == 422  # 缺 category
    assert create([{"action": "anomaly", "params": {"category": "nonexistent"}}]).status_code == 422
    assert create([{"action": "assembly"}]).status_code == 422  # 黃金樣本不存在
    assert create([{"action": "codes", "image_slot": "bad slot!"}]).status_code == 422
    assert create([{"action": "colordiff", "params": {"measure_rect": [0, 0, 1, 1]}}]).status_code == 422  # 缺標準色
    assert create([{"action": "colordiff", "params": {"ref_lab": [50, 0, 0], "ref_rect": [0, 0, 1, 1], "measure_rect": [0, 0, 1, 1]}}]).status_code == 422
    assert create([{"action": "colordiff", "params": {"ref_lab": [50, 0], "measure_rect": [0, 0, 1, 1]}}]).status_code == 422
    assert create([{"action": "colordiff", "params": {"ref_lab": [50, 0, 0], "measure_rect": [0, 0, 2, 1]}}]).status_code == 422
    assert create([{"action": "codes"}]).status_code == 201


def test_assembly_and_colordiff_steps_run_from_recipe(admin_client, blank_png):
    """assembly／colordiff 不開放批次，但可用於配方；黃金樣本預設用配方料號，色差標準存在步驟參數裡。"""
    admin_client.post("/api/master/parts", json={"part_no": "ASM-1"})
    golden = _png(make_samples.make_assembly_scene())
    assert admin_client.post("/api/assembly/golden-samples", params={"part_no": "ASM-1"},
                             data={"rois": json.dumps(make_samples.ASSEMBLY_ROIS)},
                             files={"file": ("g.png", golden, "image/png")}).status_code == 200
    rect = [[40 / 600, 40 / 300, 280 / 600, 260 / 300], [320 / 600, 40 / 300, 560 / 600, 260 / 300]]
    steps = [
        {"action": "assembly", "image_slot": "asm", "label": "組裝"},
        {"action": "colordiff", "image_slot": "color", "label": "色差",
         "params": {"ref_rect": rect[0], "measure_rect": rect[1], "threshold": 3.0}},
    ]
    recipe = admin_client.post("/api/recipes", json={"part_no": "ASM-1", "steps": steps}).json()
    assert recipe["steps"][0]["params"]["golden"] is None  # 沒填就用配方料號

    missing_part = _png(make_samples.make_assembly_scene(missing_index=2))
    chips = _png(make_samples.make_color_chip_scene((200, 30, 30), (30, 30, 200)))
    body = admin_client.post("/api/inspect/recipe", data={"part_no": "ASM-1"}, files={
        "asm": ("a.png", missing_part, "image/png"), "color": ("c.png", chips, "image/png")}).json()
    assert body["verdict"] == "NG" and [s["verdict"] for s in body["steps"]] == ["NG", "NG"]
    # 沒工單的檢驗會標記為臨時
    assert admin_client.get(f"/api/runs/{body['run_id']}").json()["adhoc"] == 1

    ok = admin_client.post("/api/inspect/recipe", data={"part_no": "ASM-1"}, files={
        "asm": ("a.png", golden, "image/png"),
        "color": ("c.png", _png(make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))), "image/png")}).json()
    assert ok["verdict"] == "OK"


def test_run_request_errors(setup, gs1_valid_png_fields, measure_scene_png_marker, admin_client):
    admin, _ = setup
    main_png, _ = gs1_valid_png_fields
    scene_png, _ = measure_scene_png_marker
    only_main = {"main": ("m.png", main_png, "image/png")}
    res = admin.post("/api/inspect/recipe", data={"work_order": "WO-1"}, files=only_main)
    assert res.status_code == 422 and "scene" in res.json()["detail"]  # 缺圖片槽
    files = {"main": ("m.png", main_png, "image/png"), "scene": ("s.png", scene_png, "image/png")}
    assert admin.post("/api/inspect/recipe", files=files).status_code == 422  # 沒指定料號也沒工單
    assert admin.post("/api/inspect/recipe", data={"part_no": "NO-RECIPE"}, files=files).status_code == 404
    mismatch = admin.post("/api/inspect/recipe", data={"work_order": "WO-1", "part_no": "OTHER"}, files=files)
    assert mismatch.status_code == 422 and "不符" in mismatch.json()["detail"]
    # 停用後不能執行
    recipe_id = admin.get("/api/recipes/active", params={"part_no": "SC-M6-20"}).json()["id"]
    admin.post(f"/api/recipes/{recipe_id}/deactivate")
    assert admin.post("/api/inspect/recipe", data={"work_order": "WO-1"}, files=files).status_code == 404


def test_run_uses_trace_headers_and_temporary_work_order_is_marked(setup, gs1_valid_png_fields, measure_scene_png_marker):
    admin, _ = setup
    main_png, _ = gs1_valid_png_fields
    scene_png, _ = measure_scene_png_marker
    files = {"main": ("m.png", main_png, "image/png"), "scene": ("s.png", scene_png, "image/png")}
    res = admin.post("/api/inspect/recipe", files=files, headers={"X-Work-Order": "WO-1"})  # 用 header 而非表單
    assert res.status_code == 200
    assert admin.get(f"/api/runs/{res.json()['run_id']}").json()["adhoc"] == 0
    temp = admin.post("/api/inspect/recipe", files=files, headers={"X-Part-No": "SC-M6-20", "X-Work-Order": "TEMP-9"})
    assert temp.status_code == 200
    assert admin.get(f"/api/runs/{temp.json()['run_id']}").json()["adhoc"] == 1  # 工單不在主檔＝臨時檢驗


def test_permissions(setup, qc_client, operator_client, client, gs1_valid_png_fields, measure_scene_png_marker):
    admin, recipe = setup
    steps = [{"action": "codes"}]
    for who in (qc_client, operator_client, client):
        assert who.post("/api/recipes", json={"part_no": "SC-M6-20", "steps": steps}).status_code == 403
        assert who.post(f"/api/recipes/{recipe['id']}/activate").status_code == 403
    assert qc_client.get("/api/recipes").status_code == 200 and client.get("/api/recipes").status_code == 200
    assert operator_client.get("/api/recipes").status_code == 403
    assert operator_client.get("/api/recipes/active", params={"part_no": "SC-M6-20"}).status_code == 200  # 要看得到圖片槽
    assert operator_client.get("/api/runs").status_code == 403 and qc_client.get("/api/runs").status_code == 200
    main_png, _ = gs1_valid_png_fields
    scene_png, _ = measure_scene_png_marker
    files = {"main": ("m.png", main_png, "image/png"), "scene": ("s.png", scene_png, "image/png")}
    for runner in (operator_client, client):
        assert runner.post("/api/inspect/recipe", data={"work_order": "WO-1"}, files=files).status_code == 200


def test_recipe_changes_are_audited_including_color_standard(setup):
    admin, recipe = setup
    color = {"action": "colordiff", "params": {"ref_lab": [50.0, 20.0, 20.0], "measure_rect": [0.1, 0.1, 0.5, 0.5], "threshold": 2.5}}
    admin.post("/api/recipes", json={"part_no": "SC-M6-20", "steps": [color], "activate": False})
    admin.post(f"/api/recipes/{recipe['id']}/deactivate")
    admin.post(f"/api/recipes/{recipe['id']}/activate")
    actions = [e["action"] for e in admin.get("/api/audit", params={"target_type": "recipe"}).json()]
    assert actions.count("recipe.create") == 2 and "recipe.deactivate" in actions and "recipe.activate" in actions
    entries = admin.get("/api/audit", params={"action": "recipe.create"}).json()
    assert entries[-1]["after"]["version"] == 1 and entries[-1]["after"]["steps"][0]["action"] == "codes"
    # 色差標準（標準 Lab、量測區、門檻）是步驟參數，隨配方版本寫進稽核
    assert entries[0]["after"]["steps"][0]["params"]["ref_lab"] == [50.0, 20.0, 20.0]
    assert entries[0]["after"]["steps"][0]["params"]["threshold"] == 2.5
    assert entries[0]["after"]["is_active"] is False
    deactivated = admin.get("/api/audit", params={"action": "recipe.deactivate"}).json()[0]
    assert deactivated["before"]["active_version"] == 1 and deactivated["after"]["is_active"] is False


def test_runs_list_filters_since_id_and_api_key_readable(setup, client, gs1_valid_png_fields, gs1_expired_png_fields,
                                                         measure_scene_png_marker):
    admin, _ = setup
    scene_png, _ = measure_scene_png_marker
    ids = [_run(admin, png, scene_png).json()["run_id"] for png, _ in (gs1_valid_png_fields, gs1_expired_png_fields)]
    assert [r["id"] for r in admin.get("/api/runs").json()] == ids[::-1]
    assert [r["id"] for r in admin.get("/api/runs", params={"verdict": "NG"}).json()] == [ids[1]]
    assert [r["id"] for r in client.get("/api/runs", params={"since_id": ids[0]}).json()] == [ids[1]]  # ERP 增量輪詢，升冪


# --- run 視角統計 ---

def test_run_scope_stats_and_review_of_a_step_changes_the_run(setup, qc_client, gs1_valid_png_fields,
                                                                gs1_expired_png_fields, measure_scene_png_marker):
    admin, _ = setup
    scene_png, _ = measure_scene_png_marker
    ok_run = _run(admin, gs1_valid_png_fields[0], scene_png).json()
    ng_run = _run(admin, gs1_expired_png_fields[0], scene_png).json()
    assert (ok_run["verdict"], ng_run["verdict"]) == ("OK", "NG")

    run_stats = admin.get("/api/inspections/stats", params={"scope": "run", "group_by": "part"}).json()
    assert run_stats["total"] == 2 and run_stats["ai_verdict_counts"] == {"OK": 1, "NG": 1, "INFO": 0}
    assert run_stats["groups"][0]["part_no"] == "SC-M6-20" and run_stats["groups"][0]["yield"] == 0.5
    step_stats = admin.get("/api/inspections/stats", params={"group_by": "module"}).json()
    assert step_stats["total"] == 6  # 單步視角：2 個 run × 3 步

    # 品管把 NG run 裡「追溯碼」那一步複判成 OK → 這個 run 的最終判定變 OK，AI 判定不變
    ng_step_id = ng_run["steps"][0]["inspection_id"]
    assert qc_client.patch(f"/api/inspections/{ng_step_id}/review", json={"review_verdict": "OK"}).status_code == 200
    after = admin.get("/api/inspections/stats", params={"scope": "run"}).json()
    assert after["ai_verdict_counts"]["NG"] == 1 and after["final_verdict_counts"] == {"OK": 2, "NG": 0, "INFO": 0}
    assert after["final_yield"] == 1.0 and after["ai_yield"] == 0.5
    assert after["reviewed_count"] == 1 and after["consistency_rate"] == 0.0

    day = admin.get("/api/inspections/stats", params={"scope": "run", "group_by": "day"}).json()
    assert day["groups"][0]["total"] == 2
    pareto = admin.get("/api/inspections/stats", params={"scope": "run", "group_by": "defect"}).json()
    assert [g["label"] for g in pareto["groups"]] == ["追溯碼已過期"]
    assert admin.get("/api/inspections/stats", params={"scope": "nonsense"}).status_code == 400
    assert admin.get("/api/inspections/stats", params={"scope": "run", "group_by": "bogus"}).status_code == 400


def test_existing_step_stats_are_unchanged_when_no_scope_given(setup, gs1_valid_png_fields, measure_scene_png_marker):
    admin, _ = setup
    _run(admin, gs1_valid_png_fields[0], measure_scene_png_marker[0])
    by_module = admin.get("/api/inspections/stats", params={"group_by": "module"}).json()
    assert {g["module"] for g in by_module["groups"]} == {"codes", "anomaly", "measure"}


def test_batch_api_still_rejects_assembly_and_colordiff(client, warning_sign_png):
    for action in ("assembly", "colordiff"):
        assert client.post(f"/api/batch/{action}", files=[("files", ("a.png", warning_sign_png, "image/png"))]).status_code == 400

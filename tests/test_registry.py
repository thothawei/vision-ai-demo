"""Phase 17：辨識動作註冊表——完整性、單一來源、批次參數驗證。"""

import dataclasses
import io
import json

import pytest

from core import registry
from core.schemas import InspectionResult
from samples import make_samples


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def modules_missing_extractor() -> list[str]:
    """會判 NG 的動作（inspection）所屬 module，都必須有缺陷抽取規則，否則 NG 進不了柏拉圖。"""
    return sorted({
        s.module for s in registry.all_actions()
        if s.verdict_kind == "inspection" and registry.extractor_for_module(s.module) is None
    })


def test_every_inspection_module_has_defect_extractor():
    assert modules_missing_extractor() == []


def test_completeness_check_fails_when_an_extractor_is_removed():
    """證明上面那個檢查不是空轉：把 assembly 的 extractor 拿掉，檢查就會抓到。"""
    original = registry.get_action("assembly")
    registry.register(dataclasses.replace(original, defect_extractor=None))
    try:
        assert modules_missing_extractor() == ["assembly"]
    finally:
        registry.register(original)
    assert modules_missing_extractor() == []


def test_registry_structure_is_consistent():
    specs = registry.all_actions()
    assert len({s.action for s in specs}) == len(specs)
    for s in specs:
        assert s.category in registry.CATEGORIES, s.action
        assert s.router, s.action
        if s.batchable:
            assert callable(s.handler)
        if s.params is not None:
            assert s.params.model_config.get("extra") == "forbid", f"{s.action} 的參數模型必須拒絕未知參數"
    assert {s.tab for s in specs} == {
        "general", "docs", "anomaly", "codes", "measure", "safety", "ppe", "defect", "nameplate",
        "sevenseg", "gauge", "packaging", "pneumonia", "assembly", "colordiff", "shipping",
    }
    assert len(registry.routers()) == len({s.router for s in specs})


def test_modules_endpoint_matches_registry(client):
    body = client.get("/api/modules").json()
    assert body["categories"] == registry.CATEGORIES
    assert {a["action"] for a in body["actions"]} == {s.action for s in registry.all_actions()}
    assert "handler" not in body["actions"][0]
    assert body["modules"]["measure"] == "計數／尺寸量測"
    measure = next(a for a in body["actions"] if a["action"] == "measure")
    assert "tolerance_mm" in measure["params_schema"]["properties"]


def test_adding_an_action_only_needs_the_registry(client, warning_sign_png):
    """新增動作只改註冊表一處：批次 API、/api/modules 自動出現，不用碰 batch 的任何檔案。"""

    def fake_handler(image_bytes, params):
        return InspectionResult(module="fake_mod", verdict="INFO", items=[{"n": len(image_bytes)}],
                                engine="fake", elapsed_ms=1)

    registry.register(registry.ActionSpec(
        "fake", "fake_mod", "假動作", "其他", "fake", "info", handler=fake_handler,
    ))
    try:
        listed = client.get("/api/modules").json()
        assert any(a["action"] == "fake" and a["batchable"] for a in listed["actions"])
        assert listed["modules"]["fake_mod"] == "假動作"
        res = client.post("/api/batch/fake", files=[("files", ("a.png", warning_sign_png, "image/png"))])
        assert res.status_code == 200
        assert res.json()["info"] == 1
    finally:
        registry.unregister("fake")
    assert client.post("/api/batch/fake", files=[("files", ("a.png", warning_sign_png, "image/png"))]).status_code == 400


def test_batch_unknown_param_is_422_not_silently_ignored(client, screws_png):
    files = [("files", ("a.png", screws_png, "image/png"))]
    res = client.post("/api/batch/count", params={"expected_cont": 8}, files=files)  # 少打一個 u
    assert res.status_code == 422
    assert "expected_cont" in json.dumps(res.json(), ensure_ascii=False)


def test_batch_action_without_params_rejects_extra_params(client, warning_sign_png):
    res = client.post("/api/batch/codes", params={"mode": "ocr"},
                      files=[("files", ("a.png", warning_sign_png, "image/png"))])
    assert res.status_code == 422


def test_batch_empty_string_params_are_treated_as_missing(client, screws_png):
    res = client.post("/api/batch/count", params={"expected_count": ""},
                      files=[("files", ("a.png", screws_png, "image/png"))])
    assert res.status_code == 200
    assert res.json()["info"] == 1  # 沒有預期數量 → INFO


def test_batch_bad_param_type_is_422(client, screws_png):
    res = client.post("/api/batch/count", params={"expected_count": "abc"},
                      files=[("files", ("a.png", screws_png, "image/png"))])
    assert res.status_code == 422


def test_batch_missing_files_is_422(client):
    res = client.post("/api/batch/general", data={"x": "1"})
    assert res.status_code == 422
    assert "files" in res.json()["detail"]


def test_assembly_and_colordiff_are_not_batchable(client, warning_sign_png):
    for action in ("assembly", "colordiff"):
        res = client.post(f"/api/batch/{action}", files=[("files", ("a.png", warning_sign_png, "image/png"))])
        assert res.status_code == 400


# --- B1：原本漏掉的模組，NG 後都要出現在 NG 原因柏拉圖 ---

def _pareto_labels(client) -> set[str]:
    stats = client.get("/api/inspections/stats", params={"group_by": "defect"}).json()
    return {g["label"] for g in stats["groups"]}


def _queue(fake_llm_queue, doc_type, extract):
    responses, _ = fake_llm_queue
    responses.append(({"文件類型": doc_type}, "fake:classify"))
    responses.append((extract, "fake:extract"))


def test_previously_missing_modules_now_appear_in_pareto(client, fake_llm_queue, nameplate_png, work_order_png,
                                                        screws_png, measure_scene_png_marker,
                                                        gs1_expired_png_fields):
    # codes：效期已過期
    expired_png, _ = gs1_expired_png_fields
    assert client.post("/api/codes/decode", files={"file": ("c.png", expired_png, "image/png")}).json()["verdict"] == "NG"

    # measure：數量不符 + 長度超差
    assert client.post("/api/measure/count", params={"expected_count": 99},
                       files={"file": ("s.png", screws_png, "image/png")}).json()["verdict"] == "NG"
    png, marker_mm = measure_scene_png_marker
    assert client.post("/api/measure/measure",
                       params={"marker_size_mm": marker_mm, "target_length_mm": 80, "tolerance_mm": 1.0},
                       files={"file": ("m.png", png, "image/png")}).json()["verdict"] == "NG"

    # colordiff：色差超標
    ref, meas = [40 / 600, 40 / 300, 280 / 600, 260 / 300], [320 / 600, 40 / 300, 560 / 600, 260 / 300]
    chips = _png(make_samples.make_color_chip_scene((200, 30, 30), (30, 30, 200)))
    assert client.post("/api/color/check", params={"ref_rect": json.dumps(ref), "measure_rect": json.dumps(meas)},
                       files={"file": ("c.png", chips, "image/png")}).json()["verdict"] == "NG"

    # assembly：ROI 3 缺件
    golden = _png(make_samples.make_assembly_scene())
    client.post("/api/assembly/golden-samples", params={"part_no": "p1"},
                data={"rois": json.dumps(make_samples.ASSEMBLY_ROIS)}, files={"file": ("g.png", golden, "image/png")})
    missing = _png(make_samples.make_assembly_scene(missing_index=2))
    assert client.post("/api/assembly/inspect?part_no=p1",
                       files={"file": ("t.png", missing, "image/png")}).json()["verdict"] == "NG"

    # docs：缺必要欄位；nameplate：缺必要欄位
    _queue(fake_llm_queue, "工單", {"工單號": "WO-1"})
    assert client.post("/api/docs/extract", params={"mode": "ocr"},
                       files={"file": ("w.png", work_order_png, "image/png")}).json()["verdict"] == "NG"
    fake_llm_queue[0].append(({"廠牌": "中科精機"}, "fake:model"))
    assert client.post("/api/nameplate/read",
                       files={"file": ("n.png", nameplate_png, "image/png")}).json()["verdict"] == "NG"

    labels = _pareto_labels(client)
    assert "追溯碼已過期" in labels
    assert "數量不符" in labels
    assert "尺寸超差：長度" in labels
    assert "色差超標" in labels
    assert "組裝異常：ROI 3" in labels
    assert any(label.startswith("文件欄位驗證失敗：") for label in labels)
    assert any(label.startswith("銘牌欄位驗證失敗：") for label in labels)


def test_seven_segment_unreadable_digit_label():
    from core.defect_extractors import defect_nameplate

    assert defect_nameplate([{"讀值": "2?5", "明細": []}]) == ["七段顯示器判讀失敗"]
    assert defect_nameplate([{"讀值": "235", "明細": []}]) == []


@pytest.mark.parametrize("module", ["general", "medical_pneumonia_demo"])
def test_info_modules_have_no_extractor_requirement(module):
    specs = [s for s in registry.all_actions() if s.module == module]
    assert specs and all(s.verdict_kind == "info" for s in specs)

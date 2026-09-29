"""Phase 21：模型登錄（就地登錄 v1、版本、切換、完整性、紀錄關聯、異常檢測版本化）。"""

import json
import sys
import types

import pytest

from core import model_registry
from core.schemas import ModuleError

MISSING = "找不到權重（測試用訊息）"


@pytest.fixture
def registry_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(model_registry, "REGISTRY_DIR", tmp_path / "registry")
    monkeypatch.setattr(model_registry, "ROOT", tmp_path)  # 相對路徑以 tmp 為根，測試不碰真的 models/
    model_registry._verified.clear()
    return tmp_path / "registry"


def _weights(tmp_path, name="best.pt", content=b"weights-v1"):
    path = tmp_path / "models" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_first_use_registers_existing_weights_in_place_as_v1(client, registry_dir, tmp_path):
    weights = _weights(tmp_path)
    (weights.parent / "metrics.json").write_text(json.dumps({"map50": 0.9}))
    resolved = model_registry.resolve("pcb-defect", weights, MISSING)
    assert (resolved.model_id, resolved.version, resolved.path) == ("pcb-defect", 1, weights)
    entry = model_registry.get_active("pcb-defect")
    import hashlib

    assert entry["sha256"] == hashlib.sha256(b"weights-v1").hexdigest() and entry["size_bytes"] == 10
    assert entry["weights_path"] == "models/best.pt"  # 就地登錄：沒有複製，路徑相對專案根目錄
    assert entry["metrics"] == {"map50": 0.9} and entry["registered_by"] == "system:bootstrap"
    model_registry.resolve("pcb-defect", weights, MISSING)
    assert len(model_registry.list_versions("pcb-defect")) == 1  # 第二次使用不會再登錄


def test_bootstrap_metrics_fall_back_to_documented_numbers_with_source(client, registry_dir, tmp_path):
    model_registry.resolve("pcb-defect", _weights(tmp_path), MISSING)
    metrics = model_registry.get_active("pcb-defect")["metrics"]
    assert metrics["mAP50"] == 0.978 and "test-log" in metrics["來源"]


def test_missing_weights_and_no_active_version_give_clear_errors(client, registry_dir, tmp_path):
    with pytest.raises(ModuleError) as e:
        model_registry.resolve("pcb-defect", tmp_path / "nope.pt", MISSING)
    assert e.value.status_code == 503 and e.value.message == MISSING
    weights = _weights(tmp_path)
    model_registry.register_version("pcb-defect", weights)  # 有版本但沒有啟用
    with pytest.raises(ModuleError, match="沒有啟用中的版本"):
        model_registry.resolve("pcb-defect", weights, MISSING)
    weights.unlink()
    model_registry.activate_version("pcb-defect", 1)
    with pytest.raises(ModuleError, match="權重檔不存在"):
        model_registry.resolve("pcb-defect", None, MISSING)


def test_only_one_version_can_be_active_and_activation_switches(client, registry_dir, tmp_path):
    a, b = _weights(tmp_path, "a.pt", b"AAA"), _weights(tmp_path, "b.pt", b"BBB")
    v1 = model_registry.register_version("m", a, activate=True)
    v2 = model_registry.register_version("m", b)
    assert (v1["status"], v2["status"], v2["version"]) == ("active", "archived", 2)
    previous, current = model_registry.activate_version("m", 2)
    assert previous["version"] == 1 and current["version"] == 2
    assert [(v["version"], v["status"]) for v in model_registry.list_versions("m")] == [(2, "active"), (1, "archived")]
    from core.inspection_log import connect

    with connect() as conn, pytest.raises(Exception):  # 資料庫本身也擋：不可能有兩個 active
        conn.execute("UPDATE model_versions SET status = 'active' WHERE model_id = 'm' AND version = 1")
    with pytest.raises(LookupError):
        model_registry.activate_version("m", 99)


def test_integrity_check_refuses_tampered_weights_once_per_process(client, registry_dir, tmp_path):
    weights = _weights(tmp_path)
    model_registry.register_version("m", weights, activate=True)
    model_registry._verified.clear()  # 模擬新的程序
    model_registry.resolve("m", weights, MISSING)  # 沒被動過：通過
    weights.write_bytes(b"tampered!!")
    model_registry.resolve("m", weights, MISSING)  # 同一程序已驗證過，不重算（這是刻意的成本取捨）
    model_registry._verified.clear()  # 換成新程序
    with pytest.raises(ModuleError, match="SHA-256 與登錄不符") as e:
        model_registry.resolve("m", weights, MISSING)
    assert e.value.status_code == 500


def test_new_version_dirs_never_overwrite(client, registry_dir):
    v1, d1 = model_registry.new_version_dir("m")
    v2, d2 = model_registry.new_version_dir("m")  # 上一個還沒登錄也不會撞到同一個資料夾
    assert (v1, v2) == (1, 2) and d1 != d2 and d1.parent == registry_dir / "m"
    with pytest.raises(ValueError, match="模型 id"):
        model_registry.new_version_dir("../evil")


def test_versioned_cache_reloads_when_version_changes(client, registry_dir, tmp_path):
    loads = []
    cache = model_registry.VersionedCache()
    r1 = model_registry.Resolved("m", 1, tmp_path / "a")
    r2 = model_registry.Resolved("m", 2, tmp_path / "b")
    assert cache.get(r1, lambda p: loads.append(p) or "one") == "one"
    assert cache.get(r1, lambda p: loads.append(p) or "again") == "one"  # 同版本不重載
    assert cache.get(r2, lambda p: loads.append(p) or "two") == "two"  # 換版本才重載
    assert loads == [tmp_path / "a", tmp_path / "b"]


# --- 與服務、檢驗紀錄整合：登錄第二版 → 切換 → 新紀錄的 model_version 跟著變 ---

@pytest.fixture
def real_defect_service(monkeypatch, registry_dir, tmp_path):
    """用真的登錄流程，只把 YOLO 載入換成假的（記錄載入了哪個檔案）。"""
    from modules.defect import service

    loaded = []

    class _Box:
        def __init__(self):
            import torch

            self.cls, self.conf, self.xyxy = torch.tensor([0]), torch.tensor([0.9]), torch.tensor([[10, 10, 50, 50]])

    class _Model:
        names = {0: "open"}

        def __init__(self, path):
            self.path = path

        def predict(self, bgr, conf=0.4, verbose=False):
            return [types.SimpleNamespace(boxes=[_Box()])]

    def fake_load(path):
        loaded.append(path.name)
        return _Model(path)

    monkeypatch.setattr(service, "_load_yolo", fake_load)
    monkeypatch.setattr(service, "WEIGHTS_PATH", _weights(tmp_path, "pcb_v1.pt", b"PCB-1"))
    service._cache.clear()
    return loaded


def test_switching_active_version_changes_loaded_weights_and_recorded_model_version(
        real_defect_service, client, admin_client, tmp_path, blank_png):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "scripts"))
    import register_model

    files = {"file": ("p.png", blank_png, "image/png")}
    first = client.post("/api/defect/pcb", files=files).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{first}").json()["model_id"] == "pcb-defect"
    assert admin_client.get(f"/api/inspections/{first}").json()["model_version"] == 1

    new_weights = _weights(tmp_path, "retrained.pt", b"PCB-2")
    entry = register_model.register("pcb-defect", new_weights, {"mAP50": 0.99}, "重訓", activate=False)
    assert entry["version"] == 2 and entry["status"] == "archived"
    assert entry["weights_path"].startswith("registry/pcb-defect/v2/")  # 複製進登錄庫，不動原檔
    assert new_weights.exists()
    still_v1 = client.post("/api/defect/pcb", files=files).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{still_v1}").json()["model_version"] == 1  # 登錄不等於啟用

    res = admin_client.post("/api/models/pcb-defect/versions/2/activate")
    assert res.status_code == 200 and res.json()["status"] == "active"
    second = client.post("/api/defect/pcb", files=files).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{second}").json()["model_version"] == 2
    assert real_defect_service == ["pcb_v1.pt", "retrained.pt"]  # 切換後真的載入了新檔案

    admin_client.post("/api/models/pcb-defect/versions/1/activate")  # 回滾
    third = client.post("/api/defect/pcb", files=files).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{third}").json()["model_version"] == 1
    assert admin_client.get("/api/inspections/export.csv").text.splitlines()[0].endswith("model_id,model_version")


def test_models_without_a_model_leave_the_columns_empty(client, admin_client, fake_llm, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
    record = admin_client.get(f"/api/inspections/{res.json()['inspection_id']}").json()
    assert record["model_id"] is None and record["model_version"] is None


def test_batch_records_each_files_own_model_version_and_resets_between_files(client, admin_client, real_defect_service,
                                                                            blank_png, warning_sign_png):
    body = client.post("/api/batch/defect", files=[("files", ("a.png", blank_png, "image/png")),
                                                    ("files", ("b.png", warning_sign_png, "image/png"))]).json()
    for r in body["results"]:
        assert admin_client.get(f"/api/inspections/{r['result']['inspection_id']}").json()["model_version"] == 1


# --- API 與權限 ---

def test_models_api_activation_rules_and_audit(client, admin_client, qc_client, operator_client, registry_dir, tmp_path):
    a, b = _weights(tmp_path, "a.pt", b"AAA"), _weights(tmp_path, "b.pt", b"BBB")
    model_registry.register_version("m", a, {"acc": 0.9}, activate=True)
    model_registry.register_version("m", b, {"acc": 0.95})

    listed = admin_client.get("/api/models").json()
    assert listed[0]["model_id"] == "m" and listed[0]["active_version"] == 1 and len(listed[0]["versions"]) == 2
    assert "weights_abs" not in json.dumps(listed)  # 不把伺服器的絕對路徑露給前端
    detail = admin_client.get("/api/models/m").json()
    assert detail["versions"][0]["metrics"] == {"acc": 0.95} and detail["catalog"]["title"] == "m"
    assert admin_client.get("/api/models/none").status_code == 404

    assert qc_client.get("/api/models").status_code == 200 and client.get("/api/models").status_code == 200
    assert operator_client.get("/api/models").status_code == 403
    for who in (qc_client, operator_client, client):
        assert who.post("/api/models/m/versions/2/activate").status_code == 403

    assert admin_client.post("/api/models/m/versions/9/activate").status_code == 404
    b.write_bytes(b"corrupted")  # 回滾到壞掉的版本要擋下來
    assert admin_client.post("/api/models/m/versions/2/activate").status_code == 422
    b.write_bytes(b"BBB")
    assert admin_client.post("/api/models/m/versions/2/activate").status_code == 200
    assert admin_client.post("/api/models/m/versions/2/activate").status_code == 200  # 已經是啟用中：不重複稽核
    entries = admin_client.get("/api/audit", params={"action": "model.activate"}).json()
    assert len(entries) == 1 and entries[0]["before"] == {"version": 1} and entries[0]["after"] == {"version": 2}
    assert entries[0]["actor"] == "user:admin_test" and entries[0]["target_id"] == "m"
    b.unlink()
    assert admin_client.post("/api/models/m/versions/1/activate").status_code == 200  # a 還在
    assert admin_client.post("/api/models/m/versions/2/activate").status_code == 422  # b 已不存在


# --- 異常檢測：門檻與評分跟版本走 ---

@pytest.fixture
def anomaly_env(monkeypatch, registry_dir, tmp_path):
    from core import anomaly_training
    from modules.anomaly import service

    models_dir = tmp_path / "anomaly"
    monkeypatch.setattr(anomaly_training, "MODELS_DIR", models_dir)
    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", models_dir / "categories.json")
    monkeypatch.setattr(anomaly_training, "CUSTOM_DATA_DIR", tmp_path / "custom")
    monkeypatch.setattr(service, "MODELS_DIR", models_dir)
    service._cache.clear()
    return models_dir


def _fake_train_module(monkeypatch, fail=False):
    """替身 train_anomaly：把擬合結果寫成跟真的一樣的資料夾結構（權重、門檻、評分、指標）。"""
    counter = {"n": 0}

    def train_custom(name, good_paths, defect_paths, export_root):
        if fail:
            (export_root / "half-done.txt").parent.mkdir(parents=True, exist_ok=True)
            (export_root / "half-done.txt").write_text("x")
            raise RuntimeError("擬合失敗（測試）")
        counter["n"] += 1
        weights = export_root / "weights" / "torch" / "model.pt"
        weights.parent.mkdir(parents=True)
        weights.write_bytes(f"weights-{counter['n']}".encode())
        threshold = 10.0 * counter["n"]  # 每次擬合的距離分數尺度不同 → 門檻不同
        (export_root / "threshold.json").write_text(json.dumps({"threshold": threshold}))
        (export_root / "scores.json").write_text(json.dumps([{"label": "good", "score": threshold}]))
        (export_root / "metrics.json").write_text(json.dumps({"image_auroc": 0.9 + counter["n"] / 100}))
        return {"image_auroc": 0.9 + counter["n"] / 100, "threshold_source": "test", "fit_seconds": 1.0}

    monkeypatch.setitem(sys.modules, "train_anomaly", types.SimpleNamespace(train_custom=train_custom))


def _prepare_category(anomaly_env, name="cat"):
    from core import anomaly_training

    good = anomaly_training.CUSTOM_DATA_DIR / name / "good"
    good.mkdir(parents=True, exist_ok=True)
    (good / "a.png").write_bytes(b"x")
    anomaly_training._update_entry(name, status="fitting", source="custom")


def test_each_fit_becomes_a_new_version_and_rollback_restores_its_threshold(anomaly_env, admin_client, monkeypatch):
    from core import anomaly_training
    from modules.anomaly import service

    _fake_train_module(monkeypatch)
    _prepare_category(anomaly_env)
    anomaly_training._run_fit("cat")
    anomaly_training._run_fit("cat")

    versions = model_registry.list_versions("anomaly-cat")
    assert [(v["version"], v["status"]) for v in versions] == [(2, "active"), (1, "archived")]
    assert versions[0]["metrics"]["image_auroc"] == 0.92 and versions[1]["metrics"]["image_auroc"] == 0.91
    assert service._load_threshold("cat") == 20.0 and anomaly_training.get_scores("cat")[0]["score"] == 20.0
    assert anomaly_training.get_status("cat")["model_version"] == 2 and anomaly_training.get_status("cat")["threshold"] == 20.0

    admin_client.post("/api/models/anomaly-cat/versions/1/activate")  # 回滾：權重、門檻、評分一起回到 v1
    status = admin_client.get("/api/anomaly/categories/cat/status").json()
    listed = next(c for c in admin_client.get("/api/anomaly/categories").json() if c["name"] == "cat")
    for shown in (status, listed):  # 管理畫面顯示的版本、AUROC、門檻都要以啟用中的 v1 為準，不是最近一次擬合的 v2
        assert (shown["model_version"], shown["image_auroc"], shown["threshold"]) == (1, 0.91, 10.0)
    assert service._load_threshold("cat") == 10.0 and anomaly_training.get_scores("cat")[0]["score"] == 10.0
    assert (model_registry.REGISTRY_DIR / "anomaly-cat" / "v1" / "weights" / "torch" / "model.pt").read_bytes() == b"weights-1"


def test_threshold_change_applies_to_the_active_version_only(anomaly_env, admin_client, monkeypatch):
    from core import anomaly_training
    from modules.anomaly import service

    _fake_train_module(monkeypatch)
    _prepare_category(anomaly_env)
    anomaly_training._run_fit("cat")
    anomaly_training._run_fit("cat")
    assert admin_client.patch("/api/anomaly/categories/cat/threshold", json={"threshold": 33.3}).status_code == 200
    assert service._load_threshold("cat") == 33.3
    admin_client.post("/api/models/anomaly-cat/versions/1/activate")
    assert service._load_threshold("cat") == 10.0  # v1 的門檻沒被 v2 的調整污染
    admin_client.post("/api/models/anomaly-cat/versions/2/activate")
    assert service._load_threshold("cat") == 33.3


def test_failed_fit_leaves_no_version_and_no_half_written_folder(anomaly_env, monkeypatch):
    from core import anomaly_training

    _fake_train_module(monkeypatch)
    _prepare_category(anomaly_env)
    anomaly_training._run_fit("cat")  # 先有 v1
    _fake_train_module(monkeypatch, fail=True)
    with pytest.raises(RuntimeError):
        anomaly_training._run_fit("cat")
    assert [v["version"] for v in model_registry.list_versions("anomaly-cat")] == [1]
    assert sorted(p.name for p in (model_registry.REGISTRY_DIR / "anomaly-cat").iterdir()) == ["v1"]
    assert model_registry.get_active("anomaly-cat")["version"] == 1


def test_legacy_category_folder_is_adopted_as_v1_and_refit_does_not_overwrite_it(anomaly_env, monkeypatch):
    from core import anomaly_training
    from modules.anomaly import service

    legacy = anomaly_env / "old_cat"
    (legacy / "weights" / "torch").mkdir(parents=True)
    (legacy / "weights" / "torch" / "model.pt").write_bytes(b"legacy-weights")
    (legacy / "threshold.json").write_text(json.dumps({"threshold": 7.0}))
    resolved = model_registry.resolve("anomaly-old_cat", legacy / "weights" / "torch" / "model.pt", MISSING)
    assert resolved.version == 1 and service._load_threshold("old_cat") == 7.0  # 就地登錄，門檻仍讀舊資料夾

    _fake_train_module(monkeypatch)
    _prepare_category(anomaly_env, "old_cat")
    anomaly_training._run_fit("old_cat")
    assert (legacy / "weights" / "torch" / "model.pt").read_bytes() == b"legacy-weights"  # 舊版本原封不動
    assert service._load_threshold("old_cat") == 10.0
    model_registry.activate_version("anomaly-old_cat", 1)
    assert service._load_threshold("old_cat") == 7.0


def test_anomaly_service_missing_weights_message_is_unchanged(anomaly_env, client, warning_sign_png, monkeypatch):
    monkeypatch.setattr("modules.anomaly.service.CATEGORIES", ["metal_nut", "screw", "tile"])
    res = client.post("/api/anomaly/inspect", params={"category": "screw"}, files={"file": ("s.png", warning_sign_png, "image/png")})
    assert res.status_code == 503 and "train_anomaly.py --category screw" in res.json()["detail"]

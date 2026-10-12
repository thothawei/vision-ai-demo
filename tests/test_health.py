"""Phase 22：健康檢查、功能可用性、系統狀態。所有權重與服務都用暫存的替身狀態，測試不依賴這台機器上有沒有真的權重或 Ollama。"""

import types

import pytest
from core import health, model_registry
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _fresh_health_cache():
    health.clear_cache()
    yield
    health.clear_cache()


@pytest.fixture
def weights(tmp_path, monkeypatch):
    """把所有內建模型的預設權重位置指到暫存資料夾，並全部先放好檔案；回傳 {模型 id: 檔案路徑} 讓測試自己刪。"""
    from modules.anomaly import service as anomaly
    from modules.defect import service as defect
    from modules.medical import service as medical
    from modules.safety import service as safety

    root = tmp_path / "w"
    paths = {
        "pcb-defect": root / "pcb.pt",
        "ppe-helmet": root / "ppe.pt",
        "person-detector": root / "person.pt",
        "pneumonia-cnn": root / "cnn.pt",
        "anomaly-screw": root / "anomaly" / "screw" / "weights" / "torch" / "model.pt",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"w")
    monkeypatch.setattr(defect, "WEIGHTS_PATH", paths["pcb-defect"])
    monkeypatch.setattr(safety, "PPE_WEIGHTS_PATH", paths["ppe-helmet"])
    monkeypatch.setattr(safety, "WEIGHTS_PATH", paths["person-detector"])
    monkeypatch.setattr(medical, "WEIGHTS_PATH", paths["pneumonia-cnn"])
    monkeypatch.setattr(anomaly, "MODELS_DIR", root / "anomaly")
    monkeypatch.setattr(anomaly, "CATEGORIES", ["screw"])
    monkeypatch.setattr(model_registry, "ROOT", tmp_path)
    return paths


@pytest.fixture
def ollama_up(monkeypatch):
    """假的 Ollama：回傳設定的模型已下載。"""
    import ollama

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def list(self):
            return types.SimpleNamespace(models=[types.SimpleNamespace(model="qwen3.5:9b")])

    monkeypatch.setattr(ollama, "Client", FakeClient)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("LLM_ENGINE", "ollama")


def _features(client):
    return {f["action"]: f for f in client.get("/api/system/status").json()["features"]}


LLM_ACTIONS = {"general", "docs", "packaging", "shipping", "nameplate"}


def test_healthz_is_public_and_leaks_nothing(client):
    bare = TestClient(client.app)
    res = bare.get("/healthz")
    assert res.status_code == 200 and res.json() == {"status": "ok"}


def test_readyz_is_public_returns_only_a_summary_without_paths(client, weights, ollama_up, tmp_path):
    bare = TestClient(client.app)
    res = bare.get("/readyz")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True and body["degraded"] is False and body["unavailable_features"] == 0
    assert set(body["checks"]) == {"sqlite", "migrations", "llm", "disk", "jobs"} and set(body["checks"].values()) == {
        "ok"
    }
    text = res.text
    assert str(tmp_path) not in text and ".pt" not in text and "models/" not in text  # 公開端點不洩漏路徑與細節


def test_everything_available_when_weights_and_ollama_are_present(admin_client, weights, ollama_up):
    features = _features(admin_client)
    assert len(features) == 17 and all(f["available"] for f in features.values()), [
        f for f in features.values() if not f["available"]
    ]


def test_removing_a_weight_file_disables_only_that_feature(admin_client, client, weights, ollama_up, tmp_path):
    weights["pcb-defect"].unlink()
    status = admin_client.get("/api/system/status").json()
    features = {f["action"]: f for f in status["features"]}
    assert features["defect"]["available"] is False
    assert "PCB 瑕疵偵測" in features["defect"]["reason"] and "register_model.py" in features["defect"]["reason"]
    assert [a for a, f in features.items() if not f["available"]] == ["defect"]  # 其他功能不受影響
    assert status["tabs"]["defect"]["available"] is False and status["tabs"]["codes"]["available"] is True
    assert str(tmp_path) not in features["defect"]["reason"]
    ready = TestClient(client.app).get("/readyz")
    assert ready.status_code == 200 and ready.json()["degraded"] is True and ready.json()["unavailable_features"] == 1


def test_registered_version_whose_file_vanished_names_the_version_and_the_way_out(admin_client, weights, ollama_up):
    model_registry.register_version("pcb-defect", weights["pcb-defect"], activate=True)
    weights["pcb-defect"].unlink()
    reason = _features(admin_client)["defect"]["reason"]
    assert "v1" in reason and "權重檔不存在" in reason and "管理 → 模型" in reason
    # 沒有啟用版本
    weights["pcb-defect"].write_bytes(b"w")
    with __import__("core.inspection_log", fromlist=["connect"]).connect() as conn:
        conn.execute("UPDATE model_versions SET status = 'archived'")
        conn.commit()
    health.clear_cache()
    assert "沒有啟用中的版本" in _features(admin_client)["defect"]["reason"]


def test_first_use_bootstrappable_default_path_counts_as_available(admin_client, weights, ollama_up):
    assert model_registry.get_active("ppe-helmet") is None  # 還沒登錄過
    assert _features(admin_client)["ppe"]["available"] is True  # 預設位置有權重 → 首次使用會自動登錄
    assert model_registry.get_active("ppe-helmet") is None  # 健康檢查本身不會去登錄（不寫資料庫）


def test_ollama_down_disables_llm_features_but_not_the_rest(admin_client, weights, monkeypatch):
    import ollama

    class Down:
        def __init__(self, *a, **k):
            pass

        def list(self):
            raise ConnectionError("refused")

    monkeypatch.setattr(ollama, "Client", Down)
    monkeypatch.setenv("LLM_ENGINE", "ollama")
    status = admin_client.get("/api/system/status").json()
    features = {f["action"]: f for f in status["features"]}
    assert {a for a, f in features.items() if not f["available"]} == LLM_ACTIONS
    assert "ollama serve" in features["docs"]["reason"]
    assert all(features[a]["available"] for a in ("codes", "measure", "defect", "anomaly", "colordiff", "assembly"))
    assert status["checks"]["llm"]["ok"] is False
    assert TestClient(admin_client.app).get("/readyz").status_code == 200  # 核心（資料庫）正常，只是降級


def test_ollama_missing_model_says_how_to_pull(admin_client, weights, monkeypatch):
    import ollama

    class Other:
        def __init__(self, *a, **k):
            pass

        def list(self):
            return types.SimpleNamespace(models=[types.SimpleNamespace(model="llama3:8b")])

    monkeypatch.setattr(ollama, "Client", Other)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("LLM_ENGINE", "ollama")
    reason = _features(admin_client)["general"]["reason"]
    assert "ollama pull qwen3.5:9b" in reason


def test_ollama_model_with_latest_tag_matches(admin_client, weights, monkeypatch):
    import ollama

    class Tagged:
        def __init__(self, *a, **k):
            pass

        def list(self):
            return types.SimpleNamespace(models=[types.SimpleNamespace(model="mymodel:latest")])

    monkeypatch.setattr(ollama, "Client", Tagged)
    monkeypatch.setenv("OLLAMA_MODEL", "mymodel")
    assert _features(admin_client)["general"]["available"] is True


def test_gemini_engine_checks_only_the_key_and_never_calls_out(admin_client, weights, monkeypatch):
    import ollama

    monkeypatch.setattr(ollama, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不該連 Ollama")))
    monkeypatch.setenv("LLM_ENGINE", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert "GEMINI_API_KEY" in _features(admin_client)["general"]["reason"]
    health.clear_cache()
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    assert _features(admin_client)["general"]["available"] is True


def test_anomaly_needs_at_least_one_usable_category(admin_client, weights, ollama_up):
    assert _features(admin_client)["anomaly"]["available"] is True
    weights["anomaly-screw"].unlink()
    health.clear_cache()
    reason = _features(admin_client)["anomaly"]["reason"]
    assert "train_anomaly.py" in reason and "自訂類別" in reason


def test_readyz_is_503_only_when_the_core_is_broken(client, weights, ollama_up, monkeypatch):
    bare = TestClient(client.app)
    monkeypatch.setattr(health, "check_sqlite", lambda: {"ok": False, "message": "資料庫無法寫入：disk I/O error"})
    res = bare.get("/readyz")
    assert res.status_code == 503 and res.json()["ready"] is False and res.json()["checks"]["sqlite"] == "fail"
    assert "disk I/O" not in res.text  # 細節不外洩
    health.clear_cache()
    monkeypatch.setattr(health, "check_sqlite", lambda: {"ok": True, "message": "ok"})
    monkeypatch.setattr(health, "check_migrations", lambda: {"ok": False, "message": "schema 版本 1／程式支援 3"})
    assert bare.get("/readyz").status_code == 503


def test_sqlite_check_really_detects_a_locked_database(client, tmp_path, monkeypatch):
    """真的把資料庫鎖住（另一條連線持有寫入鎖），檢查應該失敗而不是卡住或誤報正常。"""
    import sqlite3

    from core.inspection_log import _db_path

    real_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda path, *a, **k: real_connect(path, timeout=0.2))  # 不要等預設的 5 秒
    holder = real_connect(_db_path(), timeout=0.2)
    holder.execute("BEGIN IMMEDIATE")
    try:
        result = health.check_sqlite()
    finally:
        holder.rollback()
        holder.close()
    assert result["ok"] is False and "無法寫入" in result["message"]
    assert health.check_sqlite()["ok"] is True


def test_low_disk_is_a_warning_not_a_failure(admin_client, client, weights, ollama_up, monkeypatch):
    monkeypatch.setattr(
        health.shutil, "disk_usage", lambda p: types.SimpleNamespace(total=100 << 30, used=99 << 30, free=200 << 20)
    )
    status = admin_client.get("/api/system/status").json()
    assert status["checks"]["disk"]["ok"] is False and status["checks"]["disk"]["warning"] is True
    body = TestClient(client.app).get("/readyz")
    assert body.status_code == 200 and body.json()["checks"]["disk"] == "warn" and body.json()["degraded"] is True


def test_interrupted_jobs_show_up_as_a_warning(admin_client, weights, ollama_up):
    from core import jobs

    job = jobs.create_job("anomaly_fit", {"name": "x"}, status="running")
    jobs.finish(job["id"], "interrupted", "test")
    assert "1 個背景工作被中斷" in admin_client.get("/api/system/status").json()["checks"]["jobs"]["message"]


def test_status_is_cached_for_a_few_seconds_and_force_bypasses_it(admin_client, weights, ollama_up, monkeypatch):
    calls = []
    real = health.check_llm
    monkeypatch.setattr(health, "check_llm", lambda: calls.append(1) or real())
    for _ in range(3):
        admin_client.get("/api/system/status")
    assert len(calls) == 1  # 5 秒內重複查詢不會每次都問 Ollama
    admin_client.get("/api/system/status", params={"force": True})
    assert len(calls) == 2


def test_status_requires_login_but_any_role_can_read_it(
    admin_client, qc_client, operator_client, client, weights, ollama_up
):
    assert TestClient(client.app).get("/api/system/status").status_code == 401
    for who in (admin_client, qc_client, operator_client, client):
        assert who.get("/api/system/status").status_code == 200  # 導覽灰掉每個角色都要用


def test_tab_is_available_if_any_of_its_actions_is(admin_client, weights, ollama_up):
    tabs = admin_client.get("/api/system/status").json()["tabs"]
    assert tabs["measure"]["available"] is True  # 計數與量測共用一個分頁
    assert set(tabs) >= {"general", "anomaly", "defect", "shipping"}


def test_requires_are_expressed_as_model_ids_not_stale_paths():
    from core import registry

    tokens = {t for s in registry.all_actions() for t in s.requires}
    assert tokens == {
        "llm",
        "anomaly",
        "model:pcb-defect",
        "model:person-detector",
        "model:ppe-helmet",
        "model:pneumonia-cnn",
    }


def test_startup_readiness_summary_is_logged_with_reasons(weights, ollama_up, client, caplog):
    import logging

    import main

    weights["pcb-defect"].unlink()
    with caplog.at_level(logging.INFO, logger="vision.http"):
        main._log_readiness(health, {"interrupted": [], "orphaned": []})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "啟動就緒 ready=True degraded=True" in text and "功能不可用 action=defect" in text and "PCB 瑕疵偵測" in text

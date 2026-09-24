"""Phase 12：M3 自訂類別的 zip 驗證、排隊/狀態 registry、門檻調校（不跑真的 PatchCore 擬合，
真實擬合流程見 test_live_anomaly.py 的 live 測試）。"""

import io
import zipfile

import pytest


def _make_zip(n_images: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n_images):
            zf.writestr(f"img_{i}.png", b"fake png bytes")  # 內容不重要，enqueue 階段只驗證數量/副檔名
    return buf.getvalue()


@pytest.fixture
def anomaly_paths(tmp_path, monkeypatch):
    from core import anomaly_training

    models_dir = tmp_path / "models" / "anomaly"
    custom_dir = tmp_path / "data" / "custom_anomaly"
    monkeypatch.setattr(anomaly_training, "MODELS_DIR", models_dir)
    monkeypatch.setattr(anomaly_training, "CUSTOM_DATA_DIR", custom_dir)
    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", models_dir / "categories.json")
    return anomaly_training


def test_enqueue_rejects_builtin_name(anomaly_paths):
    from core.schemas import ModuleError

    with pytest.raises(ModuleError) as exc:
        anomaly_paths.enqueue_category("metal_nut", _make_zip(20), None)
    assert exc.value.status_code == 400
    assert "內建" in exc.value.message


def test_enqueue_rejects_invalid_name(anomaly_paths):
    from core.schemas import ModuleError

    with pytest.raises(ModuleError):
        anomaly_paths.enqueue_category("有 中文/斜線", _make_zip(20), None)


def test_enqueue_rejects_too_few_good_images(anomaly_paths):
    from core.schemas import ModuleError

    with pytest.raises(ModuleError) as exc:
        anomaly_paths.enqueue_category("my_part", _make_zip(3), None)
    assert "太少" in exc.value.message


def test_enqueue_accepts_valid_zip_extracts_and_sets_queued(anomaly_paths):
    entry = anomaly_paths.enqueue_category("my_part", _make_zip(20), _make_zip(5))
    assert entry["status"] == "queued"
    assert entry["good_count"] == 20
    assert entry["defect_count"] == 5

    good_files = list((anomaly_paths.CUSTOM_DATA_DIR / "my_part" / "good").glob("*.png"))
    defect_files = list((anomaly_paths.CUSTOM_DATA_DIR / "my_part" / "defect").glob("*.png"))
    assert len(good_files) == 20
    assert len(defect_files) == 5

    status = anomaly_paths.get_status("my_part")
    assert status["status"] == "queued"


def test_enqueue_rejects_duplicate_while_in_progress(anomaly_paths):
    from core.schemas import ModuleError

    anomaly_paths.enqueue_category("my_part", _make_zip(20), None)  # 進入 queued
    with pytest.raises(ModuleError) as exc:
        anomaly_paths.enqueue_category("my_part", _make_zip(20), None)
    assert exc.value.status_code == 409


def test_enqueue_allows_resubmit_after_done_or_failed(anomaly_paths):
    anomaly_paths.enqueue_category("my_part", _make_zip(20), None)
    anomaly_paths._update_entry("my_part", status="done")
    entry = anomaly_paths.enqueue_category("my_part", _make_zip(25), None)  # 重新送出不該被擋
    assert entry["status"] == "queued"
    assert entry["good_count"] == 25


def test_set_threshold_requires_done_status(anomaly_paths):
    from core.schemas import ModuleError

    anomaly_paths.enqueue_category("my_part", _make_zip(20), None)  # 還在 queued
    with pytest.raises(ModuleError):
        anomaly_paths.set_threshold("my_part", 0.5)


def test_set_threshold_writes_file_and_updates_registry(anomaly_paths):
    anomaly_paths._update_entry("my_part", status="done")
    weights_dir = anomaly_paths.MODELS_DIR / "my_part"
    weights_dir.mkdir(parents=True)

    updated = anomaly_paths.set_threshold("my_part", 0.42)
    assert updated["threshold"] == 0.42

    import json
    saved = json.loads((weights_dir / "threshold.json").read_text())
    assert saved["threshold"] == 0.42


def test_get_scores_404_when_missing(anomaly_paths):
    from core.schemas import ModuleError

    with pytest.raises(ModuleError) as exc:
        anomaly_paths.get_scores("no_such_category")
    assert exc.value.status_code == 404


def test_worker_updates_status_on_success_and_failure(anomaly_paths, monkeypatch):
    # 直接呼叫 _process_one()（單一迭代），不起真的 while True 背景執行緒——
    # 起真執行緒會在測試結束後繼續活著搶同一個 module-level 佇列，污染後面的測試。
    calls = []

    def _fake_run_fit(name):
        calls.append(name)
        if name == "boom":
            raise RuntimeError("擬合失敗測試")

    monkeypatch.setattr(anomaly_paths, "_run_fit", _fake_run_fit)

    anomaly_paths._process_one("ok_category")
    anomaly_paths._process_one("boom")

    assert calls == ["ok_category", "boom"]
    # worker 在呼叫 _run_fit 前會先把狀態設成 fitting；假的 _run_fit 不會再往後推進成 done
    # （那是真正的 _run_fit 內部邏輯），這裡只驗證 worker 迴圈本身有正確設定 fitting/failed。
    ok_status = anomaly_paths.get_status("ok_category")
    assert ok_status["status"] == "fitting"
    boom_status = anomaly_paths.get_status("boom")
    assert boom_status["status"] == "failed"
    assert "擬合失敗測試" in boom_status["error"]


def test_router_create_category_and_list(client, anomaly_paths):
    res = client.post(
        "/api/anomaly/categories", params={"name": "router_test_cat"},
        files={"good_zip": ("good.zip", _make_zip(20), "application/zip")},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "queued"

    listed = client.get("/api/anomaly/categories").json()
    assert any(c["name"] == "router_test_cat" for c in listed)

    status = client.get("/api/anomaly/categories/router_test_cat/status").json()
    assert status["status"] == "queued"

    missing = client.get("/api/anomaly/categories/no_such/status")
    assert missing.status_code == 404

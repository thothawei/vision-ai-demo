"""Phase 22：持久化工作佇列、重啟後的恢復（中斷、接續、重試）。"""

import io
import threading
import time
import zipfile

import pytest
from core import anomaly_training, jobs
from fastapi.testclient import TestClient


def _zip(n=20) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n):
            zf.writestr(f"i{i}.png", b"x")
    return buf.getvalue()


@pytest.fixture
def training(tmp_path, monkeypatch):
    models_dir, custom_dir = tmp_path / "models" / "anomaly", tmp_path / "data" / "custom_anomaly"
    monkeypatch.setattr(anomaly_training, "MODELS_DIR", models_dir)
    monkeypatch.setattr(anomaly_training, "CUSTOM_DATA_DIR", custom_dir)
    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", models_dir / "categories.json")
    return anomaly_training


def _wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# --- 佇列本身 ---


def test_jobs_are_claimed_once_in_fifo_order(client):
    a, b = jobs.create_job("k", {"name": "a"}), jobs.create_job("k", {"name": "b"})
    first, second = jobs.claim_next("k"), jobs.claim_next("k")
    assert (first["id"], second["id"]) == (a["id"], b["id"]) and first["status"] == "running" and first["attempts"] == 1
    assert jobs.claim_next("k") is None  # 已經都被領走，不會領到第二次
    assert jobs.counts_by_status()["running"] == 2


def test_claim_can_target_a_name_and_other_kinds_are_left_alone(client):
    jobs.create_job("other", {"name": "z"})
    a = jobs.create_job("k", {"name": "a"})
    b = jobs.create_job("k", {"name": "b"})
    assert jobs.claim_next("k", "b")["id"] == b["id"]
    assert jobs.claim_next("k", "nope") is None
    assert jobs.claim_next("k")["id"] == a["id"]
    assert jobs.get_job(jobs.list_jobs("other")[0]["id"])["status"] == "queued"


def test_claim_is_atomic_under_concurrent_workers(client):
    for i in range(20):
        jobs.create_job("k", {"name": str(i)})
    claimed, lock = [], threading.Lock()

    def worker():
        while job := jobs.claim_next("k"):
            with lock:
                claimed.append(job["id"])

    threads = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(claimed) == sorted(set(claimed)) and len(claimed) == 20  # 沒有任何一個工作被領兩次


def test_recover_marks_only_running_jobs_as_interrupted(client):
    queued = jobs.create_job("k", {"name": "q"})
    running = jobs.create_job("k", {"name": "r"}, status="running")
    done = jobs.create_job("k", {"name": "d"}, status="running")
    jobs.finish(done["id"], "done")
    marked = jobs.recover_interrupted()
    assert [j["id"] for j in marked] == [running["id"]]
    assert jobs.get_job(queued["id"])["status"] == "queued" and jobs.get_job(done["id"])["status"] == "done"
    interrupted = jobs.get_job(running["id"])
    assert interrupted["status"] == "interrupted" and "重啟" in interrupted["error"] and interrupted["finished_at"]


def test_retry_rules(client):
    job = jobs.create_job("k", {"name": "a"})
    with pytest.raises(ValueError, match="只有中斷或失敗"):
        jobs.retry(job["id"])  # 排隊中不能重試
    jobs.claim_next("k")
    jobs.finish(job["id"], "failed", "boom")
    retried = jobs.retry(job["id"])
    assert retried["status"] == "queued" and retried["error"] is None
    assert jobs.claim_next("k")["attempts"] == 2  # 同一列，次數累加
    with pytest.raises(LookupError):
        jobs.retry(9999)
    with pytest.raises(ValueError):
        jobs.finish(job["id"], "queued")


# --- 擬合的整合 ---


def test_enqueue_creates_a_persistent_job_and_worker_runs_it(training, monkeypatch):
    ran = []
    monkeypatch.setattr(training, "_run_fit", lambda name: ran.append(name))
    entry = training.enqueue_category("part_a", _zip(), None, "user:admin")
    job = jobs.get_job(entry["job_id"])
    assert (job["kind"], job["status"], job["payload"], job["created_by"]) == (
        "anomaly_fit",
        "queued",
        {"name": "part_a"},
        "user:admin",
    )
    assert entry["status"] == "queued"
    training._run_job(jobs.claim_next(training.JOB_KIND))
    assert ran == ["part_a"] and jobs.get_job(job["id"])["status"] == "done"


def test_failed_fit_marks_both_the_job_and_the_category(training, monkeypatch):
    def boom(name):
        raise RuntimeError("擬合失敗（測試）")

    monkeypatch.setattr(training, "_run_fit", boom)
    entry = training.enqueue_category("part_b", _zip(), None)
    training._run_job(jobs.claim_next(training.JOB_KIND))
    job = jobs.get_job(entry["job_id"])
    assert job["status"] == "failed" and "擬合失敗" in job["error"]
    assert training.get_status("part_b")["status"] == "failed"


def test_polling_worker_thread_picks_up_queued_work_without_any_in_memory_queue(training, monkeypatch):
    """重啟後排隊中的工作靠輪詢自然接續：這裡在工作已經寫進資料庫之後才啟動 worker。"""
    monkeypatch.setattr(training, "POLL_INTERVAL_SECONDS", 0.05)
    done = []

    def fake_fit(name):
        done.append(name)
        training._update_entry(name, status="done")

    monkeypatch.setattr(training, "_run_fit", fake_fit)
    entry = training.enqueue_category("part_c", _zip(), None)  # 「重啟前」排進去的
    stop = threading.Event()
    worker = threading.Thread(target=training._worker_loop, args=(stop,), daemon=True)
    worker.start()
    try:
        assert _wait(lambda: jobs.get_job(entry["job_id"])["status"] == "done")
        assert done == ["part_c"]
        second = training.enqueue_category("part_d", _zip(), None)  # 執行中再進來的也會被接走
        assert _wait(lambda: jobs.get_job(second["job_id"])["status"] == "done")
    finally:
        stop.set()
        worker.join(timeout=3)
    assert not worker.is_alive()


def test_restart_recovery_interrupts_running_keeps_queued_and_flags_orphans(training, monkeypatch):
    monkeypatch.setattr(training, "_run_fit", lambda name: training._update_entry(name, status="done"))
    queued = training.enqueue_category("waiting", _zip(), None)
    training.enqueue_category("midway", _zip(), None)
    mid_job = jobs.claim_next(training.JOB_KIND, "midway")  # 擬合做到一半…
    training._update_entry("midway", status="fitting")
    training._update_entry("legacy", status="fitting", source="custom")  # Phase 22 之前遺留：狀態檔卡住、沒有工作紀錄
    training._update_entry("finished", status="done", source="custom")

    result = training.recover()  # …服務重啟
    assert result == {"interrupted": [mid_job["id"]], "orphaned": ["legacy"]}
    assert training.get_status("midway")["status"] == "interrupted" and "重啟" in training.get_status("midway")["error"]
    assert jobs.get_job(mid_job["id"])["status"] == "interrupted"
    assert (
        training.get_status("legacy")["status"] == "interrupted"
        and "重新上傳" in training.get_status("legacy")["error"]
    )
    assert training.get_status("waiting")["status"] == "queued" and jobs.get_job(queued["job_id"])["status"] == "queued"
    assert training.get_status("finished")["status"] == "done"
    assert training.recover() == {"interrupted": [], "orphaned": []}  # 再呼叫一次沒有新的東西要處理（可重複執行）
    # 排隊中的工作照常被 worker 接續
    training._run_job(jobs.claim_next(training.JOB_KIND))
    assert training.get_status("waiting")["status"] == "done"


def test_lifespan_runs_recovery_and_logs_readiness(training, client, monkeypatch, caplog):
    import logging

    import main
    from core import webhook

    training._update_entry("midway", status="fitting", source="custom")
    jobs.create_job(training.JOB_KIND, {"name": "midway"}, status="running")
    monkeypatch.setattr(training, "start_worker", lambda: None)  # 測試不要留下會一直輪詢的執行緒
    monkeypatch.setattr(webhook, "start_background_retry_loop", lambda: None)
    with caplog.at_level(logging.INFO, logger="vision.http"), TestClient(main.app):
        pass
    assert training.get_status("midway")["status"] == "interrupted"
    assert "啟動就緒" in "\n".join(r.getMessage() for r in caplog.records)


# --- 重試 API ---


def test_retry_api_requeues_reuses_stored_photos_and_audits(training, admin_client, monkeypatch):
    monkeypatch.setattr(training, "_run_fit", lambda name: training._update_entry(name, status="done"))
    entry = training.enqueue_category("part_e", _zip(), None)
    job = jobs.claim_next(training.JOB_KIND)
    training._update_entry("part_e", status="fitting")
    training.recover()  # 重啟 → 中斷
    assert training.get_status("part_e")["status"] == "interrupted"
    res = admin_client.post(f"/api/jobs/{entry['job_id']}/retry")
    assert res.status_code == 200 and res.json()["status"] == "queued" and res.json()["attempts"] == job["attempts"]
    assert training.get_status("part_e")["status"] == "queued" and training.get_status("part_e")["error"] is None
    retry_job = jobs.claim_next(training.JOB_KIND)
    assert retry_job["attempts"] == 2
    training._run_job(retry_job)
    assert training.get_status("part_e")["status"] == "done"
    entry_log = admin_client.get("/api/audit", params={"action": "job.retry"}).json()[0]
    assert entry_log["before"]["status"] == "interrupted" and entry_log["after"] == {
        "status": "queued",
        "name": "part_e",
    }


def test_retry_api_errors_and_permissions(training, admin_client, qc_client, operator_client, client, monkeypatch):
    monkeypatch.setattr(training, "_run_fit", lambda name: None)
    entry = training.enqueue_category("part_f", _zip(), None)
    assert admin_client.post(f"/api/jobs/{entry['job_id']}/retry").status_code == 422  # 排隊中不能重試
    assert admin_client.post("/api/jobs/9999/retry").status_code == 404
    jobs.finish(jobs.claim_next(training.JOB_KIND)["id"], "failed", "x")
    import shutil

    shutil.rmtree(training.CUSTOM_DATA_DIR / "part_f")  # 照片被刪掉就不能重試
    gone = admin_client.post(f"/api/jobs/{entry['job_id']}/retry")
    assert gone.status_code == 422 and "重新上傳" in gone.json()["detail"]
    for who in (qc_client, operator_client, client):
        assert who.post(f"/api/jobs/{entry['job_id']}/retry").status_code == 403
    assert TestClient(admin_client.app).post(f"/api/jobs/{entry['job_id']}/retry").status_code == 401


def test_jobs_list_api(training, admin_client, qc_client, operator_client, client, monkeypatch):
    monkeypatch.setattr(training, "_run_fit", lambda name: None)
    training.enqueue_category("part_g", _zip(), None)
    listed = admin_client.get("/api/jobs").json()
    assert listed[0]["payload"] == {"name": "part_g"} and listed[0]["status"] == "queued"
    assert admin_client.get("/api/jobs", params={"status": "done"}).json() == []
    assert qc_client.get("/api/jobs").status_code == 200 and client.get("/api/jobs").status_code == 200
    assert operator_client.get("/api/jobs").status_code == 403


def test_category_list_exposes_job_id_and_new_status_for_the_retry_button(training, admin_client, monkeypatch):
    monkeypatch.setattr(training, "_run_fit", lambda name: None)
    entry = training.enqueue_category("part_h", _zip(), None)
    jobs.claim_next(training.JOB_KIND)
    training.recover()
    listed = next(c for c in admin_client.get("/api/anomaly/categories").json() if c["name"] == "part_h")
    assert listed["status"] == "interrupted" and listed["job_id"] == entry["job_id"]

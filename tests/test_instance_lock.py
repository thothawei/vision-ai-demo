"""Phase 22：單一實例鎖（同一個資料庫同一時間只允許一個服務程序）。"""

import multiprocessing
import time

import pytest
from fastapi.testclient import TestClient

from core import instance_lock, jobs


def test_second_holder_is_refused_with_the_first_holders_pid(tmp_path):
    db = tmp_path / "x.db"
    first = instance_lock.acquire(db)
    try:
        with pytest.raises(instance_lock.InstanceLockError) as e:
            instance_lock.acquire(db)
        assert "同一時間只能有一個服務程序" in str(e.value) and str(__import__("os").getpid()) in str(e.value)
    finally:
        instance_lock.release(first)
    instance_lock.release(instance_lock.acquire(db))  # 釋放之後可以再拿


def test_different_databases_do_not_block_each_other(tmp_path):
    a, b = instance_lock.acquire(tmp_path / "a.db"), instance_lock.acquire(tmp_path / "b.db")
    instance_lock.release(a)
    instance_lock.release(b)


def _hold(path, ready, stop):
    from pathlib import Path

    handle = instance_lock.acquire(Path(path))
    ready.set()
    stop.wait(30)
    instance_lock.release(handle)


def test_lock_is_held_across_processes_and_released_when_the_holder_dies(tmp_path):
    db = tmp_path / "shared.db"
    ctx = multiprocessing.get_context("spawn")
    ready, stop = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=_hold, args=(str(db), ready, stop))
    proc.start()
    try:
        assert ready.wait(20)
        with pytest.raises(instance_lock.InstanceLockError, match=str(proc.pid)):
            instance_lock.acquire(db)  # 另一個程序持有
        proc.kill()  # 模擬程序被 kill -9：作業系統會釋放鎖，不會留下卡死的鎖
        proc.join(10)
        for _ in range(50):
            try:
                instance_lock.release(instance_lock.acquire(db))
                break
            except instance_lock.InstanceLockError:
                time.sleep(0.1)
        else:
            pytest.fail("持有者被 kill 之後鎖沒有釋放")
    finally:
        # 不能在子程序被 kill 之後再 stop.set()：它死時可能還握著 Event 內部的鎖，set() 會永遠卡住
        if proc.is_alive():
            proc.kill()


def test_second_app_instance_on_the_same_database_refuses_to_start_and_touches_nothing(client, monkeypatch):
    """第二個實例在拿不到鎖時，連「把 running 工作標成中斷」都不能做（這正是它要防止的事）。"""
    import main
    from core import anomaly_training, webhook

    monkeypatch.setattr(anomaly_training, "start_worker", lambda: None)  # 測試不要留下會一直輪詢的執行緒
    monkeypatch.setattr(webhook, "start_background_retry_loop", lambda: None)
    running = jobs.create_job("anomaly_fit", {"name": "busy"}, status="running")
    with TestClient(main.app):  # 第一個實例正常啟動（它會把遺留的 running 標成中斷，這是重啟的正常行為）
        fresh = jobs.create_job("anomaly_fit", {"name": "live"}, status="running")  # 第一個實例「正在做」的工作
        with pytest.raises(instance_lock.InstanceLockError):
            with TestClient(main.app):  # 第二個實例
                pass
        assert jobs.get_job(fresh["id"])["status"] == "running"  # 沒被第二個實例誤標成中斷
    assert jobs.get_job(running["id"])["status"] == "interrupted"
    with TestClient(main.app):  # 第一個實例結束、鎖釋放之後可以再啟動
        pass

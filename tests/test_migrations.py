"""Phase 21：資料庫 schema 版本管理（schema_version、migration、舊資料庫升級）。"""

import json
import sqlite3
from pathlib import Path

import pytest

from core import migrations
from core.inspection_log import connect, query_inspections

# Phase 15 當時真實的 schema（取自該版 inspection_log.py：基礎 6 欄位＋Phase 9 補的 11 個欄位＋webhook_queue）
_PHASE15_DDL = """
CREATE TABLE inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, module TEXT NOT NULL, verdict TEXT NOT NULL,
    engine TEXT NOT NULL, elapsed_ms INTEGER NOT NULL, summary_json TEXT NOT NULL,
    work_order TEXT, part_no TEXT, lot_no TEXT, station TEXT, operator TEXT, image_path TEXT, annotated_path TEXT,
    review_verdict TEXT, reviewer TEXT, reviewed_at TEXT, review_note TEXT
);
CREATE INDEX idx_inspections_module_time ON inspections(module, created_at);
CREATE TABLE webhook_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, inspection_id INTEGER NOT NULL, payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL, next_retry_at TEXT NOT NULL,
    given_up INTEGER NOT NULL DEFAULT 0
);
"""


def _make_phase15_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_PHASE15_DDL)
    conn.execute("INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json, work_order, part_no,"
                 " image_path, review_verdict, reviewer, reviewed_at, review_note) VALUES"
                 " ('2026-09-20T10:00:00', 'defect', 'NG', 'yolo', 12, ?, 'WO-1', 'P-1', 'images/2026-09-20/1_raw.png',"
                 " 'OK', '王品檢', '2026-09-21T09:00:00', '誤判')", (json.dumps([{"明細": [{"瑕疵類型": "斷路 open"}]}], ensure_ascii=False),))
    conn.execute("INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json) VALUES"
                 " ('2026-09-22T10:00:00', 'codes', 'OK', 'zxing', 3, '[]')")
    conn.execute("INSERT INTO webhook_queue (inspection_id, payload_json, attempts, created_at, next_retry_at) VALUES"
                 " (1, '{\"a\": 1}', 2, '2026-09-20T10:00:01', '2026-09-20T10:05:00')")
    conn.commit()
    conn.close()


def test_fresh_database_gets_all_migrations_and_tables(client):
    with connect() as conn:
        assert migrations.current_version(conn) == migrations.latest_version() >= 2
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = conn.execute("SELECT version, name FROM schema_version ORDER BY version").fetchall()
    assert {"inspections", "webhook_queue", "users", "audit_log", "parts", "work_orders", "recipes", "recipe_steps",
            "inspection_runs", "measurements", "model_versions", "schema_version"} <= names
    assert [(r[0], r[1]) for r in rows][:2] == [(1, "baseline"), (2, "model_registry")]


def test_phase15_database_migrates_with_all_data_intact(tmp_path, monkeypatch):
    db = tmp_path / "phase15.db"
    _make_phase15_db(db)
    monkeypatch.setenv("INSPECTION_DB", str(db))
    migrations.forget()

    rows = {r["id"]: r for r in query_inspections()}
    assert len(rows) == 2
    first = rows[1]
    assert (first["module"], first["verdict"], first["work_order"], first["part_no"], first["image_path"]) == (
        "defect", "NG", "WO-1", "P-1", "images/2026-09-20/1_raw.png")
    assert (first["review_verdict"], first["reviewer"], first["review_note"]) == ("OK", "王品檢", "誤判")
    assert first["summary"] == [{"明細": [{"瑕疵類型": "斷路 open"}]}]
    # 之後各 Phase 新增的欄位都補上了，舊資料為空
    for col in ("images", "request_id", "created_by", "run_id", "adhoc", "model_id", "model_version"):
        assert col in first and first[col] in (None, {})
    with connect() as conn:
        assert conn.execute("SELECT attempts FROM webhook_queue").fetchone()[0] == 2  # 重試佇列沒動
        assert migrations.current_version(conn) == migrations.latest_version()
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    # 升級後可以照常寫入新紀錄與統計
    from core.inspection_log import get_stats, log_inspection

    log_inspection("defect", "OK", "yolo", 5, [{"明細": []}], {"part_no": "P-1"}, model_id="pcb-defect", model_version=1)
    assert get_stats("module")["total"] == 3


def test_migrations_run_once_per_database_file_per_process(client, monkeypatch):
    calls = []
    real = migrations._discover

    def counting_discover():
        calls.append(1)
        return real()

    connect().close()  # 確保 client 用的資料庫已檢查過
    monkeypatch.setattr(migrations, "_discover", counting_discover)
    for _ in range(3):
        connect().close()
    assert calls == []  # 已檢查過的資料庫不再重跑
    migrations.forget()
    connect().close()
    assert calls == [1]


def test_database_newer_than_the_program_is_refused(tmp_path, monkeypatch):
    db = tmp_path / "future.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    conn.execute("INSERT INTO schema_version VALUES (999, 'from_the_future', '2099-01-01T00:00:00')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("INSPECTION_DB", str(db))
    migrations.forget()
    with pytest.raises(migrations.SchemaTooNew, match="999.*比這個程式支援的"):
        connect()


def test_migration_numbers_are_contiguous_and_each_module_is_complete():
    found = migrations._discover()
    assert [v for v, _, _ in found] == list(range(1, len(found) + 1))
    for _, name, module in found:
        assert callable(module.upgrade) and name


def test_baseline_is_repeatable(client):
    from importlib import import_module

    baseline = import_module("migrations.001_baseline")
    with connect() as conn:
        baseline.upgrade(conn)  # 再跑一次不會壞
        baseline.upgrade(conn)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

"""持久化工作佇列：狀態存在 SQLite（`jobs` 表），背景 worker 輪詢資料庫領取工作。

- 領取用原子的 `UPDATE … WHERE status = 'queued'`，同一個工作不會被領兩次。
- 服務重啟時，`running` 的工作標成 `interrupted`（可重試），`queued` 的工作不用特別處理——worker 下次輪詢就會撿起來。
- 假設**單一程序**執行：啟動時把所有 `running` 視為中斷，多個程序同時跑會誤判別的程序的工作。
"""

import json
import sqlite3
from datetime import datetime

from core.inspection_log import connect

STATUSES = ("queued", "running", "done", "failed", "interrupted")
RETRYABLE = ("interrupted", "failed")
INTERRUPTED_MESSAGE = "服務重啟時這個工作還沒做完，已中斷；可以重試"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _job(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d


def create_job(kind: str, payload: dict, created_by: str | None = None, status: str = "queued") -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (kind, payload_json, status, attempts, created_by, created_at, started_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, json.dumps(payload, ensure_ascii=False), status, 1 if status == "running" else 0, created_by, _now(),
             _now() if status == "running" else None))
        conn.commit()
    return get_job(cur.lastrowid)


def get_job(job_id: int) -> dict | None:
    with connect() as conn:
        return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def list_jobs(kind: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
    sql, params = "SELECT * FROM jobs WHERE 1=1", []
    for column, value in (("kind", kind), ("status", status)):
        if value:
            sql += f" AND {column} = ?"
            params.append(value)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return [_job(r) for r in conn.execute(sql, params).fetchall()]


def counts_by_status() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
    counts = {s: 0 for s in STATUSES}
    counts.update({r[0]: r[1] for r in rows})
    return counts


def claim_next(kind: str, name: str | None = None) -> dict | None:
    """領取一個排隊中的工作（最早的先做）並標成 running；沒有就回傳 None。
    `name` 只給測試與直接呼叫用：只領 payload 裡 name 相符的工作。"""
    with connect() as conn:
        rows = conn.execute("SELECT id, payload_json FROM jobs WHERE kind = ? AND status = 'queued' ORDER BY id",
                            (kind,)).fetchall()
        for row in rows:
            if name is not None and json.loads(row["payload_json"]).get("name") != name:
                continue
            claimed = conn.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, started_at = ?, finished_at = NULL, error = NULL"
                " WHERE id = ? AND status = 'queued'", (_now(), row["id"]))
            conn.commit()
            if claimed.rowcount == 1:  # 別的 worker 搶先領走的話 rowcount 是 0，換下一個
                return get_job(row["id"])
    return None


def finish(job_id: int, status: str, error: str | None = None) -> None:
    if status not in ("done", "failed", "interrupted"):
        raise ValueError(f"finish 的狀態只能是 done／failed／interrupted，目前是「{status}」")
    with connect() as conn:
        conn.execute("UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?", (status, error, _now(), job_id))
        conn.commit()


def recover_interrupted() -> list[dict]:
    """啟動時呼叫：把還在 running 的工作標成 interrupted（單一程序假設，見模組說明）。回傳被標記的工作。"""
    with connect() as conn:
        rows = conn.execute("SELECT id FROM jobs WHERE status = 'running'").fetchall()
        conn.execute("UPDATE jobs SET status = 'interrupted', error = ?, finished_at = ? WHERE status = 'running'",
                     (INTERRUPTED_MESSAGE, _now()))
        conn.commit()
    return [get_job(r["id"]) for r in rows]


def retry(job_id: int) -> dict:
    """把 interrupted／failed 的工作重新排隊（同一列，次數會在領取時 +1）。"""
    with connect() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise LookupError(f"找不到工作 id={job_id}")
        if row["status"] not in RETRYABLE:
            raise ValueError(f"只有中斷或失敗的工作可以重試，這個工作目前是 {row['status']}")
        conn.execute("UPDATE jobs SET status = 'queued', error = NULL, finished_at = NULL WHERE id = ?", (job_id,))
        conn.commit()
    return get_job(job_id)

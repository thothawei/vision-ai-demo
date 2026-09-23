"""SQLite 檢驗紀錄：每次辨識寫一筆，供查詢、匯出 CSV，之後給 manufacturing-erp 品檢模組讀取。"""

import csv
import io
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from core.schemas import InspectionResult

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "inspections.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    module TEXT NOT NULL,
    verdict TEXT NOT NULL,
    engine TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inspections_module_time ON inspections(module, created_at);
"""


def _db_path() -> Path:
    return Path(os.environ.get("INSPECTION_DB", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def log_inspection(module: str, verdict: str, engine: str, elapsed_ms: int, summary: list | dict) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                module,
                verdict,
                engine,
                elapsed_ms,
                json.dumps(summary, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def record_result(
    module: str,
    verdict: str,
    items: list[dict],
    engine: str,
    started: float,
    annotated_image: str | None = None,
) -> InspectionResult:
    """模組辨識完成後呼叫：算耗時、寫一筆紀錄、組成共用回應格式。started 為 time.perf_counter()。"""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    inspection_id = log_inspection(module, verdict, engine, elapsed_ms, items)
    return InspectionResult(
        module=module,
        verdict=verdict,
        items=items,
        annotated_image=annotated_image,
        engine=engine,
        elapsed_ms=elapsed_ms,
        inspection_id=inspection_id,
    )


def query_inspections(
    module: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """date_from / date_to 接受 ISO 日期（YYYY-MM-DD）或日期時間；date_to 只給日期時含當天整天。"""
    sql = "SELECT * FROM inspections WHERE 1=1"
    params: list = []
    if module:
        sql += " AND module = ?"
        params.append(module)
    if verdict:
        sql += " AND verdict = ?"
        params.append(verdict)
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def to_csv(records: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "module", "verdict", "engine", "elapsed_ms", "summary_json"])
    for r in records:
        writer.writerow([
            r["id"], r["created_at"], r["module"], r["verdict"], r["engine"], r["elapsed_ms"],
            json.dumps(r["summary"], ensure_ascii=False),
        ])
    return buf.getvalue()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["summary"] = json.loads(d.pop("summary_json"))
    return d

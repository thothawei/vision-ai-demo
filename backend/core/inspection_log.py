"""SQLite 檢驗紀錄：每次辨識寫一筆，供查詢、匯出 CSV、看板統計，之後給
manufacturing-erp 品檢模組讀取。

Phase 9 起新增追溯欄位（工單/料號/批號/站別/操作員）、原圖與標註圖存檔、人工複判。
舊的 inspections.db（只有 Phase 1-8 的 6 個欄位）會在 `_connect()` 時自動用
`ALTER TABLE ADD COLUMN` 補齊新欄位，不需要刪庫重建。
"""

import csv
import io
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from core import request_scope
from core.schemas import InspectionResult
from core.settings import get_settings

logger = logging.getLogger("vision.inspection")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "inspections.db"
DEFAULT_IMAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "images"

_BASE_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS webhook_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    next_retry_at TEXT NOT NULL,
    given_up INTEGER NOT NULL DEFAULT 0
);
"""

# Phase 9 新增欄位：全部可 NULL，用 ALTER TABLE ADD COLUMN 補進舊 db。
_NEW_COLUMNS = [
    "work_order", "part_no", "lot_no", "station", "operator",
    "image_path", "annotated_path",
    "review_verdict", "reviewer", "reviewed_at", "review_note",
    "images_json", "request_id",
]

_ALL_COLUMNS = [
    "id", "created_at", "module", "verdict", "engine", "elapsed_ms", "summary_json",
    *_NEW_COLUMNS,
]

def extract_defect_labels(module: str, summary: list | dict) -> list[str]:
    """從 record_result 存進 summary_json 的 items 抽出缺陷類別清單。
    沒有對應規則的模組（或 summary 格式不是預期的 list）一律回傳 []，不猜測。"""
    if not isinstance(summary, list):
        return []
    from core.registry import extractor_for_module  # 延後匯入：registry 會匯入各模組 service，而 service 匯入本檔

    fn = extractor_for_module(module)
    if fn is None:
        return []
    try:
        return fn(summary)
    except (TypeError, AttributeError):
        return []


def _db_path() -> Path:
    return get_settings().inspection_db or DEFAULT_DB_PATH


def _images_dir() -> Path:
    return get_settings().inspection_images_dir or DEFAULT_IMAGES_DIR


def _save_images_enabled() -> bool:
    return get_settings().save_images


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_BASE_SCHEMA)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(inspections)").fetchall()}
    for col in _NEW_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE inspections ADD COLUMN {col} TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inspections_work_order ON inspections(work_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inspections_part_no_time ON inspections(part_no, created_at)")
    conn.commit()


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def log_inspection(
    module: str,
    verdict: str,
    engine: str,
    elapsed_ms: int,
    summary: list | dict,
    trace: dict | None = None,
    request_id: str | None = None,
) -> int:
    trace = trace or {}
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO inspections "
            "(created_at, module, verdict, engine, elapsed_ms, summary_json, "
            " work_order, part_no, lot_no, station, operator, request_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                module,
                verdict,
                engine,
                elapsed_ms,
                json.dumps(summary, ensure_ascii=False),
                trace.get("work_order"),
                trace.get("part_no"),
                trace.get("lot_no"),
                trace.get("station"),
                trace.get("operator"),
                request_id,
            ),
        )
        return cur.lastrowid


def _decode_data_url(data_url: str) -> bytes:
    import base64
    header, _, b64data = data_url.partition(",")
    return base64.b64decode(b64data)


def _save_images(
    inspection_id: int, created_at: str, images: dict[str, tuple[bytes, str]], annotated_image: str | None
) -> tuple[str | None, str | None, dict[str, str]]:
    """存本次請求的所有圖片到 data/images/YYYY-MM-DD/<id>_<role>.<ext>。
    回傳 (image_path＝raw, annotated_path, 其他 role 的路徑)，路徑相對於 repo 根目錄。"""
    day_dir = _images_dir() / created_at[:10]
    day_dir.mkdir(parents=True, exist_ok=True)
    base = _images_dir().parents[0]

    image_path = None
    annotated_path = None
    extra: dict[str, str] = {}

    for role, (data, ext) in images.items():
        file = day_dir / f"{inspection_id}_{role}.{ext}"
        file.write_bytes(data)
        rel = str(file.relative_to(base))
        if role == "raw":
            image_path = rel
        else:
            extra[role] = rel

    if annotated_image:
        annotated_file = day_dir / f"{inspection_id}_annotated.png"
        annotated_file.write_bytes(_decode_data_url(annotated_image))
        annotated_path = str(annotated_file.relative_to(base))

    return image_path, annotated_path, extra


def record_result(
    module: str,
    verdict: str,
    items: list[dict],
    engine: str,
    started: float,
    annotated_image: str | None = None,
) -> InspectionResult:
    """模組辨識完成後呼叫：算耗時、寫一筆紀錄（含追溯資訊、原圖/標註圖）、組成共用回應格式。
    started 為 time.perf_counter()。追溯資訊、request_id 與本次請求的所有圖片從 request_scope 取得
    （由 main.py 的 middleware 與 image_io.load_image() 設定），呼叫端不用額外傳參數。"""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    trace = request_scope.get_trace()
    inspection_id = log_inspection(
        module, verdict, engine, elapsed_ms, items, trace, request_scope.get_request_id()
    )

    if _save_images_enabled():
        with _connect() as conn:
            row = conn.execute("SELECT created_at FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
        created_at = row["created_at"]
        image_path, annotated_path, extra = _save_images(
            inspection_id, created_at, request_scope.get_images(), annotated_image
        )
        if image_path or annotated_path or extra:
            with _connect() as conn:
                conn.execute(
                    "UPDATE inspections SET image_path = ?, annotated_path = ?, images_json = ? WHERE id = ?",
                    (image_path, annotated_path, json.dumps(extra) if extra else None, inspection_id),
                )

    logger.info("辨識完成 module=%s verdict=%s engine=%s elapsed_ms=%s inspection_id=%s",
                module, verdict, engine, elapsed_ms, inspection_id)

    if verdict == "NG":
        from core import webhook  # 延後匯入避免循環匯入（webhook.py 會匯入本檔的佇列函式）

        webhook.notify_ng(inspection_id, module, verdict, trace)

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
    work_order: str | None = None,
    part_no: str | None = None,
    lot_no: str | None = None,
    station: str | None = None,
    limit: int = 200,
    since_id: int | None = None,
) -> list[dict]:
    """date_from / date_to 接受 ISO 日期（YYYY-MM-DD）或日期時間；date_to 只給日期時含當天整天。

    `since_id`（Phase 10，給 ERP 增量輪詢用）：傳了就只回傳 id > since_id 的紀錄，
    且排序改成 id **升冪**（跟沒傳 since_id 時預設的降冪相反，ERP 端輪詢時要注意）。"""
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
    if work_order:
        sql += " AND work_order = ?"
        params.append(work_order)
    if part_no:
        sql += " AND part_no = ?"
        params.append(part_no)
    if lot_no:
        sql += " AND lot_no = ?"
        params.append(lot_no)
    if station:
        sql += " AND station = ?"
        params.append(station)
    if since_id is not None:
        sql += " AND id > ?"
        params.append(since_id)
        sql += " ORDER BY id ASC LIMIT ?"
    else:
        sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def query_reviewed_since(since: str, limit: int = 200) -> list[dict]:
    """給 ERP 抓「事後被改判」的紀錄：`reviewed_at > since`，ISO 時間字串，升冪排序。
    since_id 抓不到這種情況——一筆很舊的紀錄（id 很小）可能昨天才被複判。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM inspections WHERE reviewed_at IS NOT NULL AND reviewed_at > ?"
            " ORDER BY reviewed_at ASC LIMIT ?",
            (since, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_inspection(inspection_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_image_file_path(inspection_id: int, kind: str) -> Path | None:
    """kind 為 raw、annotated 或其他 role（golden、reference）。找不到紀錄或該張圖沒存就回傳 None。"""
    record = get_inspection(inspection_id)
    if record is None:
        return None
    if kind == "raw":
        rel_path = record["image_path"]
    elif kind == "annotated":
        rel_path = record["annotated_path"]
    else:
        rel_path = record["images"].get(kind)
    if not rel_path:
        return None
    full_path = _images_dir().parent / rel_path
    return full_path if full_path.exists() else None


VALID_REVIEW_VERDICTS = ("OK", "NG")


def update_review(inspection_id: int, review_verdict: str, reviewer: str | None, review_note: str | None) -> dict | None:
    if review_verdict not in VALID_REVIEW_VERDICTS:
        raise ValueError(f"review_verdict 只能是 {VALID_REVIEW_VERDICTS} 其中之一，目前是「{review_verdict}」")
    with _connect() as conn:
        existing = conn.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
        if existing is None:
            return None
        conn.execute(
            "UPDATE inspections SET review_verdict = ?, reviewer = ?, reviewed_at = ?, review_note = ? WHERE id = ?",
            (review_verdict, reviewer, datetime.now().isoformat(timespec="seconds"), review_note, inspection_id),
        )
        conn.commit()
    return get_inspection(inspection_id)


def to_csv(records: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [
        "id", "created_at", "module", "verdict", "engine", "elapsed_ms",
        "work_order", "part_no", "lot_no", "station", "operator",
        "review_verdict", "reviewer", "reviewed_at", "review_note",
        "summary_json", "request_id",
    ]
    writer.writerow(header)
    for r in records:
        writer.writerow([
            r["id"], r["created_at"], r["module"], r["verdict"], r["engine"], r["elapsed_ms"],
            r.get("work_order"), r.get("part_no"), r.get("lot_no"), r.get("station"), r.get("operator"),
            r.get("review_verdict"), r.get("reviewer"), r.get("reviewed_at"), r.get("review_note"),
            json.dumps(r["summary"], ensure_ascii=False),
            r.get("request_id"),
        ])
    return buf.getvalue()


def _final_verdict(record: dict) -> str:
    return record["review_verdict"] or record["verdict"]


def get_stats(
    group_by: str = "module",
    date_from: str | None = None,
    date_to: str | None = None,
    module: str | None = None,
) -> dict:
    """group_by: module | day | defect。
    良率 = OK / (OK + NG)，INFO 判定不列入良率分母（不是良品也不是不良品）。"""
    if group_by not in ("module", "day", "defect"):
        raise ValueError(f"group_by 只能是 module/day/defect 其中之一，目前是「{group_by}」")

    records = query_inspections(module=module, date_from=date_from, date_to=date_to, limit=1_000_000)

    ai_counts = {"OK": 0, "NG": 0, "INFO": 0}
    final_counts = {"OK": 0, "NG": 0, "INFO": 0}
    reviewed = 0
    consistent = 0
    for r in records:
        ai_counts[r["verdict"]] = ai_counts.get(r["verdict"], 0) + 1
        final = _final_verdict(r)
        final_counts[final] = final_counts.get(final, 0) + 1
        if r["review_verdict"]:
            reviewed += 1
            if r["review_verdict"] == r["verdict"]:
                consistent += 1

    def _yield_rate(counts: dict) -> float | None:
        denom = counts.get("OK", 0) + counts.get("NG", 0)
        return round(counts.get("OK", 0) / denom, 4) if denom else None

    groups: list[dict]
    if group_by == "module":
        by_module: dict[str, dict] = {}
        for r in records:
            g = by_module.setdefault(r["module"], {"module": r["module"], "total": 0, "OK": 0, "NG": 0, "INFO": 0})
            g["total"] += 1
            g[_final_verdict(r)] += 1
        groups = []
        for g in by_module.values():
            g["yield"] = _yield_rate(g)
            groups.append(g)
        groups.sort(key=lambda g: g["module"])
    elif group_by == "day":
        by_day: dict[str, dict] = {}
        for r in records:
            day = r["created_at"][:10]
            g = by_day.setdefault(day, {"day": day, "total": 0, "OK": 0, "NG": 0, "INFO": 0})
            g["total"] += 1
            g[_final_verdict(r)] += 1
        groups = []
        for g in by_day.values():
            g["yield"] = _yield_rate(g)
            groups.append(g)
        groups.sort(key=lambda g: g["day"])
    else:  # defect
        label_counts: dict[str, int] = {}
        for r in records:
            for label in extract_defect_labels(r["module"], r["summary"]):
                label_counts[label] = label_counts.get(label, 0) + 1
        total_defects = sum(label_counts.values())
        sorted_labels = sorted(label_counts.items(), key=lambda kv: kv[1], reverse=True)
        cum = 0
        groups = []
        for label, count in sorted_labels:
            cum += count
            groups.append({
                "label": label,
                "count": count,
                "pct": round(count / total_defects * 100, 2) if total_defects else 0.0,
                "cum_pct": round(cum / total_defects * 100, 2) if total_defects else 0.0,
            })

    return {
        "total": len(records),
        "ai_verdict_counts": ai_counts,
        "final_verdict_counts": final_counts,
        "ai_yield": _yield_rate(ai_counts),
        "final_yield": _yield_rate(final_counts),
        "reviewed_count": reviewed,
        "consistency_rate": round(consistent / reviewed, 4) if reviewed else None,
        "group_by": group_by,
        "groups": groups,
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["summary"] = json.loads(d.pop("summary_json"))
    images_json = d.pop("images_json", None)
    d["images"] = json.loads(images_json) if images_json else {}
    return d


# --- webhook_queue：core/webhook.py 送出失敗時的重試佇列 ---

def enqueue_webhook(inspection_id: int, payload: dict) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO webhook_queue (inspection_id, payload_json, attempts, created_at, next_retry_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (inspection_id, json.dumps(payload, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def list_pending_webhooks(limit: int = 50) -> list[dict]:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM webhook_queue WHERE given_up = 0 AND next_retry_at <= ? ORDER BY id LIMIT ?",
            (now, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_webhook_attempt(queue_id: int, success: bool, error: str | None, max_attempts: int, retry_delay_seconds: int) -> None:
    with _connect() as conn:
        if success:
            conn.execute("DELETE FROM webhook_queue WHERE id = ?", (queue_id,))
            conn.commit()
            return
        row = conn.execute("SELECT attempts FROM webhook_queue WHERE id = ?", (queue_id,)).fetchone()
        if row is None:
            return
        attempts = row["attempts"] + 1
        given_up = 1 if attempts >= max_attempts else 0
        next_retry = (datetime.now() + timedelta(seconds=retry_delay_seconds)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE webhook_queue SET attempts = ?, last_error = ?, next_retry_at = ?, given_up = ? WHERE id = ?",
            (attempts, error, next_retry, given_up, queue_id),
        )
        conn.commit()

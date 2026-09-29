"""主檔：料號與工單。工單可手動維護，也可由 ERP 以 bulk-upsert 推送。"""

import re
import sqlite3
from datetime import date, datetime

from core.inspection_log import connect

WORK_ORDER_STATUSES = ("planned", "in_progress", "done", "cancelled")
OPEN_STATUSES = ("planned", "in_progress")
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _check_code(value: str, label: str) -> str:
    value = (value or "").strip()
    if not _CODE_PATTERN.match(value):
        raise ValueError(f"{label}只能用英數字與 . _ -，長度 1–64")
    return value


def _check_date(value: str | None, label: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{label}要是 YYYY-MM-DD 日期，目前是「{value}」")


def _part_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["is_active"] = bool(d["is_active"])
    return d


# --- 料號 ---

def get_part(part_no: str) -> dict | None:
    with connect() as conn:
        return _part_row(conn.execute("SELECT * FROM parts WHERE part_no = ?", (part_no,)).fetchone())


def list_parts(active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM parts" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY part_no"
    with connect() as conn:
        return [_part_row(r) for r in conn.execute(sql).fetchall()]


def upsert_part(part_no: str, name: str = "", spec: str = "", customer: str = "", is_active: bool = True) -> tuple[dict, str]:
    """新增或更新料號；回傳 (料號, 'created'|'updated')。"""
    part_no = _check_code(part_no, "料號")
    now = _now()
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM parts WHERE part_no = ?", (part_no,)).fetchone()
        if exists:
            conn.execute("UPDATE parts SET name = ?, spec = ?, customer = ?, is_active = ?, updated_at = ? WHERE part_no = ?",
                         (name, spec, customer, 1 if is_active else 0, now, part_no))
        else:
            conn.execute("INSERT INTO parts (part_no, name, spec, customer, is_active, created_at, updated_at)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?)", (part_no, name, spec, customer, 1 if is_active else 0, now, now))
        conn.commit()
    return get_part(part_no), "updated" if exists else "created"


# --- 工單 ---

def get_work_order(work_order_no: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM work_orders WHERE work_order_no = ?", (work_order_no,)).fetchone()
    return dict(row) if row else None


def list_work_orders(open_only: bool = False, part_no: str | None = None, limit: int = 500) -> list[dict]:
    sql, params = "SELECT * FROM work_orders WHERE 1=1", []
    if open_only:
        sql += f" AND status IN ({','.join('?' * len(OPEN_STATUSES))})"
        params += list(OPEN_STATUSES)
    if part_no:
        sql += " AND part_no = ?"
        params.append(part_no)
    sql += " ORDER BY work_order_no DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def upsert_work_order(
    work_order_no: str, part_no: str, quantity: int = 0, status: str = "planned",
    start_date: str | None = None, end_date: str | None = None, lot_no: str | None = None,
) -> tuple[dict, str]:
    work_order_no = _check_code(work_order_no, "工單號")
    part_no = _check_code(part_no, "料號")
    if status not in WORK_ORDER_STATUSES:
        raise ValueError(f"狀態只能是 {WORK_ORDER_STATUSES} 其中之一，目前是「{status}」")
    if quantity < 0:
        raise ValueError("數量不可為負")
    start_date, end_date = _check_date(start_date, "開工日"), _check_date(end_date, "完工日")
    lot_no = (lot_no or "").strip() or None
    now = _now()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM parts WHERE part_no = ?", (part_no,)).fetchone() is None:
            raise ValueError(f"料號「{part_no}」不在主檔，請先建立料號")
        exists = conn.execute("SELECT 1 FROM work_orders WHERE work_order_no = ?", (work_order_no,)).fetchone()
        if exists:
            conn.execute("UPDATE work_orders SET part_no = ?, quantity = ?, status = ?, start_date = ?, end_date = ?,"
                         " lot_no = ?, updated_at = ? WHERE work_order_no = ?",
                         (part_no, quantity, status, start_date, end_date, lot_no, now, work_order_no))
        else:
            conn.execute("INSERT INTO work_orders (work_order_no, part_no, quantity, status, start_date, end_date, lot_no,"
                         " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (work_order_no, part_no, quantity, status, start_date, end_date, lot_no, now, now))
        conn.commit()
    return get_work_order(work_order_no), "updated" if exists else "created"


def bulk_upsert(kind: str, rows: list[dict]) -> dict:
    """整批更新：每一列各自成功或失敗，不因一列有誤讓整批失敗（ERP 推送才好對帳）。"""
    fn = upsert_part if kind == "parts" else upsert_work_order
    created, updated, errors = [], [], []
    for index, row in enumerate(rows):
        key_name = "part_no" if kind == "parts" else "work_order_no"
        try:
            _, outcome = fn(**row)
            (created if outcome == "created" else updated).append(row[key_name])
        except (ValueError, TypeError) as e:
            errors.append({"index": index, "key": row.get(key_name), "error": str(e)})
    return {"created": created, "updated": updated, "errors": errors}

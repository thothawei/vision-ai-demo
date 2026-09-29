"""稽核紀錄：誰、何時、對什麼做了什麼，附變更前後的值。只增不改。"""

import json
from datetime import datetime

from core import request_scope
from core.inspection_log import connect


def record(actor: str, action: str, target_type: str, target_id, before=None, after=None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO audit_log (at, actor, action, target_type, target_id, before_json, after_json, request_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"), actor, action, target_type,
                None if target_id is None else str(target_id),
                None if before is None else json.dumps(before, ensure_ascii=False),
                None if after is None else json.dumps(after, ensure_ascii=False),
                request_scope.get_request_id(),
            ),
        )
        conn.commit()
        return cur.lastrowid


def query(action: str | None = None, actor: str | None = None, target_type: str | None = None,
          date_from: str | None = None, date_to: str | None = None, limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []
    for column, value in (("action", action), ("actor", actor), ("target_type", target_type)):
        if value:
            sql += f" AND {column} = ?"
            params.append(value)
    if date_from:
        sql += " AND at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND at <= ?"
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["before"] = json.loads(d.pop("before_json")) if d["before_json"] else None
        d["after"] = json.loads(d.pop("after_json")) if d["after_json"] else None
        out.append(d)
    return out

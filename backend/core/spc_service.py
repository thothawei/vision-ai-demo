"""SPC 資料存取：從 measurements 取值、判斷規格、呼叫 core/spc.py 算圖。"""

from core import spc
from core.inspection_log import connect

NO_PART = "__none__"  # API 參數：料號為空的量測
NO_PART_LABEL = "（未指定料號）"


def _where(part_no: str | None, characteristic: str | None, date_from: str | None, date_to: str | None):
    sql, params = "WHERE 1=1", []
    if part_no:
        sql += " AND part_no IS NULL" if part_no == NO_PART else " AND part_no = ?"
        if part_no != NO_PART:
            params.append(part_no)
    if characteristic:
        sql += " AND characteristic = ?"
        params.append(characteristic)
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    return sql, params


def list_characteristics(part_no: str | None = None) -> list[dict]:
    sql, params = _where(part_no, None, None, None)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT part_no, characteristic, unit, COUNT(*) AS n, MIN(created_at) AS first_at, MAX(created_at) AS last_at,"
            f" SUM(usl IS NOT NULL OR lsl IS NOT NULL) AS with_spec FROM measurements {sql}"
            f" GROUP BY part_no, characteristic, unit ORDER BY part_no, characteristic",
            params,
        ).fetchall()
    return [
        {
            "part_no": r["part_no"] or NO_PART,
            "part_label": r["part_no"] or NO_PART_LABEL,
            "characteristic": r["characteristic"],
            "unit": r["unit"],
            "count": r["n"],
            "first_at": r["first_at"],
            "last_at": r["last_at"],
            "has_spec": bool(r["with_spec"]),
        }
        for r in rows
    ]


def load_series(
    part_no: str | None,
    characteristic: str,
    date_from: str | None = None,
    date_to: str | None = None,
    station: str | None = None,
) -> list[dict]:
    sql, params = _where(part_no, characteristic, date_from, date_to)
    if station:
        sql += " AND station = ?"
        params.append(station)
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM measurements {sql} ORDER BY created_at, id", params).fetchall()
    return [dict(r) for r in rows]


def current_spec(rows: list[dict]) -> dict:
    """規格取最近一筆有上下限的紀錄；範圍內規格變過（改了目標或公差）就回報，讓使用者知道能力指標混了兩種規格。"""
    with_spec = [r for r in rows if r["lsl"] is not None or r["usl"] is not None]
    if not with_spec:
        return {"lsl": None, "usl": None, "target": None, "changed": False}
    latest = with_spec[-1]
    distinct = {(r["lsl"], r["usl"]) for r in with_spec}
    return {"lsl": latest["lsl"], "usl": latest["usl"], "target": latest["target"], "changed": len(distinct) > 1}


def analyze(
    part_no: str | None,
    characteristic: str,
    chart: str = "xbar_r",
    subgroup_size: int = 5,
    date_from: str | None = None,
    date_to: str | None = None,
    station: str | None = None,
    run_length: int = spc.DEFAULT_RUN_LENGTH,
) -> dict:
    if chart not in ("xbar_r", "imr"):
        raise ValueError(f"chart 只能是 xbar_r 或 imr，目前是「{chart}」")
    rows = load_series(part_no, characteristic, date_from, date_to, station)
    spec = current_spec(rows)
    base = {
        "part_no": part_no,
        "characteristic": characteristic,
        "count": len(rows),
        "spec": spec,
        "unit": rows[0]["unit"] if rows else None,
    }
    if not rows:
        return {**base, "insufficient_data": True, "message": "這個條件下沒有量測資料"}
    values = [r["value"] for r in rows]
    try:
        result = (
            spc.imr(values, spec["lsl"], spec["usl"], run_length)
            if chart == "imr"
            else spc.xbar_r(values, subgroup_size, spec["lsl"], spec["usl"], run_length)
        )
    except ValueError as e:
        return {**base, "insufficient_data": True, "message": str(e)}
    labels = [r["created_at"] for r in rows]
    if chart == "xbar_r":  # 每個子群用它最後一筆的時間當標籤
        n = result["subgroup_size"]
        labels = [labels[(i + 1) * n - 1] for i in range(result["subgroups"])]
    return {**base, "insufficient_data": False, "labels": labels, "run_length": run_length, **result}

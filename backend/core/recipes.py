"""檢驗配方：一個料號有多個版本（版本不可變、同時只有一個啟用），每個版本是一串「動作＋參數＋圖片槽」。

依配方執行時，每一步各自走 `record_result`（原圖、標註圖、webhook 沿用），並用 `run_id` 關聯成一次 run；
run 的合併判定：任一「會判 NG 的動作」NG → NG；否則有步驟出錯或無法判定 → INFO；否則 OK。
`verdict_kind="info"` 的動作（現場照片辨識、指針錶…）本來就不判 OK/NG，不影響合併判定。
"""

import json
import logging
import re
from datetime import datetime

from pydantic import ValidationError

from core import master, registry, request_scope
from core.inspection_log import _final_verdict, connect, extract_defect_labels
from core.schemas import ModuleError

logger = logging.getLogger("vision.recipe")

_SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,20}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- 步驟驗證 ---


def _normalize_steps(part_no: str, steps: list[dict]) -> list[dict]:
    from modules.anomaly.service import is_valid_category
    from modules.assembly.service import list_golden_samples

    if not steps:
        raise ValueError("配方至少要有一個步驟")
    normalized = []
    for i, step in enumerate(steps, 1):
        where = f"步驟 {i}"
        action = step.get("action")
        spec = registry.get_action(action) if action else None
        if spec is None or spec.handler is None:
            usable = sorted(s.action for s in registry.all_actions() if s.handler is not None)
            raise ValueError(f"{where}：動作「{action}」不能用於配方，可用的動作：{usable}")
        raw_params = step.get("params") or {}
        if spec.params is None:
            if raw_params:
                raise ValueError(f"{where}：動作 {action} 不接受參數，收到 {sorted(raw_params)}")
            params_dict = {}
        else:
            try:
                model = spec.params.model_validate(raw_params)
            except ValidationError as e:
                detail = "；".join(
                    f"{'.'.join(str(p) for p in err['loc']) or '參數'}：{err['msg']}" for err in e.errors()
                )
                raise ValueError(f"{where}（{action}）參數不正確：{detail}")
            params_dict = model.model_dump(mode="json")
            if action == "anomaly":
                if not model.category:
                    raise ValueError(f"{where}：anomaly 需要 category")
                if not is_valid_category(model.category):
                    raise ValueError(f"{where}：異常檢測類別「{model.category}」不存在")
            if action == "assembly":
                golden = model.golden or part_no
                if golden not in {g["part_no"] for g in list_golden_samples()}:
                    raise ValueError(f"{where}：黃金樣本「{golden}」不存在，請先建立")
        slot = step.get("image_slot") or "main"
        if not _SLOT_PATTERN.match(slot):
            raise ValueError(f"{where}：圖片槽名稱只能用英數字與底線，長度 1–20")
        normalized.append(
            {"action": action, "params": params_dict, "image_slot": slot, "label": (step.get("label") or "").strip()}
        )
    return normalized


# --- 版本管理 ---


def _recipe_row(conn, row) -> dict:
    steps = conn.execute("SELECT * FROM recipe_steps WHERE recipe_id = ? ORDER BY position", (row["id"],)).fetchall()
    recipe = dict(row)
    recipe["is_active"] = bool(recipe["is_active"])
    recipe["steps"] = [
        {
            "position": s["position"],
            "action": s["action"],
            "params": json.loads(s["params_json"]),
            "image_slot": s["image_slot"],
            "label": s["label"],
        }
        for s in steps
    ]
    recipe["slots"] = list(dict.fromkeys(s["image_slot"] for s in recipe["steps"]))
    return recipe


def get_recipe(recipe_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        return _recipe_row(conn, row) if row else None


def get_active_recipe(part_no: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE part_no = ? AND is_active = 1", (part_no,)).fetchone()
        return _recipe_row(conn, row) if row else None


def list_recipes(part_no: str | None = None) -> list[dict]:
    """版本清單（不含步驟明細，用 get_recipe 取明細）。"""
    sql, params = "SELECT * FROM recipes WHERE 1=1", []
    if part_no:
        sql += " AND part_no = ?"
        params.append(part_no)
    sql += " ORDER BY part_no, version DESC"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        counts = {
            r["recipe_id"]: r["n"]
            for r in conn.execute("SELECT recipe_id, COUNT(*) AS n FROM recipe_steps GROUP BY recipe_id").fetchall()
        }
    return [{**dict(r), "is_active": bool(r["is_active"]), "step_count": counts.get(r["id"], 0)} for r in rows]


def create_recipe(part_no: str, steps: list[dict], note: str, created_by: str, activate: bool = True) -> dict:
    """新增一個版本（版本號＝該料號最大版本＋1）。既有版本永不修改。"""
    if master.get_part(part_no) is None:
        raise ValueError(f"料號「{part_no}」不在主檔，請先建立料號")
    normalized = _normalize_steps(part_no, steps)
    with connect() as conn:
        version = (
            conn.execute("SELECT MAX(version) FROM recipes WHERE part_no = ?", (part_no,)).fetchone()[0] or 0
        ) + 1
        cur = conn.execute(
            "INSERT INTO recipes (part_no, version, is_active, note, created_by, created_at) VALUES (?, ?, 0, ?, ?, ?)",
            (part_no, version, note, created_by, _now()),
        )
        recipe_id = cur.lastrowid
        for position, step in enumerate(normalized, 1):
            conn.execute(
                "INSERT INTO recipe_steps (recipe_id, position, action, params_json, image_slot, label)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    recipe_id,
                    position,
                    step["action"],
                    json.dumps(step["params"], ensure_ascii=False),
                    step["image_slot"],
                    step["label"],
                ),
            )
        conn.commit()
    if activate:
        return activate_recipe(recipe_id)
    return get_recipe(recipe_id)


def activate_recipe(recipe_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT part_no FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            raise LookupError(f"找不到配方 id={recipe_id}")
        conn.execute("UPDATE recipes SET is_active = 0 WHERE part_no = ?", (row["part_no"],))
        conn.execute("UPDATE recipes SET is_active = 1 WHERE id = ?", (recipe_id,))
        conn.commit()
    return get_recipe(recipe_id)


def deactivate_recipe(recipe_id: int) -> dict:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone() is None:
            raise LookupError(f"找不到配方 id={recipe_id}")
        conn.execute("UPDATE recipes SET is_active = 0 WHERE id = ?", (recipe_id,))
        conn.commit()
    return get_recipe(recipe_id)


# --- 合併判定 ---


def combine(steps: list[dict]) -> tuple[str, list[str]]:
    """steps 每項：position、label、action、verdict_kind、status（ok／error）、verdict、error。
    回傳 (verdict, reasons)。"""
    ng, unknown = [], []
    for s in steps:
        name = f"步驟 {s['position']} {s.get('label') or s['action']}"
        if s["status"] == "error":
            unknown.append(f"{name}：{s.get('error')}")
        elif s["verdict_kind"] == "inspection":
            if s["verdict"] == "NG":
                ng.append(f"{name}：NG")
            elif s["verdict"] == "INFO":
                unknown.append(f"{name}：無法判定")
    if ng:
        return "NG", ng
    if unknown:
        return "INFO", unknown
    return "OK", []


# --- 執行 ---


def slots_required(recipe: dict) -> list[str]:
    return recipe["slots"]


def run_recipe(recipe: dict, images: dict[str, bytes]) -> dict:
    """依序執行配方各步驟。images：圖片槽名稱 → 圖檔 bytes（呼叫端已確認槽都有給）。"""
    scope = request_scope.get_scope()
    trace = scope.trace
    with connect() as conn:
        from core.inspection_log import _is_adhoc

        cur = conn.execute(
            "INSERT INTO inspection_runs (created_at, recipe_id, part_no, work_order, lot_no, station, operator,"
            " created_by, request_id, adhoc, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')",
            (
                _now(),
                recipe["id"],
                recipe["part_no"],
                trace.get("work_order"),
                trace.get("lot_no"),
                trace.get("station"),
                trace.get("operator"),
                scope.user,
                scope.request_id,
                _is_adhoc(conn, trace.get("work_order")),
            ),
        )
        run_id = cur.lastrowid
        conn.commit()

    scope.run_id = run_id
    steps_out, meta = [], []
    try:
        for step in recipe["steps"]:
            request_scope.reset_step()
            spec = registry.get_action(step["action"])
            entry = {
                "position": step["position"],
                "action": step["action"],
                "label": step["label"],
                "image_slot": step["image_slot"],
                "verdict_kind": spec.verdict_kind if spec else "inspection",
            }
            try:
                if spec is None or spec.handler is None:
                    raise ModuleError(f"動作「{step['action']}」已不存在", 500)
                params = spec.params.model_validate(step["params"]) if spec.params else None
                if step["action"] == "assembly" and not params.golden:
                    params = params.model_copy(update={"golden": recipe["part_no"]})
                result = spec.handler(images[step["image_slot"]], params)
                entry.update(status="ok", verdict=result.verdict, inspection_id=result.inspection_id)
                steps_out.append({**entry, "result": result.model_dump()})
            except ModuleError as e:
                entry.update(status="error", verdict=None, inspection_id=None, error=e.message)
                steps_out.append({**entry})
            except Exception as e:  # noqa: BLE001 — 單一步驟的未預期錯誤不該讓整個 run 中斷
                logger.exception("配方步驟執行失敗 run_id=%s action=%s", run_id, step["action"])
                entry.update(status="error", verdict=None, inspection_id=None, error=str(e))
                steps_out.append({**entry})
            meta.append({k: v for k, v in entry.items()})
    finally:
        scope.run_id = None
        request_scope.reset_step()

    verdict, reasons = combine(meta)
    with connect() as conn:
        conn.execute(
            "UPDATE inspection_runs SET status = 'done', verdict = ?, reasons_json = ?, steps_json = ? WHERE id = ?",
            (verdict, json.dumps(reasons, ensure_ascii=False), json.dumps(meta, ensure_ascii=False), run_id),
        )
        conn.commit()
    logger.info(
        "配方檢驗完成 run_id=%s part_no=%s recipe_version=%s verdict=%s",
        run_id,
        recipe["part_no"],
        recipe["version"],
        verdict,
    )
    return {
        "run_id": run_id,
        "recipe_id": recipe["id"],
        "part_no": recipe["part_no"],
        "version": recipe["version"],
        "verdict": verdict,
        "reasons": reasons,
        "steps": steps_out,
    }


# --- 查詢 ---


def _run_row(row) -> dict:
    d = dict(row)
    d["reasons"] = json.loads(d.pop("reasons_json"))
    d["steps"] = json.loads(d.pop("steps_json"))
    return d


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM inspection_runs WHERE id = ?", (run_id,)).fetchone()
    return _run_row(row) if row else None


def list_runs(
    part_no: str | None = None,
    work_order: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    since_id: int | None = None,
) -> list[dict]:
    sql, params = "SELECT * FROM inspection_runs WHERE status = 'done'", []
    for column, value in (("part_no", part_no), ("work_order", work_order), ("verdict", verdict)):
        if value:
            sql += f" AND {column} = ?"
            params.append(value)
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    if since_id is not None:
        sql += " AND id > ? ORDER BY id ASC LIMIT ?"
        params += [since_id, limit]
    else:
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
    with connect() as conn:
        return [_run_row(r) for r in conn.execute(sql, params).fetchall()]


def get_run_stats(group_by: str = "part", date_from: str | None = None, date_to: str | None = None) -> dict:
    """run 視角的統計：以「一次配方檢驗」為單位。最終判定由各步驟的最終判定（複判優先）動態合併，
    所以複判單一步驟會改變它所屬 run 的最終判定。group_by：part | day | defect。"""
    if group_by not in ("part", "day", "defect"):
        raise ValueError(f"group_by 只能是 part/day/defect 其中之一，目前是「{group_by}」")
    runs = list_runs(date_from=date_from, date_to=date_to, limit=1_000_000)

    ids = [s["inspection_id"] for r in runs for s in r["steps"] if s.get("inspection_id")]
    records: dict[int, dict] = {}
    if ids:
        with connect() as conn:
            for chunk_start in range(0, len(ids), 500):
                chunk = ids[chunk_start : chunk_start + 500]
                rows = conn.execute(
                    f"SELECT * FROM inspections WHERE id IN ({','.join('?' * len(chunk))})", chunk
                ).fetchall()
                for row in rows:
                    from core.inspection_log import _row_to_dict

                    records[row["id"]] = _row_to_dict(row)

    ai_counts = {"OK": 0, "NG": 0, "INFO": 0}
    final_counts = {"OK": 0, "NG": 0, "INFO": 0}
    reviewed = consistent = 0
    finals: dict[int, str] = {}
    for run in runs:
        final_steps = []
        run_reviewed = False
        for s in run["steps"]:
            rec = records.get(s.get("inspection_id"))
            final_steps.append({**s, "verdict": _final_verdict(rec) if rec else s.get("verdict")})
            run_reviewed = run_reviewed or bool(rec and rec["review_verdict"])
        final, _ = combine(final_steps)
        finals[run["id"]] = final
        ai_counts[run["verdict"]] = ai_counts.get(run["verdict"], 0) + 1
        final_counts[final] += 1
        if run_reviewed:
            reviewed += 1
            consistent += final == run["verdict"]

    def yield_rate(c):
        denom = c["OK"] + c["NG"]
        return round(c["OK"] / denom, 4) if denom else None

    if group_by in ("part", "day"):
        key = "part_no" if group_by == "part" else "day"
        by: dict[str, dict] = {}
        for run in runs:
            k = run["part_no"] if group_by == "part" else run["created_at"][:10]
            g = by.setdefault(k, {key: k, "total": 0, "OK": 0, "NG": 0, "INFO": 0})
            g["total"] += 1
            g[finals[run["id"]]] += 1
        groups = sorted(by.values(), key=lambda g: g[key])
        for g in groups:
            g["yield"] = yield_rate(g)
    else:
        label_counts: dict[str, int] = {}
        for run in runs:
            for s in run["steps"]:
                rec = records.get(s.get("inspection_id"))
                if rec:
                    for label in extract_defect_labels(rec["module"], rec["summary"]):
                        label_counts[label] = label_counts.get(label, 0) + 1
        total = sum(label_counts.values())
        groups, cum = [], 0
        for label, count in sorted(label_counts.items(), key=lambda kv: kv[1], reverse=True):
            cum += count
            groups.append(
                {
                    "label": label,
                    "count": count,
                    "pct": round(count / total * 100, 2) if total else 0.0,
                    "cum_pct": round(cum / total * 100, 2) if total else 0.0,
                }
            )

    return {
        "scope": "run",
        "total": len(runs),
        "ai_verdict_counts": ai_counts,
        "final_verdict_counts": final_counts,
        "ai_yield": yield_rate(ai_counts),
        "final_yield": yield_rate(final_counts),
        "reviewed_count": reviewed,
        "consistency_rate": round(consistent / reviewed, 4) if reviewed else None,
        "group_by": group_by,
        "groups": groups,
    }

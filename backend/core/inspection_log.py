"""SQLite 檢驗紀錄：每次辨識寫一筆，供查詢、匯出 CSV、看板統計，之後給
manufacturing-erp 品檢模組讀取。

Phase 9 起新增追溯欄位（工單/料號/批號/站別/操作員）、原圖與標註圖存檔、人工複判。
舊的 inspections.db（只有 Phase 1-8 的 6 個欄位）會在 `_connect()` 時自動用
`ALTER TABLE ADD COLUMN` 補齊新欄位，不需要刪庫重建。
"""

import csv
import io
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from core import context
from core.schemas import InspectionResult

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
"""

# Phase 9 新增欄位：全部可 NULL，用 ALTER TABLE ADD COLUMN 補進舊 db。
_NEW_COLUMNS = [
    "work_order", "part_no", "lot_no", "station", "operator",
    "image_path", "annotated_path",
    "review_verdict", "reviewer", "reviewed_at", "review_note",
]

_ALL_COLUMNS = [
    "id", "created_at", "module", "verdict", "engine", "elapsed_ms", "summary_json",
    *_NEW_COLUMNS,
]

# extract_defect_labels 用：每個模組怎麼從 summary（record_result 存進去的 items）
# 抽出「缺陷類別」清單，用來畫 NG 原因柏拉圖。沒有缺陷類別概念的模組不用列在這裡，
# 一律回傳 []（例如 M9 開放式辨識、M1 追溯碼、M4 文件、M7 銘牌/七段/指針錶、M8-2 分類展示）。
_DEFECT_LABEL_EXTRACTORS = {}


def _extractor(module):
    def register(fn):
        _DEFECT_LABEL_EXTRACTORS[module] = fn
        return fn
    return register


@_extractor("defect")
def _extract_defect_labels_pcb(summary):
    labels = []
    for item in summary:
        for d in item.get("明細", []):
            if "瑕疵類型" in d:
                labels.append(d["瑕疵類型"])
    return labels


@_extractor("ppe")
def _extract_defect_labels_ppe(summary):
    labels = []
    for item in summary:
        for d in item.get("明細", []):
            if d.get("類型") == "未戴安全帽":
                labels.append("未戴安全帽")
    return labels


@_extractor("anomaly")
def _extract_defect_labels_anomaly(summary):
    labels = []
    for item in summary:
        if item.get("判定") == "異常":
            labels.append(f"外觀異常（{item.get('類別', '未知類別')}）")
    return labels


@_extractor("safety")
def _extract_defect_labels_safety(summary):
    labels = []
    for item in summary:
        for p in item.get("明細", []):
            if p.get("是否入侵"):
                labels.append("危險區域入侵")
    return labels


@_extractor("medical_packaging")
def _extract_defect_labels_packaging(summary):
    labels = []
    for item in summary:
        for problem in item.get("問題") or []:
            labels.append(f"包裝不一致：{problem}")
    return labels


def extract_defect_labels(module: str, summary: list | dict) -> list[str]:
    """從 record_result 存進 summary_json 的 items 抽出缺陷類別清單。
    沒有對應規則的模組（或 summary 格式不是預期的 list）一律回傳 []，不猜測。"""
    if not isinstance(summary, list):
        return []
    fn = _DEFECT_LABEL_EXTRACTORS.get(module)
    if fn is None:
        return []
    try:
        return fn(summary)
    except (TypeError, AttributeError):
        return []


def _db_path() -> Path:
    return Path(os.environ.get("INSPECTION_DB", DEFAULT_DB_PATH))


def _images_dir() -> Path:
    return Path(os.environ.get("INSPECTION_IMAGES_DIR", DEFAULT_IMAGES_DIR))


def _save_images_enabled() -> bool:
    return os.environ.get("SAVE_IMAGES", "true").lower() not in ("false", "0", "no")


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
) -> int:
    trace = trace or {}
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO inspections "
            "(created_at, module, verdict, engine, elapsed_ms, summary_json, "
            " work_order, part_no, lot_no, station, operator)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            ),
        )
        return cur.lastrowid


def _decode_data_url(data_url: str) -> bytes:
    import base64
    header, _, b64data = data_url.partition(",")
    return base64.b64decode(b64data)


def _save_images(inspection_id: int, created_at: str, raw: tuple[bytes, str] | None, annotated_image: str | None) -> tuple[str | None, str | None]:
    """存原圖與標註圖到 data/images/YYYY-MM-DD/，回傳 (image_path, annotated_path)（相對於 repo 根目錄）。"""
    day = created_at[:10]
    day_dir = _images_dir() / day
    day_dir.mkdir(parents=True, exist_ok=True)

    image_path = None
    annotated_path = None

    if raw is not None:
        raw_bytes, ext = raw
        raw_file = day_dir / f"{inspection_id}_raw.{ext}"
        raw_file.write_bytes(raw_bytes)
        image_path = str(raw_file.relative_to(_images_dir().parents[0]))

    if annotated_image:
        annotated_file = day_dir / f"{inspection_id}_annotated.png"
        annotated_file.write_bytes(_decode_data_url(annotated_image))
        annotated_path = str(annotated_file.relative_to(_images_dir().parents[0]))

    return image_path, annotated_path


def record_result(
    module: str,
    verdict: str,
    items: list[dict],
    engine: str,
    started: float,
    annotated_image: str | None = None,
) -> InspectionResult:
    """模組辨識完成後呼叫：算耗時、寫一筆紀錄（含追溯資訊、原圖/標註圖）、組成共用回應格式。
    started 為 time.perf_counter()。追溯資訊與原圖 bytes 從 contextvar 取得
    （由 main.py 的 middleware 與 image_io.load_image() 設定），呼叫端不用額外傳參數。"""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    trace = context.get_trace()
    inspection_id = log_inspection(module, verdict, engine, elapsed_ms, items, trace)

    if _save_images_enabled():
        with _connect() as conn:
            row = conn.execute("SELECT created_at FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
        created_at = row["created_at"]
        raw = context.get_raw_image()
        image_path, annotated_path = _save_images(inspection_id, created_at, raw, annotated_image)
        if image_path or annotated_path:
            with _connect() as conn:
                conn.execute(
                    "UPDATE inspections SET image_path = ?, annotated_path = ? WHERE id = ?",
                    (image_path, annotated_path, inspection_id),
                )

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
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_inspection(inspection_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_image_file_path(inspection_id: int, kind: str) -> Path | None:
    """kind 為 raw 或 annotated。找不到紀錄或該張圖沒存就回傳 None。"""
    record = get_inspection(inspection_id)
    if record is None:
        return None
    rel_path = record["image_path"] if kind == "raw" else record["annotated_path"]
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
        "summary_json",
    ]
    writer.writerow(header)
    for r in records:
        writer.writerow([
            r["id"], r["created_at"], r["module"], r["verdict"], r["engine"], r["elapsed_ms"],
            r.get("work_order"), r.get("part_no"), r.get("lot_no"), r.get("station"), r.get("operator"),
            r.get("review_verdict"), r.get("reviewer"), r.get("reviewed_at"), r.get("review_note"),
            json.dumps(r["summary"], ensure_ascii=False),
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
    return d

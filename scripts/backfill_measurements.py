"""把既有檢驗紀錄的量測值補進 measurements（Phase 20 之前的紀錄沒有這張表的資料）。

會寫入資料庫，所以不會在啟動時自動執行，需要你明確執行：
    python scripts/backfill_measurements.py --dry-run   # 先看會補幾筆
    python scripts/backfill_measurements.py

可重複執行（已經有 measurements 的紀錄會跳過）。歷史紀錄只補「量測值」：尺寸量測當時沒有存公差，
所以補進來的長度／寬度沒有規格上下限，只能畫管制圖；色差有存門檻，所以有上限。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core.inspection_log import connect, insert_measurements  # noqa: E402
from core.measurement_extractors import extract_measurements  # noqa: E402

MODULES = ("measure", "colordiff", "nameplate")


def backfill(dry_run: bool = False) -> dict:
    inserted, inspections = 0, 0
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM inspections WHERE module IN ({','.join('?' * len(MODULES))})"
            " AND id NOT IN (SELECT inspection_id FROM measurements) ORDER BY id",
            MODULES,
        ).fetchall()
        for row in rows:
            summary = json.loads(row["summary_json"])
            if not extract_measurements(row["module"], summary):
                continue
            inspections += 1
            if dry_run:
                inserted += len(extract_measurements(row["module"], summary))
                continue
            trace = {k: row[k] for k in ("part_no", "work_order", "lot_no", "station")}
            inserted += insert_measurements(
                conn, row["id"], row["created_at"], row["module"], summary, trace, row["run_id"]
            )
        if not dry_run:
            conn.commit()
    return {"inspections": inspections, "measurements": inserted, "dry_run": dry_run}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="補歷史量測值")
    parser.add_argument("--dry-run", action="store_true", help="只統計，不寫入")
    result = backfill(parser.parse_args().dry_run)
    print(
        f"{'（試跑）' if result['dry_run'] else ''}補了 {result['inspections']} 筆紀錄、{result['measurements']} 個量測值"
    )

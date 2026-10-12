"""依保存期限清理檢驗圖片（原圖、標註圖、黃金樣本副本）；紀錄本身保留，路徑欄位改存 `expired`。

**預設只預覽**（列出會清多少），加 `--apply` 才真的刪檔（刪掉就回不來）。
有人工複判的圖片預設不清（再訓練資料的來源），要連它們一起清請加 `--include-reviewed`。

用法：
    python scripts/cleanup_images.py                    # 預覽，保存天數取 .env 的 IMAGE_RETENTION_DAYS（預設 180）
    python scripts/cleanup_images.py --days 90 --apply
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core.inspection_log import IMAGE_EXPIRED, _images_dir, connect  # noqa: E402
from core.settings import get_settings  # noqa: E402


def _files_of(row, images_dir: Path) -> list[Path]:
    """這筆紀錄記著的圖檔（只認 images 目錄底下的，資料庫被改壞的路徑不會被拿來刪檔）。"""
    stored = [row["image_path"], row["annotated_path"], *json.loads(row["images_json"] or "{}").values()]
    base, root = images_dir.parent, images_dir.resolve()
    out = []
    for rel in stored:
        if not rel or rel == IMAGE_EXPIRED:
            continue
        path = (base / rel).resolve()
        if root in path.parents:
            out.append(path)
    return out


def cleanup(days: int, apply: bool = False, include_reviewed: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    cutoff = (now - timedelta(days=days)).isoformat(timespec="seconds")
    images_dir = _images_dir()
    summary = {
        "days": days,
        "cutoff": cutoff,
        "apply": apply,
        "inspections": 0,
        "files": 0,
        "bytes": 0,
        "skipped_reviewed": 0,
    }
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM inspections WHERE created_at < ? AND ((image_path IS NOT NULL AND image_path != ?)"
            " OR (annotated_path IS NOT NULL AND annotated_path != ?) OR images_json IS NOT NULL) ORDER BY id",
            (cutoff, IMAGE_EXPIRED, IMAGE_EXPIRED),
        ).fetchall()
        for row in rows:
            if row["review_verdict"] and not include_reviewed:
                summary["skipped_reviewed"] += 1
                continue
            files = _files_of(row, images_dir)
            summary["inspections"] += 1
            summary["files"] += sum(1 for f in files if f.exists())
            summary["bytes"] += sum(f.stat().st_size for f in files if f.exists())
            if not apply:
                continue
            for f in files:
                f.unlink(missing_ok=True)
            extra = json.loads(row["images_json"] or "{}")
            conn.execute(
                "UPDATE inspections SET image_path = ?, annotated_path = ?, images_json = ? WHERE id = ?",
                (
                    IMAGE_EXPIRED if row["image_path"] else None,
                    IMAGE_EXPIRED if row["annotated_path"] else None,
                    json.dumps({role: IMAGE_EXPIRED for role in extra}) if extra else None,
                    row["id"],
                ),
            )
        if apply:
            conn.commit()
    if apply and images_dir.exists():
        for day_dir in images_dir.iterdir():  # 順手清掉空的日期資料夾
            if day_dir.is_dir() and not any(day_dir.iterdir()):
                day_dir.rmdir()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="清理過期的檢驗圖片")
    parser.add_argument("--days", type=int, default=None, help="保存天數（預設取設定 IMAGE_RETENTION_DAYS）")
    parser.add_argument("--apply", action="store_true", help="真的刪檔（預設只預覽）")
    parser.add_argument("--include-reviewed", action="store_true", help="連有人工複判的圖片一起清")
    args = parser.parse_args()
    s = cleanup(
        args.days if args.days is not None else get_settings().image_retention_days, args.apply, args.include_reviewed
    )
    verb = "已清理" if s["apply"] else "（預覽，沒有刪任何檔）會清理"
    print(
        f"{verb}：{s['inspections']} 筆紀錄的 {s['files']} 個圖檔、{s['bytes'] / 1024 / 1024:.1f} MB"
        f"（早於 {s['cutoff']}）；因有人工複判而保留 {s['skipped_reviewed']} 筆"
    )
    if not s["apply"] and s["files"]:
        print("確認無誤後加 --apply 執行")


if __name__ == "__main__":
    main()

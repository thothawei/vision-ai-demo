"""還原 `scripts/backup.py` 產生的備份。**還原前請先停止服務。**

預設只列出「將會做什麼」，加 `--yes` 才執行。既有的資料不會被刪除，而是改名成
`<原名>.before-restore-<時間>`，確認還原結果沒問題後再自行刪除。

檢查：manifest 與每個檔案的 sha256 都要相符；備份的 schema 版本比目前程式新就拒絕（請先升級程式）；
較舊的備份還原後，第一次連線會自動升級 schema。

用法：
    python scripts/restore.py backups/vision-backup-20261001-020000.tar.gz          # 預覽
    python scripts/restore.py backups/vision-backup-20261001-020000.tar.gz --yes
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from backup import MANIFEST, sha256_of  # noqa: E402
from core import anomaly_training, migrations  # noqa: E402
from core.inspection_log import _db_path, _images_dir, connect  # noqa: E402
from modules.assembly.service import _golden_dir  # noqa: E402


class RestoreError(Exception):
    pass


def _targets(includes_models: bool, models_dir: Path) -> dict[str, Path]:
    targets = {
        "db/inspections.db": _db_path(),
        "images": _images_dir(),
        "golden_samples": _golden_dir(),
        "anomaly/categories.json": anomaly_training.REGISTRY_PATH,
    }
    if includes_models:
        targets["models"] = models_dir
    return targets


def restore(archive: Path, apply: bool = False, models_dir: Path | None = None, now: datetime | None = None) -> dict:
    models_dir = models_dir or ROOT / "models"
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(stage, filter="data")  # filter="data" 擋掉絕對路徑、.. 與特殊檔案
        if not (stage / MANIFEST).exists():
            raise RestoreError("備份檔裡沒有 manifest.json，不是 backup.py 產生的備份")
        manifest = json.loads((stage / MANIFEST).read_text(encoding="utf-8"))

        for name, info in manifest["files"].items():
            path = stage / name
            if not path.is_file():
                raise RestoreError(f"備份檔缺少 {name}")
            if sha256_of(path) != info["sha256"]:
                raise RestoreError(f"{name} 的 SHA-256 與 manifest 不符（備份檔損毀或被更動），中止還原")
        extra = (
            {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()}
            - set(manifest["files"])
            - {MANIFEST}
        )
        if extra:
            raise RestoreError(f"備份檔含有 manifest 沒列的檔案：{sorted(extra)[:3]}，中止還原")
        latest = migrations.latest_version()
        if manifest["schema_version"] > latest:
            raise RestoreError(
                f"備份的資料庫 schema 版本 {manifest['schema_version']} 比這個程式支援的 {latest} 新，請先升級程式"
            )

        targets = _targets(manifest["includes_models"], models_dir)
        plan = [
            {"source": name, "target": str(path), "replaces_existing": path.exists()}
            for name, path in targets.items()
            if (stage / name).exists()
        ]
        summary = {
            "apply": apply,
            "created_at": manifest["created_at"],
            "schema_version": manifest["schema_version"],
            "counts": manifest["counts"],
            "includes_models": manifest["includes_models"],
            "plan": plan,
            "moved_aside": [],
        }
        if not apply:
            return summary

        for name, path in targets.items():
            source = stage / name
            if not source.exists():
                continue
            if path.exists():
                aside = path.with_name(f"{path.name}.before-restore-{stamp}")
                path.rename(aside)
                summary["moved_aside"].append(str(aside))
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(path))

    migrations.forget(_db_path())
    with connect() as conn:  # 較舊的備份在這裡自動升級 schema
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RestoreError("還原後的資料庫完整性檢查未通過")
        summary["restored_counts"] = {
            "inspections": conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0],
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="還原備份（還原前請先停止服務）")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--yes", action="store_true", help="真的執行（預設只預覽）")
    args = parser.parse_args()
    try:
        s = restore(args.archive, args.yes)
    except (RestoreError, sqlite3.Error, tarfile.TarError, OSError) as e:
        sys.exit(f"還原失敗：{e}")
    print(
        f"備份時間 {s['created_at']}，schema v{s['schema_version']}，內容 {s['counts']}"
        f"{'（含 models）' if s['includes_models'] else '（不含模型權重）'}"
    )
    for item in s["plan"]:
        print(
            f"  {item['source']} → {item['target']}" + ("（既有的會先改名保留）" if item["replaces_existing"] else "")
        )
    if not s["apply"]:
        print("這只是預覽；確認無誤、服務已停止後，加 --yes 執行")
        return
    for aside in s["moved_aside"]:
        print(f"  已保留舊資料：{aside}")
    print(f"還原完成：{s['restored_counts']}")


if __name__ == "__main__":
    main()

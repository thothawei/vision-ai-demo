"""備份：資料庫（用 SQLite online backup，不是直接複製檔案）、檢驗圖片、黃金樣本、自訂類別狀態，
打成一個 `.tar.gz`，附 `manifest.json`（schema 版本、時間、每個檔案的 sha256）。

- **不含 `.env`**（祕密不進備份）。**但資料庫裡有使用者的密碼雜湊**，備份檔請妥善保管（輸出檔權限為 0600）。
- 模型權重預設不含（大、可重訓）；`--include-models` 才把整個 `models/`（含模型登錄用的權重）放進去。
  還原時沒有權重的模型會在使用時回「權重檔不存在」，需要另外放回或重新登錄。

用法：
    python scripts/backup.py                       # 輸出到 backups/
    python scripts/backup.py --out /mnt/nas/vision --include-models
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from core import anomaly_training, migrations  # noqa: E402
from core.inspection_log import _db_path, _images_dir, connect  # noqa: E402
from modules.assembly.service import _golden_dir  # noqa: E402

MANIFEST = "manifest.json"
FORMAT_VERSION = 1


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree(base: Path, prefix: str) -> list[tuple[str, Path]]:
    if not base.exists():
        return []
    return [(f"{prefix}/{p.relative_to(base).as_posix()}", p) for p in sorted(base.rglob("*")) if p.is_file()]


def _app_version() -> str:
    try:
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError):
        return "unknown"


def backup(out_dir: Path, include_models: bool = False, models_dir: Path | None = None, now: datetime | None = None) -> Path:
    now = now or datetime.now()
    models_dir = models_dir or ROOT / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"vision-backup-{now.strftime('%Y%m%d-%H%M%S')}.tar.gz"

    with connect():  # 確保資料庫存在且已升到最新 schema
        pass
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "inspections.db"
        source = sqlite3.connect(_db_path())
        dest = sqlite3.connect(snapshot)
        try:
            source.backup(dest)  # online backup：服務正在寫入時也能得到一致的快照
        finally:
            dest.close()
            source.close()
        check = sqlite3.connect(snapshot)
        counts = {
            "inspections": check.execute("SELECT COUNT(*) FROM inspections").fetchone()[0],
            "users": check.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "model_versions": check.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0],
        }
        schema_version = migrations.current_version(check)
        check.close()

        members = [("db/inspections.db", snapshot), *_tree(_images_dir(), "images"), *_tree(_golden_dir(), "golden_samples")]
        if anomaly_training.REGISTRY_PATH.exists():
            members.append(("anomaly/categories.json", anomaly_training.REGISTRY_PATH))
        if include_models:
            members += _tree(models_dir, "models")
        manifest = {
            "format": FORMAT_VERSION, "created_at": now.isoformat(timespec="seconds"), "app_version": _app_version(),
            "schema_version": schema_version, "includes_models": include_models, "counts": counts,
            "files": {name: {"size": path.stat().st_size, "sha256": sha256_of(path)} for name, path in members},
        }
        manifest_path = Path(tmp) / MANIFEST
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 備份含密碼雜湊，只有擁有者可讀
        with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
            tar.add(manifest_path, arcname=MANIFEST)
            for name, path in members:
                tar.add(path, arcname=name)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="備份資料庫、圖片與設定")
    parser.add_argument("--out", type=Path, default=ROOT / "backups")
    parser.add_argument("--include-models", action="store_true", help="連 models/ 的權重一起備份（很大）")
    args = parser.parse_args()
    path = backup(args.out, args.include_models)
    print(f"已備份：{path}（{path.stat().st_size / 1024 / 1024:.1f} MB，權限 0600）")
    print("提醒：備份檔含使用者密碼雜湊，請妥善保管；不含 .env。")


if __name__ == "__main__":
    main()

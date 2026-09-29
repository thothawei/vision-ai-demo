"""資料庫 schema 版本管理（輕量，不用 Alembic）。

`backend/migrations/NNN_名稱.py` 各自定義 `NAME` 與 `upgrade(conn)`；連線時依序套用還沒套用的版本，
版本記在 `schema_version` 表。規則：
- 已經釋出的 migration 不再修改，變更一律新增下一號。
- `001_baseline` 可重複執行，涵蓋 Phase 1–20 累積的 schema，所以任何舊狀態的資料庫都能升上來。
- 不支援降版：資料庫的版本比程式新就拒絕連線（請升級程式，或還原較舊的備份）。
- 每個程序對每個資料庫檔只檢查一次（以路徑＋inode 判斷；還原或換檔後請呼叫 `forget()`）。
"""

import importlib
import os
import pkgutil
import sqlite3
from datetime import datetime
from pathlib import Path

import migrations as _package

_checked: set[tuple[str, int | None]] = set()


class SchemaTooNew(RuntimeError):
    pass


def _discover() -> list[tuple[int, str, object]]:
    found = []
    for info in pkgutil.iter_modules(_package.__path__):
        prefix, _, _ = info.name.partition("_")
        if prefix.isdigit():
            module = importlib.import_module(f"migrations.{info.name}")
            found.append((int(prefix), getattr(module, "NAME", info.name), module))
    found.sort(key=lambda m: m[0])
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"migration 編號必須從 1 連續遞增，目前是 {versions}")
    return found


def latest_version() -> int:
    return _discover()[-1][0]


def current_version(conn: sqlite3.Connection) -> int:
    has_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not has_table:
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]


def _key(path: Path) -> tuple[str, int | None]:
    try:
        return str(path), os.stat(path).st_ino
    except FileNotFoundError:
        return str(path), None


def forget(path: Path | None = None) -> None:
    """清除「已檢查過」的記憶（還原、換檔之後用）。"""
    if path is None:
        _checked.clear()
    else:
        for key in [k for k in _checked if k[0] == str(path)]:
            _checked.discard(key)


def migrate(conn: sqlite3.Connection, path: Path) -> None:
    key = _key(path)
    if key in _checked:
        return
    migrations = _discover()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    conn.commit()
    current = current_version(conn)
    latest = migrations[-1][0]
    if current > latest:
        raise SchemaTooNew(f"資料庫的 schema 版本是 {current}，比這個程式支援的 {latest} 新；請升級程式，或還原較舊的備份")
    for version, name, module in migrations:
        if version <= current:
            continue
        module.upgrade(conn)
        conn.execute("INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                     (version, name, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    _checked.add(_key(path))

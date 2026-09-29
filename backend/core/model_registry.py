"""模型登錄：每個模型有多個版本（權重路徑＋sha256＋指標），同時只有一個啟用（資料庫用唯一索引保證）。

- 內建權重第一次使用時就地登錄成 v1（不搬檔、不複製）；新版本放 `models/registry/<模型 id>/v<N>/`，不可覆寫。
- 切換啟用版本＝回滾；服務每次請求都向 `resolve()` 取目前啟用的版本，快取以版本為鍵，所以切換立即生效。
- 每個版本在同一程序首次載入時重算 sha256，不符就拒絕載入（權重被更動或損毀）。
- 權重（尤其異常檢測的 pickle 檔）只能由伺服器端腳本登錄，網頁不提供上傳。
"""

import hashlib
import json
import logging
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core import model_catalog, request_scope
from core.inspection_log import connect
from core.schemas import ModuleError

logger = logging.getLogger("vision.model")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "models" / "registry"
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_verified: set[tuple[str, int, str]] = set()
_verify_lock = threading.Lock()


@dataclass(frozen=True)
class Resolved:
    model_id: str
    version: int
    path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stored(path: Path) -> str:
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def absolute_path(stored: str) -> Path:
    p = Path(stored)
    return p if p.is_absolute() else ROOT / p


def _version(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["metrics"] = json.loads(d.pop("metrics_json"))
    d["weights_abs"] = str(absolute_path(d["weights_path"]))
    return d


def _check_id(model_id: str) -> str:
    if not _MODEL_ID.match(model_id):
        raise ValueError(f"模型 id 只能用英數字與 . _ -，長度 1–81，目前是「{model_id}」")
    return model_id


# --- 查詢 ---

def list_versions(model_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM model_versions WHERE model_id = ? ORDER BY version DESC", (model_id,)).fetchall()
    return [_version(r) for r in rows]


def get_version(model_id: str, version: int) -> dict | None:
    with connect() as conn:
        return _version(conn.execute("SELECT * FROM model_versions WHERE model_id = ? AND version = ?",
                                     (model_id, version)).fetchone())


def get_active(model_id: str) -> dict | None:
    with connect() as conn:
        return _version(conn.execute("SELECT * FROM model_versions WHERE model_id = ? AND status = 'active'",
                                     (model_id,)).fetchone())


def list_models() -> list[dict]:
    with connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT DISTINCT model_id FROM model_versions ORDER BY model_id").fetchall()]
    out = []
    for model_id in ids:
        versions = list_versions(model_id)
        active = next((v for v in versions if v["status"] == "active"), None)
        info = model_catalog.describe(model_id)
        out.append({"model_id": model_id, "title": info["title"], "active_version": active["version"] if active else None,
                    "version_count": len(versions), "versions": versions})
    return out


# --- 登錄與切換 ---

def next_version(model_id: str) -> int:
    with connect() as conn:
        latest = conn.execute("SELECT MAX(version) FROM model_versions WHERE model_id = ?", (model_id,)).fetchone()[0] or 0
    on_disk = [int(p.name[1:]) for p in (REGISTRY_DIR / model_id).glob("v*") if p.name[1:].isdigit()]
    return max([latest, *on_disk]) + 1


def new_version_dir(model_id: str) -> tuple[int, Path]:
    """替下一個版本準備資料夾 `models/registry/<模型 id>/v<N>/`（尚未登錄；失敗時呼叫端要自己清掉）。"""
    _check_id(model_id)
    version = next_version(model_id)
    path = REGISTRY_DIR / model_id / f"v{version}"
    path.mkdir(parents=True, exist_ok=False)
    return version, path


def register_version(model_id: str, weights_path: Path, metrics: dict | None = None, note: str = "",
                     registered_by: str = "script", activate: bool = False, version: int | None = None) -> dict:
    _check_id(model_id)
    weights_path = Path(weights_path)
    if not weights_path.is_file():
        raise ValueError(f"找不到權重檔：{weights_path}")
    digest, size = sha256_file(weights_path), weights_path.stat().st_size
    with connect() as conn:
        version = version or next_version(model_id)
        conn.execute(
            "INSERT INTO model_versions (model_id, version, weights_path, sha256, size_bytes, metrics_json, status, note,"
            " registered_by, created_at) VALUES (?, ?, ?, ?, ?, ?, 'archived', ?, ?, ?)",
            (model_id, version, _stored(weights_path), digest, size, json.dumps(metrics or {}, ensure_ascii=False), note,
             registered_by, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    with _verify_lock:
        _verified.add((model_id, version, digest))  # 剛算過雜湊，不必在首次載入時重算
    logger.info("模型登錄 model=%s version=%s sha256=%s size=%s", model_id, version, digest[:12], size)
    return activate_version(model_id, version)[1] if activate else get_version(model_id, version)


def activate_version(model_id: str, version: int) -> tuple[dict | None, dict]:
    """把指定版本設為啟用（原本啟用的改 archived）。回傳 (原本啟用的版本, 新啟用的版本)。"""
    with connect() as conn:
        target = conn.execute("SELECT 1 FROM model_versions WHERE model_id = ? AND version = ?", (model_id, version)).fetchone()
        if target is None:
            raise LookupError(f"找不到模型 {model_id} 的版本 v{version}")
        previous = _version(conn.execute("SELECT * FROM model_versions WHERE model_id = ? AND status = 'active'", (model_id,)).fetchone())
        conn.execute("UPDATE model_versions SET status = 'archived' WHERE model_id = ? AND status = 'active'", (model_id,))
        conn.execute("UPDATE model_versions SET status = 'active' WHERE model_id = ? AND version = ?", (model_id, version))
        conn.commit()
    logger.info("模型啟用版本切換 model=%s from=%s to=%s", model_id, previous["version"] if previous else None, version)
    return previous, get_version(model_id, version)


# --- 服務使用 ---

def _bootstrap_metrics(model_id: str, path: Path) -> dict:
    for candidate in (path.parent / "metrics.json", path.parents[2] / "metrics.json" if len(path.parents) > 2 else None):
        if candidate and candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    return dict(model_catalog.describe(model_id).get("documented_metrics") or {})


def _verify_integrity(model_id: str, entry: dict, path: Path) -> None:
    key = (model_id, entry["version"], entry["sha256"])
    with _verify_lock:
        if key in _verified:
            return
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        logger.error("權重完整性檢查失敗 model=%s version=%s expected=%s actual=%s", model_id, entry["version"],
                     entry["sha256"][:12], actual[:12])
        raise ModuleError(
            f"模型 {model_id} v{entry['version']} 的權重檔 SHA-256 與登錄不符（檔案被更動或損毀），拒絕載入；"
            f"請還原原檔，或登錄新版本並切換（登錄 {entry['sha256'][:12]}…，實際 {actual[:12]}…）", 500)
    with _verify_lock:
        _verified.add(key)


def resolve(model_id: str, default_path: Path | None, missing_message: str) -> Resolved:
    """取得模型目前啟用的版本並驗證完整性；同時把版本記進請求範圍資料，讓檢驗紀錄寫得進去。
    該模型還沒有任何版本、而預設路徑的權重存在時，就地登錄成 v1（既有權重不用搬）。"""
    entry = get_active(model_id)
    if entry is None:
        if list_versions(model_id):
            raise ModuleError(f"模型 {model_id} 沒有啟用中的版本，請在「管理 → 模型」啟用一個版本", 503)
        if default_path is None or not Path(default_path).is_file():
            raise ModuleError(missing_message, 503)
        try:
            register_version(model_id, Path(default_path), _bootstrap_metrics(model_id, Path(default_path)),
                             "既有權重就地登錄為 v1", "system:bootstrap", activate=True)
        except sqlite3.IntegrityError:
            pass  # 同時有另一個請求先登錄了
        entry = get_active(model_id)
    path = Path(entry["weights_abs"])
    if not path.is_file():
        raise ModuleError(f"模型 {model_id} v{entry['version']} 的權重檔不存在：{path}", 503)
    _verify_integrity(model_id, entry, path)
    request_scope.set_model(model_id, entry["version"])
    return Resolved(model_id, entry["version"], path)


def active_anomaly_root(category: str, fallback: Path) -> Path:
    """異常檢測類別「目前啟用版本」的資料夾（權重在 `<root>/weights/torch/model.pt`，門檻、評分、指標檔跟權重放在
    同一個 root）。沒有登錄（尚未使用過）時退回舊的每類別資料夾。"""
    entry = get_active(f"anomaly-{category}")
    return Path(entry["weights_abs"]).parents[2] if entry else fallback


class VersionedCache:
    """每個模型只快取目前版本的載入結果；版本換了就丟掉舊的重新載入。"""

    def __init__(self):
        self._items: dict[str, tuple[int, object]] = {}
        self._lock = threading.Lock()

    def get(self, resolved: Resolved, loader):
        with self._lock:
            cached = self._items.get(resolved.model_id)
            if cached and cached[0] == resolved.version:
                return cached[1]
            obj = loader(resolved.path)
            self._items[resolved.model_id] = (resolved.version, obj)
            return obj

    def drop(self, model_id: str) -> None:
        with self._lock:
            self._items.pop(model_id, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

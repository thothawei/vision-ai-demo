"""健康檢查與功能可用性：資料庫、migration、Ollama、磁碟、擬合工作，以及每個辨識功能需要的模型與服務。

只做便宜的檢查（檔案存在、Ollama 的模型清單、資料庫可寫），**不載入模型、不重算 SHA-256**。
結果快取 5 秒，避免公開的 /readyz 被輪詢時每次都去查 Ollama。
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from core import jobs, migrations, model_catalog, model_registry, registry
from core.inspection_log import _images_dir, connect
from core.settings import get_settings

CACHE_SECONDS = 5.0
MIN_FREE_BYTES = 1 << 30  # 剩餘空間低於 1GB 給警告（圖片會持續增長）
OLLAMA_TIMEOUT_SECONDS = 2.0

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "value": None}


def _result(ok: bool, message: str, **extra) -> dict:
    return {"ok": ok, "message": message, **extra}


def check_sqlite() -> dict:
    conn = None
    try:
        conn = connect()
        conn.execute("BEGIN IMMEDIATE")  # 取得寫入鎖再放掉，不改任何資料
        conn.rollback()
        return _result(True, "資料庫可寫入")
    except Exception as e:  # noqa: BLE001 — 任何原因造成不可寫都要回報成失敗，而不是讓檢查本身崩潰
        return _result(False, f"資料庫無法寫入：{e}")
    finally:
        if conn is not None:
            conn.close()


def check_migrations() -> dict:
    try:
        conn = connect()
        try:
            current = migrations.current_version(conn)
        finally:
            conn.close()
        latest = migrations.latest_version()
        return _result(current == latest, f"schema 版本 {current}／程式支援 {latest}", current=current, latest=latest)
    except Exception as e:  # noqa: BLE001
        return _result(False, f"讀不到資料庫版本：{e}")


def check_llm() -> dict:
    settings = get_settings()
    engine = settings.llm_engine.strip().lower()
    if engine == "gemini":
        if not settings.gemini_api_key:
            return _result(False, "LLM_ENGINE=gemini 但沒有設定 GEMINI_API_KEY（請在 .env 設定）", engine=engine)
        return _result(True, "Gemini 已設定 API key（不會實際呼叫外部服務檢查）", engine=engine)
    try:
        import ollama

        listing = ollama.Client(timeout=OLLAMA_TIMEOUT_SECONDS).list()
        names = {m.model for m in listing.models}
    except Exception:  # noqa: BLE001 — 連不上、逾時、回應格式不對，對使用者都是「Ollama 不能用」
        return _result(False, "連不到 Ollama，請執行 `ollama serve`（或開啟 Ollama App）", engine=engine)
    wanted = settings.ollama_model
    if wanted not in names and f"{wanted}:latest" not in names:
        return _result(False, f"Ollama 沒有模型 {wanted}，請先執行 `ollama pull {wanted}`", engine=engine)
    return _result(True, f"Ollama 可用，模型 {wanted} 已下載", engine=engine)


def check_disk() -> dict:
    images = _images_dir()
    target = images if images.exists() else images.parent
    while not target.exists() and target != target.parent:
        target = target.parent
    free = shutil.disk_usage(target).free
    gb = free / (1 << 30)
    if free < MIN_FREE_BYTES:
        return _result(False, f"磁碟剩餘空間只有 {gb:.1f} GB（低於 1 GB），請清理舊圖片或備份後擴充", warning=True, free_bytes=free)
    return _result(True, f"磁碟剩餘 {gb:.1f} GB", free_bytes=free)


def check_jobs() -> dict:
    counts = jobs.counts_by_status()
    if counts["interrupted"]:
        return _result(False, f"{counts['interrupted']} 個背景工作被中斷，可在這裡重試", warning=True, counts=counts)
    return _result(True, f"排隊 {counts['queued']}、執行中 {counts['running']}", counts=counts)


def model_state(model_id: str) -> tuple[bool, str | None]:
    """模型能不能用：啟用版本的權重檔存在；或還沒登錄過但預設位置有權重（首次使用會自動登錄）。"""
    title = model_catalog.describe(model_id)["title"]
    active = model_registry.get_active(model_id)
    if active:
        if Path(active["weights_abs"]).is_file():
            return True, None
        return False, (f"模型「{title}」v{active['version']} 的權重檔不存在（{active['weights_path']}）；"
                       "請還原檔案，或在「管理 → 模型」切換到可用的版本")
    if model_registry.list_versions(model_id):
        return False, f"模型「{title}」沒有啟用中的版本，請在「管理 → 模型」啟用一個版本"
    default = model_catalog.default_weights_path(model_id)
    if default is not None and default.is_file():
        return True, None
    hint = model_catalog.MISSING_HINTS.get(model_id, "")
    return False, f"缺少「{title}」的權重：{hint}。" if hint else f"缺少「{title}」的權重。"


def anomaly_state() -> tuple[bool, str | None]:
    from modules.anomaly.service import list_all_categories

    categories = list_all_categories()
    usable = [c for c in categories if model_state(f"anomaly-{c}")[0]]
    if usable:
        return True, None
    return False, ("沒有可用的異常檢測類別：請執行 `python scripts/train_anomaly.py --category all`，"
                   "或在「外觀異常檢測」上傳良品照片建立自訂類別")


def _feature_states(llm: dict) -> list[dict]:
    memo: dict[str, tuple[bool, str | None]] = {}

    def evaluate(token: str) -> tuple[bool, str | None]:
        if token not in memo:
            if token == "llm":
                memo[token] = (llm["ok"], None if llm["ok"] else llm["message"])
            elif token == "anomaly":
                memo[token] = anomaly_state()
            elif token.startswith("model:"):
                memo[token] = model_state(token[len("model:"):])
            else:
                memo[token] = (True, None)
        return memo[token]

    features = []
    for spec in registry.all_actions():
        reason = next((r for ok, r in map(evaluate, spec.requires) if not ok), None)
        features.append({"action": spec.action, "label": spec.label, "tab": spec.tab, "category": spec.category,
                         "available": reason is None, "reason": reason, "requires": spec.requires})
    return features


def _tab_states(features: list[dict]) -> dict[str, dict]:
    tabs: dict[str, dict] = {}
    for f in features:
        t = tabs.setdefault(f["tab"], {"available": False, "reason": None})
        if f["available"]:
            t["available"], t["reason"] = True, None
        elif not t["available"] and t["reason"] is None:
            t["reason"] = f["reason"]
    return tabs


def compute_status(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["value"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
        checks = {"sqlite": check_sqlite(), "migrations": check_migrations(), "llm": check_llm(),
                  "disk": check_disk(), "jobs": check_jobs()}
        features = _feature_states(checks["llm"]) if checks["sqlite"]["ok"] else []
        value = {
            "ready": checks["sqlite"]["ok"] and checks["migrations"]["ok"],
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "checks": checks, "features": features, "tabs": _tab_states(features),
        }
        value["degraded"] = any(not f["available"] for f in features) or any(
            not c["ok"] for name, c in checks.items() if name not in ("sqlite", "migrations"))
        _cache.update(at=time.monotonic(), value=value)
        return value


def clear_cache() -> None:
    with _lock:
        _cache.update(at=0.0, value=None)


def summary(status: dict) -> dict:
    """公開的 /readyz 只回摘要：各檢查項 ok／warn／fail，不含路徑與細節。"""
    def state(name: str, check: dict) -> str:
        if check["ok"]:
            return "ok"
        return "fail" if name in ("sqlite", "migrations") else "warn"

    return {"ready": status["ready"], "degraded": status["degraded"],
            "checks": {name: state(name, c) for name, c in status["checks"].items()},
            "unavailable_features": sum(1 for f in status["features"] if not f["available"])}

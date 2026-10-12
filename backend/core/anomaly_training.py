"""Phase 12：M3 自訂類別——zip 上傳、背景排隊擬合、狀態 registry。

同時只允許一個擬合工作（16GB 記憶體限制）：工作狀態存在資料庫（`core/jobs.py`），單一背景 worker
輪詢並領取，新請求只負責解壓驗證、寫入 `queued` 狀態與 job 就立刻回應，真正的擬合（`scripts/train_anomaly.py`
的 `train_custom()`）由 worker 逐一處理，天然保證同時只跑一個。服務重啟後，做到一半的工作標成 `interrupted`
（可重試），排隊中的工作由 worker 自動接續。
"""

import io
import json
import logging
import shutil
import sys
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from core import jobs
from core.schemas import ModuleError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models" / "anomaly"
CUSTOM_DATA_DIR = PROJECT_ROOT / "data" / "custom_anomaly"
REGISTRY_PATH = MODELS_DIR / "categories.json"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
MIN_GOOD_IMAGES = 15  # 建議 >=50，但擬合流程本身（扣掉留出評分用的 20%）下限抓寬鬆一點

BUILTIN_CATEGORIES = ["metal_nut", "screw", "tile"]  # Phase 3 就有的示範類別，不能被覆蓋

_registry_lock = threading.Lock()
logger = logging.getLogger("vision.jobs")
JOB_KIND = "anomaly_fit"
POLL_INTERVAL_SECONDS = 2.0


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _save_registry(reg: dict) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=2))


def _update_entry(name: str, **fields) -> dict:
    with _registry_lock:
        reg = _load_registry()
        entry = reg.get(name, {})
        entry.update(fields)
        reg[name] = entry
        _save_registry(reg)
        return entry


def _overlay_active_version(name: str, entry: dict) -> dict:
    """狀態檔記的是「最近一次擬合」；切換（回滾）版本之後，顯示的版本、AUROC、門檻要以目前啟用的版本為準。"""
    if entry.get("status") != "done":
        return entry
    from core import model_registry

    active = model_registry.get_active(f"anomaly-{name}")
    if active is None:
        return entry
    entry = dict(entry, model_version=active["version"])
    if "image_auroc" in active["metrics"]:
        entry["image_auroc"] = active["metrics"]["image_auroc"]
    threshold_file = Path(active["weights_abs"]).parents[2] / "threshold.json"
    if threshold_file.exists():
        entry["threshold"] = json.loads(threshold_file.read_text())["threshold"]
    return entry


def get_status(name: str) -> dict | None:
    reg = _load_registry()
    entry = reg.get(name)
    return dict(name=name, **_overlay_active_version(name, entry)) if entry else None


def list_custom_categories(overlay: bool = False) -> list[dict]:
    """overlay=True 時（給管理畫面的類別表）以目前啟用版本的資訊為準；預設不查登錄表（推論路徑每次請求都會呼叫）。"""
    reg = _load_registry()
    return [dict(name=k, **(_overlay_active_version(k, v) if overlay else v)) for k, v in sorted(reg.items())]


def _safe_extract_images(zf: zipfile.ZipFile, dest: Path) -> list[Path]:
    """只取檔名（丟掉 zip 裡的路徑），防 zip slip；只留圖片副檔名。"""
    dest.mkdir(parents=True, exist_ok=True)
    extracted = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = Path(info.filename).name
        if not name or name.startswith("."):
            continue
        if Path(name).suffix.lower() not in IMAGE_EXTS:
            continue
        target = dest / name
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        extracted.append(target)
    return extracted


def enqueue_category(
    name: str, good_zip_bytes: bytes, defect_zip_bytes: bytes | None, created_by: str | None = None
) -> dict:
    if not name or not all(c.isalnum() or c in "_-" for c in name):
        raise ModuleError("類別名稱只能是英數字、底線、連字號", 400)
    if name in BUILTIN_CATEGORIES:
        raise ModuleError(f"「{name}」是內建示範類別，不能覆蓋，請換一個名稱", 400)

    existing = get_status(name)
    if existing and existing.get("status") in ("queued", "fitting"):
        raise ModuleError(f"類別「{name}」已經在排隊或擬合中，請等它完成再重新送出", 409)

    if not good_zip_bytes:
        raise ModuleError("請上傳良品照片 zip", 400)

    category_dir = CUSTOM_DATA_DIR / name
    good_dir = category_dir / "good"
    defect_dir = category_dir / "defect"
    if good_dir.exists():
        shutil.rmtree(good_dir)
    if defect_dir.exists():
        shutil.rmtree(defect_dir)

    try:
        with zipfile.ZipFile(io.BytesIO(good_zip_bytes)) as zf:
            good_paths = _safe_extract_images(zf, good_dir)
    except zipfile.BadZipFile:
        raise ModuleError("良品照片 zip 不是合法的 zip 檔", 400)

    if len(good_paths) < MIN_GOOD_IMAGES:
        raise ModuleError(f"良品照片太少（zip 裡只有 {len(good_paths)} 張圖片），至少需要 {MIN_GOOD_IMAGES} 張", 400)

    defect_paths: list[Path] = []
    if defect_zip_bytes:
        try:
            with zipfile.ZipFile(io.BytesIO(defect_zip_bytes)) as zf:
                defect_paths = _safe_extract_images(zf, defect_dir)
        except zipfile.BadZipFile:
            raise ModuleError("NG 照片 zip 不是合法的 zip 檔", 400)

    job = jobs.create_job(JOB_KIND, {"name": name}, created_by)
    _update_entry(
        name,
        status="queued",
        source="custom",
        created_at=datetime.now().isoformat(timespec="seconds"),
        good_count=len(good_paths),
        defect_count=len(defect_paths),
        error=None,
        job_id=job["id"],
    )
    return get_status(name)


def _category_root(name: str) -> Path:
    """類別目前啟用版本的資料夾（門檻、評分、指標檔都在這裡）；沒有登錄時退回舊的每類別資料夾。"""
    from core import model_registry

    return model_registry.active_anomaly_root(name, MODELS_DIR / name)


def set_threshold(name: str, threshold: float) -> dict:
    entry = get_status(name)
    if entry is None or entry.get("status") != "done":
        raise ModuleError(f"類別「{name}」還沒有擬合完成，無法設定門檻", 400)
    root = _category_root(name)
    root.mkdir(parents=True, exist_ok=True)
    (root / "threshold.json").write_text(json.dumps({"threshold": threshold}, ensure_ascii=False, indent=2))
    return _update_entry(name, threshold=threshold)


def get_scores(name: str) -> list[dict]:
    scores_path = _category_root(name) / "scores.json"
    if not scores_path.exists():
        raise ModuleError(f"類別「{name}」沒有評分資料（可能還沒擬合完成）", 404)
    return json.loads(scores_path.read_text())


def _run_fit(name: str) -> None:
    scripts_dir = PROJECT_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import train_anomaly  # noqa: PLC0415 — 故意延後匯入，scripts/ 不是 backend 套件的一部分

    category_dir = CUSTOM_DATA_DIR / name
    good_paths = sorted(p for p in (category_dir / "good").glob("*") if p.suffix.lower() in IMAGE_EXTS)
    defect_dir = category_dir / "defect"
    defect_paths = (
        sorted(p for p in defect_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS) if defect_dir.exists() else []
    )

    # 每次擬合都寫進新的版本資料夾（不覆寫舊版本），完成後登錄並啟用；失敗就清掉半成品
    from core import model_registry

    model_id = f"anomaly-{name}"
    version, root = model_registry.new_version_dir(model_id)
    try:
        result = train_anomaly.train_custom(name, good_paths, defect_paths or None, export_root=root)
        weights = root / "weights" / "torch" / "model.pt"
        metrics = json.loads((root / "metrics.json").read_text()) if (root / "metrics.json").exists() else {}
        model_registry.register_version(
            model_id,
            weights,
            metrics,
            f"自訂類別擬合（良品 {len(good_paths)} 張、NG {len(defect_paths)} 張）",
            "system:fit",
            activate=True,
            version=version,
        )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    from modules.anomaly import service as anomaly_service

    anomaly_service.invalidate_cache(name)  # 提早釋放舊版本的推論器（快取本來就以版本為鍵）

    _update_entry(
        name,
        status="done",
        finished_at=datetime.now().isoformat(timespec="seconds"),
        image_auroc=result["image_auroc"],
        threshold_source=result["threshold_source"],
        threshold=json.loads((root / "threshold.json").read_text())["threshold"],
        fit_seconds=result["fit_seconds"],
        model_version=version,
    )


def _run_job(job: dict) -> None:
    """執行一個已領取（running）的擬合工作，並把結果寫回工作狀態與類別狀態檔。"""
    name = job["payload"]["name"]
    try:
        _update_entry(name, status="fitting", started_at=datetime.now().isoformat(timespec="seconds"), job_id=job["id"])
        _run_fit(name)
        jobs.finish(job["id"], "done")
    except Exception as e:  # noqa: BLE001 — 背景 worker 不能讓例外整條執行緒死掉，記錄失敗原因就好
        jobs.finish(job["id"], "failed", str(e))
        _update_entry(name, status="failed", error=str(e), finished_at=datetime.now().isoformat(timespec="seconds"))


def _process_one(name: str) -> None:
    """處理佇列裡（指定類別）的一個工作；抽成獨立函式方便測試直接呼叫，不用真的起一個會無限迴圈的執行緒。
    找不到排隊中的工作（直接呼叫）時，就替這個類別建立一個。"""
    job = jobs.claim_next(JOB_KIND, name)
    if job is None:
        jobs.create_job(JOB_KIND, {"name": name})
        job = jobs.claim_next(JOB_KIND, name)
    _run_job(job)


def _worker_loop(stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            job = jobs.claim_next(JOB_KIND)
        except Exception:  # noqa: BLE001 — 資料庫暫時忙碌不能讓 worker 死掉
            logger.exception("領取擬合工作時發生例外")
            job = None
        if job is None:
            stop.wait(POLL_INTERVAL_SECONDS)
            continue
        _run_job(job)


def recover() -> dict:
    """服務啟動時呼叫：把做到一半的工作標成中斷，並讓類別狀態檔跟上（排隊中的不用處理，worker 會自己接續）。
    也處理 Phase 22 之前遺留、卡在 queued／fitting 但資料庫裡沒有對應工作的類別。"""
    interrupted = [j for j in jobs.recover_interrupted() if j["kind"] == JOB_KIND]
    for job in interrupted:
        name = job["payload"]["name"]
        _update_entry(
            name,
            status="interrupted",
            error=jobs.INTERRUPTED_MESSAGE,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            job_id=job["id"],
        )
    live = {
        j["payload"].get("name") for j in jobs.list_jobs(JOB_KIND, limit=10_000) if j["status"] in ("queued", "running")
    }
    orphaned = []
    for entry in list_custom_categories():
        if entry.get("status") in ("queued", "fitting") and entry["name"] not in live:
            _update_entry(
                entry["name"],
                status="interrupted",
                error="服務重啟前中斷（沒有對應的工作紀錄），請重新上傳",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            orphaned.append(entry["name"])
    if interrupted or orphaned:
        logger.warning("擬合工作重啟後恢復 interrupted=%s orphaned=%s", [j["id"] for j in interrupted], orphaned)
    return {"interrupted": [j["id"] for j in interrupted], "orphaned": orphaned}


def retry_job(job_id: int) -> dict:
    """重試中斷或失敗的擬合：用 data/custom_anomaly/<類別>/ 已存的照片重新擬合成新版本。"""
    job = jobs.get_job(job_id)
    if job is None or job["kind"] != JOB_KIND:
        raise LookupError(f"找不到擬合工作 id={job_id}")
    name = job["payload"]["name"]
    if not (CUSTOM_DATA_DIR / name / "good").exists():
        raise ValueError(f"類別「{name}」的良品照片已經不在（{CUSTOM_DATA_DIR / name / 'good'}），請重新上傳")
    updated = jobs.retry(job_id)
    _update_entry(name, status="queued", error=None, job_id=job_id)
    return updated


def start_worker() -> threading.Thread:
    t = threading.Thread(target=_worker_loop, daemon=True)
    t.start()
    return t

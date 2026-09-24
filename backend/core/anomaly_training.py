"""Phase 12：M3 自訂類別——zip 上傳、背景排隊擬合、狀態 registry。

同時只允許一個擬合工作（16GB 記憶體限制）：`queue.Queue()` + 單一背景 worker 執行緒，
新請求只負責解壓驗證、寫入 `queued` 狀態、丟進佇列就立刻回應，真正的擬合（`scripts/
train_anomaly.py` 的 `train_custom()`）由 worker 逐一處理，天然保證同時只跑一個。
"""

import io
import json
import queue
import shutil
import sys
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from core.schemas import ModuleError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models" / "anomaly"
CUSTOM_DATA_DIR = PROJECT_ROOT / "data" / "custom_anomaly"
REGISTRY_PATH = MODELS_DIR / "categories.json"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
MIN_GOOD_IMAGES = 15  # 建議 >=50，但擬合流程本身（扣掉留出評分用的 20%）下限抓寬鬆一點

BUILTIN_CATEGORIES = ["metal_nut", "screw", "tile"]  # Phase 3 就有的示範類別，不能被覆蓋

_registry_lock = threading.Lock()
_fit_queue: "queue.Queue[str]" = queue.Queue()


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


def get_status(name: str) -> dict | None:
    reg = _load_registry()
    entry = reg.get(name)
    return dict(name=name, **entry) if entry else None


def list_custom_categories() -> list[dict]:
    reg = _load_registry()
    return [dict(name=k, **v) for k, v in sorted(reg.items())]


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


def enqueue_category(name: str, good_zip_bytes: bytes, defect_zip_bytes: bytes | None) -> dict:
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

    _update_entry(
        name,
        status="queued",
        source="custom",
        created_at=datetime.now().isoformat(timespec="seconds"),
        good_count=len(good_paths),
        defect_count=len(defect_paths),
        error=None,
    )
    _fit_queue.put(name)
    return get_status(name)


def set_threshold(name: str, threshold: float) -> dict:
    entry = get_status(name)
    if entry is None or entry.get("status") != "done":
        raise ModuleError(f"類別「{name}」還沒有擬合完成，無法設定門檻", 400)
    weights_dir = MODELS_DIR / name
    (weights_dir / "threshold.json").write_text(json.dumps({"threshold": threshold}, ensure_ascii=False, indent=2))
    return _update_entry(name, threshold=threshold)


def get_scores(name: str) -> list[dict]:
    scores_path = MODELS_DIR / name / "scores.json"
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
    defect_paths = sorted(p for p in defect_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS) if defect_dir.exists() else []

    result = train_anomaly.train_custom(name, good_paths, defect_paths or None, export_root=MODELS_DIR / name)

    from modules.anomaly import service as anomaly_service

    anomaly_service.invalidate_cache(name)  # 重訓覆蓋舊權重時，清掉可能存在的舊快取推論器

    _update_entry(
        name,
        status="done",
        finished_at=datetime.now().isoformat(timespec="seconds"),
        image_auroc=result["image_auroc"],
        threshold_source=result["threshold_source"],
        threshold=json.loads((MODELS_DIR / name / "threshold.json").read_text())["threshold"],
        fit_seconds=result["fit_seconds"],
    )


def _process_one(name: str) -> None:
    """處理佇列裡的一個類別；抽成獨立函式方便測試直接呼叫，不用真的起一個會無限迴圈的執行緒。"""
    try:
        _update_entry(name, status="fitting", started_at=datetime.now().isoformat(timespec="seconds"))
        _run_fit(name)
    except Exception as e:  # noqa: BLE001 — 背景 worker 不能讓例外整條執行緒死掉，記錄失敗原因就好
        _update_entry(name, status="failed", error=str(e), finished_at=datetime.now().isoformat(timespec="seconds"))


def _worker_loop() -> None:
    while True:
        name = _fit_queue.get()
        try:
            _process_one(name)
        finally:
            _fit_queue.task_done()


def start_worker() -> threading.Thread:
    t = threading.Thread(target=_worker_loop, daemon=True)
    t.start()
    return t

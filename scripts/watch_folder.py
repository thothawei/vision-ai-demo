"""Phase 11：監看一個資料夾，新圖進來就呼叫本機辨識 API，成功搬到 done/、失敗搬到 error/ 並寫 .log。

用法：
    python scripts/watch_folder.py --action general --in ./inbox \
        --station AOI-01 --work-order WO-2026-0001

辨識端點不用 X-API-Key（Phase 10 只保護 /api/inspections*），所以這支腳本不用帶 key。

核心邏輯（`process_one`）刻意跟 CLI 的 watchdog 迴圈分開，吃一個 httpx.Client 相容物件
（本機正式執行是 `httpx.Client(base_url=...)`，測試用 FastAPI 的 TestClient——兩者介面
相容，不用真的啟動一個 uvicorn process 也能測完整的上傳→搬檔→寫 log 流程）。
"""

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# 跟 backend/core/batch_dispatch.py 的 ACTIONS 用同一組代號，兩邊要保持一致。
ACTION_URLS = {
    "general": "/api/general/describe",
    "docs": "/api/docs/extract",
    "anomaly": "/api/anomaly/inspect",
    "codes": "/api/codes/decode",
    "count": "/api/measure/count",
    "measure": "/api/measure/measure",
    "intrusion": "/api/safety/intrusion",
    "ppe": "/api/safety/ppe",
    "defect": "/api/defect/pcb",
    "nameplate": "/api/nameplate/read",
    "seven_segment": "/api/nameplate/seven-segment",
    "gauge": "/api/nameplate/gauge",
    "packaging": "/api/medical/packaging-check",
    "pneumonia": "/api/medical/pneumonia-demo",
}

TRACE_HEADER_MAP = {
    "work_order": "X-Work-Order", "part_no": "X-Part-No", "lot_no": "X-Lot-No",
    "station": "X-Station", "operator": "X-Operator",
}


def wait_until_stable(path: Path, poll_interval: float, stable_checks: int, timeout: float = 30.0) -> bool:
    """等檔案大小連續 stable_checks 次不變才算寫完，避免讀到還在寫入中的半個檔案。"""
    last_size = -1
    stable_count = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not path.exists():
            return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= stable_checks:
                return True
        else:
            stable_count = 0
        last_size = size
        time.sleep(poll_interval)
    return False


def _move_with_log(path: Path, target_dir: Path, message: str, ok: bool) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / path.name
    shutil.move(str(path), str(dest))
    log_path = target_dir / (path.stem + ".log")
    log_path.write_text(f"{datetime.now().isoformat(timespec='seconds')} {message}\n", encoding="utf-8")
    print(f"[{'done' if ok else 'error'}] {path.name}: {message}")


def process_one(
    client,
    action: str,
    path: Path,
    done_dir: Path,
    error_dir: Path,
    params: dict,
    data: dict,
    headers: dict,
    poll_interval: float = 0.5,
    stable_checks: int = 2,
) -> bool:
    """處理單一檔案：等寫入穩定 → 呼叫辨識 API → 搬檔 + 寫 log。回傳是否成功。"""
    if path.suffix.lower() not in SUPPORTED_EXTS:
        return False
    if not wait_until_stable(path, poll_interval, stable_checks):
        _move_with_log(path, error_dir, "等待檔案寫入穩定逾時", ok=False)
        return False

    url = ACTION_URLS[action]
    content_type = "image/" + ("jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else path.suffix.lstrip("."))
    try:
        with open(path, "rb") as f:
            res = client.post(
                url, params=params, data=data, headers=headers,
                files={"file": (path.name, f.read(), content_type)}, timeout=60,
            )
    except httpx.HTTPError as e:
        _move_with_log(path, error_dir, f"連線失敗：{e}", ok=False)
        return False

    if res.status_code != 200:
        _move_with_log(path, error_dir, f"API 回傳 {res.status_code}：{res.text}", ok=False)
        return False

    body = res.json()
    _move_with_log(
        path, done_dir,
        f"OK inspection_id={body.get('inspection_id')} verdict={body.get('verdict')}",
        ok=True,
    )
    return True


def build_request_context(args) -> tuple[dict, dict, dict]:
    params = {}
    for key in ("mode", "category"):
        value = getattr(args, key, None)
        if value:
            params[key] = value
    for key in ("expected_count", "marker_size_mm", "target_length_mm", "target_width_mm",
                "tolerance_mm", "min_value", "max_value", "min_angle", "max_angle"):
        value = getattr(args, key, None)
        if value is not None:
            params[key] = value

    data = {}
    if getattr(args, "zone", None):
        data["zone"] = args.zone

    headers = {}
    for field, header_name in TRACE_HEADER_MAP.items():
        value = getattr(args, field, None)
        if value:
            headers[header_name] = quote(value)

    return params, data, headers


def scan_existing(client, args, in_dir: Path, done_dir: Path, error_dir: Path) -> None:
    params, data, headers = build_request_context(args)
    for path in sorted(in_dir.iterdir()):
        if path.is_file():
            process_one(client, args.action, path, done_dir, error_dir, params, data, headers,
                        args.poll_interval, args.stable_checks)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True, choices=sorted(ACTION_URLS), help="要呼叫的辨識動作")
    parser.add_argument("--in", dest="in_dir", required=True, help="監看的資料夾")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--station")
    parser.add_argument("--work-order", dest="work_order")
    parser.add_argument("--part-no", dest="part_no")
    parser.add_argument("--lot-no", dest="lot_no")
    parser.add_argument("--operator")
    parser.add_argument("--mode", help="M4 文件結構化用：ocr/tesseract/end_to_end")
    parser.add_argument("--category", help="M3 異常檢測用：metal_nut/screw/tile")
    parser.add_argument("--zone", help="M5 危險區域入侵用：JSON 字串，例如 '[[0.1,0.1],[0.9,0.9],[0.1,0.9]]'")
    parser.add_argument("--expected-count", dest="expected_count", type=int)
    parser.add_argument("--marker-size-mm", dest="marker_size_mm", type=float)
    parser.add_argument("--target-length-mm", dest="target_length_mm", type=float)
    parser.add_argument("--target-width-mm", dest="target_width_mm", type=float)
    parser.add_argument("--tolerance-mm", dest="tolerance_mm", type=float)
    parser.add_argument("--min-value", dest="min_value", type=float)
    parser.add_argument("--max-value", dest="max_value", type=float)
    parser.add_argument("--min-angle", dest="min_angle", type=float)
    parser.add_argument("--max-angle", dest="max_angle", type=float)
    parser.add_argument("--poll-interval", type=float, default=0.5, help="檢查檔案大小是否穩定的間隔秒數")
    parser.add_argument("--stable-checks", type=int, default=2, help="連續幾次大小不變才算寫完")
    parser.add_argument("--once", action="store_true", help="只處理一次目前資料夾裡的檔案，不繼續監看（測試/單次批次用）")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    in_dir = Path(args.in_dir)
    in_dir.mkdir(parents=True, exist_ok=True)
    done_dir = in_dir / "done"
    error_dir = in_dir / "error"

    client = httpx.Client(base_url=args.base_url)
    scan_existing(client, args, in_dir, done_dir, error_dir)

    if args.once:
        return

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    params, data, headers = build_request_context(args)

    class InboxHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            process_one(client, args.action, Path(event.src_path), done_dir, error_dir,
                        params, data, headers, args.poll_interval, args.stable_checks)

    observer = Observer()
    observer.schedule(InboxHandler(), str(in_dir), recursive=False)
    observer.start()
    print(f"監看中：{in_dir}（action={args.action}），Ctrl+C 結束")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    sys.exit(main())

"""Phase 10：NG 時非同步通知 ERP_WEBHOOK_URL，絕不擋住辨識 API 的回應。

`notify_ng()` 在 `inspection_log.record_result()` 判定 verdict=NG 時被呼叫，開一個
daemon thread 立即送出、不等待結果；送出失敗（例外或非 2xx）才寫進 `webhook_queue`，
交給 `start_background_retry_loop()` 開的背景執行緒定時重試，超過上限次數放棄但保留紀錄。
"""

import json
import logging
import os
import threading
import time

import httpx

from core.inspection_log import enqueue_webhook, list_pending_webhooks, mark_webhook_attempt

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 60
POLL_INTERVAL_SECONDS = 30
SEND_TIMEOUT_SECONDS = 5


def _webhook_url() -> str | None:
    return os.environ.get("ERP_WEBHOOK_URL") or None


def _build_payload(inspection_id: int, module: str, verdict: str, trace: dict) -> dict:
    return {
        "inspection_id": inspection_id,
        "module": module,
        "verdict": verdict,
        "work_order": trace.get("work_order"),
        "part_no": trace.get("part_no"),
        "lot_no": trace.get("lot_no"),
        "station": trace.get("station"),
    }


def _send(url: str, payload: dict) -> tuple[bool, str | None]:
    try:
        res = httpx.post(url, json=payload, timeout=SEND_TIMEOUT_SECONDS)
        if 200 <= res.status_code < 300:
            return True, None
        return False, f"HTTP {res.status_code}"
    except httpx.HTTPError as e:
        return False, str(e)


def notify_ng(inspection_id: int, module: str, verdict: str, trace: dict) -> None:
    """未設定 ERP_WEBHOOK_URL、或 verdict 不是 NG 時完全不啟用（不開 thread）。"""
    url = _webhook_url()
    if not url or verdict != "NG":
        return
    payload = _build_payload(inspection_id, module, verdict, trace)

    def _worker():
        ok, err = _send(url, payload)
        if not ok:
            enqueue_webhook(inspection_id, payload)
            logger.warning("webhook 送出失敗，已進重試佇列：inspection_id=%s error=%s", inspection_id, err)

    threading.Thread(target=_worker, daemon=True).start()


def retry_pending_once() -> None:
    """給背景重試執行緒與測試呼叫：掃一次 webhook_queue，逐筆重送。"""
    url = _webhook_url()
    if not url:
        return
    for row in list_pending_webhooks():
        payload = json.loads(row["payload_json"])
        ok, err = _send(url, payload)
        mark_webhook_attempt(row["id"], ok, err, MAX_ATTEMPTS, RETRY_DELAY_SECONDS)


def start_background_retry_loop() -> threading.Thread:
    def _loop():
        while True:
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                retry_pending_once()
            except Exception:
                logger.exception("webhook 背景重試迴圈發生未預期例外")

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t

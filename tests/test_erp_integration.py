"""Phase 10：ERP 串接（API Key、since_id 增量拉取、reviews 同步、webhook、上傳/CORS 資安）。"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_API_KEY


def test_api_key_missing_or_wrong_is_401_correct_key_is_200(client):
    from main import app

    bare = TestClient(app)  # 沒有預設 header，模擬真的沒帶 key
    assert bare.get("/api/inspections").status_code == 401
    assert bare.get("/api/inspections", headers={"X-API-Key": "wrong-key"}).status_code == 401
    assert bare.get("/api/inspections", headers={"X-API-Key": TEST_API_KEY}).status_code == 200


def test_recognition_endpoints_do_not_need_api_key(client, fake_llm, warning_sign_png):
    from main import app

    bare = TestClient(app)  # 辨識端點刻意不用 key，見 core/api_auth.py
    res = bare.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
    assert res.status_code == 200


def test_since_id_ascending_no_duplicate_no_miss(client):
    from core.inspection_log import log_inspection

    ids = [log_inspection("codes", "OK", "e", 1, [{"n": i}]) for i in range(5)]

    page = client.get("/api/inspections", params={"since_id": ids[1], "limit": 100}).json()
    assert [r["id"] for r in page] == ids[2:]  # 升冪、只回 id > since_id 的 3 筆
    assert page == sorted(page, key=lambda r: r["id"])


def test_reviews_endpoint_returns_records_reviewed_after_since(client, fake_llm, warning_sign_png):
    res = client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")})
    inspection_id = res.json()["inspection_id"]

    before_review = "2000-01-01T00:00:00"
    client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "OK", "reviewer": "王"})

    reviewed = client.get("/api/inspections/reviews", params={"since": before_review}).json()
    assert [r["id"] for r in reviewed] == [inspection_id]

    future = "2099-01-01T00:00:00"
    assert client.get("/api/inspections/reviews", params={"since": future}).json() == []


def test_upload_too_large_returns_413(client, monkeypatch, warning_sign_png):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")  # 任何檔案都算超過上限
    res = client.post("/api/general/describe", files={"file": ("a.png", warning_sign_png, "image/png")})
    assert res.status_code == 413
    assert "過大" in res.json()["detail"]


def test_non_image_bytes_with_image_extension_is_rejected(client):
    res = client.post("/api/general/describe", files={"file": ("fake.png", b"not a real image", "image/png")})
    assert res.status_code == 400
    assert "無法讀取圖片" in res.json()["detail"]


def test_cors_only_allows_whitelisted_origin(client):
    # CORSMiddleware 的 allow_origins 是 main.py import 當下就讀死的（CORSMiddleware 設計如此，
    # 不是每個請求重讀 env），所以這裡測預設白名單（127.0.0.1:8000／localhost:8000），
    # 不試圖用 monkeypatch 改 CORS_ORIGINS——那樣改了也不會生效，測試會產生假象。
    from main import app

    fresh = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    allowed = fresh.get("/api/inspections", headers={"Origin": "http://127.0.0.1:8000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"

    blocked = fresh.get("/api/inspections", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in blocked.headers


class _CapturingHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CapturingHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # 靜音，測試輸出不需要每個請求的存取紀錄


@pytest.fixture
def webhook_server():
    _CapturingHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", _CapturingHandler.received
    server.shutdown()
    server.server_close()


def _wait_until(predicate, timeout=3.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_ok_verdict_does_not_trigger_webhook(client, fake_pcb_detector_no_defect, webhook_server, monkeypatch, warning_sign_png):
    url, received = webhook_server
    monkeypatch.setenv("ERP_WEBHOOK_URL", url)

    res_ok = client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")})
    assert res_ok.json()["verdict"] == "OK"
    time.sleep(0.3)
    assert received == []


def test_ng_verdict_triggers_webhook(client, fake_pcb_detector, webhook_server, monkeypatch, warning_sign_png):
    url, received = webhook_server
    monkeypatch.setenv("ERP_WEBHOOK_URL", url)

    res_ng = client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")})
    assert res_ng.json()["verdict"] == "NG"
    assert _wait_until(lambda: len(received) == 1)
    assert received[0]["inspection_id"] == res_ng.json()["inspection_id"]
    assert received[0]["verdict"] == "NG"
    assert received[0]["module"] == "defect"


def test_ng_webhook_receiver_down_response_still_ok_and_queued(client, fake_pcb_detector, monkeypatch, warning_sign_png):
    # 先開一個 server 拿到一個「保證沒人聽」的 port，再關掉，確保連線失敗
    dead_server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
    dead_port = dead_server.server_address[1]
    dead_server.server_close()

    monkeypatch.setenv("ERP_WEBHOOK_URL", f"http://127.0.0.1:{dead_port}")

    started = time.perf_counter()
    res = client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")})
    elapsed = time.perf_counter() - started

    assert res.status_code == 200
    assert res.json()["verdict"] == "NG"
    assert elapsed < 2.0  # 接收端掛掉不該讓辨識 API 卡住等 timeout（daemon thread 背景送）

    from core.inspection_log import list_pending_webhooks

    assert _wait_until(lambda: len(list_pending_webhooks()) == 1)
    queued = list_pending_webhooks()[0]
    assert queued["inspection_id"] == res.json()["inspection_id"]


def test_webhook_retry_succeeds_once_receiver_is_back(client, fake_pcb_detector, monkeypatch, warning_sign_png):
    dead_server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
    dead_port = dead_server.server_address[1]
    dead_server.server_close()
    monkeypatch.setenv("ERP_WEBHOOK_URL", f"http://127.0.0.1:{dead_port}")

    res = client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")})

    from core.inspection_log import list_pending_webhooks
    assert _wait_until(lambda: len(list_pending_webhooks()) == 1)

    _CapturingHandler.received = []
    live_server = ThreadingHTTPServer(("127.0.0.1", dead_port), _CapturingHandler)
    thread = threading.Thread(target=live_server.serve_forever, daemon=True)
    thread.start()
    try:
        from core import webhook

        webhook.retry_pending_once()
        assert _wait_until(lambda: len(_CapturingHandler.received) == 1)
        assert list_pending_webhooks() == []
    finally:
        live_server.shutdown()
        live_server.server_close()

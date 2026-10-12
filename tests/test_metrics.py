"""Phase 22：/metrics（Prometheus 指標）與 webhook 佇列重啟後的恢復。"""

import json
import re
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from core import metrics
from core.inspection_log import connect, enqueue_webhook, list_pending_webhooks


def _sample(text: str, name: str, **labels) -> float | None:
    """從 Prometheus 文字格式取出某個序列的值（沒有回傳 None）。"""
    for line in text.splitlines():
        m = re.match(rf"^{name}\{{(.*)\}} ([0-9.e+-]+)$", line)
        if m and all(f'{k}="{v}"' in m.group(1) for k, v in labels.items()):
            return float(m.group(2))
    return None


def _scrape(client) -> str:
    res = client.get("/metrics")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/plain")
    return res.text


def test_metrics_requires_qc_or_api_key(client, qc_client, operator_client, admin_client):
    assert TestClient(client.app).get("/metrics").status_code == 401
    assert operator_client.get("/metrics").status_code == 403
    for who in (qc_client, admin_client, client):
        assert who.get("/metrics").status_code == 200


def _delta(before: str, after: str, name: str, **labels) -> float:
    """指標是整個測試程序共用的累計值，所以一律看「前後差」，不依賴別的測試先跑了什麼。"""
    return (_sample(after, name, **labels) or 0) - (_sample(before, name, **labels) or 0)


def test_inspection_counters_and_latency_histogram(client, fake_pcb_detector_no_defect, warning_sign_png):
    before = _scrape(client)
    assert client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")}).json()["verdict"] == "OK"
    after = _scrape(client)
    assert _delta(before, after, "vision_inspections_total", module="defect", verdict="OK") == 1.0
    assert _delta(before, after, "vision_inspections_total", module="defect", verdict="NG") == 0.0
    assert _delta(before, after, "vision_inference_seconds_count", module="defect") == 1.0
    assert _delta(before, after, "vision_inference_seconds_bucket", module="defect", le="+Inf") == 1.0


def test_ng_count_is_readable_from_the_verdict_label(client, fake_pcb_detector, warning_sign_png):
    before = _scrape(client)
    for _ in range(3):
        client.post("/api/defect/pcb", files={"file": ("p.png", warning_sign_png, "image/png")})
    assert _delta(before, _scrape(client), "vision_inspections_total", module="defect", verdict="NG") == 3.0


def test_http_metrics_use_route_templates_so_labels_do_not_explode(client, admin_client, fake_llm, warning_sign_png):
    before = _scrape(client)
    ids = [client.post("/api/general/describe", files={"file": ("s.png", warning_sign_png, "image/png")}).json()["inspection_id"]
           for _ in range(3)]
    for i in ids:
        admin_client.get(f"/api/inspections/{i}")
    admin_client.get("/api/no/such/route")
    text = _scrape(client)
    assert _delta(before, text, "vision_http_requests_total", method="GET", route="/api/inspections/{inspection_id}", status="200") == 3.0
    assert not re.search(r'route="/api/inspections/\d+"', text)  # 不會每個 id 一個序列
    assert 'route="unmatched"' in text or 'route="/"' in text
    assert _delta(before, text, "vision_http_request_seconds_count", method="POST", route="/api/general/describe") == 3.0


def test_metrics_never_contain_secrets(client):
    text = _scrape(client)
    # 路由樣板本身會有 /password 這個字（改密碼端點），所以檢查的是實際的祕密值，不是單字
    assert "test-key" not in text and "password-1234" not in text and "SESSION_SECRET" not in text


def test_jobs_gauge_reflects_the_database(client, admin_client):
    from core import jobs

    jobs.create_job("k", {"name": "a"})
    jobs.create_job("k", {"name": "b"}, status="running")
    text = _scrape(admin_client)
    assert _sample(text, "vision_jobs", status="queued") == 1.0 and _sample(text, "vision_jobs", status="running") == 1.0


def test_registry_is_isolated_from_the_default_process_collectors():
    assert b"process_cpu_seconds_total" not in metrics.render()  # 只輸出本系統自己的指標


# --- webhook 佇列重啟後的恢復 ---

class _Handler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Handler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def receiver():
    _Handler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _Handler.received
    server.shutdown()
    server.server_close()


def test_pending_webhooks_are_retried_after_a_restart_and_leave_the_queue(client, receiver, monkeypatch):
    """「重啟」＝ 程序內什麼都不記得，只剩資料庫裡的 webhook_queue；重試掃描照常把它送出去。"""
    from core import webhook

    url, received = receiver
    monkeypatch.setenv("ERP_WEBHOOK_URL", url)
    enqueue_webhook(11, {"inspection_id": 11, "module": "defect", "verdict": "NG"})
    enqueue_webhook(12, {"inspection_id": 12, "module": "defect", "verdict": "NG"})
    assert len(list_pending_webhooks()) == 2
    webhook.retry_pending_once()
    assert sorted(p["inspection_id"] for p in received) == [11, 12]
    assert list_pending_webhooks() == []  # 送成功就離開佇列，不會重複送
    webhook.retry_pending_once()
    assert len(received) == 2


def test_given_up_and_not_yet_due_webhooks_are_not_sent(client, receiver, monkeypatch):
    from core import webhook

    url, received = receiver
    monkeypatch.setenv("ERP_WEBHOOK_URL", url)
    gave_up = enqueue_webhook(21, {"inspection_id": 21})
    later = enqueue_webhook(22, {"inspection_id": 22})
    with connect() as conn:
        conn.execute("UPDATE webhook_queue SET given_up = 1, attempts = ? WHERE id = ?", (webhook.MAX_ATTEMPTS, gave_up))
        conn.execute("UPDATE webhook_queue SET next_retry_at = ? WHERE id = ?",
                     ((datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds"), later))
        conn.commit()
    webhook.retry_pending_once()
    assert received == []  # 放棄的不再送；還沒到重試時間的等到期
    with connect() as conn:  # 到期後就會送
        conn.execute("UPDATE webhook_queue SET next_retry_at = '2000-01-01T00:00:00' WHERE id = ?", (later,))
        conn.commit()
    webhook.retry_pending_once()
    assert [p["inspection_id"] for p in received] == [22]


def test_failed_retry_is_rescheduled_and_given_up_after_max_attempts(client, monkeypatch):
    from core import webhook

    dead = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = dead.server_address[1]
    dead.server_close()
    monkeypatch.setenv("ERP_WEBHOOK_URL", f"http://127.0.0.1:{port}")
    queued = enqueue_webhook(31, {"inspection_id": 31})
    for attempt in range(1, webhook.MAX_ATTEMPTS + 1):
        with connect() as conn:  # 讓它到期
            conn.execute("UPDATE webhook_queue SET next_retry_at = '2000-01-01T00:00:00' WHERE id = ?", (queued,))
            conn.commit()
        webhook.retry_pending_once()
        with connect() as conn:
            row = conn.execute("SELECT attempts, given_up, last_error FROM webhook_queue WHERE id = ?", (queued,)).fetchone()
        assert row["attempts"] == attempt and row["last_error"]
    assert row["given_up"] == 1  # 第 5 次仍失敗就放棄，但紀錄保留供事後排查

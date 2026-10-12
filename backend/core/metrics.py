"""Prometheus 指標（只提供 `/metrics` 端點，不架 Prometheus）。

用自己的 registry（不帶預設的 process／platform 收集器）。標籤一律用「路由樣板」而不是實際網址，
避免 `/api/inspections/123` 這類路徑造成標籤爆炸。程序內計數：多個程序時各自獨立（本系統假設單一程序）。
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry()

_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
_INFERENCE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 60, 120)

HTTP_REQUESTS = Counter("vision_http_requests_total", "HTTP 請求數", ["method", "route", "status"], registry=REGISTRY)
HTTP_SECONDS = Histogram(
    "vision_http_request_seconds", "HTTP 請求耗時（秒）", ["method", "route"], buckets=_HTTP_BUCKETS, registry=REGISTRY
)
INSPECTIONS = Counter(
    "vision_inspections_total", "辨識完成筆數（NG 數看 verdict=NG）", ["module", "verdict"], registry=REGISTRY
)
INFERENCE_SECONDS = Histogram(
    "vision_inference_seconds", "各模組辨識耗時（秒）", ["module"], buckets=_INFERENCE_BUCKETS, registry=REGISTRY
)
JOBS = Gauge("vision_jobs", "背景工作數（依狀態）", ["status"], registry=REGISTRY)


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_SECONDS.labels(method, route).observe(seconds)


def observe_inspection(module: str, verdict: str, elapsed_ms: int) -> None:
    INSPECTIONS.labels(module, verdict).inc()
    INFERENCE_SECONDS.labels(module).observe(elapsed_ms / 1000)


def render() -> bytes:
    """輸出前把「背景工作數」更新成目前資料庫裡的值（查詢很便宜）。"""
    from core import jobs

    try:
        for status, count in jobs.counts_by_status().items():
            JOBS.labels(status).set(count)
    except Exception:  # noqa: BLE001 — 資料庫暫時不可用時，其餘指標照常輸出
        pass
    return generate_latest(REGISTRY)

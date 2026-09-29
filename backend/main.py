"""FastAPI 入口：只負責掛載各模組 router、統一錯誤格式、服務前端靜態檔。"""

import importlib
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core import api_auth, registry, request_scope
from core.logging_setup import setup_logging
from core.schemas import ModuleError
from core.settings import startup_settings

setup_logging(startup_settings().log_level)
logger = logging.getLogger("vision.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core import anomaly_training, webhook

    webhook.start_background_retry_loop()
    anomaly_training.start_worker()
    yield


app = FastAPI(title="製造業 AI 辨識系統", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in startup_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """只保護 /api/inspections*（ERP 輪詢面），辨識端點不用 key——見 core/api_auth.py 說明。"""
    if api_auth.is_protected_path(request.url.path):
        key = api_auth.extract_key(request)
        if not api_auth.is_valid_key(key):
            return JSONResponse(status_code=401, content={"detail": "缺少或無效的 X-API-Key"})
    return await call_next(request)


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.middleware("http")
async def request_scope_middleware(request: Request, call_next):
    """最外層：建立 request_id 與請求範圍資料（追溯資訊 header、圖片），記錄請求日誌，
    並在所有回應（含 401）帶上 X-Request-ID。追溯資訊值用 encodeURIComponent 傳送
    （HTTP header 不保證能放非 ASCII 字元）。"""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex[:16]
    trace = {}
    for field, header_name in request_scope.TRACE_HEADER_MAP.items():
        raw = request.headers.get(header_name)
        if raw:
            trace[field] = unquote(raw)
    request_scope.begin_request(trace, request_id)

    started = time.perf_counter()
    is_api = request.url.path.startswith("/api/")
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("請求發生未處理例外 method=%s path=%s", request.method, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.log(
        logging.INFO if is_api else logging.DEBUG,
        "method=%s path=%s status=%s elapsed_ms=%s", request.method, request.url.path,
        response.status_code, elapsed_ms,
    )
    return response


@app.exception_handler(ModuleError)
def handle_module_error(_: Request, exc: ModuleError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


for _router in registry.routers():
    app.include_router(_router)
for _path in ("modules.inspections.router", "modules.batch.router"):
    app.include_router(importlib.import_module(_path).router)


@app.get("/api/modules", tags=["系統"])
def list_modules():
    """辨識動作註冊表（不含程式物件），前端導覽與名稱由此產生。"""
    return registry.describe()


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

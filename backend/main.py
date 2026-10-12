"""FastAPI 入口：只負責掛載各模組 router、統一錯誤格式、服務前端靜態檔。"""

import importlib
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from core import auth, metrics, registry, request_scope
from core.logging_setup import setup_logging
from core.schemas import ModuleError
from core.settings import startup_settings

setup_logging(startup_settings().log_level)
logger = logging.getLogger("vision.http")

MIN_SESSION_SECRET_LENGTH = 32


def _session_secret() -> str:
    secret = startup_settings().session_secret
    if not secret or len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise RuntimeError(
            f"SESSION_SECRET 未設定或短於 {MIN_SESSION_SECRET_LENGTH} 字元，拒絕啟動。"
            '請在 .env 設定，例如：python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    return secret


SESSION_SECRET = _session_secret()


def _log_readiness(health, recovered: dict) -> None:
    """啟動時把就緒狀況寫進日誌：哪些功能現在用不了、為什麼（不能讓檢查本身擋住啟動）。"""
    try:
        status = health.compute_status(force=True)
    except Exception:  # noqa: BLE001
        logger.exception("啟動時的就緒檢查失敗")
        return
    logger.info("啟動就緒 ready=%s degraded=%s recovered=%s", status["ready"], status["degraded"], recovered)
    for name, check in status["checks"].items():
        if not check["ok"]:
            logger.warning("檢查未通過 check=%s message=%s", name, check["message"])
    for feature in status["features"]:
        if not feature["available"]:
            logger.warning("功能不可用 action=%s reason=%s", feature["action"], feature["reason"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core import anomaly_training, health, instance_lock, webhook
    from core.inspection_log import _db_path

    # 同一個資料庫只允許一個服務程序：背景工作的恢復與輪詢都假設單一程序，
    # 拿不到鎖就直接讓啟動失敗（uvicorn 會在綁定埠號之前結束），不去動別的程序正在做的工作
    lock = instance_lock.acquire(_db_path())
    try:
        recovered = anomaly_training.recover()  # 重啟前做到一半的擬合標成中斷，排隊中的由 worker 接續
        webhook.start_background_retry_loop()
        anomaly_training.start_worker()
        _log_readiness(health, recovered)
        yield
    finally:
        instance_lock.release(lock)


app = FastAPI(title="製造業 AI 辨識系統", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in startup_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PAGE_PATHS = {"/", "/index.html"}
_PRIVATE_DOC_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def csrf_origin_middleware(request: Request, call_next):
    """瀏覽器發出的寫入請求必須與本站同源（Origin 與 Host 一致）；搭配 SameSite=Lax cookie 擋掉 CSRF。
    沒帶 Origin 的請求（curl、程式）與帶 X-API-Key 的系統呼叫不受影響。"""
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin and not request.headers.get("x-api-key"):
        if urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse(status_code=403, content={"detail": "不允許跨網站的寫入請求"})
    return await call_next(request)


@app.middleware("http")
async def page_guard_middleware(request: Request, call_next):
    """主頁面與 API 文件需要登入：瀏覽器導向登入頁，文件的 JSON 回 401。登入頁與靜態檔公開（不含任何密鑰）。"""
    path = request.url.path
    if path in _PAGE_PATHS or path in _PRIVATE_DOC_PATHS:
        if auth.principal_from_request(request) is None:
            if path in _PAGE_PATHS or path in {"/docs", "/redoc"}:
                return RedirectResponse("/login.html", status_code=302)
            return JSONResponse(status_code=401, content={"detail": "請先登入"})
    return await call_next(request)


app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="vision_session",
    max_age=startup_settings().session_hours * 3600, same_site="lax",
    https_only=startup_settings().session_cookie_secure,
)


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
    route = request.scope.get("route")
    metrics.observe_request(request.method, getattr(route, "path", None) or "unmatched", response.status_code,
                            elapsed_ms / 1000)
    logger.log(
        logging.INFO if is_api else logging.DEBUG,
        "method=%s path=%s status=%s elapsed_ms=%s", request.method, request.url.path,
        response.status_code, elapsed_ms,
    )
    return response


@app.exception_handler(ModuleError)
def handle_module_error(_: Request, exc: ModuleError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# 辨識端點：任何已登入使用者或有效的 API key；需要更高權限的端點在各自的函式上另加 require_role
for _router in registry.routers():
    app.include_router(_router, dependencies=[Depends(auth.require_login)])
app.include_router(importlib.import_module("modules.batch.router").router, dependencies=[Depends(auth.require_login)])
# 以下 router 自行在端點或 router 層級宣告權限（登入端點本身不需要驗證）
for _path in ("modules.auth.router", "modules.users.router", "modules.audit.router", "modules.inspections.router",
              "modules.master.router", "modules.recipes.router", "modules.spc.router", "modules.reports.router", "modules.models.router", "modules.system.router"):
    app.include_router(importlib.import_module(_path).router)


@app.get("/api/modules", tags=["系統"], dependencies=[Depends(auth.require_login)])
def list_modules():
    """辨識動作註冊表（不含程式物件），前端導覽與名稱由此產生。"""
    return registry.describe()


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

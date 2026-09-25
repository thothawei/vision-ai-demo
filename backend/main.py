"""FastAPI 入口：只負責掛載各模組 router、統一錯誤格式、服務前端靜態檔。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import api_auth, context  # noqa: E402
from core.schemas import ModuleError  # noqa: E402
from modules.anomaly.router import router as anomaly_router  # noqa: E402
from modules.assembly.router import router as assembly_router  # noqa: E402
from modules.batch.router import router as batch_router  # noqa: E402
from modules.codes.router import router as codes_router  # noqa: E402
from modules.colordiff.router import router as colordiff_router  # noqa: E402
from modules.defect.router import router as defect_router  # noqa: E402
from modules.docs.router import router as docs_router  # noqa: E402
from modules.general.router import router as general_router  # noqa: E402
from modules.inspections.router import router as inspections_router  # noqa: E402
from modules.measure.router import router as measure_router  # noqa: E402
from modules.medical.router import router as medical_router  # noqa: E402
from modules.nameplate.router import router as nameplate_router  # noqa: E402
from modules.safety.router import router as safety_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core import anomaly_training, webhook

    webhook.start_background_retry_loop()
    anomaly_training.start_worker()
    yield


app = FastAPI(title="製造業 AI 辨識系統", lifespan=lifespan)

_cors_origins = os.environ.get("CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """只保護 /api/inspections*（ERP 輪詢面），13 個辨識端點不用 key——見 core/api_auth.py 說明。"""
    if api_auth.is_protected_path(request.url.path):
        key = api_auth.extract_key(request)
        if not api_auth.is_valid_key(key):
            return JSONResponse(status_code=401, content={"detail": "缺少或無效的 X-API-Key"})
    return await call_next(request)


@app.middleware("http")
async def trace_context_middleware(request: Request, call_next):
    """把追溯資訊 header（工單/料號/批號/站別/操作員）存進 contextvar，
    讓 record_result() 不用改動 13 個模組 service.py 的函式簽名就能取用。
    值用 encodeURIComponent 傳送（HTTP header 不保證能放非 ASCII 字元）。"""
    from urllib.parse import unquote

    trace = {}
    for field, header_name in context.TRACE_HEADER_MAP.items():
        raw = request.headers.get(header_name)
        if raw:
            trace[field] = unquote(raw)
    context.set_trace(trace)
    return await call_next(request)


@app.exception_handler(ModuleError)
def handle_module_error(_: Request, exc: ModuleError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(general_router)
app.include_router(docs_router)
app.include_router(anomaly_router)
app.include_router(defect_router)
app.include_router(codes_router)
app.include_router(measure_router)
app.include_router(nameplate_router)
app.include_router(medical_router)
app.include_router(safety_router)
app.include_router(inspections_router)
app.include_router(batch_router)
app.include_router(assembly_router)
app.include_router(colordiff_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

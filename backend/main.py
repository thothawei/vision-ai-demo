"""FastAPI 入口：只負責掛載各模組 router、統一錯誤格式、服務前端靜態檔。"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core.schemas import ModuleError  # noqa: E402
from modules.anomaly.router import router as anomaly_router  # noqa: E402
from modules.codes.router import router as codes_router  # noqa: E402
from modules.defect.router import router as defect_router  # noqa: E402
from modules.docs.router import router as docs_router  # noqa: E402
from modules.general.router import router as general_router  # noqa: E402
from modules.inspections.router import router as inspections_router  # noqa: E402
from modules.measure.router import router as measure_router  # noqa: E402
from modules.nameplate.router import router as nameplate_router  # noqa: E402
from modules.safety.router import router as safety_router  # noqa: E402

app = FastAPI(title="製造業 AI 辨識 Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(safety_router)
app.include_router(inspections_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

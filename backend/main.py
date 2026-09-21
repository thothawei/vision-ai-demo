"""FastAPI 入口：兩個辨識 API + 靜態前端。"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.genai.errors import APIError

load_dotenv()

from doc_extract import extract_end_to_end, extract_via_ocr  # noqa: E402
from vision_scan import scan_image  # noqa: E402

app = FastAPI(title="Vision AI Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/scan")
async def api_scan(file: UploadFile = File(...)):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="檔案是空的")

    try:
        result = scan_image(image_bytes, file.content_type or "image/jpeg")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Gemini API 錯誤：{e.message}")

    return result


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...), mode: str = "ocr"):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="檔案是空的")

    try:
        if mode == "end_to_end":
            result = extract_end_to_end(image_bytes, file.content_type or "image/jpeg")
        else:
            result = extract_via_ocr(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Gemini API 錯誤：{e.message}")

    return result


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

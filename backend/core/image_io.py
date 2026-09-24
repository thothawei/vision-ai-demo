"""讀圖、EXIF 轉正、縮圖、轉 base64 等共用影像工具。"""

import base64
import io
import os

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from core import context
from core.schemas import ModuleError

_FORMAT_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "BMP": "bmp", "GIF": "gif"}


def _max_upload_mb() -> int:
    return int(os.environ.get("MAX_UPLOAD_MB", "20"))


def load_image(image_bytes: bytes) -> Image.Image:
    """讀取上傳的圖片並依 EXIF 轉正（手機直拍照片常見方向錯誤）。

    大小上限（`MAX_UPLOAD_MB`，預設 20）在這裡檢查，是所有模組讀圖的唯一入口；
    不信任副檔名/Content-Type，一律靠 Pillow 實際開檔驗證是不是真的圖片。"""
    if not image_bytes:
        raise ModuleError("檔案是空的", 400)
    max_mb = _max_upload_mb()
    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > max_mb:
        raise ModuleError(f"檔案過大（{size_mb:.1f}MB），上限 {max_mb}MB", 413)
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception as e:
        # 刻意用寬鬆的 except（不只 UnidentifiedImageError/OSError）：
        # ultralytics 匯入後會 monkeypatch PIL.Image.open 加 HEIF 支援，格式辨識失敗時
        # 會嘗試 lazy import pi_heif（沒裝的話丟 ModuleNotFoundError，不是 Image 家族的例外）。
        # 這個函式的目的就是「bytes 讀不出圖片就回 400」，不管底層丟的是哪種例外型別，
        # 都不該讓使用者看到 500（實測踩到：M5/M6 用過 YOLO 後，上傳壞檔會變成未攔截的 500）。
        raise ModuleError(f"無法讀取圖片：{e}", 400)
    ext = _FORMAT_EXT.get(image.format, "jpg")
    context.set_raw_image(image_bytes, ext)
    return ImageOps.exif_transpose(image).convert("RGB")


def resize_max(image: Image.Image, max_side: int) -> Image.Image:
    if max(image.size) <= max_side:
        return image
    resized = image.copy()
    resized.thumbnail((max_side, max_side))
    return resized


def to_jpeg_bytes(image: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def to_data_url(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def to_bgr(image: Image.Image) -> np.ndarray:
    """PIL(RGB) → OpenCV 慣用的 BGR numpy array。"""
    return np.array(image)[:, :, ::-1].copy()


def from_bgr(array: np.ndarray) -> Image.Image:
    """OpenCV BGR numpy array → PIL(RGB)。"""
    return Image.fromarray(array[:, :, ::-1].copy())


def bgr_to_data_url(array: np.ndarray) -> str:
    return to_data_url(from_bgr(array))

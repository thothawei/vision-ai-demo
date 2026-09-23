"""讀圖、EXIF 轉正、縮圖、轉 base64 等共用影像工具。"""

import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from core.schemas import ModuleError


def load_image(image_bytes: bytes) -> Image.Image:
    """讀取上傳的圖片並依 EXIF 轉正（手機直拍照片常見方向錯誤）。"""
    if not image_bytes:
        raise ModuleError("檔案是空的", 400)
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ModuleError(f"無法讀取圖片：{e}", 400)
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

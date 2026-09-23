"""用程式生成測試圖（不依賴外部授權圖片）。

直接執行會把圖寫進 tests/samples/，方便手動在瀏覽器上傳測試：
    python tests/samples/make_samples.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SAMPLES_DIR = Path(__file__).resolve().parent
CJK_FONT = Path("/System/Library/Fonts/STHeiti Medium.ttc")

WORK_ORDER_LINES = [
    "工單 WORK ORDER",
    "工單號：WO-2026-0915",
    "料號：SC-M6-20",
    "品名：六角螺栓 M6x20",
    "數量：5000 PCS",
    "開工日：2026-09-15",
    "完工日：2026-09-20",
    "製程站別：成型、搓牙、熱處理、電鍍",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    if not CJK_FONT.exists():
        raise FileNotFoundError(f"找不到中文字型 {CJK_FONT}，無法生成含中文的測試圖")
    return ImageFont.truetype(str(CJK_FONT), size)


def make_work_order() -> Image.Image:
    image = Image.new("RGB", (900, 620), "white")
    draw = ImageDraw.Draw(image)
    font = _font(36)
    for i, line in enumerate(WORK_ORDER_LINES):
        draw.text((50, 40 + i * 70), line, fill="black", font=font)
    return image


def make_warning_sign() -> Image.Image:
    """簡化的機台警告標示：黃底三角形 + 文字，給開放式辨識做煙霧測試。"""
    image = Image.new("RGB", (800, 600), (200, 200, 200))
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 60, 650, 540), fill=(255, 204, 0), outline="black", width=8)
    draw.polygon([(400, 100), (300, 280), (500, 280)], fill="black")
    draw.text((385, 150), "!", fill=(255, 204, 0), font=_font(100))
    draw.text((230, 320), "危險 DANGER", fill="black", font=_font(64))
    draw.text((210, 420), "機台運轉中 請勿靠近", fill="black", font=_font(40))
    return image


def make_blank() -> Image.Image:
    return Image.new("RGB", (400, 300), "white")


if __name__ == "__main__":
    for name, maker in [("work_order.png", make_work_order), ("warning_sign.png", make_warning_sign)]:
        maker().save(SAMPLES_DIR / name)
        print("已產生", SAMPLES_DIR / name)

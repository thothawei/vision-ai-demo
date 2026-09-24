"""用程式生成測試圖（不依賴外部授權圖片）。

直接執行會把圖寫進 tests/samples/，方便手動在瀏覽器上傳測試：
    python tests/samples/make_samples.py
"""

from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import zxingcpp
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


# ---------- M1 追溯碼 ----------

def make_gs1_datamatrix(days_from_today: int) -> tuple[Image.Image, dict]:
    """產生一個 GS1 DataMatrix：(01)GTIN (17)效期 (10)批號 (21)序號。

    days_from_today 可為負（已過期）、0~30（即將到期）、>30（正常），對應 service.py 的效期判斷。
    """
    expiry = date.today() + timedelta(days=days_from_today)
    yymmdd = expiry.strftime("%y%m%d")
    fields = {"gtin": "04912345123457", "expiry": expiry, "batch": "LOT2026A", "serial": "SN00042"}
    content = f"(01){fields['gtin']}(17){yymmdd}(10){fields['batch']}(21){fields['serial']}"

    barcode = zxingcpp.create_barcode(content, zxingcpp.DataMatrix, gs1=True)
    marker = zxingcpp.write_barcode_to_image(barcode, scale=8)
    marker_rgb = Image.fromarray(np.array(marker)).convert("RGB")

    canvas = Image.new("RGB", (marker_rgb.width + 80, marker_rgb.height + 80), "white")
    canvas.paste(marker_rgb, (40, 40))
    return canvas, fields


# ---------- M2 計數與量測 ----------

def make_screws_photo() -> Image.Image:
    """白底黑色圓形零件：6 顆分開 + 2 顆相黏（測試 watershed 分離），給計數模組用。"""
    image = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(image)
    centers = [(100, 100), (250, 100), (400, 100), (100, 250), (250, 250), (400, 250)]
    for cx, cy in centers:
        draw.ellipse((cx - 35, cy - 35, cx + 35, cy + 35), fill="black")
    # 兩顆相黏：圓心距小於兩倍半徑
    draw.ellipse((600 - 35, 200 - 35, 600 + 35, 200 + 35), fill="black")
    draw.ellipse((655 - 35, 200 - 35, 655 + 35, 200 + 35), fill="black")
    return image


TEST_PX_PER_MM = 4
TEST_MARKER_SIZE_MM = 30.0


def make_measure_scene(target_length_mm: float, target_width_mm: float, hole_diameter_mm: float | None = None):
    """正視角（無透視變形）場景：ArUco 標記 + 已知實際尺寸的矩形零件，供量測模組驗證精度。

    回傳 (PIL Image, marker_size_mm)；用固定的 TEST_PX_PER_MM 換算，讓 service.py 算出的
    mm 值理論上該等於 target_length_mm / target_width_mm（正視角下無透視誤差）。
    """
    marker_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_px = round(TEST_MARKER_SIZE_MM * TEST_PX_PER_MM)
    marker_img = cv2.aruco.generateImageMarker(marker_dict, 0, marker_px)

    canvas_w, canvas_h = 900, 700
    canvas = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 255
    mx, my = 40, 40
    canvas[my:my + marker_px, mx:mx + marker_px] = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)

    rect_w = round(target_length_mm * TEST_PX_PER_MM)
    rect_h = round(target_width_mm * TEST_PX_PER_MM)
    rx, ry = mx + marker_px + 120, my
    cv2.rectangle(canvas, (rx, ry), (rx + rect_w, ry + rect_h), (0, 0, 0), -1)

    if hole_diameter_mm:
        hole_r = round(hole_diameter_mm * TEST_PX_PER_MM / 2)
        cv2.circle(canvas, (rx + rect_w // 2, ry + rect_h // 2), hole_r, (255, 255, 255), -1)

    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)), TEST_MARKER_SIZE_MM


# ---------- M4 製造文件（RapidOCR + Pydantic schema） ----------

INSPECTION_REPORT_LINES = [
    "進料檢驗報告 INCOMING INSPECTION REPORT",
    "供應商：台中精密螺絲有限公司",
    "料號：SC-M6-20",
    "批號：LOT2026A",
    "抽樣數：50",
    "不良數：2",
    "判定：合格",
]


def make_inspection_report() -> Image.Image:
    image = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(image)
    font = _font(36)
    for i, line in enumerate(INSPECTION_REPORT_LINES):
        draw.text((50, 40 + i * 60), line, fill="black", font=font)
    return image


def make_shipping_order() -> Image.Image:
    """出貨單：標頭文字 + 品項表格（格線），給 RapidTable 表格辨識用。"""
    image = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    font = _font(32)
    header = ["出貨單 SHIPPING ORDER", "單號：SO-2026-0088", "客戶：中科精密工業", "日期：2026-09-22"]
    for i, line in enumerate(header):
        draw.text((50, 30 + i * 50), line, fill="black", font=font)

    table_font = _font(26)
    rows = [["料號", "品名", "數量", "單價"], ["SC-M6-20", "六角螺栓", "1000", "5"], ["SC-M8-30", "螺帽", "500", "3"]]
    cell_w, cell_h = 190, 55
    ox, oy = 50, 250
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            x0, y0 = ox + c * cell_w, oy + r * cell_h
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline="black", width=2)
            draw.text((x0 + 10, y0 + 12), val, fill="black", font=table_font)

    draw.text((50, oy + len(rows) * cell_h + 30), "總額：6500", fill="black", font=font)
    return image


# ---------- M7 銘牌／儀表 ----------

NAMEPLATE_LINES = [
    "機台銘牌 NAMEPLATE",
    "廠牌：中科精機 CHUNG-KE",
    "型號：CK-850V",
    "序號：SN-20260088",
    "製造日期：2026-03",
    "電壓：220V / 3相",
]


def make_nameplate() -> Image.Image:
    image = Image.new("RGB", (800, 420), "white")
    draw = ImageDraw.Draw(image)
    font = _font(34)
    for i, line in enumerate(NAMEPLATE_LINES):
        draw.text((40, 30 + i * 60), line, fill="black", font=font)
    return image


_SEVEN_SEG_MAP = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def make_seven_segment(digits: str = "235", bg=(10, 10, 10), color=(255, 20, 20)) -> Image.Image:
    """畫合成七段顯示器；digits 只能是 0-9（不支援小數點，測試小數點另外處理）。"""
    digit_w, digit_h, gap, thick = 70, 130, 40, 10
    width = len(digits) * (digit_w + gap) + gap
    image = Image.new("RGB", (width, digit_h + 60), bg)
    draw = ImageDraw.Draw(image)
    x = gap
    for ch in digits:
        segs = _SEVEN_SEG_MAP.get(ch, "")
        y0, my = 30, digit_h // 2
        lines = {
            "a": [(x, y0), (x + digit_w, y0)], "g": [(x, y0 + my), (x + digit_w, y0 + my)],
            "d": [(x, y0 + digit_h), (x + digit_w, y0 + digit_h)], "f": [(x, y0), (x, y0 + my)],
            "e": [(x, y0 + my), (x, y0 + digit_h)], "b": [(x + digit_w, y0), (x + digit_w, y0 + my)],
            "c": [(x + digit_w, y0 + my), (x + digit_w, y0 + digit_h)],
        }
        for s in segs:
            draw.line(lines[s], fill=color, width=thick)
        x += digit_w + gap
    return image


def make_gauge(min_angle_deg: float = 135, max_angle_deg: float = 45,
               needle_angle_deg: float = 270, size: int = 400) -> Image.Image:
    """合成指針錶：白底黑框圓 + 紅色指針。角度慣例見 backend/core/gauge.py。"""
    cx, cy, r = size // 2, size // 2, int(size * 0.375)
    canvas = np.ones((size, size, 3), dtype=np.uint8) * 255
    cv2.circle(canvas, (cx, cy), r, (0, 0, 0), 3)
    rad = np.radians(needle_angle_deg)
    end_x, end_y = int(cx + r * 0.85 * np.cos(rad)), int(cy + r * 0.85 * np.sin(rad))
    cv2.line(canvas, (cx, cy), (end_x, end_y), (0, 0, 255), 5)
    cv2.circle(canvas, (cx, cy), 6, (0, 0, 255), -1)
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


if __name__ == "__main__":
    for name, maker in [
        ("work_order.png", make_work_order),
        ("warning_sign.png", make_warning_sign),
        ("screws.png", make_screws_photo),
        ("inspection_report.png", make_inspection_report),
        ("shipping_order.png", make_shipping_order),
        ("nameplate.png", make_nameplate),
        ("seven_segment.png", make_seven_segment),
        ("gauge.png", make_gauge),
    ]:
        maker().save(SAMPLES_DIR / name)
        print("已產生", SAMPLES_DIR / name)

    gs1_img, _ = make_gs1_datamatrix(days_from_today=200)
    gs1_img.save(SAMPLES_DIR / "gs1_valid.png")
    print("已產生", SAMPLES_DIR / "gs1_valid.png")

    measure_img, marker_mm = make_measure_scene(target_length_mm=50, target_width_mm=20, hole_diameter_mm=5)
    measure_img.save(SAMPLES_DIR / "measure_scene.png")
    print("已產生", SAMPLES_DIR / "measure_scene.png", f"(marker={marker_mm}mm)")

"""產生 M2 量測用的 ArUco 標記，可列印 PDF（A4，300 DPI，物理尺寸精確）。

用法：
    python scripts/make_aruco.py                 # 預設 id=0、30mm，輸出 models/aruco_marker_id0_30mm.pdf
    python scripts/make_aruco.py --id 1 --size-mm 40

列印後務必用尺實測一次標記邊長，跟 --size-mm 不符時要以實測值為準（印表機縮放設定常見誤差來源）。
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 300
MM_PER_INCH = 25.4
A4_MM = (210, 297)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models"


def mm_to_px(mm: float) -> int:
    return round(mm / MM_PER_INCH * DPI)


def make_marker_pdf(marker_id: int, size_mm: float, output_path: Path) -> None:
    marker_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_px = mm_to_px(size_mm)
    marker_img = cv2.aruco.generateImageMarker(marker_dict, marker_id, marker_px)

    page = Image.new("L", (mm_to_px(A4_MM[0]), mm_to_px(A4_MM[1])), 255)
    marker_pil = Image.fromarray(marker_img)
    x = (page.width - marker_px) // 2
    y = mm_to_px(40)
    page.paste(marker_pil, (x, y))

    draw = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", mm_to_px(6))
    except OSError:
        font = ImageFont.load_default()
    label = f"ArUco DICT_4X4_50  id={marker_id}  邊長={size_mm:.0f}mm（列印後請用尺覆核）"
    draw.text((x, y + marker_px + mm_to_px(5)), label, fill=0, font=font)
    draw.rectangle([x, y, x + marker_px, y + marker_px], outline=0, width=2)

    page.convert("RGB").save(output_path, "PDF", resolution=DPI)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, default=0, dest="marker_id")
    parser.add_argument("--size-mm", type=float, default=30.0)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"aruco_marker_id{args.marker_id}_{args.size_mm:.0f}mm.pdf"
    make_marker_pdf(args.marker_id, args.size_mm, out)
    print(f"已產生：{out}")

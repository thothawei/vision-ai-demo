"""Phase 23：七段顯示器判讀——真實照片與合成圖沒涵蓋的情況（深字亮底、線段彼此不相連）。

真實照片來自 tests/real_samples/seven_segment（Wikimedia Commons，授權見 SOURCES.md）。完整場景照（磅秤連同紅蘿蔔、
整台計算機）不是這個功能的設計用法（顯示器要近拍），不在這裡斷言；結果見 docs/evaluation.md。
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from core import seven_segment
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "real_samples" / "seven_segment"
_labels = {s["file"]: s["expected"]["讀值"] for s in json.loads((REAL / "labels.json").read_text())["samples"]}


def _read(path: Path) -> str:
    return seven_segment.decode(cv2.imread(str(path)))[0]


@pytest.mark.parametrize(
    "name", ["scale_lcd_112_closeup", "led_clock_238_closeup", "beckman_77_closeup", "led_clock_238"]
)
def test_real_photo_closeups_are_read_correctly(name):
    # LCD 深字亮底＋斜體、LED 線段不相連、光暈把整個數字框塗滿，都是合成圖沒有的情況
    assert _read(REAL / f"{name}.jpg") == _labels[f"{name}.jpg"]


def test_dim_thin_led_is_never_misread_as_wrong_digits():
    # 亮度很弱的細線 LED（計算機）有三個數字看不清：必須標成 ?（整體判 NG 交人工），不可以讀成別的數字
    text = _read(REAL / "calculator_led_closeup.jpg")
    expected = _labels["calculator_led_closeup.jpg"]
    assert len(text) == len(expected)
    assert all(got == want or got == "?" for got, want in zip(text, expected, strict=True)), text
    assert text.count("?") >= 1


_SEGS = {
    "0": "abcdef",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}


def _draw(digits: str, gap: int = 0, dark_on_light: bool = False) -> np.ndarray:
    """畫七段顯示器；gap>0 時每條線段兩端各內縮 gap 像素（像真實顯示器，線段之間不相連）。"""
    w, h, pitch, thick = 70, 130, 110, 12
    fg, bg = ((20, 20, 20), (235, 235, 235)) if dark_on_light else ((255, 30, 30), (10, 10, 10))
    image = Image.new("RGB", (len(digits) * pitch + 40, h + 60), bg)
    d = ImageDraw.Draw(image)
    x = 40
    for ch in digits:
        y0, my = 30, h // 2
        lines = {
            "a": [(x + gap, y0), (x + w - gap, y0)],
            "g": [(x + gap, y0 + my), (x + w - gap, y0 + my)],
            "d": [(x + gap, y0 + h), (x + w - gap, y0 + h)],
            "f": [(x, y0 + gap), (x, y0 + my - gap)],
            "e": [(x, y0 + my + gap), (x, y0 + h - gap)],
            "b": [(x + w, y0 + gap), (x + w, y0 + my - gap)],
            "c": [(x + w, y0 + my + gap), (x + w, y0 + h - gap)],
        }
        for s in _SEGS[ch]:
            d.line(lines[s], fill=fg, width=thick)
        x += pitch
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


@pytest.mark.parametrize("gap", [0, 8])
@pytest.mark.parametrize("dark_on_light", [False, True])
def test_all_digits_with_disconnected_segments_and_both_polarities(gap, dark_on_light):
    assert seven_segment.decode(_draw("0123456789", gap, dark_on_light))[0] == "0123456789"


def test_decimal_point_is_kept_and_colon_is_ignored():
    image = _draw("12", gap=8)
    cv2.circle(image, (40 + 70 + 12 + 40 + 70 + 25, 30 + 130), 7, (255, 30, 30), -1)  # 第二個數字右下方的小數點
    assert seven_segment.decode(image)[0] == "12."
    clock = _draw("12", gap=8)
    for y in (70, 110):  # 兩個數字之間的冒號
        cv2.circle(clock, (40 + 70 + 12 + 25, y), 7, (255, 30, 30), -1)
    assert seven_segment.decode(clock)[0] == "12"

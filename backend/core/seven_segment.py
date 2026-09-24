"""七段顯示器（LED/LCD 數字管）判讀。

一般 OCR（RapidOCR、Tesseract）認不出七段顯示器的字型（實測：RapidOCR 完全偵測不到文字，
Tesseract 會把數字亂猜成中文字），所以照規劃改用 OpenCV 分段判讀：

1. 二值化，抓連通元件。正常畫法下同一個數字的線段會在轉角共用像素，本身就是單一連通元件，
   不需要額外做膨脹黏合（實測膨脹反而會把相鄰數字或小數點誤黏在一起）。
2. 用元件高度區分「數字」跟「小數點」（小數點的高度明顯矮很多，用面積區分在數字「1」這種
   窄字元上不可靠，因為「1」面積雖小但高度跟其他數字一樣）。
3. 數字「1」只有右側兩條線段，緊致邊界框寬度會遠小於其他數字，若照一般 7 個取樣點的比例去
   取樣，取樣點會意外全部落在同一條線上而誤判成「8」；改用「寬度明顯小於其他數字」直接特判為 1。
4. 其餘數字在緊致邊界框內用 7 個固定比例座標點取樣（a~g 七段），亮的線段組合對照表得出數字。
5. 小數點：高度矮的小元件，落在某個數字右下方就當作接在那個數字後面的小數點。
"""

import cv2
import numpy as np

# 七段 a~g 在數字緊致邊界框內的取樣位置（比例座標），數值來自實測合成測試圖校準
_SEG_POINTS = {
    "a": (0.5, 0.04), "b": (0.93, 0.27), "c": (0.93, 0.73),
    "d": (0.5, 0.96), "e": (0.07, 0.73), "f": (0.07, 0.27), "g": (0.5, 0.5),
}
_SEGMENTS_ON = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}
_PATTERN_TO_DIGIT = {"".join(sorted(segs)): digit for digit, segs in _SEGMENTS_ON.items()}

_ON_THRESHOLD = 0.25  # 取樣點窗口內「亮像素」比例超過這個門檻算該段有亮
_DOT_HEIGHT_RATIO = 0.4  # 元件高度低於「數字高度中位數」乘這個比例，當作小數點
_NARROW_WIDTH_RATIO = 0.5  # 元件寬度低於「數字寬度中位數」乘這個比例，直接判定是數字 1


def binarize_minority_foreground(gray: np.ndarray) -> np.ndarray:
    """假設前景（發光/深色數字）是畫面中的少數像素；兩種極性都算，取前景面積較小的那個。"""
    _, binary_normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary_inv = cv2.bitwise_not(binary_normal)
    return binary_normal if cv2.countNonZero(binary_normal) <= cv2.countNonZero(binary_inv) else binary_inv


def decode(bgr: np.ndarray) -> tuple[str, list[dict]]:
    """回傳 (判讀出的字串, 每個字元的除錯資訊)。判讀不出的字元用 "?" 表示，不會瞎猜。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = binarize_minority_foreground(gray)

    n, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    components = [tuple(int(v) for v in stats[i][:4]) for i in range(1, n) if stats[i][4] >= 10]
    if not components:
        return "", []

    heights = sorted(h for _, _, _, h in components)
    median_h = heights[len(heights) // 2]

    digit_boxes = [c for c in components if c[3] >= median_h * _DOT_HEIGHT_RATIO]
    dot_boxes = [c for c in components if c[3] < median_h * _DOT_HEIGHT_RATIO]
    digit_boxes.sort(key=lambda b: b[0])

    if not digit_boxes:
        return "", []
    widths = sorted(w for _, _, w, _ in digit_boxes)
    median_w = widths[len(widths) // 2]

    result = ""
    details = []
    for x, y, w, h in digit_boxes:
        if w < median_w * _NARROW_WIDTH_RATIO:
            digit, pattern = "1", "bc（寬度特判）"
        else:
            segs = sorted(s for s, (fx, fy) in _SEG_POINTS.items() if _is_segment_on(binary, x, y, w, h, fx, fy))
            pattern = "".join(segs)
            digit = _PATTERN_TO_DIGIT.get(pattern, "?")
        result += digit
        details.append({"位置": [x, y, w, h], "亮的線段": pattern, "判讀": digit})

        for dx, dy, dw, dh in dot_boxes:
            if x - 5 <= dx <= x + w + 20 and dy > y + h * 0.7:
                result += "."
                details.append({"位置": [dx, dy, dw, dh], "亮的線段": "dot", "判讀": "."})

    return result, details


def _is_segment_on(binary: np.ndarray, x: int, y: int, w: int, h: int, fx: float, fy: float) -> bool:
    px, py = int(x + fx * w), int(y + fy * h)
    patch = binary[max(0, py - 4):py + 5, max(0, px - 4):px + 5]
    return patch.size > 0 and bool((patch > 0).mean() > _ON_THRESHOLD)

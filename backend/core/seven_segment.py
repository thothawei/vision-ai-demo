"""七段顯示器（LED/LCD 數字管）判讀。

一般 OCR（RapidOCR、Tesseract）認不出七段顯示器的字型（實測：RapidOCR 完全偵測不到文字，
Tesseract 會把數字亂猜成中文字），所以改用 OpenCV 分段判讀。流程：

1. 二值化：亮字深底（LED）與深字亮底（LCD）兩種極性都試，各自完整判讀後取「判得出的數字最多、
   `?` 最少」的那個。不用「前景是少數像素」這類假設：LCD 的背光區域很大，會選錯極性。
2. 過濾：丟掉面積太小的噪點（相對於最大的元件）與幾乎佔滿整張圖的大塊（機殼、邊框）。
3. 分組：真實顯示器的每一段線段彼此不相連（只有合成圖才會在轉角共用像素），所以把「水平範圍有
   重疊、垂直距離夠近」的元件合併成同一個數字（union-find）。
4. 小數點／冒號：高度遠小於數字的小元件。落在某個數字右下方的當作小數點；其餘（例如時鐘的冒號）不
   列入讀值。
5. 數字「1」只有右側線段，群組寬度遠小於其他數字，直接特判為 1。
6. 其餘數字在群組邊界框內，對 a~g 七個區域算「覆蓋率」：水平線段看區域內有亮像素的欄位比例，垂直線段
   看有亮像素的列比例，超過門檻就算該段亮。覆蓋率與筆畫粗細無關，細線的 LED 與粗的 LCD 都適用。

限制：假設顯示器只有單一列數字，數字大致直立（輕微斜體可以，明顯傾斜需先轉正）。
"""

from dataclasses import dataclass

import cv2
import numpy as np

# 七段在數字邊界框內的區域（x0, x1, y0, y1，皆為比例）與方向
_SEG_REGIONS = {
    "a": (0.2, 0.8, 0.0, 0.22, "h"),
    "g": (0.2, 0.8, 0.39, 0.61, "h"),
    "d": (0.2, 0.8, 0.78, 1.0, "h"),
    "f": (0.0, 0.3, 0.08, 0.46, "v"),
    "e": (0.0, 0.3, 0.54, 0.92, "v"),
    "b": (0.7, 1.0, 0.08, 0.46, "v"),
    "c": (0.7, 1.0, 0.54, 0.92, "v"),
}
_SEGMENTS_ON = {
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
_PATTERN_TO_DIGIT = {"".join(sorted(segs)): digit for digit, segs in _SEGMENTS_ON.items()}
# 7 的另一種常見畫法（多一條 f 線段）
_PATTERN_TO_DIGIT["".join(sorted("abcf"))] = "7"

_COVERAGE_ON = 0.6  # 區域內有亮像素的欄／列比例超過這個門檻算該段有亮
_MIN_AREA_RATIO = 0.01  # 元件面積低於「最大元件面積」乘這個比例當噪點
_GIANT_RATIO = 0.9  # 元件寬或高佔整張圖超過這個比例（機殼、邊框）丟掉
_DIGIT_MIN_HEIGHT_RATIO = 0.5  # 群組高度低於「最高群組」乘這個比例，不當數字
_DOT_MAX_RATIO = 0.3  # 小數點的寬、高上限（相對於數字高度）
_GROUP_GAP_RATIO = 0.15  # 第一階段：兩元件的間隙低於「較高者的高度」乘這個比例，視為同一個數字
_MERGE_GAP_RATIO = 0.12  # 第二階段：群組間隙低於「最高群組的高度」乘這個比例再合併（補回『1』上下兩段之間的縫隙）
_NARROW_WIDTH_RATIO = 0.5  # 群組寬度低於一般數字寬度乘這個比例，判定是數字 1
_ONE_MAX_ASPECT = 0.3  # 只有一個數字可參考時，寬高比低於這個值判定是 1


@dataclass
class _Box:
    x0: int
    y0: int
    x1: int
    y1: int
    area: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0


def _masks(gray: np.ndarray) -> list[np.ndarray]:
    """亮字深底與深字亮底各一張前景遮罩（前景＝顯示器上「有畫的線段」）。"""
    t1, normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks = [normal, cv2.bitwise_not(normal)]
    # 較嚴格的版本：只在「前景」像素內再做一次 Otsu。LED 的光暈、未點亮線段的微光會讓第一層遮罩把整個
    # 數字框都塗滿（所有線段看起來都亮），嚴格版本只留下真正點亮的核心。
    for polarity, base in (("bright", gray), ("dark", 255 - gray)):
        pixels = base[base > t1] if polarity == "bright" else base[base > 255 - t1]
        if pixels.size > 50:
            t2, _ = cv2.threshold(pixels.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            masks.append(((base > t2) * 255).astype(np.uint8))
    # 局部自適應門檻：全域 Otsu 會被畫面中大片亮區（機殼、背光）主導，漏掉亮度較弱的細線數字
    block = max(15, (min(gray.shape) // 3) | 1)
    for invert in (False, True):
        kind = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        masks.append(
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, kind, block, -8 if not invert else 8)
        )
    return masks


def _components(mask: np.ndarray) -> list[_Box]:
    height, width = mask.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes = [
        _Box(int(s[0]), int(s[1]), int(s[0] + s[2]), int(s[1] + s[3]), int(s[4]))
        for s in stats[1:]
        if s[4] >= 4 and s[2] < width * _GIANT_RATIO and s[3] < height * _GIANT_RATIO and s[4] < width * height * 0.3
    ]
    if not boxes:
        return []
    largest = max(b.area for b in boxes)
    return [b for b in boxes if b.area >= largest * _MIN_AREA_RATIO]


def _gap(a0: int, a1: int, b0: int, b1: int) -> int:
    """兩段區間的間隙（重疊時為 0）。"""
    return max(0, max(a0, b0) - min(a1, b1))


def _merge(boxes: list[_Box], limit_of) -> list[_Box]:
    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            limit = limit_of(a, b)
            if _gap(a.x0, a.x1, b.x0, b.x1) <= limit and _gap(a.y0, a.y1, b.y0, b.y1) <= limit:
                parent[find(i)] = find(j)

    merged: dict[int, _Box] = {}
    for i, b in enumerate(boxes):
        r = find(i)
        m = merged.get(r)
        merged[r] = (
            b
            if m is None
            else _Box(min(m.x0, b.x0), min(m.y0, b.y0), max(m.x1, b.x1), max(m.y1, b.y1), m.area + b.area)
        )
    return list(merged.values())


def _group(boxes: list[_Box]) -> list[_Box]:
    """距離夠近的元件併成同一個數字。真實顯示器的水平線段（a、g、d）縮在兩條垂直線段之間，彼此在水平方向
    不重疊，所以不能只看重疊，要看「兩軸的間隙都小於門檻」。分兩階段：先用跟元件高度成比例的嚴格門檻，
    再用跟「最高群組」成比例的門檻補合併；相鄰數字的間距遠大於同一數字內線段之間的縫隙。"""
    if not boxes:
        return []
    groups = _merge(boxes, lambda a, b: max(3.0, _GROUP_GAP_RATIO * max(a.h, b.h)))
    digit_height = max(g.h for g in groups)
    groups = _merge(groups, lambda a, b: max(3.0, _MERGE_GAP_RATIO * digit_height))
    return _merge_columns(groups, digit_height)


def _merge_columns(groups: list[_Box], digit_height: int) -> list[_Box]:
    """同一直行的併起來：暗淡的細線 LED，數字「3」只剩三條水平線段，彼此隔著半個數字高度，距離門檻併不起來；
    但它們的水平範圍幾乎完全重疊。只併「兩者都比數字矮很多」的群組，避免把完整的數字跟別的東西黏在一起。"""
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(groups):
        for j in range(i + 1, len(groups)):
            b = groups[j]
            if a.h > 0.5 * digit_height or b.h > 0.5 * digit_height:
                continue
            overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
            if overlap >= 0.6 * min(a.w, b.w) and a.w >= 0.3 * digit_height * 0.4 and b.w >= 0.3 * digit_height * 0.4:
                if _gap(a.y0, a.y1, b.y0, b.y1) <= 0.6 * digit_height:
                    parent[find(i)] = find(j)
    merged: dict[int, _Box] = {}
    for i, b in enumerate(groups):
        r = find(i)
        m = merged.get(r)
        merged[r] = (
            b
            if m is None
            else _Box(min(m.x0, b.x0), min(m.y0, b.y0), max(m.x1, b.x1), max(m.y1, b.y1), m.area + b.area)
        )
    return list(merged.values())


def _segment_on(mask: np.ndarray, box: _Box, seg: str) -> bool:
    fx0, fx1, fy0, fy1, kind = _SEG_REGIONS[seg]
    x0, x1 = box.x0 + int(fx0 * box.w), box.x0 + max(int(fx1 * box.w), int(fx0 * box.w) + 1)
    y0, y1 = box.y0 + int(fy0 * box.h), box.y0 + max(int(fy1 * box.h), int(fy0 * box.h) + 1)
    region = mask[y0:y1, x0:x1] > 0
    if region.size == 0:
        return False
    lit = region.any(axis=0 if kind == "h" else 1)
    return bool(lit.mean() >= _COVERAGE_ON)


def _decode_mask(mask: np.ndarray) -> tuple[str, list[dict]]:
    groups = _group(_components(mask))
    if not groups:
        return "", []
    tallest = max(g.h for g in groups)
    reference = [g for g in groups if g.h >= 0.7 * tallest]
    row_center = float(np.median([(g.y0 + g.y1) / 2 for g in reference]))
    digits = [
        g
        for g in groups
        if g.h >= _DIGIT_MIN_HEIGHT_RATIO * tallest and abs((g.y0 + g.y1) / 2 - row_center) <= 0.6 * tallest
    ]
    digits.sort(key=lambda g: g.x0)
    dots = [
        g for g in groups if g not in digits and g.w <= _DOT_MAX_RATIO * tallest and g.h <= _DOT_MAX_RATIO * tallest
    ]
    if not digits:
        return "", []

    wide = [g.w for g in digits if g.w >= 0.4 * g.h]
    reference_width = float(np.median(wide)) if wide else None

    text, details = "", []
    for g in digits:
        if reference_width is not None:
            narrow = g.w < reference_width * _NARROW_WIDTH_RATIO
        else:
            narrow = g.w < _ONE_MAX_ASPECT * g.h
        if narrow:
            digit, pattern = "1", "bc（寬度特判）"
        else:
            pattern = "".join(sorted(s for s in _SEG_REGIONS if _segment_on(mask, g, s)))
            digit = _PATTERN_TO_DIGIT.get(pattern, "?")
        text += digit
        details.append({"位置": [g.x0, g.y0, g.w, g.h], "亮的線段": pattern, "判讀": digit})
        # 小數點：在這個數字右邊（到下一個數字之前）、位置偏下
        for d in dots:
            near = g.x1 - 0.1 * g.w <= d.x0 <= g.x1 + 0.5 * max(g.w, 0.4 * g.h)
            on_baseline = g.y0 + 0.7 * g.h <= d.y0 and d.y1 <= g.y1 + 0.1 * g.h  # 單位字母（g、kg）通常在基線下方
            if near and on_baseline:
                text += "."
                details.append({"位置": [d.x0, d.y0, d.w, d.h], "亮的線段": "dot", "判讀": "."})
                break
    return text, details


def _quality(text: str) -> tuple[int, int]:
    """判讀品質：認得的數字越多越好、`?` 越少越好（用來在兩種極性之間選一個）。"""
    known = sum(c.isdigit() for c in text)
    return known - text.count("?"), known


def decode(bgr: np.ndarray) -> tuple[str, list[dict]]:
    """回傳 (判讀出的字串, 每個字元的除錯資訊)。判讀不出的字元用 "?" 表示，不會瞎猜。"""
    gray = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    best: tuple[str, list[dict]] = ("", [])
    best_key: tuple | None = None
    for mask in _masks(gray):
        result = _decode_mask(mask)
        # 品質相同時選前景面積較小（較嚴格）的遮罩：光暈把整個數字框塗滿時，兩者都「讀得出數字」，但只有嚴格的才對
        key = (_quality(result[0]), -cv2.countNonZero(mask))
        if best_key is None or key > best_key:
            best, best_key = result, key
    return best

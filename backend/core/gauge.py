"""指針式儀表（壓力錶、溫度錶等）讀值：使用者輸入最小/最大刻度與對應角度，
偵測指針角度後線性換算成讀值。

角度慣例：以畫面座標系（y 軸向下）的 atan2(dy, dx) 為準，0 度＝3 點鐘方向，
角度隨順時針方向遞增（因為 y 向下，順時針剛好是角度增加的方向）。使用者輸入
的 min_angle／max_angle 要用同一套慣例量測，這是本模組最不直覺、最需要在
前端說明清楚的地方。

流程：
1. 找錶面圓心：優先用 HoughCircles 抓外框圓；找不到就要求使用者提供 center_x/center_y。
2. 二值化抓指針（假設指針是畫面中的少數前景像素，跟計數模組同一套假設與限制）。
3. HoughLinesP 找線段，只保留「一端靠近圓心」的線段，挑最長的當指針。
4. 指針角度 → 用 min_angle/max_angle 對應 min_value/max_value 線性內插，
   處理跨 360 度的情況（例如 min_angle=225、max_angle=135，指針順時針掃過頂端）。
"""

import math

import cv2
import numpy as np

from core.schemas import ModuleError

_NEEDLE_MIN_DIST_RATIO = 0.35  # 線段兩端點中，離圓心較近的那端要在這個比例的半徑內，才算是指針
_NEEDLE_MIN_LEN_RATIO = 0.25  # 指針長度至少要有半徑的這個比例，避免把刻度線、數字誤認成指針


def find_center(gray: np.ndarray) -> tuple[float, float, float] | None:
    """找錶面外框圓，回傳 (cx, cy, r)；找不到回傳 None。"""
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=max(h, w),
        param1=100, param2=40, minRadius=min(h, w) // 6, maxRadius=min(h, w) // 2,
    )
    if circles is None or len(circles[0]) == 0:
        return None
    cx, cy, r = circles[0][0]
    return float(cx), float(cy), float(r)


def detect_needle_angle(bgr: np.ndarray, cx: float, cy: float, r: float) -> tuple[float, float]:
    """回傳 (角度 0~360, 指針長度 px)。偵測不到指針時拋出 ModuleError。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary_a = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary_b = cv2.bitwise_not(binary_a)
    # 指針通常是畫面中的少數前景像素，兩種極性都試，取前景面積較小的那個
    binary = binary_a if cv2.countNonZero(binary_a) <= cv2.countNonZero(binary_b) else binary_b

    lines = cv2.HoughLinesP(
        binary, 1, np.pi / 180, threshold=30,
        minLineLength=max(int(r * _NEEDLE_MIN_LEN_RATIO), 10), maxLineGap=10,
    )
    if lines is None:
        raise ModuleError("找不到指針，請確認畫面清楚、指針跟錶面對比明顯", 422)

    best, best_len = None, 0.0
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        x1f, y1f, x2f, y2f = float(x1), float(y1), float(x2), float(y2)
        d1, d2 = math.hypot(x1f - cx, y1f - cy), math.hypot(x2f - cx, y2f - cy)
        length = math.hypot(x2f - x1f, y2f - y1f)
        if min(d1, d2) < r * _NEEDLE_MIN_DIST_RATIO and length > best_len:
            best_len = length
            best = (x1f, y1f, x2f, y2f)

    if best is None:
        raise ModuleError("有偵測到線段，但沒有任何一條的端點靠近圓心，可能圓心座標不準或指針太短", 422)

    x1, y1, x2, y2 = best
    d1, d2 = math.hypot(x1 - cx, y1 - cy), math.hypot(x2 - cx, y2 - cy)
    far_x, far_y = (x2, y2) if d2 > d1 else (x1, y1)
    angle = math.degrees(math.atan2(far_y - cy, far_x - cx)) % 360
    return angle, best_len


def angle_to_value(angle: float, min_angle: float, max_angle: float, min_value: float, max_value: float) -> float:
    """線性內插，處理指針掃過 0/360 度邊界的情況。

    angle 跟 angle+360 兩種解讀都試，取「未夾範圍前的比例」離 [0,1] 較近的那個。
    這是為了處理指針剛好落在 min_angle 附近、因偵測雜訊差個零點幾度就低於 min_angle
    的情況：不能只看「angle < min_angle 就一律當成繞了一整圈」，否則像 134.7 度
    （min_angle=135）這種邊界雜訊，會被誤判成幾乎繞滿一圈、讀出最大值而不是接近最小值。
    """
    effective_max_angle = max_angle if max_angle > min_angle else max_angle + 360

    best_ratio = None
    best_distance = float("inf")
    for candidate_angle in (angle, angle + 360):
        ratio = (candidate_angle - min_angle) / (effective_max_angle - min_angle)
        distance = abs(ratio - max(0.0, min(1.0, ratio)))
        if distance < best_distance:
            best_distance = distance
            best_ratio = ratio

    clamped_ratio = max(0.0, min(1.0, best_ratio))  # 指針超出刻度範圍時夾在邊界，不外推
    return min_value + clamped_ratio * (max_value - min_value)

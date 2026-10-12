"""指針式儀表（壓力錶、溫度錶等）讀值：使用者輸入最小/最大刻度與對應角度，
偵測指針角度後線性換算成讀值。

角度慣例：以畫面座標系（y 軸向下）的 atan2(dy, dx) 為準，0 度＝3 點鐘方向，
角度隨順時針方向遞增（因為 y 向下，順時針剛好是角度增加的方向）。使用者輸入
的 min_angle／max_angle 要用同一套慣例量測，這是本模組最不直覺、最需要在
前端說明清楚的地方。

流程：
1. 找錶面圓心：優先用 HoughCircles 抓外框圓；找不到就要求使用者提供 center_x/center_y。
2. 以 Lab 色差（相對於錶面底色）取前景，彩色指針也抓得到。
3. HoughLinesP 找線段，保留所在直線通過圓心附近的，依方向投票（權重＝長度）選出指針方向；針尖是兩端中延伸較長的一端。
4. 指針角度 → 用 min_angle/max_angle 對應 min_value/max_value 線性內插，
   處理跨 360 度的情況（例如 min_angle=225、max_angle=135，指針順時針掃過頂端）。
"""

import math

import cv2
import numpy as np

from core.schemas import ModuleError

_WORK_SIZE = 640  # 指針偵測的工作解析度（最長邊）
_NEEDLE_MAX_OFFSET_RATIO = 0.12  # 圓心到線段所在直線的距離要在這個比例的半徑內，才算是通過軸心的指針
_NEEDLE_MIN_LEN_RATIO = 0.25  # 指針長度至少要有半徑的這個比例，避免把刻度線、數字誤認成指針


def find_center(gray: np.ndarray) -> tuple[float, float, float] | None:
    """找錶面外框圓，回傳 (cx, cy, r)；找不到回傳 None。"""
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(h, w),
        param1=100,
        param2=40,
        minRadius=min(h, w) // 6,
        maxRadius=min(h, w) // 2,
    )
    if circles is None or len(circles[0]) == 0:
        return None
    cx, cy, r = circles[0][0]
    return float(cx), float(cy), float(r)


def _foreground(bgr: np.ndarray, cx: float, cy: float, r: float) -> np.ndarray:
    """指針與刻度等「比附近的錶面底色突出」的像素。用 Lab 色差而不是灰階 Otsu：紅色指針在金色錶面上灰階幾乎
    一樣，灰階二值化會把它丟掉；底色用「局部」中位數而不是整張圖的單一顏色：錶面常有光照渐变，單一底色
    會把整片較亮或較暗的區域都當成前景。局部視窗要比指針寬度大很多、又比錶面小。"""
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, (5, 5), 0), cv2.COLOR_BGR2LAB)
    window = int(r * 0.3) | 1
    background = cv2.medianBlur(lab, min(window, 255))
    diff = np.linalg.norm(lab.astype(np.float32) - background.astype(np.float32), axis=2)
    yy, xx = np.mgrid[0 : diff.shape[0], 0 : diff.shape[1]]
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= (0.95 * r) ** 2
    scaled = np.clip(diff * (255.0 / max(float(diff[inside].max()), 1.0)), 0, 255).astype(np.uint8)
    threshold, _ = cv2.threshold(scaled[inside].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return ((scaled > threshold) & inside).astype(np.uint8) * 255


def _reach(mask: np.ndarray, px: float, py: float, angle_deg: float, r: float) -> float:
    """從軸心 (px, py) 沿著角度往外走，指針在前景上連續延伸到多遠（容許極短的斷點）。軸心帽常是空心圓，
    所以從 0.1 倍半徑之外才開始找，並容許在 0.1~0.3 倍半徑之間才碰到指針。找不到回傳 0。"""
    dx, dy = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    h, w = mask.shape
    start, first_limit, max_gap = int(r * 0.1), int(r * 0.3), max(4, int(r * 0.02))
    reach, gap, seen = 0.0, 0, False
    for step in range(start, int(r * 1.0)):
        x, y = round(px + dx * step), round(py + dy * step)
        if not (0 <= x < w and 0 <= y < h):
            break
        if mask[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2].any():
            reach, gap, seen = float(step), 0, True
        elif seen:
            gap += 1
            if gap > max_gap:
                break
        elif step > first_limit:
            return 0.0
    return reach


def detect_needle_angle(bgr: np.ndarray, cx: float, cy: float, r: float) -> tuple[float, float]:
    """回傳 (角度 0~360, 指針長度 px)。偵測不到指針時拋出 ModuleError。

    指針是一條通過軸心的長直線（兩端都可能離圓心很遠，例如帶配重的細長指針），所以找的是「直線是否通過
    圓心附近」而不是「端點是否靠近圓心」；方向由直線決定（不受圓心誤差影響），針尖是兩端中連續前景延伸
    比較長的那端（配重比指針短）。"""
    # 縮小到最長邊約 640 px 處理（局部中位數很吃解析度）；角度不受縮放影響，長度最後換算回原圖
    scale = min(1.0, _WORK_SIZE / max(bgr.shape[:2]))
    if scale < 1.0:
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cx, cy, r = cx * scale, cy * scale, r * scale
    mask = _foreground(bgr, cx, cy, r)
    lines = cv2.HoughLinesP(
        mask,
        1,
        np.pi / 180,
        threshold=30,
        minLineLength=max(int(r * _NEEDLE_MIN_LEN_RATIO), 10),
        maxLineGap=int(r * 0.03) + 3,
    )
    if lines is None:
        raise ModuleError("找不到指針，請確認畫面清楚、指針跟錶面對比明顯", 422)

    # 每條線段投票給它的方向（0~180 度），權重是長度；只收「直線通過圓心附近」的
    votes: dict[int, float] = {}
    members: dict[int, list[tuple[float, float, float, float]]] = {}
    for x1, y1, x2, y2 in lines.reshape(-1, 4).astype(float):
        length = math.hypot(x2 - x1, y2 - y1)
        distance = abs((x2 - x1) * (y1 - cy) - (x1 - cx) * (y2 - y1)) / max(length, 1e-6)  # 圓心到這條直線的距離
        if distance > r * _NEEDLE_MAX_OFFSET_RATIO:
            continue
        direction = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        key = round(direction / 2)
        votes[key] = votes.get(key, 0.0) + length
        members.setdefault(key, []).append((x1, y1, x2, y2))
    if not votes:
        raise ModuleError("有偵測到線段，但沒有任何一條通過圓心附近，可能圓心座標不準或指針太短", 422)

    # 相鄰方向合併後取最高票，用該方向內的線段擬合出精確方向
    smoothed = {k: votes.get(k - 1, 0) + votes[k] + votes.get(k + 1, 0) for k in votes}
    best_key = max(smoothed, key=smoothed.get)
    points = [
        pt for k in (best_key - 1, best_key, best_key + 1) for seg in members.get(k, []) for pt in (seg[:2], seg[2:])
    ]
    vx, vy, x0, y0 = cv2.fitLine(np.array(points, dtype=np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    line_angle = math.degrees(math.atan2(vy, vx)) % 360
    # 直線上離圓心最近的點當作軸心（只用來量兩端的延伸長度）
    t = (cx - x0) * vx + (cy - y0) * vy
    hub_x, hub_y = x0 + t * vx, y0 + t * vy

    forward = _reach(mask, hub_x, hub_y, line_angle, r)
    backward = _reach(mask, hub_x, hub_y, line_angle + 180, r)
    angle = line_angle if forward >= backward else (line_angle + 180) % 360
    return angle, max(forward, backward) / scale


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

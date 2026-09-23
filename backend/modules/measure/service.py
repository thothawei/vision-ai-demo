"""M2 零件計數與尺寸量測。

計數：Otsu 二值化 → 開運算去雜訊 → distance transform + watershed 分離相黏零件。
量測：畫面需放一個 ArUco 標記（scripts/make_aruco.py 產生可列印 PDF）當比例尺，
用標記四角做透視校正（homography），把整張圖攤平成「每 mm 固定像素數」的正視圖再量測，
降低手機拍攝角度造成的透視誤差；仍假設待測物與標記共平面，非共平面時誤差會變大，見 README 精度限制。
"""

import time

import cv2
import numpy as np

from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "measure"

ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
PX_PER_MM = 10  # 透視校正後的輸出解析度


# ---------- M2-1 計數 ----------


def count_parts(image_bytes: bytes, expected_count: int | None, min_area_ratio: float) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    binary = _binarize_foreground_minority(gray)

    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
    sure_bg = cv2.dilate(opened, kernel, iterations=3)

    dist = cv2.distanceTransform(opened, cv2.DIST_L2, 5)
    # 用「距離變換的局部極大值」當種子點，而不是整塊閾值：
    # 整塊閾值對相黏零件會把兩顆的前景合成同一塊連通區域，分不開；
    # 局部極大值抓的是每顆零件自己的中心峰值，即使邊緣相黏也能各自成一個種子。
    # local_kernel 大小＝能分辨的最小零件間距，零件中心距離小於這個值時仍會被視為同一顆。
    local_kernel = np.ones((25, 25), np.uint8)
    local_max = cv2.dilate(dist, local_kernel)
    sure_fg = ((dist == local_max) & (dist > 0.3 * dist.max())).astype(np.uint8) * 255
    unknown = cv2.subtract(sure_bg, sure_fg)

    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0
    cv2.watershed(bgr, markers)

    min_area = image.width * image.height * min_area_ratio
    items = []
    annotated = bgr.copy()
    for label in range(2, markers.max() + 1):
        mask = (markers == label).astype(np.uint8) * 255
        area = int(cv2.countNonZero(mask))
        if area < min_area:
            continue
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        items.append({"編號": len(items) + 1, "面積px": area, "中心點": [round(cx), round(cy)]})
        cv2.drawContours(annotated, [contour], -1, (0, 200, 0), 2)
        cv2.putText(annotated, str(items[-1]["編號"]), (round(cx) - 10, round(cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

    verdict = "INFO"
    if expected_count is not None:
        verdict = "OK" if len(items) == expected_count else "NG"

    result = [{"計數結果": len(items), "預期數量": expected_count, "明細": items}]
    return record_result(MODULE, verdict, result, "opencv-watershed", started, bgr_to_data_url(annotated))


def _binarize_foreground_minority(gray: np.ndarray) -> np.ndarray:
    """假設零件是畫面中的少數像素（背景占多數）；Otsu 兩種極性都算，取前景面積較小的那個。

    這是本模組最大的精度限制：背景必須跟零件有明顯亮度反差，且零件不能佔滿畫面。
    """
    _, binary_normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary_inv = cv2.bitwise_not(binary_normal)
    return binary_normal if cv2.countNonZero(binary_normal) <= cv2.countNonZero(binary_inv) else binary_inv


# ---------- M2-2 量測 ----------


def measure_part(
    image_bytes: bytes,
    marker_size_mm: float,
    target_length_mm: float | None,
    target_width_mm: float | None,
    tolerance_mm: float,
) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    corners_list, ids, _ = cv2.aruco.ArucoDetector(ARUCO_DICT).detectMarkers(bgr)
    if ids is None or len(ids) == 0:
        raise ModuleError("畫面中找不到 ArUco 標記，請用 scripts/make_aruco.py 產生的標記並放進畫面", 422)

    marker_corners = corners_list[0][0]  # 只用偵測到的第一個標記當比例尺
    warped = _rectify_by_marker(bgr, marker_corners, marker_size_mm)

    contour = _find_workpiece_contour(warped, marker_size_mm)
    if contour is None:
        raise ModuleError("透視校正後找不到標記以外的待測物輪廓，請確認待測物與標記都在畫面中且對比明顯", 422)

    rect = cv2.minAreaRect(contour)
    (_, _), (w_px, h_px), _ = rect
    length_mm, width_mm = sorted((w_px / PX_PER_MM, h_px / PX_PER_MM), reverse=True)

    holes_mm = _measure_holes(warped, contour)

    item = {
        "長度mm": round(length_mm, 2),
        "寬度mm": round(width_mm, 2),
        "孔徑mm": [round(d, 2) for d in holes_mm],
    }
    verdict = "INFO"
    if target_length_mm is not None:
        item["目標長度mm"] = target_length_mm
        item["長度誤差mm"] = round(length_mm - target_length_mm, 2)
        length_ok = abs(length_mm - target_length_mm) <= tolerance_mm
        verdict = "OK" if length_ok else "NG"
    if target_width_mm is not None:
        item["目標寬度mm"] = target_width_mm
        item["寬度誤差mm"] = round(width_mm - target_width_mm, 2)
        width_ok = abs(width_mm - target_width_mm) <= tolerance_mm
        verdict = "OK" if verdict != "NG" and width_ok else "NG"

    annotated = warped.copy()
    box = cv2.boxPoints(rect).astype(np.int32)
    cv2.drawContours(annotated, [box], 0, (0, 200, 0), 2)
    cv2.putText(annotated, f"{length_mm:.1f} x {width_mm:.1f} mm", (box[0][0], max(box[0][1] - 10, 15)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2, cv2.LINE_AA)

    return record_result(MODULE, verdict, [item], "opencv-aruco", started, bgr_to_data_url(annotated))


def _rectify_by_marker(bgr: np.ndarray, marker_corners: np.ndarray, marker_size_mm: float):
    """用標記四角做透視轉換，把整張圖攤平成「PX_PER_MM 像素/mm」的正視圖。"""
    s = marker_size_mm * PX_PER_MM
    margin = s * 3  # 標記以外要留夠空間放待測物
    dst = np.array([[margin, margin], [margin + s, margin], [margin + s, margin + s], [margin, margin + s]],
                   dtype=np.float32)
    h_mat = cv2.getPerspectiveTransform(marker_corners.astype(np.float32), dst)
    canvas_size = round(margin * 2 + s)
    warped = cv2.warpPerspective(bgr, h_mat, (canvas_size, canvas_size), borderValue=(255, 255, 255))
    return warped


def _find_workpiece_contour(warped: np.ndarray, marker_size_mm: float):
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = _binarize_foreground_minority(gray)

    # 挖掉標記本身所在區域（黑白格紋會被誤判成前景），只留下標記外的東西
    s = marker_size_mm * PX_PER_MM
    margin = s * 3
    mask = np.ones(binary.shape, dtype=np.uint8) * 255
    cv2.rectangle(mask, (round(margin) - 5, round(margin) - 5), (round(margin + s) + 5, round(margin + s) + 5), 0, -1)
    binary = cv2.bitwise_and(binary, mask)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _measure_holes(warped: np.ndarray, workpiece_contour) -> list[float]:
    """待測物輪廓內部的孔洞（用 RETR_CCOMP 的 hierarchy 找子輪廓），回傳每個孔的直徑 mm。"""
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    binary = _binarize_foreground_minority(gray)
    x, y, w, h = cv2.boundingRect(workpiece_contour)
    roi = binary[y:y + h, x:x + w]
    contours, hierarchy = cv2.findContours(roi, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []

    diameters = []
    for i, h_info in enumerate(hierarchy[0]):
        parent = h_info[3]
        if parent == -1:
            continue  # 不是子輪廓（不是孔）
        area = cv2.contourArea(contours[i])
        if area < 20:
            continue
        _, radius = cv2.minEnclosingCircle(contours[i])
        diameters.append(radius * 2 / PX_PER_MM)
    return diameters

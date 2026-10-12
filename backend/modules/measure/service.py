"""M2 零件計數與尺寸量測。

計數：與背景的 Lab 色差取前景 → 閉運算填洞 → distance transform 的 h-maxima + watershed 分離相黏零件。
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

    labels = _segment_parts(bgr)

    min_area = image.width * image.height * min_area_ratio
    items = []
    annotated = bgr.copy()
    for label in range(1, int(labels.max()) + 1):
        mask = (labels == label).astype(np.uint8) * 255
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
        cv2.putText(
            annotated,
            str(items[-1]["編號"]),
            (round(cx) - 10, round(cy)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    verdict = "INFO"
    if expected_count is not None:
        verdict = "OK" if len(items) == expected_count else "NG"

    result = [{"計數結果": len(items), "預期數量": expected_count, "明細": items}]
    return record_result(MODULE, verdict, result, "opencv-watershed", started, bgr_to_data_url(annotated))


_MIN_COLOR_DIFF = 12.0  # 與背景的 Lab 色差低於這個值不算前景（避免空畫面被雜訊切出一堆東西）
_PEAK_MIN_RATIO = (
    0.7  # 候選種子（距離變換的峰）至少要有「最大內切圓半徑」的這個比例；螺紋牙齒、凸起比零件本體小很多，會被排除
)
_MIN_PIECE_RATIO = 0.3  # 相鄰兩個區域中較小的面積低於較大的這個比例，視為附屬的凸起（端帽、被反光切斷的一截），併回去
_NECK_MAX_RATIO = 0.7  # 兩個相鄰區域之間的頸部要比「較小的峰」窄到這個比例以下，才當作兩個零件；否則合併回去
_WORK_SIZE = 800  # 分割的工作解析度（最長邊）


_BACKGROUND_MIN_FRACTION = (
    0.5  # 畫面邊緣帶中「像背景」的像素比例低於這個值，代表沒有可參考的背景（零件占滿畫面、背景雜亂）
)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """把外輪廓圍起來的區域全部填滿：高光、反光造成的缺口、螺絲孔都算零件的一部分。
    限制：O 形環、墊圈這類中空零件，嵌在裡面的另一個環會被一起填掉，併成同一個零件。"""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


def _foreground(bgr: np.ndarray) -> np.ndarray:
    """零件的前景遮罩。以畫面邊緣的中位數顏色當背景，用 Lab 色差取前景（而不是灰階 Otsu：金屬零件的高光會
    被當成背景，前景因此破碎，每顆零件被切成十幾塊）。背景平滑時再加上「邊緣輪廓圍起來的區域」：金屬零件放在
    灰色背景上色差很小，只靠色差會剩下零星碎片，但輪廓邊緣仍然明顯。再用閉運算與填洞把高光造成的缺口補起來。
    畫面邊緣沒有可參考的背景（零件占滿畫面）時直接報錯，不回報一個沒有依據的數字。"""
    h, w = bgr.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    m = max(2, int(min(h, w) * 0.03))
    band = np.zeros((h, w), bool)
    band[:m] = band[-m:] = True
    band[:, :m] = band[:, -m:] = True
    background = np.median(lab[band], axis=0)
    diff = np.linalg.norm(lab - background, axis=2)
    if float((diff[band] < _MIN_COLOR_DIFF).mean()) < _BACKGROUND_MIN_FRACTION:
        raise ModuleError(
            "畫面邊緣沒有可參考的背景（零件占滿畫面，或背景雜亂），無法計數；請把零件放在素色背景上、四周留一點空白",
            422,
        )
    scaled = np.clip(diff * (255.0 / max(float(diff.max()), 1.0)), 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    floor = _MIN_COLOR_DIFF * 255.0 / max(float(diff.max()), 1.0)
    mask = (scaled > max(otsu, floor)).astype(np.uint8) * 255

    # 邊緣輪廓：背景平滑（邊緣帶幾乎沒有邊緣）時才用，雜亂背景會到處都是邊緣
    gradient = np.hypot(cv2.Sobel(lab[:, :, 0], cv2.CV_32F, 1, 0), cv2.Sobel(lab[:, :, 0], cv2.CV_32F, 0, 1))
    g8 = np.clip(gradient * (255.0 / max(float(gradient.max()), 1.0)), 0, 255).astype(np.uint8)
    g_threshold, _ = cv2.threshold(g8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = (g8 > g_threshold).astype(np.uint8) * 255
    if float((edges[band] > 0).mean()) < 0.05:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, int(min(h, w) * 0.012)) | 1,) * 2)
        outline = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k)
        regions = _fill_holes(outline)
        n_regions, region_labels = cv2.connectedComponents(regions)
        for r in range(1, n_regions):
            region = region_labels == r
            if float((mask[region] > 0).mean()) < 0.6:  # 色差已經抓得好好的區域不動它，免得閉運算把相黏零件的頸部填寬
                mask[region] = 255

    close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, int(min(h, w) * 0.012)) | 1,) * 2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close)
    return cv2.morphologyEx(_fill_holes(mask), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _segment_parts(bgr: np.ndarray) -> np.ndarray:
    """回傳標籤圖（0＝背景，1..N＝各零件）。每個連通區域預設是一個零件；只有「有證據」才分開：區域內有兩個以上
    夠高的距離變換峰（各自至少是最大內切圓半徑的 70%），而且它們之間的頸部明顯比較窄（見 _NECK_MAX_RATIO）。
    細長零件（螺絲、電阻）的距離變換沿著本體是一條稜線，螺紋牙齒的小峰太低、頸部也不夠窄，不會被切開；
    兩顆相黏的圓形零件各有一個明顯的峰、中間有頸部，會被分成兩個。"""
    from skimage.morphology import h_maxima
    from skimage.segmentation import watershed

    scale = min(1.0, _WORK_SIZE / max(bgr.shape[:2]))
    work = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else bgr
    mask = _foreground(work)
    labels = np.zeros(mask.shape, np.int32)
    if cv2.countNonZero(mask) == 0:
        return labels

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    n_comp, comp = cv2.connectedComponents(mask)
    next_label = 1
    for c in _real_components(comp, n_comp):
        region = comp == c
        radius = float(dist[region].max())
        seeds = (
            h_maxima(np.where(region, dist, 0), max(1.0, 0.1 * radius)) & region & (dist >= _PEAK_MIN_RATIO * radius)
        )
        seed_labels = cv2.connectedComponents(seeds.astype(np.uint8))[1]
        if seed_labels.max() <= 1:
            labels[region] = next_label
            next_label += 1
            continue
        piece = watershed(-dist, seed_labels, mask=region)
        for group in _merge_wide_necks(piece, dist):
            labels[np.isin(piece, group)] = next_label
            next_label += 1
    if scale < 1.0:
        labels = cv2.resize(
            labels.astype(np.float32), (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_NEAREST
        ).astype(np.int32)
    return labels


_FRAGMENT_MEDIAN_RATIO = 0.1  # 面積低於「其餘零件面積中位數」乘這個比例的碎片丟掉
_ABSORB_AREA_RATIO = 5  # 較大零件的面積至少是碎片的這麼多倍，碎片才會被併入


def _real_components(comp: np.ndarray, n_comp: int) -> list[int]:
    """前景連通區中真正是「零件」的編號。高光、陰影常在零件旁邊或裡面切出幾個獨立的小塊，它們不是零件：
    ① 重心落在較大零件的凸包內的小塊，當作該零件的一部分併入（丟掉，不另外計數）；
    ② 面積遠小於其餘零件中位數的碎片（例如印在零件旁的編號文字）丟掉。"""
    areas, hulls, centers = {}, {}, {}
    for c in range(1, n_comp):
        ys, xs = np.nonzero(comp == c)
        areas[c] = len(xs)
        centers[c] = (float(xs.mean()), float(ys.mean()))
        hulls[c] = cv2.convexHull(np.column_stack([xs, ys]).astype(np.int32))
    kept = []
    for c, area in areas.items():
        absorbed = any(
            o != c and areas[o] >= _ABSORB_AREA_RATIO * area and cv2.pointPolygonTest(hulls[o], centers[c], False) >= 0
            for o in areas
        )
        if not absorbed:
            kept.append(c)
    if len(kept) >= 3:
        median = float(np.median([areas[c] for c in kept]))
        kept = [c for c in kept if areas[c] >= _FRAGMENT_MEDIAN_RATIO * median]
    return kept


def _merge_wide_necks(piece: np.ndarray, dist: np.ndarray) -> list[list[int]]:
    """把 watershed 切出的相鄰區域，頸部不夠窄的併回去；回傳每個零件由哪些區域組成。"""
    ids = [int(i) for i in np.unique(piece) if i > 0]
    peak = {i: float(dist[piece == i].max()) for i in ids}
    area = {i: int((piece == i).sum()) for i in ids}
    saddle: dict[tuple[int, int], float] = {}
    for a, b in ((piece[:, :-1], piece[:, 1:]), (piece[:-1, :], piece[1:, :])):
        da, db = (
            (dist[:, :-1], dist[:, 1:])
            if a.shape[0] == piece.shape[0] and a.shape[1] != piece.shape[1]
            else (dist[:-1, :], dist[1:, :])
        )
        touching = (a != b) & (a > 0) & (b > 0)
        for x, y, height in zip(a[touching], b[touching], np.minimum(da, db)[touching], strict=True):
            key = (int(min(x, y)), int(max(x, y)))
            saddle[key] = max(saddle.get(key, 0.0), float(height))

    parent = {i: i for i in ids}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (x, y), height in saddle.items():
        small, large = sorted((area[x], area[y]))
        if height >= _NECK_MAX_RATIO * min(peak[x], peak[y]) or small < _MIN_PIECE_RATIO * large:
            parent[find(x)] = find(y)
    groups: dict[int, list[int]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _binarize_foreground_minority(gray: np.ndarray) -> np.ndarray:
    """假設零件是畫面中的少數像素（背景占多數）；Otsu 兩種極性都算，取前景面積較小的那個。

    這是本模組最大的精度限制：背景必須跟零件有明顯亮度反差，且零件不能佔滿畫面。
    """
    _, binary_normal = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary_inv = cv2.bitwise_not(binary_normal)
    return binary_normal if cv2.countNonZero(binary_normal) <= cv2.countNonZero(binary_inv) else binary_inv


# ---------- M2-2 量測 ----------


def _marker_detector() -> "cv2.aruco.ArucoDetector":
    """角點做子像素細化：預設只有整數像素精度，標記只有一百多像素寬時，單一角點差 1 像素就會讓比例尺偏約 1%。"""
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(ARUCO_DICT, params)


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

    corners_list, ids, _ = _marker_detector().detectMarkers(bgr)
    if ids is None or len(ids) == 0:
        raise ModuleError("畫面中找不到 ArUco 標記，請用 scripts/make_aruco.py 產生的標記並放進畫面", 422)

    marker_corners = corners_list[0][0]  # 只用偵測到的第一個標記當比例尺
    warped, valid, px_per_mm, marker_box = _rectify_by_marker(bgr, marker_corners, marker_size_mm)

    mask = _workpiece_mask(warped, valid, marker_box)
    contour = _largest_contour(mask)
    if contour is None:
        raise ModuleError("透視校正後找不到標記以外的待測物輪廓，請確認待測物與標記都在畫面中且對比明顯", 422)
    if _touches_edge(contour, valid):
        raise ModuleError(
            "待測物碰到畫面邊緣（只拍到一部分），量到的尺寸會偏小；請讓整個待測物與標記都完整入鏡、四周留一點空白", 422
        )

    rect = cv2.minAreaRect(contour)
    (_, _), (w_px, h_px), _ = rect
    length_mm, width_mm = sorted((w_px / px_per_mm, h_px / px_per_mm), reverse=True)

    holes_mm = _measure_holes(mask, contour, px_per_mm)

    item = {
        "長度mm": round(length_mm, 2),
        "寬度mm": round(width_mm, 2),
        "孔徑mm": [round(d, 2) for d in holes_mm],
    }
    verdict = "INFO"
    out_of_tolerance = []
    if target_length_mm is not None:
        item["目標長度mm"] = target_length_mm
        item["長度誤差mm"] = round(length_mm - target_length_mm, 2)
        length_ok = abs(length_mm - target_length_mm) <= tolerance_mm
        verdict = "OK" if length_ok else "NG"
        if not length_ok:
            out_of_tolerance.append("長度")
    if target_width_mm is not None:
        item["目標寬度mm"] = target_width_mm
        item["寬度誤差mm"] = round(width_mm - target_width_mm, 2)
        width_ok = abs(width_mm - target_width_mm) <= tolerance_mm
        verdict = "OK" if verdict != "NG" and width_ok else "NG"
        if not width_ok:
            out_of_tolerance.append("寬度")
    if out_of_tolerance:
        item["超差項目"] = out_of_tolerance
    if target_length_mm is not None or target_width_mm is not None:
        item["公差mm"] = tolerance_mm  # 存下來，量測值的規格上下限（目標 ± 公差）才算得出來

    annotated = warped.copy()
    box = cv2.boxPoints(rect).astype(np.int32)
    cv2.drawContours(annotated, [box], 0, (0, 200, 0), 2)
    cv2.putText(
        annotated,
        f"{length_mm:.1f} x {width_mm:.1f} mm",
        (box[0][0], max(box[0][1] - 10, 15)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 200, 0),
        2,
        cv2.LINE_AA,
    )

    return record_result(MODULE, verdict, [item], "opencv-aruco", started, bgr_to_data_url(annotated))


_MAX_CANVAS_PX = 5000  # 校正後畫布的最大邊長（像素）；視野更大時降低解析度
_MAX_FIELD_MM = 1000.0  # 視野超過這個範圍（極端斜拍，遠處的點被拉到無限遠）就只取標記周圍
_MIN_COLOR_DIFF = 12.0  # 與背景的 Lab 色差低於這個值不算工件


def _rectify_by_marker(bgr: np.ndarray, marker_corners: np.ndarray, marker_size_mm: float):
    """用標記四角做透視轉換，把整張圖攤平成約 PX_PER_MM 像素/mm 的正視圖。

    畫布依「整張照片攤平後的範圍」決定，不再只涵蓋標記周圍固定幾倍的範圍：舊做法只取標記四周 ±3 個標記邊長，
    工件比這大時會被無聲截斷，回報一個偏小的尺寸。回傳 (正視圖, 有效區域遮罩, 實際像素/mm, 標記方框)。"""
    h, w = bgr.shape[:2]
    image_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)

    def homography(scale: float) -> np.ndarray:
        s = marker_size_mm * scale
        dst = np.array([[0, 0], [s, 0], [s, s], [0, s]], dtype=np.float32)
        return cv2.getPerspectiveTransform(marker_corners.astype(np.float32), dst)

    h0 = homography(1.0)  # 1 像素 = 1 mm 的座標，只用來量範圍
    pts = cv2.perspectiveTransform(image_corners, h0).reshape(-1, 2)
    marker_mm = cv2.perspectiveTransform(marker_corners.astype(np.float32).reshape(-1, 1, 2), h0).reshape(-1, 2)
    if not np.isfinite(pts).all() or np.ptp(pts, axis=0).max() > _MAX_FIELD_MM:
        center = marker_mm.mean(axis=0)
        lo, hi = center - _MAX_FIELD_MM / 2, center + _MAX_FIELD_MM / 2
    else:
        lo, hi = pts.min(axis=0), pts.max(axis=0)
    extent_mm = float((hi - lo).max())
    scale = min(float(PX_PER_MM), _MAX_CANVAS_PX / max(extent_mm, 1.0))

    shift = np.array([[1, 0, -lo[0] * scale], [0, 1, -lo[1] * scale], [0, 0, 1]], dtype=np.float64)
    h_mat = shift @ homography(scale)
    size = (int(np.ceil((hi[0] - lo[0]) * scale)), int(np.ceil((hi[1] - lo[1]) * scale)))
    warped = cv2.warpPerspective(bgr, h_mat, size, borderValue=(0, 0, 0))
    valid = cv2.warpPerspective(np.full((h, w), 255, np.uint8), h_mat, size, flags=cv2.INTER_NEAREST)
    valid = cv2.erode(valid, np.ones((5, 5), np.uint8)) > 0  # 邊緣的內插像素不算

    box = cv2.perspectiveTransform(marker_corners.astype(np.float32).reshape(-1, 1, 2), h_mat).reshape(-1, 2)
    marker_box = (int(box[:, 0].min()), int(box[:, 1].min()), int(box[:, 0].max()), int(box[:, 1].max()))
    return warped, valid, scale, marker_box


def _background_plane(lab: np.ndarray, band: np.ndarray) -> np.ndarray:
    """背景顏色的平滑模型：用有效區域邊緣帶的像素擬合每個 Lab 通道的平面（一次函數）。照片常有光照漸變（一側較暗），
    單一背景色會把暗的那一半整片當成工件。只用一次函數：高次曲面外推到沒有樣本的地方會失控。
    擬合兩輪，第二輪丟掉殘差大的點（碰到邊緣的工件）。"""
    h, w = band.shape
    ys, xs = np.nonzero(band)
    if len(xs) > 6000:
        pick = np.random.default_rng(0).choice(len(xs), 6000, replace=False)
        ys, xs = ys[pick], xs[pick]

    def design(x, y):
        return np.stack([np.ones_like(x), x / w - 0.5, y / h - 0.5], axis=-1)

    a = design(xs.astype(np.float32), ys.astype(np.float32))
    target = lab[ys, xs]
    keep = np.ones(len(xs), bool)
    coef = np.zeros((3, 3))
    for _ in range(2):
        coef, *_ = np.linalg.lstsq(a[keep], target[keep], rcond=None)
        residual = np.linalg.norm(a @ coef - target, axis=1)
        keep = residual < max(8.0, 3 * float(np.median(residual)))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return (design(xx, yy) @ coef).astype(np.float32)


def _workpiece_mask(warped: np.ndarray, valid: np.ndarray, marker_box: tuple[int, int, int, int]) -> np.ndarray:
    """標記以外、與背景有明顯色差的前景。背景用有效區域邊緣帶擬合的平面（見 _background_plane），不是灰階 Otsu：
    灰階 Otsu 假設工件比背景暗，遇到灰色背景、亮工件、光照漸變都會抓錯。畫面外的區域（攤平後的空白）不參與。"""
    lab = cv2.cvtColor(cv2.GaussianBlur(warped, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    ys, xs = np.nonzero(valid)
    margin = max(5, int(0.03 * min(np.ptp(xs), np.ptp(ys))))
    band = valid & ~cv2.erode(valid.astype(np.uint8), np.ones((2 * margin + 1,) * 2, np.uint8)).astype(bool)
    band = band & ~_box_mask(valid.shape, marker_box, 0)
    if band.sum() < 100:
        band = valid.copy()
    diff = np.linalg.norm(lab - _background_plane(lab, band), axis=2)
    exclude = ~valid | _box_mask(valid.shape, marker_box, max(10, int(0.1 * (marker_box[2] - marker_box[0]))))
    diff[exclude] = 0
    scaled = np.clip(diff * (255.0 / max(float(diff.max()), 1.0)), 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(scaled[valid & ~exclude].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    floor = _MIN_COLOR_DIFF * 255.0 / max(float(diff.max()), 1.0)
    mask = (scaled > max(otsu, floor)).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _box_mask(shape: tuple[int, int], box: tuple[int, int, int, int], pad: int) -> np.ndarray:
    mask = np.zeros(shape, bool)
    mask[max(0, box[1] - pad) : box[3] + pad + 1, max(0, box[0] - pad) : box[2] + pad + 1] = True
    return mask


def _largest_contour(mask: np.ndarray):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return max(contours, key=cv2.contourArea) if contours else None


def _touches_edge(contour, valid: np.ndarray) -> bool:
    """工件輪廓貼著有效區域（照片範圍攤平後）的邊緣，代表只拍到一部分。"""
    edge = valid & ~cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    pts = contour_points = contour.reshape(-1, 2)
    del contour_points
    return bool(edge[pts[:, 1], pts[:, 0]].any())


def _measure_holes(mask: np.ndarray, workpiece_contour, px_per_mm: float) -> list[float]:
    """待測物輪廓內部的孔洞（用 RETR_CCOMP 的 hierarchy 找子輪廓），回傳每個孔的直徑 mm。"""
    x, y, w, h = cv2.boundingRect(workpiece_contour)
    roi = mask[y : y + h, x : x + w]
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
        diameters.append(radius * 2 / px_per_mm)
    return diameters

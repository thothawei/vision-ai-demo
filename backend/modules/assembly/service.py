"""M10 組裝防呆／黃金樣本比對（免訓練）。

使用者在一張「黃金樣本」照片上框多個 ROI（零件應該在的位置），存成「料號設定」。
之後每次辨識：ORB 特徵 + homography 把待測照片對齊到黃金樣本座標系，再逐一用
SSIM 比對每個 ROI（有沒有零件、零件方向對不對），任一 ROI 沒過就整體判 NG。

黃金樣本設定存成檔案（data/golden_samples/<料號>/golden.png + rois.json），
不是資料庫表——跟 M3 自訂類別的 registry 風格一致，這個規模用不到資料庫。
"""

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from core.image_io import bgr_to_data_url, load_image, to_bgr, to_data_url
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError

MODULE = "assembly"

_DEFAULT_GOLDEN_DIR = Path(__file__).resolve().parents[3] / "data" / "golden_samples"


def _golden_dir() -> Path:
    """每次呼叫都重讀 env（跟 INSPECTION_DB/INSPECTION_IMAGES_DIR 同一個模式），
    測試才能用 monkeypatch.setenv 隔離，不會寫進專案真實的 data/golden_samples/。"""
    return Path(os.environ.get("GOLDEN_SAMPLES_DIR", _DEFAULT_GOLDEN_DIR))

MIN_GOOD_MATCHES = 8    # 至少要有這麼多好的特徵配對才嘗試算 homography
MIN_INLIER_RATIO = 0.5  # RANSAC inlier 比例低於這個就當對齊失敗，不硬判 OK/NG
SSIM_THRESHOLD = 0.85   # 低於這個相似度該 ROI 判 NG。實測校準過程：一開始沒做高斯模糊，
                         # warpPerspective 對齊後（尤其 ±15 度旋轉）的插值誤差會讓正確零件的 ROI
                         # 掉到 0.75-0.83，跟「裝反」的 0.708 太接近，門檻很難兩邊都顧到。
                         # 對兩邊 ROI 先做 5x5 高斯模糊再比較後，旋轉/縮放情境的最差分數回升到 0.92
                         # 以上，跟「裝反」(0.71) 之間有足夠安全邊界，0.85 剛好卡在中間。


def _validate_part_no(part_no: str) -> None:
    if not part_no or not all(c.isalnum() or c in "_-" for c in part_no):
        raise ModuleError("料號只能是英數字、底線、連字號", 400)


def save_golden_sample(part_no: str, image_bytes: bytes, rois: list[list[float]]) -> dict:
    _validate_part_no(part_no)
    if not rois:
        raise ModuleError("至少要框 1 個 ROI", 400)
    for r in rois:
        if len(r) != 4:
            raise ModuleError("每個 ROI 要是 [x1,y1,x2,y2]（正規化座標 0~1）", 400)

    image = load_image(image_bytes)
    part_dir = _golden_dir() / part_no
    part_dir.mkdir(parents=True, exist_ok=True)
    image.save(part_dir / "golden.png")
    (part_dir / "rois.json").write_text(json.dumps({"rois": rois}, ensure_ascii=False, indent=2))
    return {"part_no": part_no, "roi_count": len(rois)}


def list_golden_samples() -> list[dict]:
    if not _golden_dir().exists():
        return []
    result = []
    for d in sorted(_golden_dir().iterdir()):
        rois_path = d / "rois.json"
        if rois_path.exists():
            rois = json.loads(rois_path.read_text())["rois"]
            result.append({"part_no": d.name, "roi_count": len(rois)})
    return result


def get_golden_sample(part_no: str) -> dict:
    part_dir = _golden_dir() / part_no
    rois_path = part_dir / "rois.json"
    if not rois_path.exists():
        raise ModuleError(f"找不到料號「{part_no}」的黃金樣本設定", 404)
    rois = json.loads(rois_path.read_text())["rois"]
    golden_image = Image.open(part_dir / "golden.png")
    return {"part_no": part_no, "rois": rois, "golden_image": to_data_url(golden_image)}


_orb = None


def _get_orb():
    global _orb
    if _orb is None:
        _orb = cv2.ORB_create(nfeatures=2000)
    return _orb


def _align_to_golden(golden_bgr: np.ndarray, target_bgr: np.ndarray) -> tuple[np.ndarray | None, dict]:
    """把 target 對齊到 golden 的座標系。回傳 (對齊後影像 或 None, 除錯資訊)。"""
    orb = _get_orb()
    golden_gray = cv2.cvtColor(golden_bgr, cv2.COLOR_BGR2GRAY)
    target_gray = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)

    kp1, des1 = orb.detectAndCompute(golden_gray, None)
    kp2, des2 = orb.detectAndCompute(target_gray, None)
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return None, {"配對數": 0, "inlier比例": None, "原因": "特徵點太少"}

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = bf.knnMatch(des2, des1, k=2)  # 拿 target 的每個特徵點去 golden 裡找最像的兩個
    good = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:  # Lowe's ratio test，濾掉不夠明確的配對
            good.append(m)

    if len(good) < MIN_GOOD_MATCHES:
        return None, {"配對數": len(good), "inlier比例": None, "原因": "有效特徵配對數不足"}

    src_pts = np.float32([kp2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None:
        return None, {"配對數": len(good), "inlier比例": None, "原因": "homography 求解失敗"}

    inlier_ratio = float(mask.sum()) / len(good)
    if inlier_ratio < MIN_INLIER_RATIO:
        return None, {"配對數": len(good), "inlier比例": round(inlier_ratio, 3), "原因": "對齊品質太差"}

    h, w = golden_bgr.shape[:2]
    aligned = cv2.warpPerspective(target_bgr, H, (w, h))
    return aligned, {"配對數": len(good), "inlier比例": round(inlier_ratio, 3), "原因": None}


def inspect_assembly(part_no: str, image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    part_dir = _golden_dir() / part_no
    rois_path = part_dir / "rois.json"
    if not rois_path.exists():
        raise ModuleError(f"找不到料號「{part_no}」的黃金樣本設定，請先建立", 404)

    rois = json.loads(rois_path.read_text())["rois"]
    golden_image = Image.open(part_dir / "golden.png").convert("RGB")
    golden_bgr = to_bgr(golden_image)

    target_image = load_image(image_bytes)
    target_bgr = to_bgr(target_image)

    aligned, debug = _align_to_golden(golden_bgr, target_bgr)
    if aligned is None:
        item = {"料號": part_no, **debug, "提示": "無法對齊到黃金樣本，請確認拍攝角度/光線跟黃金樣本接近"}
        return record_result(MODULE, "INFO", [item], "orb-homography", started, bgr_to_data_url(target_bgr))

    h, w = golden_bgr.shape[:2]
    results = []
    annotated = aligned.copy()
    for i, (x1n, y1n, x2n, y2n) in enumerate(rois):
        x1, y1, x2, y2 = int(x1n * w), int(y1n * h), int(x2n * w), int(y2n * h)
        golden_roi = cv2.cvtColor(golden_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        target_roi = cv2.cvtColor(aligned[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        if golden_roi.size == 0 or target_roi.size == 0 or min(golden_roi.shape) < 7:
            score = 0.0
        else:
            # 先做輕度高斯模糊再比較：warpPerspective 對齊後的插值誤差在像素級會讓 SSIM
            # 對旋轉/縮放這種「零件其實都對」的情境過度敏感，模糊掉之後只比較區塊級的結構相似度。
            golden_roi = cv2.GaussianBlur(golden_roi, (5, 5), 0)
            target_roi = cv2.GaussianBlur(target_roi, (5, 5), 0)
            score = float(structural_similarity(golden_roi, target_roi))
        ok = score >= SSIM_THRESHOLD
        results.append({"ROI編號": i + 1, "相似度": round(score, 4), "判定": "OK" if ok else "NG"})
        color = (0, 200, 0) if ok else (0, 0, 255)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, f"{i + 1}:{score:.2f}", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    verdict = "NG" if any(r["判定"] == "NG" for r in results) else "OK"
    item = {
        "料號": part_no, "對齊配對數": debug["配對數"], "對齊inlier比例": debug["inlier比例"],
        "明細": results,
    }
    return record_result(MODULE, verdict, [item], "orb-homography-ssim", started, bgr_to_data_url(annotated))

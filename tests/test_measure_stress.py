"""Phase 23：尺寸量測的合成壓力測試。

**這不是真實照片評估**（公開網路上找不到「ArUco 標記＋已知尺寸工件」的照片，見 tests/real_samples/measure/README.md），
而是把合成場景加上真實拍攝常見的退化：透視傾斜、旋轉、噪點、模糊、JPEG、光照漸變、灰色背景、亮工件、大工件。
這些情境曾經讓舊做法回報 130×128 mm（實際 50×20）、把 150 mm 的工件無聲截斷成 59 mm。
"""

import cv2
import numpy as np
import pytest
from core.schemas import ModuleError
from modules.measure import service
from samples import make_samples

MARKER_MM = make_samples.TEST_MARKER_SIZE_MM


def _scene(length=50, width=20, hole=5):
    image, _ = make_samples.make_measure_scene(length, width, hole)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _recolor(bgr, background, workpiece):
    """換背景與工件的灰階（標記的黑白格保持不動）。"""
    out = bgr.copy()
    px = int(MARKER_MM * make_samples.TEST_PX_PER_MM)
    in_marker = np.zeros(out.shape[:2], bool)
    in_marker[40 : 40 + px, 40 : 40 + px] = True
    out[(bgr[:, :, 0] == 255) & ~in_marker] = background
    out[(bgr[:, :, 0] == 0) & ~in_marker] = workpiece
    return out


def _perspective(bgr, factor):
    h, w = bgr.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * 0.5 * (1 - factor), 0], [w - w * 0.5 * (1 - factor), 0], [w, h], [0, h]])
    return cv2.warpPerspective(bgr, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(255, 255, 255))


def _rotate(bgr, angle):
    padded = cv2.copyMakeBorder(bgr, 300, 300, 300, 300, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    h, w = padded.shape[:2]
    return cv2.warpAffine(
        padded, cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0), (w, h), borderValue=(255, 255, 255)
    )


def _noise(bgr):
    return np.clip(bgr.astype(np.float32) + np.random.default_rng(0).normal(0, 10, bgr.shape), 0, 255).astype(np.uint8)


def _gradient(bgr):
    ramp = np.tile(np.linspace(0.55, 1.0, bgr.shape[1], dtype=np.float32), (bgr.shape[0], 1))[:, :, None]
    return np.clip(bgr * ramp, 0, 255).astype(np.uint8)


def _measure(bgr, quality=95):
    data = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
    return service.measure_part(data, MARKER_MM, None, None, 1.0).items[0]


CASES = {
    "正視": (lambda: _scene(), 50, 20),
    "透視傾斜 30°": (lambda: _perspective(_scene(), 0.87), 50, 20),
    "透視傾斜 40°": (lambda: _perspective(_scene(), 0.77), 50, 20),
    "整張旋轉 15°": (lambda: _rotate(_scene(), 15), 50, 20),
    "整張旋轉 45°": (lambda: _rotate(_scene(), 45), 50, 20),
    "高斯噪點": (lambda: _noise(_scene()), 50, 20),
    "模糊": (lambda: cv2.GaussianBlur(_scene(), (0, 0), 2.0), 50, 20),
    "光照漸變（左暗右亮）": (lambda: _gradient(_scene()), 50, 20),
    "灰色背景＋淺灰工件": (lambda: _recolor(_scene(), 200, 120), 50, 20),
    "灰色背景＋亮工件": (lambda: _recolor(_scene(), 128, 230), 50, 20),
    "大工件 150×40（標記 30mm）": (lambda: _scene(150, 40, 8), 150, 40),
    "大工件 100×60": (lambda: _scene(100, 60, 10), 100, 60),
}


@pytest.mark.parametrize("name", CASES)
def test_measurement_stays_within_1mm_under_realistic_degradation(name, client):
    build, length, width = CASES[name]
    item = _measure(build())
    assert abs(item["長度mm"] - length) <= 1.0, item
    assert abs(item["寬度mm"] - width) <= 1.0, item


def test_jpeg_compression(client):
    item = _measure(_scene(), quality=30)
    assert abs(item["長度mm"] - 50) <= 1.0 and abs(item["寬度mm"] - 20) <= 1.0


def test_workpiece_cut_off_by_the_frame_is_refused_not_reported_short(client):
    # 工件只拍到一部分：量到的尺寸會偏小，必須拒絕並說明，不能回報一個看起來合理的數字
    scene = _scene(150, 40, 8)
    cropped = scene[:, :350]
    with pytest.raises(ModuleError) as e:
        _measure(cropped)
    assert e.value.status_code == 422 and "邊緣" in e.value.message


def test_large_workpiece_is_not_silently_truncated(client):
    # 舊做法的校正畫布只涵蓋標記四周 ±3 個標記邊長（約 90 mm），150 mm 的工件被截成 59 mm
    assert _measure(_scene(150, 40, 8))["長度mm"] > 140

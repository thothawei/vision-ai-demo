"""Phase 23：指針錶讀值——真實照片（tests/real_samples/gauge，Wikimedia Commons，授權見 SOURCES.md）。

涵蓋合成圖沒有的情況：彩色指針在同色系錶面上（紅針金底）、指針通過軸心且兩端都離圓心很遠（帶配重）、空心軸心帽、
光照漸變、輕微傾斜。標註是人工目視，容許誤差約為滿刻度的 4–5%；其中 hygrometer／boiler／india 三張是演算法
修改之後才加入的留出照片（不是拿來調參數的）。
"""

import json
from pathlib import Path

import cv2
import pytest
from core import gauge

REAL = Path(__file__).resolve().parents[1] / "tests" / "real_samples" / "gauge"
SAMPLES = json.loads((REAL / "labels.json").read_text())["samples"]


@pytest.mark.parametrize("sample", SAMPLES, ids=[s["file"] for s in SAMPLES])
def test_real_gauge_photo_reads_within_tolerance(sample):
    bgr = cv2.imread(str(REAL / sample["file"]))
    center = gauge.find_center(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    assert center is not None
    p = sample["params"]
    angle, _ = gauge.detect_needle_angle(bgr, *center)
    value = gauge.angle_to_value(angle, p["min_angle"], p["max_angle"], p["min_value"], p["max_value"])
    assert abs(value - sample["expected"]["讀值"]) <= sample["tolerance"], f"{sample['file']}: 讀到 {value:.2f}"


def test_counterweight_end_is_not_mistaken_for_the_tip():
    # manometer_104026：細長、末端碰到刻度弧的一端是指針（指在 0），帶小圓環的短端是配重
    bgr = cv2.imread(str(REAL / "manometer_104026.jpg"))
    angle, length = gauge.detect_needle_angle(bgr, *gauge.find_center(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)))
    assert 120 < angle < 145 and length > 200


def test_gauge_api_on_a_real_photo(client):
    s = next(x for x in SAMPLES if x["file"] == "round_thermometer.jpg")
    res = client.post(
        "/api/nameplate/gauge",
        params=s["params"],
        files={"file": ("t.jpg", (REAL / s["file"]).read_bytes(), "image/jpeg")},
    )
    assert res.status_code == 200, res.text
    assert abs(res.json()["items"][0]["讀值"] - s["expected"]["讀值"]) <= s["tolerance"]

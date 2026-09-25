"""M11 烤漆/陽極色差 ΔE（CIELAB + CIEDE2000）。"""

import io
import json

import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

from samples import make_samples

REF_RECT = [40 / 600, 40 / 300, 280 / 600, 260 / 300]
MEASURE_RECT = [320 / 600, 40 / 300, 560 / 600, 260 / 300]


def _png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _post(client, image, **params):
    return client.post("/api/color/check", params=params, files={"file": ("c.png", _png_bytes(image), "image/png")})


def test_same_color_is_ok_and_delta_e_near_zero(client):
    img = make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))
    res = _post(client, img, ref_rect=json.dumps(REF_RECT), measure_rect=json.dumps(MEASURE_RECT))
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "OK"
    assert body["items"][0]["ΔE00"] < 0.5


def test_clearly_different_color_is_ng(client):
    img = make_samples.make_color_chip_scene((200, 30, 30), (30, 30, 200))  # 紅 vs 藍
    res = _post(client, img, ref_rect=json.dumps(REF_RECT), measure_rect=json.dumps(MEASURE_RECT))
    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["ΔE00"] > 20


def test_threshold_is_configurable(client):
    """同一張圖，門檻設寬鬆一點就從 NG 變 OK，證明門檻參數真的有生效，不是寫死的。"""
    img = make_samples.make_color_chip_scene((180, 60, 60), (190, 65, 65))  # 小色差
    tight = _post(client, img, ref_rect=json.dumps(REF_RECT), measure_rect=json.dumps(MEASURE_RECT), threshold=0.1)
    loose = _post(client, img, ref_rect=json.dumps(REF_RECT), measure_rect=json.dumps(MEASURE_RECT), threshold=50)
    assert tight.json()["verdict"] == "NG"
    assert loose.json()["verdict"] == "OK"


def test_manual_lab_reference_instead_of_rect(client):
    img = make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))
    res = _post(client, img, ref_lab=json.dumps([50.0, 20.0, 20.0]), measure_rect=json.dumps(MEASURE_RECT))
    body = res.json()
    assert body["items"][0]["標準來源"] == "手動輸入 Lab"
    assert body["items"][0]["標準Lab"] == [50.0, 20.0, 20.0]


def test_missing_both_reference_sources_rejected(client):
    img = make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))
    res = _post(client, img, measure_rect=json.dumps(MEASURE_RECT))
    assert res.status_code == 400


def test_missing_measure_rect_rejected(client):
    img = make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))
    res = _post(client, img, ref_rect=json.dumps(REF_RECT))
    assert res.status_code == 400


def test_invalid_json_rejected(client):
    img = make_samples.make_color_chip_scene((180, 60, 60), (180, 60, 60))
    res = _post(client, img, ref_rect="not json", measure_rect=json.dumps(MEASURE_RECT))
    assert res.status_code == 400


def test_pipeline_matches_skimage_deltaE_ciede2000_directly(client):
    """驗收條件：ΔE 計算要跟 scikit-image 的結果一致——不是自己跟自己比對，而是拿同一個
    量測色塊，一邊走 API（裁切→算平均 Lab→呼叫 skimage），一邊自己直接呼叫
    skimage.color.rgb2lab + deltaE_ciede2000 算「正確答案」，兩者要吻合。"""
    measured_rgb = (90, 140, 200)
    img = make_samples.make_color_chip_scene((0, 0, 0), measured_rgb)  # 標準色區內容不重要，這裡用手動 Lab
    ref_lab = [50.0, 10.0, -20.0]

    res = _post(client, img, ref_lab=json.dumps(ref_lab), measure_rect=json.dumps(MEASURE_RECT))
    body = res.json()

    # 獨立計算「正確答案」：量測區是純色，rgb2lab 對任一像素的結果就是整塊的平均
    expected_measured_lab = rgb2lab(np.array([[list(measured_rgb)]], dtype=np.float64) / 255.0)[0, 0]
    expected_delta_e = float(deltaE_ciede2000(np.array(ref_lab), expected_measured_lab))

    assert body["items"][0]["量測Lab"] == [round(float(v), 2) for v in expected_measured_lab]
    assert abs(body["items"][0]["ΔE00"] - expected_delta_e) < 0.01


def test_known_ciede2000_test_vectors_match_skimage():
    """CIEDE2000 論文（Sharma et al. 2005）公開的標準測試向量，直接驗證 skimage 本身算得對，
    不是只信任套件文件——這樣 M11 用到的 deltaE_ciede2000 才是真的驗證過的，不是憑空信任。"""
    test_vectors = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
        ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ]
    for lab1, lab2, expected in test_vectors:
        result = float(deltaE_ciede2000(np.array(lab1), np.array(lab2)))
        assert abs(result - expected) < 0.001, f"{lab1} vs {lab2}: 預期 {expected}，實際 {result}"

"""Phase 23：零件計數——真實照片（tests/real_samples/count，Wikimedia Commons，授權見 SOURCES.md）。

只斷言目前確實數對的照片，以及「沒有背景就拒絕」的設計；數錯的照片（零件互相疊壓的螺栓堆、五金件、嵌套的 O 形環
等）記錄在 docs/evaluation.md，不放進測試假裝通過。標註是人工目視。
"""

import json
from pathlib import Path

import pytest

REAL = Path(__file__).resolve().parents[1] / "tests" / "real_samples" / "count"
SAMPLES = json.loads((REAL / "labels.json").read_text())["samples"]
COUNTED_CORRECTLY = [
    "two_screws.jpg",
    "two_screws_closeup.jpg",
    "four_screws_4.jpg",
    "wood_screw_1.jpg",
    "resistors_6.jpg",
    "gaskets_5.jpg",
    "ceramic_balls_5.jpg",
]


@pytest.mark.parametrize("name", COUNTED_CORRECTLY)
def test_real_photo_is_counted_correctly(client, name):
    expected = next(s for s in SAMPLES if s["file"] == name)["expected"]["計數結果"]
    res = client.post("/api/measure/count", files={"file": (name, (REAL / name).read_bytes(), "image/jpeg")})
    assert res.status_code == 200, res.text
    assert res.json()["items"][0]["計數結果"] == expected


def test_photo_without_a_visible_background_is_refused_not_guessed(client):
    # 瓶蓋占滿畫面：邊緣沒有可參考的背景，回 422 並說明怎麼拍，而不是回報一個沒有依據的數字
    res = client.post(
        "/api/measure/count", files={"file": ("cap.jpg", (REAL / "bottle_cap_1.jpg").read_bytes(), "image/jpeg")}
    )
    assert res.status_code == 422
    assert "背景" in res.json()["detail"]


def test_one_part_with_specular_highlights_is_not_split_into_pieces(client):
    # 反光的金屬螺絲：舊做法（灰階 Otsu＋固定視窗的局部極大值）會把單顆木螺絲切成 16 個
    res = client.post(
        "/api/measure/count", files={"file": ("w.jpg", (REAL / "wood_screw_1.jpg").read_bytes(), "image/jpeg")}
    )
    assert res.json()["items"][0]["計數結果"] == 1

"""M5 危險區域入侵：多邊形判斷邏輯（用假偵測結果隔離 YOLO，真實偵測準確度見 test_live_safety.py）。"""

import io

from PIL import Image


def _dummy_image_bytes(w=800, h=600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_no_zone_is_info(client, fake_person_detector):
    res = client.post("/api/safety/intrusion", files={"file": ("i.png", _dummy_image_bytes(), "image/png")})

    body = res.json()
    assert body["verdict"] == "INFO"
    assert body["items"][0]["偵測到人數"] == 1
    assert body["items"][0]["明細"][0]["是否入侵"] is False


def test_zone_covering_person_is_ng(client, fake_person_detector):
    # 假的人在 [100,100,200,500]，腳底參考點 [150,500]；區域涵蓋左半邊
    zone = "[[0,0],[0.5,0],[0.5,1],[0,1]]"
    res = client.post("/api/safety/intrusion", data={"zone": zone},
                      files={"file": ("i.png", _dummy_image_bytes(), "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert body["items"][0]["明細"][0]["是否入侵"] is True


def test_zone_not_covering_person_is_ok(client, fake_person_detector):
    zone = "[[0.8,0],[1,0],[1,1],[0.8,1]]"
    res = client.post("/api/safety/intrusion", data={"zone": zone},
                      files={"file": ("i.png", _dummy_image_bytes(), "image/png")})

    assert res.json()["verdict"] == "OK"


def test_invalid_zone_json_rejected(client, fake_person_detector):
    res = client.post("/api/safety/intrusion", data={"zone": "not json"},
                      files={"file": ("i.png", _dummy_image_bytes(), "image/png")})
    assert res.status_code == 400


def test_zone_needs_at_least_3_points(client, fake_person_detector):
    res = client.post("/api/safety/intrusion", data={"zone": "[[0,0],[1,1]]"},
                      files={"file": ("i.png", _dummy_image_bytes(), "image/png")})
    assert res.status_code == 400

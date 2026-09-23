"""真的跑 YOLO11n 人員偵測（不 mock），驗證實際照片的偵測準確度：pytest -m live

測試圖是真實 CC BY 2.0 授權照片（Wikimedia Commons，非本專案拍攝），不進版控，
下載方式見 tests/live_samples/README.md。沒有這張圖就跳過，不假裝測過。
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.live

FACTORY_WORKER_JPG = Path(__file__).resolve().parent / "live_samples" / "factory_worker.jpg"


@pytest.mark.skipif(not FACTORY_WORKER_JPG.exists(), reason="測試圖未下載，見 tests/live_samples/README.md")
def test_live_detects_real_person(client):
    img_bytes = FACTORY_WORKER_JPG.read_bytes()

    no_zone = client.post("/api/safety/intrusion", files={"file": ("f.jpg", img_bytes, "image/jpeg")})
    assert no_zone.status_code == 200, no_zone.text
    body = no_zone.json()
    print("\n[M5 live] 偵測到", body["items"][0]["偵測到人數"], "人", body["items"][0]["明細"])
    assert body["items"][0]["偵測到人數"] >= 1
    assert body["items"][0]["明細"][0]["信心度"] > 0.5

    # 人物在照片左半邊，涵蓋左半邊的區域應該判定入侵
    covering = client.post("/api/safety/intrusion", data={"zone": "[[0,0],[0.6,0],[0.6,1],[0,1]]"},
                           files={"file": ("f.jpg", img_bytes, "image/jpeg")})
    assert covering.json()["verdict"] == "NG"

    not_covering = client.post("/api/safety/intrusion", data={"zone": "[[0.8,0],[1,0],[1,1],[0.8,1]]"},
                               files={"file": ("f.jpg", img_bytes, "image/jpeg")})
    assert not_covering.json()["verdict"] == "OK"

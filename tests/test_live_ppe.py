"""真的載入訓練好的 PPE YOLO 權重，跑 Hard Hat Workers 驗證集抽樣：pytest -m live"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.live

VAL_DIR = Path(__file__).resolve().parent.parent / "data" / "hardhat_yolo" / "val"


@pytest.mark.skipif(not VAL_DIR.exists(), reason="Hardhat 驗證集未準備，見 scripts/prepare_hardhat.py")
def test_live_ppe_detects_helmets(client):
    images = sorted((VAL_DIR / "images").glob("*.jpg"))[:10]
    assert images, "驗證集是空的"

    total_detections = 0
    for img_path in images:
        with open(img_path, "rb") as f:
            res = client.post("/api/safety/ppe", files={"file": (img_path.name, f.read(), "image/jpeg")})
        assert res.status_code == 200, res.text
        body = res.json()
        n = body["items"][0]["偵測到人頭數"]
        total_detections += n
        print(f"\n[M5 PPE live] {img_path.name}: {body['verdict']}，偵測到 {n} 顆頭")

    assert total_detections > 0, "10 張圖一顆頭都沒偵測到，模型可能有問題"

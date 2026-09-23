"""真的載入訓練好的 PCB YOLO 權重，跑 DeepPCB 測試集抽樣，驗證真的能抓到瑕疵：pytest -m live"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.live

TEST_DIR = Path(__file__).resolve().parent.parent / "data" / "deeppcb_yolo" / "test"


@pytest.mark.skipif(not TEST_DIR.exists(), reason="DeepPCB 測試集未準備，見 scripts/prepare_deeppcb.py")
def test_live_pcb_defects_detected(client):
    images = sorted((TEST_DIR / "images").glob("*.jpg"))[:10]
    assert images, "測試集是空的"

    ng_count = 0
    for img_path in images:
        with open(img_path, "rb") as f:
            res = client.post("/api/defect/pcb", files={"file": (img_path.name, f.read(), "image/jpeg")})
        assert res.status_code == 200, res.text
        body = res.json()
        if body["verdict"] == "NG":
            ng_count += 1
        print(f"\n[M6 live] {img_path.name}: {body['verdict']}，"
              f"偵測到 {body['items'][0]['偵測到瑕疵數']} 個瑕疵")

    # DeepPCB 測試圖幾乎都含瑕疵（資料集設計就是每張圖 3-12 個瑕疵），抽 10 張應該大多數判 NG
    assert ng_count >= 8

"""M8 真的打本機 Ollama（包裝檢核）與真的載入訓練好的肺炎分類權重：pytest -m live"""

from datetime import date

import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")


def test_live_packaging_match(client, ollama_env, packaging_match_png):
    res = client.post("/api/medical/packaging-check", files={"file": ("p.png", packaging_match_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print("\n[M8 live 包裝檢核]", body["engine"], body["elapsed_ms"], "ms", item)
    assert body["verdict"] == "OK"
    assert item["批號一致"] is True
    assert item["效期一致"] is True


def test_live_pneumonia_demo_on_real_test_set(client):
    """用真實 PneumoniaMNIST 測試集抽樣，驗證跟 CLAUDE.md 記錄的實測準確率同一個量級。"""
    from pathlib import Path

    data_root = Path(__file__).resolve().parent.parent / "data" / "medmnist"
    if not data_root.exists():
        pytest.skip("PneumoniaMNIST 未下載，見 scripts/train_medmnist.py")

    import io

    from medmnist import PneumoniaMNIST
    from PIL import Image

    ds = PneumoniaMNIST(split="test", download=False, root=data_root, size=28)
    n_samples = 30
    correct = 0
    for i in range(n_samples):
        img = Image.fromarray(ds.imgs[i]).convert("L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        res = client.post("/api/medical/pneumonia-demo", files={"file": (f"{i}.png", buf.getvalue(), "image/png")})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["items"][0]["警語"] == "僅供技術展示，非醫療診斷用途"
        predicted_pneumonia = "pneumonia" in body["items"][0]["分類"]
        true_label = int(ds.labels[i][0])
        correct += int(predicted_pneumonia == bool(true_label))

    accuracy = correct / n_samples
    print(f"\n[M8 live 肺炎分類] 抽樣 {n_samples} 張正確率 {accuracy:.2%}")
    # 訓練紀錄整體測試集 ACC=0.8862，抽樣小樣本容許誤差，門檻設寬鬆一點避免抽樣運氣造成假失敗
    assert accuracy >= 0.6

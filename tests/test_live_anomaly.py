"""真的載入 Phase 3 訓練好的 PatchCore 權重，跑 MVTec AD 官方測試集抽樣，
驗證良品/瑕疵品的判定方向正確：pytest -m live

資料集需先下載到 data/mvtec_ad/<category>/（不進版控，下載連結見 docs/licenses.md）。
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.live

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "mvtec_ad"
CATEGORIES = ["metal_nut", "screw", "tile"]


def _sample_images(category: str, subfolder: str, n: int) -> list[Path]:
    folder = DATA_ROOT / category / "test" / subfolder
    return sorted(folder.glob("*.png"))[:n] if folder.exists() else []


@pytest.mark.parametrize("category", CATEGORIES)
def test_live_good_and_defect_samples(client, category):
    good = _sample_images(category, "good", 3)
    defect_dirs = [d for d in (DATA_ROOT / category / "test").iterdir() if d.is_dir() and d.name != "good"] \
        if (DATA_ROOT / category / "test").exists() else []
    defects = [p for d in defect_dirs for p in sorted(d.glob("*.png"))[:2]]

    if not good and not defects:
        pytest.skip(f"MVTec AD {category} 測試集未下載，見 docs/licenses.md")

    correct, total = 0, 0
    for path, expected_ng in [(p, False) for p in good] + [(p, True) for p in defects]:
        with open(path, "rb") as f:
            res = client.post("/api/anomaly/inspect", params={"category": category},
                              files={"file": (path.name, f.read(), "image/png")})
        assert res.status_code == 200, res.text
        body = res.json()
        is_ng = body["verdict"] == "NG"
        total += 1
        correct += int(is_ng == expected_ng)
        print(f"\n[M3 live {category}] {path.parent.name}/{path.name}: "
              f"分數={body['items'][0]['異常分數']} 判定={body['items'][0]['判定']} "
              f"(預期{'異常' if expected_ng else '正常'})")

    print(f"[M3 live {category}] 抽樣正確率 {correct}/{total}")
    # 抽樣快篩，不是正式 AUROC（正式數字在 models/anomaly/<category>/metrics.json，
    # 由 scripts/train_anomaly.py 用完整官方測試集算出）
    assert correct / total >= 0.7

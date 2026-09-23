"""擬合 M3 異常檢測模型（Anomalib PatchCore），並用官方測試集實測 image-level AUROC。

PatchCore 不是傳統意義的「訓練」：只用良品照片擬合一個 memory bank（記住良品長什麼樣），
不需要 NG 樣本、不需要反向傳播，這正是工廠場景缺 NG 樣本時的賣點。

用法：
    python scripts/train_anomaly.py --category metal_nut
    python scripts/train_anomaly.py --category screw
    python scripts/train_anomaly.py --category tile
    python scripts/train_anomaly.py --category all   # 三類都跑

資料集需先手動下載到 data/mvtec_ad/<category>/（MVTec AD 官方目錄結構），
下載連結見 docs/licenses.md；CC BY-NC-SA 4.0，僅供學習/作品集展示。
"""

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from anomalib.data import MVTecAD
from anomalib.deploy import ExportType
from anomalib.engine import Engine
from anomalib.models import Patchcore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "mvtec_ad"
MODELS_DIR = PROJECT_ROOT / "models" / "anomaly"
CATEGORIES = ["metal_nut", "screw", "tile"]


def train_one(category: str) -> dict:
    category_dir = DATA_ROOT / category
    if not category_dir.exists():
        raise FileNotFoundError(
            f"找不到資料集 {category_dir}，請先下載（連結見 docs/licenses.md）並解壓到這個路徑"
        )

    # PatchCore 的 coreset 篩選（greedy k-center）在 Python 迴圈裡逐一對張量呼叫 .item()
    # 把純量搬回 CPU，每次呼叫都會讓 MPS 做一次 GPU 同步；實測用 `sample` 系統工具
    # 抓到呼叫堆疊卡在 MPSStream::synchronize，幾分鐘幾乎沒有進度。CPU 沒有這個同步開銷，
    # 反而比 MPS 快，所以固定用 CPU（不是「不支援 MPS 自動退回」，是「MPS 支援但這個
    # 演算法在 MPS 上特別慢」）。
    device = "cpu"
    print(f"[{category}] 使用裝置：{device}（PatchCore coreset 篩選在 MPS 上會因逐元素同步變得極慢，見程式註解）")

    datamodule = MVTecAD(root=DATA_ROOT, category=category, train_batch_size=32, eval_batch_size=32)
    model = Patchcore()
    engine = Engine(accelerator=device, devices=1, default_root_dir=str(MODELS_DIR / "_engine_logs"))

    started = time.perf_counter()
    engine.fit(model=model, datamodule=datamodule)
    fit_seconds = time.perf_counter() - started

    test_results = engine.test(model=model, datamodule=datamodule)
    # anomalib 回傳的 metric key 依版本可能是 image_AUROC 或 AUROC，兩種都嘗試
    metrics = test_results[0] if test_results else {}
    auroc = metrics.get("image_AUROC", metrics.get("AUROC"))
    if auroc is None:
        raise RuntimeError(f"engine.test 沒有回傳 AUROC，實際回傳鍵值：{list(metrics.keys())}")

    weights_dir = MODELS_DIR / category
    weights_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = engine.trainer.checkpoint_callback.best_model_path or engine.trainer.checkpoint_callback.last_model_path

    # 匯出成 TorchInferencer 可直接載入的 .pt（把 pre-processor、門檻值一起包進去），
    # 服務層不需要重建完整的 Lightning 模組就能推論。
    exported_dir = engine.export(model=model, export_type=ExportType.TORCH, export_root=weights_dir, ckpt_path=ckpt_path)

    n_test = sum(1 for _ in (category_dir / "test").rglob("*.png"))
    result = {
        "category": category,
        "device": device,
        "image_auroc": round(float(auroc), 4),
        "fit_seconds": round(fit_seconds, 1),
        "test_set_size": n_test,
        "weights_path": str(Path(exported_dir).relative_to(PROJECT_ROOT)),
    }
    (weights_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[{category}] image-level AUROC = {result['image_auroc']}（測試集 {n_test} 張，擬合耗時 {result['fit_seconds']}秒）")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, choices=[*CATEGORIES, "all"])
    args = parser.parse_args()

    targets = CATEGORIES if args.category == "all" else [args.category]
    all_results = [train_one(c) for c in targets]

    if len(all_results) > 1:
        print("\n=== 總結 ===")
        for r in all_results:
            print(f"  {r['category']}: AUROC={r['image_auroc']}, 測試集={r['test_set_size']}張")

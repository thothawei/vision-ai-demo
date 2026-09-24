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
import math
import os
import shutil
import tempfile
import time
from pathlib import Path

import torch
from anomalib.data import Folder, MVTecAD
from anomalib.deploy import ExportType
from anomalib.engine import Engine
from anomalib.models import Patchcore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "mvtec_ad"
MODELS_DIR = PROJECT_ROOT / "models" / "anomaly"
CATEGORIES = ["metal_nut", "screw", "tile"]

MIN_TRAIN_GOOD = 10  # 擬合用的良品照片數量下限（扣掉留給評分用的那一小部分之後）


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


def _suggest_threshold(scores: list[dict]) -> tuple[float, float | None]:
    """scores：[{"label": "good"|"defect", "score": float}, ...]（held-out 評分集）。
    只有良品：用良品分數的 99th percentile 當門檻建議，回傳 (threshold, None)。
    有 NG 樣本：用 ROC 找 Youden's J（TPR-FPR 最大處）最佳門檻，回傳 (threshold, AUROC)。"""
    good_scores = sorted(s["score"] for s in scores if s["label"] == "good")
    defect_scores = [s["score"] for s in scores if s["label"] == "defect"]
    if not good_scores:
        raise ValueError("評分集裡沒有良品分數，無法建議門檻")

    if not defect_scores:
        idx = min(len(good_scores) - 1, math.ceil(0.99 * len(good_scores)) - 1)
        return good_scores[idx], None

    from sklearn.metrics import roc_auc_score, roc_curve

    y_true = [0] * len(good_scores) + [1] * len(defect_scores)
    y_score = good_scores + defect_scores
    auroc = float(roc_auc_score(y_true, y_score))
    fpr, tpr, thresholds = roc_curve(y_true, y_score)
    best_idx = (tpr - fpr).argmax()
    return float(thresholds[best_idx]), auroc


def train_custom(
    category: str,
    good_paths: list[Path],
    defect_paths: list[Path] | None = None,
    export_root: Path | None = None,
    held_out_ratio: float = 0.2,
) -> dict:
    """給 Phase 12 自訂類別用：不是 MVTec 官方目錄結構，沒有像素級 mask，
    good_paths/defect_paths 是使用者上傳解壓後的扁平圖片路徑清單。

    做法跟 train_one() 不同：良品照片自己切一部分（held_out_ratio）留著評分用，
    不進擬合的 memory bank；剩下的良品才拿去給 anomalib 的 Folder datamodule 擬合。
    擬合完用匯出的推論器對「留出來的良品 + 全部 NG 照片」個別評分，算出 scores.json，
    再用 _suggest_threshold() 建議門檻——這樣不用依賴 anomalib 的 Folder test-split
    語意（那是為了有 mask 的情境設計的），評分邏輯完全掌握在自己手上、跟正式推論路徑
    （TorchInferencer.predict）一致。
    """
    import random

    from PIL import Image

    export_root = export_root or (MODELS_DIR / category)
    good_paths = list(good_paths)
    if len(good_paths) < MIN_TRAIN_GOOD + 1:
        raise ValueError(f"良品照片太少（{len(good_paths)} 張），建議至少 {MIN_TRAIN_GOOD + 5} 張才能擬合")

    rng = random.Random(42)
    shuffled = good_paths[:]
    rng.shuffle(shuffled)
    n_held = max(1, round(len(shuffled) * held_out_ratio))
    held_out_good = shuffled[:n_held]
    train_good = shuffled[n_held:]
    if len(train_good) < MIN_TRAIN_GOOD:
        raise ValueError(
            f"扣掉留給評分用的 {n_held} 張後，擬合用的良品只剩 {len(train_good)} 張（低於下限 {MIN_TRAIN_GOOD}），"
            "請上傳更多良品照片"
        )

    device = "cpu"
    print(f"[{category}] 使用裝置：{device}（PatchCore coreset 篩選在 MPS 上會因逐元素同步變得極慢，同 train_one）")

    with tempfile.TemporaryDirectory(prefix=f"anomaly_train_{category}_") as tmp:
        tmp_root = Path(tmp)
        normal_dir = tmp_root / "good"
        normal_dir.mkdir()
        for i, p in enumerate(train_good):
            shutil.copy(p, normal_dir / f"{i:04d}{p.suffix.lower()}")

        # 關掉 anomalib 內建的 min-max 正規化/自動門檻：那套校準是用「Folder 自動從 normal_dir
        # 切出來的一小塊內部驗證集」算 min/max，這塊驗證集也是良品、分數範圍天生就很窄，實測會讓
        # 良品/NG 的原始分數大量被裁到剛好卡在 0 或 1（見 CLAUDE.md 踩坑紀錄）。門檻由我們自己
        # 用 held-out 良品／NG 的原始分數算（_suggest_threshold），不需要 anomalib 的正規化。
        from anomalib.post_processing import PostProcessor

        post_processor = PostProcessor(enable_normalization=False, enable_thresholding=False)
        datamodule = Folder(name=category, root=tmp_root, normal_dir="good", train_batch_size=32, eval_batch_size=32)
        model = Patchcore(post_processor=post_processor)
        engine = Engine(accelerator=device, devices=1, default_root_dir=str(export_root / "_engine_logs"))

        started = time.perf_counter()
        engine.fit(model=model, datamodule=datamodule)
        fit_seconds = time.perf_counter() - started

        export_root.mkdir(parents=True, exist_ok=True)
        ckpt_path = engine.trainer.checkpoint_callback.best_model_path or engine.trainer.checkpoint_callback.last_model_path
        exported_dir = Path(engine.export(model=model, export_type=ExportType.TORCH, export_root=export_root, ckpt_path=ckpt_path))

    from anomalib.deploy import TorchInferencer

    os.environ["TRUST_REMOTE_CODE"] = "1"  # 只信任本機剛匯出的權重，見 CLAUDE.md 說明
    weights_path = exported_dir  # engine.export() 回傳的就是完整的 model.pt 路徑（不是目錄）
    inferencer = TorchInferencer(path=weights_path, device="cpu")

    scores = []
    for p in held_out_good:
        pred = inferencer.predict(Image.open(p).convert("RGB"))
        scores.append({"label": "good", "score": round(float(pred.pred_score), 6), "file": p.name})
    for p in defect_paths or []:
        pred = inferencer.predict(Image.open(p).convert("RGB"))
        scores.append({"label": "defect", "score": round(float(pred.pred_score), 6), "file": p.name})

    threshold, auroc = _suggest_threshold(scores)

    result = {
        "category": category,
        "device": device,
        "source": "custom",
        "image_auroc": round(auroc, 4) if auroc is not None else None,
        "fit_seconds": round(fit_seconds, 1),
        "train_good_count": len(train_good),
        "held_out_good_count": len(held_out_good),
        "defect_count": len(defect_paths or []),
        "weights_path": str(weights_path.relative_to(PROJECT_ROOT)),
        "threshold_source": "roc_youden_j" if auroc is not None else "good_99th_percentile",
    }
    (export_root / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (export_root / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2))
    (export_root / "threshold.json").write_text(json.dumps({"threshold": threshold}, ensure_ascii=False, indent=2))

    print(
        f"[{category}] 擬合完成：{result['fit_seconds']}秒，"
        f"AUROC={result['image_auroc']}（{'ROC/Youden J' if auroc is not None else '無 NG 樣本，僅良品分佈估計'}），"
        f"門檻={threshold:.4f}"
    )
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

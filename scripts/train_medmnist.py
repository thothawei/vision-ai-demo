"""M8-2 教學展示用：PneumoniaMNIST（CC BY 4.0）小型 CNN 分類器，CPU 可訓練。

**僅供技術展示，非醫療診斷用途**——這只是示範「AI 影像分類」這個技術能力用胸腔 X 光當
公開資料集範例，不是真的拿來做任何醫療判斷，前端與 API 回應都會重複這個警語。

用法：
    python scripts/train_medmnist.py
    → 資料集自動下載到 data/medmnist/，權重與實測 ACC/AUC 存到 models/medical/pneumonia_cnn/
"""

import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from medmnist import Evaluator, PneumoniaMNIST
from torch.utils.data import DataLoader
from torchvision.transforms import ToTensor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "medmnist"
MODELS_DIR = PROJECT_ROOT / "models" / "medical" / "pneumonia_cnn"
EPOCHS = 15
BATCH_SIZE = 64
LR = 1e-3


class SmallCNN(nn.Module):
    """兩層卷積的小模型，28x28 灰階圖，CPU 訓練幾分鐘等級。"""

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2)
        self.fc1 = nn.Linear(32 * 7 * 7, 64)
        self.fc2 = nn.Linear(64, 1)  # binary-class，輸出單一 logit

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.flatten(1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


def main():
    device = "cpu"  # 資料量小、模型小，CPU 就夠快，不用糾結 MPS
    transform = ToTensor()
    train_ds = PneumoniaMNIST(split="train", download=True, root=DATA_ROOT, size=28, transform=transform)
    val_ds = PneumoniaMNIST(split="val", download=True, root=DATA_ROOT, size=28, transform=transform)
    test_ds = PneumoniaMNIST(split="test", download=True, root=DATA_ROOT, size=28, transform=transform)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False)

    # 訓練集類別不平衡（normal 1214 張 vs pneumonia 3494 張，約 1:2.9）。
    # 實測：不加權重訓練出來的模型，對 normal 的召回率只有 55.6%（234 張正常樣本
    # 誤判掉 104 張），因為模型學到「猜 pneumonia 比較容易對」。用 pos_weight 把
    # 多數類別（pneumonia=1）的損失權重調低，逼模型認真學 normal 的特徵。
    n_normal = int((train_ds.labels == 0).sum())
    n_pneumonia = int((train_ds.labels == 1).sum())
    pos_weight = torch.tensor([n_normal / n_pneumonia])
    print(f"訓練集類別分布：normal={n_normal} pneumonia={n_pneumonia}，pos_weight={pos_weight.item():.4f}")

    model = SmallCNN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    started = time.perf_counter()
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device).float(), labels.to(device).float()
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)

        val_acc = _accuracy(model, val_loader, device)
        print(f"epoch {epoch}/{EPOCHS}  train_loss={total_loss / len(train_ds):.4f}  val_acc={val_acc:.4f}")

    fit_seconds = time.perf_counter() - started

    test_scores = _predict_scores(model, test_loader, device)
    test_labels = test_ds.labels.astype(np.float32).flatten()
    test_preds = (test_scores.flatten() > 0.5).astype(np.float32)

    evaluator = Evaluator("pneumoniamnist", "test", root=DATA_ROOT)
    auc, acc = evaluator.evaluate(test_scores)

    normal_mask = test_labels == 0
    pneumonia_mask = test_labels == 1
    normal_recall = float((test_preds[normal_mask] == test_labels[normal_mask]).mean())
    pneumonia_recall = float((test_preds[pneumonia_mask] == test_labels[pneumonia_mask]).mean())

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODELS_DIR / "model.pt")

    result = {
        "dataset": "PneumoniaMNIST（CC BY 4.0，僅供技術展示，非醫療診斷用途）",
        "test_acc": round(float(acc), 4),
        "test_auc": round(float(auc), 4),
        "test_set_size": len(test_ds),
        "normal_recall": round(normal_recall, 4),
        "pneumonia_recall": round(pneumonia_recall, 4),
        "epochs": EPOCHS,
        "fit_seconds": round(fit_seconds, 1),
        "pos_weight_used": round(float(pos_weight.item()), 4),
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n測試集 ACC={result['test_acc']} AUC={result['test_auc']}（{len(test_ds)} 張，訓練耗時 {result['fit_seconds']} 秒）")
    print(f"normal 召回率={result['normal_recall']}　pneumonia 召回率={result['pneumonia_recall']}")


def _accuracy(model, loader, device) -> float:
    model.eval()
    correct, total = 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device).float(), labels.to(device).float()
            preds = (torch.sigmoid(model(images)) > 0.5).float()
            correct += (preds == labels).sum().item()
            total += labels.numel()
    return correct / total


def _predict_scores(model, loader, device) -> np.ndarray:
    model.eval()
    scores = []
    with torch.no_grad():
        for images, _ in loader:
            images = images.to(device).float()
            probs = torch.sigmoid(model(images))
            scores.append(probs.cpu().numpy())
    return np.concatenate(scores, axis=0)


if __name__ == "__main__":
    main()

"""M8 醫療相關辨識。

M8-1 包裝追溯碼檢核：同一張包裝照片，用 M1 的邏輯解出 GS1 UDI 條碼（批號/效期），
再用 OCR+LLM 讀印刷文字上的批號/效期，兩邊比對是否一致——這是 GMP 追溯的真實需求，
條碼跟印刷文字如果對不上，代表包裝可能印錯或條碼貼錯，要擋下來。

M8-2 醫學影像分類：PneumoniaMNIST（CC BY 4.0）小型 CNN 教學展示。
**僅供技術展示，非醫療診斷用途**，不是真的用來做任何醫療判斷。
"""

import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import zxingcpp
from PIL import Image

from core import llm
from core.image_io import bgr_to_data_url, load_image, to_bgr
from core.inspection_log import record_result
from core.schemas import InspectionResult, ModuleError
from modules.codes.service import describe_barcode

PACKAGING_MODULE = "medical_packaging"
MEDMNIST_MODULE = "medical_pneumonia_demo"

MEDMNIST_DISCLAIMER = "僅供技術展示，非醫療診斷用途"

PRINTED_TEXT_PROMPT_TEMPLATE = """以下是從一張藥品/醫材包裝 OCR 掃描出來的印刷文字，可能包含雜訊或斷行錯誤。
請找出包裝上印刷的批號（LOT/Batch No）跟效期（Expiry/EXP），只回傳 JSON（不要多餘文字）：

{{
  "批號": "找到的批號原文，找不到填空字串 ''",
  "效期": "找到的效期，轉成 YYYY-MM-DD 格式；只有年月就用該月最後一天；找不到填空字串 ''"
}}

只能照抄原文轉換格式，不能自己編造。

原始 OCR 文字如下：
---
{ocr_text}
---
"""


def check_packaging(image_bytes: bytes) -> InspectionResult:
    from core import ocr as rapid_ocr

    started = time.perf_counter()
    image = load_image(image_bytes)
    bgr = to_bgr(image)

    barcodes = zxingcpp.read_barcodes(bgr)
    gs1_items = [describe_barcode(b) for b in barcodes if b.content_type == zxingcpp.ContentType.GS1]
    if not gs1_items:
        raise ModuleError("畫面中找不到 GS1 條碼（UDI），無法比對，請確認條碼清楚可讀", 422)
    barcode_item = gs1_items[0]
    barcode_fields = barcode_item.get("GS1欄位", {})
    barcode_batch = barcode_fields.get("批號")
    barcode_expiry = barcode_item.get("效期")  # ISO 字串或 None

    ocr_text = rapid_ocr.extract_text(image)
    printed_batch, printed_expiry_raw, engine = None, None, "zxing-cpp"
    if ocr_text.strip():
        raw, llm_engine = llm.generate_json(PRINTED_TEXT_PROMPT_TEMPLATE.format(ocr_text=ocr_text))
        printed_batch = (raw.get("批號") or "").strip() or None
        printed_expiry_raw = (raw.get("效期") or "").strip() or None
        engine = f"zxing-cpp+rapidocr+{llm_engine}"

    batch_match = _compare_batch(barcode_batch, printed_batch)
    expiry_match = _compare_expiry(barcode_expiry, printed_expiry_raw)

    mismatches = [name for name, ok in [("批號", batch_match), ("效期", expiry_match)] if ok is False]
    if barcode_item["效期狀態"] == "已過期":
        mismatches.append("條碼效期已過期")

    verdict = "NG" if mismatches else ("OK" if batch_match and expiry_match else "INFO")
    item = {
        "條碼批號": barcode_batch, "印刷批號": printed_batch, "批號一致": batch_match,
        "條碼效期": barcode_expiry, "印刷效期": printed_expiry_raw, "效期一致": expiry_match,
        "條碼效期狀態": barcode_item["效期狀態"],
        "問題": mismatches if mismatches else None,
    }
    return record_result(PACKAGING_MODULE, verdict, [item], engine, started, bgr_to_data_url(bgr))


def _compare_batch(barcode_batch: str | None, printed_batch: str | None) -> bool | None:
    if not barcode_batch or not printed_batch:
        return None  # 兩邊有一邊沒讀到，沒辦法比對，不是「不一致」
    return barcode_batch.strip().upper() == printed_batch.strip().upper()


def _compare_expiry(barcode_expiry_iso: str | None, printed_expiry_raw: str | None) -> bool | None:
    if not barcode_expiry_iso or not printed_expiry_raw:
        return None
    try:
        printed_date = datetime.strptime(printed_expiry_raw, "%Y-%m-%d").date()
        barcode_date = date.fromisoformat(barcode_expiry_iso)
    except ValueError:
        return None
    return printed_date == barcode_date


# ---------- M8-2 醫學影像分類教學展示 ----------


class _SmallCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2)
        self.fc1 = nn.Linear(32 * 7 * 7, 64)
        self.fc2 = nn.Linear(64, 1)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.flatten(1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "models" / "medical" / "pneumonia_cnn" / "model.pt"
_model: _SmallCNN | None = None


def _get_model() -> _SmallCNN:
    global _model
    if _model is None:
        if not WEIGHTS_PATH.exists():
            raise ModuleError(
                f"找不到教學展示模型權重 {WEIGHTS_PATH}，請先執行 `python scripts/train_medmnist.py`", 503,
            )
        model = _SmallCNN()
        model.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cpu"))
        model.eval()
        _model = model
    return _model


def classify_pneumonia_demo(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    gray = image.convert("L").resize((28, 28), Image.BILINEAR)
    tensor = torch.from_numpy(np.array(gray, dtype=np.float32) / 255.0).unsqueeze(0).unsqueeze(0)

    model = _get_model()
    with torch.no_grad():
        prob_pneumonia = float(torch.sigmoid(model(tensor))[0, 0])

    label = "pneumonia（肺炎樣態）" if prob_pneumonia > 0.5 else "normal（正常樣態）"
    item = {
        "分類": label,
        "肺炎機率": round(prob_pneumonia, 4),
        "警語": MEDMNIST_DISCLAIMER,
    }
    # 這個 verdict 不代表醫療判斷，只是技術展示的分類結果，用 INFO 避免被誤讀成 OK/NG 的品檢結論
    return record_result(MEDMNIST_MODULE, "INFO", [item], "pytorch-smallcnn-pneumoniamnist", started)

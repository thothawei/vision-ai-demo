"""內建模型的靜態說明（用途、資料集與授權、已記錄的指標、限制、不適用情境），給模型登錄與說明卡用。

指標只放「有出處」的數字：機器可讀的 metrics.json（異常檢測、肺炎 CNN）由登錄時讀入；
defect／ppe 沒有 metrics.json，數字取自開發紀錄（docs/dev/test-log.md）並標明出處，不憑空產生。
"""

_YOLO_LICENSE = "權重衍生自 Ultralytics YOLO11n（AGPL-3.0）；散佈與網路服務義務見 docs/licenses.md"

CATALOG: dict[str, dict] = {
    "pcb-defect": {
        "title": "PCB 瑕疵偵測",
        "task": "監督式物件偵測（YOLO11n）：斷路、短路、缺口、毛刺、多餘銅箔、針孔六類",
        "dataset": "DeepPCB（1500 張 640x640，依固定種子 42 自行切成 1000／250／250，非官方切分）",
        "dataset_license": f"資料集 MIT；{_YOLO_LICENSE}",
        "documented_metrics": {
            "mAP50": 0.978,
            "mAP50-95": 0.735,
            "precision": 0.964,
            "recall": 0.945,
            "test_set_size": 250,
            "來源": "docs/dev/test-log.md「Phase 5：功能驗證」（官方測試集切分上的驗證輸出）",
        },
        "limitations": "只認上述 6 類瑕疵；以 DeepPCB 風格的 PCB 影像訓練，實際產線影像（光源、解析度、板型不同）的準確度未驗證，導入時需以自有資料重訓。",
        "not_for": "不可直接當作 AOI 的最終判定；非 DeepPCB 風格影像、其他瑕疵類型。",
    },
    "ppe-helmet": {
        "title": "安全帽偵測",
        "task": "監督式物件偵測（YOLO11n）：已戴安全帽（helmet）與未戴安全帽（head）",
        "dataset": "Hard Hat Workers（5297 張訓練、1766 張測試，沿用資料集官方切分）",
        "dataset_license": f"資料集 CC0 1.0；{_YOLO_LICENSE}",
        "documented_metrics": {
            "mAP50": 0.977,
            "mAP50-95": 0.680,
            "precision": 0.948,
            "recall": 0.942,
            "test_set_size": 1766,
            "來源": "docs/dev/test-log.md「Phase 5：功能驗證」（官方測試集）",
        },
        "limitations": "只有 helmet／head 兩類，沒有反光背心等其他防護具；召回率 0.942，約 6% 的未戴安全帽可能漏判。",
        "not_for": "不可當作唯一的工安判定；遠距離或遮擋嚴重的場景。",
    },
    "person-detector": {
        "title": "人員偵測（危險區域入侵）",
        "task": "COCO 預訓練 YOLO11n 的 person 類別，搭配使用者畫的多邊形判斷腳底位置是否入侵",
        "dataset": "COCO（官方預訓練權重，本專案未重新訓練）",
        "dataset_license": f"COCO 標註 CC BY 4.0、圖片依 Flickr 各自授權；{_YOLO_LICENSE}",
        "documented_metrics": {
            "來源": "本專案未重新評估 COCO 指標；只用一張授權真人照片驗證過（95.1% 信心度，見 docs/dev/test-log.md「Phase 2」）"
        },
        "limitations": "以腳底參考點判斷，假設危險區域畫在地面；抽幀影片可能漏掉快速通過的違規。",
        "not_for": "不可當作唯一的安全聯鎖。",
    },
    "pneumonia-cnn": {
        "title": "醫學影像分類展示（肺炎）",
        "task": "小型 CNN 二元分類（normal／pneumonia），僅供技術展示",
        "dataset": "PneumoniaMNIST（MedMNIST，28x28 灰階；train 4708／val 524／test 624）",
        "dataset_license": "CC BY 4.0（需署名）；官方註明非臨床用途",
        "documented_metrics": {},
        "limitations": "僅供技術展示，非醫療診斷用途。normal 召回率僅約 74.8%，約每 4 張正常影像有 1 張被誤判為肺炎樣態。",
        "not_for": "任何臨床或診斷用途。",
    },
}

_ANOMALY_BUILTIN = {
    "dataset": "MVTec AD（{category}）",
    "dataset_license": "CC BY-NC-SA 4.0（非商用）：以此資料擬合的權重不得用於商業產線，正式導入需以自有良品照片重新擬合",
}
_ANOMALY_CUSTOM = {
    "dataset": "使用者上傳的自有良品照片（可含少量 NG 照片用於門檻）",
    "dataset_license": "自有資料",
}
_ANOMALY_COMMON = {
    "task": "非監督式外觀異常檢測（PatchCore，固定 CPU）：只用良品照片擬合，回報整張影像的異常分數與熱力圖",
    "limitations": "分數是 PatchCore 原始距離值，只有同一個模型版本內可比較；光源、角度與擬合照片不同會誤報；只能說哪裡異常，不能說是哪一種瑕疵。",
    "not_for": "拍攝條件與擬合照片明顯不同的場景；需要瑕疵分類的情境（請用監督式模型）。",
}
BUILTIN_ANOMALY = ("metal_nut", "screw", "tile")


def describe(model_id: str) -> dict:
    """回傳模型的靜態說明；不認得的 id（例如新的自訂類別）用對應的通用說明。"""
    if model_id in CATALOG:
        return CATALOG[model_id]
    if model_id.startswith("anomaly-"):
        category = model_id[len("anomaly-") :]
        source = _ANOMALY_BUILTIN if category in BUILTIN_ANOMALY else _ANOMALY_CUSTOM
        return {
            "title": f"外觀異常檢測：{category}",
            **_ANOMALY_COMMON,
            "documented_metrics": {},
            "dataset": source["dataset"].format(category=category),
            "dataset_license": source["dataset_license"],
        }
    return {
        "title": model_id,
        "task": "",
        "dataset": "",
        "dataset_license": "",
        "documented_metrics": {},
        "limitations": "",
        "not_for": "",
    }


# 缺權重時給使用者的下一步（健康檢查與系統狀態頁用）
MISSING_HINTS = {
    "pcb-defect": "請準備 DeepPCB 資料並訓練（scripts/prepare_deeppcb.py），再用 scripts/register_model.py 登錄",
    "ppe-helmet": "請準備 Hard Hat Workers 資料並訓練（scripts/prepare_hardhat.py），再用 scripts/register_model.py 登錄",
    "person-detector": "請下載 yolo11n.pt 放到 models/yolo/（見 README 安裝步驟）",
    "pneumonia-cnn": "請執行 python scripts/train_medmnist.py",
}


def default_weights_path(model_id: str):
    """模型第一次使用時會就地登錄的預設權重位置（各服務的 WEIGHTS_PATH 常數）；不認得的 id 回傳 None。"""
    if model_id == "pcb-defect":
        from modules.defect.service import WEIGHTS_PATH
    elif model_id == "ppe-helmet":
        from modules.safety.service import PPE_WEIGHTS_PATH as WEIGHTS_PATH
    elif model_id == "person-detector":
        from modules.safety.service import WEIGHTS_PATH
    elif model_id == "pneumonia-cnn":
        from modules.medical.service import WEIGHTS_PATH
    elif model_id.startswith("anomaly-"):
        from modules.anomaly.service import MODELS_DIR

        return MODELS_DIR / model_id[len("anomaly-") :] / "weights" / "torch" / "model.pt"
    else:
        return None
    return WEIGHTS_PATH

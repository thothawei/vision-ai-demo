# 台中製造業 AI 辨識 Demo

本機執行的視覺辨識網頁 Demo，作品集用途，對應台中／中科製造業常見情境（工具機與精密機械、手工具、螺絲扣件、金屬加工/CNC、PCB 與電子）。核心辨識完全離線（本機 Ollama／自行訓練的模型），Gemini 免費層只當可選備援。

技術決策、每個 Phase 的實測數字與踩過的坑，見 [CLAUDE.md](CLAUDE.md)；套件/模型/資料集授權查證見 [docs/licenses.md](docs/licenses.md)。開發規劃原始需求見 [docs/manufacturing-ai-plan-prompt.md](docs/manufacturing-ai-plan-prompt.md)。

## 目前功能（Phase 0-5 已完成）

| 模組 | 功能 | 技術 | 實測指標 |
|---|---|---|---|
| M9 | 現場照片開放式辨識（機台、工具、零件、標示、安全觀察） | Ollama `qwen3.5:9b`（本機）／Gemini 備援 | — |
| M4 | 製造文件結構化（工單／出貨單／進料檢驗報告有嚴格 schema + 數字來源核對，其餘文件類型自由格式） | RapidOCR + RapidTable + Ollama／Gemini（Tesseract 保留當比較選項） | — |
| M3 | 外觀瑕疵異常檢測（非監督式，只需良品照片） | Anomalib PatchCore | AUROC 0.965-0.999（三類別） |
| M1 | 追溯碼辨識（QR / 條碼 / DataMatrix / GS1 UDI，效期檢核） | zxing-cpp | — |
| M2 | 零件計數（含相黏分離）與尺寸量測（ArUco 透視校正） | OpenCV | 誤差約 1% |
| M5 | 危險區域入侵偵測（人員偵測 + 前端畫多邊形） | YOLO11n（COCO 預訓練） | — |
| M5 PPE | 安全帽偵測（helmet／head 兩類，無反光背心類別） | YOLO11n（監督式訓練） | mAP50 0.977 |
| M6 | PCB 瑕疵偵測（6 種瑕疵：斷路/短路/缺口/毛刺/多餘銅箔/針孔） | YOLO11n（監督式訓練） | mAP50 0.978 |

M7-M8 待做（銘牌儀表 OCR、醫療包裝檢核），見 [CLAUDE.md](CLAUDE.md) 的「待辦」章節。

## 安裝

### 1. 系統需求

- macOS（實測於 Apple Silicon M1 Pro，PyTorch 用 CPU／MPS 視模組而定）
- [Homebrew](https://brew.sh)
- [uv](https://github.com/astral-sh/uv)（用來裝 Python 3.11——系統原生沒有這個版本）
- [Ollama](https://ollama.com)

### 2. 系統套件

```bash
brew install tesseract tesseract-lang   # M4 mode=tesseract 比較選項用，非預設路徑（預設是 RapidOCR，Python 套件自動下載模型）
brew install unar                       # 解壓 Hard Hat Workers 資料集的 .rar（M5 PPE 訓練用）
ollama pull qwen3.5:9b                  # M9/M4 預設本機 LLM，約 6.6GB
```

### 3. Python 環境

```bash
git clone https://github.com/thothawei/vision-ai-demo.git
cd vision-ai-demo
uv venv --python 3.11 venv
uv pip install --python venv/bin/python -r backend/requirements.txt
```

### 4. YOLO 權重（M5 危險區域入侵用，免訓練）

```bash
venv/bin/python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
mkdir -p models/yolo && mv yolo11n.pt models/yolo/
```

### 5. MVTec AD 資料集 + 擬合異常檢測模型（M3 用，選用）

M3 需要先擬合模型才能用。資料集下載連結見 [docs/licenses.md](docs/licenses.md)（CC BY-NC-SA 4.0，僅供學習/作品集展示，不可商用）：

```bash
mkdir -p data/mvtec_ad && cd data/mvtec_ad
curl -sL -o metal_nut.tar.xz "https://www.mydrive.ch/shares/150459/c68856a21dca589b0f8ff6d4ee0f18f4/download/420937637-1629959294/metal_nut.tar.xz" && tar xf metal_nut.tar.xz
curl -sL -o screw.tar.xz "https://www.mydrive.ch/shares/150461/242f454cc6385e5693c4fd4b94567d1e/download/420938130-1629960389/screw.tar.xz" && tar xf screw.tar.xz
curl -sL -o tile.tar.xz "https://www.mydrive.ch/shares/150462/5479f0fdc97bc6fa16eab0cb0cf0109f/download/420938133-1629960456/tile.tar.xz" && tar xf tile.tar.xz
cd ../..
venv/bin/python scripts/train_anomaly.py --category all   # CPU，約 22 分鐘，實測 AUROC 見 CLAUDE.md
```

（連結來自 MVTec 官方下載頁 https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads 轉址後的真實網址，若失效請重新到官方頁面查詢。）

### 6. DeepPCB 資料集 + 訓練 M6 瑕疵偵測模型（選用）

```bash
git clone --depth 1 https://github.com/tangsanli5201/DeepPCB.git data/deeppcb
venv/bin/python scripts/prepare_deeppcb.py   # 轉成 YOLO 格式
venv/bin/python -c "
from ultralytics import YOLO
YOLO('yolo11n.pt').train(data='data/deeppcb_yolo/data.yaml', epochs=60, imgsz=640,
    batch=16, device='mps', patience=15,
    project='$(pwd)/models/defect', name='pcb_yolo11n', seed=42)
"   # MPS，實測 32 分鐘（41 epoch early stop），mAP50 0.978
```

沒有 Mac／想用 GPU 更快跑更多 epoch，用 `notebooks/train_pcb_defect.ipynb`（Colab）。

### 7. Hard Hat Workers 資料集 + 訓練 M5 PPE 模型（選用）

```bash
mkdir -p data/hardhat && cd data/hardhat
curl -sL -o Hardhat.rar "https://dataverse.harvard.edu/api/access/datafile/3344658"
unar Hardhat.rar
cd ../..
venv/bin/python scripts/prepare_hardhat.py   # 轉成 YOLO 格式
venv/bin/python -c "
from ultralytics import YOLO
YOLO('yolo11n.pt').train(data='data/hardhat_yolo/data.yaml', epochs=60, imgsz=640,
    batch=16, device='mps', patience=15,
    project='$(pwd)/models/ppe', name='ppe_yolo11n', seed=42)
"   # MPS，實測 4.15 小時（跑滿 60 epoch，沒有提早停止），mAP50 0.977
```

資料集比 M6 大 5 倍，訓練時間長很多；沒時間等就用 `notebooks/train_ppe.ipynb`（Colab GPU）。

**`project` 參數務必用絕對路徑**：`ultralytics` 會把相對路徑的 `project` 加上全域設定的 `runs_dir` 前綴，實際輸出位置會跟你以為的不一樣（踩過的坑，見 CLAUDE.md）。

### 8.（可選）Gemini 備援

去 [Google AI Studio](https://aistudio.google.com/apikey) 申請免費 API key，複製 `.env.example` 為 `.env` 填入，並把 `LLM_ENGINE` 設成 `gemini`（預設 `ollama`）。免費層限制見下方「已知限制」。

## 啟動

```bash
ollama serve &        # 若尚未執行
source venv/bin/activate
cd backend
uvicorn main:app --reload
```

瀏覽器開 <http://127.0.0.1:8000>，八個分頁各對應一個模組。

## 測試

```bash
source venv/bin/activate
python tests/samples/make_samples.py   # 產生測試圖，未進版控
pytest                                  # 單元測試（假 LLM/YOLO/PatchCore），約 10 秒
pytest -m live -s                       # 真打本機模型，需先完成上面的安裝/訓練步驟，約 1-2 分鐘
```

## 已知限制

- **Gemini 免費層速率限制**：`LLM_ENGINE=gemini` 時，`gemini-3.6-flash` 免費層實測 RPM=5、RPD=20，只當備援，不是核心路徑。
- **M2 量測精度**：正視角下實測誤差約 0.3-0.6mm（50mm 零件上約 1%），假設待測物與 ArUco 標記共平面。
- **M3 用 CPU 而非 MPS**：PatchCore 的 coreset 篩選在 MPS 上因逐元素 GPU 同步而變得極慢，固定用 CPU（實測反而更快）。詳見 CLAUDE.md。
- **M4 數字來源核對只在 OCR 模式生效**：端到端模式沒有獨立 OCR 原文可以核對，會誠實標記「無法驗證」而不是假裝驗證過。
- **M5 PPE 只有兩類（helmet/head）**：Hard Hat Workers 資料集本身沒有反光背心類別，是資料集限制。
- **M5 危險區域入侵只做單張圖片**：短影片逐幀抽樣目前還沒做。
- **YOLO 監督式訓練耗時差異大**：M6（1000 張）32 分鐘，M5 PPE（5297 張）在 MPS 上要 4.15 小時；`project` 參數務必用絕對路徑，否則權重會存到意外的位置（見上方安裝步驟）。
- 僅供本機 `localhost` 使用，若要手機或外部裝置存取需另外部署。

## 專案結構

```
vision-ai-demo/
├── backend/
│   ├── main.py                 # FastAPI 入口，掛載各模組 router
│   ├── core/                   # 共用回應格式、LLM 抽象層、RapidOCR/Tesseract、SQLite 檢驗紀錄
│   ├── schemas/documents.py    # M4 工單/出貨單/進料檢驗報告 Pydantic schema
│   ├── modules/                # general(M9) / docs(M4) / anomaly(M3) / codes(M1) / measure(M2) / safety(M5+PPE) / defect(M6) / inspections
│   └── requirements.txt
├── frontend/index.html         # 分頁式單頁前端（8 個模組）
├── scripts/                    # make_aruco.py、train_anomaly.py、prepare_deeppcb.py、prepare_hardhat.py
├── notebooks/                  # train_pcb_defect.ipynb、train_ppe.ipynb（Colab GPU 版訓練）
├── models/                     # 權重，gitignore
├── data/                       # SQLite、資料集（MVTec AD / DeepPCB / Hardhat），gitignore
├── tests/                      # pytest：單元測試（假模型）+ live 測試（真模型，-m live）
└── docs/                       # 規劃文件、授權查證紀錄
```

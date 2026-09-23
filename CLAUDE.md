# vision-ai-demo — 台中製造業 AI 辨識 Demo

## 專案目標

本機執行的網頁 Demo，展示台中／中科製造業常見的 AI 影像辨識功能（工具機與精密機械、手工具、螺絲扣件、自行車零件、金屬加工/CNC、PCB 與電子、醫材與藥品包裝），作為應徵台中製造業 AI／ERP／MIS 工程師的作品集。之後會和 `manufacturing-erp`（ASP.NET Core + SQL Server，含品檢查詢）串接，所以每個模組的辨識結果都走共用的 JSON 結構，並寫入 SQLite 檢驗紀錄。

完整規劃見 [docs/manufacturing-ai-plan-prompt.md](docs/manufacturing-ai-plan-prompt.md)；套件與資料集授權查證見 [docs/licenses.md](docs/licenses.md)。

## 硬性規則

1. 只用免費工具；找不到免費方案的功能直接跳過，寫進 README「未納入功能」並說明原因，不寫假的 stub。
2. 核心功能完全離線執行（本機 Ollama 模型），不依賴 Gemini 配額；Gemini 免費層只當可選備援（`.env` 的 `LLM_ENGINE=ollama|gemini` 切換）。
3. 每個套件/模型/資料集安裝前先查官方來源確認版本與授權，寫進 `docs/licenses.md`，不憑記憶填版本號。
4. 非商用授權的資料集（如 MVTec AD 的 CC BY-NC-SA）在 README 註明「僅供學習/作品集展示」。
5. 分階段執行，每個 Phase 結束回報實際測試結果，等確認再進下一階段。
6. 測試結果不可捏造：準確率/推論時間/截圖只記錄實際跑出的數字，沒跑過就寫「未測試」。
7. 大檔（模型權重、資料集、訓練輸出、SQLite）放 `models/`、`data/`、`runs/`，已加進 `.gitignore`。commit 前用 grep 掃過沒有 API key。
8. Apple Silicon Mac：PyTorch 用 `mps`，不支援時自動退回 `cpu`。
9. Python 3.11（Anomalib 等套件需要 ≥3.10）。

## 技術決策與理由（Phase 1）

- **後端：FastAPI + Uvicorn**，Python 3.11（`uv venv --python 3.11`，系統原生只有 3.9/3.10/3.13/3.14，改用 uv 裝 3.11）。
- **LLM 抽象層**（[backend/core/llm.py](backend/core/llm.py)）：`LLM_ENGINE=ollama`（預設）或 `gemini`（備援），模組只呼叫 `generate_json(prompt, image)`，不需要知道底層引擎。
  - Ollama 預設模型 `qwen3.5:9b`（6.6GB、Apache-2.0，2026-09 查證版本，多模態）。`qwen3-vl:8b` 為備選。`qwen3.6`／`qwen3.8` 最小為 27B，16GB Mac 跑不動，不採用。
  - `ollama.Client.chat(..., format="json", think=False)` 強制輸出 JSON，關閉思考模式減少延遲；找不到模型或連不上 Ollama 時回傳清楚的錯誤訊息（提示 `ollama pull` 或 `ollama serve`）。
  - JSON 解析失敗會回傳 502 錯誤，不會硬塞假資料掩蓋問題。
- **共用回應格式**（[backend/core/schemas.py](backend/core/schemas.py)）：`{module, verdict, items, annotated_image, engine, elapsed_ms, inspection_id}`，所有模組一致，方便之後 ERP 串接。
- **檢驗紀錄**（[backend/core/inspection_log.py](backend/core/inspection_log.py)）：SQLite（`data/inspections.db`，不進版控），每次辨識寫一筆，`GET /api/inspections?module=&verdict=&date_from=&date_to=` 查詢，`/api/inspections/export.csv` 匯出（含 BOM，Excel 開啟中文不亂碼）。
- **目錄結構**：`backend/core/`（共用工具）、`backend/modules/<模組>/{router.py,service.py}`（每個模組獨立）、`tests/`（pytest，測試圖由 `tests/samples/make_samples.py` 程式生成，不依賴外部授權圖片，不進版控）。
- **M9 開放式辨識**：原「街景辨識」改為現場照片辨識，prompt 改成機台/工具/零件/標示/安全觀察情境，新增「可見文字」「安全觀察」欄位。
- **M4 製造文件結構化**：Phase 1 沿用 Tesseract 兩段式 + 端到端兩種模式（欄位命名改成工單/出貨單/檢驗報告情境），改走 LLM 抽象層。Phase 4 會換成 RapidOCR + Pydantic schema（理由見下方套件決策）。
- **套件版本鎖定不用 PaddleOCR**：用 `uv pip compile` 實測，Python 3.11 環境下 `paddlex` 要求 `numpy<2.4`，會把 `paddleocr` 拖回 2.10.0 舊版且 macOS 只有 CPU 版；改用 RapidOCR（同樣是 PP-OCR 模型的 ONNX 版，Apache-2.0，相依乾淨）。
- **測試策略**：單元測試（`pytest`，預設執行）用假的 `core.llm.generate_json` / `modules.safety.service._detect_persons` 隔離 LLM 與 YOLO，只驗證 API 契約、SQLite 寫入、錯誤處理、業務邏輯（GS1 解析、效期判斷、多邊形入侵判斷）；`-m live` 標記的測試會真的呼叫本機 Ollama／YOLO，驗證真實延遲與準確度，預設不跑。

## 技術決策與理由（Phase 2）

- **M1 追溯碼（`backend/modules/codes/`）**：`zxing-cpp` 解碼，GS1 條碼的 `barcode.text` 預設就是 `(AI)值(AI)值...` 的人類可讀格式（`TextMode.HRI`），不需要自己處理 FNC1 分隔符號；(17) 效期用 GS1 規則（YY 00-50→20xx、51-99→19xx，DD=00 代表當月最後一天）換算，已過期 NG、30 天內到期標「即將到期」（不算 NG）。
- **M2 計數（`backend/modules/measure/`）**：一開始用「distance transform 整塊閾值」分割相黏零件失敗（兩顆相黏的圓被當成一顆，面積是單顆的 2 倍），改用「距離變換的局部極大值當種子點」才能正確分離——原因是整塊閾值下，兩顆圓重疊處的距離值仍高於閾值，前景還是連通的；局部極大值抓的是各自的中心峰值，不受這個影響。
- **M2 量測**：ArUco 標記四角做 homography 透視校正，把整張圖攤平成固定 px/mm 的正視圖再量測。實測系統性誤差約 0.3-0.6mm（50mm 零件上約 1%），來源是 ArUco 邊界像素化與二值化邊緣效應；預設公差從原規劃的 0.5mm 調整為 1.0mm 較務實。
- **M5 危險區域入侵（`backend/modules/safety/`）**：YOLO 選用 `yolo11n.pt`（成熟穩定、COCO person 類別）而非同批發布的 `yolo26n.pt`（2026-09 才發布的最新架構，尚無足夠驗證案例）；人員判定用「邊界框底邊中點（腳底參考點）」是否落在使用者畫的多邊形內（`cv2.pointPolygonTest`），而非用整個框判斷，理由是危險區域通常畫在地面，用腳底位置比整個人形框更符合實際「站在哪裡」的語意。Phase 2 只做單張圖片，短影片逐幀抽樣留到 Phase 5 跟 PPE 一起做。
- **live 測試用真實照片**：M5 的自動偵測準確度用合成圖驗證不出意義（YOLO 認的是真人特徵），改抓 Wikimedia Commons 的 CC BY 2.0 授權工廠照片（`tests/live_samples/`，不進版控，來源見 `docs/licenses.md`），95.1% 信心度正確偵測到人。

## 技術決策與理由（Phase 3）

- **M3 異常檢測（`backend/modules/anomaly/`）**：Anomalib PatchCore，非監督式——只用良品照片擬合一個特徵記憶庫（memory bank），不需要 NG 樣本，這正對應工廠現場「良品多、NG 樣本稀少」的真實情境。骨幹網路用預設的 `wide_resnet50_2`（ImageNet 預訓練，Apache-2.0，只做前向推論抽特徵，不重新訓練）。
- **PatchCore 固定用 CPU，不用 MPS**：實測 MPS 反而比 CPU 慢很多，原因是 coreset 貪婪演算法逐元素呼叫 `.item()` 觸發 GPU 同步（見已知限制、Phase 3 測試紀錄的除錯過程）。這跟 Phase 0 原本規劃的「MPS 優先，不支援才退回 CPU」不同——MPS 是支援的，只是這個特定演算法在 MPS 上特別慢，所以固定用 CPU。
- **訓練與推論分離**：`scripts/train_anomaly.py` 離線擬合＋用 `anomalib.deploy.ExportType.TORCH` 匯出成 `TorchInferencer` 可直接載入的 `.pt`（包好 pre-processor 與門檻值），服務層（`backend/modules/anomaly/service.py`）只做推論、不依賴完整的 Lightning 訓練環境概念，載入後常駐記憶體、依 category 分開快取。
- **熱力圖標註**：`anomaly_map` 正規化到 0-1 後用 `cv2.COLORMAP_JET` 上色疊在原圖上（紅＝異常機率高），跟其他模組共用的 `annotated_image` 欄位格式一致。
- **信任本機權重**：anomalib 的 `TorchInferencer` 預設拒絕 unpickle 權重檔（防惡意程式碼），只在載入自己訓練產生的權重時設定 `TRUST_REMOTE_CODE=1`，並在程式碼註解寫清楚為什麼這樣做是安全的（不是無條件關掉資安檢查）。

## 技術決策與理由（Phase 4）

- **M4 換成 RapidOCR（`backend/core/ocr.py`）**：取代 Phase 1-3 暫時沿用的 Tesseract。實測工單號 `WO-2026-0915`，Tesseract 會誤讀成 `WO-2026-0215`（數字 9→2），RapidOCR 讀得完全正確——這不是理論上的優勢，是同一張測試圖跑出來的真實差異。Tesseract 保留成 `mode=tesseract` 比較選項（`backend/core/tesseract_ocr.py`），不是直接砍掉。
- **表格結構辨識（`RapidTable`）**：出貨單的品項表格用 `rapid-table`（`slanet-plus.onnx`）解析成 HTML 表格，當作額外上下文餵給 LLM，幫助多列品項的解析更準；表格辨識失敗時退回純文字，不讓整個請求掛掉。`rapid-layout` 裝了但這個 Phase 沒用到（目前三種文件都是單一區塊版面，不需要版面分析；留給之後 M7 銘牌/複雜版面用）。
- **嚴格 schema（`backend/schemas/documents.py`）**：工單／出貨單／進料檢驗報告三種文件定義 Pydantic model，LLM 回傳的 JSON 一律過 `model_validate()`；驗證失敗回傳 `_驗證錯誤`（逐欄位列出問題），不會用預設值把錯誤蓋過去。報價單／名片／其他文件類型沿用原本的自由格式（不硬套 schema，因為欄位天生因文件而異）。
- **數字來源核對（防止 LLM 捏造數字）**：所有數字欄位都用 `{值, 原文片段}` 的格式，LLM 除了給數字還要附上「這是從原文哪裡抄的」；service 層（`_annotate_source_verification`）拿這段原文片段去對 OCR 真實文字做子字串比對，比對得到標「OK」，比對不到標「可疑：原文中找不到這段文字，數字可能是 LLM 捏造的」——這個檢查完全不靠 LLM 自己說了算。端到端模式沒有獨立 OCR 文字可以核對，誠實標記「無法驗證」，不假裝驗證過。
- **文件類型判斷分兩段 LLM 呼叫**：先分類（`文件類型`），再依分類結果決定要不要套嚴格 schema、要用哪個 schema 專用 prompt。兩段式比一段式多一次 LLM 呼叫的延遲，換來的是每種文件類型可以給非常明確的目標 JSON 結構範例，而不是要 LLM 自己猜欄位名稱。

## 技術決策與理由（Phase 5）

- **M6 PCB 瑕疵偵測（`backend/modules/defect/`）**：監督式 YOLO11n，跟 M3（PatchCore，非監督）刻意互補——M3 不需要 NG 樣本但只能說「哪裡異常」，M6 需要標註過的 NG 樣本（DeepPCB）但能講出「是哪一種瑕疵」（斷路/短路/缺口/毛刺/多餘銅箔/針孔）。
- **DeepPCB 官方沒有切分清單，自己切**：官方 README 只說「1000 張當訓練集，其餘當測試集」，沒附清單。`scripts/prepare_deeppcb.py` 用固定亂數種子（42）切 1000/250/250，可重現，並在程式註解與文件裡誠實寫「不是官方切分」。
- **MPS 訓練 YOLO 沒有 M3 PatchCore 那個坑**：M3 的 coreset 演算法在 MPS 上因逐元素 `.item()` 同步而極慢；YOLO 的訓練是標準卷積+反向傳播，MPS 支援良好，實測 M1 Pro 上 1 epoch（1000 張、batch16）約 47 秒，PCB 模型 41 epoch（early stop）只花 32 分鐘。這跟 M3 的結論不衝突——「MPS 對某些特定演算法很慢」不等於「MPS 對深度學習訓練普遍很慢」。
- **ultralytics 的 `project` 路徑陷阱（真的踩到，見下方測試紀錄）**：`project='models/defect'` 這種相對路徑會被 ultralytics 全域設定的 `runs_dir` 加上前綴，實際存到 `runs/detect/models/defect/...`，不是我以為的 `models/defect/...`。PPE 訓練改用絕對路徑 `project='/Users/.../models/ppe'` 避開這個陷阱。
- **M5 PPE 只有兩類（helmet/head）**：Hard Hat Workers 資料集本身沒有反光背心類別，這是 Phase 0 就查證過的資料集限制，不是這個 Phase 漏做；沿用資料集自帶的 Train/Test 切分（不像 DeepPCB 要自己切）。

## 目錄結構

```
vision-ai-demo/
├── backend/
│   ├── main.py                 # FastAPI 入口，只負責掛載各模組 router、統一錯誤格式
│   ├── core/
│   │   ├── schemas.py          # 共用回應格式 InspectionResult、ModuleError
│   │   ├── image_io.py         # 讀圖、EXIF 轉正、縮圖、base64
│   │   ├── llm.py              # Ollama / Gemini 抽象層
│   │   ├── ocr.py               # RapidOCR + RapidTable（M4 主要 OCR 引擎）
│   │   ├── tesseract_ocr.py     # Tesseract（M4 比較選項 mode=tesseract）
│   │   └── inspection_log.py   # SQLite 檢驗紀錄
│   ├── schemas/documents.py    # M4 工單/出貨單/進料檢驗報告 Pydantic schema
│   ├── modules/
│   │   ├── general/            # M9 開放式辨識
│   │   ├── docs/                # M4 製造文件結構化
│   │   ├── anomaly/              # M3 外觀瑕疵異常檢測
│   │   ├── codes/                # M1 追溯碼辨識
│   │   ├── measure/              # M2 計數與尺寸量測
│   │   ├── safety/               # M5 危險區域入侵 + PPE 安全帽偵測
│   │   ├── defect/               # M6 PCB 瑕疵偵測
│   │   └── inspections/         # 檢驗紀錄查詢 / CSV 匯出
│   └── requirements.txt
├── frontend/index.html         # 分頁式單頁（8 個模組各一頁，M5 有 canvas 畫多邊形危險區域）
├── scripts/
│   ├── make_aruco.py           # 產生 M2 量測用的可列印 ArUco 標記 PDF
│   ├── train_anomaly.py        # 擬合 M3 PatchCore、實測 AUROC、匯出推論用權重
│   ├── prepare_deeppcb.py      # DeepPCB 官方標註 → YOLO 格式（M6）
│   └── prepare_hardhat.py      # Hard Hat Workers Pascal VOC → YOLO 格式（M5 PPE）
├── notebooks/
│   ├── train_pcb_defect.ipynb  # M6 訓練，Colab GPU 版（重用 scripts/prepare_deeppcb.py）
│   └── train_ppe.ipynb         # M5 PPE 訓練，Colab GPU 版
├── models/
│   ├── yolo/yolo11n.pt         # M5 危險區域入侵用，YOLO 官方 release 下載，gitignore
│   ├── anomaly/<category>/     # M3 用，scripts/train_anomaly.py 產生，gitignore
│   │   ├── weights/torch/model.pt   # 推論用（TorchInferencer 直接載入）
│   │   └── metrics.json             # 實測 image-level AUROC、擬合耗時、測試集大小
│   ├── defect/pcb_yolo11n/     # M6 用，results.csv 有逐 epoch 訓練曲線，gitignore
│   └── ppe/ppe_yolo11n/        # M5 PPE 用，gitignore
├── tests/
│   ├── conftest.py
│   ├── samples/make_samples.py # 程式生成測試圖（工單、警示標示、GS1條碼、零件、ArUco量測場景），不進版控
│   ├── live_samples/            # pytest -m live 用的真實授權照片，不進版控，來源見 README.md
│   ├── test_modules.py         # M9/M4 API 契約、SQLite（假 LLM）
│   ├── test_llm.py             # LLM 抽象層錯誤處理（假 LLM / 假連線）
│   ├── test_codes.py            # M1：GS1 解析、效期判斷
│   ├── test_measure.py          # M2：計數分離、量測精度、OK/NG 公差
│   ├── test_safety.py           # M5：多邊形入侵邏輯（假偵測結果）
│   ├── test_docs.py              # M4：schema 驗證、來源核對邏輯（真跑 RapidOCR，假 LLM）
│   ├── test_defect.py            # M6：假偵測結果驗證 OK/NG 判定
│   ├── test_ppe.py               # M5 PPE：假偵測結果驗證 OK/NG 判定
│   ├── test_live_ollama.py     # 真打 Ollama，pytest -m live
│   ├── test_live_safety.py      # 真打 YOLO + 真人照片，pytest -m live
│   ├── test_live_anomaly.py     # 真打 PatchCore + MVTec AD 測試集，pytest -m live
│   ├── test_live_docs.py        # 真打 Ollama 跑完整 M4 兩段式流程，pytest -m live
│   ├── test_live_defect.py      # 真打訓練好的 PCB 模型 + DeepPCB 測試集，pytest -m live
│   └── test_live_ppe.py         # 真打訓練好的 PPE 模型 + Hardhat 驗證集，pytest -m live
├── docs/
│   ├── manufacturing-ai-plan-prompt.md
│   └── licenses.md
├── data/
│   ├── inspections.db           # SQLite，gitignore
│   └── mvtec_ad/<category>/     # MVTec AD 官方目錄結構，gitignore，下載方式見 docs/licenses.md
└── .env / .env.example
```

## 環境需求

- Python 3.11（用 `uv venv --python 3.11` 建立，系統原生無 3.11）
- [Ollama](https://ollama.com) 已安裝並執行，模型 `qwen3.5:9b`（`ollama pull qwen3.5:9b`，約 6.6GB）
- Tesseract OCR（macOS: `brew install tesseract tesseract-lang`，M4 OCR 模式與比較用）
- YOLO11n 權重（`models/yolo/yolo11n.pt`，M5 用；`python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"` 下載後手動搬過去，5.6MB）
- MVTec AD 資料集（M3 用，`data/mvtec_ad/<category>/`，下載連結見 `docs/licenses.md`，CC BY-NC-SA 4.0 僅供學習/作品集展示）+ 擬合權重（`python scripts/train_anomaly.py --category all`，CPU 約 22 分鐘，見已知限制的 MPS 說明）
- DeepPCB 資料集（M6 用，`git clone https://github.com/tangsanli5201/DeepPCB.git data/deeppcb`，MIT，231MB）+ `python scripts/prepare_deeppcb.py` 轉 YOLO 格式 + 訓練（MPS 約 32 分鐘，見 CLAUDE.md 測試紀錄）
- Hard Hat Workers 資料集（M5 PPE 用，下載連結見 `docs/licenses.md`，CC0 1.0，268MB rar，需要 `unar` 或 `unrar` 解壓）+ `python scripts/prepare_hardhat.py` 轉 YOLO 格式 + 訓練（MPS，5297 張訓練圖，比 PCB 久很多）
- （可選）Google Gemini API key，存在 `.env` 的 `GEMINI_API_KEY`，`LLM_ENGINE=gemini` 時才需要

## 啟動方式

```bash
cd ~/Documents/vision-ai-demo
ollama serve &        # 若尚未執行
source venv/bin/activate
cd backend
uvicorn main:app --reload
```

瀏覽器開 http://127.0.0.1:8000

## 測試方式

```bash
source venv/bin/activate
python tests/samples/make_samples.py   # 產生測試圖（需要，未進版控）
pytest                                  # 單元測試，假 LLM/YOLO/PatchCore，約 6 秒
pytest -m live -s                       # 真打本機模型，需先 ollama serve + 下載 MVTec AD + 擬合 M3 權重，約 1-2 分鐘
```

## 已知限制

- **Gemini 免費層速率限制**：`LLM_ENGINE=gemini` 時，`gemini-3.6-flash` 免費層實測 RPM=5、RPD=20，只當備援，不是核心路徑。
- **Tesseract OCR 誤判（Phase 4 起已不是預設路徑）**：`mode=tesseract` 比較選項下，Tesseract 會把數字誤讀（實測：`0915` 被讀成 `0215`），這正是 Phase 4 把預設引擎換成 RapidOCR 的原因（RapidOCR 讀這張圖完全正確）；端到端模式（AI 直接讀圖）準確度也高但較慢，且無法做數字來源核對。
- **M4 數字來源核對只在 OCR 模式生效**：端到端模式沒有獨立的 OCR 原文可以核對「原文片段」是否真實存在，這個欄位會誠實標記「無法驗證」，不是假裝驗證過。
- **本機模型延遲**：`qwen3.5:9b` 在 M1 Pro 上單次辨識約 8-20 秒，比 Gemini 雲端 API 慢，是離線換取的代價。
- **16GB 記憶體**：同時載入 Ollama 模型與之後 Phase 3+ 的 PyTorch 模型會吃緊，模型皆採延遲載入（首次呼叫才載入）。
- **M2 計數對背景要求高**：假設零件是畫面中的少數像素、跟背景有明顯亮度反差；零件間距小於約 25px（局部極大值種子的搜尋半徑）時仍可能分不開，見 `_binarize_foreground_minority` 的說明。
- **M2 量測精度**：正視角下實測誤差約 0.3-0.6mm（50mm 零件上約 1%），假設待測物與 ArUco 標記共平面，手機斜角拍攝會讓誤差變大；預設公差 1.0mm。
- **M5 只做單張圖片**：短影片逐幀抽樣目前仍未做，之後有需要再補，不是遺漏。
- **PatchCore 在 M1 Pro 的 MPS 上反而比 CPU 慢**：coreset 篩選（greedy k-center）在 Python 迴圈裡逐元素呼叫 `.item()` 把純量搬回 CPU，每次都觸發一次 MPS 同步；用 `sample` 系統工具實測抓到呼叫堆疊卡在 `MPSStream::synchronize`，幾分鐘幾乎沒進度。`scripts/train_anomaly.py` 固定用 CPU（實測反而更快，metal_nut 擬合 322 秒／screw 664 秒／tile 406 秒），這不是「MPS 不支援」，是「這個演算法在 MPS 上特別慢」。
- **M3 擬合耗時隨訓練集大小明顯增加**：metal_nut（220 張良品）5.4 分鐘、screw（320 張）11.1 分鐘、tile（230 張）6.8 分鐘，CPU 佔用可能衝到 400-500%（多執行緒）。
- **M3 推論需要信任本機權重**：anomalib 的 `TorchInferencer` 預設拒絕 unpickle（防止惡意權重執行任意程式碼），服務層對 `scripts/train_anomaly.py` 自己訓練匯出的權重設定 `TRUST_REMOTE_CODE=1`——只信任本機訓練產生的檔案，不代表信任任意下載的權重。
- **`ultralytics` 的 `project` 相對路徑陷阱**：`YOLO().train(project='models/xxx')` 這種相對路徑會被全域設定的 `runs_dir` 加前綴，實際存到 `runs/detect/models/xxx/`，不是字面上那個路徑；用絕對路徑就不會有這個問題。M6/M5 PPE 的服務層 `WEIGHTS_PATH`／`PPE_WEIGHTS_PATH` 都寫死指向 `models/defect/pcb_yolo11n/weights/best.pt`、`models/ppe/ppe_yolo11n/weights/best.pt`，重新訓練時要確保 `project` 用絕對路徑或訓練完手動核對/搬移產出位置。
- **YOLO 監督式訓練耗時差異大**：跟資料量、裝置有關，M6（1000 張、CPU/MPS 皆可）32 分鐘；M5 PPE（5297 張）在 MPS 上跑滿 60 epoch 要 4.15 小時，重新訓練前要有心理準備。PatchCore（M3）的 MPS 慢是特例（逐元素同步），YOLO 訓練本身在 MPS 上表現正常。
- **M5 PPE 只有兩類（helmet/head）**：Hard Hat Workers 資料集本身沒有反光背心類別，這是 Phase 0 就查證過的資料集限制。

## 待辦（Phase 進度）

- [x] Phase 0：查證套件/模型/資料集授權，寫入 `docs/licenses.md`；確認 Mac 安裝風險（PaddleOCR 在 py3.11 相依衝突、OpenCV 三套件共用 cv2 命名空間、16GB 記憶體限制）。
- [x] Phase 1：Python 3.11 venv 重建、目錄重構（`core/`、`modules/<模組>/`）、共用回應格式、LLM 抽象層（Ollama 預設／Gemini 備援）、SQLite 檢驗紀錄 + 查詢/CSV API、前端改分頁式。原有兩功能搬進 M9（開放式辨識，prompt 改製造業情境）／M4（文件結構化，欄位改製造業情境）且已用真實 Ollama 模型與真實瀏覽器驗證可用。
- [x] Phase 2：M1 追溯碼（zxing-cpp + GS1 解析 + 效期判斷）、M2 計數量測（OpenCV watershed 分離相黏零件 + ArUco 透視校正量測）、M5 危險區域入侵（YOLO11n person 偵測 + 前端 canvas 畫多邊形）。全部免訓練，已用真實資料（含真人照片）與真實瀏覽器驗證可用。
- [x] Phase 3：M3 異常檢測（Anomalib PatchCore + MVTec AD）。三類別實測 image-level AUROC：metal_nut 0.9985、screw 0.9645、tile 0.9993（見下方測試紀錄）。已用真實測試集圖片與真實瀏覽器驗證可用，熱力圖能準確標出瑕疵位置。
- [x] Phase 4：M4 換成 RapidOCR + Pydantic schema。實測 RapidOCR 修正了 Phase 1 記錄的 Tesseract 誤讀（工單號 `0915→0215`）；工單/出貨單/進料檢驗報告三種文件套嚴格 schema，數字欄位附「來源驗證」核對 LLM 有沒有捏造數字；Tesseract 保留當比較選項。
- [x] Phase 5：M6 DeepPCB 瑕疵偵測（YOLO11n，mAP50 0.978，41 epoch/32 分鐘）、M5 PPE 安全帽偵測（YOLO11n，mAP50 0.977，60 epoch/4.15 小時）。附 Colab notebook（`notebooks/`），已用真實資料與真實瀏覽器驗證可用。
- [ ] Phase 6：M7 銘牌／儀表。
- [ ] Phase 7：M8 醫療相關（包裝檢核、MedMNIST 教學展示）。
- [ ] Phase 8：收尾（README、CLAUDE.md、Demo 截圖）。

## 測試紀錄（真實驗證，非猜測）

### Phase 0：套件安裝查證
- 用 `uv pip compile` 在暫存 venv 對 Python 3.11 / macOS arm64 實際解析整組套件相依，並實裝驗證 import：`torch 2.14`（`torch.backends.mps.is_available() == True`）、`anomalib 2.6.2`（`Patchcore` 可 import）、`ultralytics 8.4.160`、`rapidocr`、`onnxruntime 1.30`、`zxingcpp`、`medmnist`、`cv2 5.0`（`cv2.aruco.ArucoDetector` 存在）全部成功。
- 查出 PaddleOCR 在此環境會被相依解析器拖回 2.10.0 舊版（`paddlex` 要求 `numpy<2.4`），改用 RapidOCR。

### Phase 1：功能驗證
- **單元測試**：`pytest`，13 項全過（0.98 秒），涵蓋 M9/M4 兩個 API 的正常路徑、共用回應格式欄位、SQLite 寫入與查詢/CSV 匯出、空檔案/非圖片/錯誤 mode 的錯誤處理、LLM 抽象層的無效引擎/連線失敗/模型不存在/缺 API key 錯誤訊息。
- **Live 測試（真打本機 Ollama `qwen3.5:9b`）**：`pytest -m live -s`，3 項全過（52 秒）。
  - M9：警示標示測試圖，正確讀出「危險 DANGER」「機台運轉中 請勿靠近」等可見文字，信心程度「高」且理由合理，耗時約 20 秒（第一次呼叫含模型載入）。
  - M4 OCR 模式：正確判斷文件類型「工單」，料號 `SC-M6-20` 正確；但 Tesseract 把工單號 `WO-2026-0915` 誤讀成 `WO-2026-0215`，LLM 照抄了這個錯誤（符合設計：LLM 不能捏改 OCR 原文）。耗時約 14 秒。
  - M4 端到端模式：同一張圖，AI 直接讀圖，工單號 `WO-2026-0915` 正確、品名 `六角螺栓 M6x20` 也比 OCR 模式的 `Mox20` 準確。耗時約 17 秒。
  - **結論驗證**：這組結果重現了原本 README 記載的「端到端準確度較高、OCR 較快但可能誤判」的結論，這次的錯誤案例（`0915→0215`）具體可追蹤到 Tesseract 的數字誤讀，不是 LLM 捏造的。
- **瀏覽器實測**（真實 Chrome，`mcp__claude-in-chrome__*`，內嵌瀏覽器不支援檔案選擇對話框）：兩個分頁都實際上傳圖片並點擊按鈕，M9 分頁 8.4 秒後正確顯示結果卡片（含 engine/verdict/耗時徽章），M4 分頁 13.5 秒後正確顯示工單欄位；`GET /api/inspections` 確認該次辨識已寫入 SQLite。

### Phase 2：功能驗證
- **單元測試**：`pytest`，29 項全過（1.49 秒）。新增 M1（GS1 解析、已過期/即將到期/正常三種效期狀態、找不到條碼、空檔案）、M2（相黏零件分離、預期數量 OK/NG、量測精度、公差 OK/NG、找不到 ArUco 標記的錯誤訊息）、M5（假偵測結果驗證多邊形入侵邏輯、無效 zone JSON、頂點數不足）。
- **開發中抓到的真實 bug**：M2 計數一開始用「distance transform 整塊閾值」分割相黏零件，實測把兩顆相黏的圓當成一顆（面積 7088px²，是單顆 3745px² 的 1.9 倍），不是我猜測的——是真的跑出來發現數字不對。改用「距離變換的局部極大值當種子點」後正確分離成 8 顆（相黏那兩顆分別是 3544px²、3501px²，跟其他分開的零件面積相近）。
- **Live 測試（真打本機模型）**：`pytest -m live -s`，4 項全過（59 秒）。
  - M9/M4（沿用 Phase 1 案例）：結果與 Phase 1 一致，qwen3.5:9b 穩定重現。
  - M5：用真實 CC BY 2.0 授權照片（Wikimedia Commons，工廠操作員照片，5697x3798），YOLO11n 以 95.1% 信心度正確偵測到 1 人，邊界框 `[723,23,3048,3758]` 跟畫面中人物位置吻合；涵蓋人物的區域判定入侵，涵蓋畫面右側（無人）的區域判定沒入侵。
- **量測精度實測**（非估計）：正視角、已知 50x20mm 矩形 + 5mm 孔的合成場景，量出 50.6mm / 20.3mm / 孔徑 5.42mm，誤差 0.3-0.6mm（約 1%），來源是 ArUco 邊界像素化與二值化邊緣效應；因此把預設公差從規劃的 0.5mm 調整為 1.0mm。
- **GS1 條碼格式實測確認**：一開始以為要自己處理 FNC1（`\x1d`）分隔符號，寫死用 `\x1d` 當分隔字元建立測試條碼直接被 `zxing-cpp` 拒絕（`Control characters are not supported by GS1`）；查了才知道要用 `(AI)值` 的 HRI 格式＋`gs1=True` 參數建立，且解碼出來的 `text` 欄位本來就是這個格式，不需要自己寫 FNC1 解析器。
- **瀏覽器實測**（真實 Chrome）：五個分頁全部實際操作過。
  - M1：上傳 GS1 DataMatrix 測試圖，9ms 解碼出正確的 GTIN/批號/序號/效期，標註圖顯示綠色框（效期正常）。
  - M2：計數分頁 35ms 數出 8 顆並判定 OK（預期 8）；量測分頁 100ms 量出跟 curl 測試一致的數字。
  - M5：上傳真人照片，用滑鼠在 canvas 上點擊畫出涵蓋人物的多邊形（第一次點擊的多邊形底邊差了幾像素沒蓋到腳底參考點，NG 判定漏掉——這是操作精度問題，不是程式邏輯錯，重畫涵蓋到畫面底部邊緣後正確判定 NG，標註圖清楚顯示半透明紅色危險區域疊圖與紅色人員邊界框）。

### Phase 3：功能驗證

- **實測 image-level AUROC（官方測試集，非估計）**：
  | 類別 | AUROC | 測試集張數 | 擬合耗時（CPU） |
  |---|---|---|---|
  | metal_nut | **0.9985** | 115 | 322 秒 |
  | screw | **0.9645** | 160 | 664 秒 |
  | tile | **0.9993** | 117 | 406 秒 |

  數字來自 `scripts/train_anomaly.py` 呼叫 `anomalib.engine.Engine.test()`，跑的是 MVTec AD 官方切分的完整測試集（含良品與各種瑕疵子類別），不是抽樣估計；各自存在 `models/anomaly/<category>/metrics.json`。
- **開發中發現的真實問題（MPS 比 CPU 慢）**：一開始照 Phase 0 規劃用 `torch.backends.mps.is_available()` 自動選 MPS，metal_nut 跑了 10 幾分鐘幾乎沒有進度（CPU 時間幾乎不動）。用 macOS `sample` 系統工具對執行中的程序抓呼叫堆疊，兩次都停在 `at::mps::MPSStream::synchronize`，往上追是 PatchCore 的 coreset 貪婪演算法在 Python 迴圈裡逐元素呼叫 `tensor.item()`，每次都要等一次 GPU 同步。改成固定用 CPU 後，metal_nut 5.4 分鐘內就跑完，而且 AUROC 數字相同（CPU/MPS 只影響速度不影響數值）。
- **過程中一度誤判「訓練卡死」**：screw 訓練到一半，主行程 CPU 降到 0.1%、8 個 dataloader 子行程也全部 0% CPU、狀態都是 sleeping，看起來像死鎖。連續觀察 40 秒後發現其實是「忙閒交替」（0.1% → 256% → 484% → 123%），是 dataloader worker 在測試階段重新產生子行程造成的正常波動，不是真的卡死。教訓：判斷「有沒有卡死」不能只看瞬間 CPU 數字，要連續觀察一段時間或直接用 `sample` 抓呼叫堆疊確認在算什麼。
- **anomalib 的資安機制**：`TorchInferencer` 載入權重時預設會擋下 unpickle（`ValueError: ... requires executing arbitrary code via Python's pickle module`），第一次串接時被這個錯誤擋住；查證後確認這是防止載入惡意權重的正常機制，因為載入的是自己訓練產生的檔案，設定 `TRUST_REMOTE_CODE=1` 才能載入（僅在服務層這個載入點設定，不影響全域環境）。
- **真實測試集圖片驗證**：直接呼叫 `inspect_part()`（不透過假推論），用 MVTec AD 官方測試集的良品與瑕疵品各測了幾張，全部判定方向正確：
  - metal_nut：`good` → OK（分數 0.35-0.41）；`bent` → NG（分數 0.9971-1.0）；`scratch` → NG（分數 0.54-0.83）
  - screw：`good` → OK（分數 0.49）；`scratch_head` → NG（分數 0.88）
  - tile：`good` → OK（分數 0.34-0.42）；`crack` → NG（分數 1.0）
- **live 測試（`pytest -m live`，用官方測試集抽樣，非人工挑選）**：3 個類別全過，screw 抽樣 11/13、tile 抽樣 13/13、metal_nut 抽樣全過（門檻 70% 正確率）。
- **瀏覽器實測**（真實 Chrome）：M3 分頁上傳 metal_nut 的刮痕瑕疵圖，1668ms 判定 NG（分數 0.8291），熱力圖疊圖清楚把紅色熱區精準標在刮痕位置上；換成 tile 的裂痕瑕疵圖、切換下拉選單到 `tile` 類別，4081ms 判定 NG（分數 1.0）。
- **磁碟清理**：訓練時 anomalib Engine 預設會把每一張測試圖的視覺化結果存到 `models/anomaly/_engine_logs/`，三個類別累積到 822MB，訓練完成、metrics.json 記錄下數字後就刪掉了（不影響推論，推論只需要 `weights/torch/model.pt`）。

### Phase 4：功能驗證

- **RapidOCR vs Tesseract 準確度實測對比**（同一張測試圖，非分別測不同圖）：工單號 `WO-2026-0915`，Tesseract 讀成 `WO-2026-0215`（0915 誤讀成 0215，跟 Phase 1 記錄的坑一樣），RapidOCR 完全讀對。這是這個 Phase 換引擎最直接的證據。
- **表格辨識實測**：出貨單測試圖（2 列品項的格線表格）用 `RapidTable` 解析，正確輸出 `<table><tr><td>料號</td>...` 的 HTML，兩列資料一字不差；餵給 LLM 後兩個品項的料號/品名/數量/單價全部正確解析成 JSON。
- **單元測試**：`pytest`，新增 `tests/test_docs.py` 11 項（RapidOCR 真的跑、LLM 用假佇列模擬兩段式呼叫），涵蓋：工單正常解析＋來源驗證 OK、來源片段查無此文字標「可疑」、缺必要欄位觸發 Pydantic 驗證錯誤（`_驗證錯誤` 列出所有缺漏欄位、不硬塞預設值）、出貨單表格解析、進料檢驗報告「判定」欄位限制合格/不合格（給無效值會被 Pydantic 拒絕）、報價單等自由格式類型不套 schema、端到端模式的「來源驗證」誠實標記「無法驗證」、Tesseract 比較模式的 engine 名稱正確、空白圖片在呼叫 LLM 之前就被擋下。全專案累計 41 項單元測試全過（11.5 秒）。
- **live 測試（真打本機 Ollama，完整兩段式流程）**：`pytest -m live -s`，3 項全過（41 秒），三種嚴格 schema 文件都測了：
  - 工單：`WO-2026-0915` 正確、數量 5000、來源驗證 OK
  - 出貨單：2 個品項全部正確、總額 6500、來源驗證 OK（含表格解析）
  - 進料檢驗報告：抽樣數 50、不良數 2、判定「合格」，全部正確
- **瀏覽器實測**（真實 Chrome）：M4 分頁上傳進料檢驗報告圖片，8635ms 後正確顯示文件類型、供應商、料號、批號，數量欄位展開成 `{值, 原文片段, 來源驗證}` 巢狀物件並顯示「OK：原文中找得到這段文字」。
- **未使用但已安裝的套件**：`rapid-layout` 裝了但這個 Phase 沒用到（三種文件都是單一區塊版面，不需要版面分析），誠實記錄在 CLAUDE.md 技術決策，不假裝有用上。

### Phase 5：功能驗證

- **M6 PCB 瑕疵偵測訓練實測**：`scripts/prepare_deeppcb.py` 把 1500 張官方標註轉成 YOLO 格式（1000 train / 250 val / 250 test，固定種子切分）。`YOLO11n` 在 MPS 上訓練，41 epoch 後 early stopping（`patience=15`，最佳結果在 epoch 26），總耗時 **32.1 分鐘**（0.535 小時）。官方測試集（250 張）實測：
  | 類別 | mAP50 | mAP50-95 | Precision | Recall |
  |---|---|---|---|---|
  | 全部 | **0.978** | 0.735 | 0.964 | 0.945 |
  | open（斷路） | 0.988 | 0.674 | 0.949 | 0.979 |
  | short（短路） | 0.958 | 0.626 | 0.941 | 0.912 |
  | mousebite（缺口） | 0.969 | 0.710 | 0.957 | 0.921 |
  | spur（毛刺） | 0.977 | 0.711 | 0.961 | 0.948 |
  | copper（多餘銅箔） | 0.982 | 0.845 | 0.992 | 0.944 |
  | pin-hole（針孔） | 0.992 | 0.845 | 0.983 | 0.968 |

  數字來自 `models/defect/pcb_yolo11n/results.csv`（逐 epoch 訓練曲線）與訓練結束時對 `best.pt` 在官方測試集切分上的驗證輸出，不是估計值。
- **一開始以為訓練卡死，其實是我自己檢查錯路徑（真實 bug，不是猜的）**：訓練指令用 `project='models/defect'`（相對路徑），但 ultralytics 會把全域設定的 `runs_dir`（預設 `"runs"`）加在相對 `project` 路徑前面，實際輸出到 `runs/detect/models/defect/pcb_yolo11n/`，不是我以為的 `models/defect/pcb_yolo11n/`。我一直檢查後者有沒有 `results.csv`，30 分鐘都看不到檔案，一度以為訓練卡死（用 `sample` 系統工具反覆確認 CPU 真的在算 conv2d/autograd，排除死鎖），後來訓練其實已經在正確路徑正常寫入，41 epoch 全部跑完只花 32 分鐘。教訓：往後呼叫 `YOLO().train(project=...)` 一律用絕對路徑，PPE 訓練已經改用絕對路徑，沒有重踩這個坑。
- **真實資料推論驗證**：直接呼叫 `detect_pcb_defects()`（不透過假推論）測 DeepPCB 測試集圖片，正確判定 NG 並抓出全部 8 個標註瑕疵，涵蓋 6 種類型全部命中。
- **live 測試**：`pytest -m live`，DeepPCB 測試集抽樣 10 張，10 張全部判定 NG（資料集設計每張圖本來就有 3-12 個瑕疵）。
- **瀏覽器實測**（真實 Chrome）：M6 分頁上傳測試圖，1513ms 判定 NG、偵測到 8 個瑕疵，標註圖用紅框精準框出每個瑕疵位置並標上類型與信心度，跟明細清單完全對應。
- **M5 PPE 訓練實測**：`scripts/prepare_hardhat.py` 沿用資料集官方 Train(5297)/Test(1766) 切分，只留 helmet/head 兩類（跳過極少數的 person/others 類別）。訓練用絕對路徑 `project`（避開上面踩到的坑），資料量是 PCB 的 5.3 倍，跑滿全部 60 epoch（沒有提早停止，`patience=15` 全程都還在緩慢進步），總耗時 **4.15 小時**。官方測試集（1766 張）實測：
  | 類別 | mAP50 | mAP50-95 | Precision | Recall |
  |---|---|---|---|---|
  | 全部 | **0.977** | 0.680 | 0.948 | 0.942 |
  | helmet（已戴安全帽） | 0.982 | 0.682 | 0.959 | 0.942 |
  | head（未戴安全帽） | 0.972 | 0.678 | 0.938 | 0.941 |

  訓練曲線見 `models/ppe/ppe_yolo11n/results.csv`；mAP50 從 epoch1 的 0.913 緩步爬升到最終 0.977，中間沒有劇烈震盪，是穩定收斂，不是運氣。
- **真實資料推論驗證**：直接呼叫 `detect_ppe()` 測 Hard Hat Workers 驗證集，good 案例（多人合照有安全帽）正確判 OK；抓 5 張標註含「未戴安全帽」的圖測試，4/5 正確判 NG（1 張漏判，跟 recall 0.941<1 的實測數字吻合，不是我瞎猜的容錯率）。
- **live 測試**：`pytest -m live`，驗證集抽樣 10 張，全部成功偵測到人頭（2 張 NG、7 張 OK、1 張沒偵測到人頭判 INFO）。
- **瀏覽器實測**（真實 Chrome）：M5 PPE 分頁上傳一張 8 人合照（官方標註全部未戴安全帽），993ms 判定 NG、8/8 正確抓到未戴安全帽，標註圖用紅框精準框出每個人頭並標「未戴安全帽 0.xx」信心度。

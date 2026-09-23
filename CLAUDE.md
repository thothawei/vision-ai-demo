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

## 目錄結構

```
vision-ai-demo/
├── backend/
│   ├── main.py                 # FastAPI 入口，只負責掛載各模組 router、統一錯誤格式
│   ├── core/
│   │   ├── schemas.py          # 共用回應格式 InspectionResult、ModuleError
│   │   ├── image_io.py         # 讀圖、EXIF 轉正、縮圖、base64
│   │   ├── llm.py              # Ollama / Gemini 抽象層
│   │   └── inspection_log.py   # SQLite 檢驗紀錄
│   ├── modules/
│   │   ├── general/            # M9 開放式辨識
│   │   ├── docs/                # M4 製造文件結構化
│   │   ├── codes/                # M1 追溯碼辨識
│   │   ├── measure/              # M2 計數與尺寸量測
│   │   ├── safety/               # M5 危險區域入侵
│   │   └── inspections/         # 檢驗紀錄查詢 / CSV 匯出
│   └── requirements.txt
├── frontend/index.html         # 分頁式單頁（5 個模組各一頁，M5 有 canvas 畫多邊形危險區域）
├── scripts/make_aruco.py       # 產生 M2 量測用的可列印 ArUco 標記 PDF
├── models/
│   └── yolo/yolo11n.pt         # M5 用，YOLO 官方 release 下載，gitignore
├── tests/
│   ├── conftest.py
│   ├── samples/make_samples.py # 程式生成測試圖（工單、警示標示、GS1條碼、零件、ArUco量測場景），不進版控
│   ├── live_samples/            # pytest -m live 用的真實授權照片，不進版控，來源見 README.md
│   ├── test_modules.py         # M9/M4 API 契約、SQLite（假 LLM）
│   ├── test_llm.py             # LLM 抽象層錯誤處理（假 LLM / 假連線）
│   ├── test_codes.py            # M1：GS1 解析、效期判斷
│   ├── test_measure.py          # M2：計數分離、量測精度、OK/NG 公差
│   ├── test_safety.py           # M5：多邊形入侵邏輯（假偵測結果）
│   ├── test_live_ollama.py     # 真打 Ollama，pytest -m live
│   └── test_live_safety.py      # 真打 YOLO + 真人照片，pytest -m live
├── docs/
│   ├── manufacturing-ai-plan-prompt.md
│   └── licenses.md
├── data/                       # SQLite，gitignore
└── .env / .env.example
```

## 環境需求

- Python 3.11（用 `uv venv --python 3.11` 建立，系統原生無 3.11）
- [Ollama](https://ollama.com) 已安裝並執行，模型 `qwen3.5:9b`（`ollama pull qwen3.5:9b`，約 6.6GB）
- Tesseract OCR（macOS: `brew install tesseract tesseract-lang`，M4 OCR 模式與比較用）
- YOLO11n 權重（`models/yolo/yolo11n.pt`，M5 用；`python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"` 下載後手動搬過去，5.6MB）
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
pytest                                  # 單元測試，假 LLM，約 1 秒
pytest -m live -s                       # 真打本機 Ollama，需先 ollama serve，約 1 分鐘
```

## 已知限制

- **Gemini 免費層速率限制**：`LLM_ENGINE=gemini` 時，`gemini-3.6-flash` 免費層實測 RPM=5、RPD=20，只當備援，不是核心路徑。
- **Tesseract OCR 誤判**：M4 的 OCR 模式，Tesseract 會把數字誤讀（實測：`0915` 被讀成 `0215`），是已知弱點；端到端模式（AI 直接讀圖）準確度較高但較慢。
- **本機模型延遲**：`qwen3.5:9b` 在 M1 Pro 上單次辨識約 8-20 秒，比 Gemini 雲端 API 慢，是離線換取的代價。
- **16GB 記憶體**：同時載入 Ollama 模型與之後 Phase 3+ 的 PyTorch 模型會吃緊，模型皆採延遲載入（首次呼叫才載入）。
- **M2 計數對背景要求高**：假設零件是畫面中的少數像素、跟背景有明顯亮度反差；零件間距小於約 25px（局部極大值種子的搜尋半徑）時仍可能分不開，見 `_binarize_foreground_minority` 的說明。
- **M2 量測精度**：正視角下實測誤差約 0.3-0.6mm（50mm 零件上約 1%），假設待測物與 ArUco 標記共平面，手機斜角拍攝會讓誤差變大；預設公差 1.0mm。
- **M5 只做單張圖片**：短影片逐幀抽樣留到 Phase 5 跟 PPE 一起做，不是遺漏。

## 待辦（Phase 進度）

- [x] Phase 0：查證套件/模型/資料集授權，寫入 `docs/licenses.md`；確認 Mac 安裝風險（PaddleOCR 在 py3.11 相依衝突、OpenCV 三套件共用 cv2 命名空間、16GB 記憶體限制）。
- [x] Phase 1：Python 3.11 venv 重建、目錄重構（`core/`、`modules/<模組>/`）、共用回應格式、LLM 抽象層（Ollama 預設／Gemini 備援）、SQLite 檢驗紀錄 + 查詢/CSV API、前端改分頁式。原有兩功能搬進 M9（開放式辨識，prompt 改製造業情境）／M4（文件結構化，欄位改製造業情境）且已用真實 Ollama 模型與真實瀏覽器驗證可用。
- [x] Phase 2：M1 追溯碼（zxing-cpp + GS1 解析 + 效期判斷）、M2 計數量測（OpenCV watershed 分離相黏零件 + ArUco 透視校正量測）、M5 危險區域入侵（YOLO11n person 偵測 + 前端 canvas 畫多邊形）。全部免訓練，已用真實資料（含真人照片）與真實瀏覽器驗證可用。
- [ ] Phase 3：M3 異常檢測（Anomalib PatchCore + MVTec AD，實測 AUROC）。
- [ ] Phase 4：M4 換成 RapidOCR + Pydantic schema。
- [ ] Phase 5：M6 NEU-DET/DeepPCB、M5 PPE（需訓練，附 Colab notebook）。
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

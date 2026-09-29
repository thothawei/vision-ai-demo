# 製造業視覺品檢平台（vision-ai-demo）— 開發規則

## 專案目標

本機執行的製造業視覺品檢平台，涵蓋台中／中科常見情境（工具機與精密機械、手工具、螺絲扣件、自行車零件、金屬加工/CNC、PCB 與電子、醫材與藥品包裝）。所有辨識結果走共用 JSON 結構並寫入 SQLite 檢驗紀錄，供品檢看板與 `manufacturing-erp`（ASP.NET Core + SQL Server）串接。

- 產品化規劃：`docs/product-hardening-plan.md`（Phase 16–24，逐 Phase 開工前回報、完成後回報，一次一個 Phase）。
- 技術決策與測試紀錄（Phase 0–15）：`docs/dev/decisions.md`、`docs/dev/test-log.md`、`docs/dev/progress.md`。
- 使用者／管理者文件：`docs/user-guide.md`、`docs/admin-guide.md`、`docs/known-limitations.md`。
- 套件與資料集授權：`docs/licenses.md`。

## 硬性規則

1. 只用免費工具（含條件見規劃文件 1.1 節）；找不到免費方案的功能跳過，寫進 README「未納入功能」，不寫假的 stub。
2. 核心功能完全離線（本機 Ollama）；Gemini 免費層只當可選備援（`LLM_ENGINE=ollama|gemini`）。
3. 套件/模型/資料集安裝前查官方來源確認版本、授權與費用，寫進 `docs/licenses.md`，不憑記憶填版本號。
4. 非商用授權資料集（如 MVTec AD 的 CC BY-NC-SA）在文件註明「僅供學習與技術展示，不得用於商業產線」。
5. 分階段執行，每個 Phase 結束回報實際測試結果，等確認再進下一階段。
6. 測試結果不可捏造：準確率/推論時間/截圖只記錄實際跑出的數字，沒跑過就寫「未測試」。
7. 大檔（權重、資料集、訓練輸出、SQLite）放 `models/`、`data/`、`runs/`，已 gitignore。commit 前 grep 掃過沒有 API key。
8. Apple Silicon Mac：PyTorch 用 `mps`，不支援時退回 `cpu`。Python 3.11。
9. 向下相容：舊 `data/inspections.db` 自動 migrate；`InspectionResult` 只加選填欄位；既有 API 路徑保留；既有測試全過。

## 用詞規範

本專案是正式產品。程式註解、文件、commit message **不可**出現把系統定位成個人作品或示範的用語（禁用詞清單見 `scripts/check_wording.py` 的 `BANNED`），一律用「系統」「平台」「本產品」。`python scripts/check_wording.py` 必須為 0 筆。唯一例外：醫學影像分類必須保留「僅供技術展示，非醫療診斷用途」警語。模組／API 代號（如 `medical_pneumonia_demo`、`/pneumonia-demo`）為相容性識別字，不改。

## 開發時必須記得的陷阱

- **ultralytics `project` 一律用絕對路徑**：相對路徑會被 `runs_dir` 加前綴，權重實際存到 `runs/detect/models/...`。
- **PatchCore 固定用 CPU**：MPS 上 coreset 逐元素 `.item()` 同步，極慢。
- **anomalib 自訂類別要關內建正規化**：`Patchcore(post_processor=PostProcessor(enable_normalization=False, enable_thresholding=False))`，否則分數被裁成 0/1、門檻退化成 1.0。
- **anomalib `TorchInferencer` 需 `TRUST_REMOTE_CODE=1`**：只用於載入自己訓練的權重。
- **`CORS_ORIGINS` 啟動時讀死進中介層**，改 `.env` 要重啟；`API_KEYS`／`MAX_UPLOAD_MB` 每次請求重讀。測試改 `CORS_ORIGINS` 無效（`app` 是全 session 單例）。
- **FastAPI 對未宣告的 query 參數靜默忽略**：`core/batch_dispatch.py` 與 `modules/batch/router.py` 是兩份分開的參數列表，加新動作參數要兩邊都改（M12 漏改過）。
- **`extract_defect_labels()` 是白名單制**：新辨識模組要在 `core/inspection_log.py` 用 `@_extractor("模組名")` 補抽取函式，否則判 NG 也不進 NG 柏拉圖。目前 `assembly`／`colordiff`／`codes`／`measure` 尚未補（Phase 17 處理）。
- **`RAW_IMAGE_CTX` 一個請求只記最後一張圖**（`load_image()` 每次覆寫）；雙圖模組（M10）不可依賴它存圖（Phase 17 處理）。
- **`load_image()` 的 except 是刻意放寬成 `Exception`**：ultralytics monkeypatch `PIL.Image.open` 後，壞檔會丟 `ModuleNotFoundError`，窄 except 攔不到會變 500。
- **測試必須隔離全域檔案路徑**：`INSPECTION_DB`、`INSPECTION_IMAGES_DIR`、`GOLDEN_SAMPLES_DIR` 等由 `tests/conftest.py` 的 `client` fixture 隔離；新增任何寫檔的 module-level 路徑都要可用 env 覆寫並補隔離。
- **背景擬合測試不要真起 `_worker_loop` 執行緒**：呼叫 `_process_one(name)`，否則殘留 daemon thread 會搶跑後面測試的真擬合。
- **單元測試不觸發 `import ultralytics`，掩蓋了 PIL patch 類問題**：涉及圖片讀取的改動要用真實伺服器至少測一次壞檔。
- **Playwright 點 canvas 用 `locator.click(position=...)`**，不要用絕對座標的 `page.mouse.click`（超出 viewport 不會自動捲動）。
- **Mermaid 節點文字含 `{}` 要用引號並改圓括號**；改架構圖後手動重新渲染 `docs/architecture.png`。
- **本機 Ollama 模型延遲 8–20 秒**；CI／單元測試一律用假 LLM，真打標 `live`。

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
│   │   ├── seven_segment.py     # M7 七段顯示器分段判讀（純 OpenCV）
│   │   ├── gauge.py             # M7 指針錶角度偵測與讀值換算（純 OpenCV）
│   │   ├── context.py           # Phase 9：追溯資訊／原圖 bytes 的 contextvar
│   │   ├── api_auth.py          # Phase 10：/api/inspections* 的 X-API-Key 驗證
│   │   ├── webhook.py           # Phase 10：NG 非同步通知 + 失敗重試佇列
│   │   ├── batch_dispatch.py    # Phase 11：批次上傳的「動作」對照表
│   │   ├── anomaly_training.py  # Phase 12：M3 自訂類別 zip 上傳/背景排隊擬合/門檻 registry
│   │   └── inspection_log.py   # SQLite 檢驗紀錄（Phase 9 起含追溯欄位、存圖、複判、看板統計、webhook_queue）
│   ├── schemas/
│   │   ├── documents.py         # M4 工單/出貨單/進料檢驗報告 Pydantic schema
│   │   ├── nameplate.py         # M7 銘牌欄位 Pydantic schema
│   │   └── shipping_label.py    # M12 出貨標籤欄位 Pydantic schema
│   ├── modules/
│   │   ├── general/            # M9 開放式辨識
│   │   ├── docs/                # M4 製造文件結構化
│   │   ├── anomaly/              # M3 外觀瑕疵異常檢測
│   │   ├── codes/                # M1 追溯碼辨識
│   │   ├── measure/              # M2 計數與尺寸量測
│   │   ├── safety/               # M5 危險區域入侵 + PPE 安全帽偵測（Phase 11 起含短影片端點）
│   │   ├── defect/               # M6 PCB 瑕疵偵測
│   │   ├── nameplate/            # M7 銘牌／七段顯示器／指針錶
│   │   ├── medical/              # M8 包裝追溯碼檢核／醫學影像分類展示
│   │   ├── inspections/         # 檢驗紀錄查詢 / CSV 匯出 / 複判 / 看板統計 / 圖片
│   │   ├── batch/                # Phase 11：POST /api/batch/{action} 批次上傳
│   │   ├── assembly/             # Phase 13：M10 組裝防呆／黃金樣本比對
│   │   ├── colordiff/            # Phase 13：M11 烤漆/陽極色差 ΔE
│   │   └── shipping/             # Phase 14：M12 出貨標籤 vs 工單比對
│   └── requirements.txt
├── frontend/
│   ├── index.html               # 分頁式單頁（16 個分頁，15 個辨識分頁多選批次上傳+拍照，M5/M10/M11 有 canvas 畫框，⑯ 品檢看板用 Chart.js）
│   └── vendor/chart.min.js      # Chart.js 4.5.1（MIT），離線優先不用 CDN
├── scripts/
│   ├── make_aruco.py           # 產生 M2 量測用的可列印 ArUco 標記 PDF
│   ├── train_anomaly.py        # 擬合 M3 PatchCore（train_one=demo 類別／train_custom=Phase 12 自訂類別）
│   ├── export_reviewed.py      # Phase 12：已複判紀錄 → YOLO／MVTec 格式，給標註工具校正用
│   ├── prepare_deeppcb.py      # DeepPCB 官方標註 → YOLO 格式（M6）
│   ├── prepare_hardhat.py      # Hard Hat Workers Pascal VOC → YOLO 格式（M5 PPE）
│   ├── train_medmnist.py       # M8-2 PneumoniaMNIST 小型 CNN 訓練，含類別權重
│   ├── watch_folder.py         # Phase 11：資料夾監控，新圖自動辨識、搬到 done/error
│   └── capture_screenshots.py  # Playwright 產生 README 辨識畫面截圖（16 張），含 M10/M11 canvas 互動
├── notebooks/
│   ├── train_pcb_defect.ipynb  # M6 訓練，Colab GPU 版（重用 scripts/prepare_deeppcb.py）
│   └── train_ppe.ipynb         # M5 PPE 訓練，Colab GPU 版
├── models/                     # 權重（gitignore）：yolo/、anomaly/<category>/、defect/、ppe/、medical/
├── tests/                      # pytest：每模組一個 test_*.py（單元測試用假 LLM/YOLO/PatchCore），test_live_*.py 真打模型（-m live）
│   ├── conftest.py             # client fixture 隔離 data 路徑
│   ├── samples/make_samples.py # 程式生成測試圖（不進版控）
│   └── live_samples/           # live 測試用授權照片（不進版控）
├── docs/                       # walkthrough／user-guide／admin-guide／known-limitations／licenses／erp-integration，dev/（決策、測試紀錄、規劃）
├── data/                       # inspections.db、images/、golden_samples/、mvtec_ad/（gitignore）
├── LICENSE  CHANGELOG.md  pyproject.toml  pytest.ini
└── .env / .env.example
```

## 啟動與測試

```bash
cd ~/Documents/vision-ai-demo
ollama serve &                          # 若尚未執行
source venv/bin/activate
cd backend && uvicorn main:app --reload # http://127.0.0.1:8000

python tests/samples/make_samples.py    # 產生測試圖（需要，未進版控）
pytest                                  # 單元測試（假 LLM/YOLO/PatchCore）
pytest -m live -s                       # 真打本機模型，需 ollama serve 與權重
python scripts/check_wording.py         # 用詞檢查，必須 0 筆
```

環境需求與完整安裝步驟見 `README.md`「安裝」；`.env` 設定見 `docs/admin-guide.md`。

## 待辦（Phase 進度）

- [x] Phase 0–15：辨識功能、看板、ERP 介面、產線輸入、自有資料導入、M10–M12（細節見 `docs/dev/progress.md`）。
- [x] Phase 16：產品定位、授權、文件重整（本次）。
- [ ] Phase 17：模組註冊表、請求範圍資料、設定集中、前端拆分與分類導覽、logging。
- [ ] Phase 18：使用者、角色、稽核。 [ ] Phase 19：主檔與檢驗配方。 [ ] Phase 20：SPC 與報表。
- [ ] Phase 21：模型與資料治理。 [ ] Phase 22：可靠性與可觀測性。 [ ] Phase 23：真實驗證與 CI。 [ ] Phase 24：容器化與 v1.0.0。

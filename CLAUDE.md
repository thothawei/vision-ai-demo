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
- **新增辨識動作只改 `core/registry.py` 一處**：`ActionSpec`（動作、module、分頁、分類、參數模型、缺陷抽取規則）；批次 API、`GET /api/modules`、柏拉圖、前端導覽都由它衍生。參數模型繼承 `_Params`（`extra="forbid"`），批次 API 對未知參數回 422（FastAPI 對未宣告的參數會靜默忽略，M12 曾因此漏傳）。`tests/test_registry.py` 會擋下「會判 NG 卻沒有 defect_extractor」的動作。
- **缺陷抽取規則寫在 `core/defect_extractors.py`**，在查詢時才對 `summary_json` 執行，所以規則補上後歷史紀錄也會反映；但 summary 沒存的資訊補不回來（例如尺寸超差是 Phase 17 起才寫入 `超差項目`，之前的量測 NG 紀錄不會進柏拉圖）。
- **請求範圍資料在 `core/request_scope.py`**（追溯資訊、request_id、依 role 分開的圖片：raw／golden／reference）。`load_image(bytes, role="raw")`；同 role 重複載入以最後一次為準，批次每張前會 `reset_images()`。雙圖模組要自己 `request_scope.add_image()`（M10 的黃金樣本從磁碟讀，見 `assembly/service.py`）。
- **`load_image()` 的 except 是刻意放寬成 `Exception`**：ultralytics monkeypatch `PIL.Image.open` 後，壞檔會丟 `ModuleNotFoundError`，窄 except 攔不到會變 500。
- **測試必須隔離全域檔案路徑**：`INSPECTION_DB`、`INSPECTION_IMAGES_DIR`、`GOLDEN_SAMPLES_DIR` 等由 `tests/conftest.py` 的 `client` fixture 隔離；新增任何寫檔的 module-level 路徑都要可用 env 覆寫並補隔離。
- **背景擬合測試不要真起 `_worker_loop` 執行緒**：呼叫 `_process_one(name)`，否則殘留 daemon thread 會搶跑後面測試的真擬合。
- **單元測試不觸發 `import ultralytics`，掩蓋了 PIL patch 類問題**：涉及圖片讀取的改動要用真實伺服器至少測一次壞檔。
- **設定一律走 `core/settings.py`（pydantic-settings）**，禁止在 backend 直接 `os.environ.get`（`tests/test_settings.py` 會檢查）。「即時」設定用 `get_settings()`（每次重讀環境變數與 `.env`），「需重啟」用 `startup_settings()`；新增設定後執行 `python scripts/gen_settings_doc.py` 更新管理者手冊的表。
- **測試不可讀到真實 `.env`**：設定會讀專案根目錄 `.env`（含真實 Gemini key），`tests/conftest.py` 的 autouse fixture 已把 `env_file` 設為 None；新增絕對不能拿真 key 的測試也要依賴這個隔離。
- **日誌不記 API key 與圖片內容**：用 `logging.getLogger("vision.xxx")`，每行帶 `request_id`；模型載入用 `core.logging_setup.log_model_load`。uvicorn 自己的 access log 會印完整網址（含 `?api_key=`），那是已知限制。
- **前端是原生 ES modules（不用建置工具）**：`frontend/js/common.js`（共用）、`rect-canvas.js`、`tabs/<分頁>.js`（各分頁綁定）、`nav.js`（依 `/api/modules` 建左側導覽）。分頁的表單 HTML 仍寫在 `index.html` 的 `id="panel-<tab>"`；註冊表有、HTML 沒有的分頁會自動產生說明用的預設面板。
- **所有端點都要驗證**：路由層 `Depends(auth.require_login)`（登入使用者或 API key），需要更高權限的端點在函式參數加 `Depends(require_role("qc"|"admin", allow_api_key=...))`（見 `core/auth.py`）。API key 預設只能辨識與唯讀；複判與管理一律需要具名使用者。新增端點要決定它的最低角色，不要只靠 router 層級的 `require_login`。
- **session 只存 user_id，每個請求重讀使用者**（停用／改角色立即生效）；`SESSION_SECRET` 未設或短於 32 字元 main.py 會拒絕啟動，測試在 `tests/conftest.py` 開頭用 `os.environ.setdefault` 設好（必須早於任何 `import main`）。測試用 `client`（API key）、`admin_client`／`qc_client`／`operator_client`（登入 session）；整個檔案都需要 admin 時，在檔內覆寫 `client` fixture 為 `admin_client`（見 `test_assembly.py`）。
- **稽核**：會改變設定或他人資料的操作，都在 router 層呼叫 `audit.record(principal.actor, action, target_type, target_id, before, after)`；稽核內容不可含密碼或雜湊。`reviewer`、`created_by` 一律取自登入者，不信任請求 body。
- **寫入請求的 Origin 檢查**（`main.py` 的 `csrf_origin_middleware`）：瀏覽器帶的 Origin 必須與 Host 相同，測試客戶端沒有 Origin 所以不受影響；反向代理不可改寫 Host。
- **配方檢驗**（`core/recipes.py`）：配方版本不可變（改參數＝新版本），步驟參數用註冊表的 Pydantic 模型驗證；`ActionSpec.handler` 不為 None 的動作都可入配方，`batch_enabled=False` 只是不開放批次 API（assembly、colordiff）。每一步各自 `record_result`，靠 `request_scope.run_id` 關聯 run，每步前 `reset_images()`。合併判定在 `recipes.combine()`：inspection 類動作 NG→NG、出錯或 INFO→INFO，info 類動作不計。run 視角統計的最終判定由各步驟的複判動態合併（`get_run_stats`），不要把最終判定存死在 run 上。
- **臨時檢驗標記**在 `inspection_log.log_inspection` 寫入（`adhoc`：沒有工單或工單不在主檔），不要另外在各模組算。`inspections` 補進舊 db 的欄位型別由 `_COLUMN_TYPES` 決定（預設 TEXT；`run_id`、`adhoc` 是 INTEGER）。
- **主檔寫入權**：`require_role("admin", allow_api_key=True, api_key_names=("erp",))` 只讓名為 erp 的 API key 推送；其他 key 仍是唯讀。
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
│   │   ├── request_scope.py     # Phase 17：請求範圍資料（追溯資訊、request_id、依 role 分開的圖片）
│   │   ├── master.py            # Phase 19：料號與工單（含 bulk-upsert）
│   │   ├── recipes.py           # Phase 19：配方版本、依配方執行、合併判定、run 統計
│   │   ├── auth.py              # Phase 18：Principal、require_login／require_role（session 或 API key）
│   │   ├── users.py             # Phase 18：本機帳號、argon2id、登入失敗鎖定
│   │   ├── audit.py             # Phase 18：稽核紀錄
│   │   ├── api_auth.py          # Phase 10：/api/inspections* 的 X-API-Key 驗證
│   │   ├── webhook.py           # Phase 10：NG 非同步通知 + 失敗重試佇列
│   │   ├── batch_dispatch.py    # Phase 11：批次上傳執行核心（動作與參數模型來自 registry）
│   │   ├── registry.py          # Phase 17：辨識動作註冊表（單一真實來源）
│   │   ├── defect_extractors.py # Phase 17：NG 柏拉圖的缺陷標籤抽取規則
│   │   ├── settings.py          # Phase 17：pydantic-settings 集中設定（即時／需重啟）
│   │   ├── logging_setup.py     # Phase 17：key=value 日誌、request_id、模型載入計時
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
│   ├── index.html               # 版面與各分頁表單（16 個功能分頁＋看板＋使用者／稽核；導覽由 /api/modules 依角色產生）
│   ├── login.html               # 登入頁（公開，不含任何密鑰）
│   ├── css/app.css
│   ├── js/                      # ES modules：main.js、nav.js、catalog.js、common.js、rect-canvas.js、tabs/*.js
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

首次啟動前要在 `.env` 設 `SESSION_SECRET`（≥32 字元，否則拒絕啟動），並用 `python scripts/create_admin.py --username admin --display-name 系統管理員` 建立第一個管理員。

環境需求與完整安裝步驟見 `README.md`「安裝」；`.env` 設定見 `docs/admin-guide.md`。

## 待辦（Phase 進度）

- [x] Phase 0–15：辨識功能、看板、ERP 介面、產線輸入、自有資料導入、M10–M12（細節見 `docs/dev/progress.md`）。
- [x] Phase 16：產品定位、授權、文件重整。
- [x] Phase 17：模組註冊表、請求範圍資料、設定集中、前端拆分與分類導覽、logging。
- [x] Phase 18：使用者、角色、稽核。 [x] Phase 19：主檔與檢驗配方。 [ ] Phase 20：SPC 與報表。
- [ ] Phase 21：模型與資料治理。 [ ] Phase 22：可靠性與可觀測性。 [ ] Phase 23：真實驗證與 CI。 [ ] Phase 24：容器化與 v1.0.0。

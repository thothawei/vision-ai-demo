# Claude Code 任務：vision-ai-demo 第二輪規劃（Phase 9–15）

> **使用方式**：在 `~/Documents/vision-ai-demo` 開 Claude Code，輸入：
> 「請讀 `docs/next-phase-gap-plan-prompt.md`，從 Phase 9 的『開工前回報』開始執行。」
>
> 前一輪（M1–M9、Phase 0–8）已全部完成，細節見 `CLAUDE.md`、`README.md`、`docs/manufacturing-ai-plan-prompt.md`。
> 本輪目標：從「13 個辨識分頁的 Demo」補到「**可以上產線、可以接 ERP 的品檢系統**」。

---

## 1. 給 Claude Code 的執行規則（必讀）

1. **沿用 `CLAUDE.md`「硬性規則」1–9 條**，全部有效：只能用免費工具、核心離線、安裝前查證版本與授權、測試數字不可捏造、大檔不進版控、Apple Silicon 16GB。
2. **本文件寫到的套件/資料集授權是規劃時的認知，不是查證結果。** 每個 Phase 開工前都要到官方 GitHub／PyPI／官網重新查證，寫進 `docs/licenses.md`；查證結果跟本文件不同，以查證為準並在回報中指出差異。查不到免費方案就跳過，寫進 README「未納入功能」。
3. **一次只做一個 Phase**。流程固定：
   - **開工前回報**（先不寫程式）：要新增的套件＋查證版本/授權、預計新增/修改的檔案清單、設計取捨、風險。等我確認。
   - **實作**：程式 + 單元測試 + （有需要時）live 測試。
   - **完成回報**：做了什麼、驗收條件逐條打勾（附實測數字/指令輸出）、遇到的問題、沒做到的部分。等我確認再進下一個 Phase。
4. **向下相容**：
   - 舊的 `data/inspections.db` 必須能自動 migrate（`ALTER TABLE ADD COLUMN`），不能要求刪庫。
   - `core/schemas.py` 的 `InspectionResult` 只能加選填欄位，不能改名/刪欄位。
   - 既有 62 項單元測試必須全過；既有 13 個分頁功能不能壞。
5. **每個 Phase 結束要更新 `CLAUDE.md`** 的四個章節：技術決策與理由（Phase N）、已知限制、待辦（Phase 進度）、測試紀錄（Phase N），並 commit（commit 前 grep 掃 API key）。
6. 新模型一律延遲載入（首次呼叫才載入），缺權重時回傳清楚錯誤「請先執行 scripts/xxx.py」。

---

## 2. 現況程式碼定位（先讀這些檔案）

| 用途 | 檔案 / 函式 | 現況 |
|---|---|---|
| 共用回應格式 | `backend/core/schemas.py` → `InspectionResult`、`ModuleError` | 欄位：module, verdict(OK/NG/INFO), items, annotated_image, engine, elapsed_ms, inspection_id |
| 檢驗紀錄 | `backend/core/inspection_log.py` → `record_result()`、`log_inspection()`、`query_inspections()`、`to_csv()` | 表 `inspections` 只有 id, created_at, module, verdict, engine, elapsed_ms, summary_json；**不存圖、沒有追溯欄位** |
| 紀錄查詢 API | `backend/modules/inspections/router.py` | `GET /api/inspections`、`GET /api/inspections/export.csv`；**前端沒有任何地方呼叫** |
| 所有模組寫紀錄的入口 | 各 `backend/modules/*/service.py` 都呼叫 `record_result(module, verdict, items, engine, started, annotated_data_url)` | 共 13 個呼叫點（general/docs×2/anomaly/defect/safety×2/measure×2/codes/nameplate/medical×2） |
| 讀圖 | `backend/core/image_io.py` → `load_image(bytes)` | 已有空檔/非圖片檢查，**沒有檔案大小上限** |
| App 入口 | `backend/main.py` | CORS `allow_origins=["*"]`；前端用 StaticFiles 掛在 `/` |
| 前端 | `frontend/index.html`（約 717 行，純 HTML/JS） | 13 個 `.tab-btn[data-tab=...]`；共用函式 `setupPreview()`、`renderResult()`、`callApi()` |
| 截圖腳本 | `scripts/capture_screenshots.py`（Playwright） | 新分頁要加進去 |
| CI | 無 `.github/` | — |

---

## 3. 缺口總覽（為什麼要做這一輪）

| # | 缺口 | 對應 Phase |
|---|---|---|
| G1 | 檢驗紀錄 API 存在但前端沒畫面，看不到良率、NG 柏拉圖 | 9 |
| G2 | 紀錄缺工單/料號/批號/站別/操作員，也不存原圖與標註圖 → 無法追溯、無法再訓練 | 9 |
| G3 | 沒有人工複判（AI 判 NG → 品檢員改判 OK） | 9 |
| G4 | ERP 串接沒有認證、增量拉取、規格文件 | 10 |
| G5 | 只能單張上傳；沒有批次、資料夾監控、影片抽幀（CLAUDE.md 已記錄 M5 影片未做）、相機拍照 | 11 |
| G6 | 無法用自家良品重新擬合 M3、沒有門檻調校、誤判資料無法回流訓練 | 12 |
| G7 | 台中常見但未做、且有免費方案：組裝防呆、色差、出貨標籤比對、跌倒偵測；M8-1 比對無容錯 | 13 |
| G8 | 只能在 Mac 跑；無 ONNX/OpenVINO、Docker、CI、CPU-only 效能數據；上傳無防護 | 10, 14 |
| G9 | M7 七段顯示器/指針錶、M2 計數只驗證過合成圖 | 14 |
| G10 | AGPL-3.0／非商用資料集的「導入公司」風險沒寫清楚 | 14 |
| G11 | 缺架構圖與面試 Demo 腳本 | 15 |

優先順序：**P0 = Phase 9、10**（最能證明「AI + ERP」）→ P1 = 11、12 → P2 = 13、14 → P3 = 15。

---

## 4. Phase 9：檢驗紀錄強化 + 品檢看板 + 人工複判（P0）

### 目標
每筆辨識都能追溯到工單/料號/批號、保留原圖，品檢員可以複判，主管可以看良率與 NG 原因。

### 實作要點

**4.1 資料表 migration**（`backend/core/inspection_log.py`）
- `inspections` 新增欄位（全部可 NULL）：
  `work_order, part_no, lot_no, station, operator, image_path, annotated_path, review_verdict, reviewer, reviewed_at, review_note`
- `_connect()` 時用 `PRAGMA table_info(inspections)` 檢查，缺哪個欄位就 `ALTER TABLE ADD COLUMN`。
- 新增索引：`(work_order)`、`(part_no, created_at)`。

**4.2 追溯欄位怎麼傳到 `record_result()`**（開工前回報要說明選哪個方案）
- 建議方案 A（改動最小）：前端每次呼叫 API 帶 HTTP header `X-Work-Order / X-Part-No / X-Lot-No / X-Station / X-Operator`（值用 `encodeURIComponent` 處理中文），`main.py` 加 middleware 讀 header 存進 `contextvars`，`record_result()` 從 contextvar 取值。**不用改 13 個 service 的函式簽名。**
- 方案 B：每個 router 加 `Form` 選填欄位一路傳進 service。改動大，但比較顯式。
- 原圖保存：同理，在 `core/image_io.load_image()` 把原始 bytes 放進 contextvar，`record_result()` 需要時取出存檔。若選別的做法要說明理由。

**4.3 存圖**
- 設定 `.env`：`SAVE_IMAGES=true|false`（預設 true），`.env.example` 同步更新。
- 路徑：`data/images/YYYY-MM-DD/<inspection_id>_raw.<ext>`、`<inspection_id>_annotated.png`（annotated 由 `annotated_image` 的 data URL 解碼）。
- 確認 `data/images/` 在 `.gitignore` 內。

**4.4 新 API**（`backend/modules/inspections/router.py`）
- `GET /api/inspections` 新增篩選參數：`work_order, part_no, lot_no, station`。
- `PATCH /api/inspections/{id}/review`：body `{review_verdict: "OK"|"NG", reviewer, review_note}`，寫入 `reviewed_at`。
- `GET /api/inspections/{id}/image?kind=raw|annotated`：回傳圖檔，不存在回 404。
- `GET /api/inspections/stats?group_by=module|day|defect&date_from=&date_to=&module=`：回傳件數、NG 數、良率；`defect` 分組需要各模組從 `summary` 抽出缺陷類別（例如 defect 模組的瑕疵類型、ppe 的 head、anomaly 的 NG），寫成一個 `extract_defect_labels(module, summary)` 對照函式，沒有缺陷類別的模組回 `[]`。
- `to_csv()` 補上新欄位。
- 「最終判定」= `review_verdict` 有值用它，否則用 AI `verdict`；stats 同時回傳 AI 判定與最終判定的良率，以及「AI 與人工一致率」（只算有複判的紀錄）。

**4.5 前端**（`frontend/index.html`）
- 所有分頁上方共用一列「追溯資訊」：工單號/料號/批號/站別/操作員，值存 `localStorage`（try/catch 包起來），`callApi()` 自動帶 header。
- 新增第 14 個分頁「⑭ 品檢紀錄與看板」：
  - 表格：篩選（模組/判定/日期/工單/料號）、點列展開看原圖與標註圖、「複判」按鈕（改判 OK/NG + 備註）、匯出 CSV 按鈕。
  - 看板：每日良率折線、NG 原因柏拉圖（長條 + 累積百分比線）、各模組件數、AI/人工一致率。
  - 圖表庫：**Chart.js**（查證版本與授權；放 `frontend/vendor/` 或 CDN，說明取捨——離線優先建議放 vendor）。

### 要新增/修改的檔案（預期）
`backend/core/inspection_log.py`、`backend/core/image_io.py`、`backend/core/context.py`（新，contextvar）、`backend/main.py`、`backend/modules/inspections/router.py`、`frontend/index.html`、`frontend/vendor/`（新）、`.env.example`、`.gitignore`、`tests/test_inspections.py`（新）、`scripts/capture_screenshots.py`、`README.md`、`CLAUDE.md`、`docs/licenses.md`

### 驗收條件
- [ ] 用 Phase 8 留下的舊 `inspections.db` 啟動，自動補欄位，舊資料可查詢（寫測試：先建舊 schema 的 db 再開）
- [ ] 帶追溯 header 呼叫任一模組 → 紀錄有 work_order 等欄位；不帶 header 也正常
- [ ] `SAVE_IMAGES=true` 時原圖/標註圖存到正確路徑，`/image` API 取得到；`false` 時不存
- [ ] review API：改判後 `review_verdict/reviewer/reviewed_at` 正確；非法值回 422
- [ ] stats：用固定假資料驗證良率、柏拉圖數字、一致率計算正確
- [ ] CSV 含新欄位，Excel 開中文不亂碼
- [ ] 前端：實際在瀏覽器跑一次「輸入工單 → 辨識 → 看板出現該筆 → 複判 → 良率變化」，截圖存 `docs/screenshots/14_dashboard.png`
- [ ] 既有 62 項單元測試全過

---

## 5. Phase 10：ERP 串接介面 + 基本資安（P0）

### 目標
`manufacturing-erp`（ASP.NET Core + SQL Server）可以安全、不重複地拉取檢驗紀錄。

### 實作要點
- **API Key**：`.env` 設 `API_KEYS=erp:<key>,frontend:<key>`；`/api/inspections*` 需要 `X-API-Key`。本機前端的處理方式（localhost 豁免或內嵌 frontend key）在開工前回報說明取捨。辨識 API 是否也要驗證，一併說明。
- **增量拉取**：`GET /api/inspections?since_id=<n>&limit=` 回傳 `id > n`，依 id **升冪**排序（跟現有預設降冪不同，要明確區分），ERP 端記住最後一筆 id 即可。
- **複判也要同步**：新增 `GET /api/inspections/reviews?since=<ISO時間>`，讓 ERP 取得「事後被改判」的紀錄（`since_id` 抓不到舊紀錄的更新）。
- **選配 Webhook**：`.env` 設 `ERP_WEBHOOK_URL`，NG 時非同步 POST 精簡 JSON；失敗寫入 SQLite `webhook_queue` 表，背景重試（上限次數），**不能擋住辨識回應**。未設定就完全不啟用。
- **資安收斂**：
  - CORS 改 `.env` 的 `CORS_ORIGINS` 白名單，預設只允許 `http://127.0.0.1:8000,http://localhost:8000`
  - 上傳大小上限 `MAX_UPLOAD_MB`（預設 20），超過回 413
  - 不信任副檔名/Content-Type，一律用 Pillow 實際開檔驗證（`load_image` 已有，確認所有模組都經過它；影片另外處理見 Phase 11）
- **文件** `docs/erp-integration.md`：
  - 認證方式、`since_id` 輪詢流程（含 Mermaid 時序圖）
  - 欄位對照表：本系統欄位 → 建議的 ERP 品檢單欄位
  - C# 範例：`HttpClient` 帶 `X-API-Key` 輪詢 `since_id`，寫入 SQL Server（用參數化查詢；SQL Server Express/Developer 版免費，查證後註明）
  - 匯出 `docs/openapi.json`（FastAPI 的 `/openapi.json`）

### 驗收條件
- [ ] 沒帶/帶錯 key → 401；帶對 → 200
- [ ] `since_id`：連續兩次輪詢不重複、不漏（測試：插入 5 筆，since_id=2 回 3 筆升冪）
- [ ] reviews 端點能抓到舊紀錄的複判更新
- [ ] webhook：用 pytest 起假接收端驗證 NG 有送、OK 不送、接收端掛掉時辨識 API 仍正常回應且寫入重試佇列
- [ ] 超過大小回 413；副檔名 .png 但內容不是圖片回 400
- [ ] CORS：非白名單 Origin 不會拿到 `Access-Control-Allow-Origin`
- [ ] `docs/erp-integration.md` 的 C# 範例至少能通過 `dotnet build`（若本機沒有 .NET SDK，照實寫「未編譯驗證」）

---

## 6. Phase 11：產線化輸入（P1）

### 實作要點
- **資料夾監控** `scripts/watch_folder.py`：
  `--module <模組> [--category ...] --in ./inbox --station AOI-01 --work-order ...`
  用 **watchdog**（查證授權）監看資料夾，新圖進來 → 呼叫本機 API（帶 API key 與追溯 header）→ 成功移到 `inbox/done/`、失敗移到 `inbox/error/` 並寫 `.log`。處理「檔案還在寫入中」的情況（等檔案大小穩定再讀）。
- **批次 API** `POST /api/batch/{module}`：多檔上傳，逐張呼叫既有 service，回傳每張結果 + 彙總（總數/OK/NG/失敗）。前端各分頁 `<input multiple>`，結果用縮圖列表呈現。
- **M5 短影片抽幀**（補 CLAUDE.md 記錄的未完成項）：`POST /api/safety/video`、`/api/safety/ppe/video`，上傳 mp4，OpenCV `VideoCapture` 每 N 秒（參數，預設 1）抽一幀，回傳違規時間點列表 + 每個違規的縮圖；影片長度上限（例如 60 秒，可設定）。檢驗紀錄寫一筆彙總（不是每幀一筆）。
- **瀏覽器拍照**：各分頁加「📷 拍照」按鈕，`navigator.mediaDevices.getUserMedia` 開相機，拍下轉成 Blob 走原本上傳流程。注意：非 localhost 的 http 無法用相機，README 註明。
- （選做）**RTSP 定時抓圖** `scripts/rtsp_capture.py`：每 N 秒抓一張丟進 watch 資料夾。沒有實體 IP Cam 可測就照實寫「未用實體攝影機測試」，可用本機影片檔模擬。

### 驗收條件
- [ ] watch_folder：丟 10 張圖進 inbox，10 筆紀錄寫入、檔案全部移到 done；丟 1 個壞檔進 error
- [ ] 批次 API 單元測試 + 前端實際多選上傳一次
- [ ] 影片：用可公開授權的短影片或自製影片實測，記錄抽幀數、處理時間、違規偵測結果
- [ ] 手機或筆電相機實際拍一次並辨識成功（記錄在測試紀錄）

---

## 7. Phase 12：自有資料導入流程（P1）

### 實作要點
- **M3 自訂類別**：
  - `POST /api/anomaly/categories`：上傳 zip（良品照片，建議 ≥ 50 張；可選再附少量 NG 照片）+ 類別名稱
  - 用 FastAPI `BackgroundTasks` 背景呼叫 `scripts/train_anomaly.py` 的擬合邏輯（抽成可 import 的函式，CLI 仍保留），**固定用 CPU**（見 CLAUDE.md PatchCore 在 MPS 慢的紀錄）
  - `GET /api/anomaly/categories`、`GET /api/anomaly/categories/{name}/status`（排隊/擬合中/完成/失敗）
  - 前端 M3 分頁：新增類別表單、進度、完成後出現在下拉選單
  - 同時只允許一個擬合工作（16GB 記憶體），第二個排隊
- **門檻調校**：
  - 只有良品：用良品分數分佈建議門檻（例如 99th percentile），並標示「無 NG 樣本，門檻僅依良品分佈估計」
  - 有 NG 樣本：用 ROC 找 Youden's J 最佳門檻，回報 AUROC
  - 前端顯示分數分佈直方圖 + 門檻拖拉，即時顯示「良品誤判率 / NG 漏判率」；門檻存進該類別的設定檔
- **複判資料回流** `scripts/export_reviewed.py`：
  - M5 PPE / M6 → YOLO 格式（原圖 + AI 偵測框當預標註，標記「需人工校正」）
  - M3 → MVTec 資料夾格式（被改判 OK 的放 `good/`，改判 NG 的放 `defect/`）
  - README 寫「用 Label Studio Community 或 CVAT 校正標註」的匯入/匯出步驟（兩者擇一，查證授權；**不要把標註工具裝進本專案 venv**）
- **CLAUDE.md 加 Mermaid 流程圖**：現場誤判 → 人工複判 → 匯出 → 標註校正 → 重訓 → 比較新舊 mAP/AUROC → 上線。

### 驗收條件
- [ ] 用 MVTec 某個**尚未使用**的類別（例如 `bottle` 或 `grid`，查證授權同 MVTec AD）當「自家零件」，全程走 UI 建立類別，記錄擬合時間與 AUROC
- [ ] 門檻調校：同一類別比較「只用良品估計」vs「用 NG 樣本 ROC」兩種門檻的實測誤判率
- [ ] export_reviewed 產出的 YOLO 資料夾能被 `ultralytics` 直接 `val`（至少不報格式錯）

---

## 8. Phase 13：補齊台中常見辨識（P2）

| 代號 | 功能 | 產業情境 | 做法（免費工具需查證） | 訓練 |
|---|---|---|---|---|
| M10 | 組裝防呆／黃金樣本比對 | 自行車組裝、手工具、工具機組立：零件有無、方向、螺絲漏鎖 | OpenCV ORB 特徵 + homography 對齊黃金樣本 → 使用者在黃金樣本上框多個 ROI（沿用 M5 canvas 畫圖的做法）→ 每個 ROI 做 SSIM 或模板比對判 OK/NG；黃金樣本與 ROI 存成「料號設定」 | 否 |
| M11 | 烤漆/陽極色差 ΔE | 自行車車架烤漆、鋁件陽極、射出件 | OpenCV + scikit-image（CIELAB、`deltaE_ciede2000`）；使用者框「標準色區」與「量測區」，或輸入標準 Lab 值；ΔE 門檻可設定 | 否 |
| M12 | 出貨標籤 vs 工單比對 | 出貨前檢核料號、數量、批號是否貼錯 | 重用 M1 條碼 + M4/M7 的 OCR→LLM；比對對象 = Phase 9 的追溯資訊（工單/料號/批號）或手動輸入 | 否 |
| M5+ | 人員跌倒偵測 | 廠區、倉庫工安 | YOLO11n-pose（查證授權，預期同 AGPL-3.0）+ 軀幹角度/長寬比規則 | 否 |
| M8-1+ | 包裝比對容錯 | 醫材/藥品包裝 | 字元混淆正規化（O↔0、I↔1↔l、S↔5、B↔8、Z↔2）+ rapidfuzz 相似度；結果改三級：一致 / 疑似（需人工，verdict=INFO）/ 不一致 NG | 否 |

- 每個新功能：單元測試（合成圖）、至少 1 張**自己拍的真實照片** live 測試（不用來源不明的網路圖）、README 功能表與截圖更新、前端新分頁。
- **鋼材/金屬表面監督式瑕疵**（上一輪因 NEU-DET 授權不明跳過）：重新查證候選資料集（例如 KolektorSDD2、Magnetic Tile Defect 等），**只有授權明確允許學習/展示才做**；查證過程不論結果都寫進 `docs/licenses.md`。

### 驗收條件
- [ ] M10：合成圖「少一顆螺絲」「零件轉 180°」都判 NG；對齊在 ±15° 旋轉、±20% 縮放下仍成功（實測記錄）
- [ ] M11：已知 Lab 值的合成色塊，ΔE 計算與 scikit-image 結果一致；真實照片記錄光源條件
- [ ] M8-1：`LOT0O1` vs `LOT001` 判「疑似」而非 NG；完全不同判 NG；原有 7 項測試仍過（必要時更新期望值並說明原因）
- [ ] 跌倒：用可公開授權或自拍圖片實測，照實記錄誤判

---

## 9. Phase 14：部署、效能、工程品質（P2）

- **ONNX / OpenVINO**：
  - `scripts/export_models.py`：YOLO（M5 person、PPE、M6）匯出 ONNX；OpenVINO 為選項
  - 服務層加 `INFERENCE_BACKEND=torch|onnx|openvino`（預設 torch，行為不變）
  - `scripts/benchmark.py`：每模組跑 N 次，記錄平均/P95 延遲、峰值記憶體，輸出 `docs/benchmark.md`。**只寫實測數字**；沒有 Intel CPU 就寫「OpenVINO 未在 Intel CPU 實測」
- **Docker**：`Dockerfile` + `docker-compose.yml`（backend + ollama，`models/`、`data/` 用 volume）。查證 Docker Desktop 免費授權條件，並列出免費替代方案（Docker Engine、Colima 等，查證後列）。
- **Windows**：檢查路徑處理（`pathlib`）、`cv2`、onnxruntime 相容性；沒有 Windows 機器就寫「未在 Windows 實測」+ 已知差異清單。
- **CI** `.github/workflows/test.yml`：Python 3.11、`ruff check`、`python tests/samples/make_samples.py && pytest`（不含 live）。README 加 badge。需要大模型權重的單元測試必須已經是 mock（確認沒有）。
- **真實照片驗證集** `tests/real_samples/`（自己拍、確認可公開）：七段顯示器 ≥3 張、指針錶 ≥3 張、螺絲計數 ≥3 張。表現差就照實記錄，再決定是否改演算法（例如七段加透視校正/自適應二值化），改完要重測並記錄前後差異。
- **授權風險說明**：`docs/licenses.md` 新增「若導入公司內部系統」一節：
  - Ultralytics YOLO（AGPL-3.0）透過網路提供服務時的開源義務；列出查證過、授權較寬鬆（如 Apache-2.0/MIT）的替代偵測框架候選
  - MVTec AD（CC BY-NC-SA）、其他非商用資料集訓練出的權重不可商用，正式導入需以自有資料重訓
  - 註明「以上為事實整理，非法律意見」

### 驗收條件
- [ ] benchmark.md 有 torch vs onnx 實測表
- [ ] `docker compose up` 後瀏覽器可開、至少 3 個模組實測可用（若本機無 Docker 可跑，照實記錄）
- [ ] CI 在 GitHub 上跑綠燈（附 Actions 連結）
- [ ] 真實照片驗證結果寫進 CLAUDE.md 測試紀錄

---

## 10. Phase 15：作品集呈現（P3）

- README 開頭加 **Mermaid 系統架構圖**：相機/資料夾/手機拍照 → FastAPI 辨識模組 → SQLite 檢驗紀錄（含原圖）→ 品檢看板 / ERP 輪詢 / Webhook。
- `docs/demo-script.md`：**5 分鐘面試 Demo 腳本**
  1. 輸入工單號 → M1 掃零件條碼 → M3 外觀檢測判 NG
  2. 品檢員在看板複判 → 良率與柏拉圖即時變化
  3. 切到 `manufacturing-erp` 品檢查詢頁，看到剛才那筆（證明串接）
  4. 說明「換成貴公司零件怎麼導入」（Phase 12 流程）
  5. 預想面試追問與回答（AGPL、誤判怎麼處理、沒 GPU 怎麼辦、NG 樣本少怎麼辦）
- 更新 `scripts/capture_screenshots.py` 涵蓋新分頁；錄 Demo GIF（ffmpeg 轉檔）。
- 把截圖腳本改成可選的 e2e 測試：`pytest -m e2e`（`pytest.ini` 註冊 marker，預設不跑）。

---

## 11. 本輪仍不做（寫進 README「未納入功能」）

- 高速即時產線檢測、PLC 觸發整合：需要工業相機與 PLC 硬體。
- 多使用者權限/SSO：本輪只做 API Key。
- 雲端部署：需付費主機或綁卡；除非查證到免綁卡且跑得動 Ollama 的免費方案。
- 任何付費 API、付費標註服務、授權不明的資料集。

---

## 12. 回報格式範本（每個 Phase 結束照這個格式）

```
## Phase N 完成回報
### 做了什麼
- ...
### 驗收條件
- [x] 條件 1 —— 實測：<指令 / 數字 / 截圖路徑>
- [ ] 條件 2 —— 未完成原因：...
### 遇到的問題與決策
- ...
### 新增套件（已寫入 docs/licenses.md）
| 套件 | 版本 | 授權 | 可商用 | 來源 |
### 測試
- pytest：N 項全過（X 秒）
- pytest -m live：...
### 下一個 Phase 開工前需要我決定的事
- ...
```

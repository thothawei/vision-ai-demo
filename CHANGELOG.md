# 變更紀錄

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依循語意化版本。
`0.1.0`–`0.15.0` 對應開發 Phase 0–15，細節見 [docs/dev/decisions.md](docs/dev/decisions.md) 與 [docs/dev/test-log.md](docs/dev/test-log.md)。

## [Unreleased]

### 新增
- 真實照片評估集（Wikimedia Commons，授權見 `tests/real_samples/SOURCES.md`）：七段顯示器 8 張、零件計數 3 張、指針錶 3 張；實測表現差（七段 0/8、計數 0/3、指針錶 1/3），已如實寫入 `docs/evaluation.md` 與已知限制。

## [1.0.0]

### 新增
- 容器化部署：`Dockerfile`（多階段、非 root）、`compose.yaml`（app + ollama，另有選用的 SQL Server profile）；管理者手冊新增「容器化部署」與「Windows 部署（未實測）」。
- ERP 端到端驗證（SQLite 版，`tests/test_erp_end_to_end.py`）：增量輪詢、UPSERT、複判同步、重啟續傳、主檔推送。SQL Server 容器在 Apple Silicon 上無法啟動，已如實記錄。
- 批號／料號三級比對（一致／疑似／不一致，rapidfuzz）：包裝與出貨標籤共用，疑似判 INFO 交人工確認。
- `scripts/evaluate.py` 與 `tests/real_samples/`：真實照片評估集；尚無照片的模組在 `docs/evaluation.md` 標示「待補真實照片」。
- GitHub Actions CI（check_wording、ruff、pytest + coverage）；`pytest -m e2e` 截圖流程。

### 變更
- 全專案套用 ruff format 與 import 排序；`pyproject.toml` 版本與變更紀錄對齊。
- 測試中降低 argon2 成本（整套測試約快 25%）；測試圖字型可跨平台。

### 修正
- `.gitignore` 的 `models/`、`reports/` 改錨定根目錄，補回先前漏 commit 的 `backend/modules/models`、`backend/modules/reports`。
- `test_instance_lock` 在子程序被 kill 後呼叫 `Event.set()` 造成死結；Ollama 缺模型測試改用假 client，不依賴本機是否開著 Ollama。

### 已知缺口（見 docs/known-limitations.md）
- 真實照片評估集尚無照片（各模組標示「待補真實照片」）；效能基準與 ONNX 未做；Windows、Colima／Podman、x86_64 容器未實測。

## [0.22.0]

### 新增
- 健康檢查：`GET /healthz`（存活）、`GET /readyz`（資料庫可寫且 migration 到位才是 200，只回摘要、不含路徑）、`GET /api/system/status`（登入後的完整明細：每個功能是否可用與原因、Ollama、磁碟、背景工作；快取 5 秒，`?force=true` 立即重查）。
- 前端「管理 → 系統狀態」頁；不可用的功能在導覽灰掉、顯示原因，面板頂端也有說明。啟動時把就緒狀況與不可用功能寫進日誌。
- 持久化工作佇列（`jobs` 表）：擬合改由輪詢資料庫的 worker 領取；服務重啟時做到一半的工作標成 `interrupted`，排隊中的工作自動接續；`GET /api/jobs`、`POST /api/jobs/{id}/retry`（admin，寫稽核）；異常檢測類別表新增「已中斷」狀態與「重試」按鈕。
- 單一實例鎖：同一個資料庫同一時間只允許一個服務程序，拿不到鎖就拒絕啟動並說明原因（避免第二個程序把第一個程序正在做的工作誤標成中斷）。
- Prometheus 指標 `GET /metrics`（qc 以上或 API key）：請求數與耗時（以路由樣板為標籤）、各模組辨識耗時與各判定筆數、背景工作數。新增相依 prometheus-client 0.26.0（Apache-2.0 AND BSD-2-Clause）。

### 變更
- 註冊表的 `requires` 改成 `model:<模型 id>`、`anomaly`、`llm`（取代已過時的預設權重路徑）。
- 擬合的 worker 改成輪詢資料庫；`enqueue_category` 會建立 job 並在類別狀態記下 `job_id`。

## [0.21.0]

### 新增
- 模型登錄：每個模型多版本、同時一個啟用、可回滾（`GET /api/models`、`POST /api/models/{id}/versions/{v}/activate`、「管理 → 模型」頁、稽核 `model.activate`）；內建權重首次使用時就地登錄成 v1；每個版本首次載入時驗證 SHA-256。
- 異常檢測每次擬合產生新版本（不覆寫舊版本），門檻與評分檔跟著版本走，回滾時一起回滾。
- 檢驗紀錄新增 `model_id`、`model_version`（CSV 追加在最後）；`scripts/register_model.py`（登錄、列出、切換）。
- 模型說明卡：`scripts/gen_model_cards.py` → `docs/model-cards/`。
- 正式 schema migration：`schema_version` 表與 `backend/migrations/NNN_*.py`（每個程序對每個資料庫只檢查一次；資料庫比程式新就拒絕連線）。
- 資料保存：`IMAGE_RETENTION_DAYS`（預設 180）與 `scripts/cleanup_images.py`（預設只預覽、`--apply` 才刪；有人工複判的圖片預設保留；被清掉的圖標記 `expired`，圖片端點回 410）。
- 備份還原：`scripts/backup.py`（SQLite online backup、manifest 與 SHA-256、不含 `.env`、權限 0600）、`scripts/restore.py`（預設預覽、`--yes` 才執行、舊資料改名保留、拒絕損毀或較新版本的備份）。

### 變更
- 各模型服務改向登錄表取啟用版本（保留 `_get_model` 等接縫與 `WEIGHTS_PATH` 預設路徑）。
- 測試預設隔離資料庫、圖片、黃金樣本目錄（autouse fixture），避免測試寫進真實資料。

## [0.20.0]

### 新增
- `measurements` 表：辨識時自動把尺寸（長度、寬度、單孔孔徑）、色差 ΔE00、指針錶與七段顯示器讀值正規化寫入，含規格上下限（尺寸＝目標 ± 公差；色差只有上限）。尺寸量測結果新增 `公差mm`。
- SPC：X̄-R（子群 2–10）與 I-MR 管制圖、Cp／Cpk（組內變異；子群少於 25 組標示僅供參考；單邊規格只給 Cpk）、Western Electric 規則 1–4（規則 4 連續點數預設 8，可調）；`GET /api/spc`、`GET /api/spc/characteristics`（qc 以上或 API key 唯讀）；「管理 → SPC 管制圖」頁。
- 品質日報／週報：`GET /api/reports/summary`（JSON／Excel／可列印 HTML）；看板上的報表按鈕；`scripts/daily_report.py`（可排程，不需要伺服器）。
- `scripts/backfill_measurements.py`：補歷史量測值（需明確執行，可 `--dry-run`）。
- 新增相依：openpyxl 3.1.5（MIT）。

## [0.19.0]

### 新增
- 主檔：料號與工單（`parts`、`work_orders`），ERP 可用 `POST /api/master/{parts,work-orders}:bulk-upsert` 推送（只有名為 `erp` 的 API key 或 admin；每列各自成功或失敗、可重複推送）。
- 檢驗配方：一個料號多個版本（版本不可變、同時只有一個啟用、可回滾）；步驟＝動作＋參數＋圖片槽，參數以註冊表的 Pydantic 模型驗證，並檢查引用對象存在。
- 依配方檢驗 `POST /api/inspect/recipe`：多步驟、多圖片槽，合併判定（NG／INFO／OK）；`inspection_runs` 與 `inspections.run_id`；`GET /api/runs`（含 `since_id`）。
- `assembly`、`colordiff` 有了參數模型與 handler（可用於配方，仍不開放批次 API）；色差標準（標準 Lab／標準色區、量測區、門檻）隨配方版本保存並記入稽核。
- 追溯資訊列的工單選單（進行中工單，自動帶入料號與批號）；`inspections.adhoc` 標記臨時檢驗。
- 看板可切換「單筆辨識／整次配方檢驗」統計（`stats?scope=run`，最終判定由各步驟的複判動態合併）。
- 前端：依配方檢驗頁、主檔與配方管理頁（步驟參數表單由 `params_schema` 產生）。
- 稽核新增：`part.*`、`work_order.update`、`parts／work_orders.bulk_upsert`、`recipe.create／activate／deactivate`。

## [0.18.0]

### 新增
- 本機帳號與三種角色（operator／qc／admin）：登入 session（簽章 cookie）、argon2id 密碼雜湊、登入失敗鎖定（預設 5 次鎖 15 分鐘）、自行改密碼、使用者管理頁。
- 稽核紀錄 `audit_log`：複判、使用者異動、門檻調整、黃金樣本新增與覆寫、自訂類別建立、操作員代簽；管理頁可查詢。
- `inspections.created_by`：operator 只看得到自己的紀錄。
- `scripts/create_admin.py`；`watch_folder.py` 新增 `--api-key`／`WATCH_API_KEY`。
- 設定：`SESSION_SECRET`（必填，至少 32 字元）、`SESSION_HOURS`、`SESSION_COOKIE_SECURE`、`LOGIN_MAX_FAILURES`、`LOGIN_LOCK_MINUTES`。

### 變更
- **所有端點都需要驗證**（原本辨識端點公開）；主頁面與 API 文件未登入導向登入頁。
- **API key 只能辨識與唯讀**，不能複判或管理；`?api_key=` 網址參數移除。
- 複判人取自登入者（請求 body 的 `reviewer` 欄位保留但忽略）；追溯欄位「操作員」預設帶登入者。
- 寫入請求檢查 Origin 與 Host 一致（擋 CSRF）。

### 移除
- 前端寫死的 `FRONTEND_API_KEY`；`core/api_auth.py`。

## [0.17.0]

### 新增
- 辨識動作註冊表 `core/registry.py`：批次 API、`GET /api/modules`、NG 柏拉圖、前端導覽都由它衍生。
- 請求範圍資料 `core/request_scope.py`：一次請求可存多張圖（raw／golden／reference），組裝防呆同時存待測照與黃金樣本；`GET /api/inspections/{id}/image?kind=golden`。
- 集中設定 `core/settings.py`（pydantic-settings），設定表由 `scripts/gen_settings_doc.py` 自動產生。
- key=value 日誌、`X-Request-ID`、`inspections.request_id` 欄位（CSV 最後一欄）、模型載入與 LLM 耗時日誌。
- 前端拆成 ES modules，左側分類導覽（依 `/api/modules`），網址 `#分頁` 可直連。

### 修正
- NG 原因柏拉圖補上 `assembly`、`colordiff`、`codes`、`measure`、`docs`、`nameplate`（含七段顯示器）六個原本漏掉的功能。

### 變更
- 批次 API 對未知參數回 422（原本靜默忽略）；參數用各動作的 Pydantic 模型驗證。
- 設定改為每次讀取 `.env`（「即時」類不必重啟）；`CORS_ORIGINS`、`LOG_LEVEL` 仍需重啟。
- 量測結果新增 `超差項目` 欄位。

## [0.16.0]

### 新增
- `LICENSE`（AGPL-3.0）、`pyproject.toml`、本變更紀錄。
- `scripts/check_wording.py`：檢查專案是否出現不當的定位用語。
- 文件：`docs/walkthrough.md`、`docs/user-guide.md`、`docs/admin-guide.md`、`docs/known-limitations.md`、`docs/dev/`（技術決策、測試紀錄、開發進度、規劃文件）。

### 變更
- README 改為產品介紹；`CLAUDE.md` 精簡為開發規則與陷阱。
- `docs/licenses.md` 補「費用」欄與「本產品授權與第三方元件」。

## [0.15.0]
### 新增
- 系統架構圖（Mermaid＋靜態 PNG）與系統導覽文件。

## [0.14.0]
### 新增
- M12 出貨標籤與工單比對（批號優先信任 GS1 條碼；預期值：明確參數優先於追溯資訊）。
### 修正
- 批次 API 未帶入預期料號／批號／數量。

## [0.13.0]
### 新增
- M10 組裝防呆（黃金樣本、ORB 對齊、SSIM 比對）。
- M11 烤漆／陽極色差（CIEDE2000 ΔE）。

## [0.12.0]
### 新增
- M3 自訂類別（zip 上傳、背景排隊擬合、門檻調校）。
- `scripts/export_reviewed.py`：複判資料回流（YOLO／MVTec 格式）。
### 修正
- 關閉 anomalib 內建分數正規化，避免門檻退化成 1.0。

## [0.11.0]
### 新增
- 資料夾監控、批次 API、M5 短影片抽幀、瀏覽器拍照。
### 修正
- 壞圖片檔回 500 而非 400。

## [0.10.0]
### 新增
- ERP 串接：`X-API-Key`、`since_id` 增量輪詢、複判查詢、NG webhook（含失敗重試佇列）、CORS 白名單、上傳大小限制。

## [0.9.0]
### 新增
- 檢驗紀錄追溯欄位、原圖／標註圖存檔、人工複判、品檢看板；舊資料庫自動補欄位。

## [0.8.0]
### 新增
- README 實際辨識畫面截圖與「未納入功能」章節。

## [0.7.0]
### 新增
- M8 包裝追溯碼檢核、醫學影像分類展示（僅供技術展示，非醫療診斷用途）。

## [0.6.0]
### 新增
- M7 銘牌、七段顯示器、指針錶讀值。

## [0.5.0]
### 新增
- M6 PCB 瑕疵偵測（YOLO11n）、M5 安全帽偵測。

## [0.4.0]
### 新增
- M4 改用 RapidOCR、嚴格 schema 與數字來源核對。

## [0.3.0]
### 新增
- M3 外觀異常檢測（PatchCore）。

## [0.2.0]
### 新增
- M1 追溯碼、M2 計數與尺寸量測、M5 危險區域入侵。

## [0.1.0]
### 新增
- FastAPI 後端、共用回應格式、LLM 抽象層（Ollama／Gemini 備援）、SQLite 檢驗紀錄、分頁式前端。

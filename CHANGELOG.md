# 變更紀錄

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依循語意化版本。
`0.1.0`–`0.15.0` 對應開發 Phase 0–15，細節見 [docs/dev/decisions.md](docs/dev/decisions.md) 與 [docs/dev/test-log.md](docs/dev/test-log.md)。

## [Unreleased]

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

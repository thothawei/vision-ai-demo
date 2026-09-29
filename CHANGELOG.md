# 變更紀錄

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依循語意化版本。
`0.1.0`–`0.15.0` 對應開發 Phase 0–15，細節見 [docs/dev/decisions.md](docs/dev/decisions.md) 與 [docs/dev/test-log.md](docs/dev/test-log.md)。

## [Unreleased]

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

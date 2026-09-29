# 管理者手冊

適用版本 0.18.0。

## 安裝

完整步驟（系統套件、Python 環境、模型權重、資料集）見 [README.md](../README.md#安裝)。最低需求：macOS（Apple Silicon 實測）、Python 3.11、Ollama 與 `qwen3.5:9b` 模型、16GB 記憶體。

啟動：

```bash
source venv/bin/activate
ollama serve &
cd backend && uvicorn main:app
```

## 帳號與首次啟動

1. 在 `.env` 設定 `SESSION_SECRET`（至少 32 字元，沒設定或太短服務**拒絕啟動**）：
   ```bash
   python -c "import secrets;print(secrets.token_urlsafe(48))"
   ```
2. 建立第一個管理員（密碼互動輸入，程式內沒有預設帳密）：
   ```bash
   python scripts/create_admin.py --username admin --display-name 系統管理員
   ```
3. 之後由 admin 在「管理 → 使用者」建立其他帳號。密碼至少 10 個字元，以 argon2id 雜湊儲存。
4. HTTPS 部署時把 `SESSION_COOKIE_SECURE` 設為 true，並讓反向代理保留原始 `Host` header。
5. 忘記所有 admin 密碼時：對資料庫直接執行 `scripts/create_admin.py` 建立新的 admin，再由它重設其他人。

系統對系統的呼叫（ERP、`watch_folder.py`）用 `.env` 的 `API_KEYS`；資料夾監控帶 `--api-key` 或環境變數 `WATCH_API_KEY`。API key 只能辨識與唯讀。

## `.env` 設定參考

設定放在專案根目錄 `.env`（範本 `.env.example`），真實環境變數優先於 `.env`。**「即時」＝ 每次使用時重新讀取（改 `.env` 不必重啟）；「需重啟」＝ 服務啟動時讀一次。** 下表由 `scripts/gen_settings_doc.py` 依 `backend/core/settings.py` 自動產生，請勿手改。

<!-- settings-table:begin -->
| 變數 | 預設 | 用途 | 生效 |
|---|---|---|---|
| `LLM_ENGINE` | `ollama` | LLM 引擎：ollama（離線）或 gemini（免費層備援） | 即時 |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama 模型名稱 | 即時 |
| `OLLAMA_KEEP_ALIVE` | `5m` | 模型閒置多久後釋放記憶體 | 即時 |
| `OLLAMA_TIMEOUT` | `300.0` | Ollama 呼叫逾時（秒） | 即時 |
| `GEMINI_API_KEY` | 無 | 僅 LLM_ENGINE=gemini 需要；請勿啟用計費帳戶 | 即時 |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini 模型 | 即時 |
| `SAVE_IMAGES` | `True` | 是否存原圖與標註圖 | 即時 |
| `INSPECTION_DB` | 無 | 檢驗紀錄 SQLite 路徑（預設 data/inspections.db） | 即時 |
| `INSPECTION_IMAGES_DIR` | 無 | 圖片存放目錄（預設 data/images） | 即時 |
| `GOLDEN_SAMPLES_DIR` | 無 | 黃金樣本目錄（預設 data/golden_samples） | 即時 |
| `API_KEYS` | 空 | /api/inspections* 的 X-API-Key 白名單，格式 名稱:key,名稱:key；正式環境務必換成隨機字串 | 即時 |
| `CORS_ORIGINS` | `http://127.0.0.1:8000,http://localhost:8000` | 允許的前端網域（逗號分隔） | **需重啟** |
| `MAX_UPLOAD_MB` | `20` | 單張圖片大小上限（MB），超過回 413 | 即時 |
| `MAX_VIDEO_MB` | `200` | 影片大小上限（MB） | 即時 |
| `ERP_WEBHOOK_URL` | 無 | NG 時 POST 通知的網址；空白＝不啟用 | 即時 |
| `LOG_LEVEL` | `INFO` | 日誌層級（DEBUG／INFO／WARNING／ERROR） | **需重啟** |
| `SESSION_SECRET` | 無 | 登入 session 的簽章密鑰（至少 32 字元，未設定則拒絕啟動）；產生：python -c "import secrets;print(secrets.token_urlsafe(48))" | **需重啟** |
| `SESSION_HOURS` | `12` | 登入有效時數 | **需重啟** |
| `SESSION_COOKIE_SECURE` | `False` | cookie 是否只在 HTTPS 傳送（HTTPS 部署時設 true） | **需重啟** |
| `LOGIN_MAX_FAILURES` | `5` | 同一帳號連續登入失敗幾次後鎖定 | 即時 |
| `LOGIN_LOCK_MINUTES` | `15` | 登入失敗鎖定分鐘數 | 即時 |
<!-- settings-table:end -->

`TRUST_REMOTE_CODE` 由程式在載入本機訓練的異常檢測權重時自行設定，不屬於使用者設定，請勿手動設定。

## 模型訓練與擬合

- **外觀異常檢測（內建類別）**：`python scripts/train_anomaly.py --category all`（固定 CPU，約 22 分鐘）。需先下載 MVTec AD（非商用授權，見 [licenses.md](licenses.md)）。
- **外觀異常檢測（自有類別）**：在 M3 分頁「新增自訂類別」上傳 zip；擬合在背景排隊，一次一個，伺服器重啟會遺失排隊項目。
- **PCB／安全帽**：`scripts/prepare_deeppcb.py`、`scripts/prepare_hardhat.py` 轉檔後以 ultralytics 訓練，或使用 `notebooks/` 的 Colab 版。訓練的 `project` 參數必須用**絕對路徑**。
- **醫學影像分類**：`python scripts/train_medmnist.py`（僅供技術展示）。
- **權重位置**：`models/`（不進版控）。正式導入須以自有資料重新擬合／訓練，MVTec AD 訓練的權重不得商用。

## 日誌與問題追查

- 日誌為 key=value 格式（`ts= level= logger= request_id= msg=`），輸出到標準輸出；層級由 `LOG_LEVEL` 設定（需重啟）。
- 每個請求有 `request_id`（回應 header `X-Request-ID`，可由呼叫端帶入）；檢驗紀錄的 `request_id` 欄位與 CSV 最後一欄可對回日誌。
- 記錄項目：請求（方法、路徑、狀態、耗時）、辨識完成（模組、判定、耗時）、模型載入耗時、LLM 呼叫耗時與失敗。不記錄 API key 與圖片內容。

## 整合與維運

- ERP 串接（輪詢、webhook、欄位對照、C# 範例）：[erp-integration.md](erp-integration.md)。
- 資料夾監控：`WATCH_API_KEY=<key> python scripts/watch_folder.py --action <動作> --in ./inbox`（key 為 `.env` 的 `API_KEYS` 其中一組的 key）。
- 複判資料回流：`python scripts/export_reviewed.py`。
- 備份與還原：目前請自行備份 `data/`（SQLite 與圖片），還原前先停止服務；自動備份／還原腳本規劃於後續版本。
- 授權與第三方元件：[licenses.md](licenses.md)；本產品為 AGPL-3.0-or-later。

## 容器執行環境（後續版本）

容器化部署規劃於後續版本；屆時以 Colima／Podman／Docker Engine 為準。Docker Desktop 對大型企業使用需付費訂閱，僅在符合其免費條件時可選用，不作為安裝需求。

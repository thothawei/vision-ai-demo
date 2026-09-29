# 管理者手冊

適用版本 0.21.0。

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

## 主檔與配方

1. 料號：`管理 → 主檔與配方` 新增，或由 ERP 以 `parts:bulk-upsert` 推送。
2. 工單：同一頁新增，或由 ERP 推送（`.env` 的 `API_KEYS` 需有名為 `erp` 的 key）。工單的料號必須已在主檔。
3. 配方：選料號 → 新增版本 → 設定步驟（動作、圖片槽、參數）→ 儲存並啟用。儲存時會驗證參數，並檢查引用對象存在（異常檢測類別、組裝防呆黃金樣本）。
4. 只有 `assembly`、`colordiff` 這類不開放批次 API 的動作也能用在配方裡；組裝防呆的黃金樣本預設用配方的料號。
5. 配方檢驗是同步執行，步驟多或含 AI 的步驟時整個請求會較久。

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
| `IMAGE_RETENTION_DAYS` | `180` | 圖片保存天數（給 scripts/cleanup_images.py 用；有人工複判的圖片預設不清） | 即時 |
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

## 模型登錄與回滾

- 每個模型（PCB 瑕疵、安全帽、人員偵測、肺炎展示、每個異常檢測類別）有多個**版本**，同時只有一個**啟用**。`管理 → 模型` 可查看版本、指標、SHA-256，admin 可切換啟用版本（回滾）；切換立即生效並記入稽核（`model.activate`）。
- **既有權重不用搬**：第一次使用某個模型時，若它還沒有任何版本，預設位置的權重會就地登錄成 v1（登錄後不要再原地覆寫那個檔案，SHA-256 會不符）。
- **登錄新版本**只能在伺服器上做（異常檢測的權重是 pickle 檔，網頁不提供上傳）：

  ```bash
  python scripts/register_model.py list
  python scripts/register_model.py register --model-id pcb-defect --weights runs/.../best.pt \
      --metrics-json metrics.json --note "加入產線照片重訓" --activate
  python scripts/register_model.py activate --model-id pcb-defect --version 1
  ```

  權重會複製進 `models/registry/<模型 id>/v<N>/`（不可覆寫）；不加 `--activate` 則只登錄、不啟用。
- **異常檢測**：每次擬合（`train_anomaly.py`、網頁上傳良品照片）都會產生新版本並自動啟用，舊版本保留；門檻與評分檔跟著版本走，所以回滾時門檻一起回滾。`PATCH threshold` 改的是「目前啟用版本」的門檻。
- **完整性**：每個版本在同一程序首次載入時會重算 SHA-256，不符就拒絕載入並回錯誤（權重被更動或損毀）。這個檢查每個程序只做一次，服務執行中被改動的檔案要到下次重啟才會被發現。
- 檢驗紀錄會記下用了哪個模型與版本（`model_id`、`model_version`）；沒有模型的功能（條碼、量測、OCR＋AI 等）為空。
- 模型說明卡：`python scripts/gen_model_cards.py` 由登錄表產生 `docs/model-cards/`（用途、資料集與授權、指標、版本歷史、已知限制、不適用情境）；加 `--check` 檢查是否為最新。

## 資料保存與圖片清理

`IMAGE_RETENTION_DAYS`（預設 180）是保存天數。清理腳本**預設只預覽**，加 `--apply` 才真的刪檔（刪掉就回不來）：

```bash
python scripts/cleanup_images.py                  # 預覽會清多少
python scripts/cleanup_images.py --days 90 --apply
```

- **有人工複判的圖片預設不清**（再訓練資料的來源）；要連它們一起清請加 `--include-reviewed`。
- 檢驗紀錄本身保留；被清掉的圖，路徑欄位改為 `expired`，看板會顯示「圖片已依保存期限清理」，圖片端點回 410。
- 只會刪 `INSPECTION_IMAGES_DIR` 底下的檔案（資料庫裡被改壞的路徑不會被拿來刪檔）。建議用 `launchd`／工作排程器每週跑一次，做法同下面的報表排程。

## 備份與還原

```bash
python scripts/backup.py                        # 輸出到 backups/（已加入 .gitignore）
python scripts/backup.py --out /mnt/nas --include-models
python scripts/restore.py backups/vision-backup-20261001-020000.tar.gz          # 預覽
python scripts/restore.py backups/vision-backup-20261001-020000.tar.gz --yes    # 執行
```

- 備份內容：資料庫（SQLite online backup，服務執行中也能得到一致的快照）、檢驗圖片、黃金樣本、自訂類別狀態檔，以及 `manifest.json`（schema 版本、時間、每個檔案的 SHA-256）。**不含 `.env`**。
- **備份檔含使用者的密碼雜湊**（在資料庫裡），輸出檔權限為 0600，請妥善保管。
- 模型權重預設不備份（大、可重訓）；`--include-models` 才會把整個 `models/` 放進去。還原時沒有權重的模型，使用時會回「權重檔不存在」，請把權重放回或重新登錄。
- **還原前請先停止服務。** 還原會先驗 manifest 與每個檔案的 SHA-256（不符就中止）；備份的 schema 版本比目前程式新就拒絕；預設只預覽，加 `--yes` 才執行，而且**既有資料不會被刪除**，會改名成 `<原名>.before-restore-<時間>`，確認沒問題後再自行刪除。較舊的備份還原後，第一次連線會自動升級 schema。

## 資料庫版本（migration）

schema 由 `backend/migrations/NNN_*.py` 依序管理，版本記在 `schema_version` 表，服務連線時自動套用尚未套用的版本；不需要手動執行。資料庫版本比程式新（例如程式被降版）時會拒絕連線並說明原因，請升級程式或還原較舊的備份。不支援降版。

## 品質報表與排程

`scripts/daily_report.py` 直接讀資料庫產生日報／週報（Excel 與可列印 HTML），不需要伺服器在執行；輸出預設放 `reports/`（已加入 `.gitignore`）：

```bash
python scripts/daily_report.py                                # 昨天的日報
python scripts/daily_report.py --period week --date 2026-09-29 --out /path/to/dir
```

本專案不內建排程器，請用作業系統的排程：

- **macOS `launchd`**：建立 `~/Library/LaunchAgents/com.example.vision-daily-report.plist`（路徑請改成實際位置），再 `launchctl load` 它：

  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0"><dict>
    <key>Label</key><string>com.example.vision-daily-report</string>
    <key>ProgramArguments</key><array>
      <string>/path/to/vision-ai-demo/venv/bin/python</string>
      <string>/path/to/vision-ai-demo/scripts/daily_report.py</string>
    </array>
    <key>WorkingDirectory</key><string>/path/to/vision-ai-demo</string>
    <key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
  </dict></plist>
  ```
- **Windows 工作排程器**：動作選「啟動程式」，程式 `venv\Scripts\python.exe`，引數 `scripts\daily_report.py`，起始位置設為專案根目錄，觸發程序設為每天固定時間。（尚未在 Windows 實測。）

排程用的帳號必須讀得到專案的 `.env`（資料庫路徑等設定）。

## 歷史量測值回填

Phase 20 之前的檢驗紀錄沒有 `measurements`（SPC 的資料表）。要補進歷史量測值，請明確執行（會寫入資料庫，所以不會自動跑）：

```bash
python scripts/backfill_measurements.py --dry-run   # 先看會補幾筆
python scripts/backfill_measurements.py
```

可重複執行。歷史的尺寸量測當時沒存公差，補進來的長度與寬度沒有規格上下限（只能畫管制圖）；色差有存門檻，所以有上限。

## 整合與維運

- ERP 串接（輪詢、webhook、欄位對照、C# 範例）：[erp-integration.md](erp-integration.md)。
- 資料夾監控：`WATCH_API_KEY=<key> python scripts/watch_folder.py --action <動作> --in ./inbox`（key 為 `.env` 的 `API_KEYS` 其中一組的 key）。
- 複判資料回流：`python scripts/export_reviewed.py`。
- 備份與還原：目前請自行備份 `data/`（SQLite 與圖片），還原前先停止服務；自動備份／還原腳本規劃於後續版本。
- 授權與第三方元件：[licenses.md](licenses.md)；本產品為 AGPL-3.0-or-later。

## 容器執行環境（後續版本）

容器化部署規劃於後續版本；屆時以 Colima／Podman／Docker Engine 為準。Docker Desktop 對大型企業使用需付費訂閱，僅在符合其免費條件時可選用，不作為安裝需求。

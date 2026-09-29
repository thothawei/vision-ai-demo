# 管理者手冊

適用版本 0.16.0。

## 安裝

完整步驟（系統套件、Python 環境、模型權重、資料集）見 [README.md](../README.md#安裝)。最低需求：macOS（Apple Silicon 實測）、Python 3.11、Ollama 與 `qwen3.5:9b` 模型、16GB 記憶體。

啟動：

```bash
source venv/bin/activate
ollama serve &
cd backend && uvicorn main:app
```

## `.env` 設定參考

設定放在專案根目錄 `.env`（範本 `.env.example`）。**「需重啟」＝ 啟動時讀一次；「即時」＝ 每次使用時重讀。** 表格為 0.16.0 手動整理，後續版本將由程式自動產生。

| 變數 | 預設 | 用途 | 生效 |
|---|---|---|---|
| `LLM_ENGINE` | `ollama` | LLM 引擎：`ollama`（離線）或 `gemini`（免費層備援） | 即時 |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama 模型名稱 | 即時 |
| `OLLAMA_KEEP_ALIVE` | `5m` | 模型閒置多久後釋放記憶體 | 即時 |
| `OLLAMA_TIMEOUT` | `300` | Ollama 呼叫逾時（秒） | 即時 |
| `GEMINI_API_KEY` | 無 | 僅 `LLM_ENGINE=gemini` 需要；請勿啟用計費帳戶 | 即時 |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini 模型 | 即時 |
| `SAVE_IMAGES` | `true` | 是否存原圖與標註圖（`data/images/`） | 即時 |
| `INSPECTION_DB` | `data/inspections.db` | 檢驗紀錄 SQLite 路徑 | 即時 |
| `INSPECTION_IMAGES_DIR` | `data/images` | 圖片存放目錄 | 即時 |
| `GOLDEN_SAMPLES_DIR` | `data/golden_samples` | 黃金樣本目錄 | 即時 |
| `API_KEYS` | 空 | `/api/inspections*` 的 `X-API-Key` 白名單，格式 `名稱:key,名稱:key`；正式環境務必換成隨機字串 | 即時 |
| `CORS_ORIGINS` | 本機 8000 埠 | 允許的前端網域（逗號分隔） | **需重啟** |
| `MAX_UPLOAD_MB` | `20` | 單張圖片大小上限，超過回 413 | 即時 |
| `MAX_VIDEO_MB` | `200` | 影片大小上限 | 即時 |
| `ERP_WEBHOOK_URL` | 空 | NG 時 POST 通知的網址；空白＝不啟用 | 即時 |
| `TRUST_REMOTE_CODE` | 程式內設定 | 只用於載入本機訓練的異常檢測權重，請勿手動設定 | — |

## 模型訓練與擬合

- **外觀異常檢測（內建類別）**：`python scripts/train_anomaly.py --category all`（固定 CPU，約 22 分鐘）。需先下載 MVTec AD（非商用授權，見 [licenses.md](licenses.md)）。
- **外觀異常檢測（自有類別）**：在 M3 分頁「新增自訂類別」上傳 zip；擬合在背景排隊，一次一個，伺服器重啟會遺失排隊項目。
- **PCB／安全帽**：`scripts/prepare_deeppcb.py`、`scripts/prepare_hardhat.py` 轉檔後以 ultralytics 訓練，或使用 `notebooks/` 的 Colab 版。訓練的 `project` 參數必須用**絕對路徑**。
- **醫學影像分類**：`python scripts/train_medmnist.py`（僅供技術展示）。
- **權重位置**：`models/`（不進版控）。正式導入須以自有資料重新擬合／訓練，MVTec AD 訓練的權重不得商用。

## 整合與維運

- ERP 串接（輪詢、webhook、欄位對照、C# 範例）：[erp-integration.md](erp-integration.md)。
- 資料夾監控：`python scripts/watch_folder.py --action <動作> --in ./inbox`。
- 複判資料回流：`python scripts/export_reviewed.py`。
- 備份與還原：目前請自行備份 `data/`（SQLite 與圖片），還原前先停止服務；自動備份／還原腳本規劃於後續版本。
- 授權與第三方元件：[licenses.md](licenses.md)；本產品為 AGPL-3.0-or-later。

## 容器執行環境（後續版本）

容器化部署規劃於後續版本；屆時以 Colima／Podman／Docker Engine 為準。Docker Desktop 對大型企業使用需付費訂閱，僅在符合其免費條件時可選用，不作為安裝需求。

# Claude Code 任務：製造業視覺品檢系統 v1.0 產品化規劃（Phase 16–24）

> **使用方式**：在專案根目錄開 Claude Code，輸入：
> 「請讀 `docs/product-hardening-plan.md`，從 Phase 16 的『開工前回報』開始執行。」
>
> Phase 0–15 已完成（17 個分頁、142 項單元測試）。本輪不加大量新辨識功能，重點是把現有系統整理成**一套可交付、可維運、可稽核的正式產品**。

---

## 1. 執行規則（必讀）

1. **沿用 `CLAUDE.md`「硬性規則」**：只用免費工具、核心離線、安裝前查證版本/授權並寫入 `docs/licenses.md`、測試數字不可捏造（沒跑過寫「未測試」）、大檔不進版控、Apple Silicon 16GB。
2. 本文件提到的套件/授權是規劃時的認知，**每個 Phase 開工前都要重新查證**；查證結果不同時以查證為準並回報差異。沒有免費方案就跳過，寫進 README「未納入功能」。
3. **一次一個 Phase**，流程固定：
   - 開工前回報（不寫程式）：新增套件＋查證結果、預計新增/修改檔案、設計取捨、風險、需要我決定的事 → 等我確認
   - 實作：程式＋測試
   - 完成回報：照第 12 節格式，驗收條件逐條附實測證據 → 等我確認
4. **向下相容**：既有 `data/inspections.db` 自動 migrate，不可要求刪庫；`InspectionResult` 只加選填欄位；既有 API 路徑保留（要改名就留舊路徑轉發並標 deprecated）；既有 142 項測試全過。
5. **用詞規範（全專案適用，含程式註解、文件、commit message）**：本專案是正式產品。**不可出現**「作品集」「面試」「應徵」「求職」「Demo 腳本」「展示用 demo」等字樣。描述系統一律用「系統」「平台」「本產品」。唯一例外：醫學影像分類模組必須保留「僅供技術展示，非醫療診斷用途」警語（這是安全聲明，不是定位用語）。
6. **免費工具規則（最高優先，違反即停止該項）**：見第 1.1 節。
7. 每個 Phase 結束更新開發紀錄（Phase 16 之後的位置見 16.3）並 commit；commit 前 grep 掃 API key。

### 1.1 免費工具規則

**判定標準**：一個工具/服務/資料集要同時符合以下全部條件才能使用：
- 取得與使用不需付費，也不需綁信用卡、不需「免費試用後轉付費」
- 本專案的使用方式落在它的免費範圍內（例如：只能在個人/小型組織免費的，要寫清楚條件）
- 開源授權，或廠商明文提供的永久免費版本
- 不依賴它的付費版功能（open-core 產品只能用 Community/免費版功能）

**每一項新工具都要在 `docs/licenses.md` 記錄「費用」欄**：`免費（開源）`／`免費（有條件：…）`，並附官方條款連結與查證日期。查證後發現需要付費、或免費條件不符合本專案用法 → **不用，找免費替代；找不到就跳過並寫進 README「未納入功能」**。不可寫假的 stub。

**本規劃已選定的工具（規劃時認知，開工前仍需重新查證）**：

| 用途 | 使用 | 費用條件 | 禁止使用 |
|---|---|---|---|
| 圖表 | Chart.js | 免費（開源 MIT，已在專案內） | 任何付費圖表元件 |
| 設定管理 | pydantic-settings | 免費（開源） | — |
| 密碼雜湊 | argon2-cffi | 免費（開源） | 付費身分驗證服務（Auth0 付費層、Okta 等） |
| Session | Starlette SessionMiddleware（FastAPI 已內含） | 免費（開源） | — |
| Excel 報表 | openpyxl | 免費（開源） | 付費報表引擎 |
| PDF 報表 | 瀏覽器「列印成 PDF」 | 免費（瀏覽器內建） | 付費 PDF 函式庫/服務 |
| 字串相似度 | rapidfuzz | 免費（開源） | — |
| 監控指標（可選） | prometheus-client（只提供 `/metrics` 端點） | 免費（開源） | Grafana Cloud、Datadog 等付費 SaaS |
| 程式碼檢查 | ruff、pytest、pytest-cov | 免費（開源） | Codecov/SonarCloud 等需帳號的付費層 |
| e2e 測試 | Playwright（Python） | 免費（開源，已在專案 venv） | 雲端瀏覽器測試服務 |
| CI | GitHub Actions | **有條件免費**：repo 維持公開、只用標準 GitHub 託管 runner（`ubuntu-latest`） | 私有 repo 超額分鐘數、larger runners、需付費的 runner 類型 |
| 容器 | Docker Engine／Colima／Podman（擇一，查證後選） | 免費（開源） | **Docker Desktop 不列為必要條件**（大型企業使用需付費訂閱），文件只能列為「符合其免費條件者可選用」 |
| ERP 測試資料庫 | SQL Server **Express**（可用於正式環境，有容量上限）或 **Developer**（僅限開發測試） | 有條件免費，查證條款後寫明限制 | SQL Server Standard/Enterprise、Azure SQL 等付費版本 |
| 排程 | macOS `launchd`／Windows 工作排程器 | 免費（作業系統內建） | 付費排程服務 |
| 標註工具 | Label Studio **Community**／CVAT 自架版（沿用 Phase 12 決定） | 免費（開源） | Label Studio Enterprise、CVAT 雲端付費方案 |
| LLM | Ollama 本機模型（核心） | 免費（開源） | — |
| LLM 備援 | Gemini API **免費層**（沿用，可選） | 有條件免費：不可啟用計費帳戶；README 註明免費層的資料使用條款 | Gemini 付費層、任何付費 LLM API |
| GPU 訓練（可選） | Google Colab 免費版（沿用既有 notebook） | 有條件免費 | Colab Pro、付費雲端 GPU |

**本規劃不需要任何付費帳號、付費訂閱或信用卡。** 若執行中發現某步驟只能靠付費方案完成，停下來回報，不要自行採用。

**Phase 16 額外工作**：`docs/licenses.md` 既有表格全部補上「費用」欄（逐項重新查證），發現任何既有元件已改為付費或條件不符時列出回報。

---

## 2. 現況盤點：需要加強的地方

以下都是讀程式碼確認過的事實，不是推測。

### 2.1 定位與文件
| # | 問題 | 證據 |
|---|---|---|
| A1 | 文件仍把系統定位成作品/Demo | `CLAUDE.md` 11 處、`README.md`（第 101、262 行）、`docs/licenses.md`（第 5、94 行）、`scripts/train_anomaly.py` 第 13 行、`backend/core/api_auth.py` 第 5、33 行、`docs/demo-script.md` 整份、`docs/manufacturing-ai-plan-prompt.md`、`docs/next-phase-gap-plan-prompt.md` |
| A2 | 沒有 LICENSE 檔 | repo 公開，但根目錄無 LICENSE；相依的 Ultralytics 是 AGPL-3.0 |
| A3 | 沒有版本號與 CHANGELOG | 無 `pyproject.toml`、無 tag、無 CHANGELOG |
| A4 | `CLAUDE.md` 614 行、約 57KB，每次開 session 都整份載入 | 大部分是逐 Phase 的開發史與測試紀錄，不是「開發時要遵守的規則」 |
| A5 | 缺使用者/管理者文件 | 只有 README 與開發紀錄，沒有操作手冊、部署/設定手冊 |

### 2.2 架構與程式品質
| # | 問題 | 證據 |
|---|---|---|
| B1 | **NG 原因柏拉圖漏掉 4 個會判 NG 的模組**（真實 bug） | `inspection_log.py` 只有 `defect/ppe/anomaly/safety/medical_packaging/shipping` 六個 `@_extractor`；`assembly`、`colordiff`、`codes`（效期過期判 NG）、`measure`（數量/公差 NG）都會判 NG 卻不會出現在柏拉圖 |
| B2 | 模組資訊散在多處，新增模組容易漏改 | 動作清單在 `core/batch_dispatch.py` 的 `ACTIONS` 與 `modules/batch/router.py` 各維護一份（CLAUDE.md 已記錄 M12 漏改過）；柏拉圖 extractor 白名單；前端 `MODULE_LABELS`；`main.py` 手動 include 17 個 router |
| B3 | `RAW_IMAGE_CTX` 一個請求只能記一張圖 | 已知限制有記錄；M10 黃金樣本比對這類雙圖模組已經存在 |
| B4 | 前端單檔 1784 行、17 個分頁平鋪 | `frontend/index.html`；功能分類不清，維護困難 |
| B5 | 設定散落各處讀 `os.environ` | CORS 啟動讀一次、API_KEYS 每次請求重讀，行為不一致（已知限制有記錄） |
| B6 | 幾乎沒有 logging | `backend/` 只有 4 處 logging/logger |

### 2.3 權限與稽核
| # | 問題 | 證據 |
|---|---|---|
| C1 | 前端 API key 寫死在 HTML | `frontend/index.html` 第 1546 行 `FRONTEND_API_KEY = "dev-frontend-key-change-me"`，任何人看原始碼就拿到 |
| C2 | 沒有使用者帳號，複判人是自由文字 | `reviewer` 欄位是手打的字串，無法確認是誰改判 |
| C3 | 沒有稽核紀錄 | 複判覆寫後看不到修改歷程；門檻、黃金樣本、色差標準被改也沒紀錄 |
| C4 | 13 個辨識端點完全不驗證 | Phase 10 的取捨，只適合單機 |

### 2.4 製造業流程
| # | 問題 | 證據 |
|---|---|---|
| D1 | 工單/料號/批號是自由文字 | 已知限制：大小寫不同就變兩個工單 |
| D2 | 沒有「料號 → 檢驗規格」的設定 | 公差、ΔE 門檻、M3 類別、黃金樣本、預期數量每次都要人手動選/輸入；實際產線是「選料號 → 自動套用該料號的檢驗項目」 |
| D3 | 沒有多項檢驗合併判定 | 一個零件常要同時做「條碼 + 外觀 + 尺寸」，目前要切三個分頁、產生三筆不相關的紀錄 |
| D4 | 量測資料沒有統計製程管制 | M2 有量測值，但沒有 X̄-R 管制圖、Cp/Cpk |
| D5 | 沒有正式報表 | 只有 CSV，沒有日/週品質報表 |

### 2.5 模型與資料治理
| # | 問題 | 證據 |
|---|---|---|
| E1 | 紀錄沒寫是哪個模型版本判的 | `engine` 只有名稱（如 `yolo11n-deeppcb`），重訓後無法區分新舊模型的判定 |
| E2 | 沒有模型登錄/回滾機制 | 權重路徑寫死（例如 `WEIGHTS_PATH`） |
| E3 | 沒有模型說明卡 | 各模型的資料集、授權、指標、限制散在 CLAUDE.md |
| E4 | 圖片無限增長 | `data/images/` 沒有保存期限與清理機制 |
| E5 | 沒有備份/還原 | SQLite 與圖片沒有備份腳本 |
| E6 | migration 無版本 | `PRAGMA table_info` 只能補欄位，不能做改型別、加索引以外的變更 |

### 2.6 可靠性、驗證、交付
| # | 問題 | 證據 |
|---|---|---|
| F1 | 沒有健康檢查 | 無 `/healthz`；缺權重、Ollama 沒開時，使用者要按下去才知道壞 |
| F2 | 擬合佇列重啟就消失 | 已知限制：`queue.Queue()` 在記憶體 |
| F3 | 多個模組只驗證過合成圖 | M2、M7 七段/指針錶、M10、M11、相機拍照都沒用真實照片測過 |
| F4 | M8-1 包裝比對無容錯 | O/0 混淆直接 NG |
| F5 | 沒有 CI、沒有容器化 | 無 `.github/workflows`、無 Dockerfile |
| F6 | ERP 串接沒有端到端實測 | `docs/erp-integration.md` 自己寫「未真實連線測試」 |

---

## 3. 階段總覽與優先順序

| Phase | 主題 | 解決 | 優先 |
|---|---|---|---|
| 16 | 產品定位、授權、文件重整 | A1–A5 | P0 |
| 17 | 架構重整：模組註冊表、設定集中、前端拆分 | B1–B6 | P0 |
| 18 | 使用者、角色、稽核紀錄 | C1–C4 | P0 |
| 19 | 主檔與檢驗配方（多項檢驗合併判定） | D1–D3 | P1 |
| 20 | SPC 與品質報表 | D4–D5 | P1 |
| 21 | 模型與資料治理 | E1–E6 | P1 |
| 22 | 可靠性與可觀測性 | F1–F2 | P2 |
| 23 | 真實場景驗證與 CI | F3–F5（CI） | P2 |
| 24 | 容器化部署、ERP 端到端、v1.0.0 發佈 | F5–F6 | P2 |

---

## 4. Phase 16：產品定位、授權、文件重整（P0）

### 16.1 用詞正規化
- 新增 `scripts/check_wording.py`：掃描全專案（排除 `venv/`、`data/`、`models/`、`runs/`、本規劃文件與該腳本自身）是否出現第 1 節第 5 條的禁用詞，有就列出檔案與行號並以非 0 結束；Phase 23 會把它加進 CI。
- 依腳本結果把命中處全部改寫成正式產品用語；`grep -n -i "demo"` 逐一判斷：描述系統定位的改掉，`medical_pneumonia_demo` 這類模組代號與醫療警語保留。
- `docs/demo-script.md` → 改寫為 `docs/walkthrough.md`「系統導覽」：以「品檢員一天的操作流程」為主軸（登入 → 選工單 → 檢驗 → 複判 → 看板 → 匯出），刪除所有問答式段落。
- `docs/manufacturing-ai-plan-prompt.md`、`docs/next-phase-gap-plan-prompt.md`、本文件（全部 Phase 完成後）：移到 `docs/dev/plans/` 並把定位用語改寫（內容保留當設計紀錄）。
- README 標題與開頭改為產品介紹：產品名稱、適用產業、核心能力、系統架構圖、快速開始。
- **git 歷史不改寫**：舊 commit message 含舊用語，不做 force push／rebase；在回報中列出受影響的 commit 讓我決定。

### 16.2 授權與版本
- 新增 `LICENSE`：因相依 Ultralytics（AGPL-3.0）且透過網路提供服務，**建議 AGPL-3.0**；開工前回報查證 AGPL 相容性結論，由我決定。
- 新增 `pyproject.toml`（專案名稱、版本 `0.16.0`、Python 3.11、ruff 設定；相依仍以 `backend/requirements.txt` 為準，不要兩邊重複鎖版本）。
- 新增 `CHANGELOG.md`（Keep a Changelog 格式），把 Phase 0–15 濃縮成 `0.1.0`–`0.15.0` 的條目。
- `docs/licenses.md` 補一節「本產品授權與第三方元件」：AGPL 義務、非商用資料集訓練出的權重（MVTec AD、PneumoniaMNIST 等）不得用於商業產線、正式導入需以自有資料重訓；註明「非法律意見」。

### 16.3 CLAUDE.md 瘦身
- `CLAUDE.md` 只保留：專案目標、硬性規則、用詞規範、目錄結構、啟動/測試指令、**開發時必須記得的陷阱**（從已知限制與技術決策中挑出「會影響寫程式」的，例如 ultralytics `project` 絕對路徑、PatchCore 用 CPU、CORS 需重啟、FastAPI 靜默忽略未宣告參數、測試要隔離 `data/` 路徑），目標 **≤ 200 行**。
- 其餘內容搬到：
  - `docs/dev/decisions.md`：技術決策與理由（Phase 0–15 原文保留）
  - `docs/dev/test-log.md`：測試紀錄（原文保留，數字不可改）
  - `docs/known-limitations.md`：已知限制（給使用者看的版本，改用使用者語言）
- 之後每個 Phase 的決策/測試紀錄寫進 `docs/dev/`，CLAUDE.md 只更新「陷阱」與「待辦」。

### 16.4 使用者文件
- `docs/user-guide.md`：操作手冊，依功能分類（見 17.4 的分類），每個功能寫「用途、輸入、判定規則、常見誤判與處理」。
- `docs/admin-guide.md`：安裝、`.env` 設定參考（每個變數的用途、預設值、是否需重啟）、模型訓練/擬合、備份還原（Phase 21 補）。

### 驗收條件
- [ ] `python scripts/check_wording.py` 結果為 0 筆（附輸出；醫療警語例外）
- [ ] `CLAUDE.md` ≤ 200 行，且搬走的內容在 `docs/dev/` 可找到、測試數字與原文一致（用 diff 驗證沒有遺失段落）
- [ ] LICENSE、pyproject.toml、CHANGELOG.md 存在；README 開頭是產品介紹
- [ ] 142 項測試全過（純文件變更也要跑）

---

## 5. Phase 17：架構重整（P0）

### 17.1 模組註冊表（單一真實來源）
- 新增 `backend/core/registry.py`，每個辨識動作用一個 dataclass 註冊：
  ```python
  @dataclass(frozen=True)
  class ActionSpec:
      action: str            # 批次/路由用代號，例如 "defect"
      module: str            # 寫進 inspections.module 的名稱
      label: str             # 前端顯示名稱（繁中）
      category: str          # 17.4 的功能分類
      handler: Callable      # service 函式
      params: type[BaseModel] | None   # 額外參數的 Pydantic model
      verdict_kind: Literal["inspection", "info"]  # info 不列入良率
      defect_extractor: Callable | None  # 柏拉圖用；inspection 類必填
      requires: list[str]    # 需要的權重/服務，給 Phase 22 健康檢查用
  ```
- `core/batch_dispatch.py`、`modules/batch/router.py`、`inspection_log.extract_defect_labels()`、前端模組名稱對照全部改為讀註冊表；新增 `GET /api/modules` 回傳註冊表（不含 handler），前端動態讀取。
- **加一個測試：所有 `verdict_kind="inspection"` 的動作都必須有 `defect_extractor`**，否則測試失敗 —— 直接修掉 B1，且之後不會再漏。
- 補上 `assembly`（NG 的 ROI 編號 → 「ROI n 缺件/異常」）、`colordiff`（「色差超標」）、`codes`（「已過期」）、`measure`（「數量不符」「尺寸超差：長/寬/孔徑」）的 extractor。

### 17.2 請求範圍資料（取代 contextvar 單圖限制）
- 把 `RAW_IMAGE_CTX` 改成請求範圍的物件（例如 `RequestScope`，含 `trace`、`images: list[tuple[role, bytes]]`），`load_image()` 改成 append 並可指定 role（`raw`、`golden`、`reference`）。
- `record_result()` 存圖時全部存，檔名 `<id>_<role>.<ext>`；`/api/inspections/{id}/image?kind=` 支援新 role。
- 舊紀錄的 `image_path/annotated_path` 欄位保留相容。

### 17.3 設定集中
- 新增 `backend/core/settings.py`，用 **pydantic-settings**（查證版本與授權）集中所有 `.env` 變數，型別驗證、預設值、說明文字在同一處。
- 每個設定明確標記「啟動時讀取（需重啟）」或「即時生效」，`docs/admin-guide.md` 的設定表由程式自動產生（`scripts/gen_settings_doc.py`），避免文件與程式不一致。

### 17.4 前端重整（維持純 HTML/JS、不引入建置工具）
- 拆成 `frontend/index.html` + `frontend/js/*.js`（原生 ES modules）+ `frontend/css/app.css`；共用元件（上傳、相機、canvas 畫框、結果渲染、批次卡片）各自一個檔案。
- 17 個平鋪分頁改為**左側分類導覽**：
  - 外觀檢測：異常檢測、PCB 瑕疵、組裝防呆、色差
  - 量測與讀值：計數量測、七段顯示器、指針錶
  - 追溯與標籤：追溯碼、包裝追溯碼、出貨標籤、銘牌
  - 文件：製造文件結構化
  - 工安：危險區域、安全帽
  - 其他：現場照片辨識、醫學影像分類（保留警語）
  - 管理：品檢紀錄與看板（Phase 18 後加：使用者、稽核；Phase 19 後加：主檔與配方）
- 分類與顯示名稱來自 `GET /api/modules`，不在前端寫死。
- `scripts/capture_screenshots.py` 同步更新。

### 17.5 Logging
- 統一 logging 設定（JSON 或 key=value 格式擇一），每個請求產生 `request_id`（回應 header `X-Request-ID`），寫進 log 與 `inspections` 新欄位 `request_id`。
- 模型載入、推論耗時、例外都要有 log；不可記錄 API key 與圖片內容。

### 驗收條件
- [ ] 註冊表完整性測試存在且通過；故意移除一個 extractor 時測試會失敗（附輸出）
- [ ] 用 `assembly`、`colordiff`、`codes`、`measure` 各做一筆 NG → 柏拉圖出現對應原因（瀏覽器實測截圖）
- [ ] M10 黃金樣本比對一次請求存下兩張圖（raw + golden）
- [ ] 新增一個假的測試用動作只需改註冊表一處，批次 API 與前端導覽自動出現（寫測試證明）
- [ ] 前端 17 個功能在新導覽下全部可用（Playwright 逐一點過，附截圖）
- [ ] 所有既有測試通過

---

## 6. Phase 18：使用者、角色、稽核（P0）

### 實作要點
- **本機帳號**：SQLite 新表 `users`（username、display_name、password_hash、role、is_active、created_at）。密碼雜湊用 **argon2-cffi**（查證授權）；登入後用 Starlette `SessionMiddleware`（簽章 cookie，`SESSION_SECRET` 從 `.env` 讀，未設定時拒絕啟動）。
- **角色**：
  - `operator`：執行檢驗、看自己的紀錄
  - `qc`：+ 複判、看板、匯出
  - `admin`：+ 使用者管理、主檔/配方、門檻與模型設定
- **移除 `FRONTEND_API_KEY`**：前端改用登入 session；`X-API-Key` 只留給系統對系統（ERP、`watch_folder.py`）。辨識端點改為「session 或 API key 二擇一」。
- `?api_key=` query 參數：前端改走 session 後就不需要，**移除**（ERP 本來就用 header）；若 watch_folder 或其他地方需要，開工前回報說明。
- `reviewer` 欄位改由登入者自動帶入；`operator` 追溯欄位預設帶登入者，可覆寫（產線常有代簽情況，保留彈性並記入稽核）。
- **稽核紀錄**：新表 `audit_log`（時間、使用者、動作、對象類型、對象 id、變更前 JSON、變更後 JSON）。至少記錄：複判、使用者新增/停用/改角色、門檻調整、黃金樣本/色差標準新增修改、自訂類別建立。管理分頁可查詢稽核紀錄。
- 首次啟動沒有任何 admin 時，用 `scripts/create_admin.py` 建立（不要在程式裡寫預設帳密）。
- 登入失敗次數限制（同一帳號連續 5 次失敗鎖 15 分鐘，數值可設定）。

### 驗收條件
- [ ] 未登入存取頁面導向登入；三種角色的權限邊界各有測試（operator 複判回 403 等）
- [ ] 前端原始碼 grep 不到任何 API key
- [ ] 複判後 `audit_log` 有變更前後值，reviewer 是登入者
- [ ] 沒設 `SESSION_SECRET` 時啟動失敗並顯示清楚訊息
- [ ] ERP（API key）與 `watch_folder.py` 照常運作（回歸測試）

---

## 7. Phase 19：主檔與檢驗配方（P1）

### 實作要點
- **主檔**（SQLite）：
  - `parts`（料號、品名、規格、客戶、啟用）
  - `work_orders`（工單號、料號、數量、狀態、開工/完工日）—— 可手動建立，也可由 ERP 同步（提供 `POST /api/master/work-orders:bulk-upsert`，API key 保護，ERP 推送用）
- **檢驗配方**（`inspection_recipes`、`recipe_steps`）：一個料號可有多版配方（只有一版啟用），每個步驟 = 註冊表中的一個動作 + 參數（例如：`codes`、`anomaly{category: screw}`、`measure{nominal: 50, tol: 1.0}`、`assembly{golden: SC-M6-20}`、`colordiff{L,a,b, max_de: 3.0}`）。參數用註冊表的 Pydantic model 驗證。
- **依配方執行**：`POST /api/inspect/recipe`（上傳圖片 + 工單號）→ 依序執行步驟 → 回傳每步結果 + **合併判定**（任一步 NG 即 NG；有步驟無法判定且沒有 NG 則 INFO）。資料庫新增 `inspection_runs`（一次配方執行）與既有 `inspections` 關聯（`run_id` 欄位），看板可以用 run 或單步兩種角度統計。
- 同一張圖給多個步驟共用；不同步驟需要不同圖時（例如正面、背面），配方步驟標記需要的圖片 slot，前端依配方動態產生上傳欄位。
- **追溯欄位改為選單**：工單從 `work_orders` 選，料號與批號自動帶入；仍允許「無工單的臨時檢驗」但會標記。
- 前端「管理 → 主檔與配方」頁：料號、工單、配方編輯（步驟排序、參數表單由 `GET /api/modules` 的參數 schema 自動產生）。
- 所有主檔/配方變更寫 `audit_log`。

### 驗收條件
- [ ] 建一個料號配方（codes + anomaly + measure），上傳一張圖跑完，三個步驟各一筆紀錄、一筆 run，合併判定正確（OK/NG/INFO 三種情境都有測試）
- [ ] 改配方參數 → 新版本；舊的 run 仍指向舊版本
- [ ] ERP bulk-upsert 工單 → 前端選單出現
- [ ] 舊的單一模組分頁仍可用（不強制走配方）

---

## 8. Phase 20：SPC 與品質報表（P1）

### 實作要點
- **量測資料正規化**：M2 量測值（長、寬、孔徑）與 M11 ΔE、M7 讀值寫入新表 `measurements`（inspection_id、料號、特性名稱、量測值、規格上下限、單位），不要每次從 `summary_json` 解析。
- **SPC**（純 numpy 實作，不需額外套件）：
  - X̄-R 管制圖（子群大小可設定，預設 5）、個別值-移動全距（I-MR）
  - Cp、Cpk（標示樣本數不足 25 個子群時「僅供參考」）
  - 異常規則：至少實作 Western Electric 規則 1–4，觸發點在圖上標紅並列出
  - `GET /api/spc?part_no=&characteristic=&from=&to=`
- 前端「管理 → SPC」頁：選料號與特性 → 管制圖（Chart.js）+ 能力指標 + 觸發規則清單。
- **報表**：
  - 日報/週報：總檢驗數、良率（AI/最終）、NG 柏拉圖、各站別良率、複判一致率、Cpk 摘要
  - 輸出 Excel（**openpyxl**，查證授權）與可列印 HTML（瀏覽器列印成 PDF，不引入 PDF 套件）
  - `scripts/daily_report.py` 可排程執行（說明用 macOS `launchd` 或 Windows 工作排程器，不在本專案內建排程器）

### 驗收條件
- [ ] 用已知數據（手算或 Excel 算好的範例）驗證 X̄、R、UCL/LCL、Cp、Cpk 數值一致（寫成測試）
- [ ] 刻意製造連續 7 點在中心線同一側的資料，規則正確觸發
- [ ] Excel 報表用 openpyxl 讀回驗證內容；中文不亂碼

---

## 9. Phase 21：模型與資料治理（P1）

### 實作要點
- **模型登錄**：`models/registry.json`（或 SQLite 表，開工前回報擇一）記錄每個模型：`model_id`、任務、版本、權重路徑、sha256、訓練資料集與授權、指標（AUROC/mAP50 等）、建立時間、狀態（active/archived）。
- 服務層從登錄表取 active 模型，不再寫死 `WEIGHTS_PATH`；管理頁可切換 active 版本（回滾），寫 `audit_log`。
- `inspections` 新增 `model_id` + `model_version`；舊紀錄為 NULL。
- **模型說明卡**：`docs/model-cards/<model_id>.md`，由 `scripts/gen_model_cards.py` 從登錄表＋`metrics.json` 產生，內容：用途、資料集與授權、指標、已知限制、不適用情境。
- **正式 migration**：新增 `schema_version` 表與 `backend/migrations/NNN_*.sql`（或 .py），啟動時依序套用；既有 `PRAGMA table_info` 補欄位邏輯整合為第 001 號 migration。不引入 Alembic（SQLite 為主、保持輕量），除非開工前回報有充分理由。
- **資料保存**：`IMAGE_RETENTION_DAYS`（預設 180）；`scripts/cleanup_images.py` 刪除過期圖片並把 `image_path` 標記為 `expired`（紀錄本身保留）；**有人工複判的圖片預設不刪**（再訓練資料來源）。
- **備份/還原**：`scripts/backup.py`（SQLite 用 `sqlite3` 的 online backup API，不是直接複製檔案 + 圖片打包 + 設定檔，不含 `.env` 祕密）、`scripts/restore.py`；還原前檢查 `schema_version`。

### 驗收條件
- [ ] 同一個 PCB 模型登錄兩個版本 → 切換 active → 新紀錄的 `model_version` 跟著變
- [ ] 從 Phase 15 的舊 db 走完全部 migration，資料完整（測試）
- [ ] 備份 → 刪除 data → 還原 → 看板數字與備份前一致
- [ ] 清理腳本不刪有複判的圖（測試）

---

## 10. Phase 22：可靠性與可觀測性（P2）

- `GET /healthz`（程序存活）、`GET /readyz`（逐項檢查：SQLite 可寫、各模組 `requires` 的權重存在、Ollama 可連線且模型已下載），回傳每項狀態。
- 前端「管理 → 系統狀態」頁：顯示每個功能是否可用與原因（例如「缺 PCB 模型權重，請執行 …」）；不可用的功能在導覽中標示灰色並顯示原因，而不是讓使用者按了才看到錯誤。
- **持久化工作佇列**：M3 自訂類別擬合的工作狀態存 SQLite（`jobs` 表），重啟後把 `running` 標為 `interrupted` 並可一鍵重試；`queued` 自動恢復排隊。
- webhook 重試同樣檢查重啟後是否正確恢復（既有 `webhook_queue` 已在 SQLite，補測試即可）。
- 可選：`/metrics`（**prometheus-client**，查證授權）輸出請求數、各模組推論耗時分佈、NG 數；只提供端點，不架 Prometheus。

### 驗收條件
- [ ] 拿掉某個權重檔 → `/readyz` 與系統狀態頁正確顯示，其他功能不受影響
- [ ] 擬合中重啟服務 → 工作變 `interrupted`，重試成功
- [ ] Ollama 關閉時，LLM 相關功能顯示不可用，非 LLM 功能照常

---

## 11. Phase 23：真實場景驗證與 CI（P2）

### 23.1 真實照片評估集
- `tests/real_samples/<module>/`：由我提供或自行拍攝、確認可公開的真實照片，每張附 `labels.json`（正確答案）。目標：M2 計數/量測、M7 七段/指針錶、M10、M11、M12 各 ≥ 5 張；手機相機拍照流程至少實測 1 次。
- `scripts/evaluate.py --module <m>`：跑評估集，輸出準確率、誤差、耗時到 `docs/evaluation.md`（表格，附測試日期與裝置）。**表現差就照實寫**，再決定是否改演算法（例如七段加透視校正/自適應二值化、指針錶自動找刻度）；改完重跑並保留前後數字。
- 若開工時我還沒提供照片：先完成腳本與目錄結構，評估結果寫「待補真實照片」，不可用合成圖冒充。

### 23.2 M8-1 包裝比對容錯
- 字元混淆正規化（O↔0、I↔1↔l、S↔5、B↔8、Z↔2）+ **rapidfuzz**（查證授權）相似度；結果分三級：一致 / 疑似（`INFO`，需人工確認）/ 不一致（`NG`）。M12 出貨標籤比對共用同一套比對函式。

### 23.3 CI
- `.github/workflows/ci.yml`：Python 3.11、`python scripts/check_wording.py`、`ruff check`、`ruff format --check`、`python tests/samples/make_samples.py && pytest`（不含 live/e2e）、coverage 報告（**pytest-cov**，查證授權）。
- 確認單元測試不需要大型權重/資料集（CI 上沒有）；需要的一律 mock，否則標 `live`。
- README 加 CI 徽章。workflow 只用 `runs-on: ubuntu-latest`（標準託管 runner），不用 larger runner、不用 self-hosted runner（查證目前條款：self-hosted runner 是否另計費用），不用需要付費帳號的第三方 Action/服務（例如 coverage 上傳到外部平台）；coverage 只在 Actions log 與 artifact 中輸出。查證「公開 repo 標準 runner 免費」的最新條款並寫進 licenses.md。
- 把 `scripts/capture_screenshots.py` 的流程改寫為 `pytest -m e2e`（Playwright，預設不跑，本機手動執行）。

### 驗收條件
- [ ] CI 在 GitHub 綠燈（附 Actions 連結）
- [ ] `docs/evaluation.md` 每個列出的模組都有「真實照片實測」或「待補真實照片」其中一種狀態，不可空白
- [ ] `LOT0O1` vs `LOT001` 判「疑似」；完全不同判 NG；原有包裝/出貨測試通過（需更新期望值時說明原因）

---

## 12. Phase 24：容器化部署、ERP 端到端、v1.0.0（P2）

- **容器化**：`Dockerfile`（多階段、非 root 使用者、`models/` 與 `data/` 用 volume）+ `compose.yaml`（app + ollama）。**以免費開源的容器執行環境為準**：macOS 用 Colima（或 Podman）、Linux 用 Docker Engine，實測也用這些工具跑；admin-guide 寫清楚 Docker Desktop 的免費條件，只列為「符合條件者可選用」，不作為安裝需求。基底映像只用官方免費映像（例如 `python:3.11-slim`、`ollama/ollama`），不用需訂閱的映像倉庫。
- **Windows 部署說明**：路徑處理檢查（全用 `pathlib`）、原生安裝步驟；沒有 Windows 機器可測就寫「未在 Windows 實測」與已知差異。
- **ERP 端到端**：在 compose 加可選的 SQL Server 容器，**只能用 Express 或 Developer 版**（查證兩者的免費條款：Developer 版僅限開發測試、Express 版有容量/資源上限，寫進 licenses.md），並查證 Apple Silicon 相容性（官方 Linux 映像可能只有 x86_64，需模擬執行），跑 `docs/erp-integration-sample/` 實際輪詢 → 寫入 → 查詢，把結果寫進 `docs/erp-integration.md`。**Apple Silicon 上跑不起來就照實記錄**，改提供 SQLite 版的整合測試證明輪詢邏輯正確。
- **效能基準**（可選，只用本機 CPU 測，不租用任何雲端機器）：`scripts/benchmark.py` 記錄各模組在本機 CPU 的平均/P95 延遲與記憶體，輸出 `docs/benchmark.md`；ONNX 匯出只在實測確實有改善時才納入預設。
- **發佈 v1.0.0**：更新 CHANGELOG、`pyproject.toml` 版本、README 快速開始、打 git tag `v1.0.0`（push tag 前先問我）。

### 驗收條件
- [ ] 乾淨環境 `docker compose up` → 登入 → 至少 5 個功能實測成功（若本機無法跑 Docker，照實記錄原因）
- [ ] ERP 端到端有實測結果或明確的失敗原因與替代驗證
- [ ] README 快速開始照著做可以從零啟動（在新 clone 的目錄實際走一次）

---

## 13. 本輪不做（寫進 README「未納入功能」，用產品語言說明）

- 高速產線即時檢測、PLC/工業相機觸發：需要專用硬體。
- SSO／LDAP／AD 整合：本版提供本機帳號與角色，企業目錄整合留待後續版本。
- 雲端託管版本：需付費主機；本版以地端部署為主。
- 任何需要付費、綁信用卡、試用期後轉付費的工具或服務；付費 API、付費標註服務、付費雲端主機/GPU；授權不明的資料集。
- RTSP 攝影機串流、跌倒偵測：先前已決定不納入，本輪維持。

---

## 14. 完成回報格式

```
## Phase N 完成回報
### 做了什麼
- ...
### 驗收條件
- [x] 條件 —— 證據：<指令輸出 / 數字 / 截圖路徑 / 測試名稱>
- [ ] 條件 —— 未完成原因：...
### 設計決策與取捨
- ...
### 新增套件（已寫入 docs/licenses.md）
| 套件/服務 | 版本 | 授權 | 費用（免費條件） | 可商用 | 官方條款連結 | 查證日期 |
### 測試
- pytest：N 項全過（X 秒）｜pytest -m live：...｜e2e：...
### 免費檢查
- 本 Phase 新增/使用的工具全部為免費：是／否（否則列出並說明替代方案）
### 用詞檢查
- scripts/check_wording.py：0 筆
### 下一個 Phase 開工前需要我決定的事
- ...
```

# Claude Code 任務：把 vision-ai-demo 重新規劃成「台中製造業 AI 辨識 Demo」

> 使用方式：在 `~/Documents/vision-ai-demo` 開 Claude Code，把本檔整份貼上（或輸入「請讀 docs/manufacturing-ai-plan-prompt.md 並依照執行」）。

---

## 0. 背景與目標

這個專案目前只有兩個功能：①街景照片通用辨識（Gemini）②文件轉結構化資料（Tesseract + Gemini）。
現況與限制請先讀 `CLAUDE.md`、`README.md`、`backend/*.py`，特別注意：**Gemini 免費層 RPM=5、RPD=20**，不能當核心引擎。

新目標：改造成「**台中製造業常見 AI 辨識功能**」的作品集 Demo，對應台中／中科產業（工具機與精密機械、手工具、螺絲扣件、自行車零件、金屬加工/CNC、PCB 與電子、醫材與藥品包裝），作為我應徵台中製造業 AI／ERP／MIS 工程師的作品。
它之後會和我的另一個專案 `manufacturing-erp`（ASP.NET Core + SQL Server，含品檢查詢）串接，所以辨識結果要有穩定的 JSON 結構與檢驗紀錄。

## 1. 硬性規則（每個階段都要遵守）

1. **只能用免費工具**：開源套件、免費資料集、免費 API 額度。找不到免費方案的功能**直接跳過，不要規劃、不要寫假的 stub**，並在 README「未納入功能」列出原因。
2. **核心功能必須能完全離線執行**（本機模型），不依賴 Gemini 配額。LLM 只用在「文件欄位結構化」與「開放式描述」，而且預設用 **Ollama 本機模型**，Gemini 免費層只當可選的備援引擎（用 `.env` 的 `LLM_ENGINE=ollama|gemini` 切換）。
3. **安裝前先查證**：每個套件、模型、資料集，先到官方 GitHub／PyPI／官網確認「目前最新版本」與「授權條款」，把查證結果寫進 `docs/licenses.md`（名稱、版本、授權、是否可商用、來源連結）。不要憑記憶寫版本號。
4. 資料集授權是非商用（如 MVTec AD 的 CC BY-NC-SA）的，要在 README 註明「僅供學習/作品集展示」。
5. **分階段執行**：每做完一個 Phase，停下來回報「做了什麼、實際測試結果、遇到的問題」，等我確認再進下一個 Phase。不要一次產生全部程式碼。
6. **測試結果不可捏造**：只記錄實際跑出來的數字（準確率、推論時間、截圖）。沒跑過就寫「未測試」。
7. 大檔（模型權重、資料集、訓練輸出）一律放 `models/`、`data/`、`runs/` 並加進 `.gitignore`，改用 `scripts/download_*.py` 下載。commit 前照舊用 grep 掃過沒有 API key。
8. 我的機器是 Apple Silicon Mac：PyTorch 用 `mps` 裝置，不支援時自動退回 `cpu`。需要 GPU 訓練的步驟另外提供 Google Colab 免費版的 notebook（`notebooks/`）。
9. Python 升級到 3.11（Anomalib 等套件需要 ≥3.10），重建 venv，並更新 README 安裝步驟。

## 2. 功能規劃（依優先順序）

| 代號 | 功能 | 台中產業對應情境 | 免費工具 | 是否需訓練 |
|---|---|---|---|---|
| M1 | 追溯碼辨識（QR / 條碼 / DataMatrix / GS1 UDI） | 工單條碼、零件 DataMatrix 雷刻、醫材 UDI | `zxing-cpp`（Apache-2.0）、OpenCV | 否 |
| M2 | 零件計數與尺寸量測 | 螺絲螺帽計數包裝、CNC 零件尺寸公差判定 | OpenCV（含 contrib 的 ArUco 標定） | 否 |
| M3 | 外觀瑕疵異常檢測（只需良品） | 金屬件、螺絲、磁磚、塑膠射出件外觀檢 | Anomalib PatchCore（Apache-2.0）＋ MVTec AD 資料集（CC BY-NC-SA） | 輕量（只擬合良品特徵） |
| M4 | 製造文件結構化 | 工單、出貨單、進料檢驗報告、報價單、名片 | PaddleOCR / PP-Structure（Apache-2.0）；Mac 安裝不順則用 RapidOCR（onnxruntime）；Ollama 本機視覺/語言模型 | 否 |
| M5 | 工安辨識 | 危險區域（機台周邊）人員入侵、安全帽/反光背心 | Ultralytics YOLO（AGPL-3.0，公開 repo 可用）COCO 預訓練模型；PPE 用公開資料集（如 Roboflow Universe 上 CC BY 4.0 的 hard-hat 資料集，需先查證授權） | 區域入侵：否；PPE：是 |
| M6 | 監督式瑕疵分類定位 | 鋼材表面瑕疵（刮痕、麻點、夾雜…）、PCB 瑕疵 | Ultralytics YOLO ＋ NEU-DET 鋼材表面瑕疵資料集（先做）；DeepPCB（第二步，選做） | 是（Mac MPS 或 Colab） |
| M7 | 銘牌／刻印／儀表讀值 OCR | 工具機銘牌型號序號、批號效期、七段顯示器讀數、指針式壓力錶 | PaddleOCR/RapidOCR；指針錶用 OpenCV（Hough 直線 + 角度換算） | 否 |
| M8 | 醫療相關辨識 | 中部醫材/藥品廠：包裝批號、效期、UDI 檢核；醫學影像分類教學展示 | M1+M7 重用；影像分類用 MedMNIST（CC BY 4.0）+ PyTorch（或 MONAI，Apache-2.0） | 影像分類：是（小模型，CPU 可跑） |
| M9 | 開放式辨識（原街景功能改造） | 未知零件、工具、現場照片的開放式描述 | Ollama 本機視覺模型（預設）／Gemini 免費層（備援） | 否 |

### 各功能細節

**M1 追溯碼辨識**
- 一張圖可含多個碼，回傳每個碼的類型、內容、四角座標，並畫框。
- GS1 格式解析：`(01)` GTIN、`(10)` 批號、`(17)` 效期、`(21)` 序號，醫材 UDI 用得到（自己寫 parser，不需付費函式庫）。
- 效期已過或 30 天內到期要標紅/標黃。

**M2 計數與量測**
- 計數：背景分離 → 輪廓 → 依面積過濾 → 分群計數；處理零件相黏（distance transform + watershed）。
- 量測：畫面放一個 ArUco 標記（提供可列印 PDF，`scripts/make_aruco.py`）或已知尺寸參考物，換算 mm/px；輸出長、寬、孔徑，並依使用者輸入的「標準值 ± 公差」判 OK/NG。
- 在 README 誠實寫出精度限制（手機拍攝、透視變形），並用透視校正降低誤差。

**M3 異常檢測（本 Demo 最重要的製造業功能）**
- 用 MVTec AD 的 `metal_nut`、`screw`、`tile` 三類示範（貼近螺絲扣件與金屬加工）。
- 每類先離線擬合（`scripts/train_anomaly.py --category screw`），權重存 `models/anomaly/`。
- API 回傳：異常分數、門檻、OK/NG、異常熱力圖疊圖（base64 PNG）。
- 用資料集的測試集實際算出 image-level AUROC，寫進 README（不可估計）。
- 說明賣點：工廠通常缺 NG 樣本，這種方法只需要良品照片。

**M4 製造文件結構化**
- OCR 從 Tesseract 換成 PaddleOCR（保留 Tesseract 當比較選項）；表格用 PP-Structure 或版面分析輸出成表格陣列。
- 預定義文件類型與欄位 schema（放 `backend/schemas/`，用 Pydantic）：
  - 工單：工單號、料號、品名、數量、開工/完工日、製程站別
  - 出貨單：單號、客戶、日期、品項[料號/品名/數量/單價]、總額
  - 進料檢驗報告：供應商、料號、批號、抽樣數、不良數、判定
  - 報價單、名片（沿用原本）
- LLM 只做「OCR 文字 → 符合 schema 的 JSON」，用 Pydantic 驗證，驗證失敗要回傳錯誤欄位而不是硬塞。數字欄位要能回溯到 OCR 原文（附上原文片段），避免 LLM 捏造數字。
- 預設引擎 Ollama（模型請查證目前 Ollama 上可用、支援繁中的模型，例如 Qwen 系列，並依我 Mac 的記憶體挑 7B 左右的大小），Gemini 備援。

**M5 工安**
- 先做「危險區域入侵」：YOLO COCO 預訓練 person 偵測 + 使用者在前端畫多邊形區域 → 判斷人是否在區內。免訓練，優先完成。
- 再做 PPE：查證一個可免費使用的安全帽/背心資料集，訓練 YOLO 小模型（n 或 s 版），在 Colab 或 MPS 上跑，記錄 mAP。
- 支援圖片與短影片（逐幀抽樣，不做即時串流）。

**M6 監督式瑕疵**
- NEU-DET 六類鋼材瑕疵，YOLO 偵測模型；附訓練 notebook、混淆矩陣、mAP50 實測值。
- 跟 M3 在前端並排比較：「非監督（只要良品）vs 監督（需要標註 NG）」的差異，這是面試時的說明重點。

**M7 銘牌／儀表**
- 銘牌：OCR 後用規則 + LLM 抽出「廠牌、型號、序號、製造日期、電壓」。
- 七段顯示器：先試 OCR，準度不足再做 OpenCV 七段分段判讀。
- 指針錶：使用者輸入最小/最大刻度與對應角度，OpenCV 找指針角度換算讀值。

**M8 醫療相關**
- M8-1 藥品/醫材包裝檢核：同一張包裝照片同時跑 M1（UDI 條碼）+ M7（印刷批號效期 OCR），比對兩者是否一致，不一致標 NG。這是 GMP 追溯的真實需求。
- M8-2 醫學影像分類「教學展示」：MedMNIST 的 PneumoniaMNIST（胸腔 X 光肺炎/正常），小型 CNN，CPU 可訓練，報告測試集準確率與 AUC。前端與 README 必須明顯標示「**僅供技術展示，非醫療診斷用途**」。
- 不做任何需要真實病患資料或付費醫療 API 的功能。

**M9 開放式辨識**
- 原 `vision_scan.py` 改為「現場照片開放式描述」，prompt 改成製造業情境（辨識機台、工具、零件、標示、現場安全狀況）。
- 預設 Ollama 視覺模型，Gemini 備援；保留原本的配額錯誤處理邏輯。

### 未納入（沒有免費方案或需要硬體，只寫進 README 說明）
- 商用 AOI／機器視覺軟體（Cognex VisionPro、MVTec HALCON、Keyence）：付費。
- 3D 量測、雷射輪廓、熱影像檢測：需要專用硬體。
- 產線高速即時檢測（工業相機 + PLC 觸發）：需要硬體，本 Demo 只做單張圖/短影片。
- 焊道 X 光、刀具磨耗影像：公開資料集授權不明確或取得困難，查證後若找不到明確免費授權就不做。
- 振動/聲音預測保養：不屬於影像辨識，也需要感測器，不納入。
- Google Cloud Vision / Azure AI Vision：免費額度有限且需綁信用卡，不使用。

## 3. 架構調整

```
vision-ai-demo/
├── backend/
│   ├── main.py                 # FastAPI 入口，只負責掛載各模組 router
│   ├── core/
│   │   ├── schemas.py          # 共用回應格式
│   │   ├── image_io.py         # 讀圖、EXIF 轉正、縮圖、畫框、base64
│   │   ├── llm.py              # Ollama / Gemini 抽象層（LLM_ENGINE 切換）
│   │   └── inspection_log.py   # SQLite 檢驗紀錄
│   ├── modules/
│   │   ├── codes/  measure/  anomaly/  docs/  safety/
│   │   ├── defect/  nameplate/  medical/  general/
│   │   └── 每個模組：router.py + service.py
│   └── schemas/                # M4 文件欄位 Pydantic schema
├── frontend/index.html         # 分頁式單頁（每個模組一個分頁），維持純 HTML/JS
├── scripts/                    # 下載資料集/模型、訓練、產生 ArUco
├── notebooks/                  # Colab 訓練 notebook
├── tests/                      # pytest；測試圖用程式自動生成或授權允許的小圖
├── docs/licenses.md
├── models/ data/ runs/         # gitignore
```

- **共用回應格式**（所有模組一致，方便之後 ERP 串接）：
  ```json
  {
    "module": "anomaly",
    "verdict": "OK | NG | INFO",
    "items": [ ... 模組自訂明細 ... ],
    "annotated_image": "data:image/png;base64,...",
    "engine": "anomalib-patchcore",
    "elapsed_ms": 123,
    "inspection_id": 42
  }
  ```
- **檢驗紀錄**：每次辨識寫一筆 SQLite（時間、模組、判定、摘要 JSON），提供 `GET /api/inspections?module=&verdict=&from=&to=` 查詢，並可匯出 CSV。這是之後 `manufacturing-erp` 品檢模組要讀的資料。
- 模型用「首次呼叫時載入並快取」，缺權重時回傳清楚錯誤：「請先執行 scripts/xxx.py」。
- `test_all.sh` 裡寫死的暫存路徑要改掉，改成 pytest + `tests/samples/`。

## 4. 執行階段（每階段結束都停下來等我確認）

- **Phase 0 規劃確認**：讀完現有程式碼後，先回報你要安裝的套件清單＋查證後的版本與授權（寫進 `docs/licenses.md`），以及 Mac 上可能的安裝風險（例如 PaddlePaddle 在 Apple Silicon 的支援狀況）。先不要寫程式。
- **Phase 1 重構骨架**：Python 3.11 venv、目錄重構、共用 schema、LLM 抽象層（Ollama/Gemini）、檢驗紀錄 SQLite、前端改分頁。原有兩個功能搬進 M4/M9 且仍可運作。
- **Phase 2 免訓練快速功能**：M1 追溯碼、M2 計數量測、M5 危險區域入侵。
- **Phase 3 異常檢測**：M3（Anomalib + MVTec AD），實測 AUROC。
- **Phase 4 製造文件**：M4（PaddleOCR/RapidOCR + schema + Ollama），用我提供或自行生成的範例工單/出貨單測試。
- **Phase 5 需訓練的偵測**：M6 NEU-DET、M5 PPE（附 Colab notebook 與實測 mAP）。
- **Phase 6 銘牌儀表**：M7。
- **Phase 7 醫療相關**：M8-1 包裝檢核、M8-2 MedMNIST 教學展示。
- **Phase 8 收尾**：更新 `CLAUDE.md`（技術決策、實測紀錄）、`README.md`（功能表、安裝、未納入功能、授權說明、Demo 截圖）、每個 Phase 各自一個清楚的 commit，推上 GitHub。

## 5. 每個 Phase 的完成定義

- API 用 curl 或 pytest 實際打過，貼出真實回應片段。
- 前端分頁在瀏覽器實際操作過一次。
- 準確度類指標（AUROC、mAP、準確率）只寫實際跑出的數字，附測試集名稱與樣本數。
- `CLAUDE.md` 待辦清單勾選並記錄踩到的坑（像之前 RPD 配額的教訓那樣寫清楚真正原因）。

請從 **Phase 0** 開始。

# 測試紀錄（真實驗證，非猜測）

> 原本位於 `CLAUDE.md`，Phase 16 起搬到此處，數字原文保留。

### Phase 0：套件安裝查證
- 用 `uv pip compile` 在暫存 venv 對 Python 3.11 / macOS arm64 實際解析整組套件相依，並實裝驗證 import：`torch 2.14`（`torch.backends.mps.is_available() == True`）、`anomalib 2.6.2`（`Patchcore` 可 import）、`ultralytics 8.4.160`、`rapidocr`、`onnxruntime 1.30`、`zxingcpp`、`medmnist`、`cv2 5.0`（`cv2.aruco.ArucoDetector` 存在）全部成功。
- 查出 PaddleOCR 在此環境會被相依解析器拖回 2.10.0 舊版（`paddlex` 要求 `numpy<2.4`），改用 RapidOCR。

### Phase 1：功能驗證
- **單元測試**：`pytest`，13 項全過（0.98 秒），涵蓋 M9/M4 兩個 API 的正常路徑、共用回應格式欄位、SQLite 寫入與查詢/CSV 匯出、空檔案/非圖片/錯誤 mode 的錯誤處理、LLM 抽象層的無效引擎/連線失敗/模型不存在/缺 API key 錯誤訊息。
- **Live 測試（真打本機 Ollama `qwen3.5:9b`）**：`pytest -m live -s`，3 項全過（52 秒）。
  - M9：警示標示測試圖，正確讀出「危險 DANGER」「機台運轉中 請勿靠近」等可見文字，信心程度「高」且理由合理，耗時約 20 秒（第一次呼叫含模型載入）。
  - M4 OCR 模式：正確判斷文件類型「工單」，料號 `SC-M6-20` 正確；但 Tesseract 把工單號 `WO-2026-0915` 誤讀成 `WO-2026-0215`，LLM 照抄了這個錯誤（符合設計：LLM 不能捏改 OCR 原文）。耗時約 14 秒。
  - M4 端到端模式：同一張圖，AI 直接讀圖，工單號 `WO-2026-0915` 正確、品名 `六角螺栓 M6x20` 也比 OCR 模式的 `Mox20` 準確。耗時約 17 秒。
  - **結論驗證**：這組結果重現了原本 README 記載的「端到端準確度較高、OCR 較快但可能誤判」的結論，這次的錯誤案例（`0915→0215`）具體可追蹤到 Tesseract 的數字誤讀，不是 LLM 捏造的。
- **瀏覽器實測**（真實 Chrome，`mcp__claude-in-chrome__*`，內嵌瀏覽器不支援檔案選擇對話框）：兩個分頁都實際上傳圖片並點擊按鈕，M9 分頁 8.4 秒後正確顯示結果卡片（含 engine/verdict/耗時徽章），M4 分頁 13.5 秒後正確顯示工單欄位；`GET /api/inspections` 確認該次辨識已寫入 SQLite。

### Phase 2：功能驗證
- **單元測試**：`pytest`，29 項全過（1.49 秒）。新增 M1（GS1 解析、已過期/即將到期/正常三種效期狀態、找不到條碼、空檔案）、M2（相黏零件分離、預期數量 OK/NG、量測精度、公差 OK/NG、找不到 ArUco 標記的錯誤訊息）、M5（假偵測結果驗證多邊形入侵邏輯、無效 zone JSON、頂點數不足）。
- **開發中抓到的真實 bug**：M2 計數一開始用「distance transform 整塊閾值」分割相黏零件，實測把兩顆相黏的圓當成一顆（面積 7088px²，是單顆 3745px² 的 1.9 倍），不是我猜測的——是真的跑出來發現數字不對。改用「距離變換的局部極大值當種子點」後正確分離成 8 顆（相黏那兩顆分別是 3544px²、3501px²，跟其他分開的零件面積相近）。
- **Live 測試（真打本機模型）**：`pytest -m live -s`，4 項全過（59 秒）。
  - M9/M4（沿用 Phase 1 案例）：結果與 Phase 1 一致，qwen3.5:9b 穩定重現。
  - M5：用真實 CC BY 2.0 授權照片（Wikimedia Commons，工廠操作員照片，5697x3798），YOLO11n 以 95.1% 信心度正確偵測到 1 人，邊界框 `[723,23,3048,3758]` 跟畫面中人物位置吻合；涵蓋人物的區域判定入侵，涵蓋畫面右側（無人）的區域判定沒入侵。
- **量測精度實測**（非估計）：正視角、已知 50x20mm 矩形 + 5mm 孔的合成場景，量出 50.6mm / 20.3mm / 孔徑 5.42mm，誤差 0.3-0.6mm（約 1%），來源是 ArUco 邊界像素化與二值化邊緣效應；因此把預設公差從規劃的 0.5mm 調整為 1.0mm。
- **GS1 條碼格式實測確認**：一開始以為要自己處理 FNC1（`\x1d`）分隔符號，寫死用 `\x1d` 當分隔字元建立測試條碼直接被 `zxing-cpp` 拒絕（`Control characters are not supported by GS1`）；查了才知道要用 `(AI)值` 的 HRI 格式＋`gs1=True` 參數建立，且解碼出來的 `text` 欄位本來就是這個格式，不需要自己寫 FNC1 解析器。
- **瀏覽器實測**（真實 Chrome）：五個分頁全部實際操作過。
  - M1：上傳 GS1 DataMatrix 測試圖，9ms 解碼出正確的 GTIN/批號/序號/效期，標註圖顯示綠色框（效期正常）。
  - M2：計數分頁 35ms 數出 8 顆並判定 OK（預期 8）；量測分頁 100ms 量出跟 curl 測試一致的數字。
  - M5：上傳真人照片，用滑鼠在 canvas 上點擊畫出涵蓋人物的多邊形（第一次點擊的多邊形底邊差了幾像素沒蓋到腳底參考點，NG 判定漏掉——這是操作精度問題，不是程式邏輯錯，重畫涵蓋到畫面底部邊緣後正確判定 NG，標註圖清楚顯示半透明紅色危險區域疊圖與紅色人員邊界框）。

### Phase 3：功能驗證

- **實測 image-level AUROC（官方測試集，非估計）**：
  | 類別 | AUROC | 測試集張數 | 擬合耗時（CPU） |
  |---|---|---|---|
  | metal_nut | **0.9985** | 115 | 322 秒 |
  | screw | **0.9645** | 160 | 664 秒 |
  | tile | **0.9993** | 117 | 406 秒 |

  數字來自 `scripts/train_anomaly.py` 呼叫 `anomalib.engine.Engine.test()`，跑的是 MVTec AD 官方切分的完整測試集（含良品與各種瑕疵子類別），不是抽樣估計；各自存在 `models/anomaly/<category>/metrics.json`。
- **開發中發現的真實問題（MPS 比 CPU 慢）**：一開始照 Phase 0 規劃用 `torch.backends.mps.is_available()` 自動選 MPS，metal_nut 跑了 10 幾分鐘幾乎沒有進度（CPU 時間幾乎不動）。用 macOS `sample` 系統工具對執行中的程序抓呼叫堆疊，兩次都停在 `at::mps::MPSStream::synchronize`，往上追是 PatchCore 的 coreset 貪婪演算法在 Python 迴圈裡逐元素呼叫 `tensor.item()`，每次都要等一次 GPU 同步。改成固定用 CPU 後，metal_nut 5.4 分鐘內就跑完，而且 AUROC 數字相同（CPU/MPS 只影響速度不影響數值）。
- **過程中一度誤判「訓練卡死」**：screw 訓練到一半，主行程 CPU 降到 0.1%、8 個 dataloader 子行程也全部 0% CPU、狀態都是 sleeping，看起來像死鎖。連續觀察 40 秒後發現其實是「忙閒交替」（0.1% → 256% → 484% → 123%），是 dataloader worker 在測試階段重新產生子行程造成的正常波動，不是真的卡死。教訓：判斷「有沒有卡死」不能只看瞬間 CPU 數字，要連續觀察一段時間或直接用 `sample` 抓呼叫堆疊確認在算什麼。
- **anomalib 的資安機制**：`TorchInferencer` 載入權重時預設會擋下 unpickle（`ValueError: ... requires executing arbitrary code via Python's pickle module`），第一次串接時被這個錯誤擋住；查證後確認這是防止載入惡意權重的正常機制，因為載入的是自己訓練產生的檔案，設定 `TRUST_REMOTE_CODE=1` 才能載入（僅在服務層這個載入點設定，不影響全域環境）。
- **真實測試集圖片驗證**：直接呼叫 `inspect_part()`（不透過假推論），用 MVTec AD 官方測試集的良品與瑕疵品各測了幾張，全部判定方向正確：
  - metal_nut：`good` → OK（分數 0.35-0.41）；`bent` → NG（分數 0.9971-1.0）；`scratch` → NG（分數 0.54-0.83）
  - screw：`good` → OK（分數 0.49）；`scratch_head` → NG（分數 0.88）
  - tile：`good` → OK（分數 0.34-0.42）；`crack` → NG（分數 1.0）
- **live 測試（`pytest -m live`，用官方測試集抽樣，非人工挑選）**：3 個類別全過，screw 抽樣 11/13、tile 抽樣 13/13、metal_nut 抽樣全過（門檻 70% 正確率）。
- **瀏覽器實測**（真實 Chrome）：M3 分頁上傳 metal_nut 的刮痕瑕疵圖，1668ms 判定 NG（分數 0.8291），熱力圖疊圖清楚把紅色熱區精準標在刮痕位置上；換成 tile 的裂痕瑕疵圖、切換下拉選單到 `tile` 類別，4081ms 判定 NG（分數 1.0）。
- **磁碟清理**：訓練時 anomalib Engine 預設會把每一張測試圖的視覺化結果存到 `models/anomaly/_engine_logs/`，三個類別累積到 822MB，訓練完成、metrics.json 記錄下數字後就刪掉了（不影響推論，推論只需要 `weights/torch/model.pt`）。

### Phase 4：功能驗證

- **RapidOCR vs Tesseract 準確度實測對比**（同一張測試圖，非分別測不同圖）：工單號 `WO-2026-0915`，Tesseract 讀成 `WO-2026-0215`（0915 誤讀成 0215，跟 Phase 1 記錄的坑一樣），RapidOCR 完全讀對。這是這個 Phase 換引擎最直接的證據。
- **表格辨識實測**：出貨單測試圖（2 列品項的格線表格）用 `RapidTable` 解析，正確輸出 `<table><tr><td>料號</td>...` 的 HTML，兩列資料一字不差；餵給 LLM 後兩個品項的料號/品名/數量/單價全部正確解析成 JSON。
- **單元測試**：`pytest`，新增 `tests/test_docs.py` 11 項（RapidOCR 真的跑、LLM 用假佇列模擬兩段式呼叫），涵蓋：工單正常解析＋來源驗證 OK、來源片段查無此文字標「可疑」、缺必要欄位觸發 Pydantic 驗證錯誤（`_驗證錯誤` 列出所有缺漏欄位、不硬塞預設值）、出貨單表格解析、進料檢驗報告「判定」欄位限制合格/不合格（給無效值會被 Pydantic 拒絕）、報價單等自由格式類型不套 schema、端到端模式的「來源驗證」誠實標記「無法驗證」、Tesseract 比較模式的 engine 名稱正確、空白圖片在呼叫 LLM 之前就被擋下。全專案累計 41 項單元測試全過（11.5 秒）。
- **live 測試（真打本機 Ollama，完整兩段式流程）**：`pytest -m live -s`，3 項全過（41 秒），三種嚴格 schema 文件都測了：
  - 工單：`WO-2026-0915` 正確、數量 5000、來源驗證 OK
  - 出貨單：2 個品項全部正確、總額 6500、來源驗證 OK（含表格解析）
  - 進料檢驗報告：抽樣數 50、不良數 2、判定「合格」，全部正確
- **瀏覽器實測**（真實 Chrome）：M4 分頁上傳進料檢驗報告圖片，8635ms 後正確顯示文件類型、供應商、料號、批號，數量欄位展開成 `{值, 原文片段, 來源驗證}` 巢狀物件並顯示「OK：原文中找得到這段文字」。
- **未使用但已安裝的套件**：`rapid-layout` 裝了但這個 Phase 沒用到（三種文件都是單一區塊版面，不需要版面分析），誠實記錄在 CLAUDE.md 技術決策，不假裝有用上。

### Phase 5：功能驗證

- **M6 PCB 瑕疵偵測訓練實測**：`scripts/prepare_deeppcb.py` 把 1500 張官方標註轉成 YOLO 格式（1000 train / 250 val / 250 test，固定種子切分）。`YOLO11n` 在 MPS 上訓練，41 epoch 後 early stopping（`patience=15`，最佳結果在 epoch 26），總耗時 **32.1 分鐘**（0.535 小時）。官方測試集（250 張）實測：
  | 類別 | mAP50 | mAP50-95 | Precision | Recall |
  |---|---|---|---|---|
  | 全部 | **0.978** | 0.735 | 0.964 | 0.945 |
  | open（斷路） | 0.988 | 0.674 | 0.949 | 0.979 |
  | short（短路） | 0.958 | 0.626 | 0.941 | 0.912 |
  | mousebite（缺口） | 0.969 | 0.710 | 0.957 | 0.921 |
  | spur（毛刺） | 0.977 | 0.711 | 0.961 | 0.948 |
  | copper（多餘銅箔） | 0.982 | 0.845 | 0.992 | 0.944 |
  | pin-hole（針孔） | 0.992 | 0.845 | 0.983 | 0.968 |

  數字來自 `models/defect/pcb_yolo11n/results.csv`（逐 epoch 訓練曲線）與訓練結束時對 `best.pt` 在官方測試集切分上的驗證輸出，不是估計值。
- **一開始以為訓練卡死，其實是我自己檢查錯路徑（真實 bug，不是猜的）**：訓練指令用 `project='models/defect'`（相對路徑），但 ultralytics 會把全域設定的 `runs_dir`（預設 `"runs"`）加在相對 `project` 路徑前面，實際輸出到 `runs/detect/models/defect/pcb_yolo11n/`，不是我以為的 `models/defect/pcb_yolo11n/`。我一直檢查後者有沒有 `results.csv`，30 分鐘都看不到檔案，一度以為訓練卡死（用 `sample` 系統工具反覆確認 CPU 真的在算 conv2d/autograd，排除死鎖），後來訓練其實已經在正確路徑正常寫入，41 epoch 全部跑完只花 32 分鐘。教訓：往後呼叫 `YOLO().train(project=...)` 一律用絕對路徑，PPE 訓練已經改用絕對路徑，沒有重踩這個坑。
- **真實資料推論驗證**：直接呼叫 `detect_pcb_defects()`（不透過假推論）測 DeepPCB 測試集圖片，正確判定 NG 並抓出全部 8 個標註瑕疵，涵蓋 6 種類型全部命中。
- **live 測試**：`pytest -m live`，DeepPCB 測試集抽樣 10 張，10 張全部判定 NG（資料集設計每張圖本來就有 3-12 個瑕疵）。
- **瀏覽器實測**（真實 Chrome）：M6 分頁上傳測試圖，1513ms 判定 NG、偵測到 8 個瑕疵，標註圖用紅框精準框出每個瑕疵位置並標上類型與信心度，跟明細清單完全對應。
- **M5 PPE 訓練實測**：`scripts/prepare_hardhat.py` 沿用資料集官方 Train(5297)/Test(1766) 切分，只留 helmet/head 兩類（跳過極少數的 person/others 類別）。訓練用絕對路徑 `project`（避開上面踩到的坑），資料量是 PCB 的 5.3 倍，跑滿全部 60 epoch（沒有提早停止，`patience=15` 全程都還在緩慢進步），總耗時 **4.15 小時**。官方測試集（1766 張）實測：
  | 類別 | mAP50 | mAP50-95 | Precision | Recall |
  |---|---|---|---|---|
  | 全部 | **0.977** | 0.680 | 0.948 | 0.942 |
  | helmet（已戴安全帽） | 0.982 | 0.682 | 0.959 | 0.942 |
  | head（未戴安全帽） | 0.972 | 0.678 | 0.938 | 0.941 |

  訓練曲線見 `models/ppe/ppe_yolo11n/results.csv`；mAP50 從 epoch1 的 0.913 緩步爬升到最終 0.977，中間沒有劇烈震盪，是穩定收斂，不是運氣。
- **真實資料推論驗證**：直接呼叫 `detect_ppe()` 測 Hard Hat Workers 驗證集，good 案例（多人合照有安全帽）正確判 OK；抓 5 張標註含「未戴安全帽」的圖測試，4/5 正確判 NG（1 張漏判，跟 recall 0.941<1 的實測數字吻合，不是我瞎猜的容錯率）。
- **live 測試**：`pytest -m live`，驗證集抽樣 10 張，全部成功偵測到人頭（2 張 NG、7 張 OK、1 張沒偵測到人頭判 INFO）。
- **瀏覽器實測**（真實 Chrome）：M5 PPE 分頁上傳一張 8 人合照（官方標註全部未戴安全帽），993ms 判定 NG、8/8 正確抓到未戴安全帽，標註圖用紅框精準框出每個人頭並標「未戴安全帽 0.xx」信心度。

### Phase 6：功能驗證

- **先實測 OCR 再決定走向（不是憑感覺跳過）**：合成的七段顯示器測試圖（畫「235」），RapidOCR 回傳空字串並記錄「text detection result is empty」；Tesseract 讀成「世紀二」（幻覺出完全不相關的中文字）。兩者都不堪用，這個實測結果才是改走 OpenCV 分段判讀的依據。
- **七段判讀演算法開發過程踩到的真實問題**：
  1. 一開始用膨脹（dilate）想把數字的斷開線段黏成一塊，結果反而把小數點跟隔壁數字黏在一起、緊致邊界框也被撐大導致取樣點偏移，讀出一堆 `?`。改成不做形態學處理、直接對原始二值圖做連通元件分析後解決。
  2. 數字「1」因為只有右側兩條線段、緊致邊界框特別窄，用一般比例取樣點會讓左右取樣點意外重疊到同一條線，誤判成「8」。加了「寬度明顯小於其他數字」的特判後解決。
  3. 取樣閾值一開始設 0.35，數字「9」的 b/c 段因為取樣窗口跟線段只有部分重疊，量到的比例剛好卡在 0.333，低於閾值判定成「OFF」。調整閾值到 0.25 後解決。
  - 最終在合成的 0-9 全數字圖與含小數點的「23.5」圖上，兩種情境都 100% 正確判讀。
- **指針錶角度換算踩到的真實 bug**：指針角度剛好落在 `min_angle` 邊界附近（134.7° vs 135°，只差 0.3° 的量測雜訊），原本邏輯把「角度略小於 min_angle」一律當成「指針繞了一整圈」，讀值該接近 0 卻跳成 100。改成同時試算「角度」與「角度+360」兩種解讀、取夾範圍前比例離 [0,1] 較近的那個之後修正；測 6 個指針角度（135/180/270/0/45/90）確認除了不屬於量測弧的「死區」（90 度）之外全部正確，`test_gauge_boundary_noise_does_not_wrap_to_opposite_end` 這個測試專門釘住這個邊界情況，避免以後回歸。
- **單元測試**：新增 `tests/test_nameplate.py` 9 項，涵蓋銘牌正常解析／缺欄位驗證錯誤／空白圖片擋在 LLM 呼叫之前、七段顯示器讀「235」／0-9 全對／找不到數字報錯、指針錶三個關鍵角度（min/mid/max）讀值誤差 <5／邊界雜訊不會跳到另一端／找不到指針報錯。全專案累計 55 項單元測試全過（14 秒）。
- **live 測試（真打本機 Ollama）**：`pytest -m live`，銘牌辨識正確讀出型號 `CK-850V`、序號含 `20260088`，耗時約 6.5 秒。
- **瀏覽器實測**（真實 Chrome）：三個分頁都實際上傳圖片操作過。
  - 銘牌：6781ms 後正確顯示廠牌/型號/序號/製造日期/電壓。
  - 七段顯示器：15ms 正確判讀「235」，標註圖用綠框框出每個數字並標上判讀結果。
  - 指針錶：11ms 讀出 49.42（指針角度 268.4°，接近校正中點），標註圖清楚疊出偵測到的圓心、外框與指針方向，跟原圖的紅色指針完全對齊。

### Phase 7：功能驗證

- **M8-2 PneumoniaMNIST 訓練實測，含真實抓到的類別不平衡 bug**：第一版沒處理類別不平衡（訓練集 normal 1214 張 vs pneumonia 3494 張），CPU 訓練 15 epoch 只要 19.4 秒、測試集 ACC=0.8285、AUC=0.9284，看整體數字像是不錯的結果。但實際拿一張已知標籤是 normal 的測試圖片跑分類，AI 判成 pneumonia（機率 0.9997）——這個明顯的錯誤才讓我去查每個類別各自的召回率，發現 normal 召回率只有 55.6%（234 張正常樣本裡 104 張被誤判），pneumonia 召回率卻有 99.2%，證實模型學到「猜 pneumonia 比較容易對」的偷懶策略。加上 `pos_weight=0.3475`（`n_normal/n_pneumonia`）調整損失權重後，同一張測試圖仍有機會判錯（模型不是變成 100% 準確，只是變好），但整體 normal 召回率提升到 74.8%、測試集 ACC 提升到 0.8862、AUC 提升到 0.9346。這個過程完整示範了「只看整體 ACC 會掩蓋類別偏差」的教訓，`metrics.json` 現在會記錄兩個類別各自的召回率。
- **抽樣驗證確認模型行為符合統計，不是模型壞掉**：拿 8 張已知是 normal 的測試圖實際跑分類，5/8（62.5%）正確，跟整體實測的 74.8% 召回率同一個量級（小樣本本來就會有波動），證實模型是「有這個誤判機率」而不是「完全故障」。
- **M8-1 包裝檢核真實案例測試**：條碼跟印刷文字一致的案例正確判 OK；把印刷批號跟效期都改成明顯不同的值，正確判 NG 並在「問題」欄位列出「批號」「效期」兩項。
- **單元測試**：新增 `tests/test_medical.py` 7 項，涵蓋包裝檢核一致/批號不一致/效期不一致/OCR 讀不到文字時不誤判成不一致/找不到條碼報錯，以及肺炎分類回傳警語/找不到權重報錯。全專案累計 62 項單元測試全過（14 秒）。
- **live 測試**：`pytest -m live`，包裝檢核真打 Ollama 正確判 OK；肺炎分類真的載入訓練好的權重，對 PneumoniaMNIST 官方測試集前 30 張抽樣分類，正確率 86.67%，跟訓練紀錄的整體 ACC=0.8862 同一個量級。
- **瀏覽器實測**（真實 Chrome）：兩個分頁都實際上傳圖片操作過。
  - 包裝檢核：上傳批號/效期都對不上的測試圖，4949ms 後正確判定 NG，清楚列出條碼值/印刷值/問題清單。
  - 醫學影像分類：警語用紅色粗體＋⚠️ 圖示顯眼呈現在分頁最上方；上傳一張真實 PneumoniaMNIST 測試圖（已知標籤 normal），64ms 判定 normal（肺炎機率 0.0042），跟真實標籤一致。

### Phase 8：收尾驗證

- **13 張截圖全部用 Playwright 實跑產生**（`scripts/capture_screenshots.py`），每張都是實際上傳圖片、點擊按鈕、等待真實 API 回應後的畫面截圖，不是手動擺拍或編輯過的示意圖；M3/M6/M5 PPE 三個模組刻意用官方測試集裡的真實圖片（`data/mvtec_ad/screw/test/scratch_head/000.png`、`data/deeppcb_yolo/test/images/...`、`data/hardhat_yolo/val/images/005298.jpg`），不是隨便塞無關圖片。
- **抽查 3 張截圖內容正確性**（`03_anomaly.png`、`06_safety.png`、`12_packaging.png`）：異常檢測正確顯示 NG + 熱力圖精準疊在螺絲瑕疵位置；危險區域入侵修正 canvas 座標 bug 後正確顯示 NG（危險區域: true）+ 半透明紅色覆蓋區；包裝追溯碼檢核正確顯示 NG，批號與效期兩項不一致都列在「問題」欄位。其餘 10 張截圖僅檢查檔案有效性（`identify`/`file` 確認為合法 PNG、尺寸合理），未逐張人工核對畫面內容。
- **收尾後跑過一次完整單元測試**：`pytest`，62 項全過（14.03 秒），跟 Phase 7 記錄的數字一致，確認截圖腳本與 README/CLAUDE.md 文件變動沒有動到任何程式邏輯。

### Phase 9：功能驗證

- **舊 db migration 用真的手動建的舊 schema db 測，不是只看程式碼**：`tests/test_inspections.py::test_legacy_db_auto_migrates_and_old_data_still_queryable` 用純 SQL 建一個只有 Phase 1-8 六個欄位的 `inspections` 表並塞一筆舊資料，接著呼叫 `query_inspections()`（會觸發 `_migrate()`），確認：(1) 舊資料的 `summary` 還讀得到；(2) 11 個 Phase 9 新欄位都補上了但值是 `NULL`；(3) 用 `PRAGMA table_info` 直接檢查 sqlite 檔案，`work_order`／`review_verdict` 確實存在於實體 schema。額外的真實驗證：拿專案本身累積到 Phase 8 為止的真實 `data/inspections.db`（157 筆歷史紀錄，橫跨 Phase 1-8 的真實/live 測試資料）啟動改版後的伺服器，直接查詢與寫入都正常，不需要任何手動修檔。
- **contextvar 跨 threadpool 傳遞用真實 HTTP 請求驗證**：`test_trace_headers_recorded_and_optional` 帶 5 個 header（含 `encodeURIComponent` 編碼過的中文操作員「王小明」）打 `/api/general/describe`，再用 `GET /api/inspections/{id}` 確認 5 個欄位都正確落地且中文沒有亂碼；另外驗證不帶 header 時 5 個欄位全部是 `None`，不會因為 middleware 邏輯出錯而噴例外。
- **存圖功能分三種情況測**：`SAVE_IMAGES=true` 時原圖存檔、`/image?kind=raw` 讀得到、沒有標註圖的模組（M9）`annotated_path` 正確是 `None`、讀 `kind=annotated` 回 404；`SAVE_IMAGES=false` 時完全不存檔，`image_path`/`annotated_path` 都是 `None`；有標註圖的模組（M6 PCB）驗證 `annotated_path` 有值且 `/image?kind=annotated` 回傳 `Content-Type: image/png`。
- **複判 API**：改判成功回傳更新後的完整紀錄（`review_verdict`/`reviewer`/`reviewed_at`/`review_note` 都正確）；`review_verdict` 傳無效值（例如 `"MAYBE"`）回 422；查詢不存在的 id 回 404。
- **看板統計用固定假資料算出預期數字再比對，不是「跑出什麼就信什麼」**：`test_stats_yield_pareto_and_consistency` 手動插入 5 筆已知判定的紀錄（2 筆 anomaly、2 筆 defect、1 筆 general），對其中 2 筆 anomaly 做複判（1 筆維持 OK、1 筆 NG→OK），手算預期值後逐一斷言：`reviewed_count=2`、`consistency_rate=0.5`（複判跟 AI 判定一致的比例）、anomaly 這個 group 的 `OK=2/NG=0`（因為 NG 那筆被複判成 OK）。NG 原因柏拉圖驗證 `defect` 模組的兩種瑕疵類型計數正確、`anomaly` 模組「判定=異常」也正確被算進柏拉圖（不是只有 defect/ppe 才算缺陷類別）、累積百分比最後一筆等於 100%。`group_by` 傳無效值回 400。
- **真實瀏覽器完整流程驗證**（`mcp__Claude_Browser__*`，真打本機 Ollama `qwen3.5:9b` 與訓練好的 PCB YOLO 模型，不是假資料）：
  1. 用 curl 帶追溯 header 呼叫 `/api/general/describe`（真打 LLM，25.4 秒），確認 `operator` 欄位正確存成「王小明」（URL 編碼中文解碼正確）、`image_path` 正確存檔。
  2. 用 DeepPCB 測試集真實圖片呼叫 `/api/defect/pcb`（真打訓練好的 YOLO 模型，1.4 秒），偵測到 8 個瑕疵判 NG，`image_path`／`annotated_path` 都正確存檔，`/image?kind=annotated` 讀出來是合法 PNG。
  3. 瀏覽器開看板分頁：統計卡（總筆數 159、AI 良率 61.6%）、每日良率折線圖、NG 原因柏拉圖（含累積百分比線）、各模組堆疊長條圖全部正確渲染，無 console 錯誤。
  4. 點開 id=159 的紀錄列，正確展開顯示原圖與標註圖（紅框標出瑕疵位置）、完整 JSON 明細、已有的複判紀錄。
  5. 在瀏覽器上把這筆從「複判 NG」改成「複判 OK」並送出，看板即時更新：defect 模組最終良率從 0% 變成 12.5%（8 筆裡 1 筆變 OK）、AI／人工一致率從 100% 掉到 0%（因為新的複判結果 OK 跟 AI 判定 NG 不一致）——這組數字變化跟手算的預期完全吻合，不是憑畫面「看起來有更新」就當作驗證過。
  6. 模組篩選測試：篩「PCB 瑕疵偵測」後總筆數正確變成 8、AI 良率變成 0.0%（8 筆全部 AI 判 NG）、最終良率 12.5%，跟未篩選時的全域統計數字不同，證明篩選確實套用到 `/api/inspections/stats`。
- **CSV 匯出**：帶追溯資訊呼叫一次辨識後匯出 CSV，確認 header 含 `work_order`／`review_verdict` 等新欄位，且資料列有正確寫入的工單號。
- **既有測試無回歸**：`pytest`，71 項全過（62 項既有 + 9 項新增，13 秒），confirm 前後兩次執行都是同樣結果，且測試流程不會污染專案真實的 `data/inspections.db`／`data/images/`（`tests/conftest.py` 的 `client` fixture 新增 `INSPECTION_IMAGES_DIR` 隔離，這是開發過程中第一次沒隔離時真的把測試圖寫進 `data/images/` 才發現要修的，發現後已清除誤寫的檔案並補上隔離）。

### Phase 10：功能驗證

- **API Key**：`tests/test_erp_integration.py::test_api_key_missing_or_wrong_is_401_correct_key_is_200` 用不帶預設 header 的獨立 `TestClient` 驗證三種情況（沒帶/帶錯/帶對）都符合預期；另外用真實瀏覽器/curl 對正在跑的伺服器直接測過：沒帶 key → `401`、錯 key → `401`、對的 key（`.env` 的 `dev-erp-key-change-me`）→ `200`，13 個辨識端點（用 `/api/general/describe` 代表）完全不受影響，不帶 key 也正常回應（缺檔案的 `422` 是參數驗證，不是認證擋下來的）。
- **開發中踩到「CORS 監測假象」的坑，發現後修正測試而不是強行讓它過**：一開始想用 `monkeypatch.setenv("CORS_ORIGINS", ...)` 改白名單再發請求驗證，結果測試看起來會過，但實際上是因為改的值剛好跟預設值一樣（湊巧沒露餡）。往下追才發現 `CORSMiddleware` 的白名單是 `main.py` 模組載入當下就讀死、烤進中介層物件的，不是每個請求動態重讀——這代表在同一個 pytest session 裡，`main` 模組只會被 import 一次，之後任何測試對 `CORS_ORIGINS` 的 monkeypatch 都不會影響已經建好的 `app`。改成直接測「目前這個 session 裡 `app` 實際持有的白名單」（也就是預設值：`127.0.0.1:8000` 允許、任意其他網域不允許）之後，測試才是測到真正在跑的行為。這個坑也記進了「已知限制」，避免以後改 `.env` 的 `CORS_ORIGINS` 卻忘記要重啟服務。
- **since_id 升冪查詢**：插入 5 筆紀錄後用 `since_id=第2筆的id` 查詢，正確只回傳後面 3 筆且是 id 升冪排序，跟沒帶 `since_id` 時的預設降冪明確不同。
- **reviews 端點**：對一筆紀錄複判後，`since=很久以前的時間` 抓得到這筆（`reviewed_at` 在範圍內），`since=未來時間` 抓不到，符合「事後被複判的舊紀錄」這個設計目的。
- **上傳大小限制／假圖片偵測**：`MAX_UPLOAD_MB=0` 時任何檔案都回 `413` 且訊息含「過大」；副檔名 `.png` 但內容其實是純文字的檔案回 `400` 且訊息含「無法讀取圖片」（Pillow 實際開檔驗證抓到的，不是看副檔名判斷）。
- **webhook 三種情境都用真的本機 HTTP server 測，不是 mock**：`tests/test_erp_integration.py` 用 Python 內建的 `ThreadingHTTPServer` 起一個真的會收請求的伺服器（`_CapturingHandler` 把收到的 JSON body 存進 list）：
  1. OK 判定：呼叫 `/api/defect/pcb`（假偵測器回傳無瑕疵）後等 0.3 秒，確認伺服器完全沒收到任何請求。
  2. NG 判定：呼叫同一端點（假偵測器回傳有瑕疵）後輪詢等待，確認伺服器收到的 JSON 裡 `inspection_id`／`verdict`／`module` 都正確。
  3. 接收端掛掉：先開一個 server 拿到保證沒人聽的 port 再馬上關掉，設成 `ERP_WEBHOOK_URL`，量測辨識 API 的實際回應時間 `< 2 秒`（`httpx` 的 timeout 設 5 秒，代表主執行緒確實沒有在等這個 thread，符合「daemon thread 立即送、不擋住辨識回應」的設計），並確認 `webhook_queue` 表裡多了一筆待重試紀錄。
  4. 重試成功：延續情境 3 的佇列項目，把同一個 port 的 server 重新開起來後手動呼叫 `webhook.retry_pending_once()`，確認伺服器這次真的收到請求、且 `webhook_queue` 清空（重試成功後從佇列移除）。
- **C# 範例真的編譯過**：`dotnet new console` 建立 `docs/erp-integration-sample/`、`dotnet add package Microsoft.Data.SqlClient`（實際從 nuget.org 下載 7.1.0 版）、把文件裡的範例程式碼貼進 `Program.cs`，`dotnet build` 輸出「建置成功，0 個警告，0 個錯誤」；SQL Server 連線邏輯本身沒有真的跑（沒有可連的 SQL Server 執行個體），這點在 `docs/erp-integration.md` 裡誠實寫「未編譯驗證」的地方只有連線行為，語法/型別正確性是真的驗證過的。
- **既有測試無回歸**：`pytest`，82 項全過（71 項既有 + 11 項新增，約 14 秒）。

### Phase 11：功能驗證

- **批次 API 真實跑通**：curl 對正在跑的伺服器打 `POST /api/batch/count?expected_count=8`（2 張 `screws.png`），兩張都判 OK、`預期數量` 正確吃到 8；`POST /api/batch/intrusion`（1 張真人照片 `tests/live_samples/factory_worker.jpg`，`zone` 用 Form 欄位帶整張圖範圍）正確判 NG——證明批次額外參數走 query string（`expected_count`）、`zone` 走 Form 欄位（跟原本單張端點的傳遞方式一致）都有正確接到。單元測試（`tests/test_batch.py`，6 項）額外驗證：整批 3 張全成功、中間一張壞檔不影響前後兩張好檔、未知 action 回 400、anomaly 缺 `category` 該筆標成失敗但不影響整批、count 動作的紀錄真的寫進 `inspections` 表且 `module=measure`。
- **M5 短影片端點用 `ffmpeg` 自製的真實影片測試，不是合成黑幀**：拿 `tests/live_samples/factory_worker.jpg`（真人照片）用 `ffmpeg -loop 1 -t 6 -r 5` 轉成 6 秒 mp4，打 `/api/safety/video?sample_interval_s=1&max_duration_s=6`（真打 YOLO11n），耗時 409ms，取樣 6 幀、6 個違規時間點全部正確判 NG。PPE 影片端點用 `data/hardhat_yolo/val/images/` 裡的兩張真實驗證集圖片各自轉成影片測試：`005770.jpg`（原本單張測試就是 OK）轉的影片正確判 OK、0 違規；`006279.jpg`（原本單張測試 9 個人未戴安全帽）轉的影片正確判 NG、5/5 幀全部違規、未戴安全帽數 10（YOLO 對靜態重複畫面的偵測結果穩定一致）。單元測試（`tests/test_safety_video.py`，5 項）用假偵測器驗證違規時間點/縮圖/影片過大 413/壞影片 400 等邊界情況，並確認影片辨識只寫一筆彙總紀錄（不是每幀一筆）。
- **`scripts/watch_folder.py` 真的對正在跑的伺服器執行過一次完整流程**：10 張 `warning_sign.png` 丟進 `/tmp/inbox_test`，`--action general --once` 真打 Ollama 逐張辨識（每張約 15-20 秒），10 筆全部成功搬到 `done/`、`inbox/` 清空、API 查得到這 10 筆紀錄且追溯欄位（`station=AOI-99`、`work_order=WO-LIVE-TEST`）正確落地；另外丟 1 個壞檔（純文字內容、`.png` 副檔名）進另一個 inbox，正確搬到 `error/` 並寫 `.log`。單元測試（`tests/test_watch_folder.py`，4 項）用 `TestClient` 當 `httpx.Client` 相容物件測核心邏輯（`process_one`/`scan_existing`/`wait_until_stable`），不用真的起一個 uvicorn process 也能測完整的「等檔案穩定→呼叫 API→搬檔→寫 log」流程。
- **開發中意外抓到的真實 bug：`core/image_io.load_image()` 對某些壞檔案回 500 而不是 400**：這是在跑 `watch_folder.py` 的壞檔情境時發現的——單元測試裡同樣的情境（`test_non_image_bytes_with_image_extension_is_rejected`）一直是綠燈，但拿真實伺服器測就爆 500。查了 uvicorn log 的完整 traceback，追到 `ultralytics.utils.patches` 對 `PIL.Image.open` 做了 monkeypatch（加 HEIF 支援），Pillow 格式辨識失敗時這個 patch 過的版本會嘗試 lazy import `pi_heif`（沒裝），丟出 `ModuleNotFoundError`，不是原本 `except (UnidentifiedImageError, OSError)` 攔截的型別。只有在同一個 Python process 裡已經有任何請求觸發過 `import ultralytics`（M5/M6 任何端點）之後，這個 monkeypatch 才會生效——這正是為什麼過去 10 個 Phase 的單元測試從沒踩到（測試對 ultralytics 的呼叫都被 fixture 假掉，沒有真的觸發 import）。修法：把 `load_image()` 的 except 從 `(UnidentifiedImageError, OSError)` 放寬成 `Exception`（函式的合約本來就是「bytes 讀不出圖就回 400」，不該因為第三方套件的例外型別細節就外洩成 500）。修完後 `pytest` 82→97 項照樣全過，且真實伺服器重測同一個壞檔案情境正確回 400、`watch_folder.py` 正確搬進 `error/` 並在 `.log` 寫下清楚訊息。這個 bug 完全是「Surprise is signal」抓到的：程式邏輯看起來對、單元測試也綠燈，但真實情境的結果跟預期不符，往下查才發現是環境/第三方套件的副作用，不是憑空猜到才預防的。
- **相機拍照用 Playwright + Chromium 假相機裝置（`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`）驗證完整鏈路**：開相機→等 `<video>` 可見→點拍照→確認 `#camera-modal` 關閉、`#general-preview` 顯示、`document.getElementById('general-file').files.length === 1`（真的拿到一個 `File` 物件，檔名 `camera-<timestamp>.jpg`）→點「開始辨識」送出→真的打 Ollama 拿到辨識結果（`general · INFO · ollama:qwen3.5:9b · 17353ms`，有正常的中文描述內容）。同一個 Playwright session 也測了批次上傳：3 張圖選在 `general-file`（`multiple` 屬性），送出後狀態列顯示「完成：共 3 張，OK 0／NG 0／INFO 3／失敗 0」，結果區塊正確渲染出 3 張縮圖卡片。
- **既有測試無回歸**：`pytest`，97 項全過（82 項既有 + 15 項新增，約 16-18 秒）。

### Phase 12：功能驗證

- **用 MVTec `bottle`（Phase 12 才下載，Phase 3 沒用過）模擬「自家零件」，全程走真實 UI 建立類別**：良品 209 張（`train/good/`）+ NG 63 張（`test/broken_large`+`broken_small`+`contamination`，三種瑕疵混在一起、刻意不分類別、不帶 `ground_truth/` 像素遮罩，模擬使用者上傳一包雜亂照片的真實情境），各自打包成 zip，用 curl 真的呼叫 `POST /api/anomaly/categories?name=bottle_custom` 上傳。API 立即回應（0.5 秒，`status=queued`），背景輪詢 `GET .../status` 確認狀態依序變成 `fitting`→`done`，總耗時 158 秒。
- **真實踩到 anomalib 內建正規化把分數裁成退化值的 bug，詳細除錯過程見「技術決策與理由（Phase 12）」**：第一次跑完 `image_auroc=0.9762` 但 `threshold=1.0`，檢查 `scores.json` 發現 63 筆 NG 分數全部剛好等於 `1.0`、部分良品也是——追進 anomalib 原始碼確認是內建 min-max 正規化拿一個範圍太窄的內部驗證集去裁剪外部分數。修正（`Patchcore(post_processor=PostProcessor(enable_normalization=False, enable_thresholding=False))`）後重跑同一批資料：`image_auroc=0.9977`、`threshold=40.13`，`scores.json` 顯示良品分數落在 25.8-44.7、NG 分數落在 40.1-76.6，只有邊界一點點重疊，數字完全合理。
- **實測比較「只用良品估計」vs「用 NG 樣本 ROC」兩種門檻策略**：同一批 bottle 資料，不帶 NG zip 另外建一個 `bottle_good_only` 類別，門檻用 99th percentile 估計出 `44.62`；`bottle_custom`（有 NG）用 ROC/Youden's J 估計出 `40.13`。拿 `bottle_custom` 的 `scores.json`（42 張 held-out 良品 + 63 張 NG）分別套兩種門檻算誤判率：
  | 門檻策略 | 門檻值 | 良品誤判率 | NG 漏判率 |
  |---|---|---|---|
  | 只用良品估計（99th percentile） | 44.62 | 2.4% | **9.5%** |
  | 用 NG 樣本（ROC/Youden's J） | 40.13 | 2.4% | **0.0%** |

  兩種策略的良品誤判率剛好一樣（2.4%），但只看良品分佈估計出來的門檻明顯偏高，導致將近一成的真實瑕疵被漏判成良品；用 NG 樣本找 ROC 最佳平衡點後，同樣的良品誤判率下 NG 漏判率降到 0%。這組數字是真實計算出來的，不是預期中「應該會更好」的猜測。
- **門檻調校 API 與判定邏輯真的串起來測過**：`inspect_part()` 對同一張已知 NG 的測試圖（`test/broken_large/000.png`，原始異常分數 67.09，固定不變）先後套用 ROC 門檻（40.13，判 NG）跟手動調高的門檻（45.0，仍判 NG，因為 67.09 遠大於兩者），確認 `PATCH /categories/{name}/threshold` 改了門檻後，下一次 `inspect` 呼叫立即套用新門檻、不需要重啟服務或重新擬合。
- **前端門檻調校面板用真實瀏覽器操作驗證**：切到 M3 分頁，類別表格正確顯示 `bottle_custom`（AUROC 0.9977、門檻 40.1322）與 `bottle_good_only`（AUROC 顯示 `—`、門檻 44.6232）；點「門檻調校」開出 Chart.js 直方圖，綠色（良品）與紅色（NG）分數分佈清楚分開，幾乎沒有重疊，視覺上直接印證了 AUROC 接近 1 的原因；拖拉滑桿從門檻 40.03 拉到 65.16，畫面即時把「良品誤判率」從 2.4% 更新成 0.0%、「NG 漏判率」從 0.0% 更新成 69.8%，數字跟手算的 `computeThresholdRates()` 邏輯完全吻合；點「儲存門檻」後用 `GET .../status` 確認 `threshold` 欄位真的被更新，測完手動改回 ROC 門檻 40.132244 避免影響其他測試。
- **`export_reviewed.py` 兩種匯出格式都真實跑過**：
  - PPE：用訓練好的模型對 5 張 Hard Hat Workers 驗證集圖片辨識（1 張 NG 含真實偵測框、4 張 OK），人工複判確認 AI 判定正確後匯出，YOLO 資料夾（`images/`、`labels/`、`data.yaml`）正確產生；拿 Phase 5 訓練好的 `models/ppe/ppe_yolo11n/weights/best.pt` 對匯出的資料夾跑 `model.val(data=...)`，**真的成功執行**，mAP50=0.995（標籤是模型自己的預測，數字高只證明格式正確，不代表訓練品質）。
  - anomaly：用 `bottle_custom` 的一張 NG 測試圖辨識後人工複判，匯出成 MVTec 格式（`good/`、`defect/`），`export_anomaly_mvtec("bottle_custom", ...)` 正確把這筆歸進 `defect/`。
- **收尾清理**：驗收用的 `bottle_custom`／`bottle_good_only` 兩個示範類別（連同 `models/anomaly/` 與 `data/custom_anomaly/` 底下的產物、`categories.json` 裡的條目）驗收完就清掉了，不留在系統裡當成正式功能誤導使用者；下載的 `data/mvtec_ad/bottle/` 原始資料集保留（不進版控，之後要重跑驗收或展示可以省下載時間）。
- **既有測試無回歸**：`pytest`，113 項全過（97 項既有 + 16 項新增：`test_anomaly_categories.py` 11 項、`test_export_reviewed.py` 5 項，約 15-17 秒）。

### Phase 13：功能驗證（先做 M10/M11）

- **M10 對齊穩健性用手算校準數字驗證，不是憑感覺調參數**：拿合成的組裝黃金樣本（900x500，6 個不對稱零件圖案）逐一測試：完整正視角自比對 SSIM=1.0；「少一顆」該 ROI 掉到 0.212；「裝反」該 ROI 掉到 0.708。第一版沒做高斯模糊，`±15 度旋轉` 這種「零件其實都裝對，只是拍攝角度不同」的情境，`warpPerspective` 對齊後的插值誤差讓最差 ROI 掉到 0.75-0.83（±15 度旋轉最差 0.7662、-15 度旋轉某個角落 ROI 甚至到 0.7528），跟「裝反」的 0.708 太接近，找不到一個門檻同時兼顧兩種情境；加上 5x5 高斯模糊後，旋轉情境最差分數回升到 0.9196、縮放情境到 0.986，跟「裝反」的 0.7132 之間有足夠安全邊界，最後定案 `SSIM_THRESHOLD=0.85`。這個過程完全是拿實測數字反覆調整校準出來的，中間至少推翻了兩次「應該可以了」的假設（先試 0.6 抓不到裝反、再試 0.8 在 -15 度旋轉時仍誤判）。
- **M10 端到端測試涵蓋 10 種情境**（`tests/test_assembly.py`）：建立/查詢黃金樣本、料號格式驗證、ROI 數量下限、找不到料號回 404、完整正視角判 OK、缺件判 NG（且正確標出是哪個 ROI）、裝反判 NG（且正確標出是哪個 ROI）、±15 度旋轉/±20% 縮放都判 OK 且對齊 inlier 比例都 >0.5、純雜訊圖對齊失敗回 `INFO`（不是硬猜 OK/NG）。
- **開發中意外踩到的真實 bug：`GOLDEN_SAMPLES_DIR` 第一版沒有 env 覆寫機制，測試把資料寫進專案真實目錄**：`tests/test_assembly.py` 十項測試第一次全部綠燈通過，但跑完後 `ls data/golden_samples/` 發現多了一個 `test_part` 資料夾——跟 Phase 9 存圖、Phase 12 自訂類別 registry 是同一種坑（module-level 常數路徑沒有讀 env，測試沒有機制隔離）。修法比照前兩次的模式：加 `_golden_dir()` 函式每次呼叫都重讀 `os.environ.get("GOLDEN_SAMPLES_DIR", ...)`，`tests/conftest.py` 的 `client` fixture 一起補上隔離。修完後清掉誤寫的資料夾，重跑測試確認乾淨。
- **M11 用 CIEDE2000 論文公開的標準測試向量直接驗證 skimage 本身算得對**（`test_known_ciede2000_test_vectors_match_skimage`）：4 組來自 Sharma et al. 2005 論文的已知 Lab 值配對與預期 ΔE00，呼叫 `skimage.color.deltaE_ciede2000` 算出來的結果跟論文數字誤差 <0.001；另外一項測試（`test_pipeline_matches_skimage_deltaE_ciede2000_directly`）獨立算「正確答案」（自己呼叫 `rgb2lab`+`deltaE_ciede2000`）跟服務層回傳的數字比對，確認「裁切 ROI→算平均 Lab→呼叫 skimage」這條完整管線沒有在中間哪個環節算錯，不是只測 skimage 本身。
- **M11 門檻可調整用同一張圖、兩種門檻值得到不同判定驗證**（`test_threshold_is_configurable`）：同一張色差圖，`threshold=0.1` 判 NG、`threshold=50` 判 OK，證明門檻參數真的有傳到判定邏輯，不是寫死忽略的參數。
- **前端 Playwright 實際拖曳畫框驗證，不是只測後端 API**：
  - M10：真的用滑鼠在 canvas 上拖曳畫出 6 個 ROI（座標依 canvas 顯示縮放比例換算）、輸入料號、點「儲存黃金樣本」，確認狀態列顯示「已儲存：playwright_part（6 個 ROI）」；接著上傳完整正視角照片比對，畫面顯示 `assembly · OK`；換成「少一顆」的照片再比一次，畫面顯示 `assembly · NG` 且明細裡 ROI 3 相似度 0.2197、判定 NG，跟單元測試的手算數字一致。
  - M11：真的拖曳畫「標準色區」跟「量測區」兩個矩形，送出後得到 `ΔE00=1.728`、判定合格；再勾選「手動輸入標準 Lab 值」填入 `[50,20,20]`，同一張圖送出得到不同的 `ΔE00=12.842`、判定不合格——證明兩種標準來源模式都真的接到後端邏輯，不是介面擺著沒串起來。
  - 測試用真實伺服器（不是 `TestClient`），驗證完後清掉 Playwright 留下的 `data/golden_samples/playwright_part/` 測試資料，避免污染展示系統。
- **截圖腳本（`scripts/capture_screenshots.py`）新增 M10/M11 的特殊流程**（`capture_assembly`/`capture_colordiff`），實際跑過一次產生 `14_assembly.png`／`15_colordiff.png`，人工核對畫面內容：M10 截圖清楚顯示 6 個彩色 ROI 框（畫在黃金樣本上）跟比對結果（5 個綠框 OK + 1 個紅框 NG，對應「少一顆」的示範案例）；M11 截圖清楚顯示標準色區（橙框）跟量測區（藍框）疊在色塊圖上，結果表格正確列出兩邊 Lab 值與 ΔE00。因為 M10/M11 插在既有分頁中間（⑭⑮），⑯ 品檢看板的截圖檔名跟著從 `14_dashboard.png` 改成 `16_dashboard.png`，`capture_dashboard()` 函式也同步更新。
- **既有測試無回歸**：`pytest`，132 項全過（113 項既有 + 19 項新增：`test_assembly.py` 10 項、`test_colordiff.py` 9 項，約 18-19 秒）。

### Phase 14：功能驗證（M12 出貨標籤比對）

- **單元測試涵蓋 9 種情境**（`tests/test_shipping.py`）：料號/數量/批號全部一致判 OK；料號不符判 NG；數量不符判 NG；三項預期值都沒給時誠實回 `INFO`（不是硬猜 OK/NG）；預期值改用 Phase 9 追溯資訊（`work_order`/`part_no`/`lot_no` header）當預設值；明確傳入的參數會蓋過追溯資訊（驗證優先序：手動參數 > 追溯 header）；有 GS1 條碼時批號一律信任條碼值而非 OCR/LLM 讀到的批號；LLM 回傳缺欄位觸發 Pydantic 驗證錯誤時判 NG；空白圖片在呼叫 LLM 之前就被擋下回 400。
- **真打本機 Ollama 驗證三種情境（用 Playwright 對正在跑的伺服器操作，非 `TestClient`）**：
  1. 全部一致：上傳料號/批號/數量都對得上的出貨標籤圖，填入對應預期值送出，3595ms 後正確判定 OK，三項比對欄位（`料號一致`/`數量一致`/`批號一致`）全部 `true`。
  2. 料號不符：預期值故意填錯（`SC-M8-30` vs 圖上真實料號 `SC-M6-20`），正確判 NG，「問題」欄位清楚列出「料號」。
  3. 條碼優先：標籤圖同時有 GS1 條碼與印刷批號文字、且刻意讓兩者不同，比對結果採用條碼批號而非印刷文字批號，跟 M8-1 包裝檢核「條碼優先」的既有邏輯一致。
- **開發中用 Playwright 測批次上傳時抓到真實 bug，並用 curl 重現＋驗證修復**：第一次用批次上傳（`⑯ 出貨標籤比對` 分頁多選檔案）測試時，畫面顯示「INFO 2」而非預期的 OK/NG，跟單張上傳（同一組參數）結果不一致。用 curl 直接打 `POST /api/batch/shipping?expected_part_no=SC-M6-20&...` 重現，回應裡 `"預期料號": null`——確認手動輸入的預期值完全沒有傳到 service。追到 `backend/modules/batch/router.py` 的 `batch()` 函式簽名是 Phase 11 建立時針對當時 14 個動作寫死的固定參數列表，新增 M12 這三個參數時只在 `core/batch_dispatch.py` 的 `_shipping()` 裡讀 `params.get(...)`，卻忘記同步在 `batch/router.py` 的函式簽名裡宣告——FastAPI 對函式簽名沒宣告的 query 參數是直接忽略，不會報錯也不會警告，這正是這個 bug 沒有在寫程式當下被發現的原因。修法：把 `expected_part_no`/`expected_lot_no`/`expected_quantity` 加進 `batch()` 的簽名與 `params` dict；補上 `tests/test_batch.py::test_batch_shipping_passes_expected_values_as_query_params` 回歸測試釘住。修完後重跑同一個 curl 重現指令，回應正確顯示 `"預期料號": "SC-M6-20"`、`"料號一致": true`；重新用 Playwright 走一次批次上傳，畫面正確顯示「OK 1」。
- **截圖驗證**：`scripts/capture_screenshots.py` 新增 `capture_shipping()`，真跑一次產生 `16_shipping.png`（人工用 Read 工具核對：清楚顯示上傳的出貨標籤圖、填入的預期值、AI 判定 NG 與「問題：料號」的明細，這是刻意用不符的預期值 `SC-M8-30` 示範 NG 情境）；因為 M12 插在既有分頁後面（⑯），品檢看板從 `16_dashboard.png` 改名 `17_dashboard.png`，`capture_dashboard()` 同步更新，17 張截圖全部重新產生。
- **既有測試無回歸**：`pytest`，142 項全過（132 項既有 + 10 項新增：`test_shipping.py` 9 項、`test_batch.py` 批次參數回歸測試 1 項，約 21.7 秒）。


### Phase 17：功能驗證

- **單元測試**：`pytest` 173 項全過（142 既有 + 31 新增：`test_registry.py` 15、`test_request_scope.py` 6、`test_settings.py` 10；約 25 秒）。
- **註冊表完整性**：`test_every_inspection_module_has_defect_extractor` 通過；`test_completeness_check_fails_when_an_extractor_is_removed` 把 assembly 的 extractor 拿掉後，檢查函式回報 `['assembly']`，還原後回到空清單。
- **柏拉圖補漏（真實伺服器＋暫存資料庫，Playwright）**：對 codes（過期）、count（預期 99）、measure（目標長度 80mm）、colordiff（紅 vs 藍）、assembly（ROI 3 缺件）各造 NG，看板柏拉圖標籤為 `組裝異常：ROI 3`、`色差超標`、`尺寸超差：長度`、`數量不符`、`追溯碼已過期`。docs／nameplate 的 NG 由單元測試（假 LLM）驗證標籤；七段顯示器的 `?` 判讀失敗只有單元測試（extractor 直接餵 summary），未在瀏覽器造出真實 NG。
- **雙圖存檔**：組裝防呆的紀錄展開後詳情有 3 張圖（原圖、標註圖、黃金樣本，naturalWidth 皆 900）；單元測試比對 `kind=raw` 回傳的 bytes 等於待測照、`kind=golden` 等於黃金樣本。
- **前端**：導覽 17 個項目（16 功能＋看板）逐一點過，每次只有對應的 panel active；`scripts/capture_screenshots.py` 跑完 17 個流程（含真打 Ollama 的 5 個），瀏覽器 console／頁面錯誤 0 筆；`#gauge` 網址直連與 `hashchange` 生效（第一版漏了 hashchange，Playwright 測出後補上）；攔截 `/api/modules` 加一個沒有專用畫面的假動作，導覽出現並產生預設面板；390px 寬度 `scrollWidth == clientWidth`（無橫向捲動）。
- **間歇性的測試程序結束崩潰（未查出根因）**：全測試通過之後的程序結束階段，偶爾出現 `libc++abi: terminating due to uncaught exception of type std::__1::system_error: recursive_mutex lock failed`（pytest 退出前已印出 `173 passed`，測試結果不受影響）。新測試集約 10 次執行中出現 2 次；之後連續 3 次完整測試與 3 次「只跑舊測試」皆 0 次；基準（Phase 16 的 142 項）只測過 2 次，沒出現，樣本太少，**不能斷言是既有問題或本 Phase 引入**。疑似第三方（torch／onnxruntime）在程序結束時的清理競爭，尚未驗證。
- **已寫入真實資料庫的紀錄**：`capture_screenshots.py` 沿用既有慣例對真實 `data/inspections.db` 寫入 17 筆辨識紀錄；柏拉圖與雙圖驗證改用暫存資料庫。


### Phase 18：功能驗證

- **單元測試**：`pytest` 202 項全過（173 既有 + 28 新增的 `test_auth.py` + 1 項 `test_settings.py` 調整為包含新增的需重啟設定；約 35 秒）。既有測試中，複判、建立黃金樣本、建立自訂類別改用對應角色的登入 client（原因見 decisions.md），`test_recognition_endpoints_do_not_need_api_key` 改成相反的斷言。
- **權限矩陣**：`test_auth.py` 對 operator／qc／API key／未登入各測一遍（辨識、複判、統計、匯出、明細、圖片、reviews、使用者、稽核、門檻、黃金樣本、自訂類別），403／401 邊界與矩陣一致。
- **真實伺服器＋暫存資料庫（Playwright，三個角色各登入一次）**：
  - 未登入開 `/` 導向 `/login.html`；錯誤密碼顯示統一訊息。
  - admin 導覽 19 項（含使用者、稽核），qc 與 operator 各 17 項；operator 的看板頁隱藏統計卡、標題為「我的檢驗紀錄」、表格列不可展開，直接打 `/api/inspections/stats`、`/api/users` 皆 403。
  - 各角色做一次追溯碼辨識，`created_by` 依序為 `user:admin`、`user:qcuser`、`user:opuser`，追溯欄位「操作員」留空時帶顯示名稱。
  - qc 在看板複判：資料庫 `reviewer=qcuser`（前端已無「複判人」輸入框），稽核有一筆 `inspection.review`；admin 建立使用者後稽核多一筆 `user.create`。
  - operator 登出後回登入頁，`/` 不再放行。
  - 瀏覽器 console／頁面錯誤 0 筆。`capture_screenshots.py` 改為登入後執行（帳密由環境變數提供），17 個流程全數完成，console 0 筆。
- **ERP 與資料夾監控回歸（curl，真實伺服器）**：`X-API-Key` 輪詢 `since_id` 200；`?api_key=` 401；API key 複判 403；未帶身分辨識 401。`watch_folder.py` 沒帶 key 直接退出並說明，帶 `WATCH_API_KEY` 成功辨識並搬到 `done/`，紀錄 `created_by=api-key:watcher`。
- **密碼與 session**：資料庫中的密碼雜湊前綴皆為 `$argon2id$`；session cookie 帶 `HttpOnly` 與 `SameSite=Lax`；`SESSION_SECRET` 未設定、短於 32 字元時 `import main` 以非 0 結束並顯示產生指令（子程序測試）。
- **延遲量測**（暫存伺服器，200 次 `GET /api/modules`）：session 平均 5.75ms／P95 7.56ms，API key 平均 4.85ms／P95 5.85ms，差約 0.9ms；登入（含 argon2 驗證）平均 52ms。
- **前端密鑰掃描**：測試掃描 `frontend/`（排除 vendor）不含 `FRONTEND_API_KEY`、`dev-frontend-key`、`dev-erp-key`、`X-API-Key`、`api_key`。
- **未驗證**：`create_admin.py` 的互動式密碼輸入（`getpass`）未在終端實際操作，只測了它呼叫的 `create_admin()` 函式；HTTPS 下 `SESSION_COOKIE_SECURE=true` 的行為未實測；反向代理改寫 Host 的情境未測。
- **已寫入真實資料庫的紀錄**：無。本 Phase 的瀏覽器驗證與截圖全部對暫存資料庫的伺服器執行；真實 `data/inspections.db` 在下次啟動時才會自動補上 `users`、`audit_log` 表與 `created_by` 欄位（用舊 schema 資料庫的遷移測試驗證過）。


### Phase 19：功能驗證

- **單元測試**：`pytest` 225 項全過（202 既有 + 23 新增：`test_master.py` 7、`test_recipes.py` 16；約 38 秒）。
- **配方執行**：三步驟配方（追溯碼＋異常檢測＋尺寸量測，兩個圖片槽）一次檢驗產生 1 筆 run、3 筆 inspections（皆帶 `run_id`、工單、料號、由工單帶入的批號）；合併判定三種情境都有測試：全 OK→OK、追溯碼過期→NG（其他步驟照常執行）、量測圖沒有 ArUco 標記（步驟出錯）→INFO、NG 與出錯並存→NG；`combine()` 另以純函式測 7 種組合（含 info 類動作不計、info 類出錯仍算出錯）。
- **版本不可變**：新增 v2（量測目標改 80mm）後，v1 仍是原參數、v1 舊 run 仍指向 v1、v2 執行得 NG；重新啟用 v1 後 `GET /api/recipes/active` 回 v1。
- **驗證**：13 種非法配方（空步驟、料號不在主檔、未知動作、多餘參數、參數型別錯、缺 category、類別不存在、黃金樣本不存在、非法圖片槽名稱、色差缺標準色、Lab 與矩形並存、Lab 長度不對、座標超出 0~1）皆 422。
- **assembly／colordiff 進配方**：黃金樣本預設用配方料號；缺件→NG、正常→OK；色差標準隨版本保存並出現在稽核的 `after.steps[].params`。`test_batch_api_still_rejects_assembly_and_colordiff` 仍通過。
- **run 視角統計**：單步視角 6 筆（2 個 run × 3 步）、run 視角 2 筆；複判 NG run 的追溯碼那步後，最終判定 NG→OK（AI 判定不變、AI 良率 0.5、最終良率 1.0、一致率 0.0）；`scope` 或 `group_by` 非法回 400；沒帶 `scope` 時單步統計與 Phase 18 相同。
- **ERP bulk-upsert**：重推不重複建立；3 列中 2 列失敗時其餘列照常成功（`errors` 帶 index／key／原因）；名為 `watcher` 的 key、qc、operator 皆 403，未登入 401，admin 與 `erp` key 可以；未知欄位 422；稽核一筆含新增／更新／錯誤筆數。
- **臨時檢驗標記**：無工單→1、主檔工單→0、不在主檔的工單→1（辨識與配方兩條路徑都測）。
- **真實伺服器＋暫存資料庫（Playwright、真實 HTTP 的 ERP 推送）**：ERP 推 1 料號與 3 張工單（1 張料號不存在→errors 列出），`watcher` key 推送得 403；追溯列工單選單只列進行中工單，選工單後料號與批號自動帶入且工單欄位唯讀，手動輸入不在主檔的工單號顯示「臨時檢驗（此工單不在主檔）」；主檔頁用 UI 新增工單、用動態表單建立 codes＋measure（含參數）配方，儲存為 v1（啟用中）；漏填 category 的 anomaly 步驟顯示伺服器的 422 訊息；依配方檢驗頁載入配方、依圖片槽上傳兩張圖，合併判定 OK，換成沒有標記的圖後合併判定 INFO 並列出原因；看板切到「整次配方檢驗」，總數由 3（單筆）變 2（run）、圖表標籤為料號；qc 看得到主檔頁但管理表單隱藏；operator 沒有主檔頁，選工單後能完成配方檢驗（run 合併判定 OK）。瀏覽器 console 唯一的錯誤是上述刻意送出的 422。
- **未驗證**：配方步驟含 AI 步驟（LLM 類）的整體耗時未量測；`capture_screenshots.py` 尚未加入配方與主檔頁（新頁面的截圖只在暫存驗證中產生，未進 `docs/screenshots/`）；ERP 單次推送接近 2000 列上限的效能未測。
- **已寫入真實資料庫的紀錄**：無（驗證全用暫存資料庫；真實資料庫會在下次啟動時自動補上新表與欄位）。


### Phase 20：功能驗證

- **單元測試**：`pytest` 255 項全過（225 既有 + 30 新增：`test_spc.py` 19、`test_reports.py` 11；約 40 秒）。
- **管制圖與能力指標（手算對照）**：三個子群（n=5）平均 11／12／10、全距皆 4：X̄̄=11、R̄=4、X̄ 圖 UCL=13.308／LCL=8.692、R 圖 UCL=8.456／LCL=0、σ=4/2.326；規格 5–16 時 Cp=1.06608、Cpu=0.96917、Cpl=1.163、Cpk=0.96917（皆與手算一致，`approx` 容差 1e-4）。I-MR 範例（8 筆）：X̄=11.625、MR̄=12/7、UCL=16.185、LCL=7.065、MR UCL=5.6006；規格 6–16 時 Cp=1.09667、Cpk=0.95958。同一批資料經 `log_inspection` 寫入再由 `GET /api/spc` 取得，數值相同。
- **Western Electric**：規則 1（剛好 3σ 不觸發、3.5σ 觸發）、規則 2（兩點超出 2σ 同側觸發；異側或超出三點視窗不觸發）、規則 3（五點四點觸發、三點不觸發）、規則 4（7 點不觸發、8 點觸發於第 8 點、9 點時第 8 與 9 點都標記、`run_length=7` 時 7 點觸發、落在中心線上會中斷連續）；真實圖表上，離群子群觸發規則 1、全距特別大的子群觸發 R 圖規則 1；`sigma=0` 不會出錯。透過 API 驗證：先有 10 筆交錯資料再加 7 筆同側點→規則 4 不觸發，加到 8 筆→觸發於第 18 點；`run_length=7` 時第 17、18 點觸發。
- **量測值寫入**：長度規格＝目標 ± 公差（10.5±5.5→5–16）；寬度沒填目標→無規格；單孔才收孔徑（兩個孔那筆沒收）；計數結果不算量測；舊格式（沒存公差）→ 無規格；色差 usl＝門檻、lsl 為空；指針錶與七段讀值可轉數字才收（含 `?` 不收）；銘牌欄位不收；真實 `POST /api/measure/measure` 結果含 `公差mm=1.0`，並產生長度、寬度、孔徑三個特性。
- **API 與權限**：篩選（料號、站別、日期）、資料不足回 `insufficient_data` 與說明、`chart`／`subgroup_size` 非法回 400／422、缺特性 422、料號為空用 `__none__`、規格中途改變（公差 5.5→1.0）時 `spec.changed=true` 並採用最近規格；qc 與 API key 可讀、operator 403、未登入 401（SPC 與報表皆同）。
- **報表**：欄位數字與手算一致（20 筆：AI OK 17／NG 2／INFO 1，複判一筆 NG→OK 後最終 OK 18／NG 1；AI 良率 17/19、最終良率 18/19；一致率 0；臨時檢驗 20；各站別 S1 良率 1.0、S2 0.0、未填站別 INFO；柏拉圖「追溯碼已過期」2 次；Cpk 摘要 15 筆／3 子群／Cp 1.06608／Cpk 0.96917 且標「僅供參考」）；週報範圍週一到週日（2026-09-29→09-28～10-04）；空資料不會出錯；Excel 用 openpyxl 讀回驗證 6 個工作表名稱與儲存格內容（中文不亂碼、良率字串 89.5%／94.7%）；HTML 含列印樣式且內容已跳脫（`<script>` 不會原樣輸出）；API 的 json／xlsx／html 三種格式與 400／422 驗證；`daily_report.py` 產生 xlsx 與 html；`reports/` 在 `.gitignore`。
- **回填**：模擬舊紀錄（不經 `record_result`）→ `--dry-run` 報 2 筆紀錄 4 個量測值且資料庫沒變 → 實際執行寫入 → 再執行為 0（可重複）；長度沒有規格、色差有上限、時間沿用原紀錄。
- **真實伺服器＋暫存資料庫（Playwright）**：注入 60 筆長度（含 5 筆偏高與 1 個離群值）與 12 筆色差；SPC 頁列出 4 個（料號／特性）、色差為單邊規格只顯示 Cpk 0.861 並附說明、長度 X̄-R 顯示 12 個子群、Cp 1.317／Cpk 1.191 與「僅供參考」、圖上 2 個紅點、違規表列出規則 1 與 2（X̄）及規則 1（R）；切換 I-MR 為 60 個點／59 個 MR；日期範圍無資料顯示訊息；看板「日報（可列印）」開新分頁（標題「品質日報 2026-09-29」、7 張卡、4 個表）；週報 Excel 回 200 與 spreadsheetml；qc 看得到 SPC 頁，operator 沒有該分頁且 API 回 403。`daily_report.py` 與 `backfill_measurements.py --dry-run` 以 CLI 對同一資料庫實際執行成功（後者因資料皆已有量測值回報 0）。
- **未驗證**：Excel 用 Microsoft Excel／Numbers 開啟的外觀（只用 openpyxl 讀回內容）；列印成 PDF 的實際排版；launchd plist 與 Windows 工作排程器的排程設定（只寫了說明，沒有實際排程執行）；大量資料（例如 10 萬筆量測值）的 SPC 與報表效能；常態性與穩定性假設不檢查。
- **已寫入真實資料庫的紀錄**：無（驗證全用暫存資料庫；真實資料庫在下次啟動時自動補上 `measurements` 表，歷史量測值需自行執行回填腳本）。


### Phase 21：功能驗證

- **單元測試**：`pytest` 290 項全過（255 既有 + 35 新增：`test_migrations.py` 6、`test_model_registry.py` 16、`test_maintenance.py` 12、`test_settings.py` 1；約 42 秒）。既有測試只有一處期望值調整：CSV 標頭的最後欄位由 `request_id` 變成 `request_id, model_id, model_version`（新欄位一律追加在最後）。
- **migration**：用 Phase 15 當時真實的 DDL 建資料庫（含複判資料與 webhook 重試佇列），升級後資料完整（模組、判定、工單、複判人與備註、摘要 JSON、重試次數皆不變），新欄位（`request_id`、`created_by`、`run_id`、`adhoc`、`model_id`、`model_version`）補上且舊資料為空，`schema_version` 記錄 1、2，`PRAGMA integrity_check` 為 ok，升級後照常寫入與統計；每個程序對每個資料庫檔只檢查一次（`forget()` 後才重查）；資料庫版本 999 比程式新時丟 `SchemaTooNew`；`001_baseline` 連跑兩次不出錯。
- **模型登錄**：就地登錄 v1（不複製、路徑相對專案根目錄、`registered_by=system:bootstrap`、指標取自旁邊的 metrics.json，沒有就取開發紀錄的數字並帶出處）；第二次使用不重複登錄；缺權重回原本的 503 訊息；有版本但沒有啟用、或啟用版本的檔案不見時給明確錯誤；資料庫層面擋下第二個 active；SHA-256 不符時拒絕（同一程序只驗一次，換新程序才發現被動過）；新版本資料夾不會撞名、非法模型 id 被拒；`VersionedCache` 換版本才重載。
- **與服務和檢驗紀錄整合**：PCB 服務登錄第二版（複製進登錄庫、原檔不動、登錄不等於啟用）→ 透過 API 切換 → 新紀錄的 `model_version` 變 2、真的載入新檔案 → 回滾後又是 1；批次逐張各記各的版本；沒有模型的功能兩欄為空。API：清單不含伺服器絕對路徑；qc 與 API key 可讀、operator 403；qc／operator／API key 皆不能切換；回滾到權重檔不見或被改壞的版本回 422；已是啟用中的版本不重複寫稽核；稽核 `model.activate` 有前後版本與操作者。
- **異常檢測版本化**：每次擬合成為新版本（替身 `train_custom` 寫出與真的相同的資料夾結構），門檻與評分檔跟版本走，回滾後權重、門檻、評分、類別表與狀態端點顯示的版本號／AUROC／門檻都回到 v1；調整門檻只影響啟用中的版本；擬合失敗不留版本也不留半成品資料夾；舊資料夾結構的類別就地成為 v1，重擬合不會覆寫它；缺權重的錯誤訊息與 Phase 20 完全相同。
- **真實擬合（真實伺服器＋暫存資料庫，MVTec bottle 209 張良品＋63 張 NG，透過網頁上傳流程）**：第一次擬合 196 秒、AUROC 0.9981、門檻 40.2078 → 版本 1；重新送出得到版本 2（182 秒、門檻 40.0428）；v2 啟用中時 NG 圖 66.9871 判 NG、良品 30.9528 判 OK，紀錄寫 `anomaly-bottle_v21 v2`；回滾到 v1 後狀態端點顯示版本 1、門檻 40.207752、AUROC 0.9981，NG 圖 67.3334 判 NG、良品 30.9769 判 OK，紀錄寫 v1。
- **真實權重與介面（真實伺服器＋暫存資料庫）**：真實 PCB YOLO 與真實 287MB 的 screw PatchCore 第一次使用時各自就地登錄成 v1（登錄表的 SHA-256 與獨立計算的雜湊一致），檢驗紀錄寫入 `pcb-defect v1`、`anomaly-screw v1`；`register_model.py register` 登錄第二版（複製進登錄庫），`list` 列出全部版本；Playwright 開「管理 → 模型」頁，看到 3 個模型的版本、指標（PCB v1 的 mAP50=0.978 等）、SHA-256、大小、登錄者，按「啟用（回滾）」並在確認對話框按確定後，該模型變 v2 啟用中，之後的檢驗寫 `pcb-defect v2`，看板展開紀錄顯示「使用的模型：pcb-defect v2」；瀏覽器 console 0 筆錯誤。
- **資料保存**：預設只預覽（不刪檔）；`--apply` 才刪，新舊各一筆時只清期限外的；紀錄保留、路徑改 `expired`、圖片端點回 410 並說明；再跑一次沒有東西可清；同一天資料夾在變空時一併移除；有人工複判的預設保留、`--include-reviewed` 才清；輔助圖（黃金樣本副本）一併清；資料庫裡被改成指向 `../` 的路徑不會刪到 images 目錄之外的檔案；`IMAGE_RETENTION_DAYS` 預設 180、可用環境變數改。
- **備份還原**：備份 → 刪除資料庫、圖片、黃金樣本、類別狀態 → 預覽（什麼都沒動）→ 還原後，看板統計整份相同、使用者與密碼雜湊相同、主檔相同、圖片位元組相同、黃金樣本與類別狀態相同，且可用原密碼登入；備份檔權限 0600、不含 `.env`、manifest 有 schema 版本與筆數、預設不含 `models/`、加旗標才含；備份取自 online backup 的快照且 `integrity_check` 為 ok；還原時既有資料改名成 `*.before-restore-<時間>`（測試讀回那份舊資料庫仍有 2 筆）；拒絕損毀的備份（SHA-256 不符）、備份 schema 比程式新、manifest 沒列的多餘檔案、沒有 manifest 的檔案，且拒絕時原本的資料完全沒動。
- **模型說明卡**：內容全部有出處（登錄表、metrics.json、靜態說明）；肺炎保留警語、MVTec 標明不得商用；metrics.json 裡的本機路徑不進說明卡；`--check` 偵測過期（只有異動的卡被判過期）；沒有指標來源的模型顯示「尚無機器可讀的指標紀錄」而不是編數字。以暫存資料庫登錄 7 個真實權重（就地）後產生 8 個檔案進 `docs/model-cards/`。
- **測試隔離事故**（詳見 decisions.md）：新寫的兩個測試沒用 `client` fixture，連到真實 `data/inspections.db`——真實資料庫被 migration 升級，並被寫入 13 筆垃圾 `model_versions`（`anomaly-cat` 7 筆、`anomaly-old_cat` 6 筆）；發現後修法是 autouse fixture 全域隔離，並驗證：三個資料路徑環境變數設成不可寫後整個測試套件 289 項（當時）全過，真實資料庫前後 `model_versions` 為 13、`inspections` 為 284、檔案修改時間不變。**那 13 筆垃圾列與升級後的 schema 仍在真實資料庫裡，尚未清除**（清除也是寫入資料庫，需要使用者同意）。
- **驗證時寫入的真實路徑（已清理）**：真實擬合流程會寫 `models/registry/`（1.4GB）、`data/custom_anomaly/`（139MB）與 `models/anomaly/categories.json`；驗證完已刪除前兩者並把 `categories.json` 還原成 `{}`。
- **未驗證**：`train_anomaly.py`（內建三個 MVTec 類別，每個 5–11 分鐘）改成寫進登錄庫後**沒有重新完整跑過**，只驗證了語法與其餘流程共用的登錄邏輯（網頁擬合流程實跑過）；`register_model.py register` 的 `anomaly-*` 分支（整個 root 資料夾複製）只有程式碼審視，沒有實跑；`restore.py` 的 `--include-models` 還原路徑沒有測；還原後服務重新啟動的行為只測了資料層；大量圖片（例如數十萬張）的備份與清理效能沒測；權重在服務執行中被改動要到下次重啟才會被發現（設計上的取捨）。


### Phase 22：功能驗證（2026-10-12）

- **單元測試**：`pytest` 356 項全過（含 `test_health`、`test_jobs`、`test_instance_lock`、`test_metrics`）；CI（ubuntu-latest，Python 3.11）同樣 356 項全過、覆蓋率 93%。
- **驗收 1：缺權重**（真實伺服器＋暫存資料庫，工作目錄沒有 `models/`）：`/healthz` 回 ok；`/readyz` 回 200 且 `degraded=true`、`unavailable_features=10`；`/api/system/status` 逐項列出 defect、ppe、intrusion、pneumonia、anomaly 的缺件原因與處理指令；不需模型的功能（assembly、colordiff、count、measure、seven_segment、gauge、codes）標示可用，實際 `POST /api/codes/decode` 回 200；缺權重的 `POST /api/defect/pcb` 回 503 並說明如何準備。
- **驗收 2：擬合中重啟**（真實 PatchCore，20 張合成良品經網頁上傳流程）：狀態進到 `fitting` 後對服務 `kill -9`；重啟後類別狀態為 `interrupted`（訊息「服務重啟時這個工作還沒做完，已中斷；可以重試」），`GET /api/jobs` 列出該工作為 interrupted；`POST /api/jobs/{id}/retry` 回 200，工作重新排隊，42 秒後 `done`，登錄為模型版本 1。AUROC 為空是因為沒有提供 NG 照片。
- **驗收 3：Ollama 關閉**（`OLLAMA_HOST` 指向無服務的埠）：`/readyz` 的 `llm` 為 warn；packaging、shipping、nameplate、docs、general 在狀態表標示不可用並附 `ollama serve` 指示；實際 `POST /api/general/describe` 回 503「無法連到 Ollama…」；非 LLM 功能照常。
- **前端導覽灰化與面板橫幅**：只有程式碼審視與單元測試，這次沒有用瀏覽器實際看過畫面。
- **未驗證**：webhook 重啟後恢復在單元測試中以「同一資料庫新連線」模擬，沒有真的重啟程序；`/metrics` 只驗證輸出內容，沒有接 Prometheus 抓取。
- **已寫入真實資料庫的紀錄**：無（真實 `data/inspections.db` 修改時間仍為 09-30，演練全用暫存資料庫；演練產生的 `data/`、`models/` 已刪除）。

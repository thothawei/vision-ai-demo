# 套件、模型、資料集授權查證紀錄

- 查證日期：**2026-09-23**
- 查證方式：版本與授權取自 PyPI JSON API（`https://pypi.org/pypi/<name>/json`）、GitHub API（`repos/<owner>/<repo>` 的 license 欄位）、Ollama 官方模型頁、各資料集官方頁面原文。沒有憑記憶填寫。
- 「可商用」指該元件本身的授權是否允許商業使用；本專案是作品集 Demo，不做商業用途。
- Wheel 欄位：是否有 macOS arm64 + CPython 3.11 可直接安裝的 wheel（pure = 純 Python 套件）。

## Python 套件

| 名稱 | 查證最新版本 | 授權 | 可商用 | macOS arm64 / py3.11 | 用途 | 來源 |
|---|---|---|---|---|---|---|
| fastapi | 0.141.1 | MIT | 是 | pure | API 伺服器 | https://pypi.org/project/fastapi/ |
| uvicorn[standard] | 0.53.0 | BSD-3-Clause | 是 | pure | ASGI 伺服器 | https://pypi.org/project/uvicorn/ |
| python-multipart | 0.0.32 | Apache-2.0 | 是 | pure | 上傳檔案解析 | https://pypi.org/project/python-multipart/ |
| python-dotenv | 1.2.3 | BSD-3-Clause | 是 | pure | 讀 `.env` | https://pypi.org/project/python-dotenv/ |
| pillow | 12.3.0 | MIT-CMU | 是 | 有 wheel | 讀圖、EXIF 轉正 | https://pypi.org/project/pillow/ |
| pydantic | 2.13.5 | MIT | 是 | pure | 共用回應格式、M4 文件 schema | https://pypi.org/project/pydantic/ |
| numpy | 2.5.3（需 py≥3.12）；py3.11 可用最高 2.4.6 | BSD-3-Clause 等 | 是 | 2.4.6 有 wheel | 數值運算 | https://pypi.org/project/numpy/ |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | 是 | 有 wheel（abi3） | M2 計數量測、ArUco、M7 指針錶 | https://pypi.org/project/opencv-python-headless/ |
| zxing-cpp | 3.1.1 | Apache-2.0 | 是 | 有 wheel | M1 QR / 條碼 / DataMatrix | https://github.com/zxing-cpp/zxing-cpp |
| torch | 2.14.0 | BSD-3-Clause 系（複合） | 是 | 有 wheel（MPS） | M3/M5/M6/M8 推論與訓練 | https://pypi.org/project/torch/ |
| torchvision | 0.29.0 | BSD-3-Clause | 是 | 有 wheel | 影像前處理、骨幹網路 | https://pypi.org/project/torchvision/ |
| anomalib | 2.6.2 | Apache-2.0 | 是 | pure | M3 PatchCore 異常檢測 | https://github.com/open-edge-platform/anomalib |
| lightning | 2.6.6 | Apache-2.0 | 是 | pure | anomalib 相依 | https://pypi.org/project/lightning/ |
| ultralytics | 8.4.160 | **AGPL-3.0** | 需開源或買商用授權 | pure | M5 人員偵測 / PPE、M6 瑕疵偵測 | https://github.com/ultralytics/ultralytics |
| rapidocr | 3.9.2 | Apache-2.0 | 是 | pure | M4/M7 OCR（PP-OCR 模型 ONNX 版） | https://github.com/RapidAI/RapidOCR |
| onnxruntime | 1.30.0 | MIT | 是 | 有 wheel | RapidOCR 推論引擎 | https://pypi.org/project/onnxruntime/ |
| rapid-table | 3.0.2 | Apache-2.0 | 是 | pure | M4 表格結構辨識（取代 PP-Structure） | https://pypi.org/project/rapid-table/ |
| rapid-layout | 1.2.1 | Apache-2.0 | 是 | pure | M4 版面分析 | https://pypi.org/project/rapid-layout/ |
| pytesseract | 0.3.13 | Apache-2.0 | 是 | pure | M4 Tesseract 比較選項（沿用） | https://pypi.org/project/pytesseract/ |
| ollama（Python client） | 0.6.2 | MIT | 是 | pure | 本機 LLM 呼叫 | https://pypi.org/project/ollama/ |
| google-genai | 2.25.0 | Apache-2.0 | 是 | pure | Gemini 備援引擎 | https://pypi.org/project/google-genai/ |
| medmnist | 3.0.2（Phase 7 已裝並用於訓練） | 程式 Apache-2.0 | 是 | pure | M8-2 資料集下載 | https://github.com/MedMNIST/MedMNIST |
| pytest | 9.1.1 | MIT | 是 | pure | 測試 | https://pypi.org/project/pytest/ |
| httpx | 0.28.1 | BSD-3-Clause | 是 | pure | FastAPI TestClient 相依 | https://pypi.org/project/httpx/ |
| watchdog | 6.0.0（PyPI JSON API 查證，2026-09-24） | Apache-2.0 | 是 | 有 wheel | `scripts/watch_folder.py` 資料夾監控（Phase 11） | https://pypi.org/project/watchdog/ |

## 前端套件（vendor，Phase 9 新增）

| 名稱 | 查證版本 | 授權 | 可商用 | 用途 | 來源 |
|---|---|---|---|---|---|
| Chart.js | 4.5.1（查證 `master` 分支 `package.json`，2026-09-24） | MIT | 是 | ⑭ 品檢看板：每日良率折線、NG 原因柏拉圖、各模組件數 | https://github.com/chartjs/Chart.js ；放 `frontend/vendor/chart.min.js`（離線優先，不用 CDN，符合硬性規則第 2 條核心離線） |

## .NET 套件（僅 Phase 10 文件範例編譯驗證用，不是本系統執行期相依）

| 名稱 | 查證版本 | 授權 | 可商用 | 用途 | 來源 |
|---|---|---|---|---|---|
| Microsoft.Data.SqlClient | 7.1.0（`dotnet add package` 實際從 nuget.org 安裝取得的版本，2026-09-24） | MIT | 是 | `docs/erp-integration-sample/` 驗證 `docs/erp-integration.md` 的 C# 範例能 `dotnet build` 編譯，不是 vision-ai-demo 本身的相依（本系統是 Python） | https://www.nuget.org/packages/Microsoft.Data.SqlClient |

### 評估後不採用

| 名稱 | 查證版本 | 授權 | 不採用原因 |
|---|---|---|---|
| paddlepaddle + paddleocr | 3.3.1 / 3.7.0 | Apache-2.0 | 在 Python 3.11 與整組套件一起解析時，`paddlex` 要求 `numpy<2.4`，解析器被迫把 `paddleocr` 退回 2.10.0 舊版；macOS 只有 CPU 版。RapidOCR 用的就是 PP-OCR 模型的 ONNX 版，功能等價、相依乾淨，改用它（prompt 原本就允許此退路）。 |
| opencv-contrib-python(-headless) | 5.0.0.93 | Apache-2.0 | ArUco 已在主模組，不需 contrib；多裝一種 OpenCV 發行版會與其他套件的 `cv2` 互相覆蓋。 |
| monai | 1.6.0 | Apache-2.0 | M8-2 只需小型 CNN，PyTorch 即可，不多加相依。 |

## 系統工具（Homebrew）

| 名稱 | 版本 | 授權 | 可商用 | 用途 | 來源 |
|---|---|---|---|---|---|
| Tesseract OCR | 5.5.3（本機已裝＝GitHub 最新 release） | Apache-2.0 | 是 | M4 比較選項 | https://github.com/tesseract-ocr/tesseract |
| Ollama | 0.33.3（本機已裝） | MIT | 是 | 本機 LLM 執行環境 | https://github.com/ollama/ollama |
| uv | 本機已裝 | Apache-2.0 / MIT | 是 | 安裝 Python 3.11、建 venv | https://github.com/astral-sh/uv |
| unar | 1.10.8（Phase 5 新裝） | LGPL-2.1（The Unarchiver 專案） | 是（僅開發期解壓工具，不隨產品散佈） | 解壓 Hard Hat Workers 資料集的 .rar | https://theunarchiver.com/command-line |

## 模型權重

| 名稱 | 大小 | 授權 | 可商用 | 用途 | 來源 |
|---|---|---|---|---|---|
| `qwen3.5:9b`（Ollama，多模態） | 6.6 GB | Apache-2.0 | 是 | M4 結構化、M9 開放式描述（預設候選） | https://ollama.com/library/qwen3.5 |
| `qwen3-vl:8b`（Ollama，多模態） | 6.1 GB | Apache-2.0 | 是 | 備選（若 qwen3.5 實測繁中/JSON 輸出不穩） | https://ollama.com/library/qwen3-vl |
| `qwen3-vl:4b` | 3.3 GB | Apache-2.0 | 是 | 記憶體吃緊時的退路 | https://ollama.com/library/qwen3-vl |
| YOLO11n COCO 預訓練（`yolo11n.pt`，5.6MB） | 5.6MB | **AGPL-3.0** | 需開源或商用授權 | M5 人員偵測（Phase 2 已採用）、M5/M6 微調起點 | https://github.com/ultralytics/assets/releases （tag v8.4.0） |
| PP-OCRv6 det/cls/rec ONNX（`PP-OCRv6_det_small.onnx` 等，RapidOCR 內建自動下載，Phase 4 已用） | 數十 MB | Apache-2.0（RapidAI/RapidOCR repo 授權，GitHub API 查證） | 是 | M4/M7 OCR | https://github.com/RapidAI/RapidOCR |
| `slanet-plus.onnx`（RapidTable 表格結構辨識模型，Phase 4 已用，7.4MB） | 7.4MB | Apache-2.0（RapidAI/RapidTable repo 授權，GitHub API 查證） | 是 | M4 出貨單等品項表格解析 | https://github.com/RapidAI/RapidTable（實際下載自 modelscope.cn/models/RapidAI/RapidTable） |
| `wide_resnet50_2.racm_in1k` ImageNet 權重（anomalib PatchCore 預設骨幹，經 timm 下載） | 約 130 MB | **Apache-2.0**（`timm.get_pretrained_cfg` 查證，`license='apache-2.0'`） | 是 | M3 特徵擷取（不訓練，只做前向推論抽特徵） | https://github.com/huggingface/pytorch-image-models |
| Gemini `gemini-3.6-flash` | 雲端 | Google API 條款 | 免費層 RPM=5 / RPD=20 | 僅備援 | https://aistudio.google.com/rate-limit |

備註：`qwen3.6`、`qwen3.8` 在 Ollama 上最小是 27B（查證當日），16 GB 記憶體的 Mac 無法流暢執行，不採用。

## 資料集

| 名稱 | 授權（原文出處） | 可商用 | 本專案用法 | 來源 |
|---|---|---|---|---|
| MVTec AD（metal_nut 157MB / screw 186MB / tile 335MB，Phase 3 已下載） | **CC BY-NC-SA 4.0**，官方頁明寫「not allowed to use the dataset for commercial purposes」 | 否 | M3，**僅供學習/作品集展示**，`data/mvtec_ad/`，不進版控 | 各類別分開下載連結：https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads（總頁面轉址後的真實網址） |
| NEU-DET（NEU surface defect database） | **官方頁沒有任何授權條款**，只寫「請引用論文」；下載走 Google Drive / 百度盤 | 未知（無授權＝預設保留所有權利） | M6，待使用者決定（見 Phase 0 回報） | http://faculty.neu.edu.cn/songkechen/zh_CN/zdylm/263270/list/index.htm |
| DeepPCB（1500 張 640x640，Phase 5 已下載並用於訓練） | 資料放在 GitHub repo 內，repo 授權 **MIT** | 是 | M6（clone 整個 repo，231MB） | https://github.com/tangsanli5201/DeepPCB |
| Hard Hat Workers（5297 train + 1766 test，Phase 5 已下載並用於訓練） | **CC0 1.0**（Harvard Dataverse API 回傳；Roboflow 頁標示 Public Domain） | 是 | M5 PPE（只有 helmet/head 兩類，**沒有反光背心類別**，資料集本身的限制） | https://doi.org/10.7910/DVN/7CBGOS（實際下載 https://dataverse.harvard.edu/api/access/datafile/3344658，268MB rar） |
| Safety-Helmet-Wearing-Dataset（SHWD） | repo 為 MIT，但 README 寫正樣本圖片「從 Google/百度蒐集」，圖片本身版權不明 | 不明 | 不採用，改用 CC0 的 Hard Hat Workers | https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset |
| MedMNIST（PneumoniaMNIST，Phase 7 已下載並用於訓練，train 4708/val 524/test 624 張，28x28 灰階，來源 Zenodo） | **CC BY 4.0**（DermaMNIST 例外為 CC BY-NC 4.0，本專案不用）；官方註明 NOT intended for clinical use | 是（需署名） | M8-2 教學展示，**僅供技術展示，非醫療診斷用途** | https://github.com/MedMNIST/MedMNIST |
| COCO（YOLO 預訓練所用） | 標註 CC BY 4.0；圖片依 Flickr 各自授權 | — | 只用預訓練權重，不下載資料集 | https://cocodataset.org/#termsofuse |
| 《Worker operates machinery in a factory setting》（Wikimedia Commons） | **CC BY 2.0** | 是（需署名） | Phase 2 `tests/live_samples/`：M5 真人偵測的 live 測試/手動驗證用照片，不進版控 | https://commons.wikimedia.org/wiki/File:Worker_operates_machinery_in_a_factory_setting.jpg |

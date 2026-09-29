# 套件、模型、資料集授權查證紀錄

- 查證日期：**2026-09-23**；Phase 16 於 **2026-09-29** 重新查證全部 Python 套件的版本與授權（PyPI JSON API），授權皆未變動、皆免費，僅 uvicorn／ultralytics／ollama 有新版，尚未升級 `requirements.txt`。
- 查證方式：版本與授權取自 PyPI JSON API（`https://pypi.org/pypi/<name>/json`）、GitHub API（`repos/<owner>/<repo>` 的 license 欄位）、Ollama 官方模型頁、各資料集官方頁面原文。沒有憑記憶填寫。
- 「可商用」指該元件本身的授權是否允許商業使用；本產品目前不做商業用途；若要商用，需逐項確認下方授權（見「本產品授權與第三方元件」一節）。
- 「費用」欄：`免費（開源）`＝取得與使用皆免費、無付費版功能依賴；有條件者於欄內寫明條件。依 `docs/dev/plans/` 的免費工具規則，任何需付費或綁信用卡的工具不採用。
- Wheel 欄位：是否有 macOS arm64 + CPython 3.11 可直接安裝的 wheel（pure = 純 Python 套件）。

## Python 套件

| 名稱 | 查證最新版本 | 授權 | 可商用 | 費用 | macOS arm64 / py3.11 | 用途 | 來源 |
|---|---|---|---|---|---|---|---|
| fastapi | 0.141.1 | MIT | 是 | 免費（開源） | pure | API 伺服器 | https://pypi.org/project/fastapi/ |
| uvicorn[standard] | 0.54.0（2026-09-29 查證） | BSD-3-Clause | 是 | 免費（開源） | pure | ASGI 伺服器 | https://pypi.org/project/uvicorn/ |
| python-multipart | 0.0.32 | Apache-2.0 | 是 | 免費（開源） | pure | 上傳檔案解析 | https://pypi.org/project/python-multipart/ |
| python-dotenv | 1.2.3 | BSD-3-Clause | 是 | 免費（開源） | pure | pydantic-settings 讀 `.env` 的相依（程式不再直接使用） | https://pypi.org/project/python-dotenv/ |
| argon2-cffi | 25.1.0（PyPI JSON API 查證，2026-09-29） | MIT | 是 | 免費（開源） | 有 wheel（依賴 argon2-cffi-bindings 26.1.0，MIT，有 arm64 wheel） | 密碼雜湊 argon2id（Phase 18） | https://pypi.org/project/argon2-cffi/ |
| openpyxl | 3.1.5（PyPI JSON API 查證，2026-09-29） | MIT | 是 | 免費（開源） | pure（相依 et-xmlfile 2.0.0，MIT） | 品質日報／週報 Excel 輸出（Phase 20） | https://pypi.org/project/openpyxl/ |
| itsdangerous | 2.2.0（PyPI JSON API 查證，2026-09-29） | BSD-3-Clause（PyPI 授權欄空白，依 Pallets 官方 LICENSE.txt 判定） | 是 | 免費（開源） | pure | Starlette 簽章 cookie session 的必要相依（Phase 18） | https://pypi.org/project/itsdangerous/ |
| pydantic-settings | 2.15.0（PyPI JSON API 查證，2026-09-29） | MIT | 是 | 免費（開源） | pure | 集中讀取 `.env` 與環境變數（Phase 17） | https://pypi.org/project/pydantic-settings/ |
| pillow | 12.3.0 | MIT-CMU | 是 | 免費（開源） | 有 wheel | 讀圖、EXIF 轉正 | https://pypi.org/project/pillow/ |
| pydantic | 2.13.5 | MIT | 是 | 免費（開源） | pure | 共用回應格式、M4 文件 schema | https://pypi.org/project/pydantic/ |
| numpy | 2.5.3（需 py≥3.12）；py3.11 可用最高 2.4.6 | BSD-3-Clause 等 | 是 | 免費（開源） | 2.4.6 有 wheel | 數值運算 | https://pypi.org/project/numpy/ |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | 是 | 免費（開源） | 有 wheel（abi3） | M2 計數量測、ArUco、M7 指針錶 | https://pypi.org/project/opencv-python-headless/ |
| zxing-cpp | 3.1.1 | Apache-2.0 | 是 | 免費（開源） | 有 wheel | M1 QR / 條碼 / DataMatrix | https://github.com/zxing-cpp/zxing-cpp |
| torch | 2.14.0 | BSD-3-Clause 系（複合） | 是 | 免費（開源） | 有 wheel（MPS） | M3/M5/M6/M8 推論與訓練 | https://pypi.org/project/torch/ |
| torchvision | 0.29.0 | BSD-3-Clause | 是 | 免費（開源） | 有 wheel | 影像前處理、骨幹網路 | https://pypi.org/project/torchvision/ |
| anomalib | 2.6.2 | Apache-2.0 | 是 | 免費（開源） | pure | M3 PatchCore 異常檢測 | https://github.com/open-edge-platform/anomalib |
| lightning | 2.6.6 | Apache-2.0 | 是 | 免費（開源） | pure | anomalib 相依 | https://pypi.org/project/lightning/ |
| ultralytics | 8.4.165（2026-09-29 查證；classifier 為 AGPLv3+） | **AGPL-3.0** | 需開源或買商用授權 | 免費（開源 AGPL-3.0；另有付費 Enterprise 授權，本專案不採用） | pure | M5 人員偵測 / PPE、M6 瑕疵偵測 | https://github.com/ultralytics/ultralytics |
| rapidocr | 3.9.2 | Apache-2.0 | 是 | 免費（開源） | pure | M4/M7 OCR（PP-OCR 模型 ONNX 版） | https://github.com/RapidAI/RapidOCR |
| onnxruntime | 1.30.0 | MIT | 是 | 免費（開源） | 有 wheel | RapidOCR 推論引擎 | https://pypi.org/project/onnxruntime/ |
| rapid-table | 3.0.2 | Apache-2.0 | 是 | 免費（開源） | pure | M4 表格結構辨識（取代 PP-Structure） | https://pypi.org/project/rapid-table/ |
| rapid-layout | 1.2.1 | Apache-2.0 | 是 | 免費（開源） | pure | M4 版面分析 | https://pypi.org/project/rapid-layout/ |
| pytesseract | 0.3.13 | Apache-2.0 | 是 | 免費（開源） | pure | M4 Tesseract 比較選項（沿用） | https://pypi.org/project/pytesseract/ |
| ollama（Python client） | 0.6.3（2026-09-29 查證） | MIT | 是 | 免費（開源） | pure | 本機 LLM 呼叫 | https://pypi.org/project/ollama/ |
| google-genai | 2.25.0 | Apache-2.0 | 是 | 免費（開源） | pure | Gemini 備援引擎 | https://pypi.org/project/google-genai/ |
| medmnist | 3.0.2（Phase 7 已裝並用於訓練） | 程式 Apache-2.0 | 是 | 免費（開源） | pure | M8-2 資料集下載 | https://github.com/MedMNIST/MedMNIST |
| pytest | 9.1.1 | MIT | 是 | 免費（開源） | pure | 測試 | https://pypi.org/project/pytest/ |
| httpx | 0.28.1 | BSD-3-Clause | 是 | 免費（開源） | pure | FastAPI TestClient 相依 | https://pypi.org/project/httpx/ |
| watchdog | 6.0.0（PyPI JSON API 查證，2026-09-24） | Apache-2.0 | 是 | 免費（開源） | 有 wheel | `scripts/watch_folder.py` 資料夾監控（Phase 11） | https://pypi.org/project/watchdog/ |
| scikit-learn | 1.9.1（PyPI JSON API 查證，2026-09-24） | BSD-3-Clause | 是 | 免費（開源） | 有 wheel | M3 自訂類別門檻調校（ROC/Youden's J，Phase 12） | https://pypi.org/project/scikit-learn/ |
| scikit-image | 0.26.0（PyPI JSON API 查證，2026-09-25） | BSD-3-Clause（少量元件 MIT） | 是 | 免費（開源） | 有 wheel | M10 黃金樣本 ROI 比對（SSIM）、M11 色差 ΔE（CIEDE2000），Phase 13 | https://pypi.org/project/scikit-image/ |

## 前端套件（vendor，Phase 9 新增）

| 名稱 | 查證版本 | 授權 | 可商用 | 費用 | 用途 | 來源 |
|---|---|---|---|---|---|---|
| Chart.js | 4.5.1（查證 `master` 分支 `package.json`，2026-09-24） | MIT | 是 | 免費（開源） | ⑭ 品檢看板：每日良率折線、NG 原因柏拉圖、各模組件數 | https://github.com/chartjs/Chart.js ；放 `frontend/vendor/chart.min.js`（離線優先，不用 CDN，符合硬性規則第 2 條核心離線） |

## 外部標註工具（Phase 12，不裝進本專案 venv，各自獨立安裝執行）

| 名稱 | 查證版本/授權 | 可商用 | 費用 | 用途 | 來源 |
|---|---|---|---|---|---|
| Label Studio Community Edition | 授權查證 `LICENSE` 檔（GitHub `master` 分支，2026-09-24）：**Apache-2.0** | 是 | 免費（開源） | `scripts/export_reviewed.py` 匯出的 YOLO／MVTec 資料夾用它匯入校正人工複判過的標註（見 README「複判資料回流」） | https://github.com/HumanSignal/label-studio |

## .NET 套件（僅 Phase 10 文件範例編譯驗證用，不是本系統執行期相依）

| 名稱 | 查證版本 | 授權 | 可商用 | 費用 | 用途 | 來源 |
|---|---|---|---|---|---|---|
| Microsoft.Data.SqlClient | 7.1.0（`dotnet add package` 實際從 nuget.org 安裝取得的版本，2026-09-24） | MIT | 是 | 免費（開源） | `docs/erp-integration-sample/` 驗證 `docs/erp-integration.md` 的 C# 範例能 `dotnet build` 編譯，不是 vision-ai-demo 本身的相依（本系統是 Python） | https://www.nuget.org/packages/Microsoft.Data.SqlClient |

### 評估後不採用

| 名稱 | 查證版本 | 授權 | 不採用原因 |
|---|---|---|---|
| paddlepaddle + paddleocr | 3.3.1 / 3.7.0 | Apache-2.0 | 在 Python 3.11 與整組套件一起解析時，`paddlex` 要求 `numpy<2.4`，解析器被迫把 `paddleocr` 退回 2.10.0 舊版；macOS 只有 CPU 版。RapidOCR 用的就是 PP-OCR 模型的 ONNX 版，功能等價、相依乾淨，改用它（prompt 原本就允許此退路）。 |
| opencv-contrib-python(-headless) | 5.0.0.93 | Apache-2.0 | ArUco 已在主模組，不需 contrib；多裝一種 OpenCV 發行版會與其他套件的 `cv2` 互相覆蓋。 |
| monai | 1.6.0 | Apache-2.0 | M8-2 只需小型 CNN，PyTorch 即可，不多加相依。 |

## 系統工具（Homebrew）

| 名稱 | 版本 | 授權 | 可商用 | 費用 | 用途 | 來源 |
|---|---|---|---|---|---|---|
| Tesseract OCR | 5.5.3（本機已裝＝GitHub 最新 release） | Apache-2.0 | 是 | 免費（開源） | M4 比較選項 | https://github.com/tesseract-ocr/tesseract |
| Ollama | 0.33.3（本機已裝） | MIT | 是 | 免費（開源） | 本機 LLM 執行環境 | https://github.com/ollama/ollama |
| uv | 本機已裝 | Apache-2.0 / MIT | 是 | 免費（開源） | 安裝 Python 3.11、建 venv | https://github.com/astral-sh/uv |
| unar | 1.10.8（Phase 5 新裝） | LGPL-2.1（The Unarchiver 專案） | 是（僅開發期解壓工具，不隨產品散佈） | 免費（開源） | 解壓 Hard Hat Workers 資料集的 .rar | https://theunarchiver.com/command-line |

## 模型權重

| 名稱 | 大小 | 授權 | 可商用 | 費用 | 用途 | 來源 |
|---|---|---|---|---|---|---|
| `qwen3.5:9b`（Ollama，多模態） | 6.6 GB | Apache-2.0 | 是 | 免費（開源） | M4 結構化、M9 開放式描述（預設候選） | https://ollama.com/library/qwen3.5 |
| `qwen3-vl:8b`（Ollama，多模態） | 6.1 GB | Apache-2.0 | 是 | 免費（開源） | 備選（若 qwen3.5 實測繁中/JSON 輸出不穩） | https://ollama.com/library/qwen3-vl |
| `qwen3-vl:4b` | 3.3 GB | Apache-2.0 | 是 | 免費（開源） | 記憶體吃緊時的退路 | https://ollama.com/library/qwen3-vl |
| YOLO11n COCO 預訓練（`yolo11n.pt`，5.6MB） | 5.6MB | **AGPL-3.0** | 需開源或商用授權 | 未下載資料集 | M5 人員偵測（Phase 2 已採用）、M5/M6 微調起點 | https://github.com/ultralytics/assets/releases （tag v8.4.0） |
| PP-OCRv6 det/cls/rec ONNX（`PP-OCRv6_det_small.onnx` 等，RapidOCR 內建自動下載，Phase 4 已用） | 數十 MB | Apache-2.0（RapidAI/RapidOCR repo 授權，GitHub API 查證） | 是 | 免費（開源） | M4/M7 OCR | https://github.com/RapidAI/RapidOCR |
| `slanet-plus.onnx`（RapidTable 表格結構辨識模型，Phase 4 已用，7.4MB） | 7.4MB | Apache-2.0（RapidAI/RapidTable repo 授權，GitHub API 查證） | 是 | 免費（開源） | M4 出貨單等品項表格解析 | https://github.com/RapidAI/RapidTable（實際下載自 modelscope.cn/models/RapidAI/RapidTable） |
| `wide_resnet50_2.racm_in1k` ImageNet 權重（anomalib PatchCore 預設骨幹，經 timm 下載） | 約 130 MB | **Apache-2.0**（`timm.get_pretrained_cfg` 查證，`license='apache-2.0'`） | 是 | 免費（開源） | M3 特徵擷取（不訓練，只做前向推論抽特徵） | https://github.com/huggingface/pytorch-image-models |
| Gemini `gemini-3.6-flash` | 雲端 | Google API 條款 | 免費層 RPM=5 / RPD=20 | 免費（有條件：僅限免費層、不可啟用計費帳戶） | 僅備援 | https://aistudio.google.com/rate-limit |

備註：`qwen3.6`、`qwen3.8` 在 Ollama 上最小是 27B（查證當日），16 GB 記憶體的 Mac 無法流暢執行，不採用。

## 資料集

| 名稱 | 授權（原文出處） | 可商用 | 費用 | 本專案用法 | 來源 |
|---|---|---|---|---|---|
| MVTec AD（metal_nut 157MB / screw 186MB / tile 335MB，Phase 3 已下載；bottle 155MB，Phase 12 驗收自訂類別流程時下載，用完已清掉擬合出的模型/資料，只留原始 tar.xz 供之後重跑） | **CC BY-NC-SA 4.0**，官方頁明寫「not allowed to use the dataset for commercial purposes」 | 否 | 免費（非商用授權：僅供學習與技術展示） | M3，**僅供學習與技術展示，不得用於商業產線**，`data/mvtec_ad/`，不進版控；Phase 12 用 bottle 當「假裝是自家零件」模擬使用者上傳（只用 train/good + test 的原始照片，刻意不用 ground_truth 像素遮罩） | 各類別分開下載連結：https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads（總頁面轉址後的真實網址） |
| NEU-DET（NEU surface defect database） | **官方頁沒有任何授權條款**，只寫「請引用論文」；下載走 Google Drive / 百度盤 | 未知（無授權＝預設保留所有權利） | 未採用（授權不明） | M6，待使用者決定（見 Phase 0 回報） | http://faculty.neu.edu.cn/songkechen/zh_CN/zdylm/263270/list/index.htm |
| DeepPCB（1500 張 640x640，Phase 5 已下載並用於訓練） | 資料放在 GitHub repo 內，repo 授權 **MIT** | 是 | 免費（資料集，依各自授權） | M6（clone 整個 repo，231MB） | https://github.com/tangsanli5201/DeepPCB |
| Hard Hat Workers（5297 train + 1766 test，Phase 5 已下載並用於訓練） | **CC0 1.0**（Harvard Dataverse API 回傳；Roboflow 頁標示 Public Domain） | 是 | 免費（資料集，依各自授權） | M5 PPE（只有 helmet/head 兩類，**沒有反光背心類別**，資料集本身的限制） | https://doi.org/10.7910/DVN/7CBGOS（實際下載 https://dataverse.harvard.edu/api/access/datafile/3344658，268MB rar） |
| Safety-Helmet-Wearing-Dataset（SHWD） | repo 為 MIT，但 README 寫正樣本圖片「從 Google/百度蒐集」，圖片本身版權不明 | 不明 | 未採用（版權不明） | 不採用，改用 CC0 的 Hard Hat Workers | https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset |
| MedMNIST（PneumoniaMNIST，Phase 7 已下載並用於訓練，train 4708/val 524/test 624 張，28x28 灰階，來源 Zenodo） | **CC BY 4.0**（DermaMNIST 例外為 CC BY-NC 4.0，本專案不用）；官方註明 NOT intended for clinical use | 是（需署名） | 免費（資料集，依各自授權） | M8-2 教學展示，**僅供技術展示，非醫療診斷用途** | https://github.com/MedMNIST/MedMNIST |
| COCO（YOLO 預訓練所用） | 標註 CC BY 4.0；圖片依 Flickr 各自授權 | — | 未下載資料集 | 只用預訓練權重，不下載資料集 | https://cocodataset.org/#termsofuse |
| 《Worker operates machinery in a factory setting》（Wikimedia Commons） | **CC BY 2.0** | 是（需署名） | 免費（資料集，依各自授權） | Phase 2 `tests/live_samples/`：M5 真人偵測的 live 測試/手動驗證用照片，不進版控 | https://commons.wikimedia.org/wiki/File:Worker_operates_machinery_in_a_factory_setting.jpg |

## 本產品授權與第三方元件

> 以下為工程上的整理，**非法律意見**；商用或散佈前請諮詢法務。

- **本產品授權：AGPL-3.0-or-later**（見根目錄 `LICENSE`，全文取自 https://www.gnu.org/licenses/agpl-3.0.txt，2026-09-29）。理由：相依的 Ultralytics 為 AGPL-3.0（PyPI 標示 AGPLv3+，另售 Enterprise 授權），本產品透過網路提供服務，整體以 AGPL 釋出最單純。
- **AGPL 義務**：若修改本產品並讓他人透過網路使用，須向這些使用者提供修改後的完整原始碼；散佈時須附 `LICENSE` 並保留版權聲明。
- **相容性**：其餘相依（MIT、BSD-3-Clause、Apache-2.0、MIT-CMU）皆可併入 AGPL 專案。不建議改採 MIT／Apache-2.0 釋出，因為與 Ultralytics 的 AGPL 條款不相容；若需非 AGPL 散佈，須改買 Ultralytics Enterprise 授權（付費，本專案不採用）。
- **權重與資料集**：`models/`、`data/` 不進版控、不隨 repo 散佈。以非商用資料集（MVTec AD：CC BY-NC-SA 4.0）擬合出的權重，**不得用於商業產線**；PneumoniaMNIST（CC BY 4.0）訓練的分類模型僅供技術展示，非醫療診斷用途。正式導入時，異常檢測與監督式模型須以自有資料重新擬合／訓練。
- **Gemini 免費層（可選備援）**：條款頁（https://ai.google.dev/gemini-api/terms，頁面標示更新日 2026-04-28，查證日 2026-09-29）載明免費服務的輸入與輸出可能被 Google 用於改進產品並由人工審閱。**不可啟用計費帳戶，也不要送出敏感、機密或個資影像**；核心辨識（Ollama）不受影響。

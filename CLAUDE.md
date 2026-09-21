# vision-ai-demo — 視覺辨識 AI 專案

## 專案目標

本機網頁 Demo，兩個獨立功能：

1. **街景照片通用辨識**：上傳一張照片，AI 用開放式描述回答「這是什麼」（招牌店名、建築物、商品品牌、場景描述等），不是固定類別框選。
2. **文件/圖檔轉結構化資料**：上傳文件或掃描圖檔，AI 擷取內容並整理成 JSON/表格資料（例如發票的品項/金額/日期）。

## 技術決策與理由

- **辨識引擎：Google Gemini API（`gemini-3.6-flash`），免費層**
  - 註：原本規劃用 `gemini-2.0-flash`，實測時 API 回報該模型已下架（404 NOT_FOUND），官方訊息指示改用 `gemini-3.6-flash`，已修正並重新驗證通過。
  - 理由：本地 YOLOv8 這類傳統 CV 模型只認得 COCO 等預訓練的固定類別（車/人/狗…），無法做「這是什麼招牌/品牌/建築物」這種開放式理解。多模態 LLM 才能做到通用辨識。
  - 免費層透過 [Google AI Studio](https://aistudio.google.com/apikey) 申請 API key，無需信用卡。
- **文件 OCR：Tesseract（pytesseract）+ Gemini 二段式**
  - 先用 Tesseract 本地擷取原始文字（免費、離線、支援繁中），再把文字丟給 Gemini 依文件類型解析成 JSON 欄位。
  - 同時保留「直接把圖片丟給 Gemini 端到端辨識」的模式（更準，尤其手寫或複雜版面），兩種模式可比較效果。
- **後端：FastAPI + Uvicorn**（本機執行，不需部署雲端）
- **前端：純 HTML/CSS/JS**，不用框架，降低複雜度，單頁上傳介面即可

## 目錄結構

```
vision-ai-demo/
├── backend/
│   ├── main.py              # FastAPI 入口，路由掛載
│   ├── vision_scan.py       # 街景辨識邏輯（呼叫 Gemini）
│   ├── doc_extract.py       # 文件 OCR + 結構化（Tesseract + Gemini）
│   └── requirements.txt
├── frontend/
│   └── index.html           # 單頁上傳介面
├── .env                     # GEMINI_API_KEY（不進版控）
└── CLAUDE.md                # 本檔案
```

## 環境需求

- Python 3.10+
- Tesseract OCR 執行檔（macOS: `brew install tesseract tesseract-lang` 以支援繁中）
- Google Gemini API key（存在 `.env` 的 `GEMINI_API_KEY`）

## 待辦（規劃完成後的實作順序）

- [x] `backend/requirements.txt`：fastapi, uvicorn, google-genai, pytesseract, pillow, python-dotenv, python-multipart
- [x] `backend/vision_scan.py`：接收圖片 → base64 → Gemini prompt（要求 JSON 輸出：物件名稱、描述、額外資訊）
- [x] `backend/doc_extract.py`：接收圖片 → Tesseract 擷取文字 → Gemini 結構化 JSON；另提供純端到端模式
- [x] `backend/main.py`：兩個 API 路由 `/api/scan`、`/api/extract`，掛載 CORS，靜態檔案服務 frontend
- [x] `frontend/index.html`：兩個上傳區塊，各自顯示辨識結果（JSON 轉表格顯示）
- [x] 已安裝：Homebrew 裝好 Tesseract 5.5.3（含 chi_tra 繁中語言包），Python venv 裝好所有套件
- [x] 手動測試：啟動 uvicorn 後 curl 打 `/api/scan`、`/api/extract` 皆正常回應（含缺 API key 時的錯誤處理、OCR 抓不到文字時的提前擋下），瀏覽器截圖確認前端畫面正常渲染
- [x] `.env` 已填入真實 API key，透過真實 Chrome 瀏覽器（非 headless 內建瀏覽器，該環境不支援模擬檔案選擇對話框）實際上傳圖片測試，`/api/scan` 成功回傳正確的開放式辨識結果（正確讀出畫面中的專案名稱、UI 文字等細節），`/api/extract` 兩種模式（OCR 兩段式、端到端）皆測試成功
- [x] 修掉一個真實 bug：`main.py` 原本只 `except RuntimeError`，沒接住 Gemini SDK 丟出的 `google.genai.errors.APIError`（涵蓋 `ClientError`/`ServerError`），導致 Gemini 過載時回傳純文字 `Internal Server Error`，前端 `JSON.parse` 直接爆錯、看不出真正原因。已改為額外 `except APIError` 回傳結構化 JSON 錯誤（HTTP 502 + 清楚的中文訊息）。

## 啟動方式

```bash
cd ~/Documents/vision-ai-demo
source venv/bin/activate
cd backend
uvicorn main:app --reload
```

瀏覽器開 http://127.0.0.1:8000

## 已知限制

- Gemini 免費層有速率限制（RPM），demo 用途足夠，但不適合高流量正式環境
- Tesseract 對低品質掃描件辨識率有限，複雜版面建議直接用 Gemini 端到端模式
- 本機 Demo 僅供 localhost 存取，若要手機上傳需另外部署（不在本次規劃範圍內）

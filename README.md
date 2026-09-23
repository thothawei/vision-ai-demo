# 視覺辨識 AI Demo

> **重構中**：本專案正在改造成「台中製造業 AI 辨識 Demo」（多個免訓練/需訓練的製造業辨識模組），詳見 [CLAUDE.md](CLAUDE.md) 的待辦與測試紀錄。以下安裝步驟是 Phase 1 之前的舊版，Phase 8 會整份改寫。

本機執行的視覺辨識網頁 Demo，兩個功能：

1. **街景照片通用辨識**：上傳一張照片，AI 判斷「這是什麼」（招牌店名、建築物、商品品牌、場景描述等），不是固定類別框選。
2. **文件/圖檔轉結構化資料**：上傳文件或掃描圖檔，AI 擷取內容並整理成 JSON 欄位（例如發票的品項/金額/日期）。

用到的工具全部免費：Google Gemini API 免費層、Tesseract OCR、FastAPI、純 HTML/JS。

## 安裝

### 1. 系統需求

- Python 3.10+（測試環境用 3.9 也能跑，但官方已停止支援，建議用較新版本）
- [Homebrew](https://brew.sh)（macOS 套件管理工具）

### 2. 安裝 Tesseract OCR

```bash
brew install tesseract tesseract-lang
```

`tesseract-lang` 會裝繁體中文語言包（`chi_tra`），文件辨識才能認得中文。

### 3. 建立 Python 虛擬環境並安裝套件

```bash
git clone https://github.com/thothawei/vision-ai-demo.git
cd vision-ai-demo
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 4. 申請 Gemini API Key

去 [Google AI Studio](https://aistudio.google.com/apikey) 用 Google 帳號登入，點「Create API key」，免費、不需信用卡。

複製 `.env.example` 為 `.env`，把申請到的 key 填進去：

```bash
cp .env.example .env
```

編輯 `.env`：

```
GEMINI_API_KEY=你申請到的key
```

## 啟動

```bash
source venv/bin/activate
cd backend
uvicorn main:app --reload
```

瀏覽器開 <http://127.0.0.1:8000>。

## 使用方式

- **① 街景照片辨識**：選一張照片 → 按「開始辨識」→ 等幾秒會顯示主要物件、類別、詳細描述、信心程度。
- **② 文件／圖檔轉結構化資料**：選一份文件或截圖 → 選擇模式（OCR + AI 結構化 / 端到端）→ 按「開始擷取」→ 顯示文件類型、結構化欄位、原始文字。
  - **OCR + AI 結構化**：先用 Tesseract 抓文字，再用 AI 整理成欄位，速度較快。
  - **端到端**：圖片直接丟給 AI 讀，準確度較高，適合手寫或複雜版面，但較慢。

## 已知限制

- **Gemini 免費層速率限制**：`gemini-3.6-flash` 免費層實測是 **每分鐘 5 次、每日 20 次**（去 [Rate Limit 儀表板](https://aistudio.google.com/rate-limit) 可查即時用量）。遇到「目前流量過大」通常等幾十秒重試就會好；但如果連續重試好幾分鐘都失敗，很可能是當天 20 次的額度用完了，這種情況等多久都沒用，只能等隔天重置或設定計費方案。
- Tesseract 對低品質掃描件辨識率有限，複雜版面建議改用端到端模式。
- 僅供本機 `localhost` 使用，若要手機或外部裝置存取需另外部署。

## 專案結構

```
vision-ai-demo/
├── backend/
│   ├── main.py              # FastAPI 入口，兩個 API 路由
│   ├── vision_scan.py       # 街景辨識邏輯
│   ├── doc_extract.py       # 文件 OCR + 結構化
│   └── requirements.txt
├── frontend/
│   └── index.html           # 單頁上傳介面
└── .env.example              # API key 設定範本
```

"""集中所有 `.env` 設定：型別驗證、預設值、說明與生效時機在同一處。

`apply` 標記：
- `live`：每次呼叫 `get_settings()` 都重新讀環境變數與 `.env`，改了立即生效。
- `restart`：只在服務啟動時讀一次（例如 CORS 白名單被烤進中介層），改了要重啟。
真實環境變數優先於 `.env` 檔。文件的設定表由 `scripts/gen_settings_doc.py` 由本檔產生。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def _f(default, description: str, apply: str = "live", **kw):
    return Field(default, description=description, json_schema_extra={"apply": apply}, **kw)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    llm_engine: str = _f("ollama", "LLM 引擎：ollama（離線）或 gemini（免費層備援）")
    ollama_model: str = _f("qwen3.5:9b", "Ollama 模型名稱")
    ollama_keep_alive: str = _f("5m", "模型閒置多久後釋放記憶體")
    ollama_timeout: float = _f(300.0, "Ollama 呼叫逾時（秒）")
    gemini_api_key: str | None = _f(None, "僅 LLM_ENGINE=gemini 需要；請勿啟用計費帳戶")
    gemini_model: str = _f("gemini-3.6-flash", "Gemini 模型")

    save_images: bool = _f(True, "是否存原圖與標註圖")
    inspection_db: Path | None = _f(None, "檢驗紀錄 SQLite 路徑（預設 data/inspections.db）")
    inspection_images_dir: Path | None = _f(None, "圖片存放目錄（預設 data/images）")
    golden_samples_dir: Path | None = _f(None, "黃金樣本目錄（預設 data/golden_samples）")

    api_keys: str = _f("", "/api/inspections* 的 X-API-Key 白名單，格式 名稱:key,名稱:key；正式環境務必換成隨機字串")
    cors_origins: str = _f(
        "http://127.0.0.1:8000,http://localhost:8000", "允許的前端網域（逗號分隔）", apply="restart"
    )
    max_upload_mb: int = _f(20, "單張圖片大小上限（MB），超過回 413")
    max_video_mb: int = _f(200, "影片大小上限（MB）")
    erp_webhook_url: str | None = _f(None, "NG 時 POST 通知的網址；空白＝不啟用")

    log_level: str = _f("INFO", "日誌層級（DEBUG／INFO／WARNING／ERROR）", apply="restart")


def get_settings() -> Settings:
    """即時類設定：每次呼叫重新讀取（成本為讀一個小檔案）。"""
    return Settings()


_startup: Settings | None = None


def startup_settings() -> Settings:
    """需重啟類設定：程序內只讀一次。"""
    global _startup
    if _startup is None:
        _startup = Settings()
    return _startup

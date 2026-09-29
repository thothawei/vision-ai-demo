"""Phase 17：集中設定（pydantic-settings）——即時／需重啟、.env 讀取、文件同步。"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from core import settings as settings_module
from core.settings import Settings, get_settings, startup_settings

ROOT = Path(__file__).resolve().parent.parent


def test_defaults(monkeypatch):
    for name in ("LLM_ENGINE", "MAX_UPLOAD_MB", "SAVE_IMAGES", "ERP_WEBHOOK_URL", "API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    s = get_settings()
    assert (s.llm_engine, s.max_upload_mb, s.save_images, s.erp_webhook_url, s.api_keys) == (
        "ollama", 20, True, None, "")


def test_live_settings_reflect_env_changes_immediately(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "5")
    assert get_settings().max_upload_mb == 5
    monkeypatch.setenv("MAX_UPLOAD_MB", "7")
    assert get_settings().max_upload_mb == 7


def test_startup_settings_are_read_once(monkeypatch):
    monkeypatch.setattr(settings_module, "_startup", None)
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example")
    assert startup_settings().cors_origins == "http://a.example"
    monkeypatch.setenv("CORS_ORIGINS", "http://b.example")
    assert startup_settings().cors_origins == "http://a.example"  # 改了不生效，要重啟


def test_dotenv_file_is_read_live_and_real_env_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("MAX_UPLOAD_MB=11\nLLM_ENGINE=gemini\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    monkeypatch.delenv("LLM_ENGINE", raising=False)
    assert get_settings().max_upload_mb == 11
    env_file.write_text("MAX_UPLOAD_MB=12\n", encoding="utf-8")  # 改 .env 不必重啟
    assert get_settings().max_upload_mb == 12
    monkeypatch.setenv("MAX_UPLOAD_MB", "99")  # 真實環境變數優先
    assert get_settings().max_upload_mb == 99


def test_empty_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "")
    monkeypatch.setenv("ERP_WEBHOOK_URL", "")
    s = get_settings()
    assert s.max_upload_mb == 20 and s.erp_webhook_url is None


def test_invalid_value_fails_with_clear_error(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "很大")
    with pytest.raises(ValidationError, match="max_upload_mb"):
        get_settings()


def test_every_setting_documents_itself():
    for name, field in Settings.model_fields.items():
        assert field.description, f"{name} 缺說明"
        assert (field.json_schema_extra or {}).get("apply") in ("live", "restart"), f"{name} 缺生效時機"


def test_only_startup_baked_settings_need_restart():
    restart = {n for n, f in Settings.model_fields.items() if f.json_schema_extra["apply"] == "restart"}
    assert restart == {"cors_origins", "log_level", "session_secret", "session_hours", "session_cookie_secure"}


def test_admin_guide_settings_table_is_up_to_date():
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_settings_doc.py"), "--check"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout


def test_no_direct_environ_reads_left_in_backend():
    """設定一律走 core/settings.py；只有 TRUST_REMOTE_CODE 是程式自己寫入環境變數，不是設定。"""
    offenders = []
    for path in (ROOT / "backend").rglob("*.py"):
        if path.name == "settings.py":
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "os.environ.get" in line or "os.getenv" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{no}")
    assert offenders == []

import io

import pytest
from fastapi.testclient import TestClient

from samples import make_samples


def png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 每個測試用獨立的 SQLite，不污染 data/inspections.db
    monkeypatch.setenv("INSPECTION_DB", str(tmp_path / "inspections.db"))
    from main import app

    return TestClient(app)


@pytest.fixture
def fake_llm(monkeypatch):
    """把 LLM 換成假函式，記錄收到的 prompt，回傳固定 JSON。"""
    calls = []

    def _fake(prompt, image=None):
        calls.append({"prompt": prompt, "has_image": image is not None})
        return {"主要物件": "測試物件", "文件類型": "工單", "欄位": {}}, "fake:model"

    monkeypatch.setattr("core.llm.generate_json", _fake)
    return calls


@pytest.fixture(scope="session")
def work_order_png() -> bytes:
    return png_bytes(make_samples.make_work_order())


@pytest.fixture(scope="session")
def warning_sign_png() -> bytes:
    return png_bytes(make_samples.make_warning_sign())


@pytest.fixture(scope="session")
def blank_png() -> bytes:
    return png_bytes(make_samples.make_blank())

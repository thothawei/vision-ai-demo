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


@pytest.fixture(scope="session")
def screws_png() -> bytes:
    return png_bytes(make_samples.make_screws_photo())


def gs1_png_and_fields(days_from_today: int):
    image, fields = make_samples.make_gs1_datamatrix(days_from_today)
    return png_bytes(image), fields


@pytest.fixture(scope="session")
def gs1_valid_png_fields():
    return gs1_png_and_fields(200)


@pytest.fixture(scope="session")
def gs1_expired_png_fields():
    return gs1_png_and_fields(-10)


@pytest.fixture(scope="session")
def gs1_expiring_soon_png_fields():
    return gs1_png_and_fields(10)


@pytest.fixture(scope="session")
def measure_scene_png_marker():
    image, marker_mm = make_samples.make_measure_scene(target_length_mm=50, target_width_mm=20, hole_diameter_mm=5)
    return png_bytes(image), marker_mm


@pytest.fixture
def fake_person_detector(monkeypatch):
    """把 YOLO 換成假函式，回傳固定的偵測框（單位 px，對應 800x600 測試圖）。"""
    def _fake(bgr):
        return [{"信心度": 0.9, "邊界框": [100, 100, 200, 500], "腳底參考點": [150, 500]}]

    monkeypatch.setattr("modules.safety.service._detect_persons", _fake)


class _FakeAnomalyPrediction:
    def __init__(self, score: float, is_anomalous: bool):
        import torch

        self.pred_score = score
        self.pred_label = is_anomalous
        self.anomaly_map = torch.rand(1, 1, 32, 32) * score


@pytest.fixture
def fake_anomaly_inferencer(monkeypatch):
    """把 anomalib 推論換成假函式，回傳固定分數，記錄被問到哪個 category。"""
    calls = []

    class _FakeInferencer:
        def __init__(self, score, is_anomalous):
            self._score = score
            self._is_anomalous = is_anomalous

        def predict(self, image):
            calls.append(image)
            return _FakeAnomalyPrediction(self._score, self._is_anomalous)

    def _fake_get_inferencer(category):
        calls.append(category)
        # 用 category 名稱決定假分數：帶 "ng" 的當異常，其餘正常，方便測試指定結果
        return _FakeInferencer(0.9, True) if "ng" in category else _FakeInferencer(0.1, False)

    monkeypatch.setattr("modules.anomaly.service._get_inferencer", _fake_get_inferencer)
    monkeypatch.setattr("modules.anomaly.service.CATEGORIES", ["metal_nut", "screw", "tile", "metal_nut_ng"])
    return calls

import io

import pytest
from fastapi.testclient import TestClient

from samples import make_samples


def png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def make_video_bytes(n_frames: int, width: int = 100, height: int = 100, fps: float = 1.0) -> bytes:
    """產生一支最小的合成 mp4（純黑幀），給 Phase 11 影片端點測試用，不依賴外部影片檔。"""
    import os
    import tempfile

    import cv2
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = tmp.name
    try:
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        for _ in range(n_frames):
            writer.write(np.zeros((height, width, 3), dtype=np.uint8))
        writer.release()
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


TEST_API_KEY = "test-key"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 每個測試用獨立的 SQLite 與圖片目錄，不污染 data/inspections.db、data/images/
    monkeypatch.setenv("INSPECTION_DB", str(tmp_path / "inspections.db"))
    monkeypatch.setenv("INSPECTION_IMAGES_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("GOLDEN_SAMPLES_DIR", str(tmp_path / "golden_samples"))
    # Phase 10：/api/inspections* 需要 X-API-Key，預設帶好測試 key，
    # 這樣既有測試（呼叫 /api/inspections*）不用逐一加 header；
    # 專門測「沒帶/帶錯 key」行為的測試改用不帶預設 header 的 client。
    monkeypatch.setenv("API_KEYS", f"erp:{TEST_API_KEY},frontend:{TEST_API_KEY}")
    from main import app

    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


@pytest.fixture
def fake_llm_queue(monkeypatch):
    """M4 一次請求會呼叫兩次 LLM（分類→結構化），依序把要回傳的內容放進佇列。

    用法：responses.append(({"文件類型": "工單"}, "fake:classify"))
         responses.append(({...}, "fake:extract"))
    """
    responses: list[tuple[dict, str]] = []
    calls: list[dict] = []

    def _fake(prompt, image=None):
        calls.append({"prompt": prompt, "has_image": image is not None})
        if not responses:
            raise AssertionError("fake_llm_queue 已經用完，測試準備的回應數量不夠")
        return responses.pop(0)

    monkeypatch.setattr("core.llm.generate_json", _fake)
    return responses, calls


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


@pytest.fixture(scope="session")
def inspection_report_png() -> bytes:
    return png_bytes(make_samples.make_inspection_report())


@pytest.fixture(scope="session")
def shipping_order_png() -> bytes:
    return png_bytes(make_samples.make_shipping_order())


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


@pytest.fixture(scope="session")
def nameplate_png() -> bytes:
    return png_bytes(make_samples.make_nameplate())


@pytest.fixture(scope="session")
def seven_segment_png() -> bytes:
    return png_bytes(make_samples.make_seven_segment("235"))


@pytest.fixture
def gauge_png_factory():
    """回傳一個 function(needle_angle_deg) -> png bytes，測試不同指針角度用。"""
    def _make(needle_angle_deg: float, min_angle_deg: float = 135, max_angle_deg: float = 45):
        image = make_samples.make_gauge(min_angle_deg, max_angle_deg, needle_angle_deg)
        return png_bytes(image)
    return _make


@pytest.fixture(scope="session")
def packaging_match_png() -> bytes:
    return png_bytes(make_samples.make_packaging(days_from_today=200))


@pytest.fixture
def packaging_mismatch_png_factory():
    """回傳 function(printed_batch=None, printed_expiry=None) -> png bytes。"""
    def _make(**kwargs):
        return png_bytes(make_samples.make_packaging(days_from_today=200, **kwargs))
    return _make


@pytest.fixture
def fake_pneumonia_model(monkeypatch):
    """回傳固定機率的假模型，不依賴真實訓練權重。"""
    import torch

    class _FakeModel:
        def __call__(self, tensor):
            return torch.tensor([[10.0]])  # sigmoid(10) ≈ 1.0，穩定判成 pneumonia

        def eval(self):
            return self

    monkeypatch.setattr("modules.medical.service._get_model", lambda: _FakeModel())


@pytest.fixture
def fake_person_detector(monkeypatch):
    """把 YOLO 換成假函式，回傳固定的偵測框（單位 px，對應 800x600 測試圖）。"""
    def _fake(bgr):
        return [{"信心度": 0.9, "邊界框": [100, 100, 200, 500], "腳底參考點": [150, 500]}]

    monkeypatch.setattr("modules.safety.service._detect_persons", _fake)


@pytest.fixture
def fake_pcb_detector(monkeypatch):
    """把 M6 PCB 瑕疵偵測換成假函式，回傳固定的偵測框。"""
    class _FakeBox:
        def __init__(self, cls, conf, xyxy):
            import torch

            self.cls = torch.tensor([cls])
            self.conf = torch.tensor([conf])
            self.xyxy = torch.tensor([xyxy])

    class _FakeResult:
        boxes = [_FakeBox(0, 0.9, [10, 10, 50, 50])]  # class 0 = "open"

    class _FakeModel:
        names = {0: "open", 1: "short", 2: "mousebite", 3: "spur", 4: "copper", 5: "pin-hole"}

        def predict(self, bgr, conf=0.4, verbose=False):
            return [_FakeResult()]

    monkeypatch.setattr("modules.defect.service._get_model", lambda: _FakeModel())


@pytest.fixture
def fake_pcb_detector_no_defect(monkeypatch):
    class _FakeResult:
        boxes = []

    class _FakeModel:
        names = {0: "open", 1: "short", 2: "mousebite", 3: "spur", 4: "copper", 5: "pin-hole"}

        def predict(self, bgr, conf=0.4, verbose=False):
            return [_FakeResult()]

    monkeypatch.setattr("modules.defect.service._get_model", lambda: _FakeModel())


@pytest.fixture
def fake_ppe_detector(monkeypatch):
    """回傳 1 個 helmet + 1 個 head（未戴安全帽），驗證 NG 判定。"""
    class _FakeBox:
        def __init__(self, cls, conf, xyxy):
            import torch

            self.cls = torch.tensor([cls])
            self.conf = torch.tensor([conf])
            self.xyxy = torch.tensor([xyxy])

    class _FakeResult:
        boxes = [_FakeBox(0, 0.95, [10, 10, 50, 50]), _FakeBox(1, 0.88, [100, 10, 140, 50])]

    class _FakeModel:
        names = {0: "helmet", 1: "head"}

        def predict(self, bgr, conf=0.4, verbose=False):
            return [_FakeResult()]

    monkeypatch.setattr("modules.safety.service._get_ppe_model", lambda: _FakeModel())


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

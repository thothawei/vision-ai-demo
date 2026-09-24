"""Phase 11：M5 短影片逐幀抽樣（危險區域入侵 / PPE）。"""

from conftest import make_video_bytes


def test_intrusion_video_detects_violation_in_zone(client, fake_person_detector):
    # 800x600 對應 fake_person_detector 固定回傳的腳底參考點 [150,500]
    video = make_video_bytes(5, width=800, height=600, fps=1.0)
    zone = '[[0.0,0.0],[1.0,0.0],[1.0,1.0],[0.0,1.0]]'  # 整張圖都是危險區域

    res = client.post(
        "/api/safety/video",
        params={"sample_interval_s": 1, "max_duration_s": 5},
        data={"zone": zone},
        files={"file": ("test.mp4", video, "video/mp4")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "NG"
    item = body["items"][0]
    assert item["取樣幀數"] >= 1
    assert item["違規時間點"], "應該至少有一個違規時間點"
    assert "標註圖" in item["違規時間點"][0]
    assert body["annotated_image"] is not None

    logs = client.get("/api/inspections", params={"module": "safety"}).json()
    assert len(logs) == 1  # 只寫一筆彙總，不是每幀一筆


def test_intrusion_video_no_zone_is_info(client, fake_person_detector):
    video = make_video_bytes(3, width=800, height=600, fps=1.0)
    res = client.post(
        "/api/safety/video",
        params={"sample_interval_s": 1, "max_duration_s": 3},
        files={"file": ("test.mp4", video, "video/mp4")},
    )
    assert res.json()["verdict"] == "INFO"


def test_ppe_video_detects_violation(client, fake_ppe_detector):
    video = make_video_bytes(4, width=200, height=200, fps=1.0)
    res = client.post(
        "/api/safety/ppe/video",
        params={"sample_interval_s": 1, "max_duration_s": 4},
        files={"file": ("test.mp4", video, "video/mp4")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "NG"  # fake_ppe_detector 每幀都有一個未戴安全帽
    item = body["items"][0]
    assert len(item["違規時間點"]) == item["取樣幀數"]  # 每一幀都違規

    logs = client.get("/api/inspections", params={"module": "ppe"}).json()
    assert len(logs) == 1


def test_video_too_large_returns_413(client, fake_person_detector, monkeypatch):
    monkeypatch.setenv("MAX_VIDEO_MB", "0")
    video = make_video_bytes(2, width=100, height=100, fps=1.0)
    res = client.post("/api/safety/video", files={"file": ("test.mp4", video, "video/mp4")})
    assert res.status_code == 413
    assert "過大" in res.json()["detail"]


def test_invalid_video_bytes_returns_400(client):
    res = client.post("/api/safety/ppe/video", files={"file": ("fake.mp4", b"not a real video", "video/mp4")})
    assert res.status_code == 400

"""M2 零件計數與尺寸量測：watershed 相黏分離、ArUco 量測精度、OK/NG 公差判斷。"""

import pytest


def test_count_separates_touching_parts(client, screws_png):
    """6 顆分開 + 2 顆相黏，總共應該數出 8 顆，不是被相黏那兩顆合併成 7 顆。"""
    res = client.post("/api/measure/count", files={"file": ("screws.png", screws_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "measure"
    assert body["items"][0]["計數結果"] == 8
    areas = [d["面積px"] for d in body["items"][0]["明細"]]
    assert len(areas) == 8
    # 分開的每顆應該面積相近（同一個圓半徑畫出來的）
    assert max(areas) - min(areas) < max(areas) * 0.2


def test_count_expected_count_verdict(client, screws_png):
    ok = client.post("/api/measure/count", params={"expected_count": 8},
                     files={"file": ("s.png", screws_png, "image/png")})
    ng = client.post("/api/measure/count", params={"expected_count": 5},
                     files={"file": ("s.png", screws_png, "image/png")})

    assert ok.json()["verdict"] == "OK"
    assert ng.json()["verdict"] == "NG"


def test_measure_accuracy_within_1mm(client, measure_scene_png_marker):
    """正視角、已知 50x20mm 零件 + 5mm 孔，量出來的誤差應該在 1mm 內（無透視變形的理論上限測試）。"""
    png, marker_mm = measure_scene_png_marker
    res = client.post("/api/measure/measure", params={"marker_size_mm": marker_mm},
                      files={"file": ("scene.png", png, "image/png")})

    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert abs(item["長度mm"] - 50) < 1.0
    assert abs(item["寬度mm"] - 20) < 1.0
    assert len(item["孔徑mm"]) == 1
    assert abs(item["孔徑mm"][0] - 5) < 1.0


@pytest.mark.parametrize("target,tol,expect_ok", [(50.5, 1.0, True), (55, 1.0, False)])
def test_measure_ok_ng_by_tolerance(client, measure_scene_png_marker, target, tol, expect_ok):
    png, marker_mm = measure_scene_png_marker
    res = client.post(
        "/api/measure/measure",
        params={"marker_size_mm": marker_mm, "target_length_mm": target, "tolerance_mm": tol},
        files={"file": ("scene.png", png, "image/png")},
    )

    assert (res.json()["verdict"] == "OK") == expect_ok


def test_measure_without_marker_gives_clear_error(client, warning_sign_png):
    res = client.post("/api/measure/measure", files={"file": ("w.png", warning_sign_png, "image/png")})

    assert res.status_code == 422
    assert "ArUco" in res.json()["detail"]

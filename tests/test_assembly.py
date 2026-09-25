"""M10 組裝防呆／黃金樣本比對：黃金樣本設定 CRUD + ORB/homography 對齊 + SSIM ROI 比對。"""

import io
import json

from samples import make_samples


def _png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _save_golden(client, part_no="test_part"):
    golden = make_samples.make_assembly_scene()
    res = client.post(
        "/api/assembly/golden-samples",
        params={"part_no": part_no},
        data={"rois": json.dumps(make_samples.ASSEMBLY_ROIS)},
        files={"file": ("golden.png", _png_bytes(golden), "image/png")},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_create_and_list_golden_sample(client):
    created = _save_golden(client)
    assert created == {"part_no": "test_part", "roi_count": 6}

    listed = client.get("/api/assembly/golden-samples").json()
    assert any(c["part_no"] == "test_part" for c in listed)

    detail = client.get("/api/assembly/golden-samples/test_part").json()
    assert detail["part_no"] == "test_part"
    assert len(detail["rois"]) == 6
    assert detail["golden_image"].startswith("data:image/png;base64,")


def test_get_golden_sample_404(client):
    res = client.get("/api/assembly/golden-samples/no_such_part")
    assert res.status_code == 404


def test_invalid_part_no_rejected(client):
    golden = make_samples.make_assembly_scene()
    res = client.post(
        "/api/assembly/golden-samples",
        params={"part_no": "有 中文"},
        data={"rois": json.dumps(make_samples.ASSEMBLY_ROIS)},
        files={"file": ("golden.png", _png_bytes(golden), "image/png")},
    )
    assert res.status_code == 400


def test_no_rois_rejected(client):
    golden = make_samples.make_assembly_scene()
    res = client.post(
        "/api/assembly/golden-samples",
        params={"part_no": "empty_rois"},
        data={"rois": json.dumps([])},
        files={"file": ("golden.png", _png_bytes(golden), "image/png")},
    )
    assert res.status_code == 400


def test_inspect_unknown_part_404(client):
    golden = make_samples.make_assembly_scene()
    res = client.post("/api/assembly/inspect", params={"part_no": "no_such_part"},
                      files={"file": ("t.png", _png_bytes(golden), "image/png")})
    assert res.status_code == 404


def test_inspect_full_scene_is_ok(client):
    _save_golden(client)
    target = make_samples.make_assembly_scene()
    res = client.post("/api/assembly/inspect?part_no=test_part",
                      files={"file": ("t.png", _png_bytes(target), "image/png")})
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "OK"
    assert all(r["判定"] == "OK" for r in body["items"][0]["明細"])


def test_inspect_missing_component_is_ng(client):
    _save_golden(client)
    target = make_samples.make_assembly_scene(missing_index=2)
    res = client.post("/api/assembly/inspect?part_no=test_part",
                      files={"file": ("t.png", _png_bytes(target), "image/png")})
    body = res.json()
    assert body["verdict"] == "NG"
    ng_rois = [r["ROI編號"] for r in body["items"][0]["明細"] if r["判定"] == "NG"]
    assert ng_rois == [3]  # missing_index=2 是 0-based，對應 ROI 編號 3（1-based）


def test_inspect_rotated_component_is_ng(client):
    """零件裝反 180 度（方向錯誤，不是缺件）也要判 NG——這是刻意設計不對稱零件圖案要驗證的情境，
    純圓形零件旋轉 180 度會完全看不出差異。"""
    _save_golden(client)
    target = make_samples.make_assembly_scene(rotated_index=3)
    res = client.post("/api/assembly/inspect?part_no=test_part",
                      files={"file": ("t.png", _png_bytes(target), "image/png")})
    body = res.json()
    assert body["verdict"] == "NG"
    ng_rois = [r["ROI編號"] for r in body["items"][0]["明細"] if r["判定"] == "NG"]
    assert ng_rois == [4]


def test_alignment_robust_to_rotation_and_scale(client):
    """±15 度旋轉、±20% 縮放：對齊仍要成功，且零件都正確時判 OK（不是誤判成 NG）。"""
    _save_golden(client)
    base = make_samples.make_assembly_scene()

    variants = {
        "旋轉+15度": base.rotate(15, expand=True, fillcolor=(230, 230, 230)),
        "旋轉-15度": base.rotate(-15, expand=True, fillcolor=(230, 230, 230)),
        "縮小80%": base.resize((720, 400)),
        "放大120%": base.resize((1080, 600)),
    }
    for label, img in variants.items():
        res = client.post("/api/assembly/inspect?part_no=test_part",
                          files={"file": ("t.png", _png_bytes(img), "image/png")})
        body = res.json()
        assert body["verdict"] == "OK", f"{label} 應該判 OK，實際 {body['verdict']}：{body['items']}"
        item = body["items"][0]
        assert item["對齊inlier比例"] is not None and item["對齊inlier比例"] > 0.5, label


def test_alignment_failure_returns_info_not_a_guess(client):
    """完全不相關的畫面（純雜訊）應該對齊失敗，回傳 INFO 而不是硬猜 OK/NG。"""
    _save_golden(client)
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(42)
    noise = Image.fromarray(rng.integers(0, 255, (500, 900, 3), dtype=np.uint8))
    res = client.post("/api/assembly/inspect?part_no=test_part",
                      files={"file": ("noise.png", _png_bytes(noise), "image/png")})
    body = res.json()
    assert body["verdict"] == "INFO"
    assert body["items"][0]["原因"] is not None

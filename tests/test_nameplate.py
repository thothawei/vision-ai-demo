"""M7 銘牌／儀表讀值：
- 銘牌：RapidOCR 真的跑，LLM 用假佇列（跟 M4 同樣只有一次 LLM 呼叫，不是兩段式）
- 七段顯示器：純 OpenCV，不需要任何假模型，真跑真驗證
- 指針錶：純 OpenCV，同上
"""


def test_nameplate_valid_extraction(client, fake_llm_queue, nameplate_png):
    responses, calls = fake_llm_queue
    responses.append(({
        "廠牌": "中科精機", "型號": "CK-850V", "序號": "SN-20260088",
        "製造日期": "2026-03", "電壓": "220V",
    }, "fake:model"))

    res = client.post("/api/nameplate/read", files={"file": ("np.png", nameplate_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "nameplate"
    assert body["verdict"] == "OK"
    assert body["engine"] == "rapidocr+fake:model"
    item = body["items"][0]
    assert item["型號"] == "CK-850V"
    assert "_ocr原始文字" in item
    assert calls[0]["has_image"] is False  # 送 OCR 文字，不是圖片


def test_nameplate_missing_field_gives_ng(client, fake_llm_queue, nameplate_png):
    responses, _ = fake_llm_queue
    responses.append(({"廠牌": "中科精機"}, "fake:model"))  # 故意缺其他必填欄位

    res = client.post("/api/nameplate/read", files={"file": ("np.png", nameplate_png, "image/png")})

    body = res.json()
    assert body["verdict"] == "NG"
    assert "_驗證錯誤" in body["items"][0]


def test_nameplate_blank_image_rejected(client, fake_llm_queue, blank_png):
    res = client.post("/api/nameplate/read", files={"file": ("b.png", blank_png, "image/png")})
    assert res.status_code == 422
    _, calls = fake_llm_queue
    assert calls == []


def test_seven_segment_reads_correctly(client, seven_segment_png):
    res = client.post("/api/nameplate/seven-segment", files={"file": ("s.png", seven_segment_png, "image/png")})

    assert res.status_code == 200
    body = res.json()
    assert body["module"] == "nameplate"
    assert body["verdict"] == "OK"
    assert body["engine"] == "opencv-sevenseg"
    assert body["items"][0]["讀值"] == "235"
    assert len(body["items"][0]["明細"]) == 3
    assert body["annotated_image"].startswith("data:image/png;base64,")


def test_seven_segment_all_digits_0_to_9(client):
    import io

    from samples.make_samples import make_seven_segment

    buf = io.BytesIO()
    make_seven_segment("0123456789").save(buf, format="PNG")

    res = client.post("/api/nameplate/seven-segment", files={"file": ("d.png", buf.getvalue(), "image/png")})
    assert res.json()["items"][0]["讀值"] == "0123456789"


def test_seven_segment_no_digits_found(client, blank_png):
    res = client.post("/api/nameplate/seven-segment", files={"file": ("b.png", blank_png, "image/png")})
    assert res.status_code == 422


def test_gauge_reads_min_mid_max(client, gauge_png_factory):
    cases = [(135, 0), (270, 50), (45, 100)]  # (指針角度, 預期讀值)
    for needle_angle, expected in cases:
        png = gauge_png_factory(needle_angle)
        res = client.post("/api/nameplate/gauge",
                          params={"min_value": 0, "max_value": 100, "min_angle": 135, "max_angle": 45},
                          files={"file": ("g.png", png, "image/png")})
        assert res.status_code == 200, res.text
        value = res.json()["items"][0]["讀值"]
        assert abs(value - expected) < 5, f"needle={needle_angle} 預期約 {expected} 實際 {value}"


def test_gauge_boundary_noise_does_not_wrap_to_opposite_end(client, gauge_png_factory):
    """指針幾乎剛好在 min_angle，量測雜訊不該讓讀值跳到 max（真的踩過的 bug，見 CLAUDE.md）。"""
    png = gauge_png_factory(needle_angle_deg=135, min_angle_deg=135, max_angle_deg=45)
    res = client.post("/api/nameplate/gauge",
                      params={"min_value": 0, "max_value": 100, "min_angle": 135, "max_angle": 45},
                      files={"file": ("g.png", png, "image/png")})
    assert res.json()["items"][0]["讀值"] < 10


def test_gauge_no_needle_found(client, blank_png):
    res = client.post("/api/nameplate/gauge",
                      params={"center_x": 0.5, "center_y": 0.5},
                      files={"file": ("b.png", blank_png, "image/png")})
    assert res.status_code == 422

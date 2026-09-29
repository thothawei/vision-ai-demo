"""Phase 20：SPC——管制圖、Cp／Cpk、Western Electric 規則、量測值正規化與 API。
數值用手算範例驗證（標準係數表 A2=0.577、D4=2.114、d2=2.326；I-MR 2.660／3.267／1.128）。"""

import pytest

from core import spc
from core.inspection_log import connect, log_inspection

# 三個子群（n=5）：平均 11／12／10，全距都是 4 → X̄̄=11、R̄=4
GROUPS = [9, 10, 11, 12, 13, 10, 11, 12, 13, 14, 8, 9, 10, 11, 12]


# --- 純計算 ---

def test_xbar_r_limits_and_capability_match_hand_calculation():
    r = spc.xbar_r(GROUPS, 5, lsl=5, usl=16)
    x, rng = r["x_chart"], r["range_chart"]
    assert x["points"] == [11.0, 12.0, 10.0] and rng["points"] == [4.0, 4.0, 4.0]
    assert x["center"] == pytest.approx(11.0) and rng["center"] == pytest.approx(4.0)
    assert x["ucl"] == pytest.approx(11 + 0.577 * 4) == pytest.approx(13.308)
    assert x["lcl"] == pytest.approx(8.692)
    assert rng["ucl"] == pytest.approx(2.114 * 4) == pytest.approx(8.456) and rng["lcl"] == 0.0
    sigma = 4 / 2.326
    assert r["sigma_within"] == pytest.approx(sigma)
    cap = r["capability"]
    assert cap["cp"] == pytest.approx((16 - 5) / (6 * sigma)) == pytest.approx(1.06608, rel=1e-4)
    assert cap["cpu"] == pytest.approx(5 / (3 * sigma)) == pytest.approx(0.96917, rel=1e-4)
    assert cap["cpl"] == pytest.approx(6 / (3 * sigma)) == pytest.approx(1.163, rel=1e-3)
    assert cap["cpk"] == pytest.approx(cap["cpu"])  # 取較小的一邊
    assert r["subgroups"] == 3 and cap["reference_only"] is True  # 少於 25 個子群


def test_imr_limits_and_capability_match_hand_calculation():
    values = [10, 12, 11, 13, 12, 14, 11, 10]
    r = spc.imr(values, lsl=6, usl=16)
    mrbar = (2 + 1 + 2 + 1 + 2 + 3 + 1) / 7
    assert r["range_chart"]["points"] == [2, 1, 2, 1, 2, 3, 1]
    assert r["x_chart"]["center"] == pytest.approx(11.625)
    assert r["x_chart"]["ucl"] == pytest.approx(11.625 + 2.66 * mrbar) == pytest.approx(16.185)
    assert r["x_chart"]["lcl"] == pytest.approx(7.065)
    assert r["range_chart"]["ucl"] == pytest.approx(3.267 * mrbar) == pytest.approx(5.6006, rel=1e-4)
    assert r["sigma_within"] == pytest.approx(mrbar / 1.128)
    assert r["capability"]["cp"] == pytest.approx(1.09667, rel=1e-4)
    assert r["capability"]["cpk"] == pytest.approx(0.95958, rel=1e-4)


def test_incomplete_tail_is_ignored_and_too_little_data_is_an_error():
    r = spc.xbar_r(GROUPS + [99, 99], 5)
    assert r["subgroups"] == 3 and r["ignored_tail"] == 2 and r["x_chart"]["points"] == [11.0, 12.0, 10.0]
    with pytest.raises(ValueError, match="至少需要 2 個完整子群"):
        spc.xbar_r([1, 2, 3, 4, 5, 6, 7], 5)
    with pytest.raises(ValueError, match="至少需要 3 筆"):
        spc.imr([1, 2])
    with pytest.raises(ValueError, match="2–10"):
        spc.xbar_r(GROUPS, 11)


def test_one_sided_spec_gives_only_cpk_and_no_spec_gives_none():
    one_sided = spc.xbar_r(GROUPS, 5, usl=16)["capability"]
    assert one_sided["cp"] is None and one_sided["cpl"] is None
    assert one_sided["cpk"] == pytest.approx(0.96917, rel=1e-4) and "單邊" in one_sided["note"]
    none = spc.xbar_r(GROUPS, 5)["capability"]
    assert none["cp"] is none["cpk"] is None and "沒有規格" in none["note"]
    zero_var = spc.capability(10.0, 0.0, 5, 15, 30)
    assert zero_var["cpk"] is None and "為 0" in zero_var["note"]


def test_reference_only_flag_needs_25_subgroups():
    assert spc.capability(0, 1, -5, 5, 24)["reference_only"] is True
    assert spc.capability(0, 1, -5, 5, 25)["reference_only"] is False


# --- Western Electric ---

def test_rule1_one_point_beyond_3_sigma():
    assert spc.western_electric([0, 0, 3.0, 0], 0, 1) == []  # 剛好 3σ 不算超出
    hits = spc.western_electric([0, 0, 0, -3.5], 0, 1)
    assert [(h["rule"], h["index"], h["side"]) for h in hits] == [(1, 3, "下")]


def test_rule2_two_of_three_beyond_2_sigma_same_side():
    hits = spc.western_electric([0, 2.5, 0, 2.6], 0, 1)
    assert [(h["rule"], h["position"]) for h in hits] == [(2, 4)]
    assert spc.western_electric([2.5, -2.5, 0], 0, 1) == []  # 不同側不算
    assert spc.western_electric([2.5, 0, 0, 0, 2.6], 0, 1) == []  # 中間隔太遠（超出三點視窗）


def test_rule3_four_of_five_beyond_1_sigma_same_side():
    hits = spc.western_electric([1.5, 1.2, 0, 1.6, 1.4], 0, 1)
    assert [(h["rule"], h["position"]) for h in hits] == [(3, 5)]
    assert spc.western_electric([1.5, 1.2, 0, 1.6, 0.5], 0, 1) == []  # 只有 3 點


def test_rule4_needs_eight_consecutive_points_by_default_but_run_length_is_configurable():
    seven = [0.5] * 7
    eight = [0.5] * 8
    assert spc.western_electric(seven, 0, 1) == []  # 7 點不觸發（Western Electric 原始定義是 8）
    hits = spc.western_electric(eight, 0, 1)
    assert [(h["rule"], h["position"]) for h in hits] == [(4, 8)]
    assert [h["position"] for h in spc.western_electric(seven, 0, 1, run_length=7)] == [7]  # 想用 7 可設定
    assert spc.western_electric([0.5] * 4 + [0.0] + [0.5] * 4, 0, 1) == []  # 落在中心線上會中斷連續
    assert [h["position"] for h in spc.western_electric([0.5] * 9, 0, 1)] == [8, 9]  # 第 8、9 點都算


def test_rules_can_be_restricted_and_zero_sigma_is_safe():
    assert spc.western_electric([0, 5], 0, 1, rules=(2, 3, 4)) == []
    assert spc.western_electric([1, 2, 3], 0, 0) == []


def test_violations_are_reported_on_the_real_charts():
    # 8 個子群，第 8 個子群平均遠高於其他 → 規則 1
    data = [10, 11, 10, 11, 10] * 7 + [20, 21, 20, 21, 20]
    r = spc.xbar_r(data, 5)
    assert any(v["rule"] == 1 and v["position"] == 8 for v in r["violations"])
    # 全距圖：某子群全距特別大
    spread = [10, 11, 10, 11, 10] * 6 + [1, 30, 10, 11, 10]
    assert any(v["rule"] == 1 and v["position"] == 7 for v in spc.xbar_r(spread, 5)["range_violations"])


# --- 量測值寫入（record_result 路徑）與 API ---

def _log_length(value, target=10.5, tolerance=5.5, station="S1", part="P-1", when=None, **extra):
    item = {"長度mm": value, "寬度mm": 5.0, "孔徑mm": [2.0], "目標長度mm": target, "公差mm": tolerance, **extra}
    inspection_id = log_inspection("measure", "OK", "e", 1, [item], {"part_no": part, "station": station})
    if when:
        with connect() as conn:
            conn.execute("UPDATE measurements SET created_at = ? WHERE inspection_id = ?", (when, inspection_id))
            conn.commit()
    return inspection_id


def test_measurements_are_written_with_specs_and_holes_only_when_single(client):
    _log_length(10.0)
    log_inspection("measure", "INFO", "e", 1, [{"長度mm": 50.0, "寬度mm": 20.0, "孔徑mm": [5.0, 3.0]}], {})
    log_inspection("measure", "INFO", "e", 1, [{"計數結果": 8, "預期數量": 8, "明細": []}], {})  # 計數不是量測
    with connect() as conn:
        rows = conn.execute("SELECT * FROM measurements ORDER BY id").fetchall()
    by_char = [(r["characteristic"], r["value"], r["lsl"], r["usl"], r["target"], r["part_no"]) for r in rows]
    assert ("長度", 10.0, 5.0, 16.0, 10.5, "P-1") in by_char  # 目標 ± 公差
    assert ("寬度", 5.0, None, None, None, "P-1") in by_char  # 沒填寬度目標 → 沒規格
    assert ("孔徑", 2.0, None, None, None, "P-1") in by_char  # 單孔才收
    assert [c for c, *_ in by_char].count("孔徑") == 1  # 兩個孔那筆沒有收
    assert ("長度", 50.0, None, None, None, None) in by_char  # 舊格式（沒存公差）→ 沒規格


def test_colordiff_gauge_and_sevenseg_measurements(client):
    log_inspection("colordiff", "OK", "e", 1, [{"ΔE00": 1.25, "門檻": 3.0, "判定": "合格"}], {"part_no": "P-1"})
    log_inspection("nameplate", "INFO", "e", 1, [{"讀值": 49.42, "指針角度": 268.4}], {"part_no": "P-1"})
    log_inspection("nameplate", "OK", "e", 1, [{"讀值": "23.5", "明細": []}], {"part_no": "P-1"})
    log_inspection("nameplate", "NG", "e", 1, [{"讀值": "2?5", "明細": []}], {"part_no": "P-1"})  # 有 ? 不收
    log_inspection("nameplate", "OK", "e", 1, [{"廠牌": "中科精機", "型號": "CK-850V"}], {"part_no": "P-1"})
    with connect() as conn:
        rows = {r["characteristic"]: dict(r) for r in conn.execute("SELECT * FROM measurements").fetchall()}
    assert set(rows) == {"色差ΔE00", "指針錶讀值", "七段顯示器讀值"}
    assert rows["色差ΔE00"]["usl"] == 3.0 and rows["色差ΔE00"]["lsl"] is None  # 一邊規格
    assert rows["七段顯示器讀值"]["value"] == 23.5 and rows["指針錶讀值"]["value"] == 49.42


def test_real_measure_endpoint_stores_tolerance_and_measurements(client, admin_client, measure_scene_png_marker):
    png, marker_mm = measure_scene_png_marker
    res = client.post("/api/measure/measure", params={"marker_size_mm": marker_mm, "target_length_mm": 50, "tolerance_mm": 1.0},
                      files={"file": ("m.png", png, "image/png")}, headers={"X-Part-No": "SC-1"})
    assert res.json()["items"][0]["公差mm"] == 1.0
    chars = {c["characteristic"]: c for c in admin_client.get("/api/spc/characteristics").json()}
    assert set(chars) == {"長度", "寬度", "孔徑"} and chars["長度"]["has_spec"] and not chars["寬度"]["has_spec"]


def _seed_series(values=GROUPS, **kw):
    for v in values:
        _log_length(float(v), **kw)


def test_spc_api_matches_hand_calculation(admin_client):
    _seed_series()
    body = admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度"}).json()
    assert body["insufficient_data"] is False and body["count"] == 15 and body["type"] == "xbar_r"
    assert body["x_chart"]["ucl"] == pytest.approx(13.308) and body["range_chart"]["ucl"] == pytest.approx(8.456)
    assert body["spec"] == {"lsl": 5.0, "usl": 16.0, "target": 10.5, "changed": False}
    assert body["capability"]["cp"] == pytest.approx(1.06608, rel=1e-4)
    assert body["capability"]["cpk"] == pytest.approx(0.96917, rel=1e-4)
    assert len(body["labels"]) == body["subgroups"] == 3
    imr_body = admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度", "chart": "imr"}).json()
    assert imr_body["type"] == "imr" and len(imr_body["x_chart"]["points"]) == 15


def test_spc_api_seven_points_on_one_side_do_not_trigger_but_eight_do(admin_client):
    """規則 4 依 Western Electric 原始定義用 8 點（規劃書驗收寫 7，經使用者確認改 8；run_length 可調）。"""
    base = [11.0, 10.0] * 5  # 交錯的正常資料，最後一點在平均之下，不會併進後面那段同側連續點
    _seed_series(base)  # 先有一段正常資料
    _seed_series([10.9] * 7)
    seven = admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度", "chart": "imr"}).json()
    assert not [v for v in seven["violations"] if v["rule"] == 4]
    _seed_series([10.9])
    eight = admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度", "chart": "imr"}).json()
    assert [v["position"] for v in eight["violations"] if v["rule"] == 4] == [18]
    relaxed = admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度", "chart": "imr", "run_length": 7}).json()
    assert [v["position"] for v in relaxed["violations"] if v["rule"] == 4] == [17, 18]


def test_spc_api_filters_insufficient_data_errors_and_spec_change(admin_client):
    _seed_series(part="P-1", station="S1")
    _seed_series([10, 10], part="P-2", station="S2")
    assert admin_client.get("/api/spc", params={"part_no": "P-2", "characteristic": "長度"}).json()["insufficient_data"] is True
    nodata = admin_client.get("/api/spc", params={"part_no": "NOPE", "characteristic": "長度"}).json()
    assert nodata["insufficient_data"] and "沒有量測資料" in nodata["message"]
    only_s2 = admin_client.get("/api/spc", params={"characteristic": "長度", "station": "S2", "chart": "imr"}).json()
    assert only_s2["count"] == 2 and only_s2["insufficient_data"]
    assert admin_client.get("/api/spc", params={"part_no": "P-1", "characteristic": "長度", "from": "2999-01-01"}).json()["count"] == 0
    assert admin_client.get("/api/spc", params={"characteristic": "長度", "chart": "pie"}).status_code == 400
    assert admin_client.get("/api/spc", params={"characteristic": "長度", "subgroup_size": 1}).status_code == 422
    assert admin_client.get("/api/spc").status_code == 422  # 缺 characteristic
    # 規格中途改變（公差 5.5 → 1.0）要被回報，並採用最近的規格
    _seed_series([10, 10, 10, 10, 10], part="P-3", tolerance=5.5)
    _seed_series([10, 10, 10, 10, 10], part="P-3", tolerance=1.0)
    spec = admin_client.get("/api/spc", params={"part_no": "P-3", "characteristic": "長度"}).json()["spec"]
    assert spec["changed"] is True and (spec["lsl"], spec["usl"]) == (9.5, 11.5)


def test_no_part_measurements_are_reachable_via_placeholder(admin_client):
    for v in GROUPS:
        log_inspection("measure", "INFO", "e", 1, [{"長度mm": float(v)}], {})
    chars = admin_client.get("/api/spc/characteristics").json()
    assert chars[0]["part_no"] == "__none__" and chars[0]["part_label"] == "（未指定料號）" and chars[0]["has_spec"] is False
    body = admin_client.get("/api/spc", params={"part_no": "__none__", "characteristic": "長度"}).json()
    assert body["count"] == 15 and body["capability"]["cpk"] is None and "沒有規格" in body["capability"]["note"]


def test_spc_permissions(admin_client, qc_client, operator_client, client):
    _seed_series()
    params = {"part_no": "P-1", "characteristic": "長度"}
    assert qc_client.get("/api/spc", params=params).status_code == 200
    assert client.get("/api/spc", params=params).status_code == 200  # API key 唯讀
    assert client.get("/api/spc/characteristics").status_code == 200
    assert operator_client.get("/api/spc", params=params).status_code == 403
    from fastapi.testclient import TestClient
    assert TestClient(admin_client.app).get("/api/spc", params=params).status_code == 401

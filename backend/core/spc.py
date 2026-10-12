"""統計製程管制：X̄-R、I-MR 管制圖、Cp／Cpk、Western Electric 規則 1–4。純 numpy，沒有額外相依。

約定：
- 子群依時間順序每 n 筆一組，不足 n 筆的尾端不納入（X̄-R）。
- 管制界限用標準係數表（A2、D3、D4、d2；I-MR 用 2.660／3.267／1.128）。
- 製程能力用「組內變異」估計 σ（R̄/d2 或 MR̄/1.128）。子群（或觀測值）少於 25 組標示「僅供參考」。
- 只有一邊規格（例如色差只有上限）只算 Cpk（Cpu 或 Cpl），不給 Cp；沒有規格就不算能力指標。
"""

import numpy as np

# n: (d2, D3, D4, A2)
_CONSTANTS = {
    2: (1.128, 0.0, 3.267, 1.880),
    3: (1.693, 0.0, 2.574, 1.023),
    4: (2.059, 0.0, 2.282, 0.729),
    5: (2.326, 0.0, 2.114, 0.577),
    6: (2.534, 0.0, 2.004, 0.483),
    7: (2.704, 0.076, 1.924, 0.419),
    8: (2.847, 0.136, 1.864, 0.373),
    9: (2.970, 0.184, 1.816, 0.337),
    10: (3.078, 0.223, 1.777, 0.308),
}
_IMR_E2, _IMR_D4, _IMR_D2 = 2.660, 3.267, 1.128
MIN_SUBGROUPS_FOR_CONFIDENCE = 25
DEFAULT_RUN_LENGTH = 8  # Western Electric 規則 4 的連續點數（原始定義為 8）


def western_electric(
    points, center: float, sigma: float, run_length: int = DEFAULT_RUN_LENGTH, rules: tuple[int, ...] = (1, 2, 3, 4)
) -> list[dict]:
    """對一串點套用規則，回傳觸發清單 [{rule, index, position, value, side}]（index 為 0 起算）。
    1：一點超出 3σ；2：連續三點有兩點超出 2σ（同側）；3：連續五點有四點超出 1σ（同側）；
    4：連續 run_length 點在中心線同一側。規則 2、3 在「目前這一點本身也超出該界線」時才標記。"""
    if sigma <= 0:
        return []
    z = [(p - center) / sigma for p in points]
    hits: list[dict] = []

    def add(rule, i):
        hits.append(
            {"rule": rule, "index": i, "position": i + 1, "value": float(points[i]), "side": "上" if z[i] > 0 else "下"}
        )

    for i, zi in enumerate(z):
        if 1 in rules and abs(zi) > 3:
            add(1, i)
        for rule, window, need, limit in ((2, 3, 2, 2.0), (3, 5, 4, 1.0)):
            if rule not in rules or abs(zi) <= limit:
                continue
            side = 1 if zi > 0 else -1
            recent = z[max(0, i - window + 1) : i + 1]
            if len(recent) >= need and sum(1 for v in recent if v * side > limit) >= need:
                add(rule, i)
        if 4 in rules and i >= run_length - 1:
            recent = z[i - run_length + 1 : i + 1]
            if all(v > 0 for v in recent) or all(v < 0 for v in recent):
                add(4, i)
    hits.sort(key=lambda h: (h["index"], h["rule"]))
    return hits


def _range_violations(chart: dict) -> list[dict]:
    """R／MR 圖只套規則 1：超出管制界限（上界或下界）。"""
    return [
        {"rule": 1, "index": i, "position": i + 1, "value": float(p), "side": "上" if p > chart["ucl"] else "下"}
        for i, p in enumerate(chart["points"])
        if p > chart["ucl"] or p < chart["lcl"]
    ]


def capability(mean: float, sigma: float | None, lsl: float | None, usl: float | None, subgroups: int) -> dict:
    result = {
        "lsl": lsl,
        "usl": usl,
        "cp": None,
        "cpk": None,
        "cpu": None,
        "cpl": None,
        "reference_only": subgroups < MIN_SUBGROUPS_FOR_CONFIDENCE,
        "note": None,
    }
    if lsl is None and usl is None:
        result["note"] = "沒有規格上下限，只提供管制圖"
        return result
    if not sigma or sigma <= 0:
        result["note"] = "組內變異為 0，無法計算製程能力"
        return result
    if usl is not None:
        result["cpu"] = (usl - mean) / (3 * sigma)
    if lsl is not None:
        result["cpl"] = (mean - lsl) / (3 * sigma)
    if usl is not None and lsl is not None:
        result["cp"] = (usl - lsl) / (6 * sigma)
    result["cpk"] = min(v for v in (result["cpu"], result["cpl"]) if v is not None)
    if lsl is None or usl is None:
        result["note"] = "只有單邊規格，只提供 Cpk（不提供 Cp）"
    return result


def xbar_r(values, subgroup_size: int = 5, lsl=None, usl=None, run_length: int = DEFAULT_RUN_LENGTH) -> dict:
    if subgroup_size not in _CONSTANTS:
        raise ValueError(f"子群大小要在 2–10 之間，目前是 {subgroup_size}")
    n = subgroup_size
    d2, d3, d4, a2 = _CONSTANTS[n]
    data = np.asarray(values, dtype=float)
    k = len(data) // n
    if k < 2:
        raise ValueError(f"X̄-R 至少需要 2 個完整子群（每組 {n} 筆，共 {2 * n} 筆），目前只有 {len(data)} 筆")
    groups = data[: k * n].reshape(k, n)
    xbar, rng = groups.mean(axis=1), groups.max(axis=1) - groups.min(axis=1)
    grand, rbar = float(xbar.mean()), float(rng.mean())
    sigma_chart = a2 * rbar / 3  # X̄ 圖的 1σ（界限是 3σ）
    sigma_within = rbar / d2
    x_chart = {
        "points": xbar.tolist(),
        "center": grand,
        "ucl": grand + a2 * rbar,
        "lcl": grand - a2 * rbar,
        "sigma": sigma_chart,
    }
    r_chart = {"points": rng.tolist(), "center": rbar, "ucl": d4 * rbar, "lcl": d3 * rbar}
    violations = western_electric(x_chart["points"], grand, sigma_chart, run_length)
    range_violations = _range_violations(r_chart)
    return {
        "type": "xbar_r",
        "subgroup_size": n,
        "subgroups": int(k),
        "used_points": int(k * n),
        "ignored_tail": int(len(data) - k * n),
        "x_chart": x_chart,
        "range_chart": r_chart,
        "violations": violations,
        "range_violations": range_violations,
        "sigma_within": sigma_within,
        "mean": float(groups.mean()),
        "capability": capability(float(groups.mean()), sigma_within, lsl, usl, int(k)),
    }


def imr(values, lsl=None, usl=None, run_length: int = DEFAULT_RUN_LENGTH) -> dict:
    data = np.asarray(values, dtype=float)
    if len(data) < 3:
        raise ValueError(f"I-MR 至少需要 3 筆資料，目前只有 {len(data)} 筆")
    mr = np.abs(np.diff(data))
    mean, mrbar = float(data.mean()), float(mr.mean())
    sigma_chart = _IMR_E2 * mrbar / 3
    sigma_within = mrbar / _IMR_D2
    i_chart = {
        "points": data.tolist(),
        "center": mean,
        "ucl": mean + _IMR_E2 * mrbar,
        "lcl": mean - _IMR_E2 * mrbar,
        "sigma": sigma_chart,
    }
    mr_chart = {"points": mr.tolist(), "center": mrbar, "ucl": _IMR_D4 * mrbar, "lcl": 0.0}
    range_violations = _range_violations(mr_chart)
    return {
        "type": "imr",
        "subgroup_size": 1,
        "subgroups": int(len(data)),
        "used_points": int(len(data)),
        "ignored_tail": 0,
        "x_chart": i_chart,
        "range_chart": mr_chart,
        "violations": western_electric(i_chart["points"], mean, sigma_chart, run_length),
        "range_violations": range_violations,
        "sigma_within": sigma_within,
        "mean": mean,
        "capability": capability(mean, sigma_within, lsl, usl, int(len(data))),
    }

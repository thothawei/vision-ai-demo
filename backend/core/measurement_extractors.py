"""量測值正規化：辨識完成時，把可做統計製程管制的數值特性從結果抽出來，寫進 `measurements` 表，
不必每次從 `summary_json` 解析。抽取規則依 module 而定；不認得的 module 一律回傳空清單。

收錄的特性：
- 尺寸量測：長度、寬度（有填目標值與公差時帶規格上下限＝目標 ± 公差）；孔徑只在「恰好偵測到一個孔」時收錄
  （多個孔的順序取自輪廓階層、不穩定，逐孔做 SPC 會混在一起）。
- 色差：ΔE00，只有上限（＝該次檢驗的門檻，一邊規格）。
- 指針錶、七段顯示器讀值：沒有規格，只畫管制圖。
"""


def _measurement(characteristic, value, unit, lsl=None, usl=None, target=None) -> dict:
    return {"characteristic": characteristic, "value": float(value), "unit": unit, "lsl": lsl, "usl": usl, "target": target}


def _size(item: dict, name: str, value_key: str, target_key: str) -> dict | None:
    if value_key not in item:
        return None
    target, tolerance = item.get(target_key), item.get("公差mm")
    lsl = usl = None
    if target is not None and tolerance is not None:  # 舊紀錄沒存公差 → 沒有規格上下限
        lsl, usl = target - tolerance, target + tolerance
    return _measurement(name, item[value_key], "mm", lsl, usl, target)


def _measure(items: list) -> list[dict]:
    out = []
    for item in items:
        for measurement in (_size(item, "長度", "長度mm", "目標長度mm"), _size(item, "寬度", "寬度mm", "目標寬度mm")):
            if measurement:
                out.append(measurement)
        holes = item.get("孔徑mm")
        if isinstance(holes, list) and len(holes) == 1:
            out.append(_measurement("孔徑", holes[0], "mm"))
    return out


def _colordiff(items: list) -> list[dict]:
    return [_measurement("色差ΔE00", i["ΔE00"], "ΔE", usl=i.get("門檻")) for i in items if "ΔE00" in i]


def _nameplate(items: list) -> list[dict]:
    """nameplate module 底下有銘牌、七段顯示器、指針錶三種結果，用欄位分辨。"""
    out = []
    for item in items:
        if "指針角度" in item and isinstance(item.get("讀值"), (int, float)):
            out.append(_measurement("指針錶讀值", item["讀值"], ""))
        elif "明細" in item and isinstance(item.get("讀值"), str) and "?" not in item["讀值"]:
            try:
                out.append(_measurement("七段顯示器讀值", float(item["讀值"]), ""))
            except ValueError:
                pass
    return out


_EXTRACTORS = {"measure": _measure, "colordiff": _colordiff, "nameplate": _nameplate}


def extract_measurements(module: str, summary) -> list[dict]:
    fn = _EXTRACTORS.get(module)
    if fn is None or not isinstance(summary, list):
        return []
    try:
        return fn(summary)
    except (TypeError, AttributeError, KeyError):
        return []

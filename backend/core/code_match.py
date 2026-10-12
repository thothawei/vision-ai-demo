"""批號／料號比對：包裝（M8-1）與出貨標籤（M12）共用。

OCR 常把 O 讀成 0、I 讀成 1，所以結果分三級：
- 一致：忽略大小寫與前後空白後完全相同
- 疑似：只差在容易混淆的字元（O↔0、I↔1↔L、S↔5、B↔8、Z↔2），或相似度夠高；需人工確認（整體判定 INFO）
- 不一致：其餘（整體判定 NG）
任何一邊沒值就回 None（沒辦法比對，不是「不一致」）。
"""

from rapidfuzz import fuzz

MATCH, SUSPECT, MISMATCH = "一致", "疑似", "不一致"

# 兩個方向的混淆字元都收斂到同一個代表字元
_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})
SUSPECT_SIMILARITY = 90.0  # 相似度（0–100）；長度 10 的代碼差一個字元剛好是 90


def _clean(value: str) -> str:
    return value.strip().upper()


def compare_codes(expected: str | None, actual: str | None) -> str | None:
    if not expected or not actual:
        return None
    a, b = _clean(expected), _clean(actual)
    if not a or not b:
        return None
    if a == b:
        return MATCH
    ca, cb = a.translate(_CONFUSABLE), b.translate(_CONFUSABLE)
    if ca == cb or fuzz.ratio(ca, cb) >= SUSPECT_SIMILARITY:
        return SUSPECT
    return MISMATCH


def as_flag(level: str | None) -> bool | None:
    """舊的「xx一致」布林欄位：一致 True、不一致 False、疑似與無法比對 None（疑似不算一致也不算不一致）。"""
    return {MATCH: True, MISMATCH: False}.get(level)

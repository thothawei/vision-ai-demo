"""Phase 23：批號／料號三級比對（一致／疑似／不一致）。"""

import pytest

from core.code_match import MATCH, MISMATCH, SUSPECT, as_flag, compare_codes


@pytest.mark.parametrize("expected,actual,level", [
    ("LOT001", "LOT001", MATCH),
    (" lot001 ", "LOT001", MATCH),
    ("LOT0O1", "LOT001", SUSPECT),   # O↔0
    ("LOTI01", "LOT101", SUSPECT),   # I↔1
    ("LOTl01", "LOT101", SUSPECT),   # 小寫 l↔1
    ("A5B8Z2", "ASBBZZ", SUSPECT),   # S↔5、B↔8、Z↔2
    ("LOT2026AB1", "LOT2026AB7", SUSPECT),  # 長代碼差一個字元：相似度 90，需人工確認
    ("LOT001", "LOT002", MISMATCH),  # 短代碼差一個數字不能放過
    ("LOT001", "XYZ-999", MISMATCH),
    ("LOT001", None, None),
    (None, "LOT001", None),
    ("", "LOT001", None),
])
def test_compare_codes(expected, actual, level):
    assert compare_codes(expected, actual) == level


def test_as_flag_keeps_suspect_neither_true_nor_false():
    assert (as_flag(MATCH), as_flag(MISMATCH), as_flag(SUSPECT), as_flag(None)) == (True, False, None, None)

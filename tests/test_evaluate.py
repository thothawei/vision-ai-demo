"""Phase 23：評估腳本——沒有真實照片就是「待補真實照片」，有的話用標註判定。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate  # noqa: E402


def test_module_without_photos_is_pending_not_faked(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "SAMPLES_DIR", tmp_path)
    assert evaluate.evaluate_module("gauge")["status"] == "pending"
    (tmp_path / "gauge").mkdir()
    (tmp_path / "gauge" / "labels.json").write_text(json.dumps({"samples": [{"file": "x.jpg", "expected": {}}]}))
    assert evaluate.evaluate_module("gauge")["status"] == "pending"  # 標註有、照片檔沒有


def test_numeric_tolerance_and_exact_match():
    assert evaluate._matches(3.3, 3.2, 0.2) == (True, abs(3.3 - 3.2))
    assert evaluate._matches(3.6, 3.2, 0.2)[0] is False
    assert evaluate._matches("235", "235", 0)[0] is True
    assert evaluate._matches("23?", "235", 0)[0] is False


def test_render_lists_every_module_with_a_status():
    text = evaluate.render({m: {"status": "pending", "reason": "沒有 labels.json"} for m in evaluate.MODULES})
    for m in evaluate.MODULES:
        assert f"| {m} | 待補真實照片" in text

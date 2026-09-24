"""Phase 12：scripts/export_reviewed.py 的匯出邏輯（直接建構 DB 紀錄，不透過真的辨識 API，
專注測「已複判紀錄 → YOLO/MVTec 資料夾格式」這段轉換邏輯本身）。"""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_reviewed  # noqa: E402


@pytest.fixture
def export_env(tmp_path, monkeypatch):
    monkeypatch.setenv("INSPECTION_DB", str(tmp_path / "inspections.db"))
    monkeypatch.setattr(export_reviewed, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def _make_test_image(path: Path, size=(100, 100)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 50, 50)).save(path)


def _insert_record(module, verdict, summary, image_rel_path, review_verdict=None):
    from core.inspection_log import _connect, log_inspection, update_review

    rec_id = log_inspection(module, verdict, "test-engine", 10, summary)
    # log_inspection() 沒有 image_path 參數（production 靠 record_result 的存圖流程補上），
    # 測試直接補寫，專注測匯出邏輯本身。
    with _connect() as conn:
        conn.execute("UPDATE inspections SET image_path = ? WHERE id = ?", (image_rel_path, rec_id))
        conn.commit()
    if review_verdict:
        update_review(rec_id, review_verdict, "測試員", None)
    return rec_id


def test_export_yolo_ppe_converts_boxes_and_classes(export_env):
    img_rel = "images/1_raw.png"
    _make_test_image(export_env / "data" / img_rel)
    summary = [{
        "偵測到人頭數": 2, "未戴安全帽數": 1,
        "明細": [
            {"類型": "已戴安全帽", "信心度": 0.9, "邊界框": [10, 10, 50, 50]},
            {"類型": "未戴安全帽", "信心度": 0.8, "邊界框": [60, 10, 90, 50]},
        ],
    }]
    rec_id = _insert_record("ppe", "NG", summary, img_rel, review_verdict="NG")

    out_dir = export_env / "export_ppe"
    manifest = export_reviewed.export_yolo("ppe", export_reviewed.PPE_CLASS_MAP, export_reviewed.PPE_CLASS_NAMES, out_dir)

    assert manifest["exported"] == 1
    assert manifest["skipped_no_image"] == 0
    lines = (out_dir / "labels" / f"{rec_id}.txt").read_text().strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("0 ")  # helmet class id
    assert lines[1].startswith("1 ")  # head class id
    # YOLO 格式：class cx cy w h，全部是 0~1 的正規化座標
    for line in lines:
        for value in line.split()[1:]:
            assert 0.0 <= float(value) <= 1.0
    assert (out_dir / "data.yaml").read_text().count("helmet") == 1
    assert (out_dir / "images" / f"{rec_id}.png").exists()


def test_export_yolo_only_includes_reviewed_records(export_env):
    img_rel = "images/2_raw.png"
    _make_test_image(export_env / "data" / img_rel)
    _insert_record("ppe", "OK", [{"明細": []}], img_rel, review_verdict=None)  # 沒複判，不該被匯出

    out_dir = export_env / "export_ppe2"
    manifest = export_reviewed.export_yolo("ppe", export_reviewed.PPE_CLASS_MAP, export_reviewed.PPE_CLASS_NAMES, out_dir)
    assert manifest["exported"] == 0


def test_export_yolo_skips_missing_image_file(export_env):
    _insert_record("defect", "NG", [{"明細": []}], "images/missing.png", review_verdict="NG")
    out_dir = export_env / "export_defect"
    manifest = export_reviewed.export_yolo("defect", export_reviewed.DEFECT_CLASS_MAP, export_reviewed.DEFECT_CLASS_NAMES, out_dir)
    assert manifest["exported"] == 0
    assert manifest["skipped_no_image"] == 1


def test_export_anomaly_mvtec_splits_by_review_verdict(export_env):
    img1, img2 = "images/g1.png", "images/d1.png"
    _make_test_image(export_env / "data" / img1)
    _make_test_image(export_env / "data" / img2)
    _insert_record("anomaly", "NG", [{"類別": "screw", "判定": "異常"}], img2, review_verdict="NG")
    _insert_record("anomaly", "NG", [{"類別": "screw", "判定": "異常"}], img1, review_verdict="OK")  # AI 誤判，複判成良品

    out_dir = export_env / "export_anomaly"
    manifest = export_reviewed.export_anomaly_mvtec("screw", out_dir)

    assert manifest["good"] == 1
    assert manifest["defect"] == 1
    assert len(list((out_dir / "good").glob("*.png"))) == 1
    assert len(list((out_dir / "defect").glob("*.png"))) == 1


def test_export_anomaly_mvtec_filters_by_category(export_env):
    img = "images/x.png"
    _make_test_image(export_env / "data" / img)
    _insert_record("anomaly", "OK", [{"類別": "tile", "判定": "正常"}], img, review_verdict="OK")

    out_dir = export_env / "export_screw_only"
    manifest = export_reviewed.export_anomaly_mvtec("screw", out_dir)  # 篩 screw，但這筆是 tile
    assert manifest["good"] == 0
    assert manifest["defect"] == 0

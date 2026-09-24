"""Phase 11：scripts/watch_folder.py 的核心邏輯（不啟動真的 watchdog 監看迴圈，
直接測 process_one/scan_existing，用 TestClient 當 httpx.Client 相容物件）。"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import watch_folder  # noqa: E402


def _args(**overrides):
    base = dict(
        action="general", in_dir=None, base_url="http://testserver",
        station=None, work_order=None, part_no=None, lot_no=None, operator=None,
        mode=None, category=None, zone=None, expected_count=None, marker_size_mm=None,
        target_length_mm=None, target_width_mm=None, tolerance_mm=None,
        min_value=None, max_value=None, min_angle=None, max_angle=None,
        poll_interval=0.02, stable_checks=2, once=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_watch_folder_moves_good_files_to_done_and_logs_inspections(client, fake_llm, warning_sign_png, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for i in range(10):
        (inbox / f"photo_{i}.png").write_bytes(warning_sign_png)

    args = _args(in_dir=str(inbox), station="AOI-01", work_order="WO-2026-0001")
    done_dir = inbox / "done"
    error_dir = inbox / "error"
    watch_folder.scan_existing(client, args, inbox, done_dir, error_dir)

    done_files = sorted(p.name for p in done_dir.glob("*.png"))
    assert len(done_files) == 10
    assert list(inbox.glob("*.png")) == []  # 原始檔案都搬走了
    assert len(list(done_dir.glob("*.log"))) == 10

    logs = client.get("/api/inspections", params={"module": "general", "work_order": "WO-2026-0001"}).json()
    assert len(logs) == 10
    assert all(r["station"] == "AOI-01" for r in logs)


def test_watch_folder_moves_bad_file_to_error(client, fake_llm, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "bad.png").write_bytes(b"not a real image")

    args = _args(in_dir=str(inbox))
    done_dir = inbox / "done"
    error_dir = inbox / "error"
    watch_folder.scan_existing(client, args, inbox, done_dir, error_dir)

    assert [p.name for p in error_dir.glob("*.png")] == ["bad.png"]
    log_text = (error_dir / "bad.log").read_text(encoding="utf-8")
    assert "無法讀取圖片" in log_text or "400" in log_text


def test_watch_folder_ignores_unsupported_extensions(client, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "readme.txt").write_text("hello")

    args = _args(in_dir=str(inbox))
    watch_folder.scan_existing(client, args, inbox, inbox / "done", inbox / "error")

    assert (inbox / "readme.txt").exists()  # 沒被搬走，因為副檔名不在支援清單


def test_watch_folder_waits_for_stable_file_size(tmp_path):
    f = tmp_path / "writing.png"
    f.write_bytes(b"x" * 10)
    assert watch_folder.wait_until_stable(f, poll_interval=0.02, stable_checks=2, timeout=1)

    missing = tmp_path / "missing.png"
    assert watch_folder.wait_until_stable(missing, poll_interval=0.02, stable_checks=2, timeout=0.1) is False

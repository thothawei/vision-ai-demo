"""Phase 21：資料保存（清理圖片）、備份還原、模型說明卡。"""

import json
import sqlite3
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import backup as backup_script  # noqa: E402
import cleanup_images  # noqa: E402
import gen_model_cards  # noqa: E402
import restore as restore_script  # noqa: E402
from core import model_registry  # noqa: E402
from core.inspection_log import connect, get_stats  # noqa: E402


def _make_record(client, png, days_old=0, **headers):
    """辦識一次（會存圖），再把紀錄時間挪到 days_old 天前。"""
    res = client.post("/api/general/describe", files={"file": ("s.png", png, "image/png")}, headers=headers)
    inspection_id = res.json()["inspection_id"]
    old = (datetime.now() - timedelta(days=days_old)).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute("UPDATE inspections SET created_at = ? WHERE id = ?", (old, inspection_id))
        conn.commit()
    return inspection_id


@pytest.fixture
def images_env(client, monkeypatch, fake_llm):
    monkeypatch.setenv("SAVE_IMAGES", "true")
    return client


# --- 清理圖片 ---


def test_cleanup_defaults_to_preview_and_deletes_nothing(images_env, admin_client, warning_sign_png):
    old = _make_record(images_env, warning_sign_png, days_old=200)
    from core.inspection_log import get_image_file_path

    path = get_image_file_path(old, "raw")
    assert path and path.exists()
    preview = cleanup_images.cleanup(180)
    assert (preview["apply"], preview["inspections"], preview["files"]) == (
        False,
        1,
        1,
    )  # 現場照片辨識只有原圖，沒有標註圖
    assert path.exists() and admin_client.get(f"/api/inspections/{old}").json()["image_path"] != "expired"


def test_cleanup_apply_removes_old_files_keeps_records_and_marks_expired(images_env, admin_client, warning_sign_png):
    from core.inspection_log import get_image_file_path

    old = _make_record(images_env, warning_sign_png, days_old=200)
    recent = _make_record(images_env, warning_sign_png, days_old=10)
    old_raw, recent_raw = get_image_file_path(old, "raw"), get_image_file_path(recent, "raw")
    result = cleanup_images.cleanup(180, apply=True)
    assert result["inspections"] == 1 and result["files"] == 1 and result["bytes"] > 0
    assert not old_raw.exists() and recent_raw.exists()  # 期限內的不動
    record = admin_client.get(f"/api/inspections/{old}").json()
    assert record["id"] == old and record["summary"]  # 紀錄本身保留
    assert record["image_path"] == "expired" and record["annotated_path"] is None  # 本來就沒有的圖，不會被標成過期
    gone = admin_client.get(f"/api/inspections/{old}/image", params={"kind": "raw"})
    assert gone.status_code == 410 and "保存期限" in gone.json()["detail"]
    assert admin_client.get(f"/api/inspections/{recent}/image", params={"kind": "raw"}).status_code == 200
    assert cleanup_images.cleanup(180, apply=True)["inspections"] == 0  # 再跑一次沒有東西可清
    assert old_raw.parent.exists()  # 同一天資料夾裡還有期限內的圖，所以資料夾還在


def test_cleanup_removes_day_folders_that_become_empty(images_env, warning_sign_png):
    from core.inspection_log import get_image_file_path

    old = _make_record(images_env, warning_sign_png, days_old=200)
    folder = get_image_file_path(old, "raw").parent
    cleanup_images.cleanup(180, apply=True)
    assert not folder.exists()


def test_cleanup_keeps_reviewed_images_unless_told_otherwise(images_env, admin_client, qc_client, warning_sign_png):
    from core.inspection_log import get_image_file_path

    reviewed = _make_record(images_env, warning_sign_png, days_old=300)
    plain = _make_record(images_env, warning_sign_png, days_old=300)
    qc_client.patch(f"/api/inspections/{reviewed}/review", json={"review_verdict": "OK"})
    reviewed_raw = get_image_file_path(reviewed, "raw")
    summary = cleanup_images.cleanup(180, apply=True)
    assert summary["inspections"] == 1 and summary["skipped_reviewed"] == 1
    assert reviewed_raw.exists() and admin_client.get(f"/api/inspections/{reviewed}").json()["image_path"] != "expired"
    assert admin_client.get(f"/api/inspections/{plain}").json()["image_path"] == "expired"
    forced = cleanup_images.cleanup(180, apply=True, include_reviewed=True)
    assert forced["inspections"] == 1 and not reviewed_raw.exists()


def test_cleanup_covers_extra_roles_and_ignores_paths_outside_the_images_dir(
    images_env, admin_client, tmp_path, warning_sign_png
):
    from core.inspection_log import get_image_file_path

    outside = tmp_path / "precious.txt"
    outside.write_text("do not delete")
    old = _make_record(images_env, warning_sign_png, days_old=400)
    golden = get_image_file_path(old, "raw").with_name(f"{old}_golden.png")
    golden.write_bytes(b"golden")
    with connect() as conn:  # 一筆有輔助圖，另一筆的路徑被改成指向 images 目錄之外
        conn.execute(
            "UPDATE inspections SET images_json = ? WHERE id = ?",
            (json.dumps({"golden": f"images/{golden.parent.name}/{golden.name}"}), old),
        )
        conn.execute(
            "INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json, image_path)"
            " VALUES ('2020-01-01T00:00:00', 'general', 'INFO', 'e', 1, '[]', '../precious.txt')"
        )
        conn.commit()
    cleanup_images.cleanup(180, apply=True)
    assert not golden.exists() and outside.read_text() == "do not delete"
    assert admin_client.get(f"/api/inspections/{old}").json()["images"] == {"golden": "expired"}
    assert admin_client.get(f"/api/inspections/{old}/image", params={"kind": "golden"}).status_code == 410


def test_retention_days_setting_default_is_180(monkeypatch):
    from core.settings import get_settings

    monkeypatch.delenv("IMAGE_RETENTION_DAYS", raising=False)
    assert get_settings().image_retention_days == 180
    monkeypatch.setenv("IMAGE_RETENTION_DAYS", "30")
    assert get_settings().image_retention_days == 30


# --- 備份與還原 ---


def _snapshot_state():
    stats = get_stats("module")
    with connect() as conn:
        users = conn.execute("SELECT username, password_hash, role FROM users ORDER BY id").fetchall()
        parts = conn.execute("SELECT part_no FROM parts").fetchall()
    return {"stats": stats, "users": [tuple(u) for u in users], "parts": [tuple(p) for p in parts]}


def test_backup_delete_everything_restore_gives_identical_dashboard_numbers(
    images_env, admin_client, qc_client, tmp_path, warning_sign_png, monkeypatch
):
    from core import anomaly_training
    from core.inspection_log import _db_path, _images_dir, get_image_file_path
    from modules.assembly.service import _golden_dir

    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", tmp_path / "anomaly" / "categories.json")
    monkeypatch.setattr(anomaly_training, "MODELS_DIR", tmp_path / "anomaly")
    anomaly_training._update_entry("cat", status="done")
    admin_client.post("/api/master/parts", json={"part_no": "P-1"})
    ids = [_make_record(images_env, warning_sign_png, days_old=d) for d in (0, 1, 2)]
    qc_client.patch(f"/api/inspections/{ids[0]}/review", json={"review_verdict": "NG", "review_note": "改判"})
    _golden_dir().mkdir(parents=True, exist_ok=True)
    (_golden_dir() / "sample.txt").write_text("golden")
    before = _snapshot_state()
    raw_bytes = get_image_file_path(ids[1], "raw").read_bytes()

    archive = backup_script.backup(tmp_path / "backups")
    assert oct(archive.stat().st_mode & 0o777) == "0o600"  # 備份含密碼雜湊，只有擁有者可讀
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        manifest = json.load(tar.extractfile("manifest.json"))
    assert "db/inspections.db" in names and "anomaly/categories.json" in names and "golden_samples/sample.txt" in names
    assert not any(n.endswith(".env") or ".env" == Path(n).name for n in names)  # 祕密不進備份
    assert manifest["counts"]["inspections"] == 3 and manifest["counts"]["users"] == 2
    assert manifest["schema_version"] >= 2 and manifest["includes_models"] is False

    for target in (_db_path(),):
        target.unlink()  # 模擬資料全部遺失
    import shutil

    shutil.rmtree(_images_dir())
    shutil.rmtree(_golden_dir())
    (tmp_path / "anomaly" / "categories.json").unlink()

    preview = restore_script.restore(archive, apply=False, models_dir=tmp_path / "models")
    assert preview["apply"] is False and not _db_path().exists()  # 預設只預覽，什麼都沒動
    done = restore_script.restore(archive, apply=True, models_dir=tmp_path / "models")
    assert done["restored_counts"] == {"inspections": 3, "users": 2}

    after = _snapshot_state()
    assert after == before  # 看板數字、使用者（含密碼雜湊）、主檔都一致
    assert get_image_file_path(ids[1], "raw").read_bytes() == raw_bytes
    assert (_golden_dir() / "sample.txt").read_text() == "golden"
    assert json.loads((tmp_path / "anomaly" / "categories.json").read_text())["cat"]["status"] == "done"
    assert (
        admin_client.post("/api/auth/login", json={"username": "admin_test", "password": "password-1234"}).status_code
        == 200
    )


def test_restore_keeps_existing_data_aside_instead_of_deleting(images_env, tmp_path, warning_sign_png, monkeypatch):
    from core import anomaly_training

    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", tmp_path / "anomaly" / "categories.json")
    _make_record(images_env, warning_sign_png)
    archive = backup_script.backup(tmp_path / "backups")
    _make_record(images_env, warning_sign_png)  # 備份之後又多了一筆
    done = restore_script.restore(archive, apply=True, models_dir=tmp_path / "models")
    assert done["restored_counts"]["inspections"] == 1
    aside = [Path(p) for p in done["moved_aside"]]
    assert any(p.name.startswith("inspections.db.before-restore-") for p in aside)
    kept = sqlite3.connect(next(p for p in aside if p.name.startswith("inspections.db.before-restore-")))
    assert kept.execute("SELECT COUNT(*) FROM inspections").fetchone()[0] == 2  # 還原前的資料還在


def test_restore_refuses_corrupted_archives_and_newer_schema(images_env, tmp_path, warning_sign_png, monkeypatch):
    from core import anomaly_training

    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", tmp_path / "anomaly" / "categories.json")
    _make_record(images_env, warning_sign_png)
    archive = backup_script.backup(tmp_path / "backups")

    def rewrite(path, mutate):
        stage = tmp_path / f"stage-{path.stem}"
        with tarfile.open(archive) as tar:
            tar.extractall(stage, filter="data")
        mutate(stage)
        out = tmp_path / path
        with tarfile.open(out, "w:gz") as tar:
            for p in sorted(stage.rglob("*")):
                if p.is_file():
                    tar.add(p, arcname=p.relative_to(stage).as_posix())
        return out

    def corrupt(stage):
        with open(stage / "db" / "inspections.db", "ab") as f:
            f.write(b"junk")

    with pytest.raises(restore_script.RestoreError, match="SHA-256 與 manifest 不符"):
        restore_script.restore(rewrite(Path("corrupt.tar.gz"), corrupt), apply=True, models_dir=tmp_path / "m")

    def newer(stage):
        manifest = json.loads((stage / "manifest.json").read_text())
        manifest["schema_version"] = 999
        (stage / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(restore_script.RestoreError, match="比這個程式支援的"):
        restore_script.restore(rewrite(Path("newer.tar.gz"), newer), apply=True, models_dir=tmp_path / "m")

    def extra(stage):
        (stage / "images" / "sneaky.txt").write_text("not in manifest")

    with pytest.raises(restore_script.RestoreError, match="manifest 沒列"):
        restore_script.restore(rewrite(Path("extra.tar.gz"), extra), apply=True, models_dir=tmp_path / "m")

    with pytest.raises(restore_script.RestoreError, match="沒有 manifest"):
        restore_script.restore(
            rewrite(Path("empty.tar.gz"), lambda stage: (stage / "manifest.json").unlink()),
            apply=True,
            models_dir=tmp_path / "m",
        )
    assert _snapshot_state()["stats"]["total"] == 1  # 拒絕還原時原本的資料完全沒動


def test_backup_uses_a_consistent_snapshot_and_models_only_with_flag(
    images_env, tmp_path, warning_sign_png, monkeypatch
):
    from core import anomaly_training

    monkeypatch.setattr(anomaly_training, "REGISTRY_PATH", tmp_path / "anomaly" / "categories.json")
    models = tmp_path / "models"
    (models / "registry").mkdir(parents=True)
    (models / "registry" / "w.pt").write_bytes(b"weights")
    _make_record(images_env, warning_sign_png)
    plain = backup_script.backup(tmp_path / "b1", models_dir=models, now=datetime(2026, 10, 1, 2, 0, 0))
    full = backup_script.backup(
        tmp_path / "b2", include_models=True, models_dir=models, now=datetime(2026, 10, 1, 2, 0, 1)
    )
    assert plain.name == "vision-backup-20261001-020000.tar.gz"
    assert not any(n.startswith("models/") for n in tarfile.open(plain).getnames())
    assert "models/registry/w.pt" in tarfile.open(full).getnames()
    snapshot_dir = tmp_path / "snap"
    tarfile.open(plain).extract("db/inspections.db", snapshot_dir, filter="data")
    check = sqlite3.connect(snapshot_dir / "db" / "inspections.db")
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


# --- 模型說明卡 ---


def test_model_cards_are_generated_from_registry_and_check_detects_staleness(client, tmp_path, monkeypatch):
    monkeypatch.setattr(model_registry, "ROOT", tmp_path)
    weights = tmp_path / "models" / "medical" / "model.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"w")
    (weights.parent / "metrics.json").write_text(json.dumps({"test_acc": 0.8862, "weights_path": "/本機路徑/不該出現"}))
    model_registry.resolve("pneumonia-cnn", weights, "missing")
    model_registry.register_version("anomaly-screw", weights, {"image_auroc": 0.9645}, "MVTec 擬合", activate=True)

    out = tmp_path / "cards"
    paths = gen_model_cards.generate(out)
    assert {p.name for p in paths} == {"README.md", "pneumonia-cnn.md", "anomaly-screw.md"}
    pneumonia = (out / "pneumonia-cnn.md").read_text(encoding="utf-8")
    assert "僅供技術展示，非醫療診斷用途" in pneumonia and "test_acc | 0.8862" in pneumonia
    assert "CC BY 4.0" in pneumonia and "不該出現" not in pneumonia  # 本機路徑不進說明卡
    screw = (out / "anomaly-screw.md").read_text(encoding="utf-8")
    assert "CC BY-NC-SA 4.0" in screw and "不得用於商業產線" in screw and "image_auroc | 0.9645" in screw
    for section in ("## 用途", "## 資料集與授權", "## 指標", "## 版本歷史", "## 已知限制", "## 不適用情境"):
        assert section in screw
    assert gen_model_cards.generate(out, check=True) == []
    model_registry.register_version("anomaly-screw", weights, {"image_auroc": 0.97}, "重擬合", activate=True)
    assert sorted(p.name for p in gen_model_cards.generate(out, check=True)) == [
        "README.md",
        "anomaly-screw.md",
    ]  # 沒動的卡不算過期


def test_no_metrics_are_invented_for_models_without_a_source(client, tmp_path, monkeypatch):
    monkeypatch.setattr(model_registry, "ROOT", tmp_path)
    weights = tmp_path / "custom.pt"
    weights.write_bytes(b"w")
    model_registry.register_version("anomaly-my_part", weights, {}, activate=True)
    card = gen_model_cards.render_card(model_registry.list_models()[0])
    assert "尚無機器可讀的指標紀錄" in card and "自有資料" in card

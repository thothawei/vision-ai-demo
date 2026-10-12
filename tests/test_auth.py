"""Phase 18：登入、角色權限邊界、鎖定、稽核、CSRF、啟動檢查。"""

import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def _png_file(png):
    return {"file": ("s.png", png, "image/png")}


@pytest.fixture
def bare(client):
    from main import app

    return TestClient(app)  # 沒有 API key、沒有 session


# --- 未登入 ---


def test_anonymous_requests_are_rejected(bare, warning_sign_png):
    assert bare.post("/api/general/describe", files=_png_file(warning_sign_png)).status_code == 401
    assert (
        bare.post("/api/batch/general", files=[("files", ("a.png", warning_sign_png, "image/png"))]).status_code == 401
    )
    for path in (
        "/api/modules",
        "/api/inspections",
        "/api/inspections/stats",
        "/api/users",
        "/api/audit",
        "/api/anomaly/categories",
        "/api/assembly/golden-samples",
        "/api/auth/me",
    ):
        assert bare.get(path).status_code == 401, path


def test_pages_redirect_to_login_but_login_page_and_assets_are_public(bare):
    for path in ("/", "/index.html", "/docs"):
        res = bare.get(path, follow_redirects=False)
        assert res.status_code == 302 and res.headers["location"] == "/login.html", path
    assert bare.get("/openapi.json").status_code == 401
    assert bare.get("/login.html").status_code == 200
    assert bare.get("/js/main.js").status_code == 200


def test_logged_in_user_can_open_main_page(admin_client):
    assert admin_client.get("/", follow_redirects=False).status_code == 200


# --- 登入／登出 ---


def test_login_logout_and_me(client, make_session_client):
    session = make_session_client("qc", "alice", "愛麗絲")
    me = session.get("/api/auth/me").json()
    assert me == {"kind": "user", "username": "alice", "display_name": "愛麗絲", "role": "qc"}
    assert session.post("/api/auth/logout").status_code == 200
    assert session.get("/api/auth/me").status_code == 401


def test_session_cookie_is_httponly_and_samesite(client, make_session_client):
    from core import users
    from main import app

    users.create_user("cookieuser", "C", TEST_PASSWORD, "operator")
    res = TestClient(app).post("/api/auth/login", json={"username": "cookieuser", "password": TEST_PASSWORD})
    cookie = res.headers["set-cookie"].lower()
    assert "vision_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_failed_login_message_does_not_reveal_whether_account_exists(client, bare):
    from core import users

    users.create_user("realuser", "R", TEST_PASSWORD, "operator")
    wrong_pw = bare.post("/api/auth/login", json={"username": "realuser", "password": "wrong-password-x"})
    no_user = bare.post("/api/auth/login", json={"username": "ghost", "password": "wrong-password-x"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_password_is_stored_as_argon2id_hash(client):
    from core import users
    from core.inspection_log import connect

    users.create_user("hashcheck", "H", TEST_PASSWORD, "operator")
    with connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE username = 'hashcheck'").fetchone()[0]
    assert stored.startswith("$argon2id$") and TEST_PASSWORD not in stored


def test_lockout_after_repeated_failures_even_correct_password_is_refused(client, bare, monkeypatch):
    from core import users
    from core.inspection_log import connect

    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    users.create_user("locky", "L", TEST_PASSWORD, "operator")
    for _ in range(3):
        assert (
            bare.post("/api/auth/login", json={"username": "locky", "password": "wrong-password-x"}).status_code == 401
        )
    assert bare.post("/api/auth/login", json={"username": "locky", "password": TEST_PASSWORD}).status_code == 401

    # 鎖定時間過了就能登入（把 locked_until 拉回過去，等同時間流逝）
    with connect() as conn:
        conn.execute("UPDATE users SET locked_until = '2000-01-01T00:00:00' WHERE username = 'locky'")
        conn.commit()
    assert bare.post("/api/auth/login", json={"username": "locky", "password": TEST_PASSWORD}).status_code == 200


def test_successful_login_resets_failure_counter(client, bare, monkeypatch):
    from core import users

    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    users.create_user("resetty", "R", TEST_PASSWORD, "operator")
    for _ in range(2):
        bare.post("/api/auth/login", json={"username": "resetty", "password": "wrong-password-x"})
    assert bare.post("/api/auth/login", json={"username": "resetty", "password": TEST_PASSWORD}).status_code == 200
    for _ in range(2):  # 計數已歸零，再失敗 2 次仍不會鎖
        bare.post("/api/auth/login", json={"username": "resetty", "password": "wrong-password-x"})
    assert bare.post("/api/auth/login", json={"username": "resetty", "password": TEST_PASSWORD}).status_code == 200


# --- 角色權限邊界 ---


def _make_record(session, png):
    res = session.post("/api/codes/decode", files=_png_file(png))
    assert res.status_code in (200, 422), res.text
    return res


def test_operator_can_inspect_but_not_review_stats_export_or_admin_actions(
    operator_client, client, fake_llm, warning_sign_png
):
    res = operator_client.post("/api/general/describe", files=_png_file(warning_sign_png))
    assert res.status_code == 200
    inspection_id = res.json()["inspection_id"]

    assert (
        operator_client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "OK"}).status_code
        == 403
    )
    for path in (
        "/api/inspections/stats",
        "/api/inspections/export.csv",
        f"/api/inspections/{inspection_id}",
        f"/api/inspections/{inspection_id}/image",
        "/api/inspections/reviews?since=2000-01-01T00:00:00",
        "/api/users",
        "/api/audit",
    ):
        assert operator_client.get(path).status_code == 403, path
    assert operator_client.patch("/api/anomaly/categories/screw/threshold", json={"threshold": 1}).status_code == 403
    assert operator_client.post("/api/assembly/golden-samples", params={"part_no": "p"}).status_code in (403, 422)
    assert operator_client.get("/api/inspections").status_code == 200  # 自己的紀錄


def test_qc_can_review_and_see_stats_but_not_admin_actions(qc_client, client, fake_llm, warning_sign_png):
    inspection_id = client.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    assert qc_client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "OK"}).status_code == 200
    assert qc_client.get("/api/inspections/stats").status_code == 200
    assert qc_client.get("/api/inspections/export.csv").status_code == 200
    assert qc_client.get(f"/api/inspections/{inspection_id}/image").status_code in (200, 404)
    for path in ("/api/users", "/api/audit"):
        assert qc_client.get(path).status_code == 403, path
    assert qc_client.patch("/api/anomaly/categories/screw/threshold", json={"threshold": 1}).status_code == 403
    assert qc_client.post("/api/anomaly/categories", params={"name": "x"}).status_code in (403, 422)


def test_api_key_is_read_only_and_cannot_review_or_administer(client, fake_llm, warning_sign_png):
    inspection_id = client.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    assert client.get("/api/inspections").status_code == 200
    assert client.get("/api/inspections/stats").status_code == 200
    assert client.get("/api/inspections/reviews", params={"since": "2000-01-01T00:00:00"}).status_code == 200
    assert client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "OK"}).status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/audit").status_code == 403
    assert client.patch("/api/anomaly/categories/screw/threshold", json={"threshold": 1}).status_code == 403


def test_operator_only_sees_own_records_others_see_all(client, make_session_client, fake_llm, warning_sign_png):
    alice = make_session_client("operator", "alice", "愛麗絲")
    bob = make_session_client("operator", "bob", "鮑伯")
    admin = make_session_client("admin", "boss", "老闆")
    a_id = alice.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    b_id = bob.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]

    assert [r["id"] for r in alice.get("/api/inspections").json()] == [a_id]
    assert [r["id"] for r in bob.get("/api/inspections").json()] == [b_id]
    assert {r["id"] for r in admin.get("/api/inspections").json()} == {a_id, b_id}
    assert {r["id"] for r in client.get("/api/inspections").json()} == {a_id, b_id}
    assert admin.get(f"/api/inspections/{a_id}").json()["created_by"] == "user:alice"


def test_api_key_records_are_attributed_to_the_key_name(client, fake_llm, warning_sign_png):
    inspection_id = client.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    assert client.get(f"/api/inspections/{inspection_id}").json()["created_by"] == "api-key:erp"


# --- 使用者管理 ---


def test_user_management_flow_and_immediate_effect(admin_client, make_session_client):
    created = admin_client.post(
        "/api/users", json={"username": "carol", "display_name": "卡蘿", "password": TEST_PASSWORD, "role": "operator"}
    )
    assert created.status_code == 201
    assert "password" not in json.dumps(created.json()) and "password_hash" not in created.json()
    carol_id = created.json()["id"]

    from main import app

    carol = TestClient(app)
    assert carol.post("/api/auth/login", json={"username": "carol", "password": TEST_PASSWORD}).status_code == 200
    assert carol.get("/api/inspections/stats").status_code == 403

    # 升成 qc：不用重新登入，下一個請求就生效
    admin_client.patch(f"/api/users/{carol_id}", json={"role": "qc"})
    assert carol.get("/api/inspections/stats").status_code == 200

    # 停用：既有 session 立即失效
    admin_client.patch(f"/api/users/{carol_id}", json={"is_active": False})
    assert carol.get("/api/auth/me").status_code == 401
    assert (
        TestClient(app).post("/api/auth/login", json={"username": "carol", "password": TEST_PASSWORD}).status_code
        == 401
    )


def test_cannot_disable_or_demote_the_last_active_admin(admin_client):
    admin_id = admin_client.get("/api/users").json()[0]["id"]
    assert admin_client.patch(f"/api/users/{admin_id}", json={"is_active": False}).status_code == 422
    assert admin_client.patch(f"/api/users/{admin_id}", json={"role": "qc"}).status_code == 422
    assert admin_client.get("/api/auth/me").status_code == 200


def test_duplicate_username_weak_password_and_bad_role_are_rejected(admin_client):
    base = {"username": "dave", "display_name": "D", "password": TEST_PASSWORD, "role": "operator"}
    assert admin_client.post("/api/users", json=base).status_code == 201
    assert admin_client.post("/api/users", json={**base, "username": "DAVE"}).status_code == 422  # 帳號不分大小寫
    assert admin_client.post("/api/users", json={**base, "username": "erin", "password": "short"}).status_code == 422
    assert admin_client.post("/api/users", json={**base, "username": "erin", "role": "root"}).status_code == 422
    assert admin_client.post("/api/users", json={**base, "username": "a b"}).status_code == 422


def test_change_own_password_and_admin_reset(admin_client, make_session_client):
    from main import app

    user = make_session_client("operator", "frank", "法蘭克")
    assert (
        user.post(
            "/api/auth/password", json={"current_password": "wrong-one-xxx", "new_password": "new-password-99"}
        ).status_code
        == 400
    )
    assert (
        user.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "short"}).status_code
        == 422
    )
    assert (
        user.post(
            "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "new-password-99"}
        ).status_code
        == 200
    )
    assert (
        TestClient(app).post("/api/auth/login", json={"username": "frank", "password": TEST_PASSWORD}).status_code
        == 401
    )
    assert (
        TestClient(app).post("/api/auth/login", json={"username": "frank", "password": "new-password-99"}).status_code
        == 200
    )

    frank_id = next(u["id"] for u in admin_client.get("/api/users").json() if u["username"] == "frank")
    assert (
        admin_client.post(f"/api/users/{frank_id}/password", json={"new_password": "reset-password-77"}).status_code
        == 200
    )
    assert (
        TestClient(app).post("/api/auth/login", json={"username": "frank", "password": "reset-password-77"}).status_code
        == 200
    )


# --- 稽核 ---


def _audit(admin, **params):
    return admin.get("/api/audit", params=params).json()


def test_review_audit_records_before_after_and_login_reviewer(
    client, qc_client, admin_client, fake_llm, warning_sign_png
):
    inspection_id = client.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    qc_client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "NG", "review_note": "第一次"})
    qc_client.patch(f"/api/inspections/{inspection_id}/review", json={"review_verdict": "OK", "review_note": "改判"})

    entries = _audit(admin_client, action="inspection.review")
    assert len(entries) == 2
    newest, oldest = entries
    assert newest["actor"] == "user:qc_test" and newest["target_id"] == str(inspection_id)
    assert oldest["before"]["review_verdict"] is None and oldest["after"]["review_verdict"] == "NG"
    assert newest["before"]["review_verdict"] == "NG" and newest["after"]["review_verdict"] == "OK"
    assert newest["after"]["reviewer"] == "qc_test"
    assert newest["request_id"]


def test_user_management_actions_are_audited_without_passwords(admin_client):
    created = admin_client.post(
        "/api/users", json={"username": "gina", "display_name": "吉娜", "password": TEST_PASSWORD, "role": "operator"}
    ).json()
    admin_client.patch(f"/api/users/{created['id']}", json={"role": "qc"})
    admin_client.patch(f"/api/users/{created['id']}", json={"is_active": False})
    admin_client.patch(f"/api/users/{created['id']}", json={"is_active": True})
    admin_client.post(f"/api/users/{created['id']}/password", json={"new_password": "another-password-1"})

    actions = [e["action"] for e in _audit(admin_client, target_type="user")]
    for expected in ("user.create", "user.role_change", "user.disable", "user.enable", "user.password_reset"):
        assert expected in actions
    dump = json.dumps(_audit(admin_client), ensure_ascii=False)
    assert TEST_PASSWORD not in dump and "another-password-1" not in dump and "argon2" not in dump
    role_entry = next(e for e in _audit(admin_client) if e["action"] == "user.role_change")
    assert role_entry["before"] == {"role": "operator"} and role_entry["after"] == {"role": "qc"}


def test_operator_override_is_recorded_and_default_is_login_display_name(
    make_session_client, admin_client, fake_llm, warning_sign_png
):
    from urllib.parse import quote

    op = make_session_client("operator", "hank", "漢克")
    default = op.post("/api/general/describe", files=_png_file(warning_sign_png)).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{default}").json()["operator"] == "漢克"  # 沒填就帶登入者
    assert not [e for e in _audit(admin_client) if e["action"] == "inspection.operator_override"]

    same = op.post("/api/general/describe", files=_png_file(warning_sign_png), headers={"X-Operator": quote("漢克")})
    assert same.status_code == 200
    assert not [e for e in _audit(admin_client) if e["action"] == "inspection.operator_override"]

    other = op.post(
        "/api/general/describe", files=_png_file(warning_sign_png), headers={"X-Operator": quote("代簽的小明")}
    ).json()["inspection_id"]
    assert admin_client.get(f"/api/inspections/{other}").json()["operator"] == "代簽的小明"
    override = [e for e in _audit(admin_client) if e["action"] == "inspection.operator_override"]
    assert len(override) == 1
    assert override[0]["actor"] == "user:hank" and override[0]["target_id"] == str(other)
    assert override[0]["before"] == {"operator": "漢克"} and override[0]["after"] == {"operator": "代簽的小明"}


def test_golden_sample_and_threshold_and_category_changes_are_audited(admin_client, monkeypatch):
    from core import anomaly_training
    from samples import make_samples

    def png(img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    rois_a = [[0.1, 0.1, 0.2, 0.2]]
    rois_b = [[0.3, 0.3, 0.4, 0.4], [0.5, 0.5, 0.6, 0.6]]
    for rois in (rois_a, rois_b):
        res = admin_client.post(
            "/api/assembly/golden-samples",
            params={"part_no": "audit_part"},
            data={"rois": json.dumps(rois)},
            files={"file": ("g.png", png(make_samples.make_assembly_scene()), "image/png")},
        )
        assert res.status_code == 200
    entries = [e for e in _audit(admin_client, target_type="golden_sample")]
    assert [e["action"] for e in reversed(entries)] == ["golden_sample.create", "golden_sample.update"]
    assert entries[0]["before"] == {"rois": rois_a} and entries[0]["after"] == {"rois": rois_b}

    monkeypatch.setattr(anomaly_training, "get_status", lambda name: {"status": "done", "threshold": 40.0})
    monkeypatch.setattr(anomaly_training, "set_threshold", lambda name, t: {"name": name, "threshold": t})
    assert admin_client.patch("/api/anomaly/categories/screw/threshold", json={"threshold": 45.5}).status_code == 200
    entry = _audit(admin_client, action="anomaly_threshold.update")[0]
    assert entry["before"] == {"threshold": 40.0} and entry["after"] == {"threshold": 45.5}
    assert entry["target_id"] == "screw"


def test_audit_query_filters_and_is_admin_only(admin_client, qc_client):
    admin_client.post(
        "/api/users", json={"username": "ivy", "display_name": "I", "password": TEST_PASSWORD, "role": "operator"}
    )
    assert _audit(admin_client, action="user.create")
    assert _audit(admin_client, action="no.such.action") == []
    assert _audit(admin_client, actor="user:admin_test")
    assert _audit(admin_client, actor="user:nobody") == []
    assert qc_client.get("/api/audit").status_code == 403


# --- CSRF ---


def test_cross_site_write_is_blocked_but_same_origin_and_api_key_are_fine(
    admin_client, client, fake_llm, warning_sign_png
):
    files = _png_file(warning_sign_png)
    evil = admin_client.post("/api/general/describe", files=files, headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403
    same = admin_client.post("/api/general/describe", files=files, headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    with_key = client.post("/api/general/describe", files=files, headers={"Origin": "http://evil.example"})
    assert with_key.status_code == 200  # 系統對系統呼叫不受 Origin 檢查影響


# --- 啟動檢查與機密 ---


def _import_main(env_extra: dict):
    import os

    env = {k: v for k, v in os.environ.items() if k != "SESSION_SECRET"}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", "import main"], cwd=ROOT / "backend", env=env, capture_output=True, text=True
    )


def test_startup_refuses_without_or_with_short_session_secret():
    missing = _import_main({})
    assert missing.returncode != 0 and "SESSION_SECRET" in missing.stderr
    short = _import_main({"SESSION_SECRET": "too-short"})
    assert short.returncode != 0 and "SESSION_SECRET" in short.stderr
    ok = _import_main({"SESSION_SECRET": "x" * 40})
    assert ok.returncode == 0, ok.stderr


def test_no_api_key_or_secret_in_frontend_sources():
    offenders = []
    for path in (ROOT / "frontend").rglob("*"):
        if not path.is_file() or "vendor" in path.parts or path.suffix not in (".js", ".html", ".css"):
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("FRONTEND_API_KEY", "dev-frontend-key", "dev-erp-key", "X-API-Key", "api_key"):
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)}: {needle}")
    assert offenders == []


# --- 遷移與腳本 ---


def test_legacy_db_gains_users_audit_and_created_by(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, module TEXT NOT NULL,"
        " verdict TEXT NOT NULL, engine TEXT NOT NULL, elapsed_ms INTEGER NOT NULL, summary_json TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO inspections (created_at, module, verdict, engine, elapsed_ms, summary_json)"
        " VALUES ('2026-01-01T00:00:00', 'codes', 'OK', 'e', 1, '[]')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("INSPECTION_DB", str(db))

    from core.inspection_log import query_inspections

    rows = query_inspections()
    assert len(rows) == 1 and rows[0]["created_by"] is None
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "audit_log"} <= tables


def test_create_admin_script_creates_a_loginable_admin_and_audits(client, bare):
    sys.path.insert(0, str(ROOT / "scripts"))
    import create_admin

    create_admin.create_admin("firstadmin", "第一位", "first-admin-pass")
    res = bare.post("/api/auth/login", json={"username": "firstadmin", "password": "first-admin-pass"})
    assert res.status_code == 200 and res.json()["role"] == "admin"
    with pytest.raises(ValueError):
        create_admin.create_admin("firstadmin", "重複", "first-admin-pass")
    with pytest.raises(ValueError):
        create_admin.create_admin("weakadmin", "弱", "short")

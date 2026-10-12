"""本機帳號：建立、驗證（含登入失敗鎖定）、停用、改角色、改密碼。密碼用 argon2id 雜湊。"""

import re
import sqlite3
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from core.inspection_log import connect
from core.settings import get_settings

ROLES = ("operator", "qc", "admin")
MIN_PASSWORD_LENGTH = 10
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")

_hasher = PasswordHasher()
# 帳號不存在時也做一次雜湊驗證，讓回應時間不洩漏「這個帳號存不存在」
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

LOGIN_FAILED_MESSAGE = "帳號或密碼錯誤，或帳號已停用／暫時鎖定"


class AuthError(Exception):
    pass


def _public(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    d["is_active"] = bool(d["is_active"])
    return d


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密碼至少 {MIN_PASSWORD_LENGTH} 個字元")


def create_user(username: str, display_name: str, password: str, role: str) -> dict:
    if not _USERNAME_PATTERN.match(username):
        raise ValueError("帳號只能用英數字與 . _ -，長度 3–32")
    if role not in ROLES:
        raise ValueError(f"角色只能是 {ROLES} 其中之一，目前是「{role}」")
    if not display_name.strip():
        raise ValueError("顯示名稱不可空白")
    validate_password(password)
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, created_at)"
                " VALUES (?, ?, ?, ?, 1, ?)",
                (
                    username,
                    display_name.strip(),
                    _hasher.hash(password),
                    role,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"帳號「{username}」已存在")
        conn.commit()
    return get_user(cur.lastrowid)


def get_user(user_id: int) -> dict | None:
    with connect() as conn:
        return _public(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_username(username: str) -> dict | None:
    with connect() as conn:
        return _public(conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone())


def list_users() -> list[dict]:
    with connect() as conn:
        return [_public(r) for r in conn.execute("SELECT * FROM users ORDER BY id").fetchall()]


def count_active_admins() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]


def _guard_last_admin(user: dict, *, will_remain_active_admin: bool) -> None:
    """不可讓系統沒有任何啟用中的 admin（會鎖死使用者管理）。"""
    if user["role"] == "admin" and user["is_active"] and not will_remain_active_admin:
        if count_active_admins() <= 1:
            raise ValueError("這是最後一個啟用中的 admin，不能停用或降級")


def set_active(user_id: int, active: bool) -> dict:
    user = get_user(user_id)
    if user is None:
        raise LookupError(f"找不到使用者 id={user_id}")
    _guard_last_admin(user, will_remain_active_admin=active)
    with connect() as conn:
        conn.execute(
            "UPDATE users SET is_active = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (1 if active else 0, user_id),
        )
        conn.commit()
    return get_user(user_id)


def set_role(user_id: int, role: str) -> dict:
    if role not in ROLES:
        raise ValueError(f"角色只能是 {ROLES} 其中之一，目前是「{role}」")
    user = get_user(user_id)
    if user is None:
        raise LookupError(f"找不到使用者 id={user_id}")
    _guard_last_admin(user, will_remain_active_admin=(role == "admin"))
    with connect() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
    return get_user(user_id)


def set_password(user_id: int, password: str) -> None:
    validate_password(password)
    if get_user(user_id) is None:
        raise LookupError(f"找不到使用者 id={user_id}")
    with connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (_hasher.hash(password), user_id),
        )
        conn.commit()


def authenticate(username: str, password: str) -> dict:
    """驗證成功回傳使用者；失敗一律丟 AuthError（訊息不區分原因）。連續失敗達上限會鎖定。"""
    settings = get_settings()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            try:
                _hasher.verify(_DUMMY_HASH, password)
            except (VerifyMismatchError, InvalidHashError):
                pass
            raise AuthError(LOGIN_FAILED_MESSAGE)

        now = datetime.now()
        locked = row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now
        try:
            _hasher.verify(row["password_hash"], password)
            password_ok = True
        except (VerifyMismatchError, InvalidHashError):
            password_ok = False

        if locked or not row["is_active"]:
            raise AuthError(LOGIN_FAILED_MESSAGE)  # 鎖定中／已停用：即使密碼正確也不放行，也不延長鎖定

        if not password_ok:
            failed = row["failed_attempts"] + 1
            locked_until = None
            if failed >= settings.login_max_failures:
                locked_until = (now + timedelta(minutes=settings.login_lock_minutes)).isoformat(timespec="seconds")
                failed = 0
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?", (failed, locked_until, row["id"])
            )
            conn.commit()
            raise AuthError(LOGIN_FAILED_MESSAGE)

        new_hash = _hasher.hash(password) if _hasher.check_needs_rehash(row["password_hash"]) else row["password_hash"]
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, password_hash = ? WHERE id = ?",
            (new_hash, row["id"]),
        )
        conn.commit()
    return get_user(row["id"])


def verify_password(user_id: int, password: str) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return False
    try:
        _hasher.verify(row["password_hash"], password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False

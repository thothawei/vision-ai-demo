"""使用者管理（僅 admin，不接受 API key）。所有變更寫稽核，稽核內容不含密碼或雜湊。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import audit, users
from core.auth import Principal, require_role

router = APIRouter(prefix="/api/users", tags=["使用者管理"], dependencies=[Depends(require_role("admin"))])
_admin = require_role("admin")


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    password: str
    role: str


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


def _snapshot(user: dict) -> dict:
    return {k: user[k] for k in ("username", "display_name", "role", "is_active")}


@router.get("")
def list_all():
    return users.list_users()


@router.post("", status_code=201)
def create(body: CreateUserRequest, principal: Principal = Depends(_admin)):
    try:
        user = users.create_user(body.username, body.display_name, body.password, body.role)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(principal.actor, "user.create", "user", user["id"], after=_snapshot(user))
    return user


@router.patch("/{user_id}")
def update(user_id: int, body: UpdateUserRequest, principal: Principal = Depends(_admin)):
    before = users.get_user(user_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"找不到使用者 id={user_id}")
    try:
        if body.role is not None and body.role != before["role"]:
            users.set_role(user_id, body.role)
            audit.record(principal.actor, "user.role_change", "user", user_id,
                         before={"role": before["role"]}, after={"role": body.role})
        if body.is_active is not None and body.is_active != before["is_active"]:
            users.set_active(user_id, body.is_active)
            audit.record(principal.actor, "user.enable" if body.is_active else "user.disable", "user", user_id,
                         before={"is_active": before["is_active"]}, after={"is_active": body.is_active})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return users.get_user(user_id)


@router.post("/{user_id}/password")
def reset_password(user_id: int, body: ResetPasswordRequest, principal: Principal = Depends(_admin)):
    try:
        users.set_password(user_id, body.new_password)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(principal.actor, "user.password_reset", "user", user_id)
    return {"ok": True}

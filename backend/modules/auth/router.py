"""登入、登出、目前身分、自行改密碼。登入端點本身不需要驗證。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import audit, users
from core.auth import Principal, require_login
from core.users import AuthError

router = APIRouter(prefix="/api/auth", tags=["帳號"])
logger = logging.getLogger("vision.auth")


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


def _me(principal: Principal) -> dict:
    return {"kind": principal.kind, "username": principal.name, "display_name": principal.display_name,
            "role": principal.role}


@router.post("/login")
def login(body: LoginRequest, request: Request):
    try:
        user = users.authenticate(body.username, body.password)
    except AuthError as e:
        logger.warning("登入失敗 username=%s", body.username)
        raise HTTPException(status_code=401, detail=str(e))
    request.session.clear()  # 換一份新 session，避免沿用登入前的內容
    request.session["user_id"] = user["id"]
    logger.info("登入成功 username=%s role=%s", user["username"], user["role"])
    return {"kind": "user", "username": user["username"], "display_name": user["display_name"], "role": user["role"]}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(require_login)):
    return _me(principal)


@router.post("/password")
def change_password(body: PasswordChangeRequest, principal: Principal = Depends(require_login)):
    if principal.kind != "user":
        raise HTTPException(status_code=403, detail="API key 沒有密碼可以修改")
    if not users.verify_password(principal.user_id, body.current_password):
        raise HTTPException(status_code=400, detail="目前密碼不正確")
    try:
        users.set_password(principal.user_id, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(principal.actor, "user.password_change", "user", principal.user_id)
    return {"ok": True}

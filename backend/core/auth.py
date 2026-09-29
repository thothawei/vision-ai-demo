"""身分與權限：登入 session（使用者）或 X-API-Key（系統對系統），以及依角色的 dependency。

- 使用者：session 只存 user_id，每個請求都從資料庫重讀，停用帳號或改角色立即生效。
- API key：`API_KEYS=名稱:key,...`，給 ERP、資料夾監控腳本用；預設只能辨識與唯讀，不能複判或做管理。
"""

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request

from core import request_scope, users
from core.settings import get_settings

ROLE_RANK = {"operator": 1, "qc": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    kind: Literal["user", "api-key"]
    name: str  # 帳號或 API key 名稱
    role: str | None = None  # 只有使用者有角色
    user_id: int | None = None
    display_name: str = ""

    @property
    def actor(self) -> str:
        return f"user:{self.name}" if self.kind == "user" else f"api-key:{self.name}"


def _api_key_names() -> dict[str, str]:
    keys = {}
    for pair in get_settings().api_keys.split(","):
        name, _, key = pair.strip().partition(":")
        if name and key:
            keys[key] = name
    return keys


def _match_api_key(candidate: str | None) -> str | None:
    if not candidate:
        return None
    found = None
    for key, name in _api_key_names().items():  # 逐一比對且不提早結束，避免時間差
        if hmac.compare_digest(key.encode(), candidate.encode()):
            found = name
    return found


def principal_from_request(request: Request) -> Principal | None:
    user_id = request.session.get("user_id") if "session" in request.scope else None
    if user_id is not None:
        user = users.get_user(user_id)
        if user and user["is_active"]:
            return Principal("user", user["username"], user["role"], user["id"], user["display_name"])
        request.session.clear()  # 帳號已停用或刪除：session 立即失效
    name = _match_api_key(request.headers.get("X-API-Key"))
    if name:
        return Principal("api-key", name)
    return None


def _bind_to_scope(principal: Principal) -> None:
    scope = request_scope.get_scope()
    scope.user = principal.actor
    if principal.kind != "user":
        return
    scope.trace_operator_default = principal.display_name
    typed = scope.trace.get("operator")
    if not typed:
        scope.trace["operator"] = principal.display_name  # 沒填就帶登入者
    elif typed != principal.display_name:
        scope.operator_override = typed  # 代簽：照存，並在辨識完成時記稽核


def require_login(request: Request) -> Principal:
    """任何已登入使用者或有效的 API key。"""
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="請先登入")
    _bind_to_scope(principal)
    return principal


def require_role(min_role: str, *, allow_api_key: bool = False):
    """使用者角色需達 min_role；`allow_api_key=True` 時，有效 API key 也放行（唯讀端點用）。"""

    def dependency(request: Request) -> Principal:
        principal = require_login(request)
        if principal.kind == "api-key":
            if not allow_api_key:
                raise HTTPException(status_code=403, detail="這個操作需要使用者登入，API key 不可使用")
            return principal
        if ROLE_RANK[principal.role] < ROLE_RANK[min_role]:
            raise HTTPException(status_code=403, detail=f"權限不足，需要 {min_role} 以上角色")
        return principal

    return dependency

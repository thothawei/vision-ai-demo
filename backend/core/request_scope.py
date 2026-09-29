"""請求範圍資料：追溯資訊、request_id 與本次請求讀進來的圖片（依 role 分開）。

放在 ContextVar 裡，跨 threadpool 傳遞（Phase 9 已實測）：middleware 建立 scope 物件，
threadpool 內的 service 拿到同一個物件並就地修改，所以 `record_result()` 不用改函式簽名。
同一個 role 重複載入時以最後一次為準（批次逐張處理靠這點，仍會在每張前 `reset_images()`）。"""

from contextvars import ContextVar
from dataclasses import dataclass, field

TRACE_HEADER_MAP = {
    "work_order": "X-Work-Order",
    "part_no": "X-Part-No",
    "lot_no": "X-Lot-No",
    "station": "X-Station",
    "operator": "X-Operator",
}

# raw 為使用者上傳的原圖；其餘為模組自行登錄的輔助圖（例如 M10 的黃金樣本）
IMAGE_ROLES = ("raw", "golden", "reference")


@dataclass
class RequestScope:
    trace: dict = field(default_factory=dict)
    request_id: str | None = None
    images: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    user: str | None = None  # 操作者身分（user:<帳號> 或 api-key:<名稱>），存進 inspections.created_by
    operator_override: str | None = None  # 使用者手動把追溯欄位「操作員」改成別人時的值（要記稽核）
    trace_operator_default: str | None = None  # 登入者顯示名稱（操作員欄位的預設值）


_scope_var: ContextVar[RequestScope | None] = ContextVar("request_scope", default=None)


def begin_request(trace: dict | None = None, request_id: str | None = None) -> RequestScope:
    scope = RequestScope(trace=trace or {}, request_id=request_id)
    _scope_var.set(scope)
    return scope


def get_scope() -> RequestScope:
    scope = _scope_var.get()
    if scope is None:
        # 沒經過 middleware（單元測試直接呼叫 service、背景執行緒）時退回空 scope
        scope = begin_request()
    return scope


def get_trace() -> dict:
    return get_scope().trace


def get_request_id() -> str | None:
    scope = _scope_var.get()
    return scope.request_id if scope else None


def add_image(role: str, image_bytes: bytes, ext: str) -> None:
    if role not in IMAGE_ROLES:
        raise ValueError(f"role 只能是 {IMAGE_ROLES} 其中之一，目前是「{role}」")
    get_scope().images[role] = (image_bytes, ext)


def get_images() -> dict[str, tuple[bytes, str]]:
    return get_scope().images


def reset_images() -> None:
    get_scope().images.clear()

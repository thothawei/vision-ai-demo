"""每個請求的追溯資訊（工單/料號/批號/站別/操作員）與原圖 bytes，用 contextvar 在
middleware → image_io.load_image() → inspection_log.record_result() 之間傳遞，
不需要改動 13 個模組 service.py 的函式簽名。"""

from contextvars import ContextVar

TRACE_HEADER_MAP = {
    "work_order": "X-Work-Order",
    "part_no": "X-Part-No",
    "lot_no": "X-Lot-No",
    "station": "X-Station",
    "operator": "X-Operator",
}

_trace_ctx: ContextVar[dict] = ContextVar("trace_ctx", default={})
_raw_image_ctx: ContextVar[tuple[bytes, str] | None] = ContextVar("raw_image_ctx", default=None)


def set_trace(values: dict) -> None:
    _trace_ctx.set(values)


def get_trace() -> dict:
    return _trace_ctx.get()


def set_raw_image(image_bytes: bytes, ext: str) -> None:
    _raw_image_ctx.set((image_bytes, ext))


def get_raw_image() -> tuple[bytes, str] | None:
    return _raw_image_ctx.get()

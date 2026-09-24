"""Phase 10：/api/inspections* 的 X-API-Key 驗證。

只保護 `/api/inspections*`（ERP 會定期輪詢、含原圖/標註圖的真正敏感面），13 個辨識端點
（/api/general、/api/docs...）維持不用 key，靠 main.py 的 CORS 白名單擋外部網域——這是單機
demo、沒有公開網路曝露的情境下的取捨，見 CLAUDE.md「技術決策與理由（Phase 10）」。
"""

import os

from starlette.requests import Request

PROTECTED_PREFIX = "/api/inspections"


def _valid_keys() -> set[str]:
    raw = os.environ.get("API_KEYS", "")
    keys = set()
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        _, _, key = pair.partition(":")
        if key:
            keys.add(key)
    return keys


def extract_key(request: Request) -> str | None:
    """優先讀 X-API-Key header；沒有的話退回 `?api_key=` query 參數。

    需要 query 參數退路的原因：`<img src>` 與純連結下載（CSV 匯出）沒有辦法附加自訂
    header，瀏覽器原生機制不支援。這代表 key 可能留在瀏覽器歷史紀錄／伺服器 access log，
    在單機、沒有對外網路曝露的 demo 情境下是可接受的取捨，正式環境需要额外考量。
    """
    header_key = request.headers.get("X-API-Key")
    if header_key:
        return header_key
    return request.query_params.get("api_key")


def is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    return key in _valid_keys()


def is_protected_path(path: str) -> bool:
    return path.startswith(PROTECTED_PREFIX)

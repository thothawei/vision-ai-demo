"""所有辨識模組共用的回應格式，之後 manufacturing-erp 串接時依這個結構讀取。"""

from typing import Any, Literal

from pydantic import BaseModel

Verdict = Literal["OK", "NG", "INFO"]


class InspectionResult(BaseModel):
    module: str
    verdict: Verdict
    items: list[dict[str, Any]]
    annotated_image: str | None = None
    engine: str
    elapsed_ms: int
    inspection_id: int | None = None


class ModuleError(Exception):
    """模組可預期的錯誤，main.py 統一轉成 JSON：{"detail": message}。"""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

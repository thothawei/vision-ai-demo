"""M7 銘牌欄位 schema。"""

from pydantic import BaseModel


class Nameplate(BaseModel):
    廠牌: str
    型號: str
    序號: str
    製造日期: str
    電壓: str

"""M12 出貨標籤欄位 schema。三個欄位都允許空字串／None——標籤上不見得每項都印，
LLM 找不到就填空，不強迫湊出不存在的資料。"""

from pydantic import BaseModel


class ShippingLabel(BaseModel):
    料號: str
    數量: str
    批號: str

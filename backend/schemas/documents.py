"""M4 製造文件結構化的欄位 schema。

數字欄位一律用 SourcedNumber：LLM 除了給數字，還要附上「這個數字是從 OCR 原文哪裡抄的」。
service 層會拿這段原文片段去比對 OCR 原始文字是否真的有這段文字（見 modules/docs/service.py
的 _verify_sources），比對不到就標記「來源可疑」而不是照單全收——避免 LLM 把數字捏造得煞有其事。
"""

from typing import Literal

from pydantic import BaseModel, Field

# 目前有嚴格 schema 的文件類型；其餘（報價單、名片、其他）沿用自由格式
STRICT_DOC_TYPES = ("工單", "出貨單", "進料檢驗報告")


class SourcedNumber(BaseModel):
    值: float
    原文片段: str = Field(min_length=1, description="這個數字在 OCR 原文中對應的片段，必須逐字照抄")


class WorkOrder(BaseModel):
    """工單"""

    工單號: str
    料號: str
    品名: str
    數量: SourcedNumber
    開工日: str
    完工日: str
    製程站別: str


class ShippingItem(BaseModel):
    料號: str
    品名: str
    數量: SourcedNumber
    單價: SourcedNumber


class ShippingOrder(BaseModel):
    """出貨單"""

    單號: str
    客戶: str
    日期: str
    品項: list[ShippingItem]
    總額: SourcedNumber


class InspectionReport(BaseModel):
    """進料檢驗報告"""

    供應商: str
    料號: str
    批號: str
    抽樣數: SourcedNumber
    不良數: SourcedNumber
    判定: Literal["合格", "不合格"]


DOC_TYPE_SCHEMAS: dict[str, type[BaseModel]] = {
    "工單": WorkOrder,
    "出貨單": ShippingOrder,
    "進料檢驗報告": InspectionReport,
}

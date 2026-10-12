"""辨識動作註冊表：動作／模組／分頁／分類／參數／缺陷抽取規則的單一真實來源。

新增一個辨識動作只需要在本檔 `_SPECS` 加一筆 ActionSpec：批次 API、`GET /api/modules`、
NG 原因柏拉圖、前端導覽都由這份註冊表衍生。各模組自己的 router（URL 與表單欄位）保留，
由 `router` 欄位指出，main.py 依此掛載。
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from core import defect_extractors as dx
from core.schemas import InspectionResult, ModuleError

Handler = Callable[[bytes, BaseModel], InspectionResult]

# 前端左側導覽的分類順序
CATEGORIES = ["外觀檢測", "量測與讀值", "追溯與標籤", "文件", "工安", "其他"]


class _Params(BaseModel):
    """所有動作參數模型的基底：不認得的參數一律 422，避免『參數被靜默忽略』（M12 漏改的根因）。"""

    model_config = ConfigDict(extra="forbid")


class DocsParams(_Params):
    mode: str = "ocr"


class AnomalyParams(_Params):
    category: str | None = None  # 缺少時由 handler 對該張回報錯誤，不讓整批 422


class CountParams(_Params):
    expected_count: int | None = None
    min_area_ratio: float = 0.0005


class MeasureParams(_Params):
    marker_size_mm: float = 30.0
    target_length_mm: float | None = None
    target_width_mm: float | None = None
    tolerance_mm: float = 1.0


class IntrusionParams(_Params):
    zone: str | None = None


class GaugeParams(_Params):
    min_value: float = 0.0
    max_value: float = 100.0
    min_angle: float = 135.0
    max_angle: float = 45.0
    center_x: float | None = None
    center_y: float | None = None


class AssemblyParams(_Params):
    golden: str | None = None  # 黃金樣本的料號；沒填時用配方的料號


class ColorParams(_Params):
    """色差標準：標準色（ref_lab 或 ref_rect 二選一）＋量測區＋門檻（ΔE00，超過判 NG）。"""

    ref_lab: list[float] | None = None
    ref_rect: list[float] | None = None
    measure_rect: list[float]
    threshold: float = 3.0

    @model_validator(mode="after")
    def _check(self):
        if (self.ref_lab is None) == (self.ref_rect is None):
            raise ValueError("ref_lab 與 ref_rect 要二選一")
        if self.ref_lab is not None and len(self.ref_lab) != 3:
            raise ValueError("ref_lab 要是 [L, a, b] 三個數字")
        for name in ("ref_rect", "measure_rect"):
            rect = getattr(self, name)
            if rect is not None and (len(rect) != 4 or any(not 0 <= v <= 1 for v in rect)):
                raise ValueError(f"{name} 要是 [x1, y1, x2, y2] 四個 0~1 的正規化座標")
        return self


class ShippingParams(_Params):
    expected_part_no: str | None = None
    expected_lot_no: str | None = None
    expected_quantity: int | None = None


@dataclass(frozen=True)
class ActionSpec:
    action: str  # 批次用代號
    module: str  # 寫進 inspections.module 的名稱
    label: str  # 前端顯示名稱
    category: str  # CATEGORIES 之一
    tab: str  # 前端分頁 id（一個分頁可對應多個動作，例如計數與量測）
    verdict_kind: Literal["inspection", "info"]  # info 不會判 NG，不列入良率
    handler: Handler | None = None  # 批次用；不支援批次的動作為 None
    params: type[BaseModel] | None = None
    defect_extractor: Callable[[list], list[str]] | None = None  # 柏拉圖用；掛在 module 層級
    requires: list[str] = field(
        default_factory=list
    )  # 給健康檢查用：model:<模型 id>、anomaly（至少一個異常檢測類別可用）、llm
    router: str | None = None  # 該動作端點所在的 router 模組（main.py 依此掛載）
    batch_enabled: bool = True  # False：有 handler（可用於配方）但不開放批次 API

    @property
    def batchable(self) -> bool:
        return self.handler is not None and self.batch_enabled


def _build_specs() -> list[ActionSpec]:
    # 延後匯入：各模組 service 會匯入 inspection_log，而 inspection_log 會回頭查本註冊表
    from modules.anomaly.service import inspect_part
    from modules.assembly.service import inspect_assembly
    from modules.codes.service import decode_codes
    from modules.colordiff.service import check_color_difference
    from modules.defect.service import detect_pcb_defects
    from modules.docs.service import extract_document
    from modules.general.service import describe_image
    from modules.measure.service import count_parts, measure_part
    from modules.medical.service import check_packaging, classify_pneumonia_demo
    from modules.nameplate.service import read_gauge, read_nameplate, read_seven_segment
    from modules.safety.service import detect_intrusion, detect_ppe
    from modules.shipping.service import check_shipping_label

    def anomaly(image_bytes, p):
        if not p.category:
            raise ModuleError("anomaly 動作需要 category 參數", 400)
        return inspect_part(image_bytes, p.category)

    def assembly_handler(image_bytes, p):
        if not p.golden:
            raise ModuleError("assembly 動作需要 golden（黃金樣本料號）參數", 400)
        return inspect_assembly(p.golden, image_bytes)

    return [
        ActionSpec(
            "anomaly",
            "anomaly",
            "外觀瑕疵異常檢測",
            "外觀檢測",
            "anomaly",
            "inspection",
            anomaly,
            AnomalyParams,
            dx.defect_anomaly,
            ["anomaly"],
            "modules.anomaly.router",
        ),
        ActionSpec(
            "defect",
            "defect",
            "PCB 瑕疵偵測",
            "外觀檢測",
            "defect",
            "inspection",
            lambda b, p: detect_pcb_defects(b),
            None,
            dx.defect_pcb,
            ["model:pcb-defect"],
            "modules.defect.router",
        ),
        ActionSpec(
            "assembly",
            "assembly",
            "組裝防呆比對",
            "外觀檢測",
            "assembly",
            "inspection",
            assembly_handler,
            AssemblyParams,
            dx.defect_assembly,
            [],
            "modules.assembly.router",
            batch_enabled=False,
        ),
        ActionSpec(
            "colordiff",
            "colordiff",
            "烤漆/陽極色差",
            "外觀檢測",
            "colordiff",
            "inspection",
            lambda b, p: check_color_difference(b, p.ref_rect, p.ref_lab, p.measure_rect, p.threshold),
            ColorParams,
            dx.defect_colordiff,
            [],
            "modules.colordiff.router",
            batch_enabled=False,
        ),
        ActionSpec(
            "count",
            "measure",
            "計數",
            "量測與讀值",
            "measure",
            "inspection",
            lambda b, p: count_parts(b, p.expected_count, p.min_area_ratio),
            CountParams,
            dx.defect_measure,
            [],
            "modules.measure.router",
        ),
        ActionSpec(
            "measure",
            "measure",
            "尺寸量測",
            "量測與讀值",
            "measure",
            "inspection",
            lambda b, p: measure_part(b, p.marker_size_mm, p.target_length_mm, p.target_width_mm, p.tolerance_mm),
            MeasureParams,
            dx.defect_measure,
            [],
            "modules.measure.router",
        ),
        ActionSpec(
            "seven_segment",
            "nameplate",
            "七段顯示器",
            "量測與讀值",
            "sevenseg",
            "inspection",
            lambda b, p: read_seven_segment(b),
            None,
            dx.defect_nameplate,
            [],
            "modules.nameplate.router",
        ),
        ActionSpec(
            "gauge",
            "nameplate",
            "指針錶",
            "量測與讀值",
            "gauge",
            "info",
            lambda b, p: read_gauge(b, p.min_value, p.max_value, p.min_angle, p.max_angle, p.center_x, p.center_y),
            GaugeParams,
            None,
            [],
            "modules.nameplate.router",
        ),
        ActionSpec(
            "codes",
            "codes",
            "追溯碼辨識",
            "追溯與標籤",
            "codes",
            "inspection",
            lambda b, p: decode_codes(b),
            None,
            dx.defect_codes,
            [],
            "modules.codes.router",
        ),
        ActionSpec(
            "packaging",
            "medical_packaging",
            "包裝追溯碼檢核",
            "追溯與標籤",
            "packaging",
            "inspection",
            lambda b, p: check_packaging(b),
            None,
            dx.defect_packaging,
            ["llm"],
            "modules.medical.router",
        ),
        ActionSpec(
            "shipping",
            "shipping",
            "出貨標籤比對",
            "追溯與標籤",
            "shipping",
            "inspection",
            lambda b, p: check_shipping_label(
                b, p.expected_part_no or None, p.expected_lot_no or None, p.expected_quantity
            ),
            ShippingParams,
            dx.defect_shipping,
            ["llm"],
            "modules.shipping.router",
        ),
        ActionSpec(
            "nameplate",
            "nameplate",
            "銘牌",
            "追溯與標籤",
            "nameplate",
            "inspection",
            lambda b, p: read_nameplate(b),
            None,
            dx.defect_nameplate,
            ["llm"],
            "modules.nameplate.router",
        ),
        ActionSpec(
            "docs",
            "docs",
            "製造文件結構化",
            "文件",
            "docs",
            "inspection",
            lambda b, p: extract_document(b, p.mode or "ocr"),
            DocsParams,
            dx.defect_docs,
            ["llm"],
            "modules.docs.router",
        ),
        ActionSpec(
            "intrusion",
            "safety",
            "危險區域入侵",
            "工安",
            "safety",
            "inspection",
            lambda b, p: detect_intrusion(b, p.zone),
            IntrusionParams,
            dx.defect_safety,
            ["model:person-detector"],
            "modules.safety.router",
        ),
        ActionSpec(
            "ppe",
            "ppe",
            "安全帽偵測",
            "工安",
            "ppe",
            "inspection",
            lambda b, p: detect_ppe(b),
            None,
            dx.defect_ppe,
            ["model:ppe-helmet"],
            "modules.safety.router",
        ),
        ActionSpec(
            "general",
            "general",
            "現場照片辨識",
            "其他",
            "general",
            "info",
            lambda b, p: describe_image(b),
            None,
            None,
            ["llm"],
            "modules.general.router",
        ),
        ActionSpec(
            "pneumonia",
            "medical_pneumonia_demo",
            "醫學影像分類展示",
            "其他",
            "pneumonia",
            "info",
            lambda b, p: classify_pneumonia_demo(b),
            None,
            None,
            ["model:pneumonia-cnn"],
            "modules.medical.router",
        ),
    ]


_registry: dict[str, ActionSpec] | None = None


def _load() -> dict[str, ActionSpec]:
    global _registry
    if _registry is None:
        _registry = {s.action: s for s in _build_specs()}
    return _registry


def all_actions() -> list[ActionSpec]:
    return list(_load().values())


def get_action(action: str) -> ActionSpec | None:
    return _load().get(action)


def register(spec: ActionSpec) -> None:
    """新增（或覆蓋）一個動作。正式動作寫在 _build_specs；這個函式讓測試能只改註冊表就加動作。"""
    _load()[spec.action] = spec


def unregister(action: str) -> None:
    _load().pop(action, None)


def extractor_for_module(module: str) -> Callable[[list], list[str]] | None:
    for spec in all_actions():
        if spec.module == module and spec.defect_extractor is not None:
            return spec.defect_extractor
    return None


def batch_action_names() -> list[str]:
    return sorted(s.action for s in all_actions() if s.batchable)


def routers():
    """回傳所有動作端點所在的 router（去重、依註冊順序）。"""
    seen = []
    for spec in all_actions():
        if spec.router and spec.router not in seen:
            seen.append(spec.router)
    return [importlib.import_module(path).router for path in seen]


def _module_labels() -> dict[str, str]:
    """inspections.module → 顯示名稱（看板／紀錄表用）；一個 module 有多個動作時以「／」串接。"""
    labels: dict[str, list[str]] = {}
    for spec in all_actions():
        labels.setdefault(spec.module, []).append(spec.label)
    return {module: "／".join(names) for module, names in labels.items()}


def describe() -> dict:
    """給 `GET /api/modules`：不含 handler／extractor 這類程式物件。"""
    return {
        "categories": CATEGORIES,
        "modules": _module_labels(),
        "actions": [
            {
                "action": s.action,
                "module": s.module,
                "label": s.label,
                "category": s.category,
                "tab": s.tab,
                "verdict_kind": s.verdict_kind,
                "batchable": s.batchable,
                "recipe_capable": s.handler is not None,
                "requires": s.requires,
                "params_schema": s.params.model_json_schema() if s.params else None,
            }
            for s in all_actions()
        ],
    }

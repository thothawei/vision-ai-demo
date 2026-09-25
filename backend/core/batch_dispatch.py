"""Phase 11：批次上傳（`POST /api/batch/{action}`）的動作對照表。

用「動作」而不是「module」當 key：`measure`／`nameplate`／`safety` 這三個模組底下
各自有 2-3 個不同的單張辨識動作（例如 measure 有 count 跟 measure 兩個獨立端點），
用 module 名稱當 key 會有歧義，所以直接沿用 13 個分頁實際呼叫的 14 個動作代號。
每個動作函式簽名一致：`(image_bytes: bytes, params: dict) -> InspectionResult`，
額外參數從 `params` dict 取（批次上傳裡整批共用同一組參數，不是每張各自設定）。
"""

from core.schemas import InspectionResult, ModuleError
from modules.anomaly.service import inspect_part
from modules.codes.service import decode_codes
from modules.defect.service import detect_pcb_defects
from modules.docs.service import extract_document
from modules.general.service import describe_image
from modules.measure.service import count_parts, measure_part
from modules.medical.service import check_packaging, classify_pneumonia_demo
from modules.nameplate.service import read_gauge, read_nameplate, read_seven_segment
from modules.safety.service import detect_intrusion, detect_ppe
from modules.shipping.service import check_shipping_label


def _float(params: dict, key: str, default: float | None) -> float | None:
    value = params.get(key)
    if value in (None, ""):
        return default
    return float(value)


def _general(image_bytes: bytes, params: dict) -> InspectionResult:
    return describe_image(image_bytes)


def _docs(image_bytes: bytes, params: dict) -> InspectionResult:
    return extract_document(image_bytes, params.get("mode") or "ocr")


def _anomaly(image_bytes: bytes, params: dict) -> InspectionResult:
    category = params.get("category")
    if not category:
        raise ModuleError("anomaly 動作需要 category 參數", 400)
    return inspect_part(image_bytes, category)


def _codes(image_bytes: bytes, params: dict) -> InspectionResult:
    return decode_codes(image_bytes)


def _count(image_bytes: bytes, params: dict) -> InspectionResult:
    expected = params.get("expected_count")
    return count_parts(
        image_bytes,
        int(expected) if expected not in (None, "") else None,
        _float(params, "min_area_ratio", 0.0005),
    )


def _measure(image_bytes: bytes, params: dict) -> InspectionResult:
    return measure_part(
        image_bytes,
        _float(params, "marker_size_mm", 30.0),
        _float(params, "target_length_mm", None),
        _float(params, "target_width_mm", None),
        _float(params, "tolerance_mm", 1.0),
    )


def _intrusion(image_bytes: bytes, params: dict) -> InspectionResult:
    return detect_intrusion(image_bytes, params.get("zone"))


def _ppe(image_bytes: bytes, params: dict) -> InspectionResult:
    return detect_ppe(image_bytes)


def _defect(image_bytes: bytes, params: dict) -> InspectionResult:
    return detect_pcb_defects(image_bytes)


def _nameplate(image_bytes: bytes, params: dict) -> InspectionResult:
    return read_nameplate(image_bytes)


def _seven_segment(image_bytes: bytes, params: dict) -> InspectionResult:
    return read_seven_segment(image_bytes)


def _gauge(image_bytes: bytes, params: dict) -> InspectionResult:
    return read_gauge(
        image_bytes,
        _float(params, "min_value", 0.0),
        _float(params, "max_value", 100.0),
        _float(params, "min_angle", 135.0),
        _float(params, "max_angle", 45.0),
        _float(params, "center_x", None),
        _float(params, "center_y", None),
    )


def _packaging(image_bytes: bytes, params: dict) -> InspectionResult:
    return check_packaging(image_bytes)


def _pneumonia(image_bytes: bytes, params: dict) -> InspectionResult:
    return classify_pneumonia_demo(image_bytes)


def _shipping(image_bytes: bytes, params: dict) -> InspectionResult:
    expected_quantity = params.get("expected_quantity")
    return check_shipping_label(
        image_bytes,
        params.get("expected_part_no") or None,
        params.get("expected_lot_no") or None,
        int(expected_quantity) if expected_quantity not in (None, "") else None,
    )


ACTIONS = {
    "general": _general,
    "docs": _docs,
    "anomaly": _anomaly,
    "codes": _codes,
    "count": _count,
    "measure": _measure,
    "intrusion": _intrusion,
    "ppe": _ppe,
    "defect": _defect,
    "nameplate": _nameplate,
    "seven_segment": _seven_segment,
    "gauge": _gauge,
    "packaging": _packaging,
    "pneumonia": _pneumonia,
    "shipping": _shipping,
}


def run_batch(action: str, files: list[tuple[str, bytes]], params: dict) -> dict:
    """逐檔呼叫對應動作，單檔失敗不中斷整批；回傳彙總 + 每檔結果。"""
    if action not in ACTIONS:
        raise ModuleError(f"action 只能是 {sorted(ACTIONS)} 其中之一，目前是「{action}」", 400)
    handler = ACTIONS[action]

    results = []
    counts = {"OK": 0, "NG": 0, "INFO": 0}
    failed = 0
    for filename, image_bytes in files:
        try:
            result = handler(image_bytes, params)
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
            results.append({"filename": filename, "status": "ok", "result": result})
        except ModuleError as e:
            failed += 1
            results.append({"filename": filename, "status": "error", "error": e.message})
        except Exception as e:  # noqa: BLE001 — 單張的未預期錯誤不該讓整批中斷
            failed += 1
            results.append({"filename": filename, "status": "error", "error": str(e)})

    return {
        "action": action,
        "total": len(files),
        "ok": counts["OK"],
        "ng": counts["NG"],
        "info": counts["INFO"],
        "failed": failed,
        "results": results,
    }

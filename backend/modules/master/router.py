"""主檔：料號與工單。讀取所有登入者與 API key（下拉選單用）；寫入 admin；
bulk-upsert 給 ERP 推送用（admin 或名為 `erp` 的 API key）。"""

from core import audit, master
from core.auth import Principal, require_login, require_role
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/master", tags=["主檔"])
_admin = require_role("admin")
_push = require_role("admin", allow_api_key=True, api_key_names=("erp",))


class PartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_no: str
    name: str = ""
    spec: str = ""
    customer: str = ""
    is_active: bool = True


class WorkOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_order_no: str
    part_no: str
    quantity: int = 0
    status: str = "planned"
    start_date: str | None = None
    end_date: str | None = None
    lot_no: str | None = None


class BulkParts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[PartBody] = Field(..., max_length=2000)


class BulkWorkOrders(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_orders: list[WorkOrderBody] = Field(..., max_length=2000)


_AUDIT_LIST_LIMIT = 200


@router.get("/parts")
def list_parts(active_only: bool = False, _: Principal = Depends(require_login)):
    return master.list_parts(active_only)


@router.post("/parts", status_code=201)
def upsert_part(body: PartBody, principal: Principal = Depends(_admin)):
    before = master.get_part(body.part_no)
    try:
        part, outcome = master.upsert_part(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(
        principal.actor,
        f"part.{'create' if outcome == 'created' else 'update'}",
        "part",
        part["part_no"],
        before=before,
        after=part,
    )
    return part


@router.get("/work-orders")
def list_work_orders(
    open_only: bool = False, part_no: str | None = None, limit: int = 500, _: Principal = Depends(require_login)
):
    return master.list_work_orders(open_only, part_no, limit)


@router.post("/work-orders", status_code=201)
def upsert_work_order(body: WorkOrderBody, principal: Principal = Depends(_admin)):
    before = master.get_work_order(body.work_order_no)
    try:
        work_order, _outcome = master.upsert_work_order(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(
        principal.actor, "work_order.update", "work_order", work_order["work_order_no"], before=before, after=work_order
    )
    return work_order


def _bulk(kind: str, rows: list[dict], principal: Principal) -> dict:
    result = master.bulk_upsert(kind, rows)
    audit.record(
        principal.actor,
        f"{kind}.bulk_upsert",
        kind[:-1] if kind == "parts" else "work_order",
        None,
        after={
            "created_count": len(result["created"]),
            "updated_count": len(result["updated"]),
            "error_count": len(result["errors"]),
            "created": result["created"][:_AUDIT_LIST_LIMIT],
            "updated": result["updated"][:_AUDIT_LIST_LIMIT],
        },
    )
    return result


@router.post("/parts:bulk-upsert")
def bulk_upsert_parts(body: BulkParts, principal: Principal = Depends(_push)):
    """整批更新料號；每列各自成功或失敗（errors 列出失敗的列與原因），不因一列有誤讓整批失敗。"""
    return _bulk("parts", [p.model_dump() for p in body.parts], principal)


@router.post("/work-orders:bulk-upsert")
def bulk_upsert_work_orders(body: BulkWorkOrders, principal: Principal = Depends(_push)):
    """整批更新工單；工單的料號必須已在主檔（可先呼叫 parts:bulk-upsert）。"""
    return _bulk("work_orders", [w.model_dump() for w in body.work_orders], principal)

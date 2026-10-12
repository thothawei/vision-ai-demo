from core import audit
from core.auth import require_role
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/audit", tags=["稽核紀錄"], dependencies=[Depends(require_role("admin"))])


@router.get("")
def list_audit(
    action: str | None = None,
    actor: str | None = None,
    target_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
):
    return audit.query(action, actor, target_type, date_from, date_to, limit)

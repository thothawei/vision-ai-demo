"""檢驗配方（版本管理）、依配方執行、run 查詢。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile

from core import audit, master, recipes, request_scope
from core.auth import Principal, require_login, require_role

router = APIRouter(prefix="/api", tags=["檢驗配方"])
logger = logging.getLogger("vision.recipe")
_admin = require_role("admin")
_read = require_role("qc", allow_api_key=True)


class StepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    params: dict = Field(default_factory=dict)
    image_slot: str = "main"
    label: str = ""


class RecipeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_no: str
    steps: list[StepBody]
    note: str = ""
    activate: bool = True


def _summary(recipe: dict) -> dict:
    return {"part_no": recipe["part_no"], "version": recipe["version"], "is_active": recipe["is_active"],
            "steps": [{"action": s["action"], "params": s["params"], "image_slot": s["image_slot"]}
                      for s in recipe["steps"]]}


@router.get("/recipes")
def list_recipes(part_no: str | None = None, _: Principal = Depends(_read)):
    return recipes.list_recipes(part_no)


@router.get("/recipes/active")
def active_recipe(part_no: str, _: Principal = Depends(require_login)):
    """執行前用：取得料號目前啟用的配方，前端依 `slots` 產生圖片上傳欄位。"""
    recipe = recipes.get_active_recipe(part_no)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"料號「{part_no}」沒有啟用中的檢驗配方")
    return recipe


@router.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int, _: Principal = Depends(_read)):
    recipe = recipes.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"找不到配方 id={recipe_id}")
    return recipe


@router.post("/recipes", status_code=201)
def create_recipe(body: RecipeBody, principal: Principal = Depends(_admin)):
    """新增一個版本（既有版本不可修改；要改參數就新增版本）。"""
    try:
        recipe = recipes.create_recipe(body.part_no, [s.model_dump() for s in body.steps], body.note,
                                       principal.name, body.activate)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit.record(principal.actor, "recipe.create", "recipe", recipe["id"], after=_summary(recipe))
    return recipe


def _switch(recipe_id: int, principal: Principal, activate: bool) -> dict:
    before = recipes.get_recipe(recipe_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"找不到配方 id={recipe_id}")
    previous = recipes.get_active_recipe(before["part_no"])
    after = recipes.activate_recipe(recipe_id) if activate else recipes.deactivate_recipe(recipe_id)
    audit.record(principal.actor, "recipe.activate" if activate else "recipe.deactivate", "recipe", recipe_id,
                 before={"part_no": before["part_no"], "active_version": previous["version"] if previous else None},
                 after={"part_no": before["part_no"], "version": after["version"], "is_active": after["is_active"]})
    return after


@router.post("/recipes/{recipe_id}/activate")
def activate(recipe_id: int, principal: Principal = Depends(_admin)):
    return _switch(recipe_id, principal, True)


@router.post("/recipes/{recipe_id}/deactivate")
def deactivate(recipe_id: int, principal: Principal = Depends(_admin)):
    return _switch(recipe_id, principal, False)


@router.post("/inspect/recipe")
async def inspect_by_recipe(request: Request, _: Principal = Depends(require_login)):
    """依配方檢驗：multipart 表單，圖片欄位名稱＝配方的圖片槽（多數配方只有 `main`）。
    料號來源優先序：表單 part_no > 工單（表單 work_order 或追溯 header）對應的料號 > 追溯 header 的料號。"""
    form = await request.form()
    scope = request_scope.get_scope()
    trace = scope.trace

    work_order_no = (form.get("work_order") or trace.get("work_order") or "").strip() or None
    work_order = master.get_work_order(work_order_no) if work_order_no else None
    part_no = (form.get("part_no") or "").strip() or (work_order["part_no"] if work_order else None) or trace.get("part_no")
    if not part_no:
        raise HTTPException(status_code=422, detail="請指定料號（part_no），或選一張主檔內的工單")
    if work_order and form.get("part_no") and form["part_no"].strip() != work_order["part_no"]:
        raise HTTPException(status_code=422, detail=f"工單 {work_order_no} 的料號是 {work_order['part_no']}，與指定的 {form['part_no']} 不符")

    recipe = recipes.get_active_recipe(part_no)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"料號「{part_no}」沒有啟用中的檢驗配方")

    missing = [slot for slot in recipe["slots"] if not isinstance(form.get(slot), UploadFile)]
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少圖片：{missing}（這個配方需要的圖片槽：{recipe['slots']}）")
    images = {slot: await form[slot].read() for slot in recipe["slots"]}

    # 追溯資訊：工單在主檔時，料號與批號沒填就自動帶入
    if work_order:
        trace["work_order"] = work_order_no
        trace.setdefault("part_no", work_order["part_no"])
        if work_order.get("lot_no"):
            trace.setdefault("lot_no", work_order["lot_no"])
    else:
        trace.setdefault("part_no", part_no)
        if work_order_no:
            trace["work_order"] = work_order_no

    return await run_in_threadpool(recipes.run_recipe, recipe, images)


@router.get("/runs")
def list_runs(part_no: str | None = None, work_order: str | None = None, verdict: str | None = None,
              date_from: str | None = None, date_to: str | None = None, limit: int = 200,
              since_id: int | None = None, _: Principal = Depends(_read)):
    """`since_id`：只回 id 較大的 run（升冪），給 ERP 增量輪詢。"""
    return recipes.list_runs(part_no, work_order, verdict, date_from, date_to, limit, since_id)


@router.get("/runs/{run_id}")
def get_run(run_id: int, _: Principal = Depends(_read)):
    run = recipes.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"找不到 run id={run_id}")
    return run

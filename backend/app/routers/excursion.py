"""温度异常接口：维护温度异常事件与可配置判定规则。

覆盖受理事件、提交处置、忽略事件等动作，以及按异常类型维护
「超限时长上限 / 最高温度上限」的判定规则。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.excursion import ExcursionService

router = APIRouter(prefix="/api/excursion", tags=["温度异常"])

service = ExcursionService()

LIST_FIELDS = ["事件编号", "关联运单", "异常类型", "超限时长", "最高温度", "发生时间", "处置人"]
STATUSES = ["待处置", "处置中", "已闭环", "已忽略"]


# 判定规则接口放在 /{entry_id} 之前，避免「rules」被当成事件编号匹配
@router.get("/rules")
def list_rules() -> dict[str, Any]:
    """读取按异常类型配置的判定规则；尚未配置的类型不会出现，页面按缺失口径提示。"""
    items = service.list_rules()
    return {"items": items, "total": len(items)}


@router.put("/rules/{abnormal_type}", response_model=ActionResult)
def upsert_rule(abnormal_type: str, payload: EntryPayload) -> ActionResult:
    """新增或刷新一个异常类型的判定规则；填写无效时说明原因，并保留原有规则继续判定。"""
    values = payload.values
    rule, message = service.upsert_rule(
        abnormal_type,
        values.get("超限时长上限"),
        values.get("最高温度上限"),
    )
    if rule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=rule)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按事件编号检索"),
    status: str | None = Query(default=None, description="待处置、处置中、已闭环、已忽略"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按事件编号与状态过滤温度异常列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出温度异常清单：返回当前过滤条件下的全量数据（含最新判定结论）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "excursion", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条温度异常事件明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"温度异常事件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条温度异常事件，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="温度异常事件已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条温度异常事件执行受理事件、提交处置、忽略事件；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.inspection_task import InspectionTask
from app.models.mobile_dispatch_item import MobileDispatchItem
from app.models.work_order import WorkOrder
from app.models.user_account import UserAccount
from app.schemas.work_order import (
    ResolveWorkOrderFromTopologyRequest,
    ResolveWorkOrderFromTopologyResponse,
    WorkOrderOut,
    WorkOrderSummaryOut,
    WorkOrderUpsert,
)
from app.services.auth import get_current_user, require_roles
from app.services.text_normalize import normalize_text
from app.services.work_order_flow import resolve_work_order_from_topology


router = APIRouter()


def _inspection_count_map(db: Session, work_order_ids: list[int]) -> dict[int, int]:
    if not work_order_ids:
        return {}
    rows = db.execute(
        select(InspectionTask.source_work_order_id, func.count())
        .where(InspectionTask.source_work_order_id.in_(set(work_order_ids)))
        .group_by(InspectionTask.source_work_order_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0] is not None}


def _dispatch_count_map(db: Session, work_order_ids: list[int]) -> dict[int, int]:
    if not work_order_ids:
        return {}
    rows = db.execute(
        select(MobileDispatchItem.source_work_order_id, func.count())
        .where(MobileDispatchItem.source_work_order_id.in_(set(work_order_ids)))
        .group_by(MobileDispatchItem.source_work_order_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0] is not None}


def _to_out(row: WorkOrder, linked_inspection_count: int = 0, linked_dispatch_count: int = 0) -> WorkOrderOut:
    return WorkOrderOut(
        id=row.id,
        title=normalize_text(row.title),
        order_type=row.order_type,
        status=row.status,
        priority=row.priority,
        area_name=normalize_text(row.area_name),
        source_type=row.source_type,
        source_alert_id=row.source_alert_id,
        asset_device_id=row.asset_device_id,
        topology_node_key=normalize_text(row.topology_node_key),
        topology_edge_id=row.topology_edge_id,
        verification_status=row.verification_status,
        verified_by=normalize_text(row.verified_by),
        verified_at=row.verified_at,
        closed_by=normalize_text(row.closed_by),
        close_reason=normalize_text(row.close_reason),
        topology_review_payload=normalize_text(row.topology_review_payload),
        assignee_username=normalize_text(row.assignee_username),
        description=normalize_text(row.description),
        resolution_note=normalize_text(row.resolution_note),
        linked_inspection_count=linked_inspection_count,
        linked_dispatch_count=linked_dispatch_count,
        due_at=row.due_at,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary", response_model=WorkOrderSummaryOut)
def summary(db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)) -> WorkOrderSummaryOut:
    rows = db.scalars(select(WorkOrder).order_by(WorkOrder.updated_at.desc())).all()
    inspection_count_map = _inspection_count_map(db, [row.id for row in rows])
    dispatch_count_map = _dispatch_count_map(db, [row.id for row in rows])
    now = datetime.utcnow()
    return WorkOrderSummaryOut(
        total_count=len(rows),
        open_count=sum(1 for item in rows if item.status == "open"),
        in_progress_count=sum(1 for item in rows if item.status == "in_progress"),
        resolved_count=sum(1 for item in rows if item.status == "resolved"),
        overdue_count=sum(1 for item in rows if item.due_at and item.due_at < now and item.status != "resolved"),
        recent_orders=[_to_out(item, inspection_count_map.get(item.id, 0), dispatch_count_map.get(item.id, 0)) for item in rows[:8]],
    )


@router.get("/items", response_model=list[WorkOrderOut])
def list_items(
    db: Session = Depends(get_db),
    q: str = Query(default=""),
    status: str = Query(default=""),
    priority: str = Query(default=""),
    _: UserAccount = Depends(get_current_user),
) -> list[WorkOrderOut]:
    stmt = select(WorkOrder).order_by(WorkOrder.updated_at.desc(), WorkOrder.id.desc())
    if q:
      like = f"%{q.strip()}%"
      stmt = stmt.where(
          WorkOrder.title.ilike(like)
          | WorkOrder.area_name.ilike(like)
          | WorkOrder.assignee_username.ilike(like)
          | WorkOrder.description.ilike(like)
      )
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if priority:
        stmt = stmt.where(WorkOrder.priority == priority)
    rows = db.scalars(stmt).all()
    inspection_count_map = _inspection_count_map(db, [row.id for row in rows])
    dispatch_count_map = _dispatch_count_map(db, [row.id for row in rows])
    return [_to_out(row, inspection_count_map.get(row.id, 0), dispatch_count_map.get(row.id, 0)) for row in rows]


@router.post("/items", response_model=WorkOrderOut)
def create_item(
    payload: WorkOrderUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> WorkOrderOut:
    row = WorkOrder(**payload.model_dump())
    if row.status == "resolved":
        row.resolved_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row, 0, 0)


@router.put("/items/{item_id}", response_model=WorkOrderOut)
def update_item(
    item_id: int,
    payload: WorkOrderUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> WorkOrderOut:
    row = db.get(WorkOrder, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="work_order_not_found")
    previous_status = row.status
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    if previous_status != "resolved" and row.status == "resolved":
        row.resolved_at = datetime.utcnow()
    if row.status != "resolved":
        row.resolved_at = None
    db.commit()
    db.refresh(row)
    return _to_out(row, _inspection_count_map(db, [row.id]).get(row.id, 0), _dispatch_count_map(db, [row.id]).get(row.id, 0))


@router.post("/{item_id}/resolve-from-topology", response_model=ResolveWorkOrderFromTopologyResponse)
def resolve_from_topology(
    item_id: int,
    payload: ResolveWorkOrderFromTopologyRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> dict:
    return resolve_work_order_from_topology(
        db,
        item_id,
        payload or ResolveWorkOrderFromTopologyRequest(),
        operator_username=current_user.username,
    )


@router.post("/{item_id}/create-inspection")
def create_inspection_from_work_order(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    row = db.get(WorkOrder, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="work_order_not_found")

    existing = db.scalar(
        select(InspectionTask).where(InspectionTask.source_work_order_id == row.id).order_by(InspectionTask.id.desc())
    )
    if existing:
        return {
            "ok": True,
            "created": False,
            "inspection_task_id": existing.id,
            "inspection_task_title": normalize_text(existing.title),
        }

    task = InspectionTask(
        title=f"{normalize_text(row.title)} 巡检复核",
        plan_name="工单复核",
        status="scheduled",
        area_name=normalize_text(row.area_name),
        target_type="work_order_followup",
        source_work_order_id=row.id,
        owner_username=normalize_text(row.assignee_username) or current_user.username,
        result_summary="",
        notes=normalize_text(row.description or row.resolution_note),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "ok": True,
        "created": True,
        "inspection_task_id": task.id,
        "inspection_task_title": normalize_text(task.title),
    }

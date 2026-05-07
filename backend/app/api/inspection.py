from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.inspection_task import InspectionTask
from app.models.mobile_dispatch_item import MobileDispatchItem
from app.models.user_account import UserAccount
from app.schemas.inspection_task import InspectionTaskOut, InspectionTaskSummaryOut, InspectionTaskUpsert
from app.services.auth import get_current_user, require_roles
from app.services.text_normalize import normalize_text


router = APIRouter()


def _dispatch_count_map(db: Session, inspection_ids: list[int]) -> dict[int, int]:
    if not inspection_ids:
        return {}
    rows = db.execute(
        select(MobileDispatchItem.source_inspection_id, func.count())
        .where(MobileDispatchItem.source_inspection_id.in_(set(inspection_ids)))
        .group_by(MobileDispatchItem.source_inspection_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0] is not None}


def _to_out(row: InspectionTask, linked_dispatch_count: int = 0) -> InspectionTaskOut:
    return InspectionTaskOut(
        id=row.id,
        title=normalize_text(row.title),
        plan_name=normalize_text(row.plan_name),
        status=row.status,
        area_name=normalize_text(row.area_name),
        target_type=row.target_type,
        source_work_order_id=row.source_work_order_id,
        owner_username=normalize_text(row.owner_username),
        scheduled_for=row.scheduled_for,
        completed_at=row.completed_at,
        result_summary=normalize_text(row.result_summary),
        notes=normalize_text(row.notes),
        linked_dispatch_count=linked_dispatch_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary", response_model=InspectionTaskSummaryOut)
def summary(db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)) -> InspectionTaskSummaryOut:
    rows = db.scalars(select(InspectionTask).order_by(InspectionTask.updated_at.desc())).all()
    dispatch_count_map = _dispatch_count_map(db, [row.id for row in rows])
    now = datetime.utcnow()
    return InspectionTaskSummaryOut(
        total_count=len(rows),
        scheduled_count=sum(1 for item in rows if item.status == "scheduled"),
        in_progress_count=sum(1 for item in rows if item.status == "in_progress"),
        completed_count=sum(1 for item in rows if item.status == "completed"),
        overdue_count=sum(1 for item in rows if item.scheduled_for and item.scheduled_for < now and item.status != "completed"),
        recent_tasks=[_to_out(item, dispatch_count_map.get(item.id, 0)) for item in rows[:8]],
    )


@router.get("/items", response_model=list[InspectionTaskOut])
def list_items(
    db: Session = Depends(get_db),
    q: str = Query(default=""),
    status: str = Query(default=""),
    _: UserAccount = Depends(get_current_user),
) -> list[InspectionTaskOut]:
    stmt = select(InspectionTask).order_by(InspectionTask.updated_at.desc(), InspectionTask.id.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            InspectionTask.title.ilike(like)
            | InspectionTask.plan_name.ilike(like)
            | InspectionTask.area_name.ilike(like)
            | InspectionTask.owner_username.ilike(like)
        )
    if status:
        stmt = stmt.where(InspectionTask.status == status)
    rows = db.scalars(stmt).all()
    dispatch_count_map = _dispatch_count_map(db, [row.id for row in rows])
    return [_to_out(row, dispatch_count_map.get(row.id, 0)) for row in rows]


@router.post("/items", response_model=InspectionTaskOut)
def create_item(
    payload: InspectionTaskUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> InspectionTaskOut:
    row = InspectionTask(**payload.model_dump())
    if row.status == "completed":
        row.completed_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row, 0)


@router.put("/items/{item_id}", response_model=InspectionTaskOut)
def update_item(
    item_id: int,
    payload: InspectionTaskUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> InspectionTaskOut:
    row = db.get(InspectionTask, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="inspection_task_not_found")
    previous_status = row.status
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    if previous_status != "completed" and row.status == "completed":
        row.completed_at = datetime.utcnow()
    if row.status != "completed":
        row.completed_at = None
    db.commit()
    db.refresh(row)
    return _to_out(row, _dispatch_count_map(db, [row.id]).get(row.id, 0))

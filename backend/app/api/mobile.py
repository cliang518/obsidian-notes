from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.asset import AssetDevice
from app.models.alert import OpsAlert
from app.models.inspection_task import InspectionTask
from app.models.mobile_channel import MobileChannelRegistration
from app.models.mobile_dispatch_item import MobileDispatchItem
from app.models.user_account import UserAccount
from app.models.work_order import WorkOrder
from app.schemas.mobile_channel import MobileChannelOut, MobileChannelUpsert
from app.schemas.mobile_dispatch import MobileDispatchCreate, MobileDispatchItemOut, MobileDispatchUpdate
from app.services.auth import get_current_user, require_roles
from app.services.platform_capabilities import mobile_workspace_summary
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_out(row: MobileChannelRegistration) -> MobileChannelOut:
    return MobileChannelOut(
        id=row.id,
        channel_key=row.channel_key,
        display_name=normalize_text(row.display_name),
        channel_type=row.channel_type,
        target_platform=normalize_text(row.target_platform),
        entry_mode=row.entry_mode,
        deep_link_scheme=row.deep_link_scheme,
        auth_mode=row.auth_mode,
        scope=row.scope,
        enabled=row.enabled,
        mobile_first=row.mobile_first,
        status=row.status,
        notes=normalize_text(row.notes),
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _dispatch_to_out(row: MobileDispatchItem) -> MobileDispatchItemOut:
    return MobileDispatchItemOut(
        id=row.id,
        dispatch_type=row.dispatch_type,
        status=row.status,
        priority=row.priority,
        title=normalize_text(row.title),
        area_name=normalize_text(row.area_name),
        device_label=normalize_text(row.device_label),
        source_alert_id=row.source_alert_id,
        source_work_order_id=row.source_work_order_id,
        source_inspection_id=row.source_inspection_id,
        assignee_username=normalize_text(row.assignee_username),
        mobile_channel_key=row.mobile_channel_key,
        summary=normalize_text(row.summary),
        latest_note=normalize_text(row.latest_note),
        queued_at=row.queued_at,
        acknowledged_at=row.acknowledged_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _device_label(db: Session, asset_device_id: int | None) -> str:
    if not asset_device_id:
        return ""
    row = db.get(AssetDevice, asset_device_id)
    if not row:
        return ""
    return normalize_text(row.hostname or row.management_ip or "")


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)) -> dict:
    rows = db.scalars(select(MobileChannelRegistration).order_by(MobileChannelRegistration.display_name)).all()
    base = mobile_workspace_summary()
    enabled_count = sum(1 for row in rows if row.enabled)
    mobile_first_count = sum(1 for row in rows if row.mobile_first)
    base.update(
        {
            "channel_count": len(rows),
            "enabled_count": enabled_count,
            "mobile_first_count": mobile_first_count,
            "channels": [_to_out(row).model_dump() for row in rows],
        }
    )
    return base


@router.get("/dispatch-board")
def dispatch_board(db: Session = Depends(get_db), current_user: UserAccount = Depends(get_current_user)) -> dict:
    open_alerts = db.scalars(
        select(OpsAlert).where(OpsAlert.status == "open").order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc()).limit(8)
    ).all()
    open_orders = db.scalars(
        select(WorkOrder)
        .where(WorkOrder.status.in_(["open", "in_progress"]))
        .order_by(WorkOrder.updated_at.desc(), WorkOrder.id.desc())
        .limit(8)
    ).all()
    open_inspections = db.scalars(
        select(InspectionTask)
        .where(InspectionTask.status.in_(["scheduled", "in_progress"]))
        .order_by(InspectionTask.updated_at.desc(), InspectionTask.id.desc())
        .limit(8)
    ).all()
    dispatch_items = db.scalars(
        select(MobileDispatchItem)
        .where(MobileDispatchItem.status.in_(["queued", "acknowledged", "in_progress"]))
        .order_by(MobileDispatchItem.updated_at.desc(), MobileDispatchItem.id.desc())
        .limit(10)
    ).all()

    return {
        "viewer": {
            "username": current_user.username,
            "display_name": normalize_text(current_user.display_name),
            "role": current_user.role,
        },
        "counts": {
            "open_alerts": db.query(OpsAlert).filter(OpsAlert.status == "open").count(),
            "open_work_orders": db.query(WorkOrder).filter(WorkOrder.status.in_(["open", "in_progress"])).count(),
            "open_inspections": db.query(InspectionTask).filter(InspectionTask.status.in_(["scheduled", "in_progress"])).count(),
            "pending_accounts": db.query(UserAccount).filter(UserAccount.status == "pending").count(),
            "dispatch_items": db.query(MobileDispatchItem).filter(MobileDispatchItem.status.in_(["queued", "acknowledged", "in_progress"])).count(),
        },
        "alerts": [
            {
                "id": row.id,
                "title": normalize_text(row.title),
                "severity": row.severity,
                "alert_type": row.alert_type,
                "last_seen_at": row.last_seen_at,
            }
            for row in open_alerts
        ],
        "work_orders": [
            {
                "id": row.id,
                "title": normalize_text(row.title),
                "status": row.status,
                "priority": row.priority,
                "area_name": normalize_text(row.area_name),
                "updated_at": row.updated_at,
            }
            for row in open_orders
        ],
        "inspections": [
            {
                "id": row.id,
                "title": normalize_text(row.title),
                "status": row.status,
                "plan_name": normalize_text(row.plan_name),
                "area_name": normalize_text(row.area_name),
                "updated_at": row.updated_at,
            }
            for row in open_inspections
        ],
        "dispatch_items": [_dispatch_to_out(row).model_dump() for row in dispatch_items],
    }


@router.get("/dispatch-summary")
def dispatch_summary(
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
) -> dict:
    type_rows = db.execute(
        select(MobileDispatchItem.dispatch_type, func.count())
        .group_by(MobileDispatchItem.dispatch_type)
        .order_by(func.count().desc())
    ).all()
    status_rows = db.execute(
        select(MobileDispatchItem.status, func.count())
        .group_by(MobileDispatchItem.status)
        .order_by(func.count().desc())
    ).all()
    recent_rows = db.scalars(
        select(MobileDispatchItem).order_by(MobileDispatchItem.updated_at.desc(), MobileDispatchItem.id.desc()).limit(10)
    ).all()
    return {
        "total_count": db.query(MobileDispatchItem).count(),
        "active_count": db.query(MobileDispatchItem)
        .filter(MobileDispatchItem.status.in_(["queued", "acknowledged", "in_progress"]))
        .count(),
        "completed_count": db.query(MobileDispatchItem).filter(MobileDispatchItem.status == "completed").count(),
        "dispatch_type_breakdown": [
            {"dispatch_type": row[0] or "unknown", "count": row[1]} for row in type_rows
        ],
        "dispatch_status_breakdown": [
            {"status": row[0] or "unknown", "count": row[1]} for row in status_rows
        ],
        "recent_dispatch_items": [_dispatch_to_out(row).model_dump() for row in recent_rows],
    }


@router.get("/channels", response_model=list[MobileChannelOut])
def list_channels(db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)) -> list[MobileChannelOut]:
    rows = db.scalars(select(MobileChannelRegistration).order_by(MobileChannelRegistration.display_name)).all()
    return [_to_out(row) for row in rows]


@router.post("/channels", response_model=MobileChannelOut)
def create_channel(
    payload: MobileChannelUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> MobileChannelOut:
    existing = db.scalar(select(MobileChannelRegistration).where(MobileChannelRegistration.channel_key == payload.channel_key))
    if existing:
        raise HTTPException(status_code=409, detail="channel_key_exists")

    row = MobileChannelRegistration(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/channels/{channel_id}", response_model=MobileChannelOut)
def update_channel(
    channel_id: int,
    payload: MobileChannelUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> MobileChannelOut:
    row = db.get(MobileChannelRegistration, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail="channel_not_found")

    conflict = db.scalar(
        select(MobileChannelRegistration).where(
            MobileChannelRegistration.channel_key == payload.channel_key,
            MobileChannelRegistration.id != channel_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="channel_key_exists")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/dispatch-items", response_model=list[MobileDispatchItemOut])
def list_dispatch_items(
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
) -> list[MobileDispatchItemOut]:
    rows = db.scalars(select(MobileDispatchItem).order_by(MobileDispatchItem.updated_at.desc(), MobileDispatchItem.id.desc())).all()
    return [_dispatch_to_out(row) for row in rows]


@router.post("/dispatch-items/from-alert/{alert_id}", response_model=MobileDispatchItemOut)
def create_dispatch_from_alert(
    alert_id: int,
    payload: MobileDispatchCreate,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> MobileDispatchItemOut:
    alert = db.get(OpsAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert_not_found")

    existing = db.scalar(select(MobileDispatchItem).where(MobileDispatchItem.source_alert_id == alert.id))
    if existing:
        return _dispatch_to_out(existing)

    row = MobileDispatchItem(
        dispatch_type="alert",
        status="queued",
        priority="critical" if alert.severity == "critical" else "high" if alert.severity == "warning" else "medium",
        title=normalize_text(alert.title),
        area_name="",
        device_label=_device_label(db, alert.asset_device_id),
        source_alert_id=alert.id,
        assignee_username=payload.assignee_username.strip(),
        mobile_channel_key=payload.mobile_channel_key.strip(),
        summary=normalize_text(alert.message or alert.evidence_summary or alert.title),
        latest_note=payload.latest_note.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dispatch_to_out(row)


@router.post("/dispatch-items/from-work-order/{work_order_id}", response_model=MobileDispatchItemOut)
def create_dispatch_from_work_order(
    work_order_id: int,
    payload: MobileDispatchCreate,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> MobileDispatchItemOut:
    order = db.get(WorkOrder, work_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="work_order_not_found")

    existing = db.scalar(select(MobileDispatchItem).where(MobileDispatchItem.source_work_order_id == order.id))
    if existing:
        return _dispatch_to_out(existing)

    row = MobileDispatchItem(
        dispatch_type="work_order",
        status="queued",
        priority=order.priority,
        title=normalize_text(order.title),
        area_name=normalize_text(order.area_name),
        device_label=_device_label(db, order.asset_device_id),
        source_work_order_id=order.id,
        assignee_username=payload.assignee_username.strip() or normalize_text(order.assignee_username),
        mobile_channel_key=payload.mobile_channel_key.strip(),
        summary=normalize_text(order.description or order.title),
        latest_note=payload.latest_note.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dispatch_to_out(row)


@router.post("/dispatch-items/from-inspection/{inspection_id}", response_model=MobileDispatchItemOut)
def create_dispatch_from_inspection(
    inspection_id: int,
    payload: MobileDispatchCreate,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> MobileDispatchItemOut:
    task = db.get(InspectionTask, inspection_id)
    if not task:
        raise HTTPException(status_code=404, detail="inspection_not_found")

    existing = db.scalar(select(MobileDispatchItem).where(MobileDispatchItem.source_inspection_id == task.id))
    if existing:
        return _dispatch_to_out(existing)

    row = MobileDispatchItem(
        dispatch_type="inspection",
        status="queued",
        priority="medium",
        title=normalize_text(task.title),
        area_name=normalize_text(task.area_name),
        device_label="",
        source_inspection_id=task.id,
        assignee_username=payload.assignee_username.strip() or normalize_text(task.owner_username),
        mobile_channel_key=payload.mobile_channel_key.strip(),
        summary=normalize_text(task.notes or task.result_summary or task.title),
        latest_note=payload.latest_note.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dispatch_to_out(row)


@router.put("/dispatch-items/{dispatch_id}", response_model=MobileDispatchItemOut)
def update_dispatch_item(
    dispatch_id: int,
    payload: MobileDispatchUpdate,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager", "technician")),
) -> MobileDispatchItemOut:
    row = db.get(MobileDispatchItem, dispatch_id)
    if not row:
        raise HTTPException(status_code=404, detail="dispatch_item_not_found")

    row.status = payload.status
    row.assignee_username = payload.assignee_username.strip()
    row.mobile_channel_key = payload.mobile_channel_key.strip()
    row.latest_note = payload.latest_note.strip()
    now = datetime.utcnow()
    if payload.status in {"acknowledged", "in_progress"} and row.acknowledged_at is None:
        row.acknowledged_at = now
    if payload.status == "completed":
        row.completed_at = now
    elif payload.status in {"queued", "acknowledged", "in_progress"}:
        row.completed_at = None

    if row.source_work_order_id:
        order = db.get(WorkOrder, row.source_work_order_id)
        if order:
            if payload.status in {"acknowledged", "in_progress"} and order.status == "open":
                order.status = "in_progress"
            if payload.assignee_username.strip():
                order.assignee_username = payload.assignee_username.strip()

    if row.source_inspection_id:
        task = db.get(InspectionTask, row.source_inspection_id)
        if task:
            if payload.assignee_username.strip():
                task.owner_username = payload.assignee_username.strip()
            if payload.status in {"acknowledged", "in_progress"} and task.status == "scheduled":
                task.status = "in_progress"
            if payload.status == "completed":
                task.status = "completed"
                task.completed_at = now
                if payload.latest_note.strip() and not task.result_summary:
                    task.result_summary = payload.latest_note.strip()

    db.commit()
    db.refresh(row)
    return _dispatch_to_out(row)

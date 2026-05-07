from collections import Counter
import csv
from datetime import datetime, timedelta
import io

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import OpsAlert
from app.models.asset import AssetArea, AssetDevice
from app.models.mobile_dispatch_item import MobileDispatchItem
from app.models.user_account import UserAccount
from app.models.work_order import WorkOrder
from app.schemas.alerts import OpsAlertOut
from app.schemas.work_order import AlertCreateWorkOrderRequest, WorkOrderFromAlertResponse
from app.services.alert_guard_settings import get_alert_guard_settings, update_alert_guard_settings
from app.services.alert_diagnostics import build_alert_storm_guard
from app.services.auth import get_current_user, require_roles
from app.services.text_normalize import normalize_text
from app.services.work_order_flow import create_work_order_from_alert as create_work_order_from_alert_service


router = APIRouter()


def _status_label(value: str | None) -> str:
    return {
        "open": "待处理",
        "acknowledged": "已确认",
        "resolved": "已恢复",
    }.get(str(value or "").strip().lower(), "待补状态")


def _severity_label(value: str | None) -> str:
    return {
        "critical": "严重",
        "warning": "警告",
        "info": "提示",
    }.get(str(value or "").strip().lower(), "待补级别")


def _source_label(value: str | None) -> str:
    return {
        "legacy_ops": "旧系统桥接",
        "jvss": "主平台 200",
        "tg_cos": "TG/COS 平台",
        "gateway": "网关",
        "hikvision_nvr": "海康录像机",
        "hikvision_decoder": "海康解码器",
        "control_platform_new": "风控新平台",
        "control_platform_legacy": "风控老平台",
        "control_platform_electrical": "电控平台",
        "cad_upload": "CAD 导入",
        "alert_bridge": "告警桥接",
    }.get(str(value or "").strip(), "待补来源")


def _alert_type_label(value: str | None) -> str:
    return {
        "network_flap": "网络抖动",
        "device_flapping": "网络抖动待观察",
        "video_loss": "视频丢失",
        "device_video_abnormal": "视频取流异常",
        "offline": "设备离线",
        "device_offline": "设备离线",
        "reachable_error": "可达异常",
        "observer_path_failure": "观测链路异常",
        "network_segment_outage": "区域网络中断",
        "device_fault": "设备故障",
        "legacy_alert": "历史告警",
        "global_outage_watch": "大面积异常观察",
        "global_outage_suppressed": "大面积异常抑制",
        "stream_probe_failed": "取流探测异常",
        "switch_probe_failed": "交换机探测异常",
        "platform_sync_abnormal": "平台同步异常",
    }.get(str(value or "").strip(), "待补类型")


def _attribution_label(value: str | None) -> str:
    return {
        "legacy_bridge": "旧系统桥接",
        "network_flap_watch": "网络抖动观察",
        "manual_review": "人工复核",
        "topology_inferred": "拓扑归因",
        "device_unreachable": "设备不可达",
        "switch_probe": "交换机探测归因",
        "observer_probe": "观测链路归因",
        "stream_probe": "取流探测归因",
        "global_outage_watch": "大面积异常观察",
        "global_outage_suppressed": "大面积异常抑制",
    }.get(str(value or "").strip(), "待补归因")


@router.get("/guard-settings")
def guard_settings(_: UserAccount = Depends(get_current_user)) -> dict:
    return get_alert_guard_settings()


@router.put("/guard-settings")
def update_guard_settings(
    payload: dict = Body(...),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    return update_alert_guard_settings(payload)


def _device_context(db: Session, device_ids: list[int]) -> dict[int, dict]:
    if not device_ids:
        return {}
    device_rows = db.scalars(select(AssetDevice).where(AssetDevice.id.in_(set(device_ids)))).all()
    area_ids = [row.area_id for row in device_rows if row.area_id]
    area_map = {}
    if area_ids:
        area_map = {
            row.id: row
            for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(set(area_ids)))).all()
        }
    return {
        row.id: {
            "label": normalize_text(row.hostname or row.management_ip),
            "management_ip": row.management_ip or "",
            "device_type": row.device_type or "",
            "area_display_name": normalize_text(area_map[row.area_id].display_name) if row.area_id in area_map else "",
        }
        for row in device_rows
    }


def _work_order_context(db: Session, work_order_ids: list[int]) -> dict[int, WorkOrder]:
    if not work_order_ids:
        return {}
    rows = db.scalars(select(WorkOrder).where(WorkOrder.id.in_(set(work_order_ids)))).all()
    return {row.id: row for row in rows}


def _dispatch_count_map(db: Session, alert_ids: list[int]) -> dict[int, int]:
    if not alert_ids:
        return {}
    rows = db.execute(
        select(MobileDispatchItem.source_alert_id, func.count())
        .where(MobileDispatchItem.source_alert_id.in_(set(alert_ids)))
        .group_by(MobileDispatchItem.source_alert_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0] is not None}


def _apply_alert_filters(
    stmt,
    *,
    status: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    attribution_type: str | None = None,
    q: str = "",
):
    if status:
        stmt = stmt.where(OpsAlert.status == status)
    if alert_type:
        stmt = stmt.where(OpsAlert.alert_type == alert_type)
    if severity:
        stmt = stmt.where(OpsAlert.severity == severity)
    if source_type:
        stmt = stmt.where(OpsAlert.source_type == source_type)
    if attribution_type:
        stmt = stmt.where(OpsAlert.attribution_type == attribution_type)

    keyword = q.strip()
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            OpsAlert.title.ilike(like)
            | OpsAlert.message.ilike(like)
            | OpsAlert.evidence_summary.ilike(like)
        )
    return stmt


def _to_alert_out_list(db: Session, rows: list[OpsAlert]) -> list[OpsAlertOut]:
    device_context = _device_context(db, [row.asset_device_id for row in rows if row.asset_device_id])
    work_order_context = _work_order_context(db, [row.linked_work_order_id for row in rows if row.linked_work_order_id])
    dispatch_count_map = _dispatch_count_map(db, [row.id for row in rows])
    return [
        OpsAlertOut(
            id=row.id,
            source_type=row.source_type,
            source_event_key=row.source_event_key,
            alert_type=row.alert_type,
            severity=row.severity,
            status=row.status,
            title=normalize_text(row.title),
            message=normalize_text(row.message),
            asset_device_id=row.asset_device_id,
            impacted_scope=row.impacted_scope,
            attribution_type=row.attribution_type,
            occurrence_count=row.occurrence_count,
            triggered_at=row.triggered_at,
            last_seen_at=row.last_seen_at,
            resolved_at=row.resolved_at,
            evidence_summary=normalize_text(row.evidence_summary),
            device_label=device_context.get(row.asset_device_id, {}).get("label", ""),
            management_ip=device_context.get(row.asset_device_id, {}).get("management_ip", ""),
            area_display_name=device_context.get(row.asset_device_id, {}).get("area_display_name", ""),
            linked_work_order_id=row.linked_work_order_id,
            linked_work_order_title=normalize_text(work_order_context.get(row.linked_work_order_id).title)
            if row.linked_work_order_id in work_order_context
            else "",
            linked_dispatch_count=dispatch_count_map.get(row.id, 0),
        )
        for row in rows
    ]


@router.get("")
def list_alerts(
    status: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    attribution_type: str | None = Query(default=None),
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    sort_by: str = Query(default="last_seen_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
) -> dict:
    base_stmt = _apply_alert_filters(
        select(OpsAlert),
        status=status,
        alert_type=alert_type,
        severity=severity,
        source_type=source_type,
        attribution_type=attribution_type,
        q=q,
    )
    total_count = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    offset = (page - 1) * page_size
    sort_map = {
        "id": OpsAlert.id,
        "last_seen_at": OpsAlert.last_seen_at,
        "severity": OpsAlert.severity,
        "status": OpsAlert.status,
    }
    sort_column = sort_map.get(sort_by, OpsAlert.last_seen_at)
    order_expr = sort_column if sort_order == "asc" else desc(sort_column)

    rows = db.scalars(
        base_stmt.order_by(order_expr, OpsAlert.id.desc()).offset(offset).limit(page_size)
    ).all()
    items = _to_alert_out_list(db, rows)
    page_count = max(1, (total_count + page_size - 1) // page_size)
    return {
        "items": [item.model_dump() for item in items],
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
    }


@router.get("/export.csv")
def export_alerts_csv(
    status: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    attribution_type: str | None = Query(default=None),
    q: str = Query(default=""),
    max_rows: int = Query(default=10000, ge=1, le=50000),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
) -> Response:
    stmt = _apply_alert_filters(
        select(OpsAlert),
        status=status,
        alert_type=alert_type,
        severity=severity,
        source_type=source_type,
        attribution_type=attribution_type,
        q=q,
    )
    rows = db.scalars(stmt.order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc()).limit(max_rows)).all()
    items = _to_alert_out_list(db, rows)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "告警编号",
            "状态",
            "级别",
            "来源",
            "类型",
            "归因",
            "标题",
            "说明",
            "设备名称",
            "管理IP",
            "区域",
            "最后出现时间",
            "累计次数",
            "关联工单",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.id,
                _status_label(item.status),
                _severity_label(item.severity),
                _source_label(item.source_type),
                _alert_type_label(item.alert_type),
                _attribution_label(item.attribution_type),
                item.title,
                item.message,
                item.device_label,
                item.management_ip,
                item.area_display_name,
                item.last_seen_at.isoformat() if item.last_seen_at else "",
                item.occurrence_count,
                item.linked_work_order_id or "",
            ]
        )

    csv_text = buffer.getvalue()
    filename = f"告警中心-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/bulk-action")
def bulk_action(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"acknowledge", "resolve", "delete"}:
        raise HTTPException(status_code=400, detail="invalid_action")

    ids_raw = payload.get("ids") or []
    try:
        ids = sorted({int(x) for x in ids_raw})
    except Exception as error:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=400, detail="invalid_ids") from error

    if not ids:
        raise HTTPException(status_code=400, detail="ids_required")

    rows = db.scalars(select(OpsAlert).where(OpsAlert.id.in_(ids))).all()
    skipped = max(0, len(ids) - len(rows))
    affected = 0
    now = datetime.utcnow()

    for row in rows:
        if action == "acknowledge":
            if row.status == "resolved":
                skipped += 1
                continue
            if row.status != "acknowledged":
                row.status = "acknowledged"
                row.last_seen_at = row.last_seen_at or now
                row.resolved_at = None
                affected += 1
            else:
                skipped += 1
            continue

        if action == "resolve":
            if row.status == "resolved":
                skipped += 1
                continue
            row.status = "resolved"
            row.resolved_at = now
            row.last_seen_at = row.last_seen_at or now
            affected += 1
            continue

        db.delete(row)
        affected += 1

    db.commit()
    return {
        "ok": True,
        "action": action,
        "requested": len(ids),
        "affected": affected,
        "skipped": skipped,
    }


@router.post("/cleanup")
def cleanup_alert_history(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
) -> dict:
    keep_days = int(payload.get("keep_days") or 30)
    status = str(payload.get("status") or "resolved").strip() or "resolved"
    dry_run = bool(payload.get("dry_run", False))

    keep_days = min(max(keep_days, 1), 3650)
    cutoff = datetime.utcnow() - timedelta(days=keep_days)

    ids = db.scalars(
        select(OpsAlert.id).where(OpsAlert.status == status, OpsAlert.updated_at < cutoff)
    ).all()
    if dry_run or not ids:
        return {
            "ok": True,
            "dry_run": dry_run,
            "status": status,
            "keep_days": keep_days,
            "deleted": 0,
            "matched": len(ids),
            "cutoff": cutoff.isoformat(),
        }

    db.execute(delete(OpsAlert).where(OpsAlert.id.in_(ids)))
    db.commit()
    return {
        "ok": True,
        "dry_run": False,
        "status": status,
        "keep_days": keep_days,
        "deleted": len(ids),
        "matched": len(ids),
        "cutoff": cutoff.isoformat(),
    }


@router.get("/summary")
def alert_summary(db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)) -> dict:
    storm_guard = build_alert_storm_guard(db)
    severity_rows = db.execute(
        select(OpsAlert.severity, func.count()).group_by(OpsAlert.severity).order_by(func.count().desc())
    ).all()
    type_rows = db.execute(
        select(OpsAlert.alert_type, func.count()).group_by(OpsAlert.alert_type).order_by(func.count().desc())
    ).all()
    status_rows = db.execute(
        select(OpsAlert.status, func.count()).group_by(OpsAlert.status).order_by(func.count().desc())
    ).all()
    source_rows = db.execute(
        select(OpsAlert.source_type, func.count()).group_by(OpsAlert.source_type).order_by(func.count().desc())
    ).all()
    attribution_rows = db.execute(
        select(OpsAlert.attribution_type, func.count())
        .group_by(OpsAlert.attribution_type)
        .order_by(func.count().desc())
    ).all()
    scope_rows = db.execute(
        select(OpsAlert.impacted_scope, func.count()).group_by(OpsAlert.impacted_scope).order_by(func.count().desc())
    ).all()

    open_count = db.scalar(select(func.count()).select_from(OpsAlert).where(OpsAlert.status == "open")) or 0
    resolved_count = db.scalar(select(func.count()).select_from(OpsAlert).where(OpsAlert.status == "resolved")) or 0
    open_critical_count = (
        db.scalar(
            select(func.count()).select_from(OpsAlert).where(
                OpsAlert.status == "open",
                OpsAlert.severity == "critical",
            )
        )
        or 0
    )
    flap_watch_count = (
        db.scalar(
            select(func.count()).select_from(OpsAlert).where(
                OpsAlert.attribution_type == "network_flap_watch",
                OpsAlert.status.in_(["open", "acknowledged"]),
            )
        )
        or 0
    )
    strict_unresolved_count = (
        db.scalar(
            select(func.count()).select_from(OpsAlert).where(
                OpsAlert.status == "open",
                OpsAlert.attribution_type != "network_flap_watch",
            )
        )
        or 0
    )

    latest = db.scalars(select(OpsAlert).order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc()).limit(12)).all()
    latest_open = db.scalars(
        select(OpsAlert)
        .where(OpsAlert.status == "open")
        .order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc())
        .limit(8)
    ).all()

    device_context = _device_context(
        db,
        [row.asset_device_id for row in latest if row.asset_device_id]
        + [row.asset_device_id for row in latest_open if row.asset_device_id],
    )
    work_order_context = _work_order_context(
        db,
        [row.linked_work_order_id for row in latest if row.linked_work_order_id]
        + [row.linked_work_order_id for row in latest_open if row.linked_work_order_id],
    )

    open_rows = db.scalars(
        select(OpsAlert).where(OpsAlert.status == "open").order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc())
    ).all()
    open_context = _device_context(db, [row.asset_device_id for row in open_rows if row.asset_device_id])

    area_counter = Counter()
    device_counter = Counter()
    source_open_counter = Counter()
    attribution_open_counter = Counter()
    for row in open_rows:
        source_open_counter[row.source_type or "unknown"] += 1
        attribution_open_counter[row.attribution_type or "unknown"] += 1
        ctx = open_context.get(row.asset_device_id or -1, {})
        if ctx.get("area_display_name"):
            area_counter[ctx["area_display_name"]] += 1
        if ctx.get("label"):
            device_counter[(ctx["label"], ctx.get("management_ip", ""), ctx.get("device_type", ""))] += 1

    def _alert_card(row: OpsAlert) -> dict:
        ctx = device_context.get(row.asset_device_id, {})
        work_order = work_order_context.get(row.linked_work_order_id)
        return {
            "id": row.id,
            "title": normalize_text(row.title),
            "severity": row.severity,
            "status": row.status,
            "alert_type": row.alert_type,
            "source_type": row.source_type,
            "attribution_type": row.attribution_type,
            "device_label": ctx.get("label", "-"),
            "management_ip": ctx.get("management_ip", ""),
            "device_type": ctx.get("device_type", ""),
            "area_display_name": ctx.get("area_display_name", ""),
            "last_seen_at": row.last_seen_at,
            "occurrence_count": row.occurrence_count,
            "linked_work_order_id": row.linked_work_order_id,
            "linked_work_order_title": normalize_text(work_order.title) if work_order else "",
        }

    return {
        "open_count": open_count,
        "resolved_count": resolved_count,
        "open_critical_count": open_critical_count,
        "flap_watch_count": flap_watch_count,
        "strict_unresolved_count": strict_unresolved_count,
        "severity_breakdown": [{"severity": row[0] or "unknown", "count": row[1]} for row in severity_rows],
        "type_breakdown": [{"alert_type": row[0] or "unknown", "count": row[1]} for row in type_rows],
        "status_breakdown": [{"status": row[0] or "unknown", "count": row[1]} for row in status_rows],
        "source_breakdown": [{"source_type": row[0] or "unknown", "count": row[1]} for row in source_rows],
        "attribution_breakdown": [
            {"attribution_type": row[0] or "unknown", "count": row[1]} for row in attribution_rows
        ],
        "scope_breakdown": [{"impacted_scope": row[0] or "unknown", "count": row[1]} for row in scope_rows],
        "open_source_breakdown": [
            {"source_type": key, "count": value} for key, value in source_open_counter.most_common(8)
        ],
        "open_attribution_breakdown": [
            {"attribution_type": key, "count": value} for key, value in attribution_open_counter.most_common(8)
        ],
        "top_open_areas": [{"area_display_name": key, "count": value} for key, value in area_counter.most_common(8)],
        "top_open_devices": [
            {"device_label": key[0], "management_ip": key[1], "device_type": key[2], "count": value}
            for key, value in device_counter.most_common(8)
        ],
        "latest_alerts": [_alert_card(row) for row in latest],
        "latest_open_alerts": [_alert_card(row) for row in latest_open],
        "storm_guard": storm_guard,
    }


@router.post("/{alert_id}/create-work-order", response_model=WorkOrderFromAlertResponse)
def create_work_order_from_alert(
    alert_id: int,
    payload: AlertCreateWorkOrderRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    return create_work_order_from_alert_service(
        db,
        alert_id,
        payload or AlertCreateWorkOrderRequest(),
        operator_username=current_user.username,
        operator_role=current_user.role,
    )

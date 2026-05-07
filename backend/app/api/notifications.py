import json
from datetime import datetime, timedelta
from urllib import error, request

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import OpsAlert
from app.models.notification_channel import NotificationChannelRegistration
from app.models.notification_delivery_log import NotificationDeliveryLog
from app.schemas.notification_channel import (
    NotificationChannelOut,
    NotificationChannelUpsert,
    NotificationDeliveryLogOut,
)
from app.services.alert_diagnostics import build_alert_storm_guard
from app.services.auth import get_current_user, require_roles
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_out(row: NotificationChannelRegistration) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=row.id,
        channel_key=row.channel_key,
        display_name=normalize_text(row.display_name),
        channel_type=row.channel_type,
        endpoint_url=row.endpoint_url,
        auth_mode=row.auth_mode,
        target_scope=row.target_scope,
        enabled=row.enabled,
        send_resolved=row.send_resolved,
        alert_cooldown_seconds=row.alert_cooldown_seconds,
        suppress_flap_watch=row.suppress_flap_watch,
        status=row.status,
        notes=normalize_text(row.notes),
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _log_to_out(
    row: NotificationDeliveryLog,
    channel_name: str,
) -> NotificationDeliveryLogOut:
    return NotificationDeliveryLogOut(
        id=row.id,
        channel_id=row.channel_id,
        channel_key=row.channel_key,
        channel_name=normalize_text(channel_name),
        channel_type=row.channel_type,
        event_type=row.event_type,
        title=normalize_text(row.title),
        message=normalize_text(row.message),
        ok=row.ok,
        status_code=row.status_code,
        response_detail=normalize_text(row.response_detail),
        created_at=row.created_at,
    )


def _create_delivery_log(
    db: Session,
    *,
    channel: NotificationChannelRegistration,
    title: str,
    message: str,
    ok: bool,
    detail: str,
    status_code: int | None = None,
    event_type: str = "notification_test",
) -> NotificationDeliveryLog:
    row = NotificationDeliveryLog(
        channel_id=channel.id,
        channel_key=channel.channel_key,
        channel_type=channel.channel_type,
        event_type=event_type,
        title=title,
        message=message,
        ok=ok,
        status_code=status_code,
        response_detail=detail,
    )
    db.add(row)
    return row


def _scope_allows(scope: str, event_scope: str) -> bool:
    normalized = (scope or "alerts").strip().lower()
    if normalized == "full_ops":
        return True
    if normalized == "alerts":
        return event_scope == "alerts"
    if normalized == "alerts_workorders":
        return event_scope in {"alerts", "workorders"}
    if normalized == "inspection":
        return event_scope == "inspection"
    return False


def _post_notification(channel: NotificationChannelRegistration, payload: dict) -> dict:
    result = {
        "ok": True,
        "delivery_mode": channel.channel_type,
        "endpoint_url": channel.endpoint_url,
        "detail": "未配置入口地址，已按模拟模式记录本次投递。",
        "status_code": None,
    }

    if not channel.endpoint_url:
        return result

    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            channel.endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "YongjiaWeakCurrentV2/notification-dispatch",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=8) as response:
            result.update(
                {
                    "status_code": response.status,
                    "detail": f"消息已发送，目标返回 {response.status}。",
                }
            )
    except error.HTTPError as exc:
        result = {
            "ok": False,
            "delivery_mode": channel.channel_type,
            "endpoint_url": channel.endpoint_url,
            "status_code": exc.code,
            "detail": f"目标接口返回 HTTP {exc.code}。",
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "ok": False,
            "delivery_mode": channel.channel_type,
            "endpoint_url": channel.endpoint_url,
            "status_code": None,
            "detail": f"发送失败：{exc}",
        }
    return result


def _event_kind_for_alert(alert: OpsAlert) -> str | None:
    if alert.status == "open":
        return "alert_open"
    if alert.status == "resolved":
        return "alert_resolved"
    return None


def _event_marker_for_alert(alert: OpsAlert, event_kind: str) -> str:
    if event_kind == "alert_open":
        triggered = alert.triggered_at.isoformat() if alert.triggered_at else ""
        return f"{alert.occurrence_count}:{triggered}"
    resolved = alert.resolved_at.isoformat() if alert.resolved_at else (alert.updated_at.isoformat() if alert.updated_at else "")
    return resolved or "latest"


def _recent_delivery_exists(
    db: Session,
    *,
    channel_id: int,
    event_prefix: str,
    cooldown_seconds: int,
) -> bool:
    cooldown = max(int(cooldown_seconds or 0), 0)
    if cooldown <= 0:
        return False
    threshold = datetime.utcnow() - timedelta(seconds=cooldown)
    row = db.scalar(
        select(NotificationDeliveryLog.id).where(
            NotificationDeliveryLog.channel_id == channel_id,
            NotificationDeliveryLog.ok.is_(True),
            NotificationDeliveryLog.created_at >= threshold,
            NotificationDeliveryLog.event_type.like(f"{event_prefix}%"),
        )
    )
    return row is not None


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> dict:
    storm_guard = build_alert_storm_guard(db)
    channels = db.scalars(
        select(NotificationChannelRegistration).order_by(NotificationChannelRegistration.display_name)
    ).all()
    delivery_logs = db.scalars(
        select(NotificationDeliveryLog).order_by(desc(NotificationDeliveryLog.created_at)).limit(20)
    ).all()
    success_count = sum(1 for item in delivery_logs if item.ok)
    failed_count = len(delivery_logs) - success_count

    recent_logs = []
    channel_name_map = {item.id: normalize_text(item.display_name) for item in channels}
    for item in delivery_logs[:5]:
        recent_logs.append(_log_to_out(item, channel_name_map.get(item.channel_id, item.channel_key)).model_dump())

    return {
        "stage": "foundation_ready",
        "strategy": "webhook_first_then_enterprise_messaging",
        "channel_count": len(channels),
        "enabled_count": sum(1 for item in channels if item.enabled),
        "resolved_enabled_count": sum(1 for item in channels if item.enabled and item.send_resolved),
        "delivery_count": len(delivery_logs),
        "delivery_success_count": success_count,
        "delivery_failed_count": failed_count,
        "channels": [_to_out(item).model_dump() for item in channels],
        "planned_targets": [
            {"name": "企业微信机器人", "status": "planned"},
            {"name": "飞书机器人", "status": "planned"},
            {"name": "Webhook 通道", "status": "active"},
            {"name": "微信工作台", "status": "planned"},
            {"name": "移动值班派发", "status": "planned"},
        ],
        "recommended_flows": [
            {"scope": "alerts", "target": "企业微信 / 飞书", "mode": "即时通知"},
            {"scope": "alerts_workorders", "target": "Webhook / 企业微信", "mode": "派单联动"},
            {"scope": "inspection", "target": "移动工作台", "mode": "巡检回传"},
            {"scope": "full_ops", "target": "全渠道", "mode": "值班总控"},
        ],
        "storm_guard": storm_guard,
        "recent_deliveries": recent_logs,
    }


@router.get("/channels", response_model=list[NotificationChannelOut])
def list_channels(
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[NotificationChannelOut]:
    rows = db.scalars(select(NotificationChannelRegistration).order_by(NotificationChannelRegistration.display_name)).all()
    return [_to_out(row) for row in rows]


@router.get("/deliveries", response_model=list[NotificationDeliveryLogOut])
def list_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[NotificationDeliveryLogOut]:
    rows = db.scalars(
        select(NotificationDeliveryLog).order_by(desc(NotificationDeliveryLog.created_at)).limit(limit)
    ).all()
    channel_map = {
        item.id: normalize_text(item.display_name)
        for item in db.scalars(select(NotificationChannelRegistration)).all()
    }
    return [_log_to_out(row, channel_map.get(row.channel_id, row.channel_key)) for row in rows]


@router.post("/channels", response_model=NotificationChannelOut)
def create_channel(
    payload: NotificationChannelUpsert,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> NotificationChannelOut:
    existing = db.scalar(
        select(NotificationChannelRegistration).where(NotificationChannelRegistration.channel_key == payload.channel_key)
    )
    if existing:
        raise HTTPException(status_code=409, detail="channel_key_exists")

    row = NotificationChannelRegistration(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/channels/{channel_id}", response_model=NotificationChannelOut)
def update_channel(
    channel_id: int,
    payload: NotificationChannelUpsert,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> NotificationChannelOut:
    row = db.get(NotificationChannelRegistration, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail="channel_not_found")

    conflict = db.scalar(
        select(NotificationChannelRegistration).where(
            NotificationChannelRegistration.channel_key == payload.channel_key,
            NotificationChannelRegistration.id != channel_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="channel_key_exists")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/channels/{channel_id}/test")
def test_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    row = db.get(NotificationChannelRegistration, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail="channel_not_found")

    title = "永嘉弱电综合运维平台通知联调"
    message = "这是一条来自 V2 的测试消息，用于验证通知通道是否可达。"
    payload = {
        "event": "platform_notification_test",
        "channel_key": row.channel_key,
        "channel_type": row.channel_type,
        "title": title,
        "message": message,
        "target_scope": row.target_scope,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    result = _post_notification(row, payload)

    row.last_checked_at = datetime.utcnow()
    if result["ok"]:
        row.status = "active" if row.enabled else row.status
    elif row.status == "active":
        row.status = "testing"

    log_row = _create_delivery_log(
        db,
        channel=row,
        title=title,
        message=message,
        ok=result["ok"],
        detail=result["detail"],
        status_code=result.get("status_code"),
    )
    db.commit()
    db.refresh(row)
    db.refresh(log_row)

    result["channel"] = _to_out(row).model_dump()
    result["delivery_log"] = _log_to_out(log_row, row.display_name).model_dump()
    return result


@router.post("/dispatch-alerts")
def dispatch_alert_notifications(
    payload: dict | None = Body(default=None),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    payload = payload or {}
    lookback_minutes = min(max(int(payload.get("lookback_minutes", 30) or 30), 1), 24 * 60)
    max_alerts = min(max(int(payload.get("max_alerts", 200) or 200), 1), 1000)
    dry_run = bool(payload.get("dry_run", True))
    force_dispatch = bool(payload.get("force_dispatch", False))

    window_start = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    storm_guard = build_alert_storm_guard(db, lookback_minutes=min(max(lookback_minutes, 10), 60))
    channels = db.scalars(
        select(NotificationChannelRegistration).where(NotificationChannelRegistration.enabled.is_(True))
    ).all()

    alerts = db.scalars(
        select(OpsAlert)
        .where(OpsAlert.updated_at >= window_start)
        .order_by(desc(OpsAlert.updated_at), OpsAlert.id.desc())
        .limit(max_alerts)
    ).all()

    sent = 0
    simulated = 0
    skipped = 0
    considered = 0
    details: list[dict] = []

    for alert in alerts:
        event_kind = _event_kind_for_alert(alert)
        if not event_kind:
            skipped += len(channels)
            continue

        for channel in channels:
            considered += 1
            reason = ""

            if not _scope_allows(channel.target_scope, "alerts"):
                skipped += 1
                continue

            if event_kind == "alert_resolved" and not channel.send_resolved:
                skipped += 1
                continue

            if (
                alert.attribution_type == "network_flap_watch"
                and channel.suppress_flap_watch
                and channel.target_scope != "full_ops"
            ):
                skipped += 1
                if len(details) < 20:
                    details.append(
                        {
                            "mode": "suppressed",
                            "channel_key": channel.channel_key,
                            "alert_id": alert.id,
                            "reason": "network_flap_watch",
                        }
                    )
                continue

            if storm_guard["suppression_active"] and not force_dispatch and channel.target_scope != "full_ops":
                skipped += 1
                if len(details) < 20:
                    details.append(
                        {
                            "mode": "suppressed",
                            "channel_key": channel.channel_key,
                            "alert_id": alert.id,
                            "reason": "alert_storm_guard",
                            "guard_level": storm_guard["level"],
                        }
                    )
                continue

            marker = _event_marker_for_alert(alert, event_kind)
            event_type = f"{event_kind}:{alert.id}:{marker}"
            event_prefix = f"{event_kind}:{alert.id}:"
            if _recent_delivery_exists(
                db,
                channel_id=channel.id,
                event_prefix=event_prefix,
                cooldown_seconds=channel.alert_cooldown_seconds,
            ):
                skipped += 1
                continue

            title = normalize_text(alert.title) or ("告警通知" if event_kind == "alert_open" else "恢复通知")
            message = normalize_text(alert.message or alert.evidence_summary or "")
            payload_data = {
                "event": event_kind,
                "event_type": event_type,
                "channel_key": channel.channel_key,
                "channel_type": channel.channel_type,
                "alert": {
                    "id": alert.id,
                    "status": alert.status,
                    "severity": alert.severity,
                    "alert_type": alert.alert_type,
                    "attribution_type": alert.attribution_type,
                    "title": title,
                    "message": message,
                    "asset_device_id": alert.asset_device_id,
                    "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "occurrence_count": alert.occurrence_count,
                },
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }

            if dry_run:
                simulated += 1
                if len(details) < 20:
                    details.append(
                        {
                            "mode": "dry_run",
                            "channel_key": channel.channel_key,
                            "event_type": event_type,
                            "alert_id": alert.id,
                            "status": alert.status,
                        }
                    )
                continue

            result = _post_notification(channel, payload_data)
            log_row = _create_delivery_log(
                db,
                channel=channel,
                title=title,
                message=message,
                ok=result["ok"],
                detail=result["detail"],
                status_code=result.get("status_code"),
                event_type=event_type,
            )
            channel.last_checked_at = datetime.utcnow()
            if result["ok"]:
                sent += 1
                if channel.status in {"planned", "ready", "testing"}:
                    channel.status = "active"
            else:
                reason = result["detail"]
                if channel.status == "active":
                    channel.status = "testing"

            if len(details) < 20:
                details.append(
                    {
                        "mode": "sent" if result["ok"] else "failed",
                        "channel_key": channel.channel_key,
                        "event_type": event_type,
                        "alert_id": alert.id,
                        "status_code": result.get("status_code"),
                        "detail": reason or result["detail"],
                        "log_id": log_row.id,
                    }
                )

    if not dry_run:
        db.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "force_dispatch": force_dispatch,
        "lookback_minutes": lookback_minutes,
        "max_alerts": max_alerts,
        "window_start": window_start.isoformat(),
        "channels": len(channels),
        "alerts_scanned": len(alerts),
        "considered": considered,
        "sent": sent,
        "simulated": simulated,
        "skipped": skipped,
        "storm_guard": storm_guard,
        "details": details,
    }

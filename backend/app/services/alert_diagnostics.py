from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import OpsAlert
from app.models.asset import AssetArea, AssetDevice
from app.services.alert_guard_settings import get_alert_guard_settings
from app.services.text_normalize import normalize_text


def build_alert_storm_guard(db: Session, lookback_minutes: int | None = None) -> dict:
    guard_settings = get_alert_guard_settings()
    normalized_lookback = min(
        max(int(lookback_minutes or guard_settings["lookback_minutes"]), 3),
        60,
    )
    window_start = datetime.utcnow() - timedelta(minutes=normalized_lookback)

    rows = db.scalars(
        select(OpsAlert)
        .where(
            OpsAlert.updated_at >= window_start,
            OpsAlert.status.in_(["open", "acknowledged"]),
        )
        .order_by(OpsAlert.updated_at.desc(), OpsAlert.id.desc())
        .limit(2000)
    ).all()
    actionable_rows = rows
    if guard_settings["exclude_flap_watch"]:
        actionable_rows = [row for row in rows if row.attribution_type != "network_flap_watch"]

    device_rows = []
    area_map: dict[int, AssetArea] = {}
    device_ids = {row.asset_device_id for row in actionable_rows if row.asset_device_id}
    if device_ids:
        device_rows = db.scalars(select(AssetDevice).where(AssetDevice.id.in_(device_ids))).all()
        area_ids = {row.area_id for row in device_rows if row.area_id}
        if area_ids:
            area_map = {
                row.id: row
                for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()
            }
    device_map = {row.id: row for row in device_rows}

    source_counter = Counter()
    area_counter = Counter()
    device_counter = Counter()
    attribution_counter = Counter()

    for row in actionable_rows:
        source_counter[row.source_type or "unknown"] += 1
        attribution_counter[row.attribution_type or "unknown"] += 1
        device = device_map.get(row.asset_device_id or -1)
        if device:
            label = normalize_text(device.hostname or device.management_ip or f"device-{device.id}")
            device_counter[(label, device.management_ip or "", device.device_type or "")] += 1
            if device.area_id and device.area_id in area_map:
                area_name = normalize_text(area_map[device.area_id].display_name)
                if area_name:
                    area_counter[area_name] += 1

    distinct_devices = len(device_counter)
    distinct_areas = len(area_counter)
    distinct_sources = len(source_counter)

    monitored_device_total = (
        db.scalar(
            select(func.count()).select_from(AssetDevice).where(
                AssetDevice.management_ip != "",
                AssetDevice.device_type.not_in(["platform_node", "gateway"]),
            )
        )
        or 0
    )
    device_ratio = round(distinct_devices / monitored_device_total, 4) if monitored_device_total else 0.0

    meets_mass_event = len(actionable_rows) >= guard_settings["min_events"]
    meets_mass_device = distinct_devices >= guard_settings["min_devices"]
    meets_cross_domain = (
        distinct_areas >= guard_settings["min_areas"] or distinct_sources >= guard_settings["min_sources"]
    )

    suppression_active = bool(meets_mass_event and meets_mass_device and meets_cross_domain)
    watch_active = bool(
        not suppression_active
        and meets_mass_event
        and distinct_devices >= guard_settings["watch_device_threshold"]
    )

    if suppression_active:
        level = "suppressed"
        label = "疑似全局/主干异常"
        reason = (
            f"{normalized_lookback} 分钟内出现 {len(actionable_rows)} 条有效告警，涉及 {distinct_devices} 台设备、"
            f"{distinct_areas} 个区域、{distinct_sources} 类来源，适合进入风暴抑制。"
        )
        recommendations = [
            "优先检查部署主机到监控网的连通性、上联交换机与核心链路。",
            "非 full_ops 通知通道暂缓逐条推送，避免微信/飞书被批量刷屏。",
            "先确认是否为整段 VLAN、主干光链路或开发主机断网，再回头处理单点设备。",
        ]
    elif watch_active:
        level = "watch"
        label = "疑似区域级异常"
        reason = (
            f"{normalized_lookback} 分钟内出现 {len(actionable_rows)} 条有效告警，涉及 {distinct_devices} 台设备，"
            "建议持续观察是否进一步扩散。"
        )
        recommendations = [
            "重点查看同区域交换机、电源和上联口是否存在抖动。",
            "若继续扩散到多区域或多来源，可升级为全局异常保护。",
        ]
    else:
        level = "normal"
        label = "单点告警为主"
        reason = "当前未达到大面积异常保护阈值，仍按单设备或单区域故障闭环处理。"
        recommendations = [
            "继续按设备级告警处理。",
            "保持对重复抖动设备和热点区域的持续观察。",
        ]

    return {
        "lookback_minutes": normalized_lookback,
        "window_start": window_start.isoformat(),
        "level": level,
        "label": label,
        "suppression_active": suppression_active,
        "watch_active": watch_active,
        "recent_alert_count": len(rows),
        "recent_actionable_count": len(actionable_rows),
        "distinct_device_count": distinct_devices,
        "distinct_area_count": distinct_areas,
        "distinct_source_count": distinct_sources,
        "monitored_device_total": monitored_device_total,
        "device_ratio": device_ratio,
        "reason": reason,
        "recommendations": recommendations,
        "settings": guard_settings,
        "top_sources": [{"source_type": key, "count": value} for key, value in source_counter.most_common(5)],
        "top_areas": [{"area_display_name": key, "count": value} for key, value in area_counter.most_common(5)],
        "top_devices": [
            {"device_label": key[0], "management_ip": key[1], "device_type": key[2], "count": value}
            for key, value in device_counter.most_common(5)
        ],
        "top_attributions": [
            {"attribution_type": key, "count": value} for key, value in attribution_counter.most_common(5)
        ],
    }

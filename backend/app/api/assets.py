import csv
import io
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.core.database import get_db
from app.core.settings import settings
from app.models.asset import (
    AssetArea,
    AssetDevice,
    ChannelStreamDiagnostic,
    NetworkPort,
    NetworkTopologyEdge,
    NetworkTopologyNode,
    PlatformSource,
    SwitchLiveProbe,
    TopologyLink,
    VideoChannel,
)
from app.schemas.assets import DeviceOut, DeviceUpsert, PlatformSourceOut, RuntimeCounts, TopologyLinkOut
from app.services.rtsp_snapshot import capture_channel_snapshot, iter_channel_flv, iter_channel_mjpeg
from app.services.auth import require_roles
from app.services.area_scope import area_scope_sort_key, describe_area_scope
from app.services.switch_live_probe import list_switch_probes
from app.services.text_normalize import normalize_text


router = APIRouter()
STREAM_DIAGNOSTIC_FRESH_HOURS = 24
CHANNEL_TAIL_AREA_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}$")
FIELD_VALIDATION_HISTORY_PATH = settings.runtime_dir / "field_validation_history.jsonl"
TOPOLOGY_EVIDENCE_PRIORITY = {
    "manual_override": 500,
    "direct_switch_arp_probe": 420,
    "direct_switch_mac_probe": 410,
    "platform_fact": 320,
    "platform_terminal_fact": 300,
}


def _parse_json_notes(raw: str) -> dict:
    text = (raw or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _topology_link_rank(link: TopologyLink) -> tuple[float, float, int]:
    return (
        float(TOPOLOGY_EVIDENCE_PRIORITY.get(link.evidence_type or "", 100)),
        float(link.confidence or 0),
        int(link.id or 0),
    )


def _diagnostic_label(error_class: str, scan_status: str) -> str:
    if scan_status == "ok":
        return "取流正常"
    if error_class == "rtsp_rejected_4xx":
        return "RTSP地址或服务策略被拒绝"
    if error_class == "rtsp_rejected_permission":
        return "账号密码或RTSP权限异常"
    if error_class in {"network_or_device_timeout", "timeout"}:
        return "设备或链路响应超时"
    if error_class:
        return "RTSP取流异常"
    return "未扫描"


def _diagnostic_freshness(diagnostic: ChannelStreamDiagnostic | None) -> dict:
    if not diagnostic or not diagnostic.checked_at:
        return {
            "is_stale": False,
            "age_hours": None,
            "fresh_until": "",
        }
    age = datetime.now() - diagnostic.checked_at
    if age.total_seconds() < 0:
        age = timedelta(seconds=0)
    fresh_until = diagnostic.checked_at + timedelta(hours=STREAM_DIAGNOSTIC_FRESH_HOURS)
    return {
        "is_stale": age > timedelta(hours=STREAM_DIAGNOSTIC_FRESH_HOURS),
        "age_hours": round(age.total_seconds() / 3600, 2),
        "fresh_until": fresh_until.isoformat(timespec="seconds"),
    }


def _load_stream_diagnostics(db: Session, channel_ids: set[int]) -> dict[int, ChannelStreamDiagnostic]:
    if not channel_ids:
        return {}
    rows = db.scalars(
        select(ChannelStreamDiagnostic).where(ChannelStreamDiagnostic.channel_id.in_(channel_ids))
    ).all()
    return {row.channel_id: row for row in rows}


def _latest_rtsp_report_path() -> Path | None:
    report_dir = settings.runtime_dir / "reports"
    if not report_dir.exists():
        return None
    reports = sorted(report_dir.glob("rtsp_scan_*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _safe_int(value: object) -> int | None:
    try:
        text = str(value or "").strip()
        return int(float(text)) if text else None
    except (TypeError, ValueError):
        return None


def _normalize_mac_text(value: str) -> str:
    text = re.sub(r"[^0-9a-fA-F]", "", value or "").lower()
    if len(text) != 12:
        return ""
    return ":".join(text[index : index + 2] for index in range(0, 12, 2))


def _append_note(base: str, note: str) -> str:
    base_text = (base or "").strip()
    note_text = (note or "").strip()
    if not note_text:
        return base_text
    if not base_text:
        return note_text
    if note_text in base_text:
        return base_text
    return f"{base_text}\n{note_text}"


def _get_or_create_area_by_name(db: Session, display_name: str) -> AssetArea | None:
    display_name = normalize_text(display_name or "").strip()
    if not display_name:
        return None
    area = db.scalar(select(AssetArea).where(AssetArea.display_name == display_name))
    if area:
        return area
    parts = [part.strip() for part in display_name.split("/") if part.strip()]
    site = parts[0] if parts else "中央大道"
    floor = ""
    for part in parts:
        if re.search(r"(B\d+F|\d+F|B\d+|地下|停车场)", part, flags=re.IGNORECASE):
            floor = part
            break
    area = AssetArea(
        site=site,
        building=parts[1] if len(parts) > 1 else "",
        floor=floor,
        zone=parts[-1] if parts else display_name,
        weak_current_room="",
        display_name=display_name,
    )
    db.add(area)
    db.flush()
    return area


def _normalize_area_scope(area_name: str) -> tuple[str, str]:
    area_name = normalize_text(area_name or "").strip()
    if " / " not in area_name:
        return area_name, ""
    prefix, tail = area_name.rsplit(" / ", 1)
    tail = tail.strip()
    if CHANNEL_TAIL_AREA_PATTERN.fullmatch(tail):
        return prefix.strip(), tail
    return area_name, ""


def _compact_repair_plan_summary(plan: dict | None) -> dict:
    plan = plan or {}
    groups = []
    for item in (plan.get("area_task_groups") or [])[:5]:
        groups.append(
            {
                "bucket_label": normalize_text(item.get("bucket_label") or ""),
                "segment": normalize_text(item.get("segment") or ""),
                "camera_ip_range": normalize_text(item.get("camera_ip_range") or ""),
                "host_ranges": item.get("host_ranges") or [],
                "suggested_area": normalize_text(item.get("suggested_area") or ""),
                "platform_name": normalize_text(item.get("platform_name") or ""),
                "count": int(item.get("count") or 0),
            }
        )
    next_priority_group = groups[0] if groups else None
    return {
        "area_missing_total": int(plan.get("area_missing_total") or 0),
        "area_auto_applicable_total": int(plan.get("area_auto_applicable_total") or 0),
        "area_manual_total": int(plan.get("area_manual_total") or 0),
        "area_task_group_total": len(plan.get("area_task_groups") or []),
        "next_priority_group": next_priority_group,
        "remaining_priority_groups": groups,
    }


def _append_field_validation_history(event: dict) -> None:
    FIELD_VALIDATION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FIELD_VALIDATION_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _read_field_validation_history(limit: int | None = 40) -> list[dict]:
    if not FIELD_VALIDATION_HISTORY_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FIELD_VALIDATION_HISTORY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    if limit is not None:
        return rows[-limit:]
    return rows


def _build_field_validation_progress_summary(db: Session) -> dict:
    from app.api.integrations import _build_fucheng_repair_plan

    current = _compact_repair_plan_summary(_build_fucheng_repair_plan(db))
    history = _read_field_validation_history(limit=None)
    today_key = datetime.now().strftime("%Y-%m-%d")
    today_events = []
    for item in history:
        event_time = normalize_text(item.get("imported_at") or "")
        if event_time.startswith(today_key):
            today_events.append(item)
    today_summary = {
        "event_total": len(today_events),
        "matched_total": sum(int(item.get("matched") or 0) for item in today_events),
        "area_updated_total": sum(int(item.get("area_updated") or 0) for item in today_events),
        "binding_updated_total": sum(int(item.get("binding_updated") or 0) for item in today_events),
        "mac_updated_total": sum(int(item.get("mac_updated") or 0) for item in today_events),
        "area_missing_reduced_total": sum(
            int((item.get("repair_delta") or {}).get("area_missing_reduced") or 0)
            for item in today_events
        ),
        "area_task_groups_reduced_total": sum(
            int((item.get("repair_delta") or {}).get("area_task_groups_reduced") or 0)
            for item in today_events
        ),
    }
    baseline_area_missing = current["area_missing_total"] + sum(
        int((item.get("repair_delta") or {}).get("area_missing_reduced") or 0)
        for item in history
    )
    baseline_task_groups = current["area_task_group_total"] + sum(
        int((item.get("repair_delta") or {}).get("area_task_groups_reduced") or 0)
        for item in history
    )
    completion = {
        "area_missing_baseline": baseline_area_missing,
        "area_missing_completed": max(baseline_area_missing - current["area_missing_total"], 0),
        "area_missing_rate": round(
            (max(baseline_area_missing - current["area_missing_total"], 0) / baseline_area_missing) * 100,
            1,
        )
        if baseline_area_missing
        else 0.0,
        "task_group_baseline": baseline_task_groups,
        "task_group_completed": max(baseline_task_groups - current["area_task_group_total"], 0),
        "task_group_rate": round(
            (max(baseline_task_groups - current["area_task_group_total"], 0) / baseline_task_groups) * 100,
            1,
        )
        if baseline_task_groups
        else 0.0,
    }
    latest = history[-1] if history else {}
    return {
        "today_key": today_key,
        "today_summary": today_summary,
        "current": current,
        "completion": completion,
        "latest_event": latest,
        "recent_events": history[-8:][::-1],
    }


@router.get("/field-validation/progress-summary")
def get_field_validation_progress_summary(
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    return _build_field_validation_progress_summary(db)


def _switch_gap_reason(probe: SwitchLiveProbe | None, direct_match_count: int) -> str:
    if not probe:
        return ""
    if probe.probe_status == "offline":
        return "telnet_closed_or_unreachable"
    if direct_match_count > 0:
        return "has_direct_match"
    if int(probe.l2_mac_count or 0) >= 1000 and int(probe.arp_entry_count or 0) >= 10:
        return "mac_table_rich_but_camera_mac_unmatched"
    if int(probe.l2_mac_count or 0) >= 500:
        return "likely_aggregation_or_unknown_camera_mac"
    if int(probe.arp_entry_count or 0) > 0 and int(probe.l2_mac_count or 0) == 0:
        return "arp_only_no_forwarding_table"
    if int(probe.arp_entry_count or 0) == 0 and int(probe.l2_mac_count or 0) == 0 and probe.probe_status == "ok":
        return "no_visible_forwarding_table"
    return "low_signal_needs_manual_review"


def _switch_gap_label(reason: str) -> str:
    mapping = {
        "has_direct_match": "接入口已命中摄像头",
        "mac_table_rich_but_camera_mac_unmatched": "疑似汇聚/级联设备",
        "likely_aggregation_or_unknown_camera_mac": "疑似汇聚口或待补 MAC",
        "arp_only_no_forwarding_table": "仅见 ARP，缺少转发表",
        "no_visible_forwarding_table": "未见 ARP 或转发表",
        "low_signal_needs_manual_review": "待现场核实",
        "telnet_closed_or_unreachable": "Telnet 关闭或不可达",
    }
    return mapping.get(reason, "")


def _switch_role_guess(reason: str, direct_match_count: int) -> tuple[str, str, bool]:
    if direct_match_count > 0:
        return ("camera_access", "摄像头接入交换机", False)
    mapping = {
        "mac_table_rich_but_camera_mac_unmatched": ("suspected_aggregation", "疑似汇聚/级联交换机", True),
        "likely_aggregation_or_unknown_camera_mac": ("suspected_aggregation", "疑似汇聚口或下级交换机", True),
        "arp_only_no_forwarding_table": ("unknown", "缺少转发表，待核实", True),
        "no_visible_forwarding_table": ("unknown", "未见转发表，待核实", True),
        "low_signal_needs_manual_review": ("unknown", "待现场核实", True),
        "telnet_closed_or_unreachable": ("unreachable", "不可达或未开放 Telnet", True),
    }
    role, label, flagged = mapping.get(reason, ("", "", False))
    return (role, label, flagged)


def _load_direct_match_counts(db: Session, device_ids: set[int]) -> dict[int, int]:
    if not device_ids:
        return {}
    return dict(
        db.execute(
            select(TopologyLink.src_device_id, func.count(TopologyLink.id))
            .where(
                TopologyLink.src_device_id.in_(device_ids),
                TopologyLink.evidence_type == "direct_switch_mac_probe",
            )
            .group_by(TopologyLink.src_device_id)
        ).all()
    )


def _parse_report_checked_at(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return datetime.now()


def _apply_manual_topology_binding(
    db: Session,
    channel: VideoChannel,
    switch_ip: str,
    port_name: str,
    vlan_id: str = "",
    evidence_note: str = "",
) -> TopologyLink:
    if not channel.camera_asset_id:
        raise HTTPException(status_code=400, detail="channel_has_no_camera_asset")

    current_link = db.scalar(
        select(TopologyLink)
        .where(
            TopologyLink.dst_device_id == channel.camera_asset_id,
            TopologyLink.link_type == "physical",
        )
        .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
    )
    current_switch = db.get(AssetDevice, current_link.src_device_id) if current_link and current_link.src_device_id else None

    resolved_switch_ip = normalize_text(switch_ip or (current_switch.management_ip if current_switch else "")).strip()
    resolved_port_name = normalize_text(port_name).strip()
    resolved_vlan_id = normalize_text(vlan_id).strip()
    resolved_note = normalize_text(evidence_note).strip()

    if not resolved_switch_ip or not resolved_port_name:
        raise HTTPException(status_code=400, detail="switch_ip_and_port_name_required")

    switch = db.scalar(
        select(AssetDevice).where(
            AssetDevice.device_type == "switch",
            AssetDevice.management_ip == resolved_switch_ip,
            AssetDevice.device_status != "archived",
        )
    )
    if not switch:
        raise HTTPException(status_code=404, detail="switch_not_found")

    port = db.scalar(
        select(NetworkPort).where(
            NetworkPort.device_id == switch.id,
            NetworkPort.port_name == resolved_port_name,
        )
    )
    if not port:
        port = NetworkPort(
            device_id=switch.id,
            port_name=resolved_port_name,
            port_index=_safe_int(resolved_port_name),
            port_type="electrical",
            admin_status="unknown",
            oper_status="unknown",
            vlan_id=resolved_vlan_id,
            role_guess="camera_access_manual",
        )
        db.add(port)
        db.flush()
    else:
        if resolved_vlan_id:
            port.vlan_id = resolved_vlan_id
        port.role_guess = port.role_guess or "camera_access_manual"

    if not current_link:
        current_link = TopologyLink(
            dst_device_id=channel.camera_asset_id,
            link_type="physical",
        )
        db.add(current_link)

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_link.src_device_id = switch.id
    current_link.src_port_id = port.id
    current_link.dst_device_id = channel.camera_asset_id
    current_link.dst_port_id = None
    current_link.link_type = "physical"
    current_link.confidence = 1.0
    current_link.evidence_type = "manual_override"
    note_suffix = f"，{resolved_note}" if resolved_note else ""
    current_link.evidence_summary = f"现场核实：{resolved_switch_ip} port {resolved_port_name} -> {channel.camera_ip or channel.channel_name}{note_suffix}；{now_label}"
    return current_link


def _upsert_stream_diagnostic(db: Session, row: dict, report_path: Path, checked_at: datetime) -> bool:
    channel_id = _safe_int(row.get("channel_id"))
    if not channel_id:
        return False
    channel = db.get(VideoChannel, channel_id)
    if not channel:
        return False

    existing = db.scalar(
        select(ChannelStreamDiagnostic).where(ChannelStreamDiagnostic.channel_id == channel_id)
    )
    payload = {
        "channel_id": channel_id,
        "camera_ip": str(row.get("camera_ip") or channel.camera_ip or "").strip(),
        "platform_ip": str(row.get("platform_ip") or "").strip(),
        "scan_status": str(row.get("scan_status") or "unknown").strip() or "unknown",
        "error_class": str(row.get("error_class") or "").strip(),
        "error_message": str(row.get("error") or "").strip(),
        "rtsp_url": str(row.get("rtsp_main") or channel.rtsp_main or "").strip(),
        "elapsed_ms": _safe_int(row.get("elapsed_ms")),
        "source_report": report_path.name,
        "checked_at": checked_at,
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        return True
    db.add(ChannelStreamDiagnostic(**payload))
    return True


@router.get("/runtime-counts", response_model=RuntimeCounts)
def runtime_counts(db: Session = Depends(get_db)) -> RuntimeCounts:
    return RuntimeCounts(
        platform_sources=db.scalar(select(func.count()).select_from(PlatformSource)) or 0,
        devices=db.scalar(select(func.count()).select_from(AssetDevice)) or 0,
        ports=db.scalar(select(func.count()).select_from(NetworkPort)) or 0,
        channels=db.scalar(select(func.count()).select_from(VideoChannel)) or 0,
        links=db.scalar(select(func.count()).select_from(TopologyLink)) or 0,
    )


@router.get("/areas")
def list_areas(
    db: Session = Depends(get_db),
    only_with_channels: bool = Query(default=False),
) -> list[dict]:
    if only_with_channels:
        rows = db.execute(
            select(AssetArea, func.count(VideoChannel.id))
            .join(AssetDevice, AssetDevice.area_id == AssetArea.id)
            .join(VideoChannel, VideoChannel.camera_asset_id == AssetDevice.id)
            .where(AssetDevice.device_type == "camera", AssetDevice.device_status != "archived")
            .group_by(AssetArea.id)
        ).all()
    else:
        rows = [(row, 0) for row in db.scalars(select(AssetArea).order_by(AssetArea.display_name)).all()]

    payload = []
    for area, camera_count in rows:
        scope = describe_area_scope(area.display_name)
        payload.append(
            {
                "id": area.id,
                "site": normalize_text(area.site),
                "building": normalize_text(area.building),
                "floor": normalize_text(area.floor),
                "zone": normalize_text(area.zone),
                "display_name": normalize_text(area.display_name),
                "menu_label": scope["menu_label"],
                "summary_label": scope["summary_label"],
                "scope_kind": scope["scope_kind"],
                "sort_rank": scope["sort_rank"],
                "accuracy_label": scope["accuracy_label"],
                "camera_count": int(camera_count or 0),
            }
        )
    payload.sort(key=area_scope_sort_key)
    return payload


@router.get("/area-breakdown")
def area_breakdown(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(AssetArea.display_name, func.count(AssetDevice.id))
        .join(AssetDevice, AssetDevice.area_id == AssetArea.id)
        .group_by(AssetArea.display_name)
        .order_by(func.count(AssetDevice.id).desc())
    ).all()
    return [{"area": normalize_text(row[0]), "count": row[1]} for row in rows]


@router.get("/platform-sources", response_model=list[PlatformSourceOut])
def list_platform_sources(db: Session = Depends(get_db)) -> list[PlatformSourceOut]:
    rows = db.scalars(select(PlatformSource).order_by(PlatformSource.id.desc())).all()
    return [
        PlatformSourceOut(
            id=row.id,
            source_type=row.source_type,
            name=normalize_text(row.name),
            vendor=normalize_text(row.vendor),
            base_url=row.base_url,
            management_ip=row.management_ip,
            version=normalize_text(row.version),
            sync_status=row.sync_status,
        )
        for row in rows
    ]


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    db: Session = Depends(get_db),
    area_id: int | None = None,
    device_type: str | None = None,
    source_type: str | None = None,
    source_management_ip: str | None = Query(default=None),
    status: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    keyword: str = Query(default="", alias="q"),
    limit: int = 120,
) -> list[DeviceOut]:
    stmt = select(AssetDevice)
    if not include_archived:
        stmt = stmt.where(AssetDevice.device_status != "archived")
    if area_id:
        stmt = stmt.where(AssetDevice.area_id == area_id)
    if device_type:
        stmt = stmt.where(AssetDevice.device_type == device_type)
    if source_type:
        stmt = stmt.where(AssetDevice.primary_source_type == source_type)
    if status:
        stmt = stmt.where(AssetDevice.device_status == status)
    source_management_ip = (source_management_ip or "").strip()
    if source_management_ip:
        parent_device = aliased(AssetDevice)
        camera_scope_subquery = (
            select(VideoChannel.camera_asset_id)
            .join(parent_device, parent_device.id == VideoChannel.parent_device_id)
            .where(
                VideoChannel.camera_asset_id.is_not(None),
                parent_device.management_ip == source_management_ip,
            )
        )
        stmt = stmt.where(
            (AssetDevice.management_ip == source_management_ip)
            | (AssetDevice.id.in_(camera_scope_subquery))
        )
    if keyword:
        like = f"%{keyword.strip()}%"
        camera_match_subquery = select(VideoChannel.camera_asset_id).where(
            VideoChannel.camera_asset_id.is_not(None),
            (VideoChannel.camera_ip.ilike(like)) | (VideoChannel.channel_name.ilike(like)),
        )
        stmt = stmt.where(
            AssetDevice.hostname.ilike(like)
            | AssetDevice.management_ip.ilike(like)
            | AssetDevice.model.ilike(like)
            | AssetDevice.vendor.ilike(like)
            | AssetDevice.notes.ilike(like)
            | AssetDevice.id.in_(camera_match_subquery)
        )
    device_priority = case(
        (AssetDevice.device_type == "camera", 0),
        (AssetDevice.device_type == "nvr", 1),
        (AssetDevice.device_type == "decoder", 2),
        (AssetDevice.device_type == "switch", 3),
        else_=9,
    )
    source_priority = case(
        (AssetDevice.primary_source_type == "jvss", 0),
        (AssetDevice.primary_source_type == "tg_cos", 1),
        (AssetDevice.primary_source_type == "hikvision_nvr", 2),
        else_=9,
    )
    rows = db.scalars(
        stmt.order_by(device_priority.asc(), source_priority.asc(), AssetDevice.id.desc()).limit(min(max(limit, 20), 500))
    ).all()
    switch_ids = {row.id for row in rows if row.device_type == "switch"}
    probe_map = list_switch_probes(db, switch_ids)
    direct_count_map = _load_direct_match_counts(db, switch_ids)
    return [
        DeviceOut(**_device_out_payload(db, row, probe_map.get(row.id), direct_count_map.get(row.id, 0)))
        for row in rows
    ]


def _device_out_payload(
    db: Session,
    row: AssetDevice,
    probe: SwitchLiveProbe | None = None,
    direct_match_count: int | None = None,
) -> dict:
    area = db.get(AssetArea, row.area_id) if row.area_id else None
    if probe is None and row.device_type == "switch":
        probe = db.scalar(select(SwitchLiveProbe).where(SwitchLiveProbe.device_id == row.id))
    if direct_match_count is None and row.device_type == "switch":
        direct_match_count = _load_direct_match_counts(db, {row.id}).get(row.id, 0)
    resolved_direct_count = int(direct_match_count or 0)
    gap_reason = _switch_gap_reason(probe, resolved_direct_count) if row.device_type == "switch" else ""
    gap_label = _switch_gap_label(gap_reason) if gap_reason else ""
    role_guess, role_label, auto_flagged = _switch_role_guess(gap_reason, resolved_direct_count) if row.device_type == "switch" else ("", "", False)
    judgement_summary = ""
    if row.device_type == "switch" and probe:
        if resolved_direct_count > 0:
            judgement_summary = f"系统已通过交换机实采命中 {resolved_direct_count} 路摄像头，可视为接入交换机。"
        elif gap_label:
            judgement_summary = (
                f"系统判断：{gap_label}。ARP {int(probe.arp_entry_count or 0)}，"
                f"L2 MAC {int(probe.l2_mac_count or 0)}，摄像头命中 {resolved_direct_count}。"
            )
    return {
        "id": row.id,
        "device_type": row.device_type,
        "vendor": normalize_text(row.vendor),
        "model": normalize_text(row.model),
        "serial_number": normalize_text(row.serial_number),
        "hostname": normalize_text(row.hostname),
        "management_ip": row.management_ip,
        "service_ip": row.service_ip,
        "mac_address": normalize_text(row.mac_address),
        "health_state": row.health_state,
        "device_status": row.device_status,
        "primary_source_type": row.primary_source_type,
        "area_id": row.area_id,
        "area_display_name": normalize_text(area.display_name) if area else "",
        "parent_device_id": row.parent_device_id,
        "platform_source_id": row.platform_source_id,
        "source_priority": row.source_priority,
        "notes": normalize_text(row.notes),
        "live_probe_status": probe.probe_status if probe else "unknown",
        "live_probe_checked_at": probe.checked_at.isoformat(timespec="seconds") if probe and probe.checked_at else "",
        "live_probe_telnet_status": probe.telnet_status if probe else "",
        "live_probe_http_status": probe.http_status if probe else "",
        "live_probe_https_status": probe.https_status if probe else "",
        "live_probe_ssh_status": probe.ssh_status if probe else "",
        "live_probe_version_text": normalize_text(probe.version_text) if probe else "",
        "live_probe_arp_entry_count": probe.arp_entry_count if probe else 0,
        "live_probe_camera_match_count": probe.camera_match_count if probe else 0,
        "live_probe_l2_mac_count": probe.l2_mac_count if probe else 0,
        "live_probe_error_message": normalize_text(probe.error_message) if probe else "",
        "topology_role_guess": role_guess,
        "topology_role_label": role_label,
        "topology_gap_reason": gap_reason,
        "topology_gap_label": gap_label,
        "topology_auto_flagged": auto_flagged,
        "topology_judgement_summary": judgement_summary,
    }


def _normalize_device_payload(payload: DeviceUpsert) -> dict:
    data = payload.model_dump()
    for key in (
        "device_type",
        "vendor",
        "model",
        "serial_number",
        "hostname",
        "management_ip",
        "service_ip",
        "mac_address",
        "health_state",
        "device_status",
        "primary_source_type",
        "notes",
    ):
        data[key] = normalize_text(data.get(key)).strip()
    data["device_type"] = data["device_type"] or "camera"
    data["health_state"] = data["health_state"] or "unknown"
    data["device_status"] = data["device_status"] or "manual"
    data["primary_source_type"] = data["primary_source_type"] or "manual"
    data["source_priority"] = int(data.get("source_priority") or 50)
    return data


def _validate_device_refs(db: Session, data: dict, current_device_id: int | None = None) -> None:
    if data.get("area_id") and not db.get(AssetArea, data["area_id"]):
        raise HTTPException(status_code=400, detail="area_not_found")
    if data.get("platform_source_id") and not db.get(PlatformSource, data["platform_source_id"]):
        raise HTTPException(status_code=400, detail="platform_source_not_found")
    parent_id = data.get("parent_device_id")
    if parent_id:
        if current_device_id and parent_id == current_device_id:
            raise HTTPException(status_code=400, detail="parent_device_cannot_be_self")
        if not db.get(AssetDevice, parent_id):
            raise HTTPException(status_code=400, detail="parent_device_not_found")
    management_ip = (data.get("management_ip") or "").strip()
    if management_ip:
        conflict_stmt = select(AssetDevice).where(
            AssetDevice.management_ip == management_ip,
            AssetDevice.device_status != "archived",
        )
        if current_device_id:
            conflict_stmt = conflict_stmt.where(AssetDevice.id != current_device_id)
        if db.scalar(conflict_stmt):
            raise HTTPException(status_code=409, detail="management_ip_exists")


@router.post("/devices", response_model=DeviceOut)
def create_device(
    payload: DeviceUpsert,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> DeviceOut:
    data = _normalize_device_payload(payload)
    _validate_device_refs(db, data)
    row = AssetDevice(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return DeviceOut(**_device_out_payload(db, row))


@router.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    payload: DeviceUpsert,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> DeviceOut:
    row = db.get(AssetDevice, device_id)
    if not row:
        raise HTTPException(status_code=404, detail="device_not_found")
    data = _normalize_device_payload(payload)
    _validate_device_refs(db, data, current_device_id=device_id)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return DeviceOut(**_device_out_payload(db, row))


@router.delete("/devices/{device_id}")
def archive_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    row = db.get(AssetDevice, device_id)
    if not row:
        raise HTTPException(status_code=404, detail="device_not_found")
    linked_channels = db.scalar(
        select(func.count()).select_from(VideoChannel).where(
            (VideoChannel.parent_device_id == device_id) | (VideoChannel.camera_asset_id == device_id)
        )
    ) or 0
    linked_ports = db.scalar(select(func.count()).select_from(NetworkPort).where(NetworkPort.device_id == device_id)) or 0
    linked_topology = db.scalar(
        select(func.count()).select_from(TopologyLink).where(
            (TopologyLink.src_device_id == device_id) | (TopologyLink.dst_device_id == device_id)
        )
    ) or 0
    row.device_status = "archived"
    row.health_state = "archived"
    if "人工归档" not in (row.notes or ""):
        row.notes = f"{normalize_text(row.notes)}\n人工归档：现场确认资产不再参与当前运维。".strip()
    db.commit()
    return {
        "ok": True,
        "archived": True,
        "device_id": device_id,
        "linked_channels": linked_channels,
        "linked_ports": linked_ports,
        "linked_topology": linked_topology,
    }


def _build_channel_context(db: Session, channels: list[VideoChannel]) -> tuple[dict[int, AssetDevice], dict[int, AssetArea], dict[int, NetworkPort], dict[int, TopologyLink]]:
    parent_ids = {row.parent_device_id for row in channels if row.parent_device_id}
    camera_ids = {row.camera_asset_id for row in channels if row.camera_asset_id}
    tracked_device_ids = set(parent_ids | camera_ids)

    access_links: dict[int, TopologyLink] = {}
    tracked_port_ids: set[int] = set()
    if camera_ids:
        link_rows = db.scalars(
            select(TopologyLink)
            .where(
                TopologyLink.dst_device_id.in_(camera_ids),
                TopologyLink.link_type == "physical",
            )
        ).all()
        for link in sorted(link_rows, key=_topology_link_rank, reverse=True):
            if not link.dst_device_id or link.dst_device_id in access_links:
                continue
            access_links[link.dst_device_id] = link
            if link.src_device_id:
                tracked_device_ids.add(link.src_device_id)
            if link.src_port_id:
                tracked_port_ids.add(link.src_port_id)

    device_map = (
        {row.id: row for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(tracked_device_ids))).all()}
        if tracked_device_ids
        else {}
    )
    area_ids = {row.area_id for row in device_map.values() if row.area_id}
    area_map = (
        {row.id: row for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()}
        if area_ids
        else {}
    )
    port_map = (
        {row.id: row for row in db.scalars(select(NetworkPort).where(NetworkPort.id.in_(tracked_port_ids))).all()}
        if tracked_port_ids
        else {}
    )
    return device_map, area_map, port_map, access_links


def _channel_payload(
    row: VideoChannel,
    device_map: dict[int, AssetDevice],
    area_map: dict[int, AssetArea],
    port_map: dict[int, NetworkPort],
    access_links: dict[int, TopologyLink],
    diagnostic_map: dict[int, ChannelStreamDiagnostic] | None = None,
) -> dict:
    parent = device_map.get(row.parent_device_id)
    camera = device_map.get(row.camera_asset_id)
    channel_area_id = (camera.area_id if camera else None) or (parent.area_id if parent else None)
    access_link = access_links.get(row.camera_asset_id or -1)
    switch = device_map.get(access_link.src_device_id) if access_link and access_link.src_device_id else None
    switch_port = port_map.get(access_link.src_port_id) if access_link and access_link.src_port_id else None
    note_payload = _parse_json_notes(row.notes)

    snapshot_capture_strategy = "rtsp_main" if (row.rtsp_main or "").strip() else ("rtsp_sub" if (row.rtsp_sub or "").strip() else "")
    snapshot_capture_enabled = bool(snapshot_capture_strategy)
    v2_snapshot_url = f"/api/assets/channels/{row.id}/snapshot.jpg" if snapshot_capture_enabled else ""
    direct_area_raw = normalize_text(note_payload.get("direct_area") or "")
    direct_area, direct_area_tail = _normalize_area_scope(direct_area_raw)
    direct_group = normalize_text(note_payload.get("direct_group") or "")
    direct_stream_server = normalize_text(note_payload.get("stream_server") or "")
    direct_thruster = normalize_text(note_payload.get("thruster") or "")
    direct_rtsp_status = normalize_text(note_payload.get("rtsp_status") or "")
    direct_record_status = normalize_text(note_payload.get("record_status") or "")
    direct_platform_status = normalize_text(note_payload.get("platform_status") or "")
    direct_name = normalize_text(note_payload.get("direct_name") or "")
    direct_point_ip = normalize_text(note_payload.get("direct_point_ip") or "")
    direct_point_label = normalize_text(note_payload.get("direct_point_label") or "")
    import_origin = normalize_text(note_payload.get("import_origin") or "")
    origin_path = normalize_text(note_payload.get("origin_path") or "")
    source_lineage = note_payload.get("source_lineage") if isinstance(note_payload.get("source_lineage"), list) else []
    supplemental_merged = bool(note_payload.get("supplemental_merged"))
    switch_binding_state = "bound" if switch else "pending"
    note_summary_parts = [
        f"直采名称：{direct_name}" if direct_name else "",
        f"直采区域：{direct_area}" if direct_area else "",
        f"实际点位 IP：{direct_point_ip}" if direct_point_ip else "",
        f"流媒体服务器：{direct_stream_server}" if direct_stream_server else "",
        f"RTSP 状态：{direct_rtsp_status}" if direct_rtsp_status else "",
        f"录像状态：{direct_record_status}" if direct_record_status else "",
    ]
    note_summary = " | ".join([part for part in note_summary_parts if part])
    diagnostic = (diagnostic_map or {}).get(row.id)
    diagnostic_freshness = _diagnostic_freshness(diagnostic)
    area_scope = (
        describe_area_scope(normalize_text(area_map[channel_area_id].display_name))
        if channel_area_id in area_map
        else None
    )
    direct_area_scope = describe_area_scope(direct_area) if direct_area else None

    return {
        "id": row.id,
        "parent_device_id": row.parent_device_id,
        "parent_label": normalize_text((parent.hostname if parent else "") or (parent.management_ip if parent else "")),
        "source_management_ip": parent.management_ip if parent else "",
        "channel_no": row.channel_no,
        "channel_name": normalize_text(row.channel_name),
        "camera_asset_id": row.camera_asset_id,
        "camera_ip": row.camera_ip,
        "camera_label": normalize_text((camera.hostname if camera else "") or row.camera_ip),
        "camera_source_type": camera.primary_source_type if camera else "",
        "rtsp_main": row.rtsp_main,
        "rtsp_sub": row.rtsp_sub,
        "snapshot_url": v2_snapshot_url,
        "legacy_snapshot_url": row.snapshot_url,
        "snapshot_capture_enabled": snapshot_capture_enabled,
        "snapshot_capture_strategy": snapshot_capture_strategy,
        "snapshot_capture_url": v2_snapshot_url,
        "protocol_type": row.protocol_type,
        "channel_status": row.channel_status,
        "source_type": parent.primary_source_type if parent else "",
        "notes": normalize_text(row.notes),
        "note_summary": note_summary,
        "direct_name": direct_name,
        "direct_area": direct_area,
        "direct_area_raw": direct_area_raw if direct_area_raw and direct_area_raw != direct_area else "",
        "direct_area_tail": direct_area_tail,
        "direct_group": direct_group,
        "direct_stream_server": direct_stream_server,
        "direct_thruster": direct_thruster,
        "direct_rtsp_status": direct_rtsp_status,
        "direct_record_status": direct_record_status,
        "direct_platform_status": direct_platform_status,
        "direct_point_ip": direct_point_ip,
        "direct_point_label": direct_point_label,
        "import_origin": import_origin,
        "origin_path": origin_path,
        "source_lineage": source_lineage,
        "supplemental_merged": supplemental_merged,
        "record_track_id": row.record_track_id,
        "area_id": channel_area_id,
        "area_display_name": _normalize_area_scope(normalize_text(area_map[channel_area_id].display_name))[0]
        if channel_area_id in area_map
        else "",
        "area_menu_label": area_scope["menu_label"] if area_scope else "",
        "area_summary_label": area_scope["summary_label"] if area_scope else "",
        "area_scope_kind": area_scope["scope_kind"] if area_scope else "",
        "area_accuracy_label": area_scope["accuracy_label"] if area_scope else "",
        "switch_device_id": switch.id if switch else None,
        "switch_label": normalize_text((switch.hostname if switch else "") or (switch.management_ip if switch else "")),
        "switch_ip": switch.management_ip if switch else "",
        "switch_binding_state": switch_binding_state,
        "switch_port_id": switch_port.id if switch_port else None,
        "switch_port_name": normalize_text(switch_port.port_name) if switch_port else "",
        "switch_port_vlan_id": switch_port.vlan_id if switch_port else "",
        "topology_link_id": access_link.id if access_link else None,
        "topology_confidence": access_link.confidence if access_link else 0,
        "topology_evidence_type": access_link.evidence_type if access_link else "",
        "topology_evidence_summary": normalize_text(access_link.evidence_summary) if access_link else "",
        "stream_probe_status": diagnostic.scan_status if diagnostic else "unknown",
        "stream_probe_error_class": diagnostic.error_class if diagnostic else "",
        "stream_probe_error": normalize_text(diagnostic.error_message) if diagnostic else "",
        "stream_probe_label": _diagnostic_label(
            diagnostic.error_class if diagnostic else "",
            diagnostic.scan_status if diagnostic else "unknown",
        ),
        "stream_probe_checked_at": diagnostic.checked_at.isoformat(timespec="seconds") if diagnostic else "",
        "stream_probe_elapsed_ms": diagnostic.elapsed_ms if diagnostic else None,
        "stream_probe_report": diagnostic.source_report if diagnostic else "",
        "stream_probe_is_stale": diagnostic_freshness["is_stale"],
        "stream_probe_age_hours": diagnostic_freshness["age_hours"],
        "stream_probe_fresh_hours": STREAM_DIAGNOSTIC_FRESH_HOURS,
        "stream_probe_fresh_until": diagnostic_freshness["fresh_until"],
        "direct_area_scope_kind": direct_area_scope["scope_kind"] if direct_area_scope else "",
        "direct_area_accuracy_label": direct_area_scope["accuracy_label"] if direct_area_scope else "",
        "direct_area_menu_label": direct_area_scope["menu_label"] if direct_area_scope else "",
    }


def _stream_channel_snapshot(
    channel_id: int,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    channel = db.get(VideoChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="channel_not_found")

    try:
        result = capture_channel_snapshot(
            channel_id=channel_id,
            rtsp_main=channel.rtsp_main,
            rtsp_sub=channel.rtsp_sub,
            legacy_snapshot_url=channel.snapshot_url,
            force_refresh=refresh,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc

    return FileResponse(
        result.image_path,
        media_type="image/jpeg",
        filename=f"channel-{channel_id}.jpg",
        headers={
            "Cache-Control": "private, max-age=30",
            "X-Snapshot-Strategy": result.strategy,
            "X-Snapshot-Captured-At": result.captured_at,
        },
    )


@router.get("/channels/{channel_id}/snapshot")
def get_channel_snapshot(
    channel_id: int,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return _stream_channel_snapshot(channel_id=channel_id, refresh=refresh, db=db)


@router.get("/channels/{channel_id}/snapshot.jpg")
def get_channel_snapshot_jpg(
    channel_id: int,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return _stream_channel_snapshot(channel_id=channel_id, refresh=refresh, db=db)


@router.get("/channels/{channel_id}/mjpeg")
def get_channel_mjpeg(
    channel_id: int,
    db: Session = Depends(get_db),
):
    channel = db.get(VideoChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="channel_not_found")
    try:
        stream = iter_channel_mjpeg(rtsp_main=channel.rtsp_main, rtsp_sub=channel.rtsp_sub)
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    return StreamingResponse(
        stream,
        media_type="multipart/x-mixed-replace;boundary=ffmpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/channels/{channel_id}/flv")
def get_channel_flv(
    channel_id: int,
    db: Session = Depends(get_db),
):
    channel = db.get(VideoChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="channel_not_found")
    try:
        stream = iter_channel_flv(rtsp_main=channel.rtsp_main, rtsp_sub=channel.rtsp_sub)
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    return StreamingResponse(
        stream,
        media_type="video/x-flv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f"inline; filename=channel-{channel_id}.flv",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/devices/{device_id}")
def get_device_detail(device_id: int, db: Session = Depends(get_db)) -> dict:
    device = db.get(AssetDevice, device_id)
    if device is None:
        return {"error": "not_found"}
    area = db.get(AssetArea, device.area_id) if device.area_id else None

    ports = db.scalars(select(NetworkPort).where(NetworkPort.device_id == device_id).order_by(NetworkPort.id)).all()
    channels = db.scalars(
        select(VideoChannel).where(VideoChannel.parent_device_id == device_id).order_by(VideoChannel.id)
    ).all()
    inbound_links = db.scalars(select(TopologyLink).where(TopologyLink.dst_device_id == device_id)).all()
    outbound_links = db.scalars(select(TopologyLink).where(TopologyLink.src_device_id == device_id)).all()

    channel_device_map, channel_area_map, port_map, access_links = _build_channel_context(db, channels)
    diagnostic_map = _load_stream_diagnostics(db, {row.id for row in channels})

    return {
        "device": {
            **_device_out_payload(db, device),
            "notes": normalize_text(device.notes),
        },
        "ports": [
            {
                "id": row.id,
                "port_name": normalize_text(row.port_name),
                "port_type": row.port_type,
                "role_guess": normalize_text(row.role_guess),
                "vlan_id": row.vlan_id,
            }
            for row in ports
        ],
        "channels": [
            _channel_payload(row, channel_device_map, channel_area_map, port_map, access_links, diagnostic_map)
            for row in channels
        ],
        "links": {
            "inbound": [
                {
                    "id": row.id,
                    "src_device_id": row.src_device_id,
                    "src_port_id": row.src_port_id,
                    "link_type": row.link_type,
                    "confidence": row.confidence,
                    "evidence_type": row.evidence_type,
                }
                for row in inbound_links
            ],
            "outbound": [
                {
                    "id": row.id,
                    "dst_device_id": row.dst_device_id,
                    "src_port_id": row.src_port_id,
                    "link_type": row.link_type,
                    "confidence": row.confidence,
                    "evidence_type": row.evidence_type,
                }
                for row in outbound_links
            ],
        },
    }


@router.get("/links", response_model=list[TopologyLinkOut])
def list_links(db: Session = Depends(get_db)) -> list[TopologyLinkOut]:
    rows = db.scalars(select(TopologyLink).order_by(TopologyLink.id.desc()).limit(100)).all()
    return list(rows)


@router.post("/stream-diagnostics/import-latest-report")
def import_latest_stream_diagnostics(
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    report_path = _latest_rtsp_report_path()
    if not report_path:
        raise HTTPException(status_code=404, detail="rtsp_report_not_found")

    checked_at = _parse_report_checked_at(report_path)
    imported = 0
    skipped = 0
    with report_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if _upsert_stream_diagnostic(db, row, report_path, checked_at):
                imported += 1
            else:
                skipped += 1
    db.commit()
    return {
        "ok": True,
        "report": report_path.name,
        "imported": imported,
        "skipped": skipped,
        "checked_at": checked_at.isoformat(timespec="seconds"),
    }


@router.get("/stream-diagnostics/latest-report-status")
def latest_stream_diagnostic_report_status(db: Session = Depends(get_db)) -> dict:
    report_path = _latest_rtsp_report_path()
    latest_import = db.execute(
        select(ChannelStreamDiagnostic.source_report, func.max(ChannelStreamDiagnostic.checked_at))
        .group_by(ChannelStreamDiagnostic.source_report)
        .order_by(func.max(ChannelStreamDiagnostic.checked_at).desc())
        .limit(1)
    ).first()
    imported_report = (latest_import[0] or "") if latest_import else ""
    imported_checked_at = latest_import[1] if latest_import else None

    if not report_path:
        return {
            "has_report": False,
            "pending": False,
            "latest_report": "",
            "latest_report_checked_at": "",
            "imported_report": imported_report,
            "imported_checked_at": imported_checked_at.isoformat(timespec="seconds") if imported_checked_at else "",
        }

    latest_checked_at = _parse_report_checked_at(report_path)
    pending = report_path.name != imported_report
    return {
        "has_report": True,
        "pending": pending,
        "latest_report": report_path.name,
        "latest_report_checked_at": latest_checked_at.isoformat(timespec="seconds"),
        "imported_report": imported_report,
        "imported_checked_at": imported_checked_at.isoformat(timespec="seconds") if imported_checked_at else "",
    }


@router.get("/stream-diagnostics/summary")
def stream_diagnostic_summary(db: Session = Depends(get_db)) -> dict:
    fresh_cutoff = datetime.now() - timedelta(hours=STREAM_DIAGNOSTIC_FRESH_HOURS)
    total = db.scalar(select(func.count()).select_from(ChannelStreamDiagnostic)) or 0
    channel_total = db.scalar(select(func.count()).select_from(VideoChannel)) or 0
    diagnostic_channel_total = db.scalar(select(func.count(func.distinct(ChannelStreamDiagnostic.channel_id)))) or 0
    ok_count = db.scalar(
        select(func.count()).select_from(ChannelStreamDiagnostic).where(
            ChannelStreamDiagnostic.scan_status == "ok",
            ChannelStreamDiagnostic.checked_at >= fresh_cutoff,
        )
    ) or 0
    abnormal_count = db.scalar(
        select(func.count()).select_from(ChannelStreamDiagnostic).where(
            ChannelStreamDiagnostic.scan_status != "ok",
            ChannelStreamDiagnostic.scan_status != "unknown",
            ChannelStreamDiagnostic.checked_at >= fresh_cutoff,
        )
    ) or 0
    stale_ok_count = db.scalar(
        select(func.count()).select_from(ChannelStreamDiagnostic).where(
            ChannelStreamDiagnostic.scan_status == "ok",
            ChannelStreamDiagnostic.checked_at < fresh_cutoff,
        )
    ) or 0
    stale_abnormal_count = db.scalar(
        select(func.count()).select_from(ChannelStreamDiagnostic).where(
            ChannelStreamDiagnostic.scan_status != "ok",
            ChannelStreamDiagnostic.scan_status != "unknown",
            ChannelStreamDiagnostic.checked_at < fresh_cutoff,
        )
    ) or 0
    explicit_unknown = db.scalar(
        select(func.count()).select_from(ChannelStreamDiagnostic).where(
            (ChannelStreamDiagnostic.scan_status == "") |
            (ChannelStreamDiagnostic.scan_status == "unknown") |
            (ChannelStreamDiagnostic.scan_status.is_(None))
        )
    ) or 0
    stale_count = stale_ok_count + stale_abnormal_count
    unknown_count = max(channel_total - diagnostic_channel_total, 0) + explicit_unknown
    latest = db.scalar(select(func.max(ChannelStreamDiagnostic.checked_at)))
    by_error_class = db.execute(
        select(ChannelStreamDiagnostic.error_class, func.count())
        .where(
            ChannelStreamDiagnostic.scan_status != "ok",
            ChannelStreamDiagnostic.scan_status != "unknown",
            ChannelStreamDiagnostic.checked_at >= fresh_cutoff,
        )
        .group_by(ChannelStreamDiagnostic.error_class)
        .order_by(func.count().desc())
    ).all()
    return {
        "channel_total": channel_total,
        "total": total,
        "diagnostic_channel_total": diagnostic_channel_total,
        "ok": ok_count,
        "abnormal": abnormal_count,
        "stale": stale_count,
        "stale_ok": stale_ok_count,
        "stale_abnormal": stale_abnormal_count,
        "unknown": unknown_count,
        "fresh_hours": STREAM_DIAGNOSTIC_FRESH_HOURS,
        "latest_checked_at": latest.isoformat(timespec="seconds") if latest else "",
        "by_error_class": [
            {
                "error_class": row[0] or "unknown",
                "label": _diagnostic_label(row[0] or "", "failed"),
                "count": row[1],
            }
            for row in by_error_class
        ],
    }


@router.get("/stream-diagnostics")
def list_stream_diagnostics(
    db: Session = Depends(get_db),
    scan_status: str | None = Query(default=None),
    error_class: str | None = Query(default=None),
    q: str = Query(default=""),
    limit: int = Query(default=200, ge=20, le=1200),
) -> list[dict]:
    stmt = select(ChannelStreamDiagnostic, VideoChannel).join(VideoChannel, VideoChannel.id == ChannelStreamDiagnostic.channel_id)
    if scan_status:
        stmt = stmt.where(ChannelStreamDiagnostic.scan_status == scan_status)
    if error_class:
        stmt = stmt.where(ChannelStreamDiagnostic.error_class == error_class)
    keyword = q.strip()
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            ChannelStreamDiagnostic.camera_ip.ilike(like)
            | VideoChannel.channel_name.ilike(like)
            | VideoChannel.channel_no.ilike(like)
            | ChannelStreamDiagnostic.error_message.ilike(like)
        )
    rows = db.execute(stmt.order_by(ChannelStreamDiagnostic.scan_status.desc(), ChannelStreamDiagnostic.id.desc()).limit(limit)).all()
    return [
        {
            **(freshness := _diagnostic_freshness(diag)),
            "channel_id": diag.channel_id,
            "channel_no": channel.channel_no,
            "camera_ip": diag.camera_ip or channel.camera_ip,
            "camera_name": normalize_text(channel.channel_name),
            "platform_ip": diag.platform_ip,
            "scan_status": diag.scan_status,
            "error_class": diag.error_class,
            "label": _diagnostic_label(diag.error_class, diag.scan_status),
            "error": normalize_text(diag.error_message),
            "rtsp_url": diag.rtsp_url,
            "elapsed_ms": diag.elapsed_ms,
            "source_report": diag.source_report,
            "checked_at": diag.checked_at.isoformat(timespec="seconds") if diag.checked_at else "",
            "fresh_hours": STREAM_DIAGNOSTIC_FRESH_HOURS,
        }
        for diag, channel in rows
    ]


def _parse_position_float(payload: dict, primary: str, fallback: str) -> float:
    try:
        return float(payload.get(primary, payload.get(fallback)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid_{primary}") from exc


def _device_status_from_review_status(review_status: str) -> str:
    review_status = normalize_text(review_status).strip()
    if review_status in {"field_verified", "manual_verified", "verified"}:
        return "verified"
    if review_status in {"pending_field_review", "needs_field_check", "conflict", "conflicted"}:
        return "pending_field_review"
    return review_status


def _sync_topology_node_to_asset(db: Session, node: NetworkTopologyNode, payload: dict, note: str, review_status: str) -> AssetDevice | None:
    asset = db.get(AssetDevice, node.device_id) if node.device_id else None
    if not asset and node.ip:
        asset = db.scalar(
            select(AssetDevice)
            .where(
                AssetDevice.device_status != "archived",
                (AssetDevice.management_ip == node.ip) | (AssetDevice.service_ip == node.ip),
            )
            .order_by(AssetDevice.id.desc())
            .limit(1)
        )
    if not asset:
        return None

    area_id = _safe_int(payload.get("area_id") or payload.get("areaId"))
    area_name = normalize_text(
        payload.get("area_name")
        or payload.get("areaName")
        or payload.get("area_display_name")
        or payload.get("areaDisplayName")
        or ""
    ).strip()
    if area_id and db.get(AssetArea, area_id):
        asset.area_id = area_id
    elif area_name:
        area = _get_or_create_area_by_name(db, area_name)
        if area:
            asset.area_id = area.id
    elif not asset.area_id and (node.floor or node.weak_current_room):
        inferred_area_name = " / ".join(
            part for part in ("中央大道", normalize_text(node.floor), normalize_text(node.weak_current_room)) if part
        )
        area = _get_or_create_area_by_name(db, inferred_area_name)
        if area:
            asset.area_id = area.id

    device_status = _device_status_from_review_status(review_status)
    if device_status and asset.device_status != "archived":
        asset.device_status = device_status
    sync_note = normalize_text(
        f"拓扑编辑器同步：review_status={review_status or '-'}；position_source=manual；"
        f"坐标=({node.pos_x}, {node.pos_y})"
        + (f"；{note}" if note else "")
    )
    asset.notes = _append_note(asset.notes or "", sync_note)
    asset.updated_at = datetime.utcnow()
    return asset


def _update_topology_node_position(db: Session, payload: dict) -> dict:
    try:
        node_id = payload.get("node_id") or payload.get("nodeId")
        raw_id = payload.get("id") or payload.get("ID")
        node_key = normalize_text(payload.get("node_key") or payload.get("nodeKey") or "").strip()
        ip = normalize_text(payload.get("ip") or payload.get("IP") or "").strip()
        device_id = payload.get("device_id") or payload.get("deviceId")
        x = _parse_position_float(payload, "x", "pos_x")
        y = _parse_position_float(payload, "y", "pos_y")

        if not node_id and raw_id:
            raw_id_text = normalize_text(str(raw_id)).strip()
            if raw_id_text.isdigit():
                node_id = int(raw_id_text)
            elif not node_key:
                node_key = raw_id_text

        stmt = select(NetworkTopologyNode)
        if node_id:
            stmt = stmt.where(NetworkTopologyNode.id == int(node_id))
        elif node_key:
            stmt = stmt.where(NetworkTopologyNode.node_key == node_key)
        elif device_id:
            stmt = stmt.where(NetworkTopologyNode.device_id == int(device_id))
        elif ip:
            stmt = stmt.where(NetworkTopologyNode.ip == ip)
        else:
            raise HTTPException(status_code=400, detail="node_id_or_node_key_or_ip_required")

        node = db.scalar(stmt.order_by(NetworkTopologyNode.id.desc()).limit(1))
        if not node:
            raise HTTPException(status_code=404, detail="topology_node_not_found")

        node.pos_x = x
        node.pos_y = y
        node.position_source = "manual"
        review_status = normalize_text(payload.get("review_status") or payload.get("reviewStatus") or "field_verified").strip()
        node.review_status = review_status
        note = normalize_text(payload.get("manual_note") or payload.get("note") or "现场拖拽手动固化坐标")
        node.manual_note = f"{normalize_text(node.manual_note)} | {note}".strip(" |") if node.manual_note else note
        if "floor" in payload:
            node.floor = normalize_text(payload.get("floor"))
        if "weak_current_room" in payload or "weakCurrentRoom" in payload:
            node.weak_current_room = normalize_text(payload.get("weak_current_room") or payload.get("weakCurrentRoom"))
        node.updated_at = datetime.utcnow()
        asset = _sync_topology_node_to_asset(db, node, payload, note, review_status)
        db.commit()
        return {
            "ok": True,
            "node_id": node.id,
            "asset_device_id": asset.id if asset else None,
            "node_key": node.node_key,
            "ip": node.ip,
            "x": node.pos_x,
            "y": node.pos_y,
            "position_source": node.position_source,
            "review_status": node.review_status,
        }
    except Exception:
        db.rollback()
        raise


@router.post("/update_pos")
@router.post("/update-position")
@router.post("/position")
@router.put("/update_pos")
@router.patch("/update_pos")
def update_asset_position(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    return _update_topology_node_position(db, payload)


@router.post("/clear_pos")
@router.post("/clear-position")
@router.post("/position/clear")
def clear_asset_topology_binding(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    node_id = _safe_int(payload.get("node_id") or payload.get("topology_node_id"))
    raw_id_text = normalize_text(str(payload.get("id") or ""))
    node_key = normalize_text(str(payload.get("node_key") or payload.get("nodeKey") or ""))
    device_id = _safe_int(payload.get("device_id") or payload.get("deviceId"))
    ip = normalize_text(str(payload.get("ip") or payload.get("camera_ip") or ""))
    if not node_id and raw_id_text:
        if raw_id_text.isdigit():
            node_id = _safe_int(raw_id_text)
        else:
            node_key = raw_id_text

    stmt = select(NetworkTopologyNode)
    if node_id:
        stmt = stmt.where(NetworkTopologyNode.id == int(node_id))
    elif node_key:
        stmt = stmt.where(NetworkTopologyNode.node_key == node_key)
    elif device_id:
        stmt = stmt.where(NetworkTopologyNode.device_id == int(device_id))
    elif ip:
        stmt = stmt.where(NetworkTopologyNode.ip == ip)
    else:
        raise HTTPException(status_code=400, detail="node_id_or_node_key_or_ip_required")

    node = db.scalar(stmt.order_by(NetworkTopologyNode.id.desc()).limit(1))
    if not node:
        raise HTTPException(status_code=404, detail="topology_node_not_found")

    removed_edge_ids: list[int] = []
    edge_id = _safe_int(payload.get("edge_id") or payload.get("edgeId") or payload.get("topology_edge_id"))
    if edge_id:
        edge = db.get(NetworkTopologyEdge, edge_id)
        if edge and edge.domain_id == node.domain_id and edge.dst_node_key == node.node_key:
            removed_edge_ids.append(edge.id)
            db.delete(edge)
    else:
        incoming_edges = db.scalars(
            select(NetworkTopologyEdge).where(
                NetworkTopologyEdge.domain_id == node.domain_id,
                NetworkTopologyEdge.dst_node_key == node.node_key,
            )
        ).all()
        for edge in incoming_edges:
            removed_edge_ids.append(edge.id)
            db.delete(edge)

    node.parent_node_key = ""
    node.parent_ip = ""
    node.pos_x = None
    node.pos_y = None
    node.position_source = "orphan_pool"
    node.review_status = "pending_field_review"
    note = normalize_text(payload.get("manual_note") or payload.get("note") or "拓扑编辑器退回待核实资产池")
    node.manual_note = f"{normalize_text(node.manual_note)} | {note}".strip(" |") if node.manual_note else note
    node.updated_at = datetime.utcnow()
    db.commit()
    return {
        "ok": True,
        "node_id": node.id,
        "node_key": node.node_key,
        "ip": node.ip,
        "removed_edge_ids": removed_edge_ids,
        "position_source": node.position_source,
        "review_status": node.review_status,
    }


@router.put("/channels/{channel_id}/topology-binding")
def update_channel_topology_binding(
    channel_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    channel = db.get(VideoChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    switch_ip = normalize_text(payload.get("switch_ip") or "").strip()
    port_name = normalize_text(payload.get("port_name") or "").strip()
    vlan_id = normalize_text(payload.get("vlan_id") or "").strip()
    evidence_note = normalize_text(payload.get("evidence_note") or "").strip()
    current_link = _apply_manual_topology_binding(
        db,
        channel,
        switch_ip=switch_ip,
        port_name=port_name,
        vlan_id=vlan_id,
        evidence_note=evidence_note,
    )

    db.commit()
    db.refresh(current_link)

    rows = [channel]
    device_map, area_map, port_map, access_links = _build_channel_context(db, rows)
    diagnostic_map = _load_stream_diagnostics(db, {channel.id})
    return {
        "ok": True,
        "link_id": current_link.id,
        "switch_ip": switch_ip,
        "port_name": port_name,
        "channel": _channel_payload(channel, device_map, area_map, port_map, access_links, diagnostic_map),
    }


@router.post("/field-validation/import-camera-sheet")
async def import_field_validation_camera_sheet(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    from app.api.integrations import _build_fucheng_repair_plan

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="csv_file_required")

    raw = await file.read()
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text.strip():
        raise HTTPException(status_code=400, detail="csv_file_empty")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="csv_header_missing")

    repair_before = _compact_repair_plan_summary(_build_fucheng_repair_plan(db))

    processed = 0
    matched = 0
    mac_updated = 0
    area_updated = 0
    binding_updated = 0
    skipped = 0
    unresolved_ips: list[str] = []

    for row in reader:
        processed += 1
        camera_ip = normalize_text(row.get("camera_ip") or "").strip()
        if not camera_ip:
            skipped += 1
            continue

        camera = db.scalar(
            select(AssetDevice).where(
                AssetDevice.device_type == "camera",
                AssetDevice.device_status != "archived",
                ((AssetDevice.management_ip == camera_ip) | (AssetDevice.service_ip == camera_ip)),
            )
        )
        channels: list[VideoChannel] = []
        if camera:
            channels = db.scalars(
                select(VideoChannel).where(VideoChannel.camera_asset_id == camera.id).order_by(VideoChannel.id.asc())
            ).all()
        if not camera:
            channels = db.scalars(
                select(VideoChannel).where(VideoChannel.camera_ip == camera_ip).order_by(VideoChannel.id.asc())
            ).all()
            if channels and channels[0].camera_asset_id:
                camera = db.get(AssetDevice, channels[0].camera_asset_id)

        if not camera:
            skipped += 1
            if len(unresolved_ips) < 20:
                unresolved_ips.append(camera_ip)
            continue

        matched += 1
        normalized_mac = _normalize_mac_text(normalize_text(row.get("collected_mac") or "").strip())
        if normalized_mac and normalized_mac != _normalize_mac_text(camera.mac_address or ""):
            camera.mac_address = normalized_mac
            mac_updated += 1

        collector = normalize_text(row.get("collector") or "").strip()
        verified_at = normalize_text(row.get("verified_at") or "").strip()
        collected_area_raw = normalize_text(row.get("collected_area") or "").strip()
        collected_area, collected_area_tail = _normalize_area_scope(collected_area_raw)
        switch_ip = normalize_text(row.get("collected_switch_ip") or "").strip()
        port_name = normalize_text(row.get("collected_port") or "").strip()
        field_note = normalize_text(row.get("field_note") or row.get("notes") or "").strip()

        target_channel = channels[0] if channels else db.scalar(
            select(VideoChannel).where(VideoChannel.camera_asset_id == camera.id).order_by(VideoChannel.id.asc())
        )
        if target_channel and collected_area:
            note_payload = _parse_json_notes(target_channel.notes)
            if normalize_text(note_payload.get("direct_area") or "").strip() != collected_area:
                note_payload["direct_area"] = collected_area
                if collected_area_raw and collected_area_raw != collected_area:
                    note_payload["direct_area_raw"] = collected_area_raw
                if target_channel.camera_ip:
                    note_payload["direct_point_ip"] = target_channel.camera_ip
                    note_payload["direct_point_label"] = target_channel.camera_ip
                if collected_area_tail:
                    note_payload["field_area_tail"] = collected_area_tail
                note_payload["area_field_validation"] = {
                    "source": "field_validation_import",
                    "collector": collector,
                    "verified_at": verified_at,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                target_channel.notes = json.dumps(note_payload, ensure_ascii=False)
                area_updated += 1
            area = _get_or_create_area_by_name(db, collected_area)
            if area and camera.area_id != area.id:
                camera.area_id = area.id

        notes: list[str] = []
        if collector:
            notes.append(f"核验人：{collector}")
        if verified_at:
            notes.append(f"核验时间：{verified_at}")
        if collected_area:
            notes.append(f"现场区域：{collected_area}")
        if collected_area_raw and collected_area_raw != collected_area:
            notes.append(f"现场原始区域字段：{collected_area_raw}")
        if switch_ip and port_name:
            notes.append(f"现场链路：{switch_ip} / {port_name}")
        if field_note:
            notes.append(f"现场备注：{field_note}")
        note_text = "；".join(notes)
        if note_text:
            camera.notes = _append_note(camera.notes or "", note_text)

        if target_channel and switch_ip and port_name:
            _apply_manual_topology_binding(
                db,
                target_channel,
                switch_ip=switch_ip,
                port_name=port_name,
                vlan_id=normalize_text(row.get("collected_vlan") or "").strip(),
                evidence_note=note_text,
            )
            binding_updated += 1

    db.commit()
    repair_after = _compact_repair_plan_summary(_build_fucheng_repair_plan(db))
    import_event = {
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "filename": filename,
        "processed": processed,
        "matched": matched,
        "mac_updated": mac_updated,
        "area_updated": area_updated,
        "binding_updated": binding_updated,
        "skipped": skipped,
        "repair_before": repair_before,
        "repair_after": repair_after,
        "repair_delta": {
            "area_missing_reduced": max(repair_before["area_missing_total"] - repair_after["area_missing_total"], 0),
            "area_manual_reduced": max(repair_before["area_manual_total"] - repair_after["area_manual_total"], 0),
            "area_task_groups_reduced": max(
                repair_before["area_task_group_total"] - repair_after["area_task_group_total"],
                0,
            ),
        },
    }
    _append_field_validation_history(import_event)
    progress_summary = _build_field_validation_progress_summary(db)
    return {
        "ok": True,
        "filename": filename,
        "processed": processed,
        "matched": matched,
        "mac_updated": mac_updated,
        "area_updated": area_updated,
        "binding_updated": binding_updated,
        "skipped": skipped,
        "unresolved_ips": unresolved_ips,
        "repair_before": repair_before,
        "repair_after": repair_after,
        "repair_delta": import_event["repair_delta"],
        "progress_summary": progress_summary,
    }


@router.post("/field-validation/import-switch-gap-sheet")
async def import_field_validation_switch_gap_sheet(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="csv_file_required")

    raw = await file.read()
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text.strip():
        raise HTTPException(status_code=400, detail="csv_file_empty")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="csv_header_missing")

    processed = 0
    matched = 0
    noted = 0
    status_updated = 0
    skipped = 0
    unresolved_ips: list[str] = []

    for row in reader:
        processed += 1
        switch_ip = normalize_text(row.get("switch_ip") or "").strip()
        if not switch_ip:
            skipped += 1
            continue

        switch = db.scalar(
            select(AssetDevice).where(
                AssetDevice.device_type == "switch",
                AssetDevice.device_status != "archived",
                AssetDevice.management_ip == switch_ip,
            )
        )
        if not switch:
            skipped += 1
            if len(unresolved_ips) < 20:
                unresolved_ips.append(switch_ip)
            continue

        matched += 1
        gap_reason = normalize_text(row.get("gap_reason") or "").strip()
        field_result = normalize_text(row.get("field_result") or "").strip()
        field_note = normalize_text(row.get("field_note") or "").strip()
        probe_status = normalize_text(row.get("probe_status") or "").strip()

        notes: list[str] = []
        if gap_reason:
            notes.append(f"缺口类型：{gap_reason}")
        if field_result:
            notes.append(f"现场结果：{field_result}")
        if field_note:
            notes.append(f"现场备注：{field_note}")
        if notes:
            switch.notes = _append_note(switch.notes or "", "；".join(notes))
            switch.device_status = "verified"
            noted += 1

        lower_result = f"{field_result} {field_note} {probe_status}".lower()
        target_health = None
        if any(keyword in lower_result for keyword in ["offline", "离线", "不通", "telnet_closed", "closed", "断网"]):
            target_health = "offline"
        elif any(keyword in lower_result for keyword in ["warning", "异常", "汇聚", "级联", "uplink", "trunk", "观察"]):
            target_health = "warning"
        elif field_result and any(keyword in lower_result for keyword in ["正常", "online", "直连", "已核实", "可达"]):
            target_health = "online"
        if target_health and switch.health_state != target_health:
            switch.health_state = target_health
            status_updated += 1

    db.commit()
    return {
        "ok": True,
        "filename": filename,
        "processed": processed,
        "matched": matched,
        "noted": noted,
        "status_updated": status_updated,
        "skipped": skipped,
        "unresolved_ips": unresolved_ips,
    }


@router.get("/channels")
def list_channels(
    db: Session = Depends(get_db),
    channel_id: int | None = None,
    protocol_type: str | None = None,
    source_type: str | None = None,
    source_management_ip: str | None = Query(default=None),
    area_id: int | None = None,
    switch_binding_state: str | None = Query(default=None),
    q: str = Query(default=""),
    limit: int = 240,
) -> list[dict]:
    stmt = (
        select(VideoChannel)
        .join(AssetDevice, AssetDevice.id == VideoChannel.parent_device_id)
    )
    if channel_id:
        stmt = stmt.where(VideoChannel.id == channel_id)
    if protocol_type:
        stmt = stmt.where(VideoChannel.protocol_type == protocol_type)
    if source_type:
        stmt = stmt.where(AssetDevice.primary_source_type == source_type)
    source_management_ip = (source_management_ip or "").strip()
    if source_management_ip:
        stmt = stmt.where(AssetDevice.management_ip == source_management_ip)
    keyword = q.strip()
    output_limit = min(max(limit, 20), 1200)
    fetch_limit = 1200 if keyword else output_limit
    rows = db.scalars(stmt.order_by(VideoChannel.id.desc()).limit(fetch_limit)).all()
    device_map, area_map, port_map, access_links = _build_channel_context(db, rows)
    diagnostic_map = _load_stream_diagnostics(db, {row.id for row in rows})
    payload_rows = [
        _channel_payload(row, device_map, area_map, port_map, access_links, diagnostic_map)
        for row in rows
    ]
    if keyword:
        keyword_lower = keyword.lower()
        payload_rows = [
            row
            for row in payload_rows
            if any(
                keyword_lower in str(row.get(field) or "").lower()
                for field in (
                    "channel_no",
                    "channel_name",
                    "camera_ip",
                    "camera_label",
                    "parent_label",
                    "source_management_ip",
                    "area_display_name",
                    "direct_area",
                    "switch_label",
                    "switch_ip",
                )
            )
        ]
    if area_id:
        payload_rows = [row for row in payload_rows if row.get("area_id") == area_id]
    if switch_binding_state in {"bound", "pending"}:
        payload_rows = [row for row in payload_rows if row.get("switch_binding_state") == switch_binding_state]
    return payload_rows[:output_limit]


@router.get("/device-types")
def device_type_breakdown(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(AssetDevice.device_type, func.count()).group_by(AssetDevice.device_type).order_by(func.count().desc())
    ).all()
    return [{"device_type": row[0], "count": row[1]} for row in rows]


@router.get("/source-types")
def source_type_breakdown(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(PlatformSource.source_type, func.count()).group_by(PlatformSource.source_type).order_by(func.count().desc())
    ).all()
    return [{"source_type": row[0], "count": row[1]} for row in rows]


@router.get("/summary")
def asset_summary(db: Session = Depends(get_db)) -> dict:
    recent_devices = db.scalars(select(AssetDevice).order_by(AssetDevice.id.desc()).limit(8)).all()
    recent_channels = db.scalars(select(VideoChannel).order_by(VideoChannel.id.desc()).limit(8)).all()
    recent_links = db.scalars(select(TopologyLink).order_by(TopologyLink.id.desc()).limit(8)).all()
    recent_device_area_ids = {row.area_id for row in recent_devices if row.area_id}
    channel_device_map, channel_area_map, port_map, access_links = _build_channel_context(db, recent_channels)
    diagnostic_map = _load_stream_diagnostics(db, {row.id for row in recent_channels})
    channel_area_ids = recent_device_area_ids | {row.area_id for row in channel_device_map.values() if row.area_id}
    area_map = (
        {
            row.id: row
            for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(channel_area_ids))).all()
        }
        if channel_area_ids
        else {}
    )
    return {
        "recent_devices": [
            {
                "id": row.id,
                "display_name": normalize_text(row.hostname) or row.management_ip or f"设备 {row.id}",
                "name": normalize_text(row.hostname),
                "ip_address": row.management_ip,
                "area_name": normalize_text(area_map[row.area_id].display_name) if row.area_id in area_map else "",
                "device_type": row.device_type,
                "vendor": normalize_text(row.vendor),
                "model": normalize_text(row.model),
                "hostname": normalize_text(row.hostname),
                "management_ip": row.management_ip,
                "primary_source_type": row.primary_source_type,
                "source_type": row.primary_source_type,
            }
            for row in recent_devices
        ],
        "recent_channels": [
            (
                lambda payload: {
                    **payload,
                    "area_name": payload.get("area_display_name", ""),
                }
            )(_channel_payload(row, channel_device_map, channel_area_map, port_map, access_links, diagnostic_map))
            for row in recent_channels
        ],
        "recent_links": [
            {
                "id": row.id,
                "src_device_id": row.src_device_id,
                "src_port_id": row.src_port_id,
                "dst_device_id": row.dst_device_id,
                "link_type": row.link_type,
                "confidence": row.confidence,
                "evidence_type": row.evidence_type,
            }
            for row in recent_links
        ],
    }


@router.get("/link-evidence")
def link_evidence_breakdown(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(TopologyLink.evidence_type, func.count())
        .group_by(TopologyLink.evidence_type)
        .order_by(func.count().desc())
    ).all()
    return [{"evidence_type": row[0], "count": row[1]} for row in rows]

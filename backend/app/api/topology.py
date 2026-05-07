from collections import Counter, defaultdict
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.asset import AssetArea, AssetDevice, NetworkPort, SwitchLiveProbe, TopologyLink, VideoChannel
from app.models.control_platform import ControlPlatformRegistration
from app.models.user_account import UserAccount
from app.services.area_scope import area_scope_sort_key, describe_area_scope
from app.services.auth import require_roles
from app.services.network_architecture import (
    central_avenue_architecture_payload,
    create_architecture_edge,
    create_architecture_node,
    delete_architecture_edge,
    delete_architecture_node,
    rebuild_central_avenue_architecture,
    update_architecture_node,
)
from app.services.switch_live_probe import list_switch_probes, probe_switch_live
from app.services.text_normalize import normalize_text


router = APIRouter()


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


def _switch_role_guess(reason: str, direct_match_count: int) -> tuple[str, str]:
    if direct_match_count > 0:
        return ("camera_access", "接入交换机")
    mapping = {
        "mac_table_rich_but_camera_mac_unmatched": ("suspected_aggregation", "疑似汇聚/级联"),
        "likely_aggregation_or_unknown_camera_mac": ("suspected_aggregation", "疑似汇聚/级联"),
        "arp_only_no_forwarding_table": ("unknown", "待现场核实"),
        "no_visible_forwarding_table": ("unknown", "待现场核实"),
        "low_signal_needs_manual_review": ("unknown", "待现场核实"),
        "telnet_closed_or_unreachable": ("unreachable", "不可达/Telnet关闭"),
    }
    return mapping.get(reason, ("unknown", "待现场核实"))


def _probe_payload(row: SwitchLiveProbe | None) -> dict:
    if not row:
        return {
            "probe_status": "unknown",
            "telnet_status": "",
            "http_status": "",
            "https_status": "",
            "ssh_status": "",
            "version_text": "",
            "arp_entry_count": 0,
            "camera_match_count": 0,
            "l2_mac_count": 0,
            "error_message": "",
            "checked_at": "",
        }
    return {
        "probe_status": row.probe_status,
        "telnet_status": row.telnet_status,
        "http_status": row.http_status,
        "https_status": row.https_status,
        "ssh_status": row.ssh_status,
        "version_text": normalize_text(row.version_text),
        "arp_entry_count": row.arp_entry_count,
        "camera_match_count": row.camera_match_count,
        "l2_mac_count": row.l2_mac_count,
        "error_message": normalize_text(row.error_message),
        "checked_at": row.checked_at.isoformat(timespec="seconds") if row.checked_at else "",
    }


def _device_map(db: Session, ids: set[int]) -> dict[int, AssetDevice]:
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(ids))).all()
    }


def _classify_vlan_zone(vlan_id: str) -> str:
    value = (vlan_id or "").strip().lower()
    if not value:
        return "未标注 VLAN"
    if value == "2":
        return "视频监控域"
    return "风控/电控或其他业务域"


def _infer_camera_zone_from_ip(camera_ip: str) -> str:
    ip = (camera_ip or "").strip()
    if ip.startswith("10.0."):
        return "视频监控域"
    if ip.startswith("192.168."):
        return "外部分域/录像域"
    return "未知域"


def _collect_vlan_attribution_rows(db: Session) -> tuple[list[dict], list[str]]:
    links = db.scalars(
        select(TopologyLink).where(
            TopologyLink.link_type == "physical",
            TopologyLink.src_port_id.is_not(None),
            TopologyLink.src_device_id.is_not(None),
            TopologyLink.dst_device_id.is_not(None),
        )
    ).all()
    if not links:
        return [], ["当前没有可用于归因的物理链路。请先执行基础导入。"]

    device_ids = {
        device_id
        for row in links
        for device_id in (row.src_device_id, row.dst_device_id)
        if device_id is not None
    }
    port_ids = {row.src_port_id for row in links if row.src_port_id}
    devices = _device_map(db, device_ids)
    ports = {
        row.id: row
        for row in db.scalars(select(NetworkPort).where(NetworkPort.id.in_(port_ids))).all()
    } if port_ids else {}

    rows: list[dict] = []
    for row in links:
        src = devices.get(row.src_device_id)
        dst = devices.get(row.dst_device_id)
        if not src or not dst:
            continue
        if src.device_type != "switch" or dst.device_type != "camera":
            continue
        port = ports.get(row.src_port_id)
        vlan = (port.vlan_id if port else "") or ""
        zone = _classify_vlan_zone(vlan) if vlan else _infer_camera_zone_from_ip(dst.management_ip)
        rows.append(
            {
                "link_id": row.id,
                "switch_device_id": src.id,
                "switch_ip": src.management_ip,
                "switch_label": normalize_text(src.hostname or src.management_ip),
                "port_id": port.id if port else None,
                "port_name": normalize_text(port.port_name) if port else "-",
                "camera_device_id": dst.id,
                "camera_ip": dst.management_ip,
                "camera_label": normalize_text(dst.hostname or dst.management_ip),
                "vlan_id": vlan,
                "zone": zone,
                "source": "port_vlan" if vlan else "ip_inference",
            }
        )

    total = len(rows)
    unattributed = sum(1 for item in rows if not item["vlan_id"])
    recommendations: list[str] = []
    if unattributed > 0:
        recommendations.append("存在未标注 VLAN 的链路，建议执行 tg-cos-vlan 回填并补充交换机端口表。")
    if total > 0 and unattributed / total >= 0.35:
        recommendations.append("未归因比例较高，建议优先采集交换机端口 VLAN 明细并建立端口级导入。")
    if not recommendations:
        recommendations.append("当前端口 VLAN 归因状态良好，可继续推进区域级拓扑联动。")
    return rows, recommendations


@router.get("/summary")
def topology_summary(db: Session = Depends(get_db)) -> dict:
    device_type_rows = db.execute(
        select(AssetDevice.device_type, func.count())
        .group_by(AssetDevice.device_type)
        .order_by(func.count().desc())
    ).all()
    source_rows = db.execute(
        select(AssetDevice.primary_source_type, func.count())
        .group_by(AssetDevice.primary_source_type)
        .order_by(func.count().desc())
    ).all()
    evidence_rows = db.execute(
        select(TopologyLink.evidence_type, func.count())
        .group_by(TopologyLink.evidence_type)
        .order_by(func.count().desc())
    ).all()
    vlan_rows = db.execute(
        select(NetworkPort.vlan_id, func.count(NetworkPort.id))
        .where(NetworkPort.vlan_id != "")
        .group_by(NetworkPort.vlan_id)
        .order_by(func.count(NetworkPort.id).desc())
    ).all()
    control_vlan_rows = db.execute(
        select(
            ControlPlatformRegistration.vlan_id,
            ControlPlatformRegistration.vlan_name,
            func.count(ControlPlatformRegistration.id),
        )
        .group_by(ControlPlatformRegistration.vlan_id, ControlPlatformRegistration.vlan_name)
        .order_by(func.count(ControlPlatformRegistration.id).desc())
    ).all()

    recent_links = db.scalars(
        select(TopologyLink).order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc()).limit(80)
    ).all()

    involved_device_ids = {
        device_id
        for link in recent_links
        for device_id in (link.src_device_id, link.dst_device_id)
        if device_id is not None
    }

    devices = _device_map(db, involved_device_ids)

    downstream_counts = defaultdict(int)
    for link in recent_links:
        if link.src_device_id and link.dst_device_id:
            src = devices.get(link.src_device_id)
            dst = devices.get(link.dst_device_id)
            if src and dst and src.device_type == "switch" and dst.device_type == "camera":
                downstream_counts[src.id] += 1

    switch_spotlights = [
        {
            "id": device_id,
            "label": normalize_text(devices[device_id].hostname or devices[device_id].management_ip),
            "management_ip": devices[device_id].management_ip,
            "camera_count": count,
        }
        for device_id, count in sorted(downstream_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    ]
    vlan_breakdown = []
    for row in vlan_rows[:16]:
        vlan_breakdown.append(
            {
                "vlan_id": row[0] or "unknown",
                "port_count": row[1],
                "registration_count": 0,
                "zone": _classify_vlan_zone(row[0] or ""),
                "source": "switch_port",
            }
        )

    if not vlan_breakdown:
        vlan_breakdown.append(
            {
                "vlan_id": "2",
                "port_count": 0,
                "registration_count": 0,
                "zone": "视频监控域",
                "source": "known_fact",
            }
        )
        for row in control_vlan_rows:
            vlan_breakdown.append(
                {
                    "vlan_id": row[0] or "unknown",
                    "port_count": 0,
                    "registration_count": row[2],
                    "zone": _classify_vlan_zone(row[0] or ""),
                    "source": "control_registration",
                }
            )

    zone_counter = Counter(item["zone"] for item in vlan_breakdown)

    area_breakdown = []
    for area, count in db.execute(
        select(AssetArea, func.count(AssetDevice.id))
        .join(AssetDevice, AssetDevice.area_id == AssetArea.id)
        .where(AssetDevice.device_status != "archived")
        .group_by(AssetArea.id)
    ).all():
        scope = describe_area_scope(area.display_name)
        area_breakdown.append(
            {
                "area_id": area.id,
                "area": scope["summary_label"],
                "menu_label": scope["menu_label"],
                "scope_kind": scope["scope_kind"],
                "sort_rank": scope["sort_rank"],
                "accuracy_label": scope["accuracy_label"],
                "count": count,
            }
        )
    area_breakdown.sort(key=area_scope_sort_key)

    return {
        "device_types": [{"device_type": row[0] or "unknown", "count": row[1]} for row in device_type_rows],
        "source_types": [{"source_type": row[0] or "unknown", "count": row[1]} for row in source_rows],
        "evidence_types": [{"evidence_type": row[0] or "unknown", "count": row[1]} for row in evidence_rows],
        "vlan_breakdown": vlan_breakdown,
        "network_zone_breakdown": [{"zone": key, "count": value} for key, value in zone_counter.items()],
        "area_breakdown": area_breakdown[:12],
        "switch_spotlights": switch_spotlights,
        "spotlight_links": [
            {
                "id": link.id,
                "src_device_id": link.src_device_id,
                "src_label": (
                    normalize_text(devices[link.src_device_id].hostname or devices[link.src_device_id].management_ip)
                    if link.src_device_id in devices
                    else "-"
                ),
                "dst_device_id": link.dst_device_id,
                "dst_label": (
                    normalize_text(devices[link.dst_device_id].hostname or devices[link.dst_device_id].management_ip)
                    if link.dst_device_id in devices
                    else "-"
                ),
                "link_type": link.link_type,
                "evidence_type": link.evidence_type,
                "confidence": link.confidence,
            }
            for link in recent_links[:12]
        ],
    }


@router.get("/architecture/central-avenue")
def topology_central_avenue_architecture(db: Session = Depends(get_db)) -> dict:
    return central_avenue_architecture_payload(db)


@router.post("/architecture/central-avenue/rebuild")
def topology_rebuild_central_avenue_architecture(
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    return rebuild_central_avenue_architecture(db)


@router.put("/architecture/nodes/{node_id}")
def topology_update_architecture_node(
    node_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    try:
        result = update_architecture_node(db, node_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        **result,
        "architecture": central_avenue_architecture_payload(db),
    }


@router.post("/architecture/nodes")
def topology_create_architecture_node(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    try:
        result = create_architecture_node(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **result,
        "architecture": central_avenue_architecture_payload(db),
    }


@router.post("/architecture/edges")
def topology_create_architecture_edge(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    try:
        result = create_architecture_edge(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **result,
        "architecture": central_avenue_architecture_payload(db),
    }


@router.delete("/architecture/nodes/{node_id}")
def topology_delete_architecture_node(
    node_id: int,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    try:
        result = delete_architecture_node(db, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        **result,
        "architecture": central_avenue_architecture_payload(db),
    }


@router.delete("/architecture/edges/{edge_id}")
def topology_delete_architecture_edge(
    edge_id: int,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    try:
        result = delete_architecture_edge(db, edge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        **result,
        "architecture": central_avenue_architecture_payload(db),
    }


@router.get("/switch-live-probe")
def topology_switch_live_probe_list(
    db: Session = Depends(get_db),
    limit: int = 80,
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    switches = db.scalars(
        select(AssetDevice)
        .where(AssetDevice.device_type == "switch", AssetDevice.device_status != "archived")
        .order_by(AssetDevice.management_ip)
        .limit(max(10, min(limit, 500)))
    ).all()
    probe_map = list_switch_probes(db, {row.id for row in switches})
    return {
        "items": [
            {
                "device_id": row.id,
                "label": normalize_text(row.hostname or row.management_ip),
                "management_ip": row.management_ip,
                "health_state": row.health_state,
                **_probe_payload(probe_map.get(row.id)),
            }
            for row in switches
        ]
    }


@router.post("/switch-live-probe/run")
def topology_switch_live_probe_run(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    requested_ips = {
        str(item).strip()
        for item in (payload.get("switch_ips") or [])
        if str(item).strip()
    }
    username = str(payload.get("username") or "admin").strip() or "admin"
    password = str(payload.get("password") or "a12345678").strip() or "a12345678"
    timeout_seconds = float(payload.get("timeout_seconds") or 4.0)
    limit = int(payload.get("limit") or 12)

    stmt = select(AssetDevice).where(
        AssetDevice.device_type == "switch",
        AssetDevice.device_status != "archived",
    )
    if requested_ips:
        stmt = stmt.where(AssetDevice.management_ip.in_(requested_ips))
    else:
        stmt = stmt.where(AssetDevice.primary_source_type.in_(["tg_cos", "manual"])).limit(max(1, min(limit, 80)))
    switches = db.scalars(stmt.order_by(AssetDevice.management_ip)).all()
    if not switches:
        raise HTTPException(status_code=404, detail="switch_not_found")

    results = []
    for switch in switches:
        try:
            results.append(probe_switch_live(db, switch=switch, username=username, password=password, timeout_seconds=timeout_seconds))
        except Exception as exc:
            results.append(
                {
                    "device_id": switch.id,
                    "management_ip": switch.management_ip,
                    "probe_status": "error",
                    "telnet_status": "",
                    "http_status": "",
                    "https_status": "",
                    "ssh_status": "",
                    "version_text": "",
                    "arp_entry_count": 0,
                    "camera_match_count": 0,
                    "l2_mac_count": 0,
                    "error_message": normalize_text(str(exc)),
                    "checked_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
    return {
        "ok": True,
        "count": len(results),
        "results": results,
    }


@router.get("/graph")
def topology_graph(db: Session = Depends(get_db)) -> dict:
    links = db.scalars(select(TopologyLink).order_by(TopologyLink.id.desc()).limit(200)).all()
    device_ids = {
        device_id
        for link in links
        for device_id in (link.src_device_id, link.dst_device_id)
        if device_id is not None
    }
    devices = db.scalars(select(AssetDevice).where(AssetDevice.id.in_(device_ids))).all() if device_ids else []

    area_ids = {device.area_id for device in devices if device.area_id}
    area_map = (
        {
            row.id: row
            for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()
        }
        if area_ids
        else {}
    )

    nodes = []
    for device in devices:
        area = area_map.get(device.area_id)
        nodes.append(
            {
                "id": device.id,
                "label": normalize_text(device.hostname or device.management_ip or f"device-{device.id}"),
                "device_type": device.device_type,
                "vendor": normalize_text(device.vendor),
                "model": normalize_text(device.model),
                "ip": device.management_ip,
                "source_type": device.primary_source_type,
                "area_id": device.area_id,
                "area_display_name": normalize_text(area.display_name) if area else "",
            }
        )

    edges = [
        {
            "id": link.id,
            "source": link.src_device_id,
            "target": link.dst_device_id,
            "source_port_id": link.src_port_id,
            "link_type": link.link_type,
            "evidence_type": link.evidence_type,
            "confidence": link.confidence,
        }
        for link in links
        if link.src_device_id is not None and link.dst_device_id is not None
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_type_count": dict(Counter(node["device_type"] for node in nodes)),
    }


def _ip_sort_key(value: str) -> tuple[int, int, int, int]:
    parts = str(value or "").split(".")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return (999, 999, 999, 999)
    numbers = (numbers + [999, 999, 999, 999])[:4]
    return tuple(numbers)  # type: ignore[return-value]


def _topology_device_payload(device: AssetDevice, area: AssetArea | None = None) -> dict:
    return {
        "id": device.id,
        "label": normalize_text(device.hostname or device.management_ip or f"device-{device.id}"),
        "device_type": device.device_type,
        "vendor": normalize_text(device.vendor),
        "model": normalize_text(device.model),
        "ip": device.management_ip,
        "management_ip": device.management_ip,
        "source_type": device.primary_source_type,
        "area_id": device.area_id,
        "area_display_name": normalize_text(area.display_name) if area else "",
        "health_state": device.health_state,
        "device_status": device.device_status,
    }


@router.get("/switch-focus-options")
def topology_switch_focus_options(
    subnet: str = "10.0.68.",
    limit: int = 500,
    db: Session = Depends(get_db),
) -> dict:
    subnet = str(subnet or "10.0.68.").strip()
    max_rows = max(20, min(int(limit or 500), 1000))
    switches = db.scalars(
        select(AssetDevice)
        .where(
            AssetDevice.device_type == "switch",
            AssetDevice.device_status != "archived",
            AssetDevice.management_ip.like(f"{subnet}%") if subnet else AssetDevice.management_ip != "",
        )
    ).all()
    switches = sorted(switches, key=lambda item: _ip_sort_key(item.management_ip))[:max_rows]
    switch_ids = {row.id for row in switches}

    probe_map = list_switch_probes(db, switch_ids)
    direct_counts = dict(
        db.execute(
            select(TopologyLink.src_device_id, func.count(TopologyLink.id))
            .where(
                TopologyLink.evidence_type == "direct_switch_mac_probe",
                TopologyLink.src_device_id.in_(switch_ids),
            )
            .group_by(TopologyLink.src_device_id)
        ).all()
    ) if switch_ids else {}

    links = db.scalars(
        select(TopologyLink).where(
            TopologyLink.link_type == "physical",
            or_(TopologyLink.src_device_id.in_(switch_ids), TopologyLink.dst_device_id.in_(switch_ids)),
        )
    ).all() if switch_ids else []

    involved_ids = {
        device_id
        for row in links
        for device_id in (row.src_device_id, row.dst_device_id)
        if device_id is not None
    }
    devices = _device_map(db, involved_ids)
    link_counts: Counter[int] = Counter()
    camera_counts: Counter[int] = Counter()
    evidence_counts: dict[int, Counter[str]] = defaultdict(Counter)
    confidence_sum: defaultdict[int, float] = defaultdict(float)

    for row in links:
        switch_id = row.src_device_id if row.src_device_id in switch_ids else row.dst_device_id
        if switch_id not in switch_ids:
            continue
        other_id = row.dst_device_id if switch_id == row.src_device_id else row.src_device_id
        other = devices.get(other_id)
        if other and other.device_status == "archived":
            continue
        link_counts[switch_id] += 1
        confidence_sum[switch_id] += float(row.confidence or 0)
        evidence_counts[switch_id][row.evidence_type or "unknown"] += 1
        if other and other.device_type == "camera":
            camera_counts[switch_id] += 1

    area_ids = {row.area_id for row in switches if row.area_id}
    area_map = {
        row.id: row
        for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()
    } if area_ids else {}

    items = []
    for row in switches:
        probe = probe_map.get(row.id)
        direct_match_count = int(direct_counts.get(row.id, 0) or camera_counts.get(row.id, 0))
        gap_reason = _switch_gap_reason(probe, direct_match_count)
        role_guess, role_label = _switch_role_guess(gap_reason, direct_match_count)
        link_count = int(link_counts.get(row.id, 0))
        items.append(
            {
                **_topology_device_payload(row, area_map.get(row.area_id)),
                "link_count": link_count,
                "camera_count": int(camera_counts.get(row.id, 0)),
                "direct_camera_count": direct_match_count,
                "avg_confidence": round(confidence_sum[row.id] / link_count, 3) if link_count else 0,
                "role_guess": role_guess,
                "role_label": role_label,
                "gap_reason": gap_reason,
                "main_evidence_type": evidence_counts[row.id].most_common(1)[0][0] if evidence_counts[row.id] else "",
                **_probe_payload(probe),
            }
        )

    return {
        "subnet": subnet,
        "total": len(items),
        "items": items,
    }


@router.get("/switch-focus/{switch_id}")
def topology_switch_focus(
    switch_id: int,
    limit: int = 80,
    db: Session = Depends(get_db),
) -> dict:
    switch = db.get(AssetDevice, switch_id)
    if not switch or switch.device_type != "switch" or switch.device_status == "archived":
        raise HTTPException(status_code=404, detail="switch_not_found")

    max_links = max(10, min(int(limit or 80), 300))
    links = db.scalars(
        select(TopologyLink)
        .where(
            TopologyLink.link_type == "physical",
            or_(TopologyLink.src_device_id == switch_id, TopologyLink.dst_device_id == switch_id),
        )
        .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
        .limit(max_links)
    ).all()

    device_ids = {
        device_id
        for row in links
        for device_id in (row.src_device_id, row.dst_device_id)
        if device_id is not None
    }
    device_ids.add(switch.id)
    devices = _device_map(db, device_ids)
    port_ids = {
        port_id
        for row in links
        for port_id in (row.src_port_id, row.dst_port_id)
        if port_id is not None
    }
    ports = {
        row.id: row
        for row in db.scalars(select(NetworkPort).where(NetworkPort.id.in_(port_ids))).all()
    } if port_ids else {}
    area_ids = {row.area_id for row in devices.values() if row.area_id}
    area_map = {
        row.id: row
        for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()
    } if area_ids else {}
    camera_ids = {row.id for row in devices.values() if row.device_type == "camera"}
    camera_ips = {row.management_ip for row in devices.values() if row.device_type == "camera" and row.management_ip}
    channel_map: dict[int, VideoChannel] = {}
    channel_ip_map: dict[str, VideoChannel] = {}
    if camera_ids or camera_ips:
        for channel in db.scalars(
            select(VideoChannel)
            .where(
                or_(
                    VideoChannel.camera_asset_id.in_(camera_ids) if camera_ids else False,
                    VideoChannel.camera_ip.in_(camera_ips) if camera_ips else False,
                )
            )
            .order_by(VideoChannel.camera_asset_id.asc(), VideoChannel.id.asc())
        ).all():
            if channel.camera_asset_id and channel.camera_asset_id not in channel_map:
                channel_map[channel.camera_asset_id] = channel
            if channel.camera_ip and channel.camera_ip not in channel_ip_map:
                channel_ip_map[channel.camera_ip] = channel

    rows = []
    for row in links:
        other_id = row.dst_device_id if row.src_device_id == switch_id else row.src_device_id
        other = devices.get(other_id)
        if not other or other.device_status == "archived":
            continue
        source_port_id = row.src_port_id if row.src_device_id == switch_id else row.dst_port_id
        target_port_id = row.dst_port_id if row.src_device_id == switch_id else row.src_port_id
        source_port = ports.get(source_port_id)
        target_port = ports.get(target_port_id)
        target_node = _topology_device_payload(other, area_map.get(other.area_id))
        target_channel = channel_map.get(other.id) or channel_ip_map.get(other.management_ip)
        if target_channel:
            target_node["channel_id"] = target_channel.id
            target_node["channel_no"] = target_channel.channel_no
        rows.append(
            {
                "id": row.id,
                "source": switch_id,
                "target": other.id,
                "target_channel_id": target_channel.id if target_channel else None,
                "source_port_id": source_port_id,
                "source_port_name": normalize_text(source_port.port_name) if source_port else "",
                "source_vlan_id": source_port.vlan_id if source_port else "",
                "target_port_id": target_port_id,
                "target_port_name": normalize_text(target_port.port_name) if target_port else "",
                "link_type": row.link_type,
                "evidence_type": row.evidence_type,
                "evidence_summary": normalize_text(row.evidence_summary),
                "confidence": row.confidence,
                "switch_node": _topology_device_payload(switch, area_map.get(switch.area_id)),
                "target_node": target_node,
            }
        )

    return {
        "switch": _topology_device_payload(switch, area_map.get(switch.area_id)),
        "link_count": len(rows),
        "links": rows,
    }


@router.get("/skeleton")
def topology_skeleton(db: Session = Depends(get_db)) -> dict:
    switches = db.scalars(
        select(AssetDevice)
        .where(AssetDevice.device_type == "switch", AssetDevice.device_status != "archived")
        .order_by(AssetDevice.management_ip.asc())
    ).all()
    switch_ids = {row.id for row in switches}
    probe_map = list_switch_probes(db, switch_ids)
    direct_counts = dict(
        db.execute(
            select(TopologyLink.src_device_id, func.count(TopologyLink.id))
            .where(
                TopologyLink.evidence_type == "direct_switch_mac_probe",
                TopologyLink.src_device_id.in_(switch_ids),
            )
            .group_by(TopologyLink.src_device_id)
        ).all()
    ) if switch_ids else {}
    area_ids = {row.area_id for row in switches if row.area_id}
    area_map = (
        {
            row.id: row
            for row in db.scalars(select(AssetArea).where(AssetArea.id.in_(area_ids))).all()
        }
        if area_ids
        else {}
    )

    aggregation_candidates: list[dict] = []
    access_switches: list[dict] = []
    review_switches: list[dict] = []
    unreachable_switches: list[dict] = []

    for row in switches:
        probe = probe_map.get(row.id)
        direct_match_count = int(direct_counts.get(row.id, 0))
        gap_reason = _switch_gap_reason(probe, direct_match_count)
        role_guess, role_label = _switch_role_guess(gap_reason, direct_match_count)
        area = area_map.get(row.area_id)
        payload = {
            "id": row.id,
            "label": normalize_text(row.hostname or row.management_ip),
            "management_ip": row.management_ip,
            "area_display_name": normalize_text(area.display_name) if area else "",
            "health_state": row.health_state,
            "role_guess": role_guess,
            "role_label": role_label,
            "gap_reason": gap_reason,
            "camera_count": direct_match_count,
            "arp_entry_count": int(probe.arp_entry_count or 0) if probe else 0,
            "l2_mac_count": int(probe.l2_mac_count or 0) if probe else 0,
            "checked_at": probe.checked_at.isoformat(timespec="seconds") if probe and probe.checked_at else "",
        }
        if role_guess == "camera_access":
            access_switches.append(payload)
        elif role_guess == "suspected_aggregation":
            aggregation_candidates.append(payload)
        elif role_guess == "unreachable":
            unreachable_switches.append(payload)
        else:
            review_switches.append(payload)

    aggregation_candidates.sort(key=lambda item: (-item["l2_mac_count"], -item["arp_entry_count"], item["management_ip"] or ""))
    access_switches.sort(key=lambda item: (-item["camera_count"], item["management_ip"] or ""))
    review_switches.sort(key=lambda item: (-item["l2_mac_count"], -item["arp_entry_count"], item["management_ip"] or ""))
    unreachable_switches.sort(key=lambda item: item["management_ip"] or "")

    camera_rollups = [
        {
            "id": f"camera-rollup-{item['id']}",
            "access_switch_id": item["id"],
            "label": f"{item['camera_count']} 路摄像头",
            "management_ip": item["management_ip"],
            "camera_count": item["camera_count"],
            "area_display_name": item["area_display_name"],
        }
        for item in access_switches
    ]

    manual_uplink_rows = db.scalars(
        select(TopologyLink)
        .where(
            TopologyLink.link_type == "uplink",
            TopologyLink.src_device_id.is_not(None),
            TopologyLink.dst_device_id.is_not(None),
        )
        .order_by(TopologyLink.id.desc())
        .limit(400)
    ).all()
    switch_map = {row.id: row for row in switches}
    manual_uplink_links: list[dict] = []
    manual_uplink_access_ids: set[int] = set()
    for row in manual_uplink_rows:
        source = switch_map.get(row.src_device_id)
        target = switch_map.get(row.dst_device_id)
        if not source or not target:
            continue
        if source.device_status == "archived" or target.device_status == "archived":
            continue
        source_area = area_map.get(source.area_id)
        target_area = area_map.get(target.area_id)
        manual_uplink_links.append(
            {
                "id": row.id,
                "source_id": source.id,
                "source_label": normalize_text(source.hostname or source.management_ip),
                "source_ip": source.management_ip,
                "source_area_display_name": normalize_text(source_area.display_name) if source_area else "",
                "target_id": target.id,
                "target_label": normalize_text(target.hostname or target.management_ip),
                "target_ip": target.management_ip,
                "target_area_display_name": normalize_text(target_area.display_name) if target_area else "",
                "confidence": row.confidence,
                "evidence_type": row.evidence_type,
                "evidence_summary": normalize_text(row.evidence_summary),
            }
        )
        manual_uplink_access_ids.add(target.id)
    manual_uplink_links.sort(key=lambda item: (item["source_ip"] or "", item["target_ip"] or "", item["id"]))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "aggregation": len(aggregation_candidates),
            "access": len(access_switches),
            "review": len(review_switches),
            "unreachable": len(unreachable_switches),
            "manual_uplink": len(manual_uplink_links),
        },
        "aggregation_candidates": aggregation_candidates[:18],
        "access_switches": access_switches[:28],
        "camera_rollups": camera_rollups[:28],
        "review_switches": review_switches[:16],
        "unreachable_switches": unreachable_switches[:12],
        "manual_uplink_links": manual_uplink_links[:120],
        "manual_uplink_access_ids": sorted(manual_uplink_access_ids),
        "notes": [
            "这是系统根据交换机实采自动生成的逻辑骨架，不等同于最终光口级物理拓扑。",
            "汇聚候选来自高 MAC 零摄像头命中交换机；接入交换机来自 direct_switch_mac_probe 命中结果。",
        ],
    }


@router.post("/skeleton/manual-uplinks")
def apply_topology_manual_uplinks(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    aggregation_switch_id = int(payload.get("aggregation_switch_id") or 0)
    access_switch_ids = {
        int(item)
        for item in (payload.get("access_switch_ids") or [])
        if str(item or "").strip().isdigit() and int(item) > 0
    }
    evidence_note = normalize_text(payload.get("evidence_note") or "").strip()

    if not aggregation_switch_id or not access_switch_ids:
        raise HTTPException(status_code=400, detail="aggregation_switch_id_and_access_switch_ids_required")

    aggregation_switch = db.get(AssetDevice, aggregation_switch_id)
    if not aggregation_switch or aggregation_switch.device_type != "switch" or aggregation_switch.device_status == "archived":
        raise HTTPException(status_code=404, detail="aggregation_switch_not_found")

    access_switches = db.scalars(
        select(AssetDevice).where(
            AssetDevice.id.in_(access_switch_ids),
            AssetDevice.device_type == "switch",
            AssetDevice.device_status != "archived",
        )
    ).all()
    access_switch_map = {row.id: row for row in access_switches}
    updated = 0
    skipped = 0
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for access_id in sorted(access_switch_ids):
        access_switch = access_switch_map.get(access_id)
        if not access_switch or access_switch.id == aggregation_switch.id:
            skipped += 1
            continue
        current_link = db.scalar(
            select(TopologyLink)
            .where(
                TopologyLink.link_type == "uplink",
                TopologyLink.dst_device_id == access_switch.id,
            )
            .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
        )
        if not current_link:
            current_link = TopologyLink(link_type="uplink")
            db.add(current_link)

        note_suffix = f"，{evidence_note}" if evidence_note else ""
        current_link.src_device_id = aggregation_switch.id
        current_link.src_port_id = None
        current_link.dst_device_id = access_switch.id
        current_link.dst_port_id = None
        current_link.link_type = "uplink"
        current_link.confidence = 1.0
        current_link.evidence_type = "manual_override"
        current_link.evidence_summary = (
            f"骨架人工勾连：{aggregation_switch.management_ip or aggregation_switch.hostname} -> "
            f"{access_switch.management_ip or access_switch.hostname}{note_suffix}；{now_label}"
        )
        updated += 1

    db.commit()
    return {
        "ok": True,
        "updated": updated,
        "skipped": skipped,
        "aggregation_switch": {
            "id": aggregation_switch.id,
            "label": normalize_text(aggregation_switch.hostname or aggregation_switch.management_ip),
            "ip": aggregation_switch.management_ip,
        },
        "access_switch_count": len(access_switch_ids),
        "skeleton": topology_skeleton(db),
    }


@router.get("/areas/{area_id}")
def topology_area_detail(area_id: int, db: Session = Depends(get_db)) -> dict:
    area = db.get(AssetArea, area_id)
    if not area:
        raise HTTPException(status_code=404, detail="area_not_found")
    area_scope = describe_area_scope(area.display_name)

    devices = db.scalars(
        select(AssetDevice)
        .where(AssetDevice.area_id == area_id)
        .order_by(AssetDevice.device_type, AssetDevice.hostname, AssetDevice.management_ip)
        .limit(160)
    ).all()

    device_ids = {row.id for row in devices}
    links = db.scalars(
        select(TopologyLink)
        .where(
            (TopologyLink.src_device_id.in_(device_ids)) |
            (TopologyLink.dst_device_id.in_(device_ids))
        )
        .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
        .limit(120)
    ).all() if device_ids else []

    related_ids = {
        value
        for row in links
        for value in (row.src_device_id, row.dst_device_id)
        if value is not None
    }
    related_map = _device_map(db, related_ids)

    type_counter = Counter(row.device_type or "unknown" for row in devices)
    source_counter = Counter(row.primary_source_type or "unknown" for row in devices)
    health_counter = Counter(row.health_state or "unknown" for row in devices)

    return {
        "area": {
            "id": area.id,
            "display_name": normalize_text(area.display_name),
            "menu_label": area_scope["menu_label"],
            "scope_kind": area_scope["scope_kind"],
            "accuracy_label": area_scope["accuracy_label"],
            "site": normalize_text(area.site),
            "building": normalize_text(area.building),
            "floor": normalize_text(area.floor),
            "zone": normalize_text(area.zone),
            "weak_current_room": normalize_text(area.weak_current_room),
        },
        "device_count": len(devices),
        "link_count": len(links),
        "device_type_breakdown": [
            {"device_type": key, "count": value}
            for key, value in type_counter.most_common()
        ],
        "source_type_breakdown": [
            {"source_type": key, "count": value}
            for key, value in source_counter.most_common()
        ],
        "health_breakdown": [
            {"health_state": key, "count": value}
            for key, value in health_counter.most_common()
        ],
        "devices": [
            {
                "id": row.id,
                "label": normalize_text(row.hostname or row.management_ip or f"device-{row.id}"),
                "device_type": row.device_type,
                "management_ip": row.management_ip,
                "source_type": row.primary_source_type,
                "health_state": row.health_state,
            }
            for row in devices[:40]
        ],
        "links": [
            {
                "id": row.id,
                "src_label": normalize_text(related_map[row.src_device_id].hostname or related_map[row.src_device_id].management_ip)
                if row.src_device_id in related_map else "-",
                "dst_label": normalize_text(related_map[row.dst_device_id].hostname or related_map[row.dst_device_id].management_ip)
                if row.dst_device_id in related_map else "-",
                "link_type": row.link_type,
                "evidence_type": row.evidence_type,
                "confidence": row.confidence,
            }
            for row in links[:30]
        ],
    }


@router.get("/vlan-attribution")
def topology_vlan_attribution(db: Session = Depends(get_db)) -> dict:
    rows, recommendations = _collect_vlan_attribution_rows(db)
    if not rows:
        return {
            "camera_link_total": 0,
            "attributed_count": 0,
            "unattributed_count": 0,
            "zone_breakdown": [],
            "recommendations": recommendations,
            "samples": [],
        }

    zone_counter: Counter[str] = Counter()
    attributed = 0
    unattributed = 0
    samples: list[dict] = []
    for item in rows:
        if item["vlan_id"]:
            attributed += 1
        else:
            unattributed += 1
        zone_counter[item["zone"]] += 1
        if len(samples) < 18:
            samples.append(
                {
                    "switch_ip": item["switch_ip"],
                    "switch_label": item["switch_label"],
                    "port_name": item["port_name"],
                    "camera_ip": item["camera_ip"],
                    "camera_label": item["camera_label"],
                    "vlan_id": item["vlan_id"],
                    "zone": item["zone"],
                    "source": item["source"],
                }
            )

    return {
        "camera_link_total": len(rows),
        "attributed_count": attributed,
        "unattributed_count": unattributed,
        "zone_breakdown": [{"zone": key, "count": value} for key, value in zone_counter.most_common()],
        "recommendations": recommendations,
        "samples": samples,
    }


@router.get("/vlan-attribution/unattributed")
def topology_unattributed_links(limit: int = 300, db: Session = Depends(get_db)) -> dict:
    rows, _ = _collect_vlan_attribution_rows(db)
    only = [item for item in rows if not item["vlan_id"]]
    capped = only[: max(20, min(limit, 2000))]
    return {
        "total": len(only),
        "rows": capped,
    }


@router.get("/vlan-attribution/unattributed.csv")
def topology_unattributed_links_csv(db: Session = Depends(get_db)) -> Response:
    rows, _ = _collect_vlan_attribution_rows(db)
    only = [item for item in rows if not item["vlan_id"]]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "link_id",
            "switch_ip",
            "switch_label",
            "port_name",
            "camera_ip",
            "camera_label",
            "suggested_zone",
            "suggested_source",
            "manual_vlan_id",
        ]
    )
    for item in only:
        writer.writerow(
            [
                item["link_id"],
                item["switch_ip"],
                item["switch_label"],
                item["port_name"],
                item["camera_ip"],
                item["camera_label"],
                item["zone"],
                item["source"],
                "",
            ]
        )
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=topology-unattributed-links.csv; "
                "filename*=UTF-8''topology-unattributed-links.csv"
            )
        },
    )


@router.post("/vlan-attribution/manual-apply")
def topology_manual_apply(payload: list[dict] = Body(default=[]), db: Session = Depends(get_db)) -> dict:
    updated = 0
    skipped = 0
    for item in payload:
        switch_ip = str(item.get("switch_ip") or "").strip()
        port_name = str(item.get("port_name") or "").strip()
        vlan_id = str(item.get("vlan_id") or "").strip()
        if not switch_ip or not port_name or not vlan_id:
            skipped += 1
            continue
        switch = db.scalar(
            select(AssetDevice).where(
                AssetDevice.management_ip == switch_ip,
                AssetDevice.device_type == "switch",
            )
        )
        if not switch:
            skipped += 1
            continue
        port = db.scalar(
            select(NetworkPort).where(
                NetworkPort.device_id == switch.id,
                NetworkPort.port_name == port_name,
            )
        )
        if not port:
            skipped += 1
            continue
        if port.vlan_id != vlan_id:
            port.vlan_id = vlan_id
            port.role_guess = "camera_access_monitor" if vlan_id == "2" else (port.role_guess or "camera_access")
            updated += 1
    db.commit()
    return {
        "updated": updated,
        "skipped": skipped,
    }

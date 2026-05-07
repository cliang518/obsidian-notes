from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.asset import (
    AssetDevice,
    NetworkTopologyDomain,
    NetworkTopologyEdge,
    NetworkTopologyNode,
    TopologyLink,
)
from app.services.text_normalize import normalize_text


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = ROOT / "runtime"
ANALYSIS_DIR = RUNTIME_DIR / "analysis"
SWITCH_FACTS_PATH = ANALYSIS_DIR / "normalized_switch_facts.json"
CAMERA_FACTS_PATH = ANALYSIS_DIR / "normalized_camera_facts.json"
REPORT_PATH = ANALYSIS_DIR / "excel_compare_report.json"
DOMAIN_KEY = "central-avenue"
DOMAIN_NAME = "中央大道监控网络"
CORE_ANCHOR_IP = "10.0.68.254"
FLOOR_ORDER = {"2F": 0, "1F": 1, "3F": 2, "4F": 3, "5F": 4, "CORE": 5, "未识别": 9}
LAYER_ORDER = {"core": 0, "aggregation": 1, "access": 2, "terminal": 3}


def _load_json(path: Path) -> list[dict] | dict:
    if not path.exists():
        return [] if path.name.startswith("normalized_") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ip_sort_key(value: str) -> tuple:
    ip = (value or "").strip()
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip):
        return tuple(int(part) for part in ip.split("."))
    return (999, ip)


def _floor_sort_key(value: str) -> tuple[int, str]:
    text = normalize_text(value)
    return (FLOOR_ORDER.get(text, 8), text)


def _room_token(value: str) -> str:
    text = normalize_text(value)
    match = re.search(r"([1-5])\s*楼\s*(\d+)\s*#?\s*井", text)
    if match:
        return f"{match.group(1)}F-{match.group(2)}#井"
    if "机房" in text:
        return "机房"
    return text[:80]


def _room_display(token: str) -> str:
    match = re.match(r"([1-5]F)-(\d+#井)", token or "")
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return token or "-"


def _floor_label(value: str) -> str:
    text = normalize_text(value).upper()
    if "CORE" in text or "机房" in normalize_text(value):
        return "CORE"
    match = re.search(r"([1-5])F", text)
    if match:
        return f"{match.group(1)}F"
    match = re.search(r"([1-5])\s*楼", normalize_text(value))
    if match:
        return f"{match.group(1)}F"
    return "未识别"


def _extract_ip(value: str) -> str:
    match = re.search(r"(?:\d{1,3}\.){3}\d{1,3}", normalize_text(value))
    return match.group(0) if match else ""


def _safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _switch_display_label(row: dict, device: AssetDevice | None, ip: str, layer: str) -> str:
    location = normalize_text(row.get("switch_location", ""))
    flags = set(row.get("status_flags") or [])
    room = _room_token(location)
    if ip == CORE_ANCHOR_IP:
        return "2F 3#井 光汇聚核心"
    if room == "机房":
        if ip == "10.0.68.52":
            return "机房汇聚 A"
        if ip == "10.0.68.53":
            return "机房汇聚 B"
        if ip == "10.0.68.54":
            return "机房级联"
        return "机房交换机"
    if room and room != location[:80]:
        base = _room_display(room)
        if "远距离" in flags:
            return f"{base} 远距支线"
        if layer == "aggregation":
            return f"{base} 汇聚"
        return base
    runtime_label = normalize_text((device.hostname if device else "") or "")
    return location or runtime_label or ip


def _layer_for_switch(row: dict) -> tuple[str, str]:
    floor = row.get("switch_floor") or _floor_label(row.get("switch_location", ""))
    flags = set(row.get("status_flags") or [])
    location = normalize_text(row.get("switch_location", ""))
    normalized_ips = row.get("normalized_ips") or []
    if CORE_ANCHOR_IP in normalized_ips or "核心设备" in flags:
        return "core", "光汇聚核心"
    if "机房" in flags or "机房" in location:
        return "aggregation", "机房汇聚交换机"
    if "车场用交换机" in flags:
        return "aggregation", "停车场汇聚交换机"
    if floor == "2F" and "上联核心" in flags:
        return "aggregation", "楼层主汇聚交换机"
    if "远距离" in flags:
        return "access", "远距离接入交换机"
    return "access", "接入交换机"


def _device_maps(db: Session) -> tuple[dict[str, AssetDevice], dict[int, AssetDevice]]:
    devices = db.scalars(select(AssetDevice).where(AssetDevice.device_status != "archived")).all()
    by_ip = {
        (row.management_ip or row.service_ip or "").strip(): row
        for row in devices
        if (row.management_ip or row.service_ip or "").strip()
    }
    return by_ip, {row.id: row for row in devices}


def _camera_switch_map(db: Session) -> dict[str, str]:
    rows = db.execute(
        select(AssetDevice.management_ip, AssetDevice.id)
        .where(AssetDevice.device_type == "camera", AssetDevice.device_status != "archived")
    ).all()
    camera_id_to_ip = {row[1]: row[0] for row in rows if row[0]}
    switch_rows = db.execute(
        select(TopologyLink.src_device_id, TopologyLink.dst_device_id)
        .where(TopologyLink.link_type == "physical")
    ).all()
    device_ids = {item for row in switch_rows for item in row if item}
    devices = db.scalars(select(AssetDevice).where(AssetDevice.id.in_(device_ids))).all() if device_ids else []
    by_id = {row.id: row for row in devices}
    result: dict[str, str] = {}
    for src_id, dst_id in switch_rows:
        src = by_id.get(src_id)
        dst = by_id.get(dst_id)
        if not src or not dst:
            continue
        if src.device_type == "switch" and dst.device_type == "camera" and dst.management_ip:
            result[dst.management_ip] = src.management_ip
    return result


def _camera_assignment_meta(camera_facts: list[dict], camera_to_switch: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
    meta: dict[str, dict] = {}
    unlinked: list[str] = []
    for row in camera_facts:
        camera_ip = normalize_text(row.get("ip", ""))
        if not camera_ip:
            continue
        switch_ip = camera_to_switch.get(camera_ip)
        if not switch_ip:
            unlinked.append(camera_ip)
            continue
        bucket = meta.setdefault(
            switch_ip,
            {
                "count": 0,
                "sample_ips": [],
                "area_counter": Counter(),
            },
        )
        bucket["count"] += 1
        if len(bucket["sample_ips"]) < 10:
            bucket["sample_ips"].append(camera_ip)
        bucket["area_counter"][row.get("normalized_area") or "未归类"] += 1

    for item in meta.values():
        item["area_breakdown"] = [
            {"area": key, "count": value}
            for key, value in item["area_counter"].most_common(4)
        ]
        item.pop("area_counter", None)
    return meta, sorted(unlinked, key=_ip_sort_key)


def _ensure_domain(db: Session) -> NetworkTopologyDomain:
    domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
    if not domain:
        domain = NetworkTopologyDomain(domain_key=DOMAIN_KEY)
        db.add(domain)
        db.flush()
    domain.display_name = DOMAIN_NAME
    domain.site = "长兴中央大道"
    domain.description = "由交换机级联表、图像采集设备表与运行库链路共同计算生成的楼层化网络结果。"
    domain.source_report_path = str(REPORT_PATH)
    domain.generated_at = datetime.utcnow()
    return domain


def _candidate_parent_key(child: dict, candidates: list[dict]) -> tuple:
    child_flags = set(filter(None, str(child.get("flags") or "").split(",")))
    child_room = child.get("weak_current_room") or ""

    def sort_key(candidate: dict) -> tuple:
        candidate_flags = set(filter(None, str(candidate.get("flags") or "").split(",")))
        same_room = candidate.get("weak_current_room") == child_room
        score = 100
        if candidate.get("ip") == CORE_ANCHOR_IP:
            score -= 60
        if child.get("floor") != "2F" and candidate.get("floor") == "2F":
            score -= 35
        if candidate.get("layer") == "aggregation":
            score -= 20
        if same_room:
            score -= 12
        if "远距离" in child_flags and same_room and "远距离" not in candidate_flags:
            score -= 40
        if "远距离" in candidate_flags:
            score += 12
        if candidate.get("review_status") == "needs_field_check":
            score += 6
        return (score, _floor_sort_key(candidate.get("floor", "")), _ip_sort_key(candidate.get("ip", "")))

    return min((sort_key(item), item) for item in candidates)[1]


def _resolve_parent_key(row: dict, child_key: str, nodes_by_key: dict[str, dict]) -> tuple[str, str, str]:
    child = nodes_by_key[child_key]
    ip = child.get("ip") or ""
    uplink_text = normalize_text(row.get("uplink_location", ""))
    if ip == CORE_ANCHOR_IP:
        return "", "", ""

    direct_ip = _extract_ip(uplink_text)
    if direct_ip:
        parent_key = f"switch:{direct_ip}"
        if parent_key in nodes_by_key and parent_key != child_key:
            parent = nodes_by_key[parent_key]
            return parent_key, parent.get("ip") or "", uplink_text

    if child.get("layer") == "aggregation":
        parent_key = f"switch:{CORE_ANCHOR_IP}"
        if parent_key in nodes_by_key and parent_key != child_key:
            return parent_key, CORE_ANCHOR_IP, uplink_text or "上联 2F 3#井光汇聚"

    parent_room = _room_token(uplink_text)
    candidates = [
        node
        for node in nodes_by_key.values()
        if node["node_key"] != child_key and node.get("weak_current_room") == parent_room
    ]
    if candidates:
        parent = _candidate_parent_key(child, candidates)
        return parent["node_key"], parent.get("ip") or "", uplink_text

    if f"switch:{CORE_ANCHOR_IP}" in nodes_by_key and child.get("layer") == "aggregation":
        return f"switch:{CORE_ANCHOR_IP}", CORE_ANCHOR_IP, uplink_text or "上联 2F 3#井光汇聚"
    return "", "", uplink_text


def _node_from_model(row: NetworkTopologyNode) -> dict:
    return {
        "node_key": row.node_key,
        "device_id": row.device_id,
        "ip": row.ip,
        "label": normalize_text(row.label),
        "node_type": row.node_type,
        "layer": row.layer,
        "role": row.role,
        "floor": row.floor,
        "weak_current_room": normalize_text(row.weak_current_room),
        "parent_node_key": row.parent_node_key,
        "parent_ip": row.parent_ip,
        "source_type": row.source_type,
        "confidence": row.confidence,
        "camera_count": row.camera_count,
        "switch_count": row.switch_count,
        "review_status": row.review_status,
        "flags": row.flags,
        "notes": normalize_text(row.notes),
        "manual_note": normalize_text(row.manual_note),
        "pos_x": row.pos_x,
        "pos_y": row.pos_y,
        "position_source": row.position_source,
    }


def _edge_from_model(row: NetworkTopologyEdge) -> dict:
    return {
        "src_node_key": row.src_node_key,
        "dst_node_key": row.dst_node_key,
        "src_device_id": row.src_device_id,
        "dst_device_id": row.dst_device_id,
        "edge_type": row.edge_type,
        "src_port_label": normalize_text(row.src_port_label),
        "dst_port_label": normalize_text(row.dst_port_label),
        "vlan_id": normalize_text(row.vlan_id),
        "layer_path": row.layer_path,
        "evidence_type": row.evidence_type,
        "confidence": row.confidence,
        "review_status": row.review_status,
        "notes": normalize_text(row.notes),
        "manual_note": normalize_text(row.manual_note),
    }


def _merge_manual_overrides(
    node_payloads: list[dict],
    edge_payloads: list[dict],
    existing_nodes: list[NetworkTopologyNode],
    existing_edges: list[NetworkTopologyEdge],
) -> tuple[list[dict], list[dict]]:
    node_map = {item["node_key"]: item for item in node_payloads}
    for row in existing_nodes:
        manualish = (
            row.source_type == "manual_result"
            or row.review_status != "system_built"
            or bool((row.manual_note or "").strip())
        )
        if row.node_key in node_map:
            if not manualish:
                continue
            payload = node_map[row.node_key]
            for key in (
                "label",
                "layer",
                "role",
                "floor",
                "weak_current_room",
                "parent_node_key",
                "parent_ip",
                "review_status",
                "manual_note",
            ):
                value = normalize_text(str(getattr(row, key) or ""))
                if value:
                    payload[key] = value
            if row.source_type == "manual_result":
                payload["source_type"] = "manual_result"
            payload["confidence"] = max(float(payload.get("confidence") or 0), float(row.confidence or 0))
        elif row.source_type == "manual_result":
            node_payloads.append(_node_from_model(row))
            node_map[row.node_key] = node_payloads[-1]

    edge_map = {
        (item["src_node_key"], item["dst_node_key"], item["edge_type"]): item
        for item in edge_payloads
    }
    for row in existing_edges:
        manualish = (
            row.evidence_type in {"manual_result", "manual_override", "field_verified"}
            or row.review_status != "system_built"
            or bool((row.manual_note or "").strip())
        )
        if not manualish:
            continue
        key = (row.src_node_key, row.dst_node_key, row.edge_type)
        if key in edge_map:
            payload = edge_map[key]
            payload["src_port_label"] = normalize_text(row.src_port_label) or payload["src_port_label"]
            payload["dst_port_label"] = normalize_text(row.dst_port_label) or payload["dst_port_label"]
            payload["vlan_id"] = normalize_text(row.vlan_id) or payload.get("vlan_id", "")
            payload["review_status"] = row.review_status or payload["review_status"]
            payload["manual_note"] = normalize_text(row.manual_note) or payload.get("manual_note", "")
            payload["notes"] = normalize_text(row.notes) or payload.get("notes", "")
            payload["evidence_type"] = row.evidence_type or payload["evidence_type"]
            payload["confidence"] = max(float(payload.get("confidence") or 0), float(row.confidence or 0))
        else:
            edge_payloads.append(_edge_from_model(row))
            edge_map[key] = edge_payloads[-1]
    return node_payloads, edge_payloads


def _build_node_payloads(
    switch_facts: list[dict],
    camera_facts: list[dict],
    device_by_ip: dict[str, AssetDevice],
    camera_to_switch: dict[str, str],
) -> tuple[list[dict], list[dict], dict[str, int]]:
    nodes_by_key: dict[str, dict] = {}
    edges: list[dict] = []
    switch_fact_by_ip: dict[str, dict] = {}

    camera_meta, unlinked_cameras = _camera_assignment_meta(camera_facts, camera_to_switch)

    for row in switch_facts:
        layer, role = _layer_for_switch(row)
        floor = row.get("switch_floor") or _floor_label(row.get("switch_location", ""))
        location = normalize_text(row.get("switch_location", ""))
        flags = row.get("status_flags") or []
        for ip in row.get("normalized_ips") or []:
            device = device_by_ip.get(ip)
            node_key = f"switch:{ip}"
            nodes_by_key[node_key] = {
                "node_key": node_key,
                "device_id": device.id if device else None,
                "ip": ip,
                "label": _switch_display_label(row, device, ip, layer),
                "node_type": "switch",
                "layer": layer,
                "role": role,
                "floor": floor,
                "weak_current_room": _room_token(location),
                "parent_node_key": "",
                "parent_ip": "",
                "source_type": "excel_switch_cascade",
                "confidence": 0.99 if ip == CORE_ANCHOR_IP else (0.97 if device else 0.78),
                "camera_count": int(camera_meta.get(ip, {}).get("count") or row.get("camera_count") or 0),
                "switch_count": 0,
                "review_status": "system_built" if device else "needs_field_check",
                "flags": ",".join(flags),
                "notes": normalize_text(
                    f"运行库设备名：{(device.hostname if device else '') or '-'}；原位置：{location or '-'}；上联说明：{row.get('uplink_location', '') or '-'}；原始IP：{row.get('raw_ip', '') or ip}"
                ),
                "manual_note": "",
            }
            switch_fact_by_ip[ip] = row

    for ip, row in switch_fact_by_ip.items():
        child_key = f"switch:{ip}"
        if child_key not in nodes_by_key:
            continue
        parent_key, parent_ip, port_label = _resolve_parent_key(row, child_key, nodes_by_key)
        if not parent_key:
            continue
        nodes_by_key[child_key]["parent_node_key"] = parent_key
        nodes_by_key[child_key]["parent_ip"] = parent_ip
        edges.append(
            {
                "src_node_key": parent_key,
                "dst_node_key": child_key,
                "src_device_id": nodes_by_key[parent_key].get("device_id"),
                "dst_device_id": nodes_by_key[child_key].get("device_id"),
                "edge_type": "uplink",
                "src_port_label": port_label,
                "dst_port_label": "",
                "vlan_id": "",
                "layer_path": f"{nodes_by_key[parent_key]['layer']}->{nodes_by_key[child_key]['layer']}",
                "evidence_type": "excel_switch_cascade",
                "confidence": 0.98 if nodes_by_key[child_key]["review_status"] == "system_built" else 0.82,
                "review_status": nodes_by_key[child_key]["review_status"],
                "notes": normalize_text(
                    f"{nodes_by_key[parent_key]['label']} -> {nodes_by_key[child_key]['label']}；{port_label or '依据交换机级联表'}"
                ),
                "manual_note": "",
            }
        )

    downstream_switch_count = Counter(edge["src_node_key"] for edge in edges if edge["edge_type"] == "uplink")
    for node_key, count in downstream_switch_count.items():
        if node_key in nodes_by_key:
            nodes_by_key[node_key]["switch_count"] = int(count)

    node_payloads = sorted(
        nodes_by_key.values(),
        key=lambda item: (
            LAYER_ORDER.get(item["layer"], 8),
            _floor_sort_key(item["floor"]),
            _ip_sort_key(item["ip"]),
        ),
    )
    edge_payloads = sorted(
        edges,
        key=lambda item: (
            LAYER_ORDER.get(nodes_by_key[item["src_node_key"]]["layer"], 8),
            _ip_sort_key(nodes_by_key[item["src_node_key"]]["ip"]),
            _ip_sort_key(nodes_by_key[item["dst_node_key"]]["ip"]),
        ),
    )
    counts = {
        "core": sum(1 for item in node_payloads if item["layer"] == "core"),
        "aggregation": sum(1 for item in node_payloads if item["layer"] == "aggregation"),
        "access": sum(1 for item in node_payloads if item["layer"] == "access"),
        "terminal": sum(1 for item in node_payloads if item["layer"] == "terminal"),
        "unlinked_cameras": len(unlinked_cameras),
        "camera_total": len(camera_facts),
    }
    return node_payloads, edge_payloads, counts


def _room_group_payload(room_key: str, switch_items: list[dict], parent_edge: dict | None, parent_node: dict | None) -> dict:
    switch_items = sorted(switch_items, key=lambda item: (_ip_sort_key(item["ip"]), item["label"]))
    return {
        "room_key": room_key,
        "room_label": _room_display(room_key),
        "camera_count": sum(int(item.get("sheet_camera_count") or item.get("camera_count") or 0) for item in switch_items),
        "switch_count": len(switch_items),
        "parent_switch_ip": parent_node.get("ip") if parent_node else "",
        "parent_switch_label": parent_node.get("label") if parent_node else "",
        "parent_room": parent_node.get("weak_current_room") if parent_node else "",
        "parent_port_label": (parent_edge or {}).get("src_port_label", ""),
        "switches": [
            {
                "id": item["id"],
                "node_key": item["node_key"],
                "ip": item["ip"],
                "label": item["label"],
                "role": item["role"],
                "review_status": item["review_status"],
                "confidence": item["confidence"],
                "camera_count": int(item.get("sheet_camera_count") or item.get("camera_count") or 0),
                "switch_count": int(item.get("switch_count") or 0),
                "camera_sample_ips": item.get("camera_sample_ips") or [],
                "camera_area_breakdown": item.get("camera_area_breakdown") or [],
            }
            for item in switch_items
        ],
    }


def _build_simplified_payload(node_items: list[dict], edge_items: list[dict], report: dict) -> dict:
    node_by_key = {item["node_key"]: item for item in node_items}
    switch_nodes = [item for item in node_items if item["node_type"] == "switch"]
    switch_nodes_by_ip = {item["ip"]: item for item in switch_nodes if item["ip"]}

    child_edges_by_parent = defaultdict(list)
    edge_by_target = {}
    for edge in edge_items:
        if edge["source_node_key"] in node_by_key and edge["target_node_key"] in node_by_key:
            child_edges_by_parent[edge["source_node_key"]].append(edge)
            edge_by_target[edge["target_node_key"]] = edge

    core_anchor = switch_nodes_by_ip.get(CORE_ANCHOR_IP)
    if not core_anchor:
        core_anchor = next((item for item in switch_nodes if item["layer"] == "core"), None)

    aggregation_switches: list[dict] = []
    for item in switch_nodes:
        if item["node_key"] == (core_anchor or {}).get("node_key"):
            continue
        if item["layer"] != "aggregation":
            continue
        child_edges = child_edges_by_parent.get(item["node_key"], [])
        child_nodes = [node_by_key[edge["target_node_key"]] for edge in child_edges if edge["target_node_key"] in node_by_key]
        covered_floors = Counter(child.get("floor") or "未识别" for child in child_nodes if child["node_type"] == "switch")
        aggregation_switches.append(
            {
                "id": item["id"],
                "node_key": item["node_key"],
                "ip": item["ip"],
                "label": item["label"],
                "room_label": _room_display(item.get("weak_current_room") or ""),
                "parent_port_label": edge_by_target.get(item["node_key"], {}).get("src_port_label", ""),
                "downstream_switch_count": len(child_nodes),
                "downstream_camera_count": sum(int(child.get("sheet_camera_count") or child.get("camera_count") or 0) for child in child_nodes),
                "covered_floors": [
                    {"floor": floor, "count": count}
                    for floor, count in sorted(covered_floors.items(), key=lambda pair: _floor_sort_key(pair[0]))
                ],
                "review_status": item["review_status"],
                "confidence": item["confidence"],
            }
        )
    aggregation_switches.sort(key=lambda item: (_floor_sort_key("2F"), _ip_sort_key(item["ip"])))

    floor_cards: list[dict] = []
    for floor in ["2F", "1F", "3F", "4F", "5F"]:
        floor_switches = [
            item
            for item in switch_nodes
            if item["floor"] == floor and item["node_key"] != (core_anchor or {}).get("node_key")
        ]
        if not floor_switches:
            continue
        room_map: dict[str, list[dict]] = defaultdict(list)
        for item in floor_switches:
            room_map[item.get("weak_current_room") or f"{floor}-未分配"].append(item)
        rooms = []
        for room_key, items in sorted(room_map.items(), key=lambda pair: (_floor_sort_key(floor), pair[0])):
            room_parent_edge = edge_by_target.get(items[0]["node_key"])
            room_parent_node = node_by_key.get(items[0].get("parent_node_key", "")) if items[0].get("parent_node_key") else None
            rooms.append(_room_group_payload(room_key, items, room_parent_edge, room_parent_node))
        floor_cards.append(
            {
                "floor": floor,
                "switch_count": sum(room["switch_count"] for room in rooms),
                "room_count": len(rooms),
                "camera_count": sum(room["camera_count"] for room in rooms),
                "rooms": rooms,
            }
        )

    unresolved_rows = report.get("switch_compare", {}).get("unresolved_rows", []) if isinstance(report, dict) else []
    unresolved_switches = [
        {
            "ip": (row.get("normalized_ips") or [row.get("raw_ip") or ""])[0],
            "location": normalize_text(row.get("switch_location", "")),
            "room_label": _room_display(_room_token(row.get("switch_location", ""))),
            "uplink_location": normalize_text(row.get("uplink_location", "")),
            "floor": _floor_label(row.get("switch_location", "")),
            "flags": row.get("status_flags") or [],
        }
        for row in unresolved_rows
    ]
    unresolved_switches.sort(key=lambda item: (_floor_sort_key(item["floor"]), _ip_sort_key(item["ip"])))

    missing_runtime_ips = set(report.get("switch_compare", {}).get("missing_in_runtime_ips", [])) if isinstance(report, dict) else set()
    missing_runtime_switches = []
    for ip in sorted(missing_runtime_ips, key=_ip_sort_key):
        node = switch_nodes_by_ip.get(ip)
        if node:
            missing_runtime_switches.append(
                {
                    "ip": ip,
                    "label": node["label"],
                    "floor": node["floor"],
                    "room_label": _room_display(node.get("weak_current_room") or ""),
                    "role": node["role"],
                }
            )
        else:
            missing_runtime_switches.append(
                {
                    "ip": ip,
                    "label": ip,
                    "floor": "未识别",
                    "room_label": "-",
                    "role": "待补录交换机",
                }
            )

    unlinked_camera_ips = report.get("camera_topology_coverage", {}).get("unlinked_sheet_camera_ips", []) if isinstance(report, dict) else []
    unlinked_cameras = [
        {
            "ip": ip,
        }
        for ip in sorted(unlinked_camera_ips, key=_ip_sort_key)
    ]

    stats = {
        "sheet_camera_count": int(report.get("sheet_summary", {}).get("camera_rows", 0) or 0) if isinstance(report, dict) else 0,
        "linked_sheet_camera_count": int(report.get("camera_topology_coverage", {}).get("linked_sheet_camera_count", 0) or 0) if isinstance(report, dict) else 0,
        "unlinked_sheet_camera_count": int(report.get("camera_topology_coverage", {}).get("unlinked_sheet_camera_count", 0) or 0) if isinstance(report, dict) else 0,
        "sheet_switch_count": int(report.get("sheet_summary", {}).get("normalized_switch_ip_count", 0) or 0) if isinstance(report, dict) else 0,
        "runtime_missing_switch_count": len(missing_runtime_switches),
        "aggregation_switch_count": len(aggregation_switches),
        "floor_card_count": len(floor_cards),
    }

    core_anchor_payload = None
    if core_anchor:
        child_edges = child_edges_by_parent.get(core_anchor["node_key"], [])
        child_nodes = [node_by_key[edge["target_node_key"]] for edge in child_edges if edge["target_node_key"] in node_by_key]
        core_anchor_payload = {
            "id": core_anchor["id"],
            "node_key": core_anchor["node_key"],
            "ip": core_anchor["ip"],
            "label": core_anchor["label"],
            "room_label": _room_display(core_anchor.get("weak_current_room") or ""),
            "downstream_switch_count": len(child_nodes),
            "downstream_camera_count": sum(int(item.get("sheet_camera_count") or item.get("camera_count") or 0) for item in child_nodes),
            "child_switches": [
                {
                    "id": item["id"],
                    "ip": item["ip"],
                    "label": item["label"],
                    "floor": item["floor"],
                    "camera_count": int(item.get("sheet_camera_count") or item.get("camera_count") or 0),
                }
                for item in sorted(child_nodes, key=lambda row: (_floor_sort_key(row["floor"]), _ip_sort_key(row["ip"])))
            ],
        }

    return {
        "core_anchor": core_anchor_payload,
        "aggregation_switches": aggregation_switches,
        "floor_cards": floor_cards,
        "missing_runtime_switches": missing_runtime_switches,
        "unresolved_switches": unresolved_switches,
        "unlinked_cameras": unlinked_cameras,
        "stats": stats,
    }


def rebuild_central_avenue_architecture(db: Session) -> dict:
    switch_facts = _load_json(SWITCH_FACTS_PATH)
    camera_facts = _load_json(CAMERA_FACTS_PATH)
    if not isinstance(switch_facts, list) or not isinstance(camera_facts, list):
        raise ValueError("normalized topology facts are unavailable")

    device_by_ip, _ = _device_maps(db)
    camera_to_switch = _camera_switch_map(db)
    domain = _ensure_domain(db)
    db.flush()

    existing_nodes = db.scalars(select(NetworkTopologyNode).where(NetworkTopologyNode.domain_id == domain.id)).all()
    existing_edges = db.scalars(select(NetworkTopologyEdge).where(NetworkTopologyEdge.domain_id == domain.id)).all()

    node_payloads, edge_payloads, counts = _build_node_payloads(
        switch_facts=switch_facts,
        camera_facts=camera_facts,
        device_by_ip=device_by_ip,
        camera_to_switch=camera_to_switch,
    )
    node_payloads, edge_payloads = _merge_manual_overrides(
        node_payloads=node_payloads,
        edge_payloads=edge_payloads,
        existing_nodes=existing_nodes,
        existing_edges=existing_edges,
    )

    db.execute(delete(NetworkTopologyEdge).where(NetworkTopologyEdge.domain_id == domain.id))
    db.execute(delete(NetworkTopologyNode).where(NetworkTopologyNode.domain_id == domain.id))
    db.flush()

    for payload in node_payloads:
        db.add(NetworkTopologyNode(domain_id=domain.id, **payload))
    db.flush()
    for payload in edge_payloads:
        db.add(NetworkTopologyEdge(domain_id=domain.id, **payload))
    db.commit()

    return {
        "ok": True,
        "domain_key": DOMAIN_KEY,
        "generated_at": domain.generated_at.isoformat(timespec="seconds") if domain.generated_at else "",
        "node_count": len(node_payloads),
        "edge_count": len(edge_payloads),
        "counts": counts,
    }


def central_avenue_architecture_payload(db: Session) -> dict:
    domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
    if not domain:
        return rebuild_central_avenue_architecture(db)

    nodes = db.scalars(
        select(NetworkTopologyNode)
        .where(NetworkTopologyNode.domain_id == domain.id)
        .order_by(NetworkTopologyNode.layer, NetworkTopologyNode.floor, NetworkTopologyNode.ip, NetworkTopologyNode.id)
    ).all()
    edges = db.scalars(
        select(NetworkTopologyEdge)
        .where(NetworkTopologyEdge.domain_id == domain.id)
        .order_by(NetworkTopologyEdge.edge_type, NetworkTopologyEdge.src_node_key, NetworkTopologyEdge.dst_node_key)
    ).all()
    if not nodes:
        return rebuild_central_avenue_architecture(db)

    report = _load_json(REPORT_PATH)
    camera_facts = _load_json(CAMERA_FACTS_PATH)
    device_by_ip, _ = _device_maps(db)
    camera_to_switch = _camera_switch_map(db)
    camera_meta, _ = _camera_assignment_meta(camera_facts if isinstance(camera_facts, list) else [], camera_to_switch)

    layer_counts = Counter(row.layer for row in nodes)
    floor_counts = Counter(row.floor or "未识别" for row in nodes if row.node_type == "switch")
    review_counts = Counter(row.review_status or "system_built" for row in nodes)

    node_items = []
    for row in nodes:
        runtime_device = device_by_ip.get(row.ip or "")
        meta = camera_meta.get(row.ip or "", {})
        node_items.append(
            {
                "id": row.id,
                "device_id": row.device_id,
                "node_key": row.node_key,
                "ip": row.ip,
                "label": normalize_text(row.label),
                "asset_label": normalize_text((runtime_device.hostname if runtime_device else "") or ""),
                "node_type": row.node_type,
                "layer": row.layer,
                "role": row.role,
                "floor": row.floor,
                "weak_current_room": normalize_text(row.weak_current_room),
                "parent_node_key": row.parent_node_key,
                "parent_ip": row.parent_ip,
                "source_type": row.source_type,
                "confidence": row.confidence,
                "camera_count": row.camera_count,
                "sheet_camera_count": int(meta.get("count") or row.camera_count or 0),
                "camera_sample_ips": meta.get("sample_ips") or [],
                "camera_area_breakdown": meta.get("area_breakdown") or [],
                "switch_count": row.switch_count,
                "review_status": row.review_status,
                "flags": row.flags,
                "notes": normalize_text(row.notes),
                "manual_note": normalize_text(row.manual_note),
                "pos_x": row.pos_x,
                "pos_y": row.pos_y,
                "position_source": row.position_source,
            }
        )
    edge_items = [
        {
            "id": row.id,
            "src_node_key": row.src_node_key,
            "dst_node_key": row.dst_node_key,
            "source_node_key": row.src_node_key,
            "target_node_key": row.dst_node_key,
            "src_device_id": row.src_device_id,
            "dst_device_id": row.dst_device_id,
            "edge_type": row.edge_type,
            "src_port_label": normalize_text(row.src_port_label),
            "dst_port_label": normalize_text(row.dst_port_label),
            "vlan_id": normalize_text(row.vlan_id),
            "vlan": normalize_text(row.vlan_id),
            "layer_path": row.layer_path,
            "evidence_type": row.evidence_type,
            "confidence": row.confidence,
            "review_status": row.review_status,
            "notes": normalize_text(row.notes),
            "manual_note": normalize_text(row.manual_note),
        }
        for row in edges
    ]

    simplified = _build_simplified_payload(node_items, edge_items, report if isinstance(report, dict) else {})

    return {
        "domain": {
            "id": domain.id,
            "domain_key": domain.domain_key,
            "display_name": domain.display_name,
            "site": domain.site,
            "description": domain.description,
            "source_report_path": domain.source_report_path,
            "generated_at": domain.generated_at.isoformat(timespec="seconds") if domain.generated_at else "",
        },
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "layer_counts": [{"layer": key, "count": value} for key, value in layer_counts.most_common()],
            "floor_counts": [{"floor": key, "count": value} for key, value in floor_counts.most_common()],
            "review_counts": [{"status": key, "count": value} for key, value in review_counts.most_common()],
        },
        "simplified": simplified,
        "nodes": node_items,
        "edges": edge_items,
    }


def update_architecture_node(db: Session, node_id: int, payload: dict) -> dict:
    row = db.get(NetworkTopologyNode, node_id)
    if not row:
        raise ValueError("node_not_found")
    allowed = {
        "label",
        "layer",
        "role",
        "floor",
        "weak_current_room",
        "parent_node_key",
        "parent_ip",
        "review_status",
        "manual_note",
        "position_source",
    }
    for key in allowed:
        if key in payload:
            setattr(row, key, normalize_text(str(payload.get(key) or "")))
    if "pos_x" in payload or "x" in payload:
        row.pos_x = _safe_float(payload.get("pos_x", payload.get("x")))
    if "pos_y" in payload or "y" in payload:
        row.pos_y = _safe_float(payload.get("pos_y", payload.get("y")))
    if row.pos_x is not None or row.pos_y is not None:
        row.position_source = normalize_text(str(payload.get("position_source") or "field_verified"))
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "node_id": row.id}


def create_architecture_node(db: Session, payload: dict) -> dict:
    domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
    if not domain:
        rebuild_central_avenue_architecture(db)
        domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
    if not domain:
        raise ValueError("domain_not_found")

    ip = normalize_text(str(payload.get("ip") or ""))
    layer = normalize_text(str(payload.get("layer") or "access")) or "access"
    default_node_type = "camera" if layer == "terminal" else "switch"
    node_type = normalize_text(str(payload.get("node_type") or default_node_type)) or default_node_type
    node_key = normalize_text(str(payload.get("node_key") or ""))
    if not node_key:
        node_key = f"{node_type}:{ip}" if ip else f"{node_type}:manual-{int(datetime.utcnow().timestamp())}"
    existing = db.scalar(
        select(NetworkTopologyNode).where(
            NetworkTopologyNode.domain_id == domain.id,
            NetworkTopologyNode.node_key == node_key,
        )
    )
    if existing:
        return update_architecture_node(db, existing.id, payload)

    device = None
    if ip:
        device = db.scalar(
            select(AssetDevice).where(
                AssetDevice.device_status != "archived",
                (AssetDevice.management_ip == ip) | (AssetDevice.service_ip == ip),
            )
        )
    row = NetworkTopologyNode(
        domain_id=domain.id,
        device_id=device.id if device else None,
        node_key=node_key,
        ip=ip,
        label=normalize_text(str(payload.get("label") or ip or node_key)),
        node_type=node_type,
        layer=layer,
        role=normalize_text(str(payload.get("role") or ("摄像头点位" if layer == "terminal" else "接入交换机"))),
        floor=normalize_text(str(payload.get("floor") or "")),
        weak_current_room=normalize_text(str(payload.get("weak_current_room") or "")),
        parent_node_key=normalize_text(str(payload.get("parent_node_key") or "")),
        parent_ip=normalize_text(str(payload.get("parent_ip") or "")),
        source_type="manual_result",
        confidence=1.0 if payload.get("review_status") == "field_verified" else 0.88,
        camera_count=int(payload.get("camera_count") or 0),
        switch_count=int(payload.get("switch_count") or 0),
        review_status=normalize_text(str(payload.get("review_status") or "field_verified")),
        flags=normalize_text(str(payload.get("flags") or "manual_added")),
        notes=normalize_text(str(payload.get("notes") or "现场补录节点")),
        manual_note=normalize_text(str(payload.get("manual_note") or "")),
        pos_x=_safe_float(payload.get("pos_x", payload.get("x"))),
        pos_y=_safe_float(payload.get("pos_y", payload.get("y"))),
        position_source=normalize_text(str(payload.get("position_source") or ("field_verified" if payload.get("x") or payload.get("pos_x") else ""))),
    )
    db.add(row)
    db.commit()
    return {"ok": True, "node_id": row.id, "node_key": row.node_key}


def create_architecture_edge(db: Session, payload: dict) -> dict:
    try:
        domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
        if not domain:
            rebuild_central_avenue_architecture(db)
            domain = db.scalar(select(NetworkTopologyDomain).where(NetworkTopologyDomain.domain_key == DOMAIN_KEY))
        if not domain:
            raise ValueError("domain_not_found")

        src_ip = normalize_text(str(payload.get("source_ip") or payload.get("src_ip") or ""))
        dst_ip = normalize_text(str(payload.get("target_ip") or payload.get("dst_ip") or ""))
        src_node_key = normalize_text(str(payload.get("src_node_key") or payload.get("source_node_key") or ""))
        dst_node_key = normalize_text(str(payload.get("dst_node_key") or payload.get("target_node_key") or ""))
        edge_type = normalize_text(str(payload.get("edge_type") or "uplink")) or "uplink"
        if not src_node_key and src_ip:
            src_node_key = f"switch:{src_ip}"
        if not dst_node_key and dst_ip:
            dst_node_key = f"camera:{dst_ip}" if edge_type.startswith("camera") else f"switch:{dst_ip}"
            if not db.scalar(
                select(NetworkTopologyNode).where(
                    NetworkTopologyNode.domain_id == domain.id,
                    NetworkTopologyNode.node_key == dst_node_key,
                )
            ):
                dst_node_key = f"switch:{dst_ip}" if dst_node_key.startswith("camera:") else f"camera:{dst_ip}"
        if not src_node_key or not dst_node_key:
            raise ValueError("src_and_dst_required")

        nodes = db.scalars(
            select(NetworkTopologyNode).where(
                NetworkTopologyNode.domain_id == domain.id,
                NetworkTopologyNode.node_key.in_([src_node_key, dst_node_key]),
            )
        ).all()
        node_map = {row.node_key: row for row in nodes}
        if src_node_key not in node_map or dst_node_key not in node_map:
            raise ValueError("node_not_found")

        existing = db.scalar(
            select(NetworkTopologyEdge).where(
                NetworkTopologyEdge.domain_id == domain.id,
                NetworkTopologyEdge.src_node_key == src_node_key,
                NetworkTopologyEdge.dst_node_key == dst_node_key,
                NetworkTopologyEdge.edge_type == edge_type,
            )
        )
        row = existing or NetworkTopologyEdge(domain_id=domain.id)
        if not existing:
            db.add(row)
        src = node_map[src_node_key]
        dst = node_map[dst_node_key]
        row.src_node_key = src_node_key
        row.dst_node_key = dst_node_key
        row.src_device_id = src.device_id
        row.dst_device_id = dst.device_id
        row.edge_type = edge_type
        row.src_port_label = normalize_text(str(payload.get("src_port_label") or payload.get("source_port_name") or ""))
        row.dst_port_label = normalize_text(str(payload.get("dst_port_label") or payload.get("target_port_name") or ""))
        vlan_id = normalize_text(str(payload.get("vlan_id") or payload.get("vlan") or ""))
        row.vlan_id = vlan_id
        row.layer_path = normalize_text(str(payload.get("layer_path") or f"{src.layer}->{dst.layer}"))
        row.evidence_type = normalize_text(str(payload.get("evidence_type") or "manual_result")) or "manual_result"
        payload_confidence = _safe_float(payload.get("confidence")) if payload.get("confidence") is not None else None
        row.confidence = payload_confidence if payload_confidence is not None else 1.0
        row.review_status = normalize_text(str(payload.get("review_status") or "field_verified"))
        row.notes = normalize_text(str(payload.get("notes") or (f"VLAN {vlan_id}" if vlan_id else "") or "现场补录链路"))
        row.manual_note = normalize_text(str(payload.get("manual_note") or ""))
        dst.parent_node_key = src_node_key
        dst.parent_ip = src.ip
        db.commit()
        return {"ok": True, "edge_id": row.id}
    except Exception:
        db.rollback()
        raise


def delete_architecture_node(db: Session, node_id: int) -> dict:
    row = db.get(NetworkTopologyNode, node_id)
    if not row:
        raise ValueError("node_not_found")
    domain_id = row.domain_id
    node_key = row.node_key
    db.execute(
        delete(NetworkTopologyEdge).where(
            NetworkTopologyEdge.domain_id == domain_id,
            (NetworkTopologyEdge.src_node_key == node_key) | (NetworkTopologyEdge.dst_node_key == node_key),
        )
    )
    children = db.scalars(
        select(NetworkTopologyNode).where(
            NetworkTopologyNode.domain_id == domain_id,
            NetworkTopologyNode.parent_node_key == node_key,
        )
    ).all()
    for child in children:
        child.parent_node_key = ""
        child.parent_ip = ""
    db.delete(row)
    db.commit()
    return {"ok": True, "node_id": node_id}


def delete_architecture_edge(db: Session, edge_id: int) -> dict:
    row = db.get(NetworkTopologyEdge, edge_id)
    if not row:
        raise ValueError("edge_not_found")
    dst = db.scalar(
        select(NetworkTopologyNode).where(
            NetworkTopologyNode.domain_id == row.domain_id,
            NetworkTopologyNode.node_key == row.dst_node_key,
        )
    )
    if dst and dst.parent_node_key == row.src_node_key:
        dst.parent_node_key = ""
        dst.parent_ip = ""
    db.delete(row)
    db.commit()
    return {"ok": True, "edge_id": edge_id}

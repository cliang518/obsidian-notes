from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import OpsAlert
from app.models.asset import AssetArea, AssetDevice, NetworkTopologyEdge, NetworkTopologyNode
from app.models.work_order import WorkOrder
from app.schemas.work_order import AlertCreateWorkOrderRequest, ResolveWorkOrderFromTopologyRequest
from app.services.text_normalize import normalize_text


CLOSED_WORK_ORDER_STATUSES = {"closed", "cancelled"}


def _append_note(base: str, note: str) -> str:
    base_text = normalize_text(base or "")
    note_text = normalize_text(note or "")
    if not note_text:
        return base_text
    if not base_text:
        return note_text
    if note_text in base_text:
        return base_text
    return f"{base_text}\n{note_text}"


def _safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _work_order_dict(row: WorkOrder) -> dict:
    return {
        "id": row.id,
        "title": normalize_text(row.title),
        "order_type": row.order_type,
        "status": row.status,
        "priority": row.priority,
        "area_name": normalize_text(row.area_name),
        "source_type": row.source_type,
        "source_alert_id": row.source_alert_id,
        "asset_device_id": row.asset_device_id,
        "topology_node_key": normalize_text(row.topology_node_key),
        "topology_edge_id": row.topology_edge_id,
        "verification_status": row.verification_status,
        "verified_by": normalize_text(row.verified_by),
        "verified_at": row.verified_at,
        "closed_by": normalize_text(row.closed_by),
        "close_reason": normalize_text(row.close_reason),
        "topology_review_payload": normalize_text(row.topology_review_payload),
        "assignee_username": normalize_text(row.assignee_username),
        "description": normalize_text(row.description),
        "resolution_note": normalize_text(row.resolution_note),
        "due_at": row.due_at,
        "resolved_at": row.resolved_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "linked_inspection_count": 0,
        "linked_dispatch_count": 0,
    }


def _find_topology_node(db: Session, node_key: str) -> NetworkTopologyNode | None:
    node_key = normalize_text(node_key).strip()
    if not node_key:
        return None
    return db.scalar(
        select(NetworkTopologyNode)
        .where(NetworkTopologyNode.node_key == node_key)
        .order_by(NetworkTopologyNode.id.desc())
        .limit(1)
    )


def _sync_asset_from_topology(
    asset: AssetDevice,
    *,
    device_status: str,
    health_state: str,
    area_id: int | None,
    note: str,
) -> None:
    if device_status and asset.device_status != "archived":
        asset.device_status = normalize_text(device_status)
    if health_state:
        asset.health_state = normalize_text(health_state)
    if area_id:
        asset.area_id = area_id
    asset.notes = _append_note(asset.notes or "", note)
    asset.updated_at = datetime.utcnow()


def create_work_order_from_alert(
    db: Session,
    alert_id: int,
    payload: AlertCreateWorkOrderRequest | None,
    *,
    operator_username: str = "",
    operator_role: str = "",
) -> dict:
    payload = payload or AlertCreateWorkOrderRequest()
    try:
        alert = db.get(OpsAlert, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="alert_not_found")

        if alert.linked_work_order_id:
            existing = db.get(WorkOrder, alert.linked_work_order_id)
            return {
                "ok": True,
                "created": False,
                "work_order_id": alert.linked_work_order_id,
                "work_order_title": normalize_text(existing.title) if existing else "",
                "work_order": _work_order_dict(existing) if existing else None,
                "alert": {
                    "id": alert.id,
                    "status": alert.status,
                    "linked_work_order_id": alert.linked_work_order_id,
                },
            }

        topology_edge = None
        if payload.topology_edge_id:
            topology_edge = db.get(NetworkTopologyEdge, payload.topology_edge_id)
            if not topology_edge:
                raise HTTPException(status_code=404, detail="topology_edge_not_found")

        device = db.get(AssetDevice, alert.asset_device_id) if alert.asset_device_id else None
        area_name = ""
        if device and device.area_id:
            area = db.get(AssetArea, device.area_id)
            area_name = normalize_text(area.display_name) if area else ""

        priority = normalize_text(payload.priority) or (
            "critical" if alert.severity == "critical" else "high" if alert.severity == "warning" else "medium"
        )
        assignee_username = normalize_text(payload.assignee_username)
        if not assignee_username and operator_role == "manager":
            assignee_username = normalize_text(operator_username)

        description = normalize_text(alert.message or alert.evidence_summary or alert.title)
        if payload.manual_note:
            description = _append_note(description, f"告警转工单备注：{payload.manual_note}")

        order = WorkOrder(
            title=f"{normalize_text(alert.title)} 处置工单",
            order_type="alert_followup",
            status="open",
            priority=priority,
            area_name=area_name,
            source_type="alert_bridge",
            source_alert_id=alert.id,
            asset_device_id=alert.asset_device_id,
            topology_node_key=normalize_text(payload.topology_node_key),
            topology_edge_id=topology_edge.id if topology_edge else None,
            verification_status="pending",
            assignee_username=assignee_username,
            description=description,
        )
        db.add(order)
        db.flush()

        alert.linked_work_order_id = order.id
        if alert.status == "open":
            alert.status = "acknowledged"
            alert.last_seen_at = alert.last_seen_at or datetime.utcnow()
        alert.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)
        return {
            "ok": True,
            "created": True,
            "work_order_id": order.id,
            "work_order_title": normalize_text(order.title),
            "work_order": _work_order_dict(order),
            "alert": {
                "id": alert.id,
                "status": alert.status,
                "linked_work_order_id": alert.linked_work_order_id,
            },
        }
    except Exception:
        db.rollback()
        raise


def resolve_work_order_from_topology(
    db: Session,
    work_order_id: int,
    payload: ResolveWorkOrderFromTopologyRequest,
    *,
    operator_username: str = "",
) -> dict:
    try:
        order = db.get(WorkOrder, work_order_id)
        if not order:
            raise HTTPException(status_code=404, detail="work_order_not_found")
        if order.status in CLOSED_WORK_ORDER_STATUSES:
            raise HTTPException(status_code=409, detail="work_order_already_closed")

        operator = normalize_text(payload.operator or operator_username)
        now = datetime.utcnow()
        topology_node = None
        topology_edge = None

        node_update = payload.topology_node_update
        if node_update:
            topology_node = _find_topology_node(db, node_update.node_key or order.topology_node_key)
            if not topology_node:
                raise HTTPException(status_code=404, detail="topology_node_not_found")

            pos_x = _safe_float(node_update.pos_x if node_update.pos_x is not None else node_update.x)
            pos_y = _safe_float(node_update.pos_y if node_update.pos_y is not None else node_update.y)
            if pos_x is not None:
                topology_node.pos_x = pos_x
            if pos_y is not None:
                topology_node.pos_y = pos_y
            if pos_x is not None or pos_y is not None:
                topology_node.position_source = "manual"
            topology_node.review_status = normalize_text(node_update.review_status or "field_verified")
            topology_node.manual_note = _append_note(
                topology_node.manual_note,
                normalize_text(node_update.manual_note or payload.resolution_note or "工单拓扑核实"),
            )
            topology_node.updated_at = now

        edge_update = payload.topology_edge_update
        if edge_update:
            if edge_update.edge_id:
                topology_edge = db.get(NetworkTopologyEdge, edge_update.edge_id)
                if not topology_edge:
                    raise HTTPException(status_code=404, detail="topology_edge_not_found")
            else:
                src_node_key = normalize_text(edge_update.src_node_key)
                dst_node_key = normalize_text(edge_update.dst_node_key)
                if not src_node_key or not dst_node_key:
                    raise HTTPException(status_code=400, detail="src_and_dst_required")
                edge_type = normalize_text(edge_update.edge_type or "camera") or "camera"
                topology_edge = db.scalar(
                    select(NetworkTopologyEdge)
                    .where(
                        NetworkTopologyEdge.src_node_key == src_node_key,
                        NetworkTopologyEdge.dst_node_key == dst_node_key,
                        NetworkTopologyEdge.edge_type == edge_type,
                    )
                    .order_by(NetworkTopologyEdge.id.desc())
                    .limit(1)
                )
                if not topology_edge:
                    src_node = _find_topology_node(db, src_node_key)
                    dst_node = _find_topology_node(db, dst_node_key)
                    if not src_node or not dst_node:
                        raise HTTPException(status_code=404, detail="topology_node_not_found")
                    topology_edge = NetworkTopologyEdge(
                        domain_id=src_node.domain_id,
                        src_node_key=src_node_key,
                        dst_node_key=dst_node_key,
                        src_device_id=src_node.device_id,
                        dst_device_id=dst_node.device_id,
                        edge_type=edge_type,
                    )
                    db.add(topology_edge)

            topology_edge.vlan_id = normalize_text(edge_update.vlan_id or edge_update.vlan)
            topology_edge.src_port_label = normalize_text(edge_update.src_port_label)
            topology_edge.dst_port_label = normalize_text(edge_update.dst_port_label)
            topology_edge.review_status = normalize_text(edge_update.review_status or "field_verified")
            topology_edge.evidence_type = "field_verified"
            topology_edge.confidence = 1.0
            topology_edge.manual_note = _append_note(
                topology_edge.manual_note,
                normalize_text(edge_update.manual_note or payload.resolution_note or "工单拓扑链路核实"),
            )
            topology_edge.updated_at = now

        asset_update = payload.asset_update
        asset_id = (
            asset_update.asset_device_id
            if asset_update and asset_update.asset_device_id
            else topology_node.device_id
            if topology_node and topology_node.device_id
            else order.asset_device_id
        )
        asset = db.get(AssetDevice, asset_id) if asset_id else None
        if asset_update and asset_update.asset_device_id and not asset:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset:
            asset_note = normalize_text(
                (asset_update.manual_note if asset_update else "")
                or payload.resolution_note
                or "工单拓扑核实后同步资产状态"
            )
            _sync_asset_from_topology(
                asset,
                device_status=(asset_update.device_status if asset_update else "verified"),
                health_state=(asset_update.health_state if asset_update else "online"),
                area_id=(asset_update.area_id if asset_update else None),
                note=f"工单 #{order.id} 闭环同步：{asset_note}",
            )

        order.status = "closed"
        order.verification_status = "closed"
        order.verified_by = operator
        order.verified_at = now
        order.closed_by = operator
        order.close_reason = normalize_text(payload.close_reason or payload.resolution_note or "拓扑核实闭环结单")
        order.resolved_at = now
        order.resolution_note = _append_note(order.resolution_note, payload.resolution_note or "拓扑核实闭环结单")
        if topology_node:
            order.topology_node_key = topology_node.node_key
        if topology_edge:
            db.flush()
            order.topology_edge_id = topology_edge.id
        if asset:
            order.asset_device_id = asset.id
        order.topology_review_payload = json.dumps(payload.model_dump(), ensure_ascii=False, default=str)
        order.updated_at = now

        alert_payload = None
        if payload.close_alert and order.source_alert_id:
            alert = db.get(OpsAlert, order.source_alert_id)
            if alert:
                alert.status = "resolved"
                alert.resolved_at = now
                alert.last_seen_at = alert.last_seen_at or now
                alert.linked_work_order_id = order.id
                alert.updated_at = now
                alert_payload = {
                    "id": alert.id,
                    "status": alert.status,
                    "resolved_at": alert.resolved_at.isoformat(timespec="seconds") if alert.resolved_at else "",
                }

        db.commit()
        db.refresh(order)
        return {
            "ok": True,
            "work_order": {
                "id": order.id,
                "status": order.status,
                "verification_status": order.verification_status,
                "asset_device_id": order.asset_device_id,
                "topology_node_key": normalize_text(order.topology_node_key),
                "topology_edge_id": order.topology_edge_id,
                "resolved_at": order.resolved_at.isoformat(timespec="seconds") if order.resolved_at else "",
            },
            "asset": {
                "id": asset.id,
                "device_status": asset.device_status,
                "health_state": asset.health_state,
                "area_id": asset.area_id,
            } if asset else None,
            "topology": {
                "node_key": normalize_text(topology_node.node_key) if topology_node else normalize_text(order.topology_node_key),
                "edge_id": topology_edge.id if topology_edge else order.topology_edge_id,
                "review_status": (
                    normalize_text(topology_edge.review_status)
                    if topology_edge
                    else normalize_text(topology_node.review_status)
                    if topology_node
                    else "field_verified"
                ),
            },
            "alert": alert_payload,
        }
    except Exception:
        db.rollback()
        raise

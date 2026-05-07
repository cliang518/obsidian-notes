from datetime import datetime

from pydantic import BaseModel, Field


class AlertCreateWorkOrderRequest(BaseModel):
    assignee_username: str = ""
    priority: str = ""
    manual_note: str = ""
    topology_node_key: str = ""
    topology_edge_id: int | None = None


class AssetUpdateFromTopology(BaseModel):
    asset_device_id: int | None = None
    device_status: str = "verified"
    health_state: str = "online"
    area_id: int | None = None
    manual_note: str = ""


class TopologyNodeUpdateFromWorkOrder(BaseModel):
    node_key: str = ""
    pos_x: float | None = None
    pos_y: float | None = None
    x: float | None = None
    y: float | None = None
    review_status: str = "field_verified"
    manual_note: str = ""


class TopologyEdgeUpdateFromWorkOrder(BaseModel):
    edge_id: int | None = None
    src_node_key: str = ""
    dst_node_key: str = ""
    edge_type: str = "camera"
    vlan: str = ""
    vlan_id: str = ""
    src_port_label: str = ""
    dst_port_label: str = ""
    review_status: str = "field_verified"
    manual_note: str = ""


class ResolveWorkOrderFromTopologyRequest(BaseModel):
    operator: str = ""
    resolution_note: str = ""
    close_reason: str = ""
    close_alert: bool = True
    asset_update: AssetUpdateFromTopology | None = None
    topology_node_update: TopologyNodeUpdateFromWorkOrder | None = None
    topology_edge_update: TopologyEdgeUpdateFromWorkOrder | None = None


class WorkOrderUpsert(BaseModel):
    title: str
    order_type: str = "fault_repair"
    status: str = "open"
    priority: str = "medium"
    area_name: str = ""
    source_type: str = "manual"
    source_alert_id: int | None = None
    asset_device_id: int | None = None
    topology_node_key: str = ""
    topology_edge_id: int | None = None
    verification_status: str = "pending"
    verified_by: str = ""
    verified_at: datetime | None = None
    closed_by: str = ""
    close_reason: str = ""
    topology_review_payload: str = ""
    assignee_username: str = ""
    description: str = ""
    resolution_note: str = ""
    due_at: datetime | None = None


class WorkOrderOut(WorkOrderUpsert):
    id: int
    linked_inspection_count: int = 0
    linked_dispatch_count: int = 0
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkOrderFromAlertResponse(BaseModel):
    ok: bool
    created: bool
    work_order_id: int
    work_order_title: str
    work_order: WorkOrderOut | None = None
    alert: dict = Field(default_factory=dict)


class ResolveWorkOrderFromTopologyResponse(BaseModel):
    ok: bool
    work_order: dict
    asset: dict | None = None
    topology: dict
    alert: dict | None = None


class WorkOrderSummaryOut(BaseModel):
    total_count: int
    open_count: int
    in_progress_count: int
    resolved_count: int
    overdue_count: int
    recent_orders: list[WorkOrderOut]

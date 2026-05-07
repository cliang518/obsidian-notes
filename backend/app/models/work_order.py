from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkOrder(Base):
    __tablename__ = "work_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_type: Mapped[str] = mapped_column(String(80), default="fault_repair")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(40), default="medium")
    area_name: Mapped[str] = mapped_column(String(120), default="")
    source_type: Mapped[str] = mapped_column(String(80), default="manual")
    source_alert_id: Mapped[int | None] = mapped_column(ForeignKey("ops_alert.id"), nullable=True, index=True)
    asset_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    topology_node_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    topology_edge_id: Mapped[int | None] = mapped_column(ForeignKey("network_topology_edge.id"), nullable=True, index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    verified_by: Mapped[str] = mapped_column(String(80), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str] = mapped_column(String(80), default="")
    close_reason: Mapped[str] = mapped_column(Text, default="")
    topology_review_payload: Mapped[str] = mapped_column(Text, default="")
    assignee_username: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

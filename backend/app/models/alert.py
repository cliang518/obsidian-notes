from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpsAlert(Base):
    __tablename__ = "ops_alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_event_key: Mapped[str] = mapped_column(String(255), index=True)
    alert_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    asset_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    linked_work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_order.id"), nullable=True, index=True)
    impacted_scope: Mapped[str] = mapped_column(String(50), default="device", index=True)
    attribution_type: Mapped[str] = mapped_column(String(50), default="legacy_bridge", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

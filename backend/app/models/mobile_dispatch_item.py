from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MobileDispatchItem(Base):
    __tablename__ = "mobile_dispatch_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispatch_type: Mapped[str] = mapped_column(String(50), default="alert", index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    priority: Mapped[str] = mapped_column(String(40), default="medium", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    area_name: Mapped[str] = mapped_column(String(120), default="")
    device_label: Mapped[str] = mapped_column(String(255), default="")
    source_alert_id: Mapped[int | None] = mapped_column(ForeignKey("ops_alert.id"), nullable=True, index=True)
    source_work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_order.id"), nullable=True, index=True)
    source_inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_task.id"), nullable=True, index=True)
    assignee_username: Mapped[str] = mapped_column(String(80), default="")
    mobile_channel_key: Mapped[str] = mapped_column(String(100), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    latest_note: Mapped[str] = mapped_column(Text, default="")
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

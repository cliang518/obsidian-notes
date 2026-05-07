from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InspectionTask(Base):
    __tablename__ = "inspection_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="scheduled", index=True)
    area_name: Mapped[str] = mapped_column(String(120), default="")
    target_type: Mapped[str] = mapped_column(String(80), default="area")
    source_work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_order.id"), nullable=True, index=True)
    owner_username: Mapped[str] = mapped_column(String(80), default="")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

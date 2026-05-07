from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationDeliveryLog(Base):
    __tablename__ = "notification_delivery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channel_registration.id"), index=True)
    channel_key: Mapped[str] = mapped_column(String(100), index=True)
    channel_type: Mapped[str] = mapped_column(String(50), default="webhook", index=True)
    event_type: Mapped[str] = mapped_column(String(100), default="notification_test", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

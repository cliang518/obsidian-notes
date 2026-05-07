from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationChannelRegistration(Base):
    __tablename__ = "notification_channel_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    channel_key: Mapped[str] = mapped_column(String(100), index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    channel_type: Mapped[str] = mapped_column(String(50), default="webhook", index=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), default="")
    auth_mode: Mapped[str] = mapped_column(String(50), default="none")
    target_scope: Mapped[str] = mapped_column(String(100), default="alerts")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    send_resolved: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    suppress_flap_watch: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(50), default="planned", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ControlPlatformRegistration(Base):
    __tablename__ = "control_platform_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    track_key: Mapped[str] = mapped_column(String(50), index=True)
    instance_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    instance_code: Mapped[str] = mapped_column(String(80), default="", index=True)
    endpoint_name: Mapped[str] = mapped_column(String(120), default="")
    endpoint_path: Mapped[str] = mapped_column(String(255), default="")
    vlan_id: Mapped[str] = mapped_column(String(50), default="", index=True)
    vlan_name: Mapped[str] = mapped_column(String(120), default="")
    network_zone: Mapped[str] = mapped_column(String(120), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    platform_family: Mapped[str] = mapped_column(String(100), default="")
    vendor: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    management_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    username_hint: Mapped[str] = mapped_column(String(255), default="")
    access_mode: Mapped[str] = mapped_column(String(50), default="web")
    client_required: Mapped[bool] = mapped_column(Boolean, default=False)
    certificate_required: Mapped[bool] = mapped_column(Boolean, default=False)
    plugin_required: Mapped[bool] = mapped_column(Boolean, default=False)
    read_only_strategy: Mapped[str] = mapped_column(String(100), default="web_audit")
    status: Mapped[str] = mapped_column(String(50), default="reserved", index=True)
    next_action: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    last_audited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("platform_source.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ControlDevice(Base):
    __tablename__ = "control_device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("control_platform_registration.id"), nullable=True, index=True)
    asset_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    external_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    device_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    vendor: Mapped[str] = mapped_column(String(100), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    area_hint: Mapped[str] = mapped_column(String(255), default="", index=True)
    control_status: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ControlPoint(Base):
    __tablename__ = "control_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("control_platform_registration.id"), nullable=True, index=True)
    control_device_id: Mapped[int | None] = mapped_column(ForeignKey("control_device.id"), nullable=True, index=True)
    point_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    point_code: Mapped[str] = mapped_column(String(255), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    io_direction: Mapped[str] = mapped_column(String(50), default="unknown")
    point_status: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    current_value: Mapped[str] = mapped_column(String(255), default="")
    units: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ControlScenario(Base):
    __tablename__ = "control_scenario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("control_platform_registration.id"), nullable=True, index=True)
    scenario_code: Mapped[str] = mapped_column(String(255), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    scenario_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    trigger_mode: Mapped[str] = mapped_column(String(100), default="")
    area_hint: Mapped[str] = mapped_column(String(255), default="", index=True)
    scenario_status: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ControlEvent(Base):
    __tablename__ = "control_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("control_platform_registration.id"), nullable=True, index=True)
    control_device_id: Mapped[int | None] = mapped_column(ForeignKey("control_device.id"), nullable=True, index=True)
    event_code: Mapped[str] = mapped_column(String(255), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), default="", index=True)
    severity: Mapped[str] = mapped_column(String(50), default="info", index=True)
    event_status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    triggered_at: Mapped[str] = mapped_column(String(100), default="", index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ControlMenu(Base):
    __tablename__ = "control_menu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("control_platform_registration.id"), nullable=True, index=True)
    menu_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    parent_menu_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    route_path: Mapped[str] = mapped_column(String(500), default="")
    page_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

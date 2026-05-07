from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FloorPlanDocument(Base):
    __tablename__ = "floor_plan_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="", index=True)
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    file_extension: Mapped[str] = mapped_column(String(20), default="", index=True)
    storage_path: Mapped[str] = mapped_column(String(500), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="cad_upload", index=True)
    parse_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    site: Mapped[str] = mapped_column(String(100), default="", index=True)
    building: Mapped[str] = mapped_column(String(100), default="", index=True)
    floor: Mapped[str] = mapped_column(String(100), default="", index=True)
    zone: Mapped[str] = mapped_column(String(100), default="", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    parser_used: Mapped[str] = mapped_column(String(100), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_suffix_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_anchor_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FloorPlanAnchor(Base):
    __tablename__ = "floor_plan_anchor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("floor_plan_document.id"), index=True)
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    ip_suffix_hint: Mapped[str] = mapped_column(String(16), default="", index=True)
    layer_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="")
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    match_note: Mapped[str] = mapped_column(Text, default="")

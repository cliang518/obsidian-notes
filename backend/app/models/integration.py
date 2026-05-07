from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncJob(Base):
    __tablename__ = "sync_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("platform_source.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")


class SyncSnapshot(Base):
    __tablename__ = "sync_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("platform_source.id"), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(50), index=True)
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class SourceObjectMapping(Base):
    __tablename__ = "source_object_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("platform_source.id"), index=True)
    source_object_type: Mapped[str] = mapped_column(String(50), index=True)
    source_object_key: Mapped[str] = mapped_column(String(255), index=True)
    asset_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    video_channel_id: Mapped[int | None] = mapped_column(ForeignKey("video_channel.id"), nullable=True, index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str] = mapped_column(Text, default="")


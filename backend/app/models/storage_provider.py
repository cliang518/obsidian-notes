from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StorageProviderRegistration(Base):
    __tablename__ = "storage_provider_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_key: Mapped[str] = mapped_column(String(100), index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    provider_type: Mapped[str] = mapped_column(String(50), default="local_filesystem", index=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), default="")
    bucket_or_share: Mapped[str] = mapped_column(String(255), default="")
    auth_mode: Mapped[str] = mapped_column(String(50), default="none")
    usage_scope: Mapped[str] = mapped_column(String(100), default="runtime_cache")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    writable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="planned", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

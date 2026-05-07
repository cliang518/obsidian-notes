from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LlmProviderConfig(Base):
    __tablename__ = "llm_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    provider_type: Mapped[str] = mapped_column(String(100), index=True)
    base_url: Mapped[str] = mapped_column(String(500), default="")
    default_model: Mapped[str] = mapped_column(String(255), default="")
    api_key_env_name: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

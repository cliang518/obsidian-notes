from datetime import datetime

from pydantic import BaseModel, Field


class MobileChannelBase(BaseModel):
    channel_key: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=255)
    channel_type: str = "workspace"
    target_platform: str = ""
    entry_mode: str = "h5"
    deep_link_scheme: str = ""
    auth_mode: str = "session"
    scope: str = "field_ops"
    enabled: bool = True
    mobile_first: bool = True
    status: str = "planned"
    notes: str = ""


class MobileChannelUpsert(MobileChannelBase):
    pass


class MobileChannelOut(MobileChannelBase):
    id: int
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

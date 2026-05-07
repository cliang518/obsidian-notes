from datetime import datetime

from pydantic import BaseModel, Field


class StorageProviderBase(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=255)
    provider_type: str = "local_filesystem"
    endpoint_url: str = ""
    bucket_or_share: str = ""
    auth_mode: str = "none"
    usage_scope: str = "runtime_cache"
    enabled: bool = True
    writable: bool = False
    status: str = "planned"
    notes: str = ""


class StorageProviderUpsert(StorageProviderBase):
    pass


class StorageProviderOut(StorageProviderBase):
    id: int
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

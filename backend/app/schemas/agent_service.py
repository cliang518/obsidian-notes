from datetime import datetime

from pydantic import BaseModel, Field


class AgentServiceBase(BaseModel):
    service_key: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=255)
    service_type: str = "mcp"
    endpoint_url: str = ""
    auth_mode: str = "none"
    access_scope: str = "read_only"
    enabled: bool = True
    read_only_first: bool = True
    status: str = "planned"
    notes: str = ""


class AgentServiceUpsert(AgentServiceBase):
    pass


class AgentServiceOut(AgentServiceBase):
    id: int
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

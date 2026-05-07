from datetime import datetime

from pydantic import BaseModel, Field


class ControlPlatformRegistrationBase(BaseModel):
    track_key: str = Field(..., min_length=2, max_length=50)
    instance_name: str = ""
    instance_code: str = ""
    endpoint_name: str = ""
    endpoint_path: str = ""
    vlan_id: str = ""
    vlan_name: str = ""
    network_zone: str = ""
    display_name: str = Field(..., min_length=2, max_length=255)
    platform_family: str = ""
    vendor: str = ""
    base_url: str = ""
    management_ip: str = ""
    username_hint: str = ""
    access_mode: str = "web"
    client_required: bool = False
    certificate_required: bool = False
    plugin_required: bool = False
    read_only_strategy: str = "web_audit"
    status: str = "reserved"
    next_action: str = ""
    notes: str = ""


class ControlPlatformRegistrationUpsert(ControlPlatformRegistrationBase):
    pass


class ControlPlatformRegistrationOut(ControlPlatformRegistrationBase):
    id: int
    source_id: int | None = None
    last_audited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from datetime import datetime

from pydantic import BaseModel


class NotificationChannelUpsert(BaseModel):
    channel_key: str
    display_name: str
    channel_type: str = "webhook"
    endpoint_url: str = ""
    auth_mode: str = "none"
    target_scope: str = "alerts"
    enabled: bool = True
    send_resolved: bool = True
    alert_cooldown_seconds: int = 300
    suppress_flap_watch: bool = True
    status: str = "planned"
    notes: str = ""


class NotificationChannelOut(BaseModel):
    id: int
    channel_key: str
    display_name: str
    channel_type: str
    endpoint_url: str
    auth_mode: str
    target_scope: str
    enabled: bool
    send_resolved: bool
    alert_cooldown_seconds: int
    suppress_flap_watch: bool
    status: str
    notes: str
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NotificationDeliveryLogOut(BaseModel):
    id: int
    channel_id: int
    channel_key: str
    channel_name: str
    channel_type: str
    event_type: str
    title: str
    message: str
    ok: bool
    status_code: int | None = None
    response_detail: str
    created_at: datetime

from datetime import datetime

from pydantic import BaseModel, Field


class MobileDispatchItemOut(BaseModel):
    id: int
    dispatch_type: str
    status: str
    priority: str
    title: str
    area_name: str
    device_label: str
    source_alert_id: int | None = None
    source_work_order_id: int | None = None
    source_inspection_id: int | None = None
    assignee_username: str
    mobile_channel_key: str
    summary: str
    latest_note: str
    queued_at: datetime
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MobileDispatchCreate(BaseModel):
    assignee_username: str = ""
    mobile_channel_key: str = ""
    latest_note: str = ""


class MobileDispatchUpdate(BaseModel):
    status: str = Field(..., min_length=2, max_length=40)
    assignee_username: str = ""
    mobile_channel_key: str = ""
    latest_note: str = ""

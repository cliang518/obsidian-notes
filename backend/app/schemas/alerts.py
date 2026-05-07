from datetime import datetime

from pydantic import BaseModel


class OpsAlertOut(BaseModel):
    id: int
    source_type: str
    source_event_key: str
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    asset_device_id: int | None
    impacted_scope: str
    attribution_type: str
    occurrence_count: int
    triggered_at: datetime | None
    last_seen_at: datetime | None
    resolved_at: datetime | None
    evidence_summary: str
    device_label: str = ""
    management_ip: str = ""
    area_display_name: str = ""
    linked_work_order_id: int | None = None
    linked_work_order_title: str = ""
    linked_dispatch_count: int = 0

    class Config:
        from_attributes = True

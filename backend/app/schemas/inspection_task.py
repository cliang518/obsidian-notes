from datetime import datetime

from pydantic import BaseModel


class InspectionTaskUpsert(BaseModel):
    title: str
    plan_name: str = ""
    status: str = "scheduled"
    area_name: str = ""
    target_type: str = "area"
    source_work_order_id: int | None = None
    owner_username: str = ""
    scheduled_for: datetime | None = None
    result_summary: str = ""
    notes: str = ""


class InspectionTaskOut(InspectionTaskUpsert):
    id: int
    linked_dispatch_count: int = 0
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InspectionTaskSummaryOut(BaseModel):
    total_count: int
    scheduled_count: int
    in_progress_count: int
    completed_count: int
    overdue_count: int
    recent_tasks: list[InspectionTaskOut]

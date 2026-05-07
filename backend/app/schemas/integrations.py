from pydantic import BaseModel


class IntegrationSourceOut(BaseModel):
    id: int
    source_type: str
    name: str
    vendor: str
    base_url: str
    management_ip: str
    version: str
    sync_status: str

    class Config:
        from_attributes = True


class SyncJobOut(BaseModel):
    id: int
    source_id: int
    job_type: str
    status: str
    summary: str
    error_message: str

    class Config:
        from_attributes = True


class SyncSnapshotOut(BaseModel):
    id: int
    source_id: int
    snapshot_type: str
    object_count: int
    notes: str

    class Config:
        from_attributes = True


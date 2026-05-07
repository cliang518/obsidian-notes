from datetime import datetime

from pydantic import BaseModel


class UserAccountUpsert(BaseModel):
    username: str
    display_name: str
    role: str = "technician"
    status: str = "pending"
    department: str = ""
    mobile: str = ""
    email: str = ""
    account_source: str = "local"
    password_ready: bool = False
    initial_password: str = ""
    notes: str = ""


class UserAccountOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    status: str
    department: str
    mobile: str
    email: str
    account_source: str
    password_ready: bool
    last_login_at: datetime | None = None
    approved_at: datetime | None = None
    notes: str


class UserSummaryOut(BaseModel):
    account_count: int
    active_count: int
    pending_count: int
    role_breakdown: list[dict]
    status_breakdown: list[dict]
    recent_accounts: list[UserAccountOut]

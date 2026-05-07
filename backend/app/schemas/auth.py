from datetime import datetime

from pydantic import BaseModel


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthRegisterRequest(BaseModel):
    username: str
    display_name: str
    password: str
    mobile: str = ""
    email: str = ""
    department: str = ""
    notes: str = ""


class AuthChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthUserOut(BaseModel):
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


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut

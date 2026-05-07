from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LicenseStatusResponse(BaseModel):
    active: bool
    product_code: str
    product_name: str
    machine_code: str
    fingerprint: str
    hostname: str
    issued_to: str | None = None
    contact: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    license_type: str | None = None
    max_devices: int | None = None
    features: list[str] = []
    reason: str | None = None
    request_payload: dict[str, Any]
    expired: bool = False
    in_grace_period: bool = False
    grace_deadline: str | None = None
    renewal_required: bool = False
    days_remaining: int | None = None


class LicenseActivateRequest(BaseModel):
    license_data: dict[str, Any]


class LicenseActivateResponse(BaseModel):
    ok: bool
    message: str
    status: LicenseStatusResponse

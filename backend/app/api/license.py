from __future__ import annotations

from fastapi import APIRouter

from app.schemas.license import LicenseActivateRequest, LicenseActivateResponse, LicenseStatusResponse
from app.services.license import activate_license, get_license_status


router = APIRouter()


@router.get("/status", response_model=LicenseStatusResponse)
def license_status():
    return get_license_status()


@router.get("/request", response_model=LicenseStatusResponse)
def license_request():
    return get_license_status()


@router.post("/activate", response_model=LicenseActivateResponse)
def license_activate(payload: LicenseActivateRequest):
    status = activate_license(payload.license_data)
    return LicenseActivateResponse(ok=True, message="授权已写入，系统可以开始使用。", status=status)

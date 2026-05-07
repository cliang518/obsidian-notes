from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.settings import settings


LICENSE_DIR = settings.runtime_dir / "license"
LICENSE_FILE = LICENSE_DIR / "license.json"


def ensure_license_dir() -> None:
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat()


def _machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def get_machine_fingerprint() -> str:
    parts = [
        settings.license_product_code,
        _machine_guid(),
        socket.gethostname(),
        hex(uuid.getnode()),
        os.getenv("PROCESSOR_IDENTIFIER", ""),
    ]
    raw = "|".join(part.strip() for part in parts if part and str(part).strip())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_machine_code() -> str:
    digest = get_machine_fingerprint().upper()
    return "-".join(digest[i:i + 4] for i in range(0, 24, 4))


def build_request_payload() -> dict[str, Any]:
    return {
        "product_code": settings.license_product_code,
        "product_name": settings.app_name,
        "app_version": settings.app_version,
        "machine_code": get_machine_code(),
        "fingerprint": get_machine_fingerprint(),
        "hostname": socket.gethostname(),
        "generated_at": now_iso(),
    }


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_license_payload(payload: dict[str, Any]) -> str:
    digest = hmac.new(
        settings.license_signing_secret.encode("utf-8"),
        _canonical_payload(payload),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_license_signature(payload: dict[str, Any], signature: str) -> bool:
    expected = sign_license_payload(payload)
    return hmac.compare_digest(expected, signature or "")


def save_license(license_data: dict[str, Any]) -> Path:
    ensure_license_dir()
    LICENSE_FILE.write_text(json.dumps(license_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return LICENSE_FILE


def load_license() -> dict[str, Any] | None:
    if not LICENSE_FILE.exists():
        return None
    try:
        return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _license_payload_and_signature(license_data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    payload = {key: value for key, value in license_data.items() if key != "signature"}
    signature = str(license_data.get("signature") or "")
    return payload, signature


def _parse_expiry(expires_at: str | None) -> tuple[datetime | None, str | None]:
    if not expires_at:
        return None, None
    try:
        return datetime.fromisoformat(expires_at), None
    except ValueError:
        return None, "授权文件中的到期时间格式无效"


def _license_runtime_status(payload: dict[str, Any], request_payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    expiry, expiry_error = _parse_expiry(payload.get("expires_at"))
    if expiry_error:
        return False, {"reason": expiry_error}

    now_value = now()
    grace_deadline = expiry + timedelta(days=settings.license_grace_days) if expiry else None
    in_grace = bool(expiry and expiry < now_value <= grace_deadline)
    expired = bool(expiry and now_value > expiry)
    hard_expired = bool(grace_deadline and now_value > grace_deadline)

    runtime = {
        "expired": expired,
        "in_grace_period": in_grace,
        "grace_deadline": grace_deadline.isoformat() if grace_deadline else None,
        "renewal_required": in_grace,
        "days_remaining": None,
        "reason": "授权有效",
    }

    if expiry:
        runtime["days_remaining"] = (expiry.date() - now_value.date()).days

    if payload.get("product_code") != settings.license_product_code:
        return False, {**runtime, "reason": "授权产品编码不匹配"}

    if payload.get("machine_code") != request_payload["machine_code"]:
        return False, {**runtime, "reason": "授权机器码不匹配"}

    if payload.get("fingerprint") != request_payload["fingerprint"]:
        return False, {**runtime, "reason": "主机指纹不匹配，需要重新认证"}

    if hard_expired:
        return False, {**runtime, "renewal_required": True, "reason": "授权已过期且超过宽限期"}

    if in_grace:
        return True, {**runtime, "reason": "授权已到期，当前处于 3 天宽限期内，请尽快重新认证"}

    return True, runtime


def get_license_status() -> dict[str, Any]:
    request_payload = build_request_payload()
    license_data = load_license()

    status = {
        "active": False,
        "product_code": settings.license_product_code,
        "product_name": settings.app_name,
        "machine_code": request_payload["machine_code"],
        "fingerprint": request_payload["fingerprint"],
        "hostname": request_payload["hostname"],
        "issued_to": None,
        "contact": None,
        "issued_at": None,
        "expires_at": None,
        "license_type": None,
        "max_devices": None,
        "features": [],
        "reason": "系统尚未注册，请导出注册信息并导入授权文件。",
        "request_payload": request_payload,
        "expired": False,
        "in_grace_period": False,
        "grace_deadline": None,
        "renewal_required": False,
        "days_remaining": None,
    }

    if not settings.license_enforced:
        status["active"] = True
        status["reason"] = "当前环境未启用授权校验"
        status["license_type"] = "development"
        status["features"] = ["all"]
        return status

    if not license_data:
        return status

    payload, signature = _license_payload_and_signature(license_data)
    if not verify_license_signature(payload, signature):
        status["reason"] = "授权签名无效"
        return status

    active, runtime = _license_runtime_status(payload, request_payload)
    status.update(runtime)
    if not active:
        return status

    status.update(
        {
            "active": True,
            "issued_to": payload.get("issued_to"),
            "contact": payload.get("contact"),
            "issued_at": payload.get("issued_at"),
            "expires_at": payload.get("expires_at"),
            "license_type": payload.get("license_type", "annual"),
            "max_devices": payload.get("max_devices"),
            "features": payload.get("features") or ["all"],
        }
    )
    return status


def require_active_license() -> dict[str, Any]:
    status = get_license_status()
    if not status["active"]:
        raise HTTPException(status_code=403, detail={"code": "license_required", "message": status["reason"]})
    return status


def activate_license(license_data: dict[str, Any]) -> dict[str, Any]:
    payload, signature = _license_payload_and_signature(license_data)
    if not signature:
        raise HTTPException(status_code=400, detail="授权文件缺少签名")
    if not verify_license_signature(payload, signature):
        raise HTTPException(status_code=400, detail="授权签名校验失败")

    request_payload = build_request_payload()
    active, runtime = _license_runtime_status(payload, request_payload)
    if not active and runtime["reason"] != "授权已到期，当前处于 3 天宽限期内，请尽快重新认证":
        raise HTTPException(status_code=400, detail=runtime["reason"])

    save_license({**payload, "signature": signature})
    return get_license_status()


def build_signed_license(
    *,
    issued_to: str,
    contact: str | None,
    machine_code: str,
    fingerprint: str,
    hostname: str,
    expires_at: str | None = None,
    license_type: str = "annual",
    max_devices: int | None = None,
    features: list[str] | None = None,
) -> dict[str, Any]:
    expiry = expires_at or (now() + timedelta(days=settings.license_default_valid_days)).isoformat()
    payload = {
        "product_code": settings.license_product_code,
        "product_name": settings.app_name,
        "machine_code": machine_code,
        "fingerprint": fingerprint,
        "hostname": hostname,
        "issued_to": issued_to,
        "contact": contact,
        "issued_at": now_iso(),
        "expires_at": expiry,
        "license_type": license_type,
        "max_devices": max_devices,
        "features": features or ["all"],
    }
    return {
        **payload,
        "signature": sign_license_payload(payload),
    }

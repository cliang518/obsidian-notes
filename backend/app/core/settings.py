import os
from dataclasses import dataclass
from pathlib import Path


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("V2_APP_NAME", "Yongjia Weak Current Ops Platform V2")
    app_version: str = os.getenv("V2_APP_VERSION", "2.0.0-dev")
    root_dir: Path = Path(__file__).resolve().parents[3]
    runtime_dir: Path = root_dir / "runtime"
    database_path: Path = runtime_dir / "platform_v2.db"
    license_enforced: bool = env_bool("V2_LICENSE_ENFORCED", False)
    license_product_code: str = os.getenv("V2_LICENSE_PRODUCT_CODE", "YJ-WEAKCURRENT-V2")
    license_signing_secret: str = os.getenv("V2_LICENSE_SIGNING_SECRET", "yongjia-v2-license-secret")
    license_default_valid_days: int = int(os.getenv("V2_LICENSE_DEFAULT_VALID_DAYS", "365"))
    license_grace_days: int = int(os.getenv("V2_LICENSE_GRACE_DAYS", "3"))
    auth_session_hours: int = int(os.getenv("V2_AUTH_SESSION_HOURS", "12"))
    bootstrap_admin_username: str = os.getenv("V2_BOOTSTRAP_ADMIN_USERNAME", "admin")
    bootstrap_admin_password: str = os.getenv("V2_BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    bootstrap_manager_password: str = os.getenv("V2_BOOTSTRAP_MANAGER_PASSWORD", "manager123")
    bootstrap_technician_password: str = os.getenv("V2_BOOTSTRAP_TECHNICIAN_PASSWORD", "tech123")


settings = Settings()

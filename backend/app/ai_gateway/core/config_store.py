from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hmac
from ipaddress import ip_address, ip_network
import json
from pathlib import Path
import secrets
from typing import Any

import yaml

from app.ai_gateway.core.logging import get_ai_gateway_logger
from app.core.settings import settings


logger = get_ai_gateway_logger()

RUNTIME_DIR: Path = settings.runtime_dir / "ai_gateway"
CONFIG_PATH: Path = RUNTIME_DIR / "ai_gateway.yaml"
SESSIONS_DIR: Path = RUNTIME_DIR / "sessions"
MEMORY_DIR: Path = RUNTIME_DIR / "memory"
DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parents[1] / "defaults" / "ai_gateway.yaml"
OPENCLAW_SERVICE_KEY_PATH: Path = RUNTIME_DIR / "openclaw.service-key.txt"
ACCESS_LOG_PATH: Path = RUNTIME_DIR / "ai_gateway_access.jsonl"


def _load_config_file() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write_config_file(config: dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, allow_unicode=True, sort_keys=False)


def ensure_openclaw_service_key() -> str:
    """Create a dedicated service key so OpenClaw can call the gateway without a user login."""

    config = _load_config_file()
    service_keys = list(config.get("service_keys") or [])
    openclaw_key = None
    changed = False
    for row in service_keys:
        if str(row.get("key_id", "")).strip() == "openclaw":
            openclaw_key = row
            break

    if not openclaw_key or not str(openclaw_key.get("key", "")).strip():
        generated_key = f"yj-ai-{secrets.token_urlsafe(32)}"
        openclaw_key = {
            "key_id": "openclaw",
            "display_name": "OpenClaw 局域网服务密钥",
            "enabled": True,
            "key": generated_key,
            "allowed_clients": ["127.0.0.1", "::1", "192.168.119.15"],
            "scopes": [
                "summary",
                "gateway",
                "session",
                "agents",
                "llms",
                "alert_analyze",
                "report_generate",
                "device_query",
            ],
        }
        service_keys = [row for row in service_keys if str(row.get("key_id", "")).strip() != "openclaw"]
        service_keys.append(openclaw_key)
        config["service_keys"] = service_keys
        changed = True

    default_clients = ["127.0.0.1", "::1", "192.168.119.15", "192.168.119.149"]
    allowed_clients = [str(item) for item in openclaw_key.get("allowed_clients", []) or []]
    for client in default_clients:
        if client not in allowed_clients:
            allowed_clients.append(client)
            changed = True
    openclaw_key["allowed_clients"] = allowed_clients
    default_scopes = [
        "summary",
        "gateway",
        "session",
        "agents",
        "llms",
        "logs",
        "logs_cleanup",
        "alert_analyze",
        "report_generate",
        "device_query",
    ]
    scopes = [str(item) for item in openclaw_key.get("scopes", []) or []]
    for scope in default_scopes:
        if scope not in scopes:
            scopes.append(scope)
            changed = True
    openclaw_key["scopes"] = scopes
    if changed:
        config["service_keys"] = service_keys
        _write_config_file(config)

    key_value = str(openclaw_key.get("key", "")).strip()
    OPENCLAW_SERVICE_KEY_PATH.write_text(
        "\n".join(
            [
                "OpenClaw AI Gateway Service Key",
                "Header: X-AI-Gateway-Key",
                f"Value: {key_value}",
                "Gateway: http://192.168.119.149:8011/api/ai/gateway",
                "Summary: http://192.168.119.149:8011/api/ai/summary",
                "Allowed clients: 192.168.119.15, 192.168.119.149, 127.0.0.1, ::1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return key_value


def _client_allowed(client_host: str, allowed_clients: list[str]) -> bool:
    if not allowed_clients:
        return True
    for rule in allowed_clients:
        value = str(rule or "").strip()
        if not value:
            continue
        if value == client_host:
            return True
        try:
            if "/" in value and ip_address(client_host) in ip_network(value, strict=False):
                return True
        except ValueError:
            continue
    return False


def validate_service_key(provided_key: str | None, client_host: str, required_scope: str | None = None) -> dict[str, Any] | None:
    key_value = str(provided_key or "").strip()
    if not key_value:
        return None
    config = load_config()
    for row in config.get("service_keys", []) or []:
        expected_key = str(row.get("key", "")).strip()
        scopes = [str(scope) for scope in row.get("scopes", []) or []]
        if not row.get("enabled", False) or not expected_key:
            continue
        if not hmac.compare_digest(key_value, expected_key):
            continue
        if required_scope and required_scope not in scopes and "*" not in scopes:
            return {"allowed": False, "reason": "scope_denied", "key_id": row.get("key_id", "")}
        if not _client_allowed(client_host, list(row.get("allowed_clients", []) or [])):
            return {"allowed": False, "reason": "client_denied", "key_id": row.get("key_id", "")}
        return {
            "allowed": True,
            "key_id": row.get("key_id", ""),
            "display_name": row.get("display_name", ""),
            "scopes": scopes,
            "client_host": client_host,
        }
    return None


def record_service_access_event(event: dict[str, Any]) -> None:
    ensure_bootstrap()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with ACCESS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_service_access_events(limit: int = 100) -> list[dict[str, Any]]:
    ensure_bootstrap()
    limit = max(1, min(int(limit or 100), 500))
    if not ACCESS_LOG_PATH.exists():
        return []
    rows = ACCESS_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    events: list[dict[str, Any]] = []
    for line in rows[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"timestamp": "", "raw": line, "parse_error": True})
    return events


def prune_service_access_events(keep_days: int = 30, max_lines: int = 5000) -> dict[str, int]:
    ensure_bootstrap()
    if not ACCESS_LOG_PATH.exists():
        return {"before": 0, "after": 0, "removed": 0}

    keep_days = max(1, int(keep_days or 30))
    max_lines = max(100, int(max_lines or 5000))
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    rows = ACCESS_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept: list[str] = []
    for line in rows:
        try:
            event = json.loads(line)
            timestamp = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
            if timestamp >= cutoff:
                kept.append(line)
        except Exception:
            kept.append(line)
    if len(kept) > max_lines:
        kept = kept[-max_lines:]
    ACCESS_LOG_PATH.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return {"before": len(rows), "after": len(kept), "removed": len(rows) - len(kept)}


def ensure_bootstrap() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("AI gateway default config initialized: %s", CONFIG_PATH)
    ensure_openclaw_service_key()
    return CONFIG_PATH


def load_config() -> dict[str, Any]:
    ensure_bootstrap()
    raw = _load_config_file()
    config = deepcopy(raw)
    config.setdefault("gateway", {})
    config.setdefault("agents", [])
    config.setdefault("llms", [])
    config.setdefault("protocols", [])
    config.setdefault("skills", [])
    config.setdefault("service_keys", [])
    return config


def save_config(config: dict[str, Any]) -> Path:
    ensure_bootstrap()
    _write_config_file(config)
    logger.info("AI gateway config saved: %s", CONFIG_PATH)
    return CONFIG_PATH


def upsert_list_item(section: str, item: dict[str, Any], key_field: str) -> dict[str, Any]:
    config = load_config()
    items = list(config.get(section, []))
    key_value = str(item.get(key_field, "")).strip()
    if not key_value:
        raise ValueError(f"{section}.{key_field}_required")

    updated = False
    for index, row in enumerate(items):
        if str(row.get(key_field, "")).strip() == key_value:
            items[index] = {**row, **item}
            updated = True
            break
    if not updated:
        items.append(item)
    config[section] = items
    save_config(config)
    return next(row for row in config[section] if str(row.get(key_field, "")).strip() == key_value)


def delete_list_item(section: str, key_value: str, key_field: str) -> dict[str, Any]:
    config = load_config()
    items = list(config.get(section, []))
    normalized_key = str(key_value or "").strip()
    if not normalized_key:
        raise ValueError(f"{section}.{key_field}_required")

    kept = [row for row in items if str(row.get(key_field, "")).strip() != normalized_key]
    if len(kept) == len(items):
        raise KeyError(normalized_key)

    config[section] = kept
    save_config(config)
    return {"deleted": True, key_field: normalized_key}

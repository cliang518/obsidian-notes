from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.core.settings import settings


DEFAULT_ALERT_GUARD_SETTINGS = {
    "lookback_minutes": 10,
    "min_events": 12,
    "min_devices": 8,
    "min_areas": 3,
    "min_sources": 2,
    "watch_device_threshold": 5,
    "exclude_flap_watch": True,
}


SETTINGS_BOUNDS = {
    "lookback_minutes": (3, 60),
    "min_events": (3, 500),
    "min_devices": (1, 500),
    "min_areas": (1, 50),
    "min_sources": (1, 20),
    "watch_device_threshold": (1, 500),
}


def _settings_path() -> Path:
    return Path(settings.runtime_dir) / "alert_guard_settings.json"


def get_alert_guard_settings() -> dict:
    payload = dict(DEFAULT_ALERT_GUARD_SETTINGS)
    path = _settings_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive fallback
            stored = {}
        for key in DEFAULT_ALERT_GUARD_SETTINGS:
            if key in stored:
                payload[key] = stored[key]
        payload["updated_at"] = stored.get("updated_at")
    else:
        payload["updated_at"] = None
    payload["config_path"] = str(path)
    return _sanitize_settings(payload)


def update_alert_guard_settings(raw: dict) -> dict:
    current = get_alert_guard_settings()
    merged = {**current, **(raw or {})}
    normalized = _sanitize_settings(merged)
    normalized["updated_at"] = datetime.utcnow().isoformat()
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    to_store = {key: normalized[key] for key in DEFAULT_ALERT_GUARD_SETTINGS}
    to_store["updated_at"] = normalized["updated_at"]
    path.write_text(json.dumps(to_store, ensure_ascii=False, indent=2), encoding="utf-8")
    normalized["config_path"] = str(path)
    return normalized


def _sanitize_settings(payload: dict) -> dict:
    normalized = {}
    for key, default_value in DEFAULT_ALERT_GUARD_SETTINGS.items():
        value = payload.get(key, default_value)
        if isinstance(default_value, bool):
            normalized[key] = bool(value)
            continue
        lower, upper = SETTINGS_BOUNDS[key]
        try:
            normalized[key] = min(max(int(value), lower), upper)
        except Exception:  # pragma: no cover - defensive fallback
            normalized[key] = default_value
    normalized["updated_at"] = payload.get("updated_at")
    normalized["config_path"] = str(_settings_path())
    return normalized

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control_domain import ControlDevice, ControlEvent, ControlMenu, ControlPoint, ControlScenario
from app.models.control_platform import ControlPlatformRegistration
from app.models.integration import SyncJob, SyncSnapshot
from app.services.text_normalize import normalize_text


ROOT_DIR = Path(__file__).resolve().parents[3]
CONTROL_AUDIT_ROOT = ROOT_DIR.parent / "docs" / "control-audit"

EXPECTED_AUDIT_FILES = {
    "metadata.json": "平台基础信息、版本、登录入口、厂商、说明",
    "devices.csv": "控制设备清单",
    "points.csv": "点位清单，包含输入、输出、状态或测点",
    "scenarios.csv": "场景、联动、策略或回路清单",
    "menus.json": "菜单树、功能入口或路由结构",
    "events.csv": "事件、日志、告警或操作记录",
}

FIELD_HINTS = {
    "devices": {
        "required": {
            "identity": ("display_name", "name", "device_name", "title", "external_key", "device_id", "id", "code"),
        },
        "optional": {
            "device_type": ("device_type", "type", "category"),
            "vendor": ("vendor", "brand"),
            "model": ("model", "device_model"),
            "area_hint": ("area_hint", "area", "zone", "location"),
            "status": ("control_status", "status", "state"),
        },
    },
    "points": {
        "required": {
            "identity": ("display_name", "name", "point_name", "title", "point_code", "code", "id"),
        },
        "optional": {
            "point_type": ("point_type", "type", "category"),
            "device_ref": ("device_ref", "device_id", "device_name", "parent_device"),
            "direction": ("io_direction", "direction", "io"),
            "status": ("point_status", "status", "state"),
            "value": ("current_value", "value", "current"),
        },
    },
    "scenarios": {
        "required": {
            "identity": ("display_name", "name", "scenario_name", "title", "scenario_code", "code", "id"),
        },
        "optional": {
            "scenario_type": ("scenario_type", "type", "category"),
            "trigger": ("trigger_mode", "trigger", "mode"),
            "area_hint": ("area_hint", "area", "zone", "location"),
            "status": ("scenario_status", "status", "state"),
        },
    },
    "events": {
        "required": {
            "identity": ("title", "event_title", "name", "event_code", "event_id", "code", "id"),
        },
        "optional": {
            "event_type": ("event_type", "type", "category"),
            "device_ref": ("device_ref", "device_id", "device_name", "source_device"),
            "severity": ("level", "severity"),
            "status": ("status", "event_status", "state"),
            "time": ("triggered_at", "event_time", "time"),
        },
    },
    "menus": {
        "required": {
            "identity": ("display_name", "name", "title", "label", "menu_key", "key", "id", "code"),
        },
        "optional": {
            "parent": ("parent_menu_key", "parent", "parent_id"),
            "route": ("route_path", "path", "url"),
            "page_type": ("page_type", "type", "category"),
            "sort": ("sort_index", "sort", "order"),
        },
    },
}


@dataclass(frozen=True)
class ControlAuditImportStats:
    registration_id: int
    display_name: str
    bundle_dir: str
    devices: int = 0
    points: int = 0
    scenarios: int = 0
    events: int = 0
    menus: int = 0
    missing_files: int = 0
    present_files: int = 0


def control_audit_bundle_template(track_key: str) -> dict:
    normalized = (track_key or "").strip() or "control_platform"
    return {
        "track_key": normalized,
        "expected_root": str(CONTROL_AUDIT_ROOT / normalized),
        "expected_files": [
            {"name": name, "description": description}
            for name, description in EXPECTED_AUDIT_FILES.items()
        ],
        "notes": [
            "只读审计资料建议按平台分别存放到 docs/control-audit/<track_key>/。",
            "CSV 推荐 UTF-8 编码，首行保留字段名；JSON 建议保留原始菜单和元信息。",
            "设备、点位、场景三类表格允许字段不完全一致，导入器会按常见别名自动识别。",
        ],
    }


def inspect_control_audit_bundle(bundle_dir: str | Path) -> dict:
    root = Path(bundle_dir)
    files: list[dict] = []
    present = 0
    for name, description in EXPECTED_AUDIT_FILES.items():
        path = root / name
        exists = path.exists()
        if exists:
            present += 1
        files.append(
            {
                "name": name,
                "description": description,
                "exists": exists,
                "path": str(path),
            }
        )

    return {
        "bundle_dir": str(root),
        "exists": root.exists(),
        "present_files": present,
        "missing_files": len(EXPECTED_AUDIT_FILES) - present,
        "files": files,
    }


def preview_control_audit_bundle(bundle_dir: str | Path) -> dict:
    root = Path(bundle_dir)
    inspection = inspect_control_audit_bundle(root)
    metadata = _read_json(root / "metadata.json")
    devices = _read_csv(root / "devices.csv")
    points = _read_csv(root / "points.csv")
    scenarios = _read_csv(root / "scenarios.csv")
    events = _read_csv(root / "events.csv")
    menus_payload = _read_json(root / "menus.json")
    menus = menus_payload.get("menus", []) if isinstance(menus_payload, dict) else []
    if not isinstance(menus, list):
        menus = []

    def _sample(rows: list[dict], keys: tuple[str, ...], limit: int = 5) -> list[str]:
        samples: list[str] = []
        for raw in rows[:limit]:
            row = _normalize_row(raw)
            value = _first_value(row, *keys)
            if value:
                samples.append(value)
        return samples

    def _headers(rows: list[dict], limit: int = 24) -> list[str]:
        if not rows:
            return []
        return [normalize_text(str(key)).strip() for key in list(rows[0].keys())[:limit]]

    def _compatibility(headers: list[str], row_count: int, hint_key: str) -> dict:
        hint = FIELD_HINTS[hint_key]
        header_set = {normalize_text(item).strip().lower() for item in headers}
        if row_count == 0:
            required_groups = [
                {
                    "group": group_name,
                    "matched": [],
                    "expected_aliases": list(aliases),
                    "ok": False,
                }
                for group_name, aliases in hint["required"].items()
            ]
            optional_groups = [
                {
                    "group": group_name,
                    "matched": [],
                    "expected_aliases": list(aliases),
                    "ok": False,
                }
                for group_name, aliases in hint["optional"].items()
            ]
            return {
                "status": "empty",
                "label": "待填充资料",
                "required_ok": 0,
                "required_total": len(hint["required"]),
                "optional_ok": 0,
                "optional_total": len(hint["optional"]),
                "required_groups": required_groups,
                "optional_groups": optional_groups,
                "missing_required_groups": [group["group"] for group in required_groups],
                "missing_optional_groups": [group["group"] for group in optional_groups],
                "missing_required_alias_hints": {
                    group["group"]: group["expected_aliases"][:8] for group in required_groups
                },
            }
        required_result = []
        optional_result = []
        required_ok = 0

        for group_name, aliases in hint["required"].items():
            matched = [alias for alias in aliases if alias in header_set]
            if matched:
                required_ok += 1
            required_result.append(
                {
                    "group": group_name,
                    "matched": matched,
                    "expected_aliases": list(aliases),
                    "ok": bool(matched),
                }
            )

        optional_ok = 0
        for group_name, aliases in hint["optional"].items():
            matched = [alias for alias in aliases if alias in header_set]
            if matched:
                optional_ok += 1
            optional_result.append(
                {
                    "group": group_name,
                    "matched": matched,
                    "expected_aliases": list(aliases),
                    "ok": bool(matched),
                }
            )

        required_total = len(hint["required"])
        optional_total = len(hint["optional"])
        required_ratio = required_ok / required_total if required_total else 1
        optional_ratio = optional_ok / optional_total if optional_total else 1

        if required_ratio == 1 and optional_ratio >= 0.5:
            status = "ready"
            label = "可直接导入"
        elif required_ratio == 1:
            status = "mostly_ready"
            label = "基本可导入"
        elif required_ratio >= 0.5:
            status = "partial"
            label = "需补字段"
        else:
            status = "insufficient"
            label = "暂不可导入"

        return {
            "status": status,
            "label": label,
            "required_ok": required_ok,
            "required_total": required_total,
            "optional_ok": optional_ok,
            "optional_total": optional_total,
            "required_groups": required_result,
            "optional_groups": optional_result,
            "missing_required_groups": [group["group"] for group in required_result if not group["ok"]],
            "missing_optional_groups": [group["group"] for group in optional_result if not group["ok"]],
            "missing_required_alias_hints": {
                group["group"]: group["expected_aliases"][:8] for group in required_result if not group["ok"]
            },
        }

    device_headers = _headers(devices)
    point_headers = _headers(points)
    scenario_headers = _headers(scenarios)
    event_headers = _headers(events)
    menu_headers = _headers(menus)

    menu_root_keys = []
    if isinstance(menus_payload, dict):
        menu_root_keys = [normalize_text(str(key)).strip() for key in list(menus_payload.keys())[:24]]

    compatibility = {
        "devices": _compatibility(device_headers, len(devices), "devices"),
        "points": _compatibility(point_headers, len(points), "points"),
        "scenarios": _compatibility(scenario_headers, len(scenarios), "scenarios"),
        "events": _compatibility(event_headers, len(events), "events"),
        "menus": _compatibility(menu_headers, len(menus), "menus"),
    }

    warnings: list[dict] = []
    if inspection["missing_files"]:
        warnings.append(
            {
                "level": "warning",
                "scope": "bundle",
                "message": f"资料目录缺少 {inspection['missing_files']} 个标准文件。",
            }
        )

    counts = {
        "devices": len(devices),
        "points": len(points),
        "scenarios": len(scenarios),
        "events": len(events),
        "menus": len(menus),
    }

    for key, label in {
        "devices": "设备",
        "points": "点位",
        "scenarios": "场景",
        "events": "事件",
        "menus": "菜单",
    }.items():
        if counts[key] == 0:
            warnings.append(
                {
                    "level": "info",
                    "scope": key,
                    "message": f"{label}资料当前没有数据行，适合先做模板核对。",
                }
            )
        comp = compatibility[key]
        if comp["status"] == "partial":
            warnings.append(
                {
                    "level": "warning",
                    "scope": key,
                    "message": f"{label}资料存在必需字段缺口，导入前建议先补字段。",
                }
            )
        elif comp["status"] == "insufficient":
            warnings.append(
                {
                    "level": "error",
                    "scope": key,
                    "message": f"{label}资料关键标识字段不足，当前不能可靠导入。",
                }
            )

    if metadata.get("vendor") == "" and metadata.get("platform_family") == "":
        warnings.append(
            {
                "level": "info",
                "scope": "metadata",
                "message": "元信息缺少厂商和平台类型，建议补齐以便后续归档和比对。",
            }
        )

    ready_objects = sum(1 for item in compatibility.values() if item["status"] in {"ready", "mostly_ready"})
    partial_objects = sum(1 for item in compatibility.values() if item["status"] == "partial")
    blocked_objects = sum(1 for item in compatibility.values() if item["status"] == "insufficient")
    empty_objects = sum(1 for item in compatibility.values() if item["status"] == "empty")

    if blocked_objects:
        readiness_label = "当前不建议导入"
        readiness_status = "blocked"
    elif partial_objects:
        readiness_label = "可预处理后导入"
        readiness_status = "needs_review"
    elif ready_objects:
        readiness_label = "可进入导入准备"
        readiness_status = "ready"
    else:
        readiness_label = "待填充资料"
        readiness_status = "empty"

    return {
        **inspection,
        "metadata": {
            "vendor": normalize_text(str(metadata.get("vendor", ""))),
            "platform_family": normalize_text(str(metadata.get("platform_family", ""))),
            "base_url": str(metadata.get("base_url", "")).strip(),
            "username_hint": normalize_text(str(metadata.get("username_hint", ""))),
            "version": normalize_text(str(metadata.get("version", ""))),
        },
        "counts": counts,
        "samples": {
            "devices": _sample(devices, ("display_name", "name", "device_name", "title", "external_key", "device_id")),
            "points": _sample(points, ("display_name", "name", "point_name", "title", "point_code", "code")),
            "scenarios": _sample(scenarios, ("display_name", "name", "scenario_name", "title", "scenario_code", "code")),
            "events": _sample(events, ("title", "event_title", "name", "event_code", "event_id", "code")),
            "menus": _sample(menus, ("display_name", "name", "title", "label", "menu_key", "key")),
        },
        "schemas": {
            "devices": device_headers,
            "points": point_headers,
            "scenarios": scenario_headers,
            "events": event_headers,
            "menus": menu_headers,
            "metadata": [normalize_text(str(key)).strip() for key in list(metadata.keys())[:24]],
            "menu_root_keys": menu_root_keys,
        },
        "compatibility": compatibility,
        "warnings": warnings,
        "readiness": {
            "status": readiness_status,
            "label": readiness_label,
            "ready_objects": ready_objects,
            "partial_objects": partial_objects,
            "blocked_objects": blocked_objects,
            "empty_objects": empty_objects,
        },
    }


def compare_control_audit_bundles(left_bundle_dir: str | Path, right_bundle_dir: str | Path) -> dict:
    left = preview_control_audit_bundle(left_bundle_dir)
    right = preview_control_audit_bundle(right_bundle_dir)

    metrics = ["devices", "points", "scenarios", "events", "menus"]
    counts_delta = {
        key: {
            "left": left["counts"].get(key, 0),
            "right": right["counts"].get(key, 0),
            "delta": left["counts"].get(key, 0) - right["counts"].get(key, 0),
        }
        for key in metrics
    }

    def _schema_compare(left_items: list[str], right_items: list[str]) -> dict:
        left_set = {normalize_text(item).strip() for item in left_items if normalize_text(item).strip()}
        right_set = {normalize_text(item).strip() for item in right_items if normalize_text(item).strip()}
        shared = sorted(left_set & right_set)
        return {
            "shared": shared[:24],
            "left_only": sorted(left_set - right_set)[:24],
            "right_only": sorted(right_set - left_set)[:24],
        }

    def _score(bundle: dict) -> int:
        readiness = bundle.get("readiness", {})
        return (
            readiness.get("ready_objects", 0) * 3
            + readiness.get("partial_objects", 0) * 1
            - readiness.get("blocked_objects", 0) * 3
            - bundle.get("missing_files", 0) * 2
        )

    left_score = _score(left)
    right_score = _score(right)
    if left_score > right_score:
        preferred_side = "left"
        preferred_label = "优先以左侧资料包为主继续接入"
    elif right_score > left_score:
        preferred_side = "right"
        preferred_label = "优先以右侧资料包为主继续接入"
    else:
        preferred_side = "balanced"
        preferred_label = "两侧资料包当前完整度接近，建议并行核对"

    recommendations: list[str] = []
    for side_key, bundle, side_name in [("left", left, "左侧资料包"), ("right", right, "右侧资料包")]:
        readiness = bundle.get("readiness", {})
        if bundle.get("missing_files", 0):
            recommendations.append(f"{side_name} 仍缺少标准资料文件，先补齐目录结构再继续。")
        if readiness.get("blocked_objects", 0):
            recommendations.append(f"{side_name} 存在关键对象字段阻塞，导入前需先补主标识字段。")
        if readiness.get("partial_objects", 0):
            recommendations.append(f"{side_name} 有对象仅部分兼容，建议先核对字段别名映射。")
        if readiness.get("empty_objects", 0) == 5:
            recommendations.append(f"{side_name} 当前仍是模板或空资料，适合先拿来核对结构。")

    if not recommendations:
        recommendations.append("两侧资料包当前都具备较好的导入准备度，可直接进入样本导入和字段核对。")

    return {
        "left": left,
        "right": right,
        "counts_delta": counts_delta,
        "decision": {
            "preferred_side": preferred_side,
            "label": preferred_label,
            "left_score": left_score,
            "right_score": right_score,
        },
        "recommendations": recommendations[:12],
        "compatibility_compare": {
            key: {
                "left": left["compatibility"].get(key, {}),
                "right": right["compatibility"].get(key, {}),
            }
            for key in metrics
        },
        "schema_compare": {
            key: _schema_compare(left["schemas"].get(key, []), right["schemas"].get(key, []))
            for key in ["devices", "points", "scenarios", "events", "menus", "metadata", "menu_root_keys"]
        },
    }


def import_control_audit_bundle(db: Session, registration_id: int, bundle_dir: str | Path) -> ControlAuditImportStats:
    registration = db.get(ControlPlatformRegistration, registration_id)
    if not registration:
        raise ValueError("registration_not_found")

    root = Path(bundle_dir)
    if not root.exists():
        raise FileNotFoundError(str(root))

    metadata = _read_json(root / "metadata.json")
    inspection = inspect_control_audit_bundle(root)
    job = _start_job(db, registration, str(root))

    device_count = _import_devices(db, registration, root / "devices.csv", metadata)
    point_count = _import_points(db, registration, root / "points.csv")
    scenario_count = _import_scenarios(db, registration, root / "scenarios.csv")
    event_count = _import_events(db, registration, root / "events.csv")
    menu_count = _import_menus(db, registration, root / "menus.json")

    registration.status = "audited"
    registration.last_audited_at = datetime.utcnow()
    if metadata.get("vendor"):
        registration.vendor = normalize_text(str(metadata["vendor"]))
    if metadata.get("platform_family"):
        registration.platform_family = normalize_text(str(metadata["platform_family"]))
    if metadata.get("base_url") and not registration.base_url:
        registration.base_url = str(metadata["base_url"]).strip()
    if metadata.get("username_hint") and not registration.username_hint:
        registration.username_hint = normalize_text(str(metadata["username_hint"]))

    summary = (
        f"{registration.display_name} 审计导入完成："
        f"设备 {device_count}、点位 {point_count}、场景 {scenario_count}、事件 {event_count}、菜单 {menu_count}，"
        f"资料文件 {inspection['present_files']} 个。"
    )
    _write_snapshot(
        db,
        registration,
        "control_audit_bundle",
        device_count + point_count + scenario_count + event_count + menu_count,
        summary,
    )
    if job is not None:
        _finish_job(db, job, summary)
    db.commit()

    return ControlAuditImportStats(
        registration_id=registration.id,
        display_name=normalize_text(registration.display_name),
        bundle_dir=str(root),
        devices=device_count,
        points=point_count,
        scenarios=scenario_count,
        events=event_count,
        menus=menu_count,
        missing_files=inspection["missing_files"],
        present_files=inspection["present_files"],
    )


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _normalize_row(row: dict) -> dict:
    return {normalize_text(str(key)).strip().lower(): normalize_text(str(value)).strip() for key, value in row.items()}


def _first_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return ""


def _find_control_device(
    db: Session,
    registration_id: int,
    external_key: str,
    display_name: str,
) -> ControlDevice | None:
    if external_key:
        match = db.scalar(
            select(ControlDevice).where(
                ControlDevice.registration_id == registration_id,
                ControlDevice.external_key == external_key,
            )
        )
        if match:
            return match
    if display_name:
        return db.scalar(
            select(ControlDevice).where(
                ControlDevice.registration_id == registration_id,
                ControlDevice.display_name == display_name,
            )
        )
    return None


def _import_devices(db: Session, registration: ControlPlatformRegistration, path: Path, metadata: dict) -> int:
    rows = _read_csv(path)
    vendor_default = normalize_text(str(metadata.get("vendor", "")))
    count = 0

    for raw in rows:
        row = _normalize_row(raw)
        display_name = _first_value(row, "display_name", "name", "device_name", "title")
        external_key = _first_value(row, "external_key", "device_id", "id", "code")
        if not display_name and not external_key:
            continue

        device = _find_control_device(db, registration.id, external_key, display_name)
        if not device:
            device = ControlDevice(
                registration_id=registration.id,
                external_key=external_key or display_name,
                display_name=display_name or external_key,
            )
            db.add(device)
            db.flush()

        device.device_type = _first_value(row, "device_type", "type", "category") or device.device_type or "control_device"
        device.vendor = _first_value(row, "vendor", "brand") or device.vendor or vendor_default or "Unknown"
        device.model = _first_value(row, "model", "device_model") or device.model
        device.area_hint = _first_value(row, "area_hint", "area", "zone", "location") or device.area_hint
        device.control_status = _first_value(row, "control_status", "status", "state") or device.control_status or "unknown"
        device.notes = _first_value(row, "notes", "description", "remark") or device.notes
        count += 1

    return count


def _find_control_device_by_ref(
    db: Session,
    registration_id: int,
    device_ref: str,
) -> ControlDevice | None:
    if not device_ref:
        return None
    return db.scalar(
        select(ControlDevice).where(
            ControlDevice.registration_id == registration_id,
            (ControlDevice.external_key == device_ref) | (ControlDevice.display_name == device_ref),
        )
    )


def _import_points(db: Session, registration: ControlPlatformRegistration, path: Path) -> int:
    rows = _read_csv(path)
    count = 0

    for raw in rows:
        row = _normalize_row(raw)
        point_code = _first_value(row, "point_code", "code", "id")
        display_name = _first_value(row, "display_name", "name", "point_name", "title")
        if not point_code and not display_name:
            continue

        existing = db.scalar(
            select(ControlPoint).where(
                ControlPoint.registration_id == registration.id,
                ControlPoint.point_code == (point_code or display_name),
            )
        )
        if not existing:
            existing = ControlPoint(
                registration_id=registration.id,
                point_code=point_code or display_name,
                display_name=display_name or point_code,
            )
            db.add(existing)
            db.flush()

        device_ref = _first_value(row, "device_ref", "device_id", "device_name", "parent_device")
        linked_device = _find_control_device_by_ref(db, registration.id, device_ref)
        existing.control_device_id = linked_device.id if linked_device else existing.control_device_id
        existing.point_type = _first_value(row, "point_type", "type", "category") or existing.point_type or "point"
        existing.io_direction = _first_value(row, "io_direction", "direction", "io") or existing.io_direction or "unknown"
        existing.point_status = _first_value(row, "point_status", "status", "state") or existing.point_status or "unknown"
        existing.current_value = _first_value(row, "current_value", "value", "current") or existing.current_value
        existing.units = _first_value(row, "units", "unit") or existing.units
        existing.notes = _first_value(row, "notes", "description", "remark") or existing.notes
        count += 1

    return count


def _import_scenarios(db: Session, registration: ControlPlatformRegistration, path: Path) -> int:
    rows = _read_csv(path)
    count = 0

    for raw in rows:
        row = _normalize_row(raw)
        scenario_code = _first_value(row, "scenario_code", "code", "id")
        display_name = _first_value(row, "display_name", "name", "scenario_name", "title")
        if not scenario_code and not display_name:
            continue

        existing = db.scalar(
            select(ControlScenario).where(
                ControlScenario.registration_id == registration.id,
                ControlScenario.scenario_code == (scenario_code or display_name),
            )
        )
        if not existing:
            existing = ControlScenario(
                registration_id=registration.id,
                scenario_code=scenario_code or display_name,
                display_name=display_name or scenario_code,
            )
            db.add(existing)
            db.flush()

        existing.scenario_type = _first_value(row, "scenario_type", "type", "category") or existing.scenario_type or "scenario"
        existing.trigger_mode = _first_value(row, "trigger_mode", "trigger", "mode") or existing.trigger_mode
        existing.area_hint = _first_value(row, "area_hint", "area", "zone", "location") or existing.area_hint
        existing.scenario_status = _first_value(row, "scenario_status", "status", "state") or existing.scenario_status or "unknown"
        existing.notes = _first_value(row, "notes", "description", "remark") or existing.notes
        count += 1

    return count


def _import_events(db: Session, registration: ControlPlatformRegistration, path: Path) -> int:
    rows = _read_csv(path)
    count = 0

    for raw in rows:
        row = _normalize_row(raw)
        event_code = _first_value(row, "event_id", "event_code", "code", "id")
        title = _first_value(row, "title", "event_title", "name")
        if not event_code and not title:
            continue

        existing = db.scalar(
            select(ControlEvent).where(
                ControlEvent.registration_id == registration.id,
                ControlEvent.event_code == (event_code or title),
            )
        )
        if not existing:
            existing = ControlEvent(
                registration_id=registration.id,
                event_code=event_code or title,
                title=title or event_code,
            )
            db.add(existing)
            db.flush()

        device_ref = _first_value(row, "device_ref", "device_id", "device_name", "source_device")
        linked_device = _find_control_device_by_ref(db, registration.id, device_ref)
        existing.control_device_id = linked_device.id if linked_device else existing.control_device_id
        existing.event_type = _first_value(row, "event_type", "type", "category") or existing.event_type or "event"
        existing.severity = _first_value(row, "level", "severity") or existing.severity or "info"
        existing.event_status = _first_value(row, "status", "event_status", "state") or existing.event_status or "open"
        existing.triggered_at = _first_value(row, "triggered_at", "event_time", "time") or existing.triggered_at
        existing.details = _first_value(row, "details", "detail", "description", "remark") or existing.details
        count += 1

    return count


def _import_menus(db: Session, registration: ControlPlatformRegistration, path: Path) -> int:
    payload = _read_json(path)
    menus = payload.get("menus", [])
    if not isinstance(menus, list):
        return 0

    count = 0
    for index, item in enumerate(menus, start=1):
        if not isinstance(item, dict):
            continue
        row = _normalize_row(item)
        menu_key = _first_value(row, "menu_key", "key", "id", "code")
        display_name = _first_value(row, "display_name", "name", "title", "label")
        if not menu_key and not display_name:
            continue

        existing = db.scalar(
            select(ControlMenu).where(
                ControlMenu.registration_id == registration.id,
                ControlMenu.menu_key == (menu_key or display_name),
            )
        )
        if not existing:
            existing = ControlMenu(
                registration_id=registration.id,
                menu_key=menu_key or display_name,
                display_name=display_name or menu_key,
            )
            db.add(existing)
            db.flush()

        existing.parent_menu_key = _first_value(row, "parent_menu_key", "parent", "parent_id") or existing.parent_menu_key
        existing.route_path = _first_value(row, "route_path", "path", "url") or existing.route_path
        existing.page_type = _first_value(row, "page_type", "type", "category") or existing.page_type or "menu"
        sort_text = _first_value(row, "sort_index", "sort", "order")
        if sort_text.isdigit():
            existing.sort_index = int(sort_text)
        else:
            existing.sort_index = existing.sort_index or index
        existing.notes = _first_value(row, "notes", "description", "remark") or existing.notes
        count += 1

    return count


def _start_job(db: Session, registration: ControlPlatformRegistration, bundle_dir: str) -> SyncJob | None:
    source_id = registration.source_id
    if not source_id:
        return None
    job = SyncJob(
        source_id=source_id,
        job_type="control_audit_import",
        status="running",
        started_at=datetime.utcnow(),
        summary=f"开始导入控制平台审计资料：{bundle_dir}",
    )
    db.add(job)
    db.flush()
    return job


def _finish_job(db: Session, job: SyncJob, summary: str) -> None:
    job.status = "completed"
    job.finished_at = datetime.utcnow()
    job.summary = summary
    db.add(job)


def _write_snapshot(
    db: Session,
    registration: ControlPlatformRegistration,
    snapshot_type: str,
    object_count: int,
    notes: str,
) -> None:
    source_id = registration.source_id
    if not source_id:
        return
    snapshot = SyncSnapshot(
        source_id=source_id,
        snapshot_type=snapshot_type,
        object_count=object_count,
        notes=notes,
    )
    db.add(snapshot)

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.asset import AssetDevice, PlatformSource
from app.models.control_domain import ControlDevice, ControlEvent, ControlMenu, ControlPoint, ControlScenario
from app.models.control_platform import ControlPlatformRegistration
from app.models.integration import SourceObjectMapping, SyncJob, SyncSnapshot
from app.schemas.control_platform import (
    ControlPlatformRegistrationOut,
    ControlPlatformRegistrationUpsert,
)
from app.services.control_audit_import import (
    compare_control_audit_bundles,
    control_audit_bundle_template,
    import_control_audit_bundle,
    inspect_control_audit_bundle,
    preview_control_audit_bundle,
)
from app.services.platform_capabilities import control_platform_summary
from app.services.text_normalize import normalize_text


router = APIRouter()


TRACK_TO_SOURCE_TYPE = {
    "electrical_control_platform": "control_platform_electrical",
    "new_control_platform": "control_platform_new",
    "legacy_control_platform": "control_platform_legacy",
}


def _extract_management_ip(base_url: str, fallback: str) -> str:
    if fallback.strip():
        return fallback.strip()
    if not base_url.strip():
        return ""
    try:
        host = urlparse(base_url.strip()).hostname
    except ValueError:
        return fallback.strip()
    return host or fallback.strip()


def _extract_endpoint_path(base_url: str, fallback: str) -> str:
    if fallback.strip():
        return fallback.strip()
    if not base_url.strip():
        return ""
    try:
        parsed = urlparse(base_url.strip())
    except ValueError:
        return fallback.strip()
    path = (parsed.path or "").strip()
    if not path:
        return "/"
    return path


def _default_instance_code(registration: ControlPlatformRegistration) -> str:
    if registration.instance_code.strip():
        return registration.instance_code.strip()
    if registration.management_ip.strip():
        return registration.management_ip.strip()
    if registration.base_url.strip():
        try:
            host = urlparse(registration.base_url.strip()).hostname
        except ValueError:
            host = None
        if host:
            return host
    return registration.track_key


def _default_endpoint_name(registration: ControlPlatformRegistration) -> str:
    if registration.endpoint_name.strip():
        return registration.endpoint_name.strip()
    if registration.endpoint_path.strip() in {"/Web", "/Web/"}:
        return "Web 入口"
    if registration.endpoint_path.strip() in {"/SmartEnergy/roomlist2.jsp"}:
        return "SmartEnergy 入口"
    return "默认入口"


def _default_network_zone(registration: ControlPlatformRegistration) -> str:
    if registration.network_zone.strip():
        return registration.network_zone.strip()
    vlan = registration.vlan_id.strip().lower()
    if vlan == "2":
        return "视频监控域"
    if registration.track_key in {"new_control_platform", "legacy_control_platform", "electrical_control_platform"}:
        return "风控/电控域"
    return "未分类网络域"


def _default_vlan_name(registration: ControlPlatformRegistration) -> str:
    if registration.vlan_name.strip():
        return registration.vlan_name.strip()
    if registration.vlan_id.strip() == "2":
        return "监控 VLAN2"
    if registration.track_key in {"new_control_platform", "legacy_control_platform", "electrical_control_platform"}:
        return "风控/电控待确认 VLAN"
    return "未命名 VLAN"


def _ensure_source_binding(db: Session, registration: ControlPlatformRegistration) -> int | None:
    source_type = TRACK_TO_SOURCE_TYPE.get(registration.track_key)
    if not source_type:
        return None

    source = db.scalar(select(PlatformSource).where(PlatformSource.source_type == source_type))
    if not source:
        source = PlatformSource(
            source_type=source_type,
            name=registration.display_name,
            vendor=registration.vendor or "Unknown",
            base_url=registration.base_url,
            management_ip=registration.management_ip or f"pending-{registration.track_key}",
            version="pending-intake",
            notes=registration.notes,
            sync_status="registered",
        )
        db.add(source)
        db.flush()
    else:
        source.name = registration.display_name
        source.vendor = registration.vendor or source.vendor or "Unknown"
        source.base_url = registration.base_url
        source.management_ip = registration.management_ip or source.management_ip
        source.notes = registration.notes
        source.sync_status = "registered"

    device = db.scalar(
        select(AssetDevice).where(
            AssetDevice.primary_source_type == source_type,
            AssetDevice.device_type == "platform_node",
        )
    )
    if device:
        device.vendor = registration.vendor or device.vendor or "Unknown"
        device.hostname = registration.display_name
        device.management_ip = registration.management_ip or device.management_ip
        device.service_ip = registration.management_ip or device.service_ip
        device.notes = registration.notes

    return source.id


def _to_out(row: ControlPlatformRegistration) -> ControlPlatformRegistrationOut:
    return ControlPlatformRegistrationOut(
        id=row.id,
        track_key=row.track_key,
        instance_name=normalize_text(row.instance_name),
        instance_code=row.instance_code,
        endpoint_name=normalize_text(row.endpoint_name),
        endpoint_path=row.endpoint_path,
        vlan_id=row.vlan_id,
        vlan_name=normalize_text(row.vlan_name),
        network_zone=normalize_text(row.network_zone),
        display_name=normalize_text(row.display_name),
        platform_family=normalize_text(row.platform_family),
        vendor=normalize_text(row.vendor),
        base_url=row.base_url,
        management_ip=row.management_ip,
        username_hint=row.username_hint,
        access_mode=row.access_mode,
        client_required=row.client_required,
        certificate_required=row.certificate_required,
        plugin_required=row.plugin_required,
        read_only_strategy=row.read_only_strategy,
        status=row.status,
        next_action=normalize_text(row.next_action),
        notes=normalize_text(row.notes),
        last_audited_at=row.last_audited_at,
        source_id=row.source_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _activity_for_registration(db: Session, row: ControlPlatformRegistration) -> dict:
    if not row.source_id:
        return {
            "source_id": None,
            "job_count": 0,
            "snapshot_count": 0,
            "latest_job": None,
            "latest_snapshot": None,
        }

    jobs = db.scalars(
        select(SyncJob)
        .where(SyncJob.source_id == row.source_id)
        .order_by(SyncJob.id.desc())
        .limit(6)
    ).all()
    snapshots = db.scalars(
        select(SyncSnapshot)
        .where(SyncSnapshot.source_id == row.source_id)
        .order_by(SyncSnapshot.id.desc())
        .limit(6)
    ).all()

    latest_job = jobs[0] if jobs else None
    latest_snapshot = snapshots[0] if snapshots else None
    return {
        "source_id": row.source_id,
        "job_count": len(jobs),
        "snapshot_count": len(snapshots),
        "latest_job": (
            {
                "id": latest_job.id,
                "job_type": latest_job.job_type,
                "status": latest_job.status,
                "started_at": latest_job.started_at.isoformat() if latest_job.started_at else None,
                "finished_at": latest_job.finished_at.isoformat() if latest_job.finished_at else None,
                "summary": normalize_text(latest_job.summary),
                "error_message": normalize_text(latest_job.error_message),
            }
            if latest_job
            else None
        ),
        "latest_snapshot": (
            {
                "id": latest_snapshot.id,
                "snapshot_type": latest_snapshot.snapshot_type,
                "object_count": latest_snapshot.object_count,
                "captured_at": latest_snapshot.captured_at.isoformat() if latest_snapshot.captured_at else None,
                "notes": normalize_text(latest_snapshot.notes),
            }
            if latest_snapshot
            else None
        ),
        "recent_jobs": [
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "summary": normalize_text(job.summary),
            }
            for job in jobs
        ],
        "recent_snapshots": [
            {
                "id": snapshot.id,
                "snapshot_type": snapshot.snapshot_type,
                "object_count": snapshot.object_count,
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "notes": normalize_text(snapshot.notes),
            }
            for snapshot in snapshots
        ],
    }


def _control_domain_counts(db: Session, registration_id: int) -> dict[str, int]:
    return {
        "devices": db.scalar(
            select(func.count()).select_from(ControlDevice).where(ControlDevice.registration_id == registration_id)
        )
        or 0,
        "points": db.scalar(
            select(func.count()).select_from(ControlPoint).where(ControlPoint.registration_id == registration_id)
        )
        or 0,
        "scenarios": db.scalar(
            select(func.count()).select_from(ControlScenario).where(ControlScenario.registration_id == registration_id)
        )
        or 0,
        "events": db.scalar(
            select(func.count()).select_from(ControlEvent).where(ControlEvent.registration_id == registration_id)
        )
        or 0,
        "menus": db.scalar(
            select(func.count()).select_from(ControlMenu).where(ControlMenu.registration_id == registration_id)
        )
        or 0,
    }


def _export_payload(db: Session, row: ControlPlatformRegistration) -> dict:
    counts = _control_domain_counts(db, row.id)
    activity = _activity_for_registration(db, row)
    return {
        "exported_at": datetime.utcnow().isoformat(),
        "registration": _to_out(row).model_dump(),
        "audit_data_counts": counts,
        "activity": activity,
        "totals": {
            "domain_objects": sum(counts.values()),
            "jobs": activity.get("job_count", 0),
            "snapshots": activity.get("snapshot_count", 0),
        },
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    base = control_platform_summary()
    rows = db.scalars(
        select(ControlPlatformRegistration).order_by(
            ControlPlatformRegistration.track_key,
            ControlPlatformRegistration.updated_at.desc(),
        )
    ).all()
    ready_count = sum(1 for row in rows if row.base_url and row.username_hint)
    audited_count = sum(1 for row in rows if row.last_audited_at is not None)
    vlan_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.vlan_id or "unknown", row.vlan_name or "未命名 VLAN")
        vlan_counts[key] = vlan_counts.get(key, 0) + 1
    base.update(
        {
            "registration_count": len(rows),
            "ready_count": ready_count,
            "audited_count": audited_count,
            "registrations": [_to_out(row).model_dump() for row in rows],
            "instance_count": len({(row.instance_code or row.management_ip or row.track_key) for row in rows}),
            "network_zone_count": len({(row.network_zone or "未分类网络域") for row in rows}),
            "vlan_breakdown": [
                {
                    "vlan_id": vlan_id,
                    "vlan_name": normalize_text(vlan_name),
                    "count": count,
                }
                for (vlan_id, vlan_name), count in sorted(
                    vlan_counts.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ],
        }
    )
    return base


@router.get("/instances")
def list_instances(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(ControlPlatformRegistration).order_by(
            ControlPlatformRegistration.instance_code,
            ControlPlatformRegistration.track_key,
            ControlPlatformRegistration.updated_at.desc(),
        )
    ).all()
    grouped: dict[str, dict] = {}
    for row in rows:
        key = row.instance_code or row.management_ip or row.track_key
        if key not in grouped:
            grouped[key] = {
                "instance_code": key,
                "instance_name": normalize_text(row.instance_name) or normalize_text(row.display_name),
                "management_ip": row.management_ip,
                "network_zone": normalize_text(row.network_zone),
                "vlan_id": row.vlan_id,
                "vlan_name": normalize_text(row.vlan_name),
                "registrations": [],
            }
        grouped[key]["registrations"].append(_to_out(row).model_dump())
    return {
        "instance_count": len(grouped),
        "instances": list(grouped.values()),
    }


@router.get("/registrations", response_model=list[ControlPlatformRegistrationOut])
def list_registrations(db: Session = Depends(get_db)) -> list[ControlPlatformRegistrationOut]:
    rows = db.scalars(
        select(ControlPlatformRegistration).order_by(
            ControlPlatformRegistration.track_key,
            ControlPlatformRegistration.updated_at.desc(),
        )
    ).all()
    return [_to_out(row) for row in rows]


@router.get("/registrations/{registration_id}/activity")
def registration_activity(registration_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        raise HTTPException(status_code=404, detail="registration_not_found")
    return {
        "registration_id": row.id,
        "display_name": normalize_text(row.display_name),
        "track_key": row.track_key,
        "activity": _activity_for_registration(db, row),
    }


@router.get("/registrations/{registration_id}/export")
def export_registration(registration_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        raise HTTPException(status_code=404, detail="registration_not_found")
    return _export_payload(db, row)


@router.get("/audit-template")
def audit_template(track_key: str = "new_control_platform") -> dict:
    return control_audit_bundle_template(track_key)


@router.get("/audit-inspect")
def inspect_audit_bundle(bundle_dir: str) -> dict:
    return inspect_control_audit_bundle(bundle_dir)


@router.get("/audit-preview")
def preview_audit_bundle(bundle_dir: str) -> dict:
    return preview_control_audit_bundle(bundle_dir)


@router.get("/audit-compare")
def compare_audit_bundles(left_bundle_dir: str, right_bundle_dir: str) -> dict:
    return compare_control_audit_bundles(left_bundle_dir, right_bundle_dir)


@router.get("/registrations/{registration_id}/import-plan")
def registration_import_plan(
    registration_id: int,
    bundle_dir: str,
    compare_bundle_dir: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        raise HTTPException(status_code=404, detail="registration_not_found")

    preview = preview_control_audit_bundle(bundle_dir)
    compare = compare_control_audit_bundles(bundle_dir, compare_bundle_dir) if compare_bundle_dir else None

    checklist: list[dict] = []
    checklist.append(
        {
            "step": "检查资料目录是否完整",
            "status": "done" if preview["missing_files"] == 0 else "pending",
            "detail": f"已找到 {preview['present_files']} 个标准文件，缺失 {preview['missing_files']} 个。",
        }
    )
    checklist.append(
        {
            "step": "确认元信息",
            "status": "done" if preview["metadata"].get("platform_family") or preview["metadata"].get("vendor") else "pending",
            "detail": f"平台类型：{preview['metadata'].get('platform_family') or '-'}，厂商：{preview['metadata'].get('vendor') or '-'}。",
        }
    )

    for key, label in {
        "devices": "设备表",
        "points": "点位表",
        "scenarios": "场景表",
        "events": "事件表",
        "menus": "菜单表",
    }.items():
        comp = preview["compatibility"][key]
        checklist.append(
            {
                "step": f"核对{label}关键字段",
                "status": "done" if comp["status"] in {"ready", "mostly_ready"} else ("pending" if comp["status"] == "empty" else "attention"),
                "detail": f"{comp['label']}，缺失组：{', '.join(comp.get('missing_required_groups', [])) or '无'}。",
            }
        )

    if compare:
        checklist.append(
            {
                "step": "核对新老资料包优先级",
                "status": "done",
                "detail": compare["decision"]["label"],
            }
        )

    return {
        "registration_id": row.id,
        "display_name": normalize_text(row.display_name),
        "track_key": row.track_key,
        "bundle_dir": bundle_dir,
        "compare_bundle_dir": compare_bundle_dir,
        "preview": preview,
        "compare": compare,
        "checklist": checklist,
    }


@router.post("/registrations", response_model=ControlPlatformRegistrationOut)
def create_registration(payload: ControlPlatformRegistrationUpsert, db: Session = Depends(get_db)) -> ControlPlatformRegistrationOut:
    conflict = db.scalar(
        select(ControlPlatformRegistration).where(ControlPlatformRegistration.track_key == payload.track_key)
    )
    if conflict:
        raise HTTPException(status_code=409, detail="track_key_exists")

    management_ip = _extract_management_ip(payload.base_url, payload.management_ip)
    payload_data = payload.model_dump(exclude={"management_ip", "endpoint_path", "instance_code"})
    endpoint_path = _extract_endpoint_path(payload.base_url, payload.endpoint_path)
    row = ControlPlatformRegistration(
        **payload_data,
        management_ip=management_ip,
        endpoint_path=endpoint_path,
        instance_code=payload.instance_code.strip() or management_ip,
        last_audited_at=datetime.utcnow() if payload.status == "audited" else None,
    )
    row.instance_name = payload.instance_name.strip() or row.display_name
    row.instance_code = _default_instance_code(row)
    row.vlan_name = _default_vlan_name(row)
    row.endpoint_name = _default_endpoint_name(row)
    row.network_zone = _default_network_zone(row)
    db.add(row)
    db.flush()
    row.source_id = _ensure_source_binding(db, row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/registrations/{registration_id}", response_model=ControlPlatformRegistrationOut)
def update_registration(
    registration_id: int,
    payload: ControlPlatformRegistrationUpsert,
    db: Session = Depends(get_db),
) -> ControlPlatformRegistrationOut:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        raise HTTPException(status_code=404, detail="registration_not_found")

    conflict = db.scalar(
        select(ControlPlatformRegistration).where(
            ControlPlatformRegistration.track_key == payload.track_key,
            ControlPlatformRegistration.id != registration_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="track_key_exists")

    data = payload.model_dump()
    data["management_ip"] = _extract_management_ip(data.get("base_url", ""), data.get("management_ip", ""))
    data["endpoint_path"] = _extract_endpoint_path(data.get("base_url", ""), data.get("endpoint_path", ""))
    for key, value in data.items():
        setattr(row, key, value)
    row.instance_name = payload.instance_name.strip() or row.display_name
    row.instance_code = payload.instance_code.strip() or _default_instance_code(row)
    row.vlan_name = _default_vlan_name(row)
    row.endpoint_name = _default_endpoint_name(row)
    row.network_zone = _default_network_zone(row)

    row.last_audited_at = datetime.utcnow() if row.status == "audited" else row.last_audited_at
    row.source_id = _ensure_source_binding(db, row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/registrations/{registration_id}/audit-data")
def clear_registration_audit_data(registration_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        raise HTTPException(status_code=404, detail="registration_not_found")

    before_counts = _control_domain_counts(db, registration_id)
    device_ids = db.scalars(
        select(ControlDevice.id).where(ControlDevice.registration_id == registration_id)
    ).all()
    mapping_deleted = 0
    if row.source_id:
        mapping_deleted = db.execute(
            delete(SourceObjectMapping).where(SourceObjectMapping.source_id == row.source_id)
        ).rowcount or 0
    jobs_deleted = 0
    snapshots_deleted = 0
    if row.source_id:
        jobs_deleted = db.execute(delete(SyncJob).where(SyncJob.source_id == row.source_id)).rowcount or 0
        snapshots_deleted = db.execute(
            delete(SyncSnapshot).where(SyncSnapshot.source_id == row.source_id)
        ).rowcount or 0

    events_deleted = db.execute(
        delete(ControlEvent).where(ControlEvent.registration_id == registration_id)
    ).rowcount or 0
    points_deleted = db.execute(
        delete(ControlPoint).where(ControlPoint.registration_id == registration_id)
    ).rowcount or 0
    scenarios_deleted = db.execute(
        delete(ControlScenario).where(ControlScenario.registration_id == registration_id)
    ).rowcount or 0
    menus_deleted = db.execute(
        delete(ControlMenu).where(ControlMenu.registration_id == registration_id)
    ).rowcount or 0
    devices_deleted = 0
    if device_ids:
        devices_deleted = db.execute(
            delete(ControlDevice).where(ControlDevice.id.in_(device_ids))
        ).rowcount or 0

    row.last_audited_at = None
    db.commit()

    return {
        "registration_id": registration_id,
        "display_name": normalize_text(row.display_name),
        "deleted": {
            "devices": devices_deleted,
            "points": points_deleted,
            "scenarios": scenarios_deleted,
            "events": events_deleted,
            "menus": menus_deleted,
            "jobs": jobs_deleted,
            "snapshots": snapshots_deleted,
            "source_mappings": mapping_deleted,
        },
        "before_counts": before_counts,
        "remaining_counts": _control_domain_counts(db, registration_id),
    }


@router.post("/import-audit-bundle/{registration_id}")
def import_audit_bundle(
    registration_id: int,
    bundle_dir: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        stats = import_control_audit_bundle(db, registration_id, bundle_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="bundle_not_found")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "registration_id": stats.registration_id,
        "display_name": stats.display_name,
        "bundle_dir": stats.bundle_dir,
        "devices": stats.devices,
        "points": stats.points,
        "scenarios": stats.scenarios,
        "events": stats.events,
        "menus": stats.menus,
        "present_files": stats.present_files,
        "missing_files": stats.missing_files,
    }

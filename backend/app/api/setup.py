from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_import import AUDIT_ROOT
from app.services.audit_import import (
    JVSS_V1_MAIN_XLSX,
    TG_NETWORK_SCAN_CSV,
    _read_v1_jvss_xlsx,
    LEGACY_DB_PATH,
    backfill_tg_port_vlans_from_telnet,
    import_control_platform_placeholder,
    import_hikvision_audit,
    import_jvss_channels,
    import_known_audits,
    import_legacy_alerts,
    import_tg_camera_area_map,
    import_tg_network_scan,
    import_tg_camera_switch_map,
    import_tg_terminal_fallback_map,
)


router = APIRouter()


@router.post("/import-known-audits")
def import_audits(db: Session = Depends(get_db)) -> list[dict]:
    results = import_known_audits(db)
    return [
        {
            "source_name": item.source_name,
            "devices": item.devices,
            "channels": item.channels,
            "ports": item.ports,
            "links": item.links,
            "mappings": item.mappings,
            "alerts": item.alerts,
            "areas": item.areas,
        }
        for item in results
    ]


@router.post("/import-source/{source_key}")
def import_single_source(source_key: str, db: Session = Depends(get_db)) -> dict:
    source_key = source_key.strip().lower()

    if source_key == "jvss-main":
        supplemental_rows = _read_v1_jvss_xlsx(JVSS_V1_MAIN_XLSX) if JVSS_V1_MAIN_XLSX.exists() else None
        stats = import_jvss_channels(
            db,
            "10.0.59.200",
            AUDIT_ROOT / "10.0.59.200-audit" / "extracted_channels.csv",
            supplemental_rows=supplemental_rows,
            audit_dir=AUDIT_ROOT / "10.0.59.200-audit",
        )
    elif source_key == "jvss-stream":
        stats = import_jvss_channels(
            db,
            "10.0.59.205",
            AUDIT_ROOT / "10.0.59.205-audit" / "extracted_channels.csv",
            audit_dir=AUDIT_ROOT / "10.0.59.205-audit",
        )
    elif source_key == "tg-cos":
        stats = import_tg_camera_switch_map(
            db,
            "10.0.68.250",
            AUDIT_ROOT / "10.0.68.250-audit" / "camera_switch_port_map_from_platform.csv",
        )
    elif source_key == "tg-cos-terminal-fallback":
        stats = import_tg_terminal_fallback_map(
            db,
            "10.0.68.250",
            [
                AUDIT_ROOT / "10.0.68.250-audit" / "camera_terminals_from_platform.csv",
                AUDIT_ROOT / "10.0.68.250-audit" / "all_terminals_from_platform.csv",
            ],
        )
    elif source_key == "tg-cos-area":
        stats = import_tg_camera_area_map(
            db,
            "10.0.68.250",
            AUDIT_ROOT / "10.0.68.250-audit" / "camera_area_floor_zone_detail.csv",
        )
    elif source_key == "tg-cos-vlan":
        stats = backfill_tg_port_vlans_from_telnet(
            db,
            "10.0.68.250",
            AUDIT_ROOT / "10.0.68.250-audit" / "telnet-show-bundle.txt",
        )
    elif source_key == "tg-cos-network-scan":
        stats = import_tg_network_scan(
            db,
            "10.0.68.250",
            TG_NETWORK_SCAN_CSV,
        )
    elif source_key == "legacy-alerts":
        stats = import_legacy_alerts(db, LEGACY_DB_PATH)
    elif source_key == "control-platform-new":
        stats = import_control_platform_placeholder(db, "pending-new", track_name="风控电控新平台")
    elif source_key == "control-platform-legacy":
        stats = import_control_platform_placeholder(db, "pending-legacy", track_name="风控电控老平台")
    elif source_key.startswith("hikvision-"):
        target_ip = source_key.replace("hikvision-", "", 1)
        hikvision_root = AUDIT_ROOT / "hikvision-audit-20260409"
        matches = [path for path in hikvision_root.iterdir() if path.is_dir() and path.name.startswith(target_ip)]
        if not matches:
            return {"error": "audit_not_found", "source_key": source_key}
        stats = import_hikvision_audit(db, target_ip, matches[0])
    else:
        return {"error": "unsupported_source", "source_key": source_key}

    return {
        "source_name": stats.source_name,
        "devices": stats.devices,
        "channels": stats.channels,
        "ports": stats.ports,
        "links": stats.links,
        "mappings": stats.mappings,
        "alerts": stats.alerts,
        "areas": stats.areas,
    }

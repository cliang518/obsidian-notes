import csv
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import OpsAlert
from app.models.asset import AssetArea, AssetDevice, NetworkPort, PlatformSource, TopologyLink, VideoChannel
from app.models.integration import SourceObjectMapping, SyncJob, SyncSnapshot
from app.services.text_normalize import normalize_text


ROOT_DIR = Path(__file__).resolve().parents[3]
AUDIT_ROOT = ROOT_DIR.parent / "docs" / "switch-audit"
JVSS_V1_MAIN_XLSX = ROOT_DIR.parent / "all_channels_1.xlsx"
TG_NETWORK_SCAN_CSV = ROOT_DIR.parent / "10.0.68.XX.csv"
LEGACY_DB_PATH = ROOT_DIR.parent / "backend" / "cctv_maintenance.db"
LEGACY_ALERT_FLAP_SECONDS = 180
JVSS_AREA_FALLBACKS = {}
JVSS_CHANNEL_TAIL_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}$")


def _derive_jvss_area_fallback(management_ip: str, camera_ip: str) -> str:
    if management_ip != "10.0.59.205":
        return JVSS_AREA_FALLBACKS.get(management_ip, "")
    if (camera_ip or "").startswith("10.0.59."):
        return "中央大道 / B2 停车场"
    if (camera_ip or "").startswith("10.0.58."):
        return "中央大道 / 商场视频区"
    return "中央大道 / 205分平台"


def _normalize_jvss_direct_area(area_name: str, camera_ip: str) -> tuple[str, str]:
    area_name = normalize_text(area_name or "").strip()
    if " / " not in area_name:
        return area_name, ""
    prefix, tail = area_name.rsplit(" / ", 1)
    tail = tail.strip()
    if JVSS_CHANNEL_TAIL_PATTERN.fullmatch(tail):
        return prefix.strip(), camera_ip or tail
    return area_name, camera_ip or ""


@dataclass(frozen=True)
class ImportStats:
    source_name: str
    devices: int = 0
    channels: int = 0
    ports: int = 0
    links: int = 0
    mappings: int = 0
    alerts: int = 0
    areas: int = 0


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _slug_piece(text: str, *, fallback: str = "unknown", max_len: int = 64) -> str:
    normalized = normalize_text(text or "").strip().lower()
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"[^0-9a-zA-Z\-\u4e00-\u9fff_\.]", "", normalized)
    if not normalized:
        normalized = fallback
    return normalized[:max_len]


def _legacy_dedupe_key(row: sqlite3.Row, device_ip: str, device_name: str) -> str:
    device_marker = _slug_piece(
        device_ip or device_name or (f"id{row['device_id']}" if row["device_id"] else ""),
        fallback="unknown-device",
        max_len=72,
    )
    kind_marker = _slug_piece((row["kind"] or "legacy_alert"), fallback="legacy_alert", max_len=48)
    title_marker = _slug_piece((row["title"] or ""), fallback="untitled", max_len=92)
    key = f"legacy-dk:{device_marker}:{kind_marker}:{title_marker}"
    return key[:250]


def _normalize_legacy_alert_status(
    *,
    status: str,
    triggered_at: datetime | None,
    resolved_at: datetime | None,
) -> tuple[str, str, str]:
    normalized_status = (status or "open").strip().lower() or "open"
    attribution_type = "legacy_bridge"
    note = ""

    if normalized_status == "resolved" and triggered_at and resolved_at:
        duration_seconds = (resolved_at - triggered_at).total_seconds()
        if 0 <= duration_seconds <= LEGACY_ALERT_FLAP_SECONDS:
            normalized_status = "acknowledged"
            attribution_type = "network_flap_watch"
            note = f"flap_short_recovery={int(duration_seconds)}s"

    return normalized_status, attribution_type, note


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_utf16_tsv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-16", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _read_json(path: Path):
    text = path.read_text(encoding="utf-8-sig", errors="ignore").strip()
    if not text:
        return None
    return json.loads(text)


def _read_xlsx_sheet_rows(path: Path) -> list[list[str | None]]:
    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", ns):
                shared_strings.append("".join(node.text or "" for node in si.iterfind(".//a:t", ns)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("p:Relationship", ns)}
        first_sheet = workbook.find("a:sheets", ns)[0]
        rid = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_map[rid]
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = f"xl/{target.lstrip('/')}"

        root = ET.fromstring(archive.read(target))
        rows: list[list[str | None]] = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            values: list[str | None] = []
            for cell in row.findall("a:c", ns):
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    inline_node = cell.find("a:is", ns)
                    values.append(
                        "".join(node.text or "" for node in inline_node.iterfind(".//a:t", ns))
                        if inline_node is not None
                        else None
                    )
                    continue
                value_node = cell.find("a:v", ns)
                if value_node is None:
                    values.append(None)
                    continue
                if cell_type == "s":
                    values.append(shared_strings[int(value_node.text)])
                else:
                    values.append(value_node.text)
            rows.append(values)
        return rows


def _read_v1_jvss_xlsx(path: Path) -> list[dict]:
    rows = _read_xlsx_sheet_rows(path)
    normalized: list[dict] = []
    for raw in rows[1:]:
        if len(raw) < 5:
            continue
        channel_no = (raw[0] or "").strip()
        channel_name = normalize_text((raw[1] or "").strip())
        equipment_ip = (raw[2] or "").strip()
        if not channel_no or not equipment_ip:
            continue
        normalized.append(
            {
                "id": f"v1-xlsx:{channel_no}:{equipment_ip}",
                "channel_num": channel_no,
                "channel_name": channel_name,
                "name": channel_name or equipment_ip,
                "equipment_ip": equipment_ip,
                "rtsp_address": (raw[3] or "").strip(),
                "snapshot": (raw[4] or "").strip(),
                "channel_status": "",
                "rtsp_status": "",
                "is_ptz": "",
                "server_id": "v1-xlsx",
                "_row_origin": "xlsx_supplement",
                "_origin_path": path.name,
            }
        )
    return normalized


def _read_jvss_bulk_channels(path: Path) -> list[dict]:
    payload = _read_json(path) or {}
    normalized: list[dict] = []
    for raw in payload.get("rows", []):
        channel_no = str(raw.get("channel_num") or raw.get("id") or "").strip()
        equipment_ip = str(raw.get("equipment_ip") or "").strip()
        if not channel_no or not equipment_ip:
            continue
        channel_name = normalize_text((raw.get("channel_name") or "").strip())
        direct_name = normalize_text((raw.get("name") or "").strip())
        normalized.append(
            {
                "id": str(raw.get("id") or "").strip() or f"bulk:{channel_no}:{equipment_ip}",
                "channel_num": channel_no,
                "channel_name": channel_name,
                "name": direct_name or channel_name or equipment_ip,
                "equipment_ip": equipment_ip,
                "rtsp_address": str(raw.get("rtsp_address") or "").strip(),
                "snapshot": str(raw.get("snapshot") or "").strip(),
                "channel_status": str(raw.get("channel_status") or "").strip(),
                "rtsp_status": str(raw.get("rtsp_status") or "").strip(),
                "is_ptz": str(raw.get("isPtz") or raw.get("is_ptz") or "").strip(),
                "server_id": normalize_text((raw.get("server_id") or "").strip()),
                "_row_origin": "bulk_channels_all",
                "_origin_path": path.name,
            }
        )
    return normalized


def _read_jvss_primary_rows(csv_path: Path, audit_dir: Path | None = None, *, prefer_bulk: bool = False) -> list[dict]:
    bulk_path = audit_dir / "bulk_channels_all.txt" if audit_dir else None
    if prefer_bulk and bulk_path and bulk_path.exists():
        return _read_jvss_bulk_channels(bulk_path)

    rows = _read_csv(csv_path)
    for row in rows:
        row.setdefault("_row_origin", "extracted_channels_csv")
        row.setdefault("_origin_path", csv_path.name)
    return rows


def _looks_like_generic_cam_name(value: str) -> bool:
    return bool(re.fullmatch(r"cam\d+", (value or "").strip(), flags=re.IGNORECASE))


def _looks_like_ip(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", (value or "").strip()))


def _pick_jvss_display_name(*candidates: str) -> str:
    normalized = [normalize_text(item or "").strip() for item in candidates if normalize_text(item or "").strip()]
    if not normalized:
        return ""
    for item in normalized:
        if not _looks_like_generic_cam_name(item) and not _looks_like_ip(item):
            return item
    for item in normalized:
        if not _looks_like_generic_cam_name(item):
            return item
    return normalized[0]


def _jvss_metadata_key(*, channel_id: str = "", channel_no: str = "", camera_ip: str = "") -> str:
    if channel_id:
        return f"id:{channel_id.strip()}"
    if channel_no:
        return f"ch:{str(channel_no).strip()}"
    if camera_ip:
        return f"ip:{camera_ip.strip()}"
    return ""


def _merge_metadata_entry(store: dict[str, dict], key: str, payload: dict) -> None:
    if not key:
        return
    target = store.setdefault(key, {})
    for field, value in payload.items():
        if value in (None, ""):
            continue
        target[field] = value


def _build_jvss_area_label_map(area_rows: list[dict]) -> dict[str, str]:
    areas_by_id = {
        str(item.get("id") or "").strip(): {
            "name": normalize_text(item.get("name") or "").strip(),
            "parent_id": str(item.get("hid") or "").strip(),
        }
        for item in area_rows
        if str(item.get("id") or "").strip()
    }
    resolved: dict[str, str] = {}

    def resolve(area_id: str) -> str:
        if not area_id or area_id == "999":
            return ""
        if area_id in resolved:
            return resolved[area_id]
        area = areas_by_id.get(area_id)
        if not area:
            resolved[area_id] = ""
            return ""
        label = area["name"]
        parent_id = area["parent_id"]
        if parent_id and parent_id not in {"0", area_id}:
            parent_label = resolve(parent_id)
            if parent_label and parent_label != label:
                label = f"{parent_label} / {label}"
        resolved[area_id] = label
        return label

    for area_id in list(areas_by_id):
        resolve(area_id)
    return resolved


def _load_jvss_audit_metadata(audit_dir: Path | None) -> dict[str, dict]:
    if audit_dir is None or not audit_dir.exists():
        return {}

    metadata_by_key: dict[str, dict] = {}

    bulk_path = audit_dir / "bulk_channels_all.txt"
    if bulk_path.exists():
        payload = _read_json(bulk_path) or {}
        for row in payload.get("rows", []):
            channel_id = str(row.get("id") or "").strip()
            channel_no = str(row.get("channel_num") or "").strip()
            camera_ip = (row.get("equipment_ip") or "").strip()
            direct_name = normalize_text((row.get("name") or "").strip())
            metadata = {
                "direct_name": direct_name,
                "stream_server": normalize_text((row.get("server_id") or "").strip()),
                "thruster": normalize_text((row.get("thruster_id") or "").strip()),
                "live_url": (row.get("liveUrl") or "").strip(),
                "rtsp_status": str(row.get("rtsp_status") or "").strip(),
                "record_status": str(row.get("video_record_status") or "").strip(),
                "platform_status": str(row.get("channel_status") or "").strip(),
                "is_ptz": str(row.get("isPtz") or "").strip(),
            }
            for key in (
                _jvss_metadata_key(channel_id=channel_id),
                _jvss_metadata_key(channel_no=channel_no),
                _jvss_metadata_key(camera_ip=camera_ip),
            ):
                _merge_metadata_entry(metadata_by_key, key, metadata)

    area_path = audit_dir / "crawl_channel_initArea.do.txt"
    if area_path.exists():
        payload = _read_json(area_path) or {}
        area_label_by_id = _build_jvss_area_label_map(payload.get("areas", []))
        for row in payload.get("channels", []):
            area_label = area_label_by_id.get(str(row.get("alarmPointId") or "").strip(), "")
            if not area_label:
                continue
            metadata = {"direct_area": area_label}
            for key in (
                _jvss_metadata_key(channel_id=str(row.get("id") or "").strip()),
                _jvss_metadata_key(channel_no=str(row.get("channel_num") or "").strip()),
                _jvss_metadata_key(camera_ip=(row.get("name") or "").strip()),
            ):
                _merge_metadata_entry(metadata_by_key, key, metadata)

    group_path = audit_dir / "crawl_channel_initGroup.do.txt"
    if group_path.exists():
        payload = _read_json(group_path) or {}
        group_name_by_id = {
            str(item.get("id") or "").strip(): normalize_text(item.get("group_name") or "").strip()
            for item in payload.get("groups", [])
            if str(item.get("id") or "").strip()
        }
        for row in payload.get("channels", []):
            group_label = group_name_by_id.get(str(row.get("group_id") or "").strip(), "")
            if not group_label:
                continue
            metadata = {"direct_group": group_label}
            for key in (
                _jvss_metadata_key(channel_id=str(row.get("id") or "").strip()),
                _jvss_metadata_key(channel_no=str(row.get("channel_num") or "").strip()),
                _jvss_metadata_key(camera_ip=(row.get("name") or "").strip()),
            ):
                _merge_metadata_entry(metadata_by_key, key, metadata)

    return metadata_by_key


def _match_jvss_metadata(store: dict[str, dict], row: dict) -> dict:
    merged: dict = {}
    for key in (
        _jvss_metadata_key(channel_id=str(row.get("id") or "").strip()),
        _jvss_metadata_key(channel_no=str(row.get("channel_num") or "").strip()),
        _jvss_metadata_key(camera_ip=(row.get("equipment_ip") or "").strip()),
    ):
        if key and key in store:
            merged.update(store[key])
    return merged


def _derive_jvss_channel_status(rtsp_status: str, record_status: str, *, has_rtsp: bool, has_snapshot: bool) -> str:
    if rtsp_status == "1":
        return "preview_ready" if has_snapshot else "reachable"
    if rtsp_status == "0":
        if has_rtsp or has_snapshot:
            return "preview_failed"
        return "unreachable"
    if record_status == "0" and has_rtsp:
        return "reachable"
    return "preview_ready" if has_snapshot else ("reachable" if has_rtsp else "unknown")


def _build_jvss_note_payload(management_ip: str, metadata: dict) -> str:
    payload = {
        "source": "jvss",
        "management_ip": management_ip,
        "direct_name": metadata.get("direct_name") or "",
        "direct_area": metadata.get("direct_area") or "",
        "direct_area_raw": metadata.get("direct_area_raw") or "",
        "direct_group": metadata.get("direct_group") or "",
        "direct_point_ip": metadata.get("direct_point_ip") or "",
        "direct_point_label": metadata.get("direct_point_label") or "",
        "stream_server": metadata.get("stream_server") or "",
        "thruster": metadata.get("thruster") or "",
        "live_url": metadata.get("live_url") or "",
        "rtsp_status": metadata.get("rtsp_status") or "",
        "record_status": metadata.get("record_status") or "",
        "platform_status": metadata.get("platform_status") or "",
        "is_ptz": metadata.get("is_ptz") or "",
        "import_origin": metadata.get("import_origin") or "",
        "origin_path": metadata.get("origin_path") or "",
        "source_lineage": metadata.get("source_lineage") or [],
        "supplemental_merged": bool(metadata.get("supplemental_merged")),
    }
    compact = {key: value for key, value in payload.items() if value not in ("", None)}
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def _merge_jvss_rows(primary_rows: list[dict], supplemental_rows: list[dict] | None = None) -> list[dict]:
    if not supplemental_rows:
        return primary_rows

    merged_by_key: dict[str, dict] = {}
    ordered_keys: list[str] = []

    def row_key(row: dict) -> str:
        equipment_ip = (row.get("equipment_ip") or "").strip()
        if equipment_ip:
            return f"ip:{equipment_ip}"
        channel_no = str(row.get("channel_num") or row.get("id") or "").strip()
        return f"ch:{channel_no}"

    def better_display_name(current: str, candidate: str) -> str:
        current = normalize_text(current or "").strip()
        candidate = normalize_text(candidate or "").strip()
        if not candidate:
            return current
        if not current:
            return candidate
        if (_looks_like_ip(current) or _looks_like_generic_cam_name(current)) and not (
            _looks_like_ip(candidate) or _looks_like_generic_cam_name(candidate)
        ):
            return candidate
        if _looks_like_generic_cam_name(current) and not _looks_like_generic_cam_name(candidate):
            return candidate
        if current.count(".") >= 3 and any(ch in candidate for ch in ("（", "(", "已拆", "棚", "门", "围挡", "外挂", "老")):
            return candidate
        return current

    def normalize_lineage(row: dict) -> list[str]:
        lineage = row.get("_source_lineage")
        if isinstance(lineage, list):
            return [str(item).strip() for item in lineage if str(item).strip()]
        if isinstance(lineage, str):
            return [item.strip() for item in lineage.split("|") if item.strip()]
        origin = str(row.get("_row_origin") or "").strip()
        return [origin] if origin else []

    for row in primary_rows:
        key = row_key(row)
        payload = dict(row)
        payload["_source_lineage"] = normalize_lineage(payload)
        ordered_keys.append(key)
        merged_by_key[key] = payload

    for row in supplemental_rows:
        key = row_key(row)
        existing = merged_by_key.get(key)
        if existing is None:
            payload = dict(row)
            payload["_source_lineage"] = normalize_lineage(payload)
            merged_by_key[key] = payload
            ordered_keys.append(key)
            continue

        existing["channel_num"] = existing.get("channel_num") or row.get("channel_num") or row.get("id") or ""
        existing["id"] = existing.get("id") or row.get("id") or f"xlsx-fallback:{existing['channel_num']}"
        existing["equipment_ip"] = existing.get("equipment_ip") or row.get("equipment_ip") or ""
        existing["channel_name"] = better_display_name(existing.get("channel_name", ""), row.get("channel_name", ""))
        existing["name"] = better_display_name(existing.get("name", ""), row.get("name", ""))
        existing["rtsp_address"] = existing.get("rtsp_address") or row.get("rtsp_address") or ""
        existing["snapshot"] = existing.get("snapshot") or row.get("snapshot") or ""
        existing["server_id"] = existing.get("server_id") or row.get("server_id") or ""
        existing["_supplemental_merged"] = True
        lineage = normalize_lineage(existing)
        for item in normalize_lineage(row):
            if item not in lineage:
                lineage.append(item)
        existing["_source_lineage"] = lineage

    return [merged_by_key[key] for key in ordered_keys]


def _normalize_mac(value: str) -> str:
    text = (value or "").strip().lower().replace("-", ":")
    if not text:
        return ""
    if re.match(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", text):
        return text
    compact = re.sub(r"[^0-9a-f]", "", text)
    if len(compact) != 12:
        return ""
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2))


def _parse_telnet_l2_mac_vlan_map(bundle_path: Path) -> dict[str, str]:
    if not bundle_path.exists():
        return {}
    lines = bundle_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    mapping: dict[str, str] = {}
    in_l2_block = False
    prev_nonempty = ""
    for line in lines:
        text = line.strip()
        if text.lower() == "show l2 mac" and prev_nonempty.startswith("Telnet>"):
            in_l2_block = True
            prev_nonempty = text
            continue
        if in_l2_block and text.startswith("Telnet>"):
            break
        if not in_l2_block or not text:
            if text:
                prev_nonempty = text
            continue
        parts = re.split(r"\s+", text)
        if len(parts) < 7:
            prev_nonempty = text
            continue
        mac = _normalize_mac(parts[2])
        vlan = (parts[6] or "").strip()
        if mac and vlan:
            mapping[mac] = vlan
        prev_nonempty = text
    return mapping


def _resolve_vlan_for_camera_row(row: dict, mac_vlan_map: dict[str, str]) -> str:
    vlan_candidates = [
        row.get("vlan"),
        row.get("vlan_id"),
        row.get("vlanid"),
        row.get("port_vlan"),
        row.get("sw_vlan"),
    ]
    for raw in vlan_candidates:
        value = (raw or "").strip()
        if value:
            return value
    camera_mac = _normalize_mac(row.get("mac") or "")
    if camera_mac and camera_mac in mac_vlan_map:
        return mac_vlan_map[camera_mac]
    return ""


def _derive_area_parts(area_tag: str) -> tuple[str, str, str]:
    text = normalize_text(area_tag)
    match = re.match(r"^(?P<floor>\d+F)(?P<zone>.+)$", text)
    if match:
        floor = match.group("floor")
        zone = match.group("zone")
        return floor, zone, text
    return "", text, text


def _get_platform_source(db: Session, management_ip: str) -> PlatformSource | None:
    return db.scalar(select(PlatformSource).where(PlatformSource.management_ip == management_ip))


def _get_device_by_ip(db: Session, ip: str, device_type: str | None = None) -> AssetDevice | None:
    stmt = select(AssetDevice).where(AssetDevice.management_ip == ip)
    if device_type:
        stmt = stmt.where(AssetDevice.device_type == device_type)
    return db.scalar(stmt)


def _ensure_area(db: Session, area_tag: str) -> tuple[AssetArea, bool]:
    display_name = normalize_text(area_tag) or "未命名区域"
    existing = db.scalar(select(AssetArea).where(AssetArea.display_name == display_name))
    created = False
    if existing is None:
        floor, zone, display = _derive_area_parts(display_name)
        existing = AssetArea(
            site="永嘉商场",
            building="主楼",
            floor=floor,
            zone=zone,
            weak_current_room="",
            display_name=display,
        )
        db.add(existing)
        db.flush()
        created = True
    return existing, created


def _ensure_device(
    db: Session,
    *,
    device_type: str,
    vendor: str,
    model: str,
    hostname: str,
    management_ip: str,
    service_ip: str = "",
    serial_number: str = "",
    mac_address: str = "",
    primary_source_type: str = "",
    notes: str = "",
    source_priority: int = 100,
) -> tuple[AssetDevice, bool]:
    existing = _get_device_by_ip(db, management_ip, device_type=device_type)
    created = False
    if existing is None:
        existing = AssetDevice(
            device_type=device_type,
            vendor=normalize_text(vendor),
            model=normalize_text(model),
            hostname=normalize_text(hostname),
            management_ip=management_ip,
            service_ip=service_ip or management_ip,
            mac_address=_normalize_mac(mac_address),
            serial_number=normalize_text(serial_number),
            primary_source_type=primary_source_type,
            notes=normalize_text(notes),
            source_priority=source_priority,
            health_state="discovered",
            device_status="registered",
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        incoming_priority = source_priority if source_priority is not None else 999
        current_priority = existing.source_priority if existing.source_priority is not None else 999
        replace_primary_source = (
            not (existing.primary_source_type or "").strip()
            or (primary_source_type or "").strip() == (existing.primary_source_type or "").strip()
            or incoming_priority <= current_priority
        )
        existing.vendor = normalize_text(vendor) or existing.vendor
        existing.model = normalize_text(model) or existing.model
        existing.hostname = normalize_text(hostname) or existing.hostname
        existing.service_ip = service_ip or existing.service_ip
        existing.mac_address = _normalize_mac(mac_address) or existing.mac_address
        existing.serial_number = normalize_text(serial_number) or existing.serial_number
        if replace_primary_source and primary_source_type:
            existing.primary_source_type = primary_source_type
            existing.source_priority = min(current_priority, incoming_priority)
        elif existing.source_priority is None:
            existing.source_priority = incoming_priority

        normalized_notes = normalize_text(notes)
        if normalized_notes:
            if replace_primary_source or not (existing.notes or "").strip():
                existing.notes = normalized_notes
    return existing, created


def _ensure_port(db: Session, device_id: int, port_name: str) -> tuple[NetworkPort, bool]:
    existing = db.scalar(
        select(NetworkPort).where(NetworkPort.device_id == device_id, NetworkPort.port_name == port_name)
    )
    created = False
    if existing is None:
        existing = NetworkPort(device_id=device_id, port_name=port_name, role_guess="camera_access")
        db.add(existing)
        db.flush()
        created = True
    return existing, created


def _ensure_channel(
    db: Session,
    *,
    parent_device_id: int,
    channel_no: str,
    channel_name: str,
    camera_ip: str,
    protocol_type: str,
    rtsp_main: str = "",
    snapshot_url: str = "",
    record_track_id: str = "",
    camera_asset_id: int | None = None,
    channel_status: str = "",
    notes: str = "",
) -> tuple[VideoChannel, bool]:
    existing = db.scalar(
        select(VideoChannel).where(
            VideoChannel.parent_device_id == parent_device_id,
            VideoChannel.channel_no == str(channel_no),
        )
    )
    created = False
    if existing is None:
        existing = VideoChannel(
            parent_device_id=parent_device_id,
            channel_no=str(channel_no),
            channel_name=normalize_text(channel_name),
            camera_ip=camera_ip,
            protocol_type=protocol_type,
            rtsp_main=rtsp_main,
            snapshot_url=snapshot_url,
            record_track_id=record_track_id,
            camera_asset_id=camera_asset_id,
            channel_status=channel_status or "discovered",
            notes=normalize_text(notes),
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.channel_name = normalize_text(channel_name) or existing.channel_name
        existing.camera_ip = camera_ip or existing.camera_ip
        existing.protocol_type = protocol_type or existing.protocol_type
        existing.rtsp_main = rtsp_main or existing.rtsp_main
        existing.snapshot_url = snapshot_url or existing.snapshot_url
        existing.record_track_id = record_track_id or existing.record_track_id
        existing.camera_asset_id = camera_asset_id or existing.camera_asset_id
        existing.channel_status = channel_status or existing.channel_status
        if notes:
            existing.notes = normalize_text(notes)
    return existing, created


def _append_note(existing_note: str, extra_note: str) -> str:
    current = normalize_text(existing_note or "").strip()
    extra = normalize_text(extra_note or "").strip()
    if not extra:
        return current
    if not current:
        return extra
    if extra in current:
        return current
    return f"{current} | {extra}"


def _ensure_mapping(
    db: Session,
    *,
    source_id: int,
    source_object_type: str,
    source_object_key: str,
    asset_device_id: int | None = None,
    video_channel_id: int | None = None,
    confidence: int = 100,
    notes: str = "",
) -> tuple[SourceObjectMapping, bool]:
    existing = db.scalar(
        select(SourceObjectMapping).where(
            SourceObjectMapping.source_id == source_id,
            SourceObjectMapping.source_object_type == source_object_type,
            SourceObjectMapping.source_object_key == source_object_key,
        )
    )
    created = False
    if existing is None:
        existing = SourceObjectMapping(
            source_id=source_id,
            source_object_type=source_object_type,
            source_object_key=source_object_key,
            asset_device_id=asset_device_id,
            video_channel_id=video_channel_id,
            confidence=confidence,
            notes=notes,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.asset_device_id = asset_device_id or existing.asset_device_id
        existing.video_channel_id = video_channel_id or existing.video_channel_id
        existing.confidence = confidence
        if notes:
            existing.notes = notes
    return existing, created


def _ensure_link(
    db: Session,
    *,
    src_device_id: int | None,
    src_port_id: int | None,
    dst_device_id: int | None,
    dst_port_id: int | None = None,
    link_type: str,
    confidence: float,
    evidence_type: str,
    evidence_summary: str,
) -> tuple[TopologyLink, bool]:
    existing = db.scalar(
        select(TopologyLink).where(
            TopologyLink.src_device_id == src_device_id,
            TopologyLink.src_port_id == src_port_id,
            TopologyLink.dst_device_id == dst_device_id,
            TopologyLink.link_type == link_type,
            TopologyLink.evidence_type == evidence_type,
        )
    )
    created = False
    if existing is None:
        existing = TopologyLink(
            src_device_id=src_device_id,
            src_port_id=src_port_id,
            dst_device_id=dst_device_id,
            dst_port_id=dst_port_id,
            link_type=link_type,
            confidence=confidence,
            evidence_type=evidence_type,
            evidence_summary=evidence_summary,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.confidence = confidence
        existing.evidence_summary = evidence_summary
    return existing, created


def _has_manual_physical_override(db: Session, camera_asset_id: int | None) -> bool:
    if not camera_asset_id:
        return False
    return bool(
        db.scalar(
            select(TopologyLink.id).where(
                TopologyLink.dst_device_id == camera_asset_id,
                TopologyLink.link_type == "physical",
                TopologyLink.evidence_type == "manual_override",
            )
        )
    )


def _ensure_ops_alert(
    db: Session,
    *,
    source_type: str,
    source_event_key: str,
    alert_type: str,
    severity: str,
    status: str,
    title: str,
    message: str,
    asset_device_id: int | None,
    impacted_scope: str,
    attribution_type: str,
    triggered_at,
    last_seen_at,
    resolved_at,
    evidence_summary: str,
) -> tuple[OpsAlert, bool]:
    existing = db.scalar(
        select(OpsAlert).where(
            OpsAlert.source_type == source_type,
            OpsAlert.source_event_key == source_event_key,
        )
    )
    if (
        existing is None
        and source_type == "legacy_ops"
        and source_event_key.startswith("legacy-dk:")
    ):
        parts = source_event_key.split(":")
        if len(parts) >= 4:
            coarse_prefix = ":".join(parts[:3]) + ":"
            stmt = select(OpsAlert).where(
                OpsAlert.source_type == source_type,
                OpsAlert.source_event_key.like(f"{coarse_prefix}%"),
            )
            if asset_device_id is not None:
                stmt = stmt.where(OpsAlert.asset_device_id == asset_device_id)
            existing = db.scalar(stmt.order_by(OpsAlert.last_seen_at.desc(), OpsAlert.id.desc()).limit(1))

    created = False
    if existing is None:
        existing = OpsAlert(
            source_type=source_type,
            source_event_key=source_event_key,
            alert_type=alert_type,
            severity=severity,
            status=status,
            title=title,
            message=normalize_text(message),
            asset_device_id=asset_device_id,
            impacted_scope=impacted_scope,
            attribution_type=attribution_type,
            triggered_at=triggered_at,
            last_seen_at=last_seen_at,
            resolved_at=resolved_at,
            evidence_summary=normalize_text(evidence_summary),
            occurrence_count=1,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        incoming_time = last_seen_at or resolved_at or triggered_at
        if existing.last_seen_at and incoming_time and incoming_time < existing.last_seen_at:
            return existing, created

        previous_status = existing.status
        previous_triggered_at = existing.triggered_at
        previous_last_seen_at = existing.last_seen_at

        # Keep latest refined dedupe key to improve future coalescing.
        if source_type == "legacy_ops" and source_event_key.startswith("legacy-dk:"):
            existing.source_event_key = source_event_key

        existing.alert_type = alert_type
        existing.severity = severity
        existing.status = status
        existing.title = normalize_text(title)
        existing.message = normalize_text(message)
        existing.asset_device_id = asset_device_id or existing.asset_device_id
        existing.impacted_scope = impacted_scope
        existing.attribution_type = attribution_type
        if triggered_at and (existing.triggered_at is None or triggered_at >= existing.triggered_at):
            existing.triggered_at = triggered_at
        if last_seen_at and (existing.last_seen_at is None or last_seen_at >= existing.last_seen_at):
            existing.last_seen_at = last_seen_at
        if status in {"resolved", "acknowledged"}:
            if resolved_at and (existing.resolved_at is None or resolved_at >= existing.resolved_at):
                existing.resolved_at = resolved_at
        else:
            existing.resolved_at = None
        existing.evidence_summary = normalize_text(evidence_summary)

        if status == "open":
            should_increment = False
            if previous_status != "open":
                should_increment = True
            elif (
                triggered_at
                and previous_triggered_at
                and triggered_at > previous_triggered_at
                and (previous_last_seen_at is None or triggered_at >= previous_last_seen_at)
            ):
                should_increment = True
            if should_increment:
                existing.occurrence_count = max(existing.occurrence_count, 1) + 1
        else:
            existing.occurrence_count = max(existing.occurrence_count, 1)
    return existing, created


def _start_job(db: Session, source: PlatformSource, job_type: str) -> SyncJob:
    job = SyncJob(source_id=source.id, job_type=job_type, status="running")
    db.add(job)
    db.flush()
    return job


def _finish_job(db: Session, job: SyncJob, summary: str) -> None:
    job.status = "completed"
    job.summary = summary


def _write_snapshot(db: Session, source: PlatformSource, snapshot_type: str, object_count: int, notes: str) -> None:
    db.add(
        SyncSnapshot(
            source_id=source.id,
            snapshot_type=snapshot_type,
            object_count=object_count,
            notes=notes,
        )
    )


def import_jvss_channels(
    db: Session,
    management_ip: str,
    csv_path: Path,
    supplemental_rows: list[dict] | None = None,
    audit_dir: Path | None = None,
) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    platform_device = _get_device_by_ip(db, management_ip)
    if platform_device is None:
        raise ValueError(f"Missing platform device for {management_ip}")

    rows = _merge_jvss_rows(
        _read_jvss_primary_rows(csv_path, audit_dir, prefer_bulk=(management_ip == "10.0.59.200")),
        supplemental_rows,
    )
    metadata_store = _load_jvss_audit_metadata(audit_dir)
    job = _start_job(db, source, "audit_import_jvss_channels")

    devices = channels = mappings = areas = 0
    for row in rows:
        camera_ip = (row.get("equipment_ip") or "").strip()
        if not camera_ip:
            continue
        metadata = _match_jvss_metadata(metadata_store, row)
        channel_label = _pick_jvss_display_name(
            metadata.get("direct_name", ""),
            (row.get("channel_name") or "").strip(),
            (row.get("name") or "").strip(),
            camera_ip,
        )
        direct_area_raw = normalize_text(metadata.get("direct_area") or "").strip()
        direct_area, direct_point_label = _normalize_jvss_direct_area(direct_area_raw, camera_ip)
        if management_ip == "10.0.59.205":
            direct_area = _derive_jvss_area_fallback(management_ip, camera_ip)
        elif not direct_area:
            direct_area = _derive_jvss_area_fallback(management_ip, camera_ip)
        direct_group = normalize_text(metadata.get("direct_group") or "").strip()
        rtsp_main = (row.get("rtsp_address") or "").strip()
        snapshot_url = (row.get("snapshot") or "").strip()
        effective_metadata = dict(metadata)
        if direct_area:
            effective_metadata["direct_area"] = direct_area
        if direct_area_raw and direct_area_raw != direct_area:
            effective_metadata["direct_area_raw"] = direct_area_raw
        if direct_point_label:
            effective_metadata["direct_point_ip"] = camera_ip
            effective_metadata["direct_point_label"] = camera_ip
        if direct_group:
            effective_metadata["direct_group"] = direct_group
        if not effective_metadata.get("platform_status"):
            effective_metadata["platform_status"] = str(row.get("channel_status") or "").strip()
        if not effective_metadata.get("rtsp_status"):
            effective_metadata["rtsp_status"] = str(row.get("rtsp_status") or "").strip()
        effective_metadata["import_origin"] = str(row.get("_row_origin") or "").strip()
        effective_metadata["origin_path"] = str(row.get("_origin_path") or "").strip()
        effective_metadata["source_lineage"] = row.get("_source_lineage") or []
        effective_metadata["supplemental_merged"] = bool(row.get("_supplemental_merged"))
        note_payload = _build_jvss_note_payload(management_ip, effective_metadata)
        derived_status = _derive_jvss_channel_status(
            str(effective_metadata.get("rtsp_status") or "").strip(),
            str(effective_metadata.get("record_status") or "").strip(),
            has_rtsp=bool(rtsp_main),
            has_snapshot=bool(snapshot_url),
        )
        camera, created = _ensure_device(
            db,
            device_type="camera",
            vendor="unknown",
            model="",
            hostname=channel_label,
            management_ip=camera_ip,
            service_ip=camera_ip,
            serial_number="",
            primary_source_type="jvss",
            notes=note_payload,
            source_priority=70,
        )
        if direct_area:
            area, area_created = _ensure_area(db, direct_area)
            if camera.area_id is None or management_ip == "10.0.59.205":
                camera.area_id = area.id
            if area_created:
                areas += 1
        camera.notes = note_payload
        if direct_group and direct_group != "未分组":
            camera.notes = _build_jvss_note_payload(management_ip, effective_metadata)
        if created:
            devices += 1

        channel, created = _ensure_channel(
            db,
            parent_device_id=platform_device.id,
            channel_no=str(row.get("channel_num") or row.get("id") or ""),
            channel_name=channel_label,
            camera_ip=camera_ip,
            protocol_type="platform_channel",
            rtsp_main=rtsp_main,
            snapshot_url=snapshot_url,
            camera_asset_id=camera.id,
            channel_status=derived_status,
            notes=note_payload,
        )
        if created:
            channels += 1

        for object_type, object_key, asset_id, channel_id, note in [
            ("camera", camera_ip, camera.id, None, "JVSS camera mapping"),
            ("channel", (row.get("id") or "").strip(), None, channel.id, "JVSS channel mapping"),
        ]:
            _, created = _ensure_mapping(
                db,
                source_id=source.id,
                source_object_type=object_type,
                source_object_key=object_key,
                asset_device_id=asset_id,
                video_channel_id=channel_id,
                confidence=90,
                notes=note,
            )
            if created:
                mappings += 1

    source_file = csv_path.name
    if supplemental_rows:
        source_file = f"{csv_path.name} + supplemental"
    metadata_note = source_file if not audit_dir else f"{source_file} + {audit_dir.name}"
    _write_snapshot(db, source, "jvss_channels", len(rows), metadata_note)
    _finish_job(db, job, f"Imported {len(rows)} rows from {metadata_note}")
    db.commit()
    return ImportStats(source_name=source.name, devices=devices, channels=channels, mappings=mappings, areas=areas)


def import_tg_camera_switch_map(db: Session, management_ip: str, csv_path: Path) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    rows = _read_csv(csv_path)
    job = _start_job(db, source, "audit_import_tg_camera_switch_map")
    l2_bundle_path = csv_path.parent / "telnet-show-bundle.txt"
    l2_mac_vlan_map = _parse_telnet_l2_mac_vlan_map(l2_bundle_path)

    devices = ports = links = mappings = areas = 0
    for row in rows:
        camera_ip = (row.get("ipaddr") or "").strip()
        switch_ip = (row.get("sw_ip") or "").strip()
        port_name = (row.get("port") or "").strip()
        if not camera_ip or not switch_ip or not port_name:
            continue

        area, created = _ensure_area(db, row.get("area_tag") or row.get("aliasname") or "未命名区域")
        if created:
            areas += 1

        camera, created = _ensure_device(
            db,
            device_type="camera",
            vendor=(row.get("manufactor") or "unknown").strip(),
            model=normalize_text((row.get("modelname") or "").strip()),
            hostname=normalize_text((row.get("aliasname") or camera_ip).strip()),
            management_ip=camera_ip,
            service_ip=camera_ip,
            mac_address=row.get("mac") or "",
            serial_number="",
            primary_source_type="tg_cos",
            notes="Imported from TG/COS camera-switch map",
            source_priority=90,
        )
        camera.area_id = area.id
        if created:
            devices += 1

        switch, created = _ensure_device(
            db,
            device_type="switch",
            vendor="TG-NET",
            model=normalize_text((row.get("sw_model") or "").strip()),
            hostname=normalize_text((row.get("sw_alias") or switch_ip).strip()),
            management_ip=switch_ip,
            service_ip=switch_ip,
            mac_address=row.get("sw_mac") or "",
            serial_number="",
            primary_source_type="tg_cos",
            notes="Imported from TG/COS camera-switch map",
            source_priority=95,
        )
        if created:
            devices += 1

        port, created = _ensure_port(db, switch.id, port_name)
        if created:
            ports += 1
        inferred_vlan = _resolve_vlan_for_camera_row(row, l2_mac_vlan_map)
        if inferred_vlan:
            port.vlan_id = inferred_vlan
            port.role_guess = "camera_access_monitor" if inferred_vlan == "2" else "camera_access"

        if not _has_manual_physical_override(db, camera.id):
            _, created = _ensure_link(
                db,
                src_device_id=switch.id,
                src_port_id=port.id,
                dst_device_id=camera.id,
                link_type="physical",
                confidence=0.95,
                evidence_type="platform_fact",
                evidence_summary=normalize_text(f"{switch_ip} port {port_name} -> {camera_ip}"),
            )
            if created:
                links += 1

        for object_type, object_key, asset_id, note in [
            ("camera", camera_ip, camera.id, "TG/COS camera mapping"),
            ("switch", switch_ip, switch.id, "TG/COS switch mapping"),
        ]:
            _, created = _ensure_mapping(
                db,
                source_id=source.id,
                source_object_type=object_type,
                source_object_key=object_key,
                asset_device_id=asset_id,
                confidence=95,
                notes=note,
            )
            if created:
                mappings += 1

    _write_snapshot(db, source, "tg_camera_switch_map", len(rows), csv_path.name)
    _finish_job(db, job, f"Imported {len(rows)} rows from {csv_path.name}")
    db.commit()
    return ImportStats(
        source_name=source.name,
        devices=devices,
        ports=ports,
        links=links,
        mappings=mappings,
        areas=areas,
    )


def import_tg_terminal_fallback_map(db: Session, management_ip: str, csv_paths: list[Path]) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    unresolved_camera_ips = {
        row[0]
        for row in db.execute(
            select(VideoChannel.camera_ip)
            .join(AssetDevice, AssetDevice.id == VideoChannel.parent_device_id)
            .outerjoin(
                TopologyLink,
                (TopologyLink.dst_device_id == VideoChannel.camera_asset_id) & (TopologyLink.link_type == "physical"),
            )
            .where(
                AssetDevice.primary_source_type == "jvss",
                TopologyLink.id.is_(None),
                VideoChannel.camera_ip != "",
            )
        ).all()
    }
    if not unresolved_camera_ips:
        return ImportStats(source_name=source.name)

    job = _start_job(db, source, "audit_import_tg_terminal_fallback_map")
    devices = ports = links = mappings = 0
    processed_rows = 0
    processed_ips: set[str] = set()

    for csv_path in csv_paths:
        if not csv_path.exists():
            continue
        for row in _read_csv(csv_path):
            camera_ip = (row.get("ipaddr") or "").strip()
            switch_ip = (row.get("sw_ip") or "").strip()
            port_name = (row.get("port") or "").strip()
            if (
                camera_ip not in unresolved_camera_ips
                or camera_ip in processed_ips
                or not switch_ip
                or switch_ip == "--"
                or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", switch_ip)
                or not port_name
                or port_name in {"0", "--"}
            ):
                continue

            camera, created = _ensure_device(
                db,
                device_type="camera",
                vendor=(row.get("manufactor") or "unknown").strip(),
                model=normalize_text((row.get("modelname") or "").strip()),
                hostname=normalize_text((row.get("aliasname") or camera_ip).strip()),
                management_ip=camera_ip,
                service_ip=camera_ip,
                mac_address=row.get("mac") or "",
                serial_number="",
                primary_source_type="tg_cos",
                notes="Imported from TG/COS terminal fallback map",
                source_priority=88,
            )
            if created:
                devices += 1

            switch, created = _ensure_device(
                db,
                device_type="switch",
                vendor="TG-NET",
                model=normalize_text((row.get("sw_model") or "").strip()),
                hostname=normalize_text((row.get("sw_alias") or switch_ip).strip()),
                management_ip=switch_ip,
                service_ip=switch_ip,
                mac_address=row.get("sw_mac") or "",
                serial_number="",
                primary_source_type="tg_cos",
                notes="Imported from TG/COS terminal fallback map",
                source_priority=95,
            )
            if created:
                devices += 1

            port, created = _ensure_port(db, switch.id, port_name)
            if created:
                ports += 1

            if not _has_manual_physical_override(db, camera.id):
                _, created = _ensure_link(
                    db,
                    src_device_id=switch.id,
                    src_port_id=port.id,
                    dst_device_id=camera.id,
                    link_type="physical",
                    confidence=0.86,
                    evidence_type="platform_terminal_fact",
                    evidence_summary=normalize_text(f"{switch_ip} port {port_name} -> {camera_ip}"),
                )
                if created:
                    links += 1

            _, created = _ensure_mapping(
                db,
                source_id=source.id,
                source_object_type="camera",
                source_object_key=camera_ip,
                asset_device_id=camera.id,
                confidence=88,
                notes="TG/COS terminal fallback camera mapping",
            )
            if created:
                mappings += 1

            processed_rows += 1
            processed_ips.add(camera_ip)

    snapshot_name = ", ".join(path.name for path in csv_paths if path.exists())
    _write_snapshot(db, source, "tg_terminal_fallback_map", processed_rows, snapshot_name)
    _finish_job(db, job, f"Imported {processed_rows} fallback terminal rows from {snapshot_name}")
    db.commit()
    return ImportStats(
        source_name=source.name,
        devices=devices,
        ports=ports,
        links=links,
        mappings=mappings,
    )


def backfill_tg_port_vlans_from_telnet(db: Session, management_ip: str, bundle_path: Path) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    mac_vlan_map = _parse_telnet_l2_mac_vlan_map(bundle_path)
    if not mac_vlan_map:
        return ImportStats(source_name=source.name)

    switch_ids = {
        row.id
        for row in db.scalars(
            select(AssetDevice).where(
                AssetDevice.device_type == "switch",
                AssetDevice.primary_source_type == "tg_cos",
            )
        ).all()
    }
    if not switch_ids:
        return ImportStats(source_name=source.name)

    links = db.scalars(
        select(TopologyLink).where(
            TopologyLink.link_type == "physical",
            TopologyLink.evidence_type == "platform_fact",
            TopologyLink.src_device_id.in_(switch_ids),
            TopologyLink.src_port_id.is_not(None),
            TopologyLink.dst_device_id.is_not(None),
        )
    ).all()
    if not links:
        return ImportStats(source_name=source.name)

    port_ids = {row.src_port_id for row in links if row.src_port_id}
    dst_ids = {row.dst_device_id for row in links if row.dst_device_id}
    ports = {
        row.id: row
        for row in db.scalars(select(NetworkPort).where(NetworkPort.id.in_(port_ids))).all()
    }
    cameras = {
        row.id: row
        for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(dst_ids))).all()
    }

    updated = 0
    for link in links:
        if not link.src_port_id or not link.dst_device_id:
            continue
        port = ports.get(link.src_port_id)
        camera = cameras.get(link.dst_device_id)
        if not port or not camera:
            continue
        mac = _normalize_mac(camera.mac_address)
        if not mac:
            continue
        vlan = mac_vlan_map.get(mac)
        if not vlan:
            continue
        if port.vlan_id != vlan:
            port.vlan_id = vlan
            port.role_guess = "camera_access_monitor" if vlan == "2" else (port.role_guess or "camera_access")
            updated += 1

    if updated:
        _write_snapshot(db, source, "tg_telnet_vlan_backfill", updated, bundle_path.name)
    db.commit()
    return ImportStats(source_name=source.name, ports=updated)


def import_tg_camera_area_map(db: Session, management_ip: str, csv_path: Path) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    rows = _read_csv(csv_path)
    job = _start_job(db, source, "audit_import_tg_camera_area_map")

    areas = 0
    devices = 0
    for row in rows:
        camera_ip = (row.get("ipaddr") or "").strip()
        if not camera_ip:
            continue
        area, created = _ensure_area(db, row.get("area_tag") or row.get("aliasname") or "未命名区域")
        if created:
            areas += 1
        camera = _get_device_by_ip(db, camera_ip)
        if camera is None:
            camera, created = _ensure_device(
                db,
                device_type="camera",
                vendor="unknown",
                model="",
                hostname=normalize_text(row.get("aliasname") or camera_ip),
                management_ip=camera_ip,
                service_ip=camera_ip,
                primary_source_type="tg_cos",
                notes="Imported from TG/COS area map",
                source_priority=80,
            )
            if created:
                devices += 1
        camera.area_id = area.id

    _write_snapshot(db, source, "tg_camera_area_map", len(rows), csv_path.name)
    _finish_job(db, job, f"Imported {len(rows)} rows from {csv_path.name}")
    db.commit()
    return ImportStats(source_name=source.name, devices=devices, areas=areas)


def import_tg_network_scan(db: Session, management_ip: str, csv_path: Path) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    rows = _read_utf16_tsv(csv_path)
    job = _start_job(db, source, "audit_import_tg_network_scan")

    devices = mappings = 0
    for row in rows:
        ip = (row.get("IP") or "").strip()
        if not ip:
            continue

        http_banner = normalize_text((row.get("Http") or "").strip())
        manufacturer = normalize_text((row.get("制造商") or "").strip())
        mac_address = (row.get("MAC 地址") or "").strip()
        remark = normalize_text((row.get("备注") or "").strip())

        if ip == management_ip or "运维平台" in http_banner or "nginx" in http_banner.lower():
            device_type = "platform_node"
            model = "TG/COS"
        else:
            device_type = "switch"
            model = http_banner or "TG-NET network scan"

        existing = _get_device_by_ip(db, ip, device_type=device_type)
        hostname = normalize_text(existing.hostname if existing else ip) or ip

        device, created = _ensure_device(
            db,
            device_type=device_type,
            vendor=manufacturer or "TG-NET",
            model=model,
            hostname=hostname,
            management_ip=ip,
            service_ip=ip,
            mac_address=mac_address,
            primary_source_type="tg_cos",
            notes="Imported from TG/COS network scan",
            source_priority=96,
        )
        if created:
            devices += 1

        scan_note_parts = [
            "TG网络扫描",
            f"HTTP={http_banner}" if http_banner else "",
            f"厂商={manufacturer}" if manufacturer else "",
            f"MAC={_normalize_mac(mac_address)}" if mac_address else "",
            f"备注={remark}" if remark else "",
        ]
        device.notes = _append_note(device.notes, "; ".join([item for item in scan_note_parts if item]))

        _, mapping_created = _ensure_mapping(
            db,
            source_id=source.id,
            source_object_type=device_type,
            source_object_key=ip,
            asset_device_id=device.id,
            confidence=72,
            notes="TG/COS network scan mapping",
        )
        if mapping_created:
            mappings += 1

    _write_snapshot(db, source, "tg_network_scan", len(rows), csv_path.name)
    _finish_job(db, job, f"Imported {len(rows)} rows from {csv_path.name}")
    db.commit()
    return ImportStats(source_name=source.name, devices=devices, mappings=mappings)


def _iter_input_proxy_channels(xml_path: Path) -> Iterable[dict]:
    root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="ignore"))
    for node in root.iter():
        if _localname(node.tag) != "InputProxyChannel":
            continue
        item: dict[str, str] = {}
        source_input = None
        for child in node:
            name = _localname(child.tag)
            if name == "sourceInputPortDescriptor":
                source_input = child
            elif child.text and child.text.strip():
                item[name] = child.text.strip()
        if source_input is not None:
            for child in source_input:
                name = _localname(child.tag)
                if child.text and child.text.strip():
                    item[name] = child.text.strip()
        if item:
            yield item


def _rewrite_hikvision_rtsp_host(raw_url: str, management_ip: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    return re.sub(r"^rtsp://localhost(?=[:/]|$)", f"rtsp://{management_ip}", url, flags=re.IGNORECASE)


def _build_hikvision_snapshot_url(base_url: str, track_channel: str) -> str:
    normalized_base = (base_url or "").strip().rstrip("/")
    normalized_channel = (track_channel or "").strip()
    if not normalized_base or not normalized_channel:
        return ""
    return f"{normalized_base}/ISAPI/Streaming/channels/{normalized_channel}/picture"


def _parse_hikvision_track_map(track_path: Path, management_ip: str, base_url: str) -> dict[str, dict[str, str]]:
    if not track_path.exists():
        return {}

    root = ET.fromstring(track_path.read_text(encoding="utf-8", errors="ignore"))
    track_map: dict[str, dict[str, str]] = {}

    for node in root.iter():
        if _localname(node.tag) != "Track":
            continue

        item: dict[str, str] = {}
        src_descriptor = None
        for child in node:
            name = _localname(child.tag)
            if name == "SrcDescriptor":
                src_descriptor = child
            elif child.text and child.text.strip():
                item[name] = child.text.strip()

        if src_descriptor is not None:
            for child in src_descriptor:
                name = _localname(child.tag)
                if child.text and child.text.strip():
                    item[name] = child.text.strip()

        src_channel = (item.get("SrcChannel") or "").strip()
        track_channel = (item.get("Channel") or item.get("id") or "").strip()
        rtsp_main = _rewrite_hikvision_rtsp_host(item.get("SrcUrl", ""), management_ip)
        if not src_channel or not track_channel:
            continue

        payload = {
            "src_channel": src_channel,
            "track_channel": track_channel,
            "rtsp_main": rtsp_main,
            "snapshot_url": _build_hikvision_snapshot_url(base_url, track_channel),
            "description": normalize_text(item.get("Description", "")),
        }
        track_map[src_channel] = payload
        track_map[track_channel] = payload

    return track_map


def import_hikvision_audit(db: Session, management_ip: str, audit_dir: Path) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    nvr = _get_device_by_ip(db, management_ip)
    if nvr is None:
        raise ValueError(f"Missing device for {management_ip}")

    input_proxy_path = audit_dir / "ISAPI__ContentMgmt__InputProxy__channels.txt"
    if not input_proxy_path.exists():
        return ImportStats(source_name=source.name)
    track_path = audit_dir / "ISAPI__ContentMgmt__record__tracks.txt"

    job = _start_job(db, source, "audit_import_hikvision_channels")

    devices = channels = mappings = 0
    rows = list(_iter_input_proxy_channels(input_proxy_path))
    track_map = _parse_hikvision_track_map(track_path, management_ip, source.base_url)
    for row in rows:
        camera_ip = row.get("ipAddress", "").strip()
        if not camera_ip:
            continue
        camera, created = _ensure_device(
            db,
            device_type="camera",
            vendor="Hikvision" if row.get("proxyProtocol") == "HIKVISION" else "third_party",
            model=normalize_text(row.get("model", "").strip()),
            hostname=normalize_text(row.get("name", "").strip()) or f"Camera {camera_ip}",
            management_ip=camera_ip,
            service_ip=camera_ip,
            serial_number=row.get("serialNumber", "").strip(),
            primary_source_type="hikvision_nvr",
            notes=f"Imported from Hikvision audit {management_ip}",
            source_priority=85,
        )
        if created:
            devices += 1

        track_payload = (
            track_map.get((row.get("id") or "").strip())
            or track_map.get((row.get("srcInputPort") or "").strip())
            or track_map.get((row.get("devIndex") or "").strip())
            or {}
        )
        rtsp_main = (track_payload.get("rtsp_main") or "").strip()
        snapshot_url = (track_payload.get("snapshot_url") or "").strip()
        channel_note_parts = [
            f"Hikvision audit import from {management_ip}",
            normalize_text(track_payload.get("description", "")),
        ]

        channel, created = _ensure_channel(
            db,
            parent_device_id=nvr.id,
            channel_no=row.get("id", ""),
            channel_name=normalize_text(row.get("name", "").strip()) or f"Channel {row.get('id', '')}",
            camera_ip=camera_ip,
            protocol_type=row.get("proxyProtocol", "").strip().lower(),
            rtsp_main=rtsp_main,
            snapshot_url=snapshot_url,
            camera_asset_id=camera.id,
            record_track_id=row.get("devIndex", "").strip(),
            notes=" | ".join(part for part in channel_note_parts if part),
        )
        if created:
            channels += 1

        for object_type, object_key, asset_id, channel_id, note in [
            ("camera", camera_ip, camera.id, None, "Hikvision front camera mapping"),
            ("channel", f"{management_ip}:{row.get('id', '')}", None, channel.id, "Hikvision NVR channel mapping"),
        ]:
            _, created = _ensure_mapping(
                db,
                source_id=source.id,
                source_object_type=object_type,
                source_object_key=object_key,
                asset_device_id=asset_id,
                video_channel_id=channel_id,
                confidence=92,
                notes=note,
            )
            if created:
                mappings += 1

    _write_snapshot(db, source, "hikvision_input_proxy", len(rows), input_proxy_path.name)
    _finish_job(db, job, f"Imported {len(rows)} rows from {input_proxy_path.name}")
    db.commit()
    return ImportStats(source_name=source.name, devices=devices, channels=channels, mappings=mappings)


def import_legacy_alerts(db: Session, db_path: Path = LEGACY_DB_PATH) -> ImportStats:
    source = _get_platform_source(db, "127.0.0.1")
    if source is None:
        raise ValueError("Missing legacy bridge source")
    if not db_path.exists():
        return ImportStats(source_name=source.name)

    job = _start_job(db, source, "legacy_alert_bridge")

    created_alerts = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT
                    a.id,
                    a.device_id,
                    a.kind,
                    a.title,
                    a.message,
                    a.severity,
                    a.status,
                    a.triggered_at,
                    a.resolved_at,
                    d.ip_address,
                    d.name
                FROM alert_events a
                LEFT JOIN devices d ON d.id = a.device_id
                ORDER BY a.id DESC
                LIMIT 1200
            ) latest_alerts
            ORDER BY id ASC
            """
        ).fetchall()

    for row in rows:
        related_device_id = None
        device_ip = (row["ip_address"] or "").strip()
        device_name = (row["name"] or "").strip()
        if device_ip:
            device = db.scalar(select(AssetDevice).where(AssetDevice.management_ip == device_ip))
            if device:
                related_device_id = device.id
        if related_device_id is None and device_name:
            device = db.scalar(select(AssetDevice).where(AssetDevice.hostname == device_name))
            if device:
                related_device_id = device.id

        triggered_at = _parse_dt(row["triggered_at"])
        resolved_at = _parse_dt(row["resolved_at"])
        status, attribution_type, flap_note = _normalize_legacy_alert_status(
            status=(row["status"] or "open").strip().lower(),
            triggered_at=triggered_at,
            resolved_at=resolved_at,
        )
        source_event_key = _legacy_dedupe_key(row, device_ip=device_ip, device_name=device_name)

        evidence = normalize_text(
            f"legacy_event_id={row['id']} device_id={row['device_id']} ip={device_ip or '-'} name={device_name or '-'} dedupe_key={source_event_key}"
        )
        if flap_note:
            evidence = f"{evidence} {flap_note}"

        _, created = _ensure_ops_alert(
            db,
            source_type="legacy_ops",
            source_event_key=source_event_key,
            alert_type=(row["kind"] or "legacy_alert").strip(),
            severity=(row["severity"] or "warning").strip().lower(),
            status=status,
            title=normalize_text((row["title"] or "旧系统告警").strip()),
            message=normalize_text((row["message"] or "").strip()),
            asset_device_id=related_device_id,
            impacted_scope="device",
            attribution_type=attribution_type,
            triggered_at=triggered_at,
            last_seen_at=resolved_at or triggered_at,
            resolved_at=resolved_at,
            evidence_summary=evidence,
        )
        if created:
            created_alerts += 1

    _write_snapshot(db, source, "legacy_alert_bridge", len(rows), db_path.name)
    _finish_job(db, job, f"Imported {len(rows)} legacy alerts from {db_path.name}")
    db.commit()
    return ImportStats(source_name=source.name, alerts=created_alerts)


def import_control_platform_placeholder(db: Session, management_ip: str, *, track_name: str) -> ImportStats:
    source = _get_platform_source(db, management_ip)
    if source is None:
        raise ValueError(f"Unknown source for {management_ip}")

    job = _start_job(db, source, "control_platform_placeholder_intake")
    _write_snapshot(
        db,
        source,
        "control_platform_placeholder",
        0,
        normalize_text(f"{track_name} 已建立占位同步作业，等待明日只读审计接入。"),
    )
    _finish_job(
        db,
        job,
        normalize_text(f"{track_name} 占位导入已执行，当前仅登记接入轨道与待补采字段。"),
    )
    db.commit()
    return ImportStats(source_name=source.name)


def import_known_audits(db: Session) -> list[ImportStats]:
    stats: list[ImportStats] = []

    jvss_main = AUDIT_ROOT / "10.0.59.200-audit" / "extracted_channels.csv"
    jvss_main_audit_dir = AUDIT_ROOT / "10.0.59.200-audit"
    jvss_main_v1_rows = _read_v1_jvss_xlsx(JVSS_V1_MAIN_XLSX) if JVSS_V1_MAIN_XLSX.exists() else None
    if jvss_main.exists():
        stats.append(
            import_jvss_channels(
                db,
                "10.0.59.200",
                jvss_main,
                supplemental_rows=jvss_main_v1_rows,
                audit_dir=jvss_main_audit_dir,
            )
        )

    jvss_stream = AUDIT_ROOT / "10.0.59.205-audit" / "extracted_channels.csv"
    jvss_stream_audit_dir = AUDIT_ROOT / "10.0.59.205-audit"
    if jvss_stream.exists():
        stats.append(import_jvss_channels(db, "10.0.59.205", jvss_stream, audit_dir=jvss_stream_audit_dir))

    tg_map = AUDIT_ROOT / "10.0.68.250-audit" / "camera_switch_port_map_from_platform.csv"
    if tg_map.exists():
        stats.append(import_tg_camera_switch_map(db, "10.0.68.250", tg_map))
    tg_terminal_fallback_paths = [
        AUDIT_ROOT / "10.0.68.250-audit" / "camera_terminals_from_platform.csv",
        AUDIT_ROOT / "10.0.68.250-audit" / "all_terminals_from_platform.csv",
    ]
    if any(path.exists() for path in tg_terminal_fallback_paths):
        stats.append(import_tg_terminal_fallback_map(db, "10.0.68.250", tg_terminal_fallback_paths))
    tg_telnet_bundle = AUDIT_ROOT / "10.0.68.250-audit" / "telnet-show-bundle.txt"
    if tg_telnet_bundle.exists():
        stats.append(backfill_tg_port_vlans_from_telnet(db, "10.0.68.250", tg_telnet_bundle))
    tg_area = AUDIT_ROOT / "10.0.68.250-audit" / "camera_area_floor_zone_detail.csv"
    if tg_area.exists():
        stats.append(import_tg_camera_area_map(db, "10.0.68.250", tg_area))
    if TG_NETWORK_SCAN_CSV.exists():
        stats.append(import_tg_network_scan(db, "10.0.68.250", TG_NETWORK_SCAN_CSV))

    hikvision_root = AUDIT_ROOT / "hikvision-audit-20260409"
    if hikvision_root.exists():
        for management_ip in ["192.168.1.2", "192.168.1.3", "192.168.5.253", "192.168.5.254", "192.168.6.2", "192.168.6.3"]:
            matches = [path for path in hikvision_root.iterdir() if path.is_dir() and path.name.startswith(management_ip)]
            if matches:
                stats.append(import_hikvision_audit(db, management_ip, matches[0]))

    if LEGACY_DB_PATH.exists():
        stats.append(import_legacy_alerts(db, LEGACY_DB_PATH))

    return stats

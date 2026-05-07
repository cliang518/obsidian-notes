import json
import re
import csv
import io
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.asset import AssetArea, AssetDevice, PlatformSource, TopologyLink, VideoChannel
from app.models.integration import SourceObjectMapping, SyncJob, SyncSnapshot
from app.schemas.integrations import IntegrationSourceOut, SyncJobOut, SyncSnapshotOut
from app.services.auth import require_roles
from app.services.text_normalize import normalize_text


router = APIRouter()
ROOT_DIR = Path(__file__).resolve().parents[3]
AUDIT_ROOT = ROOT_DIR.parent / "docs" / "switch-audit"

FUCHENG_RETIRED_PATTERN = re.compile(
    r"(停用|已拆|拆除|未安装|无头|空位|预留|废弃|损坏|维修|围挡|施工|拆机|封闭)"
)
FUCHENG_PLATFORM_MAP = {
    "10.0.59.200": "富成主平台",
    "10.0.59.205": "205 分平台",
}
FUCHENG_CHANNEL_TAIL_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}$")


def _safe_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _load_switch_audit_arp_ips() -> set[str]:
    pattern = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+ether\s+", flags=re.IGNORECASE)
    discovered: set[str] = set()
    for path in AUDIT_ROOT.glob("*-show_arp.txt"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                discovered.add(match.group(1))
    return discovered


@lru_cache(maxsize=1)
def _load_switch_audit_file_index() -> dict[str, set[str]]:
    file_index: dict[str, set[str]] = defaultdict(set)
    patterns = {
        "-login.txt": "login",
        "-show_arp.txt": "arp",
        "-show_mac_address_table.txt": "mac_table",
        "-show_running_config.txt": "running_config",
        "-show_version.txt": "version",
    }
    ip_pattern = re.compile(r"^(10\.0\.68\.\d+)")
    for path in AUDIT_ROOT.glob("10.0.68.*.txt"):
        match = ip_pattern.match(path.name)
        if not match:
            continue
        device_ip = match.group(1)
        for suffix, capability in patterns.items():
            if path.name.endswith(suffix):
                file_index[device_ip].add(capability)
                break
    return dict(file_index)


def _is_valid_ipv4(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", (value or "").strip()))


def _is_valid_camera_ip(value: str) -> bool:
    value = (value or "").strip()
    if not _is_valid_ipv4(value):
        return False
    try:
        octets = [int(part) for part in value.split(".")]
    except ValueError:
        return False
    return all(0 <= item <= 255 for item in octets) and value.startswith("10.0.")


def _camera_segment_and_host(value: str) -> tuple[str, int | None]:
    value = (value or "").strip()
    if not _is_valid_camera_ip(value):
        return "", None
    parts = value.split(".")
    return ".".join(parts[:3]), int(parts[3])


def _area_prefix_and_tail(area: str) -> tuple[str, str]:
    area = normalize_text(area or "").strip()
    if " / " not in area:
        return area, ""
    prefix, tail = area.rsplit(" / ", 1)
    return prefix.strip(), tail.strip()


def _normalize_fucheng_area(area: str) -> tuple[str, str]:
    prefix, tail = _area_prefix_and_tail(area)
    if tail and FUCHENG_CHANNEL_TAIL_PATTERN.fullmatch(tail):
        return prefix, tail
    return normalize_text(area or "").strip(), ""


def _compose_area_from_prefix(prefix: str, segment: str, host: int | None) -> str:
    return normalize_text(prefix or "").strip()


def _camera_tail_from_ip(camera_ip: str) -> str:
    camera_ip = normalize_text(camera_ip or "").strip()
    if not _is_valid_camera_ip(camera_ip):
        return ""
    parts = camera_ip.split(".")
    return f"{parts[2]}.{parts[3]}"


def _camera_host(camera_ip: str) -> int | None:
    camera_ip = normalize_text(camera_ip or "").strip()
    if not _is_valid_camera_ip(camera_ip):
        return None
    try:
        return int(camera_ip.split(".")[-1])
    except ValueError:
        return None


def _compress_int_ranges(values: list[int]) -> list[str]:
    if not values:
        return []
    ordered = sorted(set(values))
    ranges: list[str] = []
    start = ordered[0]
    end = ordered[0]
    for value in ordered[1:]:
        if value == end + 1:
            end = value
            continue
        ranges.append(f"{start}-{end}" if start != end else str(start))
        start = end = value
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ranges


def _get_or_create_area_scope(
    db: Session,
    area_cache: dict[str, AssetArea],
    display_name: str,
    *,
    create: bool = True,
) -> AssetArea | None:
    display_name = normalize_text(display_name or "").strip()
    if not display_name:
        return None
    cached = area_cache.get(display_name)
    if cached:
        return cached
    if not create:
        return None
    parts = [part.strip() for part in display_name.split(" / ") if part.strip()]
    floor = ""
    for part in reversed(parts):
        if "F" in part.upper() or "B" in part.upper():
            floor = part
            break
    area = AssetArea(
        site=parts[0] if parts else display_name,
        building=parts[1] if len(parts) > 1 else "",
        floor=floor,
        zone=parts[-1] if parts else display_name,
        weak_current_room="",
        display_name=display_name,
    )
    db.add(area)
    db.flush()
    area_cache[display_name] = area
    return area


def _build_fucheng_area_scope_normalization(db: Session, *, dry_run: bool = True) -> dict:
    parent_devices = db.scalars(
        select(AssetDevice).where(
            AssetDevice.management_ip.in_(tuple(FUCHENG_PLATFORM_MAP.keys())),
        )
    ).all()
    if not parent_devices:
        return {
            "ok": True,
            "dry_run": dry_run,
            "polluted_channel_total": 0,
            "channel_updates": 0,
            "camera_area_updates": 0,
            "polluted_area_row_total": 0,
            "area_row_updates": 0,
            "area_rows_removed": 0,
            "tail_mismatch_total": 0,
            "sample_channels": [],
            "sample_areas": [],
            "principle": "200 / 205 区域字段只保留区域范围，末尾错尾号不再作为区域的一部分。",
        }

    parent_device_map = {row.id: row for row in parent_devices}
    channels = db.scalars(
        select(VideoChannel).where(VideoChannel.parent_device_id.in_(tuple(parent_device_map.keys())))
    ).all()
    channel_camera_ids = {row.camera_asset_id for row in channels if row.camera_asset_id}
    cameras = {
        row.id: row
        for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(tuple(channel_camera_ids)))).all()
    } if channel_camera_ids else {}

    area_rows = db.scalars(select(AssetArea)).all()
    area_cache = {normalize_text(row.display_name or "").strip(): row for row in area_rows if row.display_name}
    area_by_id = {row.id: row for row in area_rows}

    polluted_channel_total = 0
    channel_updates = 0
    camera_area_updates = 0
    tail_mismatch_total = 0
    sample_channels: list[dict] = []

    for channel in channels:
        notes = _safe_json_dict(channel.notes)
        raw_area = normalize_text(notes.get("direct_area") or "").strip()
        normalized_area, legacy_tail = _normalize_fucheng_area(raw_area)
        if not legacy_tail:
            continue
        polluted_channel_total += 1

        actual_tail = _camera_tail_from_ip(channel.camera_ip)
        if actual_tail and legacy_tail != actual_tail:
            tail_mismatch_total += 1
        if len(sample_channels) < 20:
            sample_channels.append(
                {
                    "channel_id": channel.id,
                    "platform_ip": parent_device_map.get(channel.parent_device_id).management_ip
                    if channel.parent_device_id in parent_device_map
                    else "",
                    "platform_name": FUCHENG_PLATFORM_MAP.get(
                        parent_device_map.get(channel.parent_device_id).management_ip
                        if channel.parent_device_id in parent_device_map
                        else "",
                        "",
                    ),
                    "camera_ip": channel.camera_ip,
                    "channel_name": channel.channel_name,
                    "direct_area_raw": raw_area,
                    "normalized_area": normalized_area,
                    "legacy_tail": legacy_tail,
                    "actual_tail": actual_tail,
                }
            )

        changed = False
        if normalized_area and raw_area != normalized_area:
            notes["direct_area"] = normalized_area
            changed = True
        if raw_area and raw_area != normalized_area:
            notes["direct_area_raw"] = raw_area
        if legacy_tail:
            notes["legacy_channel_tail"] = legacy_tail
        if channel.camera_ip and _is_valid_camera_ip(channel.camera_ip):
            if normalize_text(notes.get("direct_point_ip") or "").strip() != channel.camera_ip:
                notes["direct_point_ip"] = channel.camera_ip
                changed = True
            if normalize_text(notes.get("direct_point_label") or "").strip() != channel.camera_ip:
                notes["direct_point_label"] = channel.camera_ip
                changed = True
        if changed:
            channel_updates += 1
            if not dry_run:
                channel.notes = json.dumps(notes, ensure_ascii=False)

        camera = cameras.get(channel.camera_asset_id or -1)
        canonical_area = (
            _get_or_create_area_scope(db, area_cache, normalized_area, create=not dry_run)
            if normalized_area
            else None
        )
        current_area = area_by_id.get(camera.area_id) if camera and camera.area_id else None
        current_area_name = _normalize_fucheng_area(current_area.display_name)[0] if current_area else ""
        current_area_tail = _normalize_fucheng_area(current_area.display_name)[1] if current_area else ""
        target_area_id = canonical_area.id if canonical_area else None
        if (
            camera
            and normalized_area
            and (camera.area_id is None or current_area_tail or current_area_name == normalized_area)
            and (camera.area_id is None or current_area_tail or (target_area_id is not None and camera.area_id != target_area_id))
        ):
            camera_area_updates += 1
            if not dry_run and canonical_area:
                camera.area_id = canonical_area.id

    polluted_area_rows = []
    area_row_updates = 0
    area_rows_removed = 0
    sample_areas: list[dict] = []
    for area in list(area_by_id.values()):
        normalized_name, legacy_tail = _normalize_fucheng_area(area.display_name)
        if not legacy_tail:
            continue
        polluted_area_rows.append(area)
        canonical_area = (
            _get_or_create_area_scope(db, area_cache, normalized_name, create=not dry_run)
            if normalized_name
            else None
        )
        affected_devices = db.scalars(select(AssetDevice).where(AssetDevice.area_id == area.id)).all()
        if len(sample_areas) < 12:
            sample_areas.append(
                {
                    "polluted_area": area.display_name,
                    "normalized_area": normalized_name,
                    "legacy_tail": legacy_tail,
                    "device_count": len(affected_devices),
                }
            )
        if normalized_name and normalized_name != area.display_name and affected_devices:
            area_row_updates += len(affected_devices)
        if not canonical_area or canonical_area.id == area.id:
            continue
        if affected_devices and not dry_run:
            for device in affected_devices:
                device.area_id = canonical_area.id
        if not dry_run:
            still_bound = db.scalar(select(func.count(AssetDevice.id)).where(AssetDevice.area_id == area.id)) or 0
            if still_bound == 0:
                db.delete(area)
                area_rows_removed += 1

    if not dry_run:
        for area in db.scalars(select(AssetArea)).all():
            _, legacy_tail = _normalize_fucheng_area(area.display_name)
            if not legacy_tail:
                continue
            still_bound = db.scalar(select(func.count(AssetDevice.id)).where(AssetDevice.area_id == area.id)) or 0
            if still_bound == 0:
                db.delete(area)
                area_rows_removed += 1
        db.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "polluted_channel_total": polluted_channel_total,
        "channel_updates": channel_updates,
        "camera_area_updates": camera_area_updates,
        "polluted_area_row_total": len(polluted_area_rows),
        "area_row_updates": area_row_updates,
        "area_rows_removed": area_rows_removed,
        "tail_mismatch_total": tail_mismatch_total,
        "sample_channels": sample_channels,
        "sample_areas": sample_areas,
        "principle": "200 / 205 区域字段只保留区域范围，末尾错尾号改为历史痕迹，真实摄像头以 camera_ip 为准。",
    }


def _build_tg_camera_fact_set(db: Session) -> set[str]:
    ips = {
        row[0]
        for row in db.execute(
            select(SourceObjectMapping.source_object_key)
            .join(PlatformSource, PlatformSource.id == SourceObjectMapping.source_id)
            .where(
                PlatformSource.management_ip == "10.0.68.250",
                SourceObjectMapping.source_object_type == "camera",
            )
        ).all()
        if row[0]
    }
    ips.update(
        row[0]
        for row in db.execute(
            select(AssetDevice.management_ip).where(
                AssetDevice.primary_source_type == "tg_cos",
                AssetDevice.device_type == "camera",
                AssetDevice.management_ip != "",
            )
        ).all()
        if row[0]
    )
    return ips


def _get_physical_camera_ids(db: Session) -> set[int]:
    return {
        row[0]
        for row in db.execute(
            select(TopologyLink.dst_device_id).where(
                TopologyLink.link_type == "physical",
                TopologyLink.dst_device_id.is_not(None),
            )
        ).all()
        if row[0]
    }


def _build_runtime_stats_for_source(
    db: Session,
    source: PlatformSource,
    *,
    physical_camera_ids: set[int],
) -> dict:
    parent_device = db.scalar(select(AssetDevice).where(AssetDevice.management_ip == source.management_ip))
    if parent_device is None:
        device_total = db.scalar(
            select(func.count(AssetDevice.id)).where(AssetDevice.platform_source_id == source.id)
        ) or 0
        return {
            "device_total": int(device_total),
            "channel_total": 0,
            "preview_ready": 0,
            "preview_failed": 0,
            "reachable": 0,
            "rtsp_ready": 0,
            "legacy_snapshot_ready": 0,
            "switch_bound": 0,
            "area_ready": 0,
        }

    channels = db.scalars(
        select(VideoChannel)
        .where(VideoChannel.parent_device_id == parent_device.id)
        .order_by(VideoChannel.id.asc())
    ).all()
    channel_total = len(channels)
    camera_ids = {row.camera_asset_id for row in channels if row.camera_asset_id}
    return {
        "device_total": len(camera_ids),
        "channel_total": channel_total,
        "preview_ready": sum(1 for row in channels if row.channel_status == "preview_ready"),
        "preview_failed": sum(1 for row in channels if row.channel_status == "preview_failed"),
        "reachable": sum(1 for row in channels if row.channel_status == "reachable"),
        "rtsp_ready": sum(1 for row in channels if (row.rtsp_main or "").strip()),
        "legacy_snapshot_ready": sum(1 for row in channels if (row.snapshot_url or "").strip()),
        "switch_bound": sum(
            1 for row in channels if row.camera_asset_id and row.camera_asset_id in physical_camera_ids
        ),
        "area_ready": sum(
            1
            for row in channels
            if normalize_text(_safe_json_dict(row.notes).get("direct_area") or "").strip()
        ),
    }


def _compact_counter(counter: Counter, top_n: int = 6) -> list[dict]:
    return [{"name": key, "count": value} for key, value in counter.most_common(top_n)]


def _build_next_actions(management_ip: str, reason_counter: Counter, area_counter: Counter, segment_counter: Counter) -> list[str]:
    actions: list[str] = []
    top_areas = [item for item, _ in area_counter.most_common(3) if item]
    top_segments = [item for item, _ in segment_counter.most_common(3) if item]

    if reason_counter.get("tg_fact_gap"):
        actions.append("富成主平台缺口当前不在 TG 平台导出和已采交换机审计里，下一步应补采对应楼层交换机的 ARP、MAC 表和配置。")
    if reason_counter.get("sub205_fact_gap"):
        actions.append("205 分平台缺口当前不在现有平台事实里，下一步应优先补采对应区域交换机审计或新增 205 平台导出。")
    if reason_counter.get("retired_or_special"):
        actions.append("含停用、拆除、未安装对象，建议先现场核实后再决定是否继续纳入补链。")
    if top_areas:
        actions.append(f"优先关注区域：{'、'.join(top_areas)}。")
    if top_segments:
        actions.append(f"重点 IP 段：{'、'.join(top_segments)}。")
    if not actions:
        actions.append("当前未发现额外采集建议，可继续扩充交换机审计覆盖范围。")
    return actions


def _camera_segment(camera_ip: str) -> str:
    parts = (camera_ip or "").split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else ""


def _camera_host_octet(camera_ip: str) -> int | None:
    parts = (camera_ip or "").split(".")
    if len(parts) != 4:
        return None
    try:
        return int(parts[3])
    except ValueError:
        return None


def _build_bound_switch_candidates(channels: list[VideoChannel], db: Session) -> tuple[dict[int, list[dict]], dict[str, list[dict]]]:
    camera_ids = {row.camera_asset_id for row in channels if row.camera_asset_id}
    if not camera_ids:
        return {}, {}

    links = db.scalars(
        select(TopologyLink)
        .where(
            TopologyLink.link_type == "physical",
            TopologyLink.dst_device_id.in_(camera_ids),
            TopologyLink.src_device_id.is_not(None),
        )
        .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
    ).all()
    link_by_camera: dict[int, TopologyLink] = {}
    switch_ids = set()
    for link in links:
        if not link.dst_device_id or link.dst_device_id in link_by_camera:
            continue
        link_by_camera[link.dst_device_id] = link
        if link.src_device_id:
            switch_ids.add(link.src_device_id)

    switch_map = (
        {
            row.id: row
            for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(switch_ids))).all()
        }
        if switch_ids
        else {}
    )

    candidates_by_area: dict[str, list[dict]] = defaultdict(list)
    candidates_by_segment: dict[str, list[dict]] = defaultdict(list)
    for row in channels:
        if not row.camera_asset_id or row.camera_asset_id not in link_by_camera:
            continue
        notes = _safe_json_dict(row.notes)
        direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
        segment = _camera_segment(row.camera_ip or "")
        host_octet = _camera_host_octet(row.camera_ip or "")
        link = link_by_camera[row.camera_asset_id]
        switch = switch_map.get(link.src_device_id)
        if switch is None:
            continue
        item = {
            "switch_ip": switch.management_ip,
            "switch_name": normalize_text(switch.hostname or switch.management_ip),
            "camera_ip": row.camera_ip,
            "channel_id": row.id,
            "area": direct_area,
            "segment": segment,
            "host_octet": host_octet,
        }
        if direct_area:
            candidates_by_area[direct_area].append(item)
        if segment:
            candidates_by_segment[segment].append(item)
    return dict(candidates_by_area), dict(candidates_by_segment)


def _recommend_switches_for_channel(
    row: VideoChannel,
    notes: dict,
    *,
    candidates_by_area: dict[str, list[dict]],
    candidates_by_segment: dict[str, list[dict]],
) -> list[dict]:
    direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
    segment = _camera_segment(row.camera_ip or "")
    host_octet = _camera_host_octet(row.camera_ip or "")

    scored: dict[str, dict] = {}

    def add_candidate(candidate: dict, base_score: int, reason: str) -> None:
        switch_ip = candidate.get("switch_ip") or ""
        if not switch_ip:
            return
        delta = None
        candidate_octet = candidate.get("host_octet")
        if host_octet is not None and isinstance(candidate_octet, int):
            delta = abs(host_octet - candidate_octet)
        score = base_score
        if delta is not None:
            score += max(0, 40 - min(delta, 40))
        existing = scored.get(switch_ip)
        payload = {
            "switch_ip": switch_ip,
            "switch_name": candidate.get("switch_name") or switch_ip,
            "score": score,
            "reason": reason,
            "sample_camera_ip": candidate.get("camera_ip") or "",
            "sample_channel_id": candidate.get("channel_id"),
            "distance": delta,
        }
        if existing is None or payload["score"] > existing["score"]:
            scored[switch_ip] = payload

    if direct_area and direct_area in candidates_by_area:
        for candidate in candidates_by_area[direct_area]:
            add_candidate(candidate, 100, "同区域已归属摄像头")
    if segment and segment in candidates_by_segment:
        for candidate in candidates_by_segment[segment]:
            add_candidate(candidate, 60, "同网段已归属摄像头")

    ranked = sorted(
        scored.values(),
        key=lambda item: (
            -item["score"],
            item["distance"] if item["distance"] is not None else 9999,
            item["switch_ip"],
        ),
    )
    return ranked[:3]


def _classify_fucheng_unbound(
    channel: VideoChannel,
    management_ip: str,
    *,
    tg_camera_fact_ips: set[str],
    switch_audit_arp_ips: set[str],
) -> tuple[str, str, dict]:
    notes = _safe_json_dict(channel.notes)
    text_parts = [
        normalize_text(channel.channel_name or ""),
        normalize_text(notes.get("direct_name") or ""),
        normalize_text(notes.get("direct_area") or ""),
        normalize_text(notes.get("direct_group") or ""),
    ]
    merged_text = " ".join(part for part in text_parts if part)
    camera_ip = (channel.camera_ip or "").strip()
    in_tg_platform_export = camera_ip in tg_camera_fact_ips
    in_switch_audit_arp = camera_ip in switch_audit_arp_ips
    notes["_in_tg_platform_export"] = in_tg_platform_export
    notes["_in_switch_audit_arp"] = in_switch_audit_arp

    if FUCHENG_RETIRED_PATTERN.search(merged_text):
        return "retired_or_special", "停用/拆除/未安装", notes
    if not in_tg_platform_export and not in_switch_audit_arp:
        if management_ip == "10.0.59.205":
            return "sub205_fact_gap", "205分平台待补平台/交换机事实", notes
        return "tg_fact_gap", "现有 TG 平台与交换机事实均未覆盖", notes
    if management_ip == "10.0.59.205":
        return "sub205_pending_topology", "205分平台待补拓扑", notes
    return "tg_topology_gap", "待补 250 拓扑归属", notes


def _build_fucheng_data_quality(db: Session, sample_limit: int | None = 80) -> dict:
    parent_devices = {
        management_ip: db.scalar(select(AssetDevice).where(AssetDevice.management_ip == management_ip))
        for management_ip in FUCHENG_PLATFORM_MAP
    }
    channel_rows: list[tuple[str, str, VideoChannel]] = []
    for management_ip, parent_device in parent_devices.items():
        if not parent_device:
            continue
        rows = db.scalars(
            select(VideoChannel)
            .where(VideoChannel.parent_device_id == parent_device.id)
            .order_by(VideoChannel.id.asc())
        ).all()
        channel_rows.extend((management_ip, FUCHENG_PLATFORM_MAP[management_ip], row) for row in rows)

    camera_ids = {row.camera_asset_id for _, _, row in channel_rows if row.camera_asset_id}
    camera_by_id = {
        row.id: row
        for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(camera_ids))).all()
    } if camera_ids else {}
    physical_camera_ids = _get_physical_camera_ids(db)

    issue_counter: Counter = Counter()
    platform_issue_counter: dict[str, Counter] = defaultdict(Counter)
    sample_issues: list[dict] = []
    duplicate_ip_bucket: dict[str, list[tuple[str, VideoChannel]]] = defaultdict(list)
    duplicate_channel_key_bucket: dict[tuple[int, str], list[tuple[str, VideoChannel]]] = defaultdict(list)
    issue_channel_ids: set[int] = set()

    issue_labels = {
        "invalid_camera_ip": "摄像头 IP 异常",
        "missing_rtsp": "RTSP 地址缺失",
        "missing_camera_asset": "未绑定摄像头资产",
        "camera_asset_archived": "绑定资产已归档",
        "camera_asset_type_mismatch": "绑定资产类型异常",
        "camera_asset_ip_mismatch": "绑定资产 IP 不一致",
        "missing_area": "区域信息缺失",
        "missing_topology": "未归属交换机链路",
        "preview_not_ready": "预览状态未就绪",
        "retired_or_special": "疑似停用/拆除待归档",
        "duplicate_camera_ip": "摄像头 IP 重复",
        "duplicate_channel_no": "同平台通道号重复",
    }

    def add_issue(code: str, management_ip: str, platform_name: str, channel: VideoChannel, detail: str = "") -> None:
        issue_counter[code] += 1
        platform_issue_counter[management_ip][code] += 1
        issue_channel_ids.add(channel.id)
        if sample_limit is not None and len(sample_issues) >= sample_limit:
            return
        notes = _safe_json_dict(channel.notes)
        sample_issues.append(
            {
                "issue_code": code,
                "issue_label": issue_labels.get(code, code),
                "detail": detail,
                "platform_ip": management_ip,
                "platform_name": platform_name,
                "channel_id": channel.id,
                "channel_no": channel.channel_no,
                "channel_name": normalize_text(channel.channel_name),
                "camera_ip": channel.camera_ip or "",
                "channel_status": channel.channel_status or "",
                "direct_area": _normalize_fucheng_area(notes.get("direct_area") or "")[0],
                "rtsp_ready": bool((channel.rtsp_main or "").strip()),
            }
        )

    for management_ip, platform_name, channel in channel_rows:
        camera_ip = (channel.camera_ip or "").strip()
        notes = _safe_json_dict(channel.notes)
        direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
        merged_text = " ".join(
            item
            for item in [
                normalize_text(channel.channel_name or ""),
                normalize_text(notes.get("direct_name") or ""),
                _normalize_fucheng_area(notes.get("direct_area") or "")[0],
                normalize_text(notes.get("direct_group") or ""),
            ]
            if item
        )
        retired_or_special = bool(FUCHENG_RETIRED_PATTERN.search(merged_text))
        if camera_ip:
            duplicate_ip_bucket[camera_ip].append((management_ip, channel))
        duplicate_channel_key_bucket[(channel.parent_device_id, channel.channel_no or "")].append((management_ip, channel))

        if not _is_valid_camera_ip(camera_ip):
            add_issue("invalid_camera_ip", management_ip, platform_name, channel)
        if retired_or_special:
            add_issue("retired_or_special", management_ip, platform_name, channel, "该通道疑似历史废点，建议现场确认后归档")
            continue
        if not (channel.rtsp_main or "").strip():
            add_issue("missing_rtsp", management_ip, platform_name, channel)
        if channel.channel_status != "preview_ready":
            add_issue("preview_not_ready", management_ip, platform_name, channel)
        if not channel.camera_asset_id:
            add_issue("missing_camera_asset", management_ip, platform_name, channel)
        else:
            camera_asset = camera_by_id.get(channel.camera_asset_id)
            if camera_asset is None:
                add_issue("missing_camera_asset", management_ip, platform_name, channel, "绑定的资产记录不存在")
            else:
                if camera_asset.device_status == "archived":
                    add_issue("camera_asset_archived", management_ip, platform_name, channel)
                if camera_asset.device_type != "camera":
                    add_issue(
                        "camera_asset_type_mismatch",
                        management_ip,
                        platform_name,
                        channel,
                        f"资产类型为 {camera_asset.device_type or '-'}",
                    )
                if camera_ip and camera_asset.management_ip and camera_ip != camera_asset.management_ip:
                    add_issue(
                        "camera_asset_ip_mismatch",
                        management_ip,
                        platform_name,
                        channel,
                        f"资产 IP 为 {camera_asset.management_ip}",
                    )
        if not direct_area:
            add_issue("missing_area", management_ip, platform_name, channel)
        if not channel.camera_asset_id or channel.camera_asset_id not in physical_camera_ids:
            add_issue("missing_topology", management_ip, platform_name, channel)

    duplicate_camera_ips = []
    for camera_ip, rows in duplicate_ip_bucket.items():
        if camera_ip and len(rows) > 1:
            issue_counter["duplicate_camera_ip"] += len(rows)
            for management_ip, channel in rows:
                platform_issue_counter[management_ip]["duplicate_camera_ip"] += 1
                issue_channel_ids.add(channel.id)
            duplicate_camera_ips.append(
                {
                    "camera_ip": camera_ip,
                    "count": len(rows),
                    "platforms": sorted({management_ip for management_ip, _ in rows}),
                    "channels": [
                        {
                            "platform_ip": management_ip,
                            "channel_id": channel.id,
                            "channel_no": channel.channel_no,
                            "channel_name": normalize_text(channel.channel_name),
                        }
                        for management_ip, channel in rows[:8]
                    ],
                }
            )
    duplicate_channel_keys = []
    for (parent_device_id, channel_no), rows in duplicate_channel_key_bucket.items():
        if channel_no and len(rows) > 1:
            issue_counter["duplicate_channel_no"] += len(rows)
            for management_ip, channel in rows:
                platform_issue_counter[management_ip]["duplicate_channel_no"] += 1
                issue_channel_ids.add(channel.id)
            duplicate_channel_keys.append(
                {
                    "parent_device_id": parent_device_id,
                    "channel_no": channel_no,
                    "count": len(rows),
                    "channels": [
                        {
                            "platform_ip": management_ip,
                            "channel_id": channel.id,
                            "camera_ip": channel.camera_ip or "",
                            "channel_name": normalize_text(channel.channel_name),
                        }
                        for management_ip, channel in rows[:8]
                    ],
                }
            )

    platform_cards = []
    for management_ip, platform_name in FUCHENG_PLATFORM_MAP.items():
        rows = [row for row_management_ip, _, row in channel_rows if row_management_ip == management_ip]
        issue_total = sum(platform_issue_counter[management_ip].values())
        platform_cards.append(
            {
                "management_ip": management_ip,
                "platform_name": platform_name,
                "channel_total": len(rows),
                "preview_ready": sum(1 for row in rows if row.channel_status == "preview_ready"),
                "rtsp_ready": sum(1 for row in rows if (row.rtsp_main or "").strip()),
                "asset_bound": sum(1 for row in rows if row.camera_asset_id),
                "topology_bound": sum(
                    1 for row in rows if row.camera_asset_id and row.camera_asset_id in physical_camera_ids
                ),
                "area_ready": sum(
                    1 for row in rows if normalize_text(_safe_json_dict(row.notes).get("direct_area") or "").strip()
                ),
                "issue_total": issue_total,
                "top_issues": [
                    {"code": code, "label": issue_labels.get(code, code), "count": count}
                    for code, count in platform_issue_counter[management_ip].most_common(6)
                ],
            }
        )

    channel_total = len(channel_rows)
    clean_channel_ids = {channel.id for _, _, channel in channel_rows} - issue_channel_ids
    readiness_score = round((len(clean_channel_ids) / channel_total) * 100, 1) if channel_total else 0
    metrics = [
        {"key": "channel_total", "label": "富成通道总数", "count": channel_total, "severity": "info"},
        {
            "key": "retired_or_special",
            "label": "待归档特殊点",
            "count": issue_counter["retired_or_special"],
            "severity": "info",
        },
        {"key": "missing_rtsp", "label": "RTSP缺失", "count": issue_counter["missing_rtsp"], "severity": "danger"},
        {
            "key": "missing_camera_asset",
            "label": "资产未绑定",
            "count": issue_counter["missing_camera_asset"],
            "severity": "danger",
        },
        {"key": "missing_topology", "label": "拓扑未归属", "count": issue_counter["missing_topology"], "severity": "warning"},
        {"key": "missing_area", "label": "区域缺失", "count": issue_counter["missing_area"], "severity": "warning"},
        {
            "key": "duplicate_camera_ip",
            "label": "重复IP命中",
            "count": issue_counter["duplicate_camera_ip"],
            "severity": "warning",
        },
        {
            "key": "preview_not_ready",
            "label": "预览未就绪",
            "count": issue_counter["preview_not_ready"],
            "severity": "warning",
        },
    ]
    return {
        "channel_total": channel_total,
        "readiness_score": readiness_score,
        "issue_total": sum(issue_counter.values()),
        "metrics": metrics,
        "platforms": platform_cards,
        "sample_issues": sample_issues,
        "duplicate_camera_ips": sorted(duplicate_camera_ips, key=lambda item: item["count"], reverse=True)[:40],
        "duplicate_channel_keys": sorted(duplicate_channel_keys, key=lambda item: item["count"], reverse=True)[:40],
        "issue_breakdown": [
            {"code": code, "label": issue_labels.get(code, code), "count": count}
            for code, count in issue_counter.most_common()
        ],
        "principle": "只读核验 10.0.59.200 / 10.0.59.205 的落地质量，不回写第三方平台。",
    }


def _load_fucheng_channels(db: Session) -> list[tuple[str, str, VideoChannel]]:
    channel_rows: list[tuple[str, str, VideoChannel]] = []
    for management_ip, platform_name in FUCHENG_PLATFORM_MAP.items():
        parent_device = db.scalar(select(AssetDevice).where(AssetDevice.management_ip == management_ip))
        if not parent_device:
            continue
        rows = db.scalars(
            select(VideoChannel)
            .where(VideoChannel.parent_device_id == parent_device.id)
            .order_by(VideoChannel.id.asc())
        ).all()
        channel_rows.extend((management_ip, platform_name, row) for row in rows)
    return channel_rows


def _build_fucheng_repair_plan(db: Session) -> dict:
    channel_rows = _load_fucheng_channels(db)
    physical_camera_ids = _get_physical_camera_ids(db)
    by_segment: dict[str, list[tuple[int, str, VideoChannel, dict]]] = defaultdict(list)
    for management_ip, platform_name, channel in channel_rows:
        segment, host = _camera_segment_and_host(channel.camera_ip or "")
        if not segment or host is None:
            continue
        by_segment[segment].append((host, platform_name, channel, _safe_json_dict(channel.notes)))

    area_suggestions: list[dict] = []
    topology_suggestions: list[dict] = []
    for segment, rows in by_segment.items():
        rows.sort(key=lambda item: item[0])
        known_prefixes: list[tuple[int, str]] = []
        for host, _, channel, notes in rows:
            direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
            if not direct_area:
                continue
            known_prefixes.append((host, direct_area))

        candidates_by_area, candidates_by_segment = _build_bound_switch_candidates(
            [channel for _, _, channel, _ in rows],
            db,
        )
        for host, platform_name, channel, notes in rows:
            direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
            direct_group = normalize_text(notes.get("direct_group") or "").strip()
            retired_or_special = bool(
                FUCHENG_RETIRED_PATTERN.search(
                    " ".join(
                        item
                        for item in [
                            normalize_text(channel.channel_name or ""),
                            normalize_text(notes.get("direct_name") or ""),
                            direct_area,
                            direct_group,
                        ]
                        if item
                    )
                )
            )
            if not direct_area and not retired_or_special and known_prefixes:
                channel_name_clean = normalize_text(channel.channel_name or "").strip()
                name_has_extra_annotation = bool(
                    channel_name_clean
                    and channel.camera_ip
                    and channel_name_clean != channel.camera_ip
                )
                nearest = sorted(
                    ((abs(host - known_host), known_host, prefix) for known_host, prefix in known_prefixes),
                    key=lambda item: (item[0], item[1]),
                )
                neighbor_prefixes = [
                    prefix
                    for distance, _, prefix in nearest
                    if distance <= 8
                ]
                prefix_counter = Counter(neighbor_prefixes)
                top_prefix, top_count = prefix_counter.most_common(1)[0] if prefix_counter else ("", 0)
                nearest_distance = nearest[0][0] if nearest else 999
                prefix_is_specific = " / " in top_prefix
                if name_has_extra_annotation:
                    confidence = 0.78
                    evidence = f"同网段 {segment} 存在相邻区域样本，但通道名带额外备注，需现场确认"
                elif prefix_is_specific and top_prefix and top_count >= 2 and nearest_distance <= 3:
                    confidence = 0.94
                    evidence = f"同网段 {segment} 相邻 {top_count} 个已知点位指向同楼层前缀"
                elif prefix_is_specific and top_prefix and top_count >= 3 and nearest_distance <= 8:
                    confidence = 0.84
                    evidence = f"同网段 {segment} 附近 {top_count} 个已知点位指向同楼层前缀"
                else:
                    confidence = 0.68
                    evidence = f"同网段 {segment} 存在相近区域样本，但楼层前缀不完整或证据不足"
                suggested_area = _compose_area_from_prefix(top_prefix, segment, host)
                area_suggestions.append(
                    {
                        "channel_id": channel.id,
                        "channel_no": channel.channel_no,
                        "platform_name": platform_name,
                        "camera_ip": channel.camera_ip or "",
                        "segment": segment,
                        "host": host,
                        "channel_name": normalize_text(channel.channel_name),
                        "current_area": direct_area,
                        "suggested_area": suggested_area,
                        "confidence": round(confidence, 2),
                        "auto_applicable": confidence >= 0.9,
                        "evidence": evidence,
                    }
                )

            if channel.camera_asset_id and channel.camera_asset_id not in physical_camera_ids and not retired_or_special:
                candidate_switches = _recommend_switches_for_channel(
                    channel,
                    notes,
                    candidates_by_area=candidates_by_area,
                    candidates_by_segment=candidates_by_segment,
                )
                top_candidate = candidate_switches[0] if candidate_switches else {}
                topology_suggestions.append(
                    {
                        "channel_id": channel.id,
                        "channel_no": channel.channel_no,
                        "platform_name": platform_name,
                        "camera_ip": channel.camera_ip or "",
                        "channel_name": normalize_text(channel.channel_name),
                        "direct_area": direct_area,
                        "candidate_switch_ip": top_candidate.get("switch_ip") or "",
                        "candidate_switch_name": top_candidate.get("switch_name") or "",
                        "confidence": round(min((top_candidate.get("score") or 0) / 160, 0.92), 2) if top_candidate else 0,
                        "evidence": top_candidate.get("reason") or "缺少可复用交换机样本，需现场核验",
                        "needs_field_validation": True,
                    }
                )

    area_task_groups_map: dict[tuple[str, str, str, str], dict] = {}
    for item in area_suggestions:
        segment = item.get("segment") or ""
        suggested_area = item.get("suggested_area") or ""
        if item.get("confidence", 0) >= 0.9:
            bucket = "auto"
        elif "额外备注" in (item.get("evidence") or ""):
            bucket = "annotation_review"
        elif suggested_area:
            bucket = "neighbor_review"
        else:
            bucket = "blank_review"
        key = (segment, suggested_area, bucket, item.get("platform_name") or "")
        group = area_task_groups_map.setdefault(
            key,
            {
                "segment": segment,
                "suggested_area": suggested_area,
                "bucket": bucket,
                "platform_name": item.get("platform_name") or "",
                "count": 0,
                "hosts": [],
                "sample_channels": [],
                "confidence_max": 0.0,
                "confidence_min": 1.0,
                "annotation_related": False,
            },
        )
        host = _camera_host(item.get("camera_ip") or "")
        if host is not None:
            group["hosts"].append(host)
        if len(group["sample_channels"]) < 6:
            group["sample_channels"].append(
                {
                    "camera_ip": item.get("camera_ip") or "",
                    "channel_name": item.get("channel_name") or "",
                }
            )
        confidence = float(item.get("confidence") or 0)
        group["confidence_max"] = max(float(group["confidence_max"]), confidence)
        group["confidence_min"] = min(float(group["confidence_min"]), confidence)
        group["annotation_related"] = group["annotation_related"] or ("额外备注" in (item.get("evidence") or ""))
        group["count"] += 1

    auto_area_suggestions = [item for item in area_suggestions if item["auto_applicable"]]
    bucket_labels = {
        "auto": "可自动补齐",
        "annotation_review": "备注设备待核验",
        "neighbor_review": "相邻楼层候选待核验",
        "blank_review": "无候选区域待核验",
    }
    area_task_groups = [
        {
            "segment": group["segment"],
            "platform_name": group["platform_name"],
            "suggested_area": group["suggested_area"],
            "bucket": group["bucket"],
            "bucket_label": bucket_labels.get(group["bucket"], group["bucket"]),
            "count": group["count"],
            "host_ranges": _compress_int_ranges(group["hosts"]),
            "camera_ip_range": ", ".join(
                f"{group['segment']}.{item}" for item in _compress_int_ranges(group["hosts"])[:4]
            )
            if group["segment"] and group["hosts"]
            else "",
            "confidence_min": round(float(group["confidence_min"]), 2) if group["count"] else 0,
            "confidence_max": round(float(group["confidence_max"]), 2) if group["count"] else 0,
            "annotation_related": group["annotation_related"],
            "sample_channels": group["sample_channels"],
        }
        for group in area_task_groups_map.values()
    ]
    topology_group_counter: dict[str, dict] = {}
    for item in topology_suggestions:
        group_key = item.get("candidate_switch_ip") or "待现场定位"
        group = topology_group_counter.setdefault(
            group_key,
            {
                "candidate_switch_ip": item.get("candidate_switch_ip") or "",
                "candidate_switch_name": item.get("candidate_switch_name") or "待现场定位",
                "count": 0,
                "platforms": Counter(),
                "areas": Counter(),
                "samples": [],
            },
        )
        group["count"] += 1
        if item.get("platform_name"):
            group["platforms"][item["platform_name"]] += 1
        area = item.get("direct_area") or "未标区域"
        group["areas"][area] += 1
        if len(group["samples"]) < 8:
            group["samples"].append(
                {
                    "channel_id": item.get("channel_id"),
                    "camera_ip": item.get("camera_ip") or "",
                    "channel_name": item.get("channel_name") or "",
                    "direct_area": item.get("direct_area") or "",
                }
            )
    topology_task_groups = []
    for group in topology_group_counter.values():
        topology_task_groups.append(
            {
                "candidate_switch_ip": group["candidate_switch_ip"],
                "candidate_switch_name": group["candidate_switch_name"],
                "count": group["count"],
                "platforms": _compact_counter(group["platforms"], top_n=4),
                "areas": _compact_counter(group["areas"], top_n=5),
                "samples": group["samples"],
            }
        )
    return {
        "area_missing_total": len(area_suggestions),
        "area_auto_applicable_total": len(auto_area_suggestions),
        "area_manual_total": len(area_suggestions) - len(auto_area_suggestions),
        "topology_missing_total": len(topology_suggestions),
        "topology_with_candidate_total": sum(1 for item in topology_suggestions if item["candidate_switch_ip"]),
        "area_suggestions": sorted(area_suggestions, key=lambda item: (-item["confidence"], item["camera_ip"]))[:120],
        "area_task_groups": sorted(
            area_task_groups,
            key=lambda item: (
                0 if item["bucket"] == "auto" else 1,
                -item["count"],
                item["segment"],
                item["suggested_area"] or "zzzz",
            ),
        ),
        "topology_suggestions": sorted(
            topology_suggestions,
            key=lambda item: (-item["confidence"], item["camera_ip"]),
        )[:120],
        "topology_task_groups": sorted(
            topology_task_groups,
            key=lambda item: (-item["count"], item["candidate_switch_ip"] or "zzzz"),
        ),
        "principle": "区域可高置信度自动补齐；交换机端口必须保留现场核验或交换机实采证据，不做拍脑袋写入。",
    }


def _apply_fucheng_area_suggestions(db: Session, *, min_confidence: float = 0.9, dry_run: bool = True) -> dict:
    plan = _build_fucheng_repair_plan(db)
    apply_items = [
        item
        for item in plan.get("area_suggestions", [])
        if item.get("auto_applicable") and float(item.get("confidence") or 0) >= min_confidence
    ]
    updated = 0
    skipped = 0
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    area_by_name = {
        row.display_name: row
        for row in db.scalars(select(AssetArea)).all()
        if row.display_name
    }
    for item in apply_items:
        channel = db.get(VideoChannel, int(item["channel_id"]))
        if not channel:
            skipped += 1
            continue
        notes = _safe_json_dict(channel.notes)
        if normalize_text(notes.get("direct_area") or "").strip():
            skipped += 1
            continue
        suggested_area = normalize_text(item.get("suggested_area") or "").strip()
        if not suggested_area:
            skipped += 1
            continue
        if dry_run:
            updated += 1
            continue
        notes["direct_area"] = suggested_area
        notes["area_inference"] = {
            "source": "fucheng_quality_repair_plan",
            "confidence": item.get("confidence"),
            "evidence": item.get("evidence"),
            "applied_at": now_label,
        }
        channel.notes = json.dumps(notes, ensure_ascii=False)
        if channel.camera_asset_id:
            camera = db.get(AssetDevice, channel.camera_asset_id)
            area = area_by_name.get(suggested_area)
            if camera and area:
                camera.area_id = area.id
        updated += 1
    if not dry_run:
        db.commit()
    return {
        "ok": True,
        "dry_run": dry_run,
        "min_confidence": min_confidence,
        "updated": updated,
        "skipped": skipped,
        "candidates": len(apply_items),
    }


@router.get("/sources", response_model=list[IntegrationSourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[IntegrationSourceOut]:
    rows = db.scalars(select(PlatformSource).order_by(PlatformSource.source_type, PlatformSource.name)).all()
    return list(rows)


@router.get("/jobs", response_model=list[SyncJobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[SyncJobOut]:
    rows = db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(100)).all()
    return list(rows)


@router.get("/snapshots", response_model=list[SyncSnapshotOut])
def list_snapshots(db: Session = Depends(get_db)) -> list[SyncSnapshotOut]:
    rows = db.scalars(select(SyncSnapshot).order_by(SyncSnapshot.id.desc()).limit(100)).all()
    return list(rows)


@router.get("/sources/{source_id}")
def source_detail(source_id: int, db: Session = Depends(get_db)) -> dict:
    source = db.get(PlatformSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source_not_found")
    physical_camera_ids = _get_physical_camera_ids(db)

    mappings = db.scalars(
        select(SourceObjectMapping)
        .where(SourceObjectMapping.source_id == source_id)
        .order_by(SourceObjectMapping.id.desc())
    ).all()
    jobs = db.scalars(
        select(SyncJob)
        .where(SyncJob.source_id == source_id)
        .order_by(SyncJob.id.desc())
        .limit(20)
    ).all()
    snapshots = db.scalars(
        select(SyncSnapshot)
        .where(SyncSnapshot.source_id == source_id)
        .order_by(SyncSnapshot.id.desc())
        .limit(20)
    ).all()

    device_ids = {row.asset_device_id for row in mappings if row.asset_device_id}
    channel_ids = {row.video_channel_id for row in mappings if row.video_channel_id}

    device_map = {
        row.id: row
        for row in db.scalars(select(AssetDevice).where(AssetDevice.id.in_(device_ids))).all()
    } if device_ids else {}
    channel_map = {
        row.id: row
        for row in db.scalars(select(VideoChannel).where(VideoChannel.id.in_(channel_ids))).all()
    } if channel_ids else {}

    mapping_type_counter = Counter(row.source_object_type or "unknown" for row in mappings)
    device_type_counter = Counter()
    for row in mappings:
        if row.asset_device_id and row.asset_device_id in device_map:
            device_type_counter[device_map[row.asset_device_id].device_type or "unknown"] += 1

    mapped_samples = []
    for row in mappings[:20]:
        device = device_map.get(row.asset_device_id) if row.asset_device_id else None
        channel = channel_map.get(row.video_channel_id) if row.video_channel_id else None
        mapped_samples.append(
            {
                "id": row.id,
                "source_object_type": row.source_object_type,
                "source_object_key": normalize_text(row.source_object_key),
                "confidence": row.confidence,
                "device_label": normalize_text(device.hostname or device.management_ip) if device else "",
                "device_type": device.device_type if device else "",
                "channel_label": normalize_text(channel.channel_name or f"通道 {channel.channel_no}") if channel else "",
                "camera_ip": channel.camera_ip if channel else "",
            }
        )

    return {
        "source": {
            "id": source.id,
            "name": normalize_text(source.name),
            "source_type": source.source_type,
            "vendor": normalize_text(source.vendor),
            "management_ip": source.management_ip,
            "version": normalize_text(source.version),
            "sync_status": source.sync_status,
            "last_sync_at": str(source.last_sync_at) if source.last_sync_at else "",
            "notes": normalize_text(source.notes),
        },
        "runtime_stats": _build_runtime_stats_for_source(db, source, physical_camera_ids=physical_camera_ids),
        "mapping_total": len(mappings),
        "job_total": len(jobs),
        "snapshot_total": len(snapshots),
        "mapping_type_breakdown": [
            {"source_object_type": key, "count": value}
            for key, value in mapping_type_counter.most_common()
        ],
        "device_type_breakdown": [
            {"device_type": key, "count": value}
            for key, value in device_type_counter.most_common()
        ],
        "latest_jobs": [
            {
                "id": row.id,
                "job_type": row.job_type,
                "status": row.status,
                "summary": normalize_text(row.summary),
                "error_message": normalize_text(row.error_message),
            }
            for row in jobs
        ],
        "latest_snapshots": [
            {
                "id": row.id,
                "snapshot_type": row.snapshot_type,
                "object_count": row.object_count,
                "captured_at": str(row.captured_at),
                "notes": normalize_text(row.notes),
            }
            for row in snapshots
        ],
        "mapped_samples": mapped_samples,
    }


@router.get("/summary")
def integration_summary(db: Session = Depends(get_db)) -> dict:
    sources = db.scalars(select(PlatformSource).order_by(PlatformSource.source_type, PlatformSource.name)).all()
    jobs = db.scalars(select(SyncJob).order_by(SyncJob.id.desc()).limit(40)).all()
    snapshots = db.scalars(select(SyncSnapshot).order_by(SyncSnapshot.id.desc()).limit(40)).all()
    mappings = db.scalars(select(SourceObjectMapping)).all()
    physical_camera_ids = _get_physical_camera_ids(db)

    latest_job_by_source = {}
    for job in jobs:
        latest_job_by_source.setdefault(job.source_id, job)

    latest_snapshot_by_source = {}
    for snapshot in snapshots:
        latest_snapshot_by_source.setdefault(snapshot.source_id, snapshot)

    mapping_counts = defaultdict(Counter)
    for row in mappings:
        mapping_counts[row.source_id][row.source_object_type] += 1

    source_cards = []
    for source in sources:
        latest_job = latest_job_by_source.get(source.id)
        latest_snapshot = latest_snapshot_by_source.get(source.id)
        counts = mapping_counts.get(source.id, Counter())
        runtime_stats = _build_runtime_stats_for_source(db, source, physical_camera_ids=physical_camera_ids)
        source_cards.append(
            {
                "id": source.id,
                "name": normalize_text(source.name),
                "source_type": source.source_type,
                "vendor": normalize_text(source.vendor),
                "management_ip": source.management_ip,
                "version": normalize_text(source.version),
                "sync_status": source.sync_status,
                "mapped_devices": counts.get("camera", 0) + counts.get("switch", 0) + counts.get("gateway", 0),
                "mapped_channels": counts.get("channel", 0),
                "mapping_total": sum(counts.values()),
                "runtime_stats": runtime_stats,
                "latest_job": {
                    "job_type": latest_job.job_type,
                    "status": latest_job.status,
                    "summary": normalize_text(latest_job.summary),
                }
                if latest_job
                else None,
                "latest_snapshot": {
                    "snapshot_type": latest_snapshot.snapshot_type,
                    "object_count": latest_snapshot.object_count,
                    "notes": normalize_text(latest_snapshot.notes),
                }
                if latest_snapshot
                else None,
            }
        )

    source_type_counter = Counter(source.source_type or "unknown" for source in sources)
    vendor_counter = Counter(normalize_text(source.vendor or "unknown") for source in sources)
    job_status_counter = Counter(job.status or "unknown" for job in jobs)

    return {
        "source_count": len(sources),
        "job_count": len(jobs),
        "snapshot_count": len(snapshots),
        "source_type_breakdown": [
            {"source_type": key, "count": value}
            for key, value in source_type_counter.most_common()
        ],
        "vendor_breakdown": [
            {"vendor": key, "count": value}
            for key, value in vendor_counter.most_common()
        ],
        "job_status_breakdown": [
            {"status": key, "count": value}
            for key, value in job_status_counter.most_common()
        ],
        "source_cards": source_cards,
        "latest_jobs": [
            {
                "id": row.id,
                "source_id": row.source_id,
                "job_type": row.job_type,
                "status": row.status,
                "summary": normalize_text(row.summary),
            }
            for row in jobs[:8]
        ],
        "latest_snapshots": [
            {
                "id": row.id,
                "source_id": row.source_id,
                "snapshot_type": row.snapshot_type,
                "object_count": row.object_count,
                "notes": normalize_text(row.notes),
            }
            for row in snapshots[:8]
        ],
    }


@router.get("/data-coverage")
def integration_data_coverage(db: Session = Depends(get_db)) -> dict:
    sources = db.scalars(select(PlatformSource).order_by(PlatformSource.source_type, PlatformSource.name)).all()
    devices = db.execute(select(AssetDevice.id, AssetDevice.primary_source_type)).all()
    channels = db.execute(
        select(
            AssetDevice.primary_source_type,
            func.count(VideoChannel.id),
            func.sum(case((func.length(func.trim(func.coalesce(VideoChannel.rtsp_main, ""))) > 0, 1), else_=0)),
            func.sum(case((func.length(func.trim(func.coalesce(VideoChannel.snapshot_url, ""))) > 0, 1), else_=0)),
        )
        .select_from(VideoChannel)
        .join(AssetDevice, AssetDevice.id == VideoChannel.parent_device_id, isouter=True)
        .group_by(AssetDevice.primary_source_type)
    ).all()

    device_counter = Counter()
    for device in devices:
        source_type = device[1] or "unknown"
        device_counter[source_type] += 1

    channel_map = {
        (row[0] or "unknown"): {
            "channel_total": row[1] or 0,
            "rtsp_ready": row[2] or 0,
            "snapshot_ready": row[3] or 0,
        }
        for row in channels
    }

    coverage_cards = []
    for source in sources:
        source_type = source.source_type or "unknown"
        stats = channel_map.get(source_type, {"channel_total": 0, "rtsp_ready": 0, "snapshot_ready": 0})
        channel_total = stats["channel_total"]
        rtsp_ready = stats["rtsp_ready"]
        snapshot_ready = stats["snapshot_ready"]
        coverage_cards.append(
            {
                "source_id": source.id,
                "source_name": normalize_text(source.name),
                "source_type": source_type,
                "management_ip": source.management_ip,
                "device_total": device_counter.get(source_type, 0),
                "channel_total": channel_total,
                "rtsp_ready": rtsp_ready,
                "snapshot_ready": snapshot_ready,
                "rtsp_missing": max(channel_total - rtsp_ready, 0),
                "snapshot_missing": max(channel_total - snapshot_ready, 0),
            }
        )

    source_type_summary = []
    for source_type, count in sorted(device_counter.items(), key=lambda item: item[0]):
        stats = channel_map.get(source_type, {"channel_total": 0, "rtsp_ready": 0, "snapshot_ready": 0})
        source_type_summary.append(
            {
                "source_type": source_type,
                "device_total": count,
                "channel_total": stats["channel_total"],
                "rtsp_ready": stats["rtsp_ready"],
                "snapshot_ready": stats["snapshot_ready"],
            }
        )

    return {
        "source_type_summary": source_type_summary,
        "source_cards": coverage_cards,
        "channel_total": sum(item["channel_total"] for item in channel_map.values()),
        "rtsp_ready_total": sum(item["rtsp_ready"] for item in channel_map.values()),
        "snapshot_ready_total": sum(item["snapshot_ready"] for item in channel_map.values()),
    }


@router.get("/fucheng-alignment")
def fucheng_alignment(db: Session = Depends(get_db)) -> dict:
    return _build_fucheng_alignment(db)


@router.get("/fucheng-alignment-v2")
def fucheng_alignment_v2(db: Session = Depends(get_db)) -> dict:
    return _build_fucheng_alignment(db)


@router.get("/fucheng-data-quality")
def fucheng_data_quality(db: Session = Depends(get_db)) -> dict:
    return _build_fucheng_data_quality(db)


@router.get("/fucheng-data-quality-export.csv")
def fucheng_data_quality_export_csv(db: Session = Depends(get_db)):
    payload = _build_fucheng_data_quality(db, sample_limit=None)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "issue_code",
            "issue_label",
            "detail",
            "platform_ip",
            "platform_name",
            "channel_id",
            "channel_no",
            "channel_name",
            "camera_ip",
            "channel_status",
            "direct_area",
            "rtsp_ready",
        ],
    )
    writer.writeheader()
    writer.writerows(payload.get("sample_issues") or [])
    content = output.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fucheng-data-quality-issues.csv"},
    )


@router.get("/fucheng-area-scope-normalization-preview")
def fucheng_area_scope_normalization_preview(db: Session = Depends(get_db)) -> dict:
    return _build_fucheng_area_scope_normalization(db, dry_run=True)


@router.get("/fucheng-repair-plan")
def fucheng_repair_plan(db: Session = Depends(get_db)) -> dict:
    return _build_fucheng_repair_plan(db)


@router.get("/fucheng-repair-plan-export.csv")
def fucheng_repair_plan_export_csv(db: Session = Depends(get_db)):
    payload = _build_fucheng_repair_plan(db)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "repair_type",
            "channel_id",
            "channel_no",
            "platform_name",
            "camera_ip",
            "channel_name",
            "current_area",
            "suggested_area",
            "candidate_switch_ip",
            "candidate_switch_name",
            "confidence",
            "auto_applicable",
            "evidence",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for item in payload.get("area_suggestions") or []:
        writer.writerow({**item, "repair_type": "area"})
    for group in payload.get("area_task_groups") or []:
        writer.writerow(
            {
                "repair_type": "area_task_group",
                "platform_name": group.get("platform_name") or "",
                "camera_ip": group.get("camera_ip_range") or "",
                "channel_name": f"{group.get('bucket_label') or '区域核验'} 共 {group.get('count') or 0} 路",
                "current_area": "",
                "suggested_area": group.get("suggested_area") or "",
                "confidence": f"{group.get('confidence_min')}-{group.get('confidence_max')}",
                "auto_applicable": group.get("bucket") == "auto",
                "evidence": f"{group.get('segment') or ''} / 主机段 {', '.join(group.get('host_ranges') or [])}",
            }
        )
    for item in payload.get("topology_suggestions") or []:
        writer.writerow(
            {
                **item,
                "repair_type": "topology",
                "current_area": item.get("direct_area") or "",
                "suggested_area": "",
                "auto_applicable": False,
            }
        )
    for group in payload.get("topology_task_groups") or []:
        writer.writerow(
            {
                "repair_type": "topology_task_group",
                "channel_name": f"{group.get('candidate_switch_name') or '待现场定位'} 共 {group.get('count') or 0} 路",
                "current_area": " / ".join(f"{row['name']}({row['count']})" for row in group.get("areas", [])),
                "candidate_switch_ip": group.get("candidate_switch_ip") or "",
                "candidate_switch_name": group.get("candidate_switch_name") or "",
                "auto_applicable": False,
                "evidence": "按候选交换机汇总的现场派工包",
            }
        )
    content = output.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fucheng-repair-plan.csv"},
    )


@router.get("/fucheng-field-validation-template.csv")
def fucheng_field_validation_template_csv(db: Session = Depends(get_db)):
    payload = _build_fucheng_repair_plan(db)
    merged: dict[int, dict] = {}
    area_group_index: dict[int, dict] = {}
    area_group_bucket_labels = {
        "auto": "可自动补齐",
        "annotation_review": "备注设备待核验",
        "neighbor_review": "相邻楼层候选待核验",
        "blank_review": "无候选区域待核验",
    }
    area_group_priority = {
        "auto": 10,
        "annotation_review": 20,
        "neighbor_review": 30,
        "blank_review": 40,
    }
    area_group_map: dict[tuple[str, str, str, str], dict] = {}
    for item in payload.get("area_suggestions") or []:
        segment = item.get("segment") or _camera_segment_and_host(item.get("camera_ip") or "")[0]
        suggested_area = item.get("suggested_area") or ""
        if float(item.get("confidence") or 0) >= 0.9:
            bucket = "auto"
        elif "额外备注" in (item.get("evidence") or ""):
            bucket = "annotation_review"
        elif suggested_area:
            bucket = "neighbor_review"
        else:
            bucket = "blank_review"
        key = (segment, suggested_area, bucket, item.get("platform_name") or "")
        group = area_group_map.setdefault(
            key,
            {
                "segment": segment,
                "suggested_area": suggested_area,
                "bucket": bucket,
                "platform_name": item.get("platform_name") or "",
                "hosts": [],
            },
        )
        host = _camera_host(item.get("camera_ip") or "")
        if host is not None:
            group["hosts"].append(host)
        area_group_index[int(item.get("channel_id") or 0)] = group

    for item in payload.get("area_suggestions") or []:
        channel_id = int(item.get("channel_id") or 0)
        if not channel_id:
            continue
        group = area_group_index.get(channel_id) or {}
        host_ranges = _compress_int_ranges(group.get("hosts") or [])
        row = merged.setdefault(
            channel_id,
            {
                "task_type": "",
                "task_priority": 99,
                "channel_id": channel_id,
                "channel_no": item.get("channel_no") or "",
                "platform_name": item.get("platform_name") or "",
                "camera_ip": item.get("camera_ip") or "",
                "channel_name": item.get("channel_name") or "",
                "current_area": item.get("current_area") or "",
                "suggested_area": "",
                "collected_area": "",
                "candidate_switch_ip": "",
                "candidate_switch_name": "",
                "collected_switch_ip": "",
                "collected_port": "",
                "collected_vlan": "",
                "collected_mac": "",
                "collector": "",
                "verified_at": "",
                "field_note": "",
                "system_hint": "",
                "task_group_bucket": "",
                "task_group_label": "",
                "task_group_segment": "",
                "task_group_range": "",
                "task_group_size": 0,
            },
        )
        row["task_type"] = "区域核验" if not row["task_type"] else f"{row['task_type']}+区域核验"
        row["task_priority"] = min(int(row.get("task_priority") or 99), area_group_priority.get(group.get("bucket") or "", 50))
        row["suggested_area"] = item.get("suggested_area") or ""
        row["system_hint"] = item.get("evidence") or ""
        row["task_group_bucket"] = group.get("bucket") or ""
        row["task_group_label"] = area_group_bucket_labels.get(group.get("bucket") or "", "")
        row["task_group_segment"] = group.get("segment") or ""
        row["task_group_range"] = ", ".join(host_ranges)
        row["task_group_size"] = len(group.get("hosts") or [])
    for item in payload.get("topology_suggestions") or []:
        channel_id = int(item.get("channel_id") or 0)
        if not channel_id:
            continue
        row = merged.setdefault(
            channel_id,
            {
                "task_type": "",
                "task_priority": 99,
                "channel_id": channel_id,
                "channel_no": item.get("channel_no") or "",
                "platform_name": item.get("platform_name") or "",
                "camera_ip": item.get("camera_ip") or "",
                "channel_name": item.get("channel_name") or "",
                "current_area": item.get("direct_area") or "",
                "suggested_area": "",
                "collected_area": "",
                "candidate_switch_ip": "",
                "candidate_switch_name": "",
                "collected_switch_ip": "",
                "collected_port": "",
                "collected_vlan": "",
                "collected_mac": "",
                "collector": "",
                "verified_at": "",
                "field_note": "",
                "system_hint": "",
                "task_group_bucket": "",
                "task_group_label": "",
                "task_group_segment": "",
                "task_group_range": "",
                "task_group_size": 0,
            },
        )
        row["task_type"] = "链路核验" if not row["task_type"] else f"{row['task_type']}+链路核验"
        row["task_priority"] = min(int(row.get("task_priority") or 99), 60)
        row["candidate_switch_ip"] = item.get("candidate_switch_ip") or ""
        row["candidate_switch_name"] = item.get("candidate_switch_name") or ""
        hint = item.get("evidence") or ""
        row["system_hint"] = f"{row['system_hint']}；{hint}".strip("；") if row["system_hint"] else hint

    output = io.StringIO()
    fieldnames = [
        "task_type",
        "task_priority",
        "task_group_bucket",
        "task_group_label",
        "task_group_segment",
        "task_group_range",
        "task_group_size",
        "channel_id",
        "channel_no",
        "platform_name",
        "camera_ip",
        "channel_name",
        "current_area",
        "suggested_area",
        "collected_area",
        "candidate_switch_ip",
        "candidate_switch_name",
        "collected_switch_ip",
        "collected_port",
        "collected_vlan",
        "collected_mac",
        "collector",
        "verified_at",
        "field_note",
        "system_hint",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in sorted(
        merged.values(),
        key=lambda item: (
            int(item.get("task_priority") or 99),
            item.get("task_group_segment") or "",
            item.get("task_group_range") or "",
            item["camera_ip"],
        ),
    ):
        writer.writerow(row)
    content = output.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fucheng-field-validation-template.csv"},
    )


@router.post("/fucheng-repair-plan/apply-area-suggestions")
def apply_fucheng_area_suggestions(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    min_confidence = float(payload.get("min_confidence") or 0.9)
    dry_run = bool(payload.get("dry_run", True))
    return _apply_fucheng_area_suggestions(db, min_confidence=min_confidence, dry_run=dry_run)


@router.post("/fucheng-area-scope-normalization-apply")
def apply_fucheng_area_scope_normalization(
    db: Session = Depends(get_db),
    _: object = Depends(require_roles("admin", "manager")),
) -> dict:
    return _build_fucheng_area_scope_normalization(db, dry_run=False)


@router.get("/fucheng-alignment-export.csv")
def fucheng_alignment_export_csv(db: Session = Depends(get_db)):
    payload = _build_fucheng_alignment(db)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "platform_ip",
            "platform_name",
            "channel_id",
            "channel_no",
            "channel_name",
            "camera_ip",
            "channel_status",
            "direct_area",
            "direct_group",
            "reason_code",
            "reason_label",
            "in_tg_platform_export",
            "in_switch_audit_arp",
            "candidate_switches",
        ],
    )
    writer.writeheader()
    for row in payload.get("export_rows", []):
        writer.writerow(row)
    content = output.getvalue()
    output.close()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fucheng-alignment-gap.csv"},
    )


@router.get("/tg-switch-audit-coverage")
def tg_switch_audit_coverage(db: Session = Depends(get_db)) -> dict:
    audit_index = _load_switch_audit_file_index()
    switches = db.scalars(
        select(AssetDevice)
        .where(
            AssetDevice.primary_source_type == "tg_cos",
            AssetDevice.device_type == "switch",
        )
        .order_by(AssetDevice.management_ip.asc(), AssetDevice.id.asc())
    ).all()

    valid_switches = [item for item in switches if _is_valid_ipv4(item.management_ip or "")]
    invalid_switches = [item for item in switches if not _is_valid_ipv4(item.management_ip or "")]

    audited_cards = []
    pending_cards = []
    for switch in valid_switches:
        capabilities = sorted(audit_index.get(switch.management_ip or "", set()))
        card = {
            "device_id": switch.id,
            "management_ip": switch.management_ip,
            "hostname": normalize_text(switch.hostname or switch.management_ip),
            "model": normalize_text(switch.model or ""),
            "coverage_count": len(capabilities),
            "capabilities": capabilities,
            "audit_ready": len(capabilities) >= 4,
            "notes": normalize_text(switch.notes or ""),
        }
        audited_cards.append(card)
        if len(capabilities) < 4:
            pending_cards.append(card)

    recommendations = []
    if pending_cards:
        recommendations.append("优先补采未完成审计的交换机，至少补齐 ARP、MAC 表、运行配置和版本信息。")
    if invalid_switches:
        recommendations.append("发现无效交换机对象，建议后续清理或修正这些脏数据，避免干扰拓扑判断。")
    if not recommendations:
        recommendations.append("当前 10.0.68 交换机审计覆盖完整，可继续扩展到相邻网段或新增区域。")

    return {
        "switch_total": len(switches),
        "valid_switch_total": len(valid_switches),
        "audited_switch_total": sum(1 for item in audited_cards if item["audit_ready"]),
        "partial_switch_total": sum(1 for item in audited_cards if 0 < item["coverage_count"] < 4),
        "unaudited_switch_total": sum(1 for item in audited_cards if item["coverage_count"] == 0),
        "invalid_switch_total": len(invalid_switches),
        "recommendations": recommendations,
        "pending_switches": pending_cards[:20],
        "invalid_switches": [
            {
                "device_id": item.id,
                "management_ip": item.management_ip,
                "hostname": normalize_text(item.hostname or ""),
                "model": normalize_text(item.model or ""),
                "notes": normalize_text(item.notes or ""),
            }
            for item in invalid_switches[:20]
        ],
    }


@router.get("/tg-switch-audit-coverage-export.csv")
def tg_switch_audit_coverage_export_csv(db: Session = Depends(get_db)):
    payload = tg_switch_audit_coverage(db)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "row_type",
            "device_id",
            "management_ip",
            "hostname",
            "model",
            "coverage_count",
            "capabilities",
            "audit_ready",
            "notes",
        ],
    )
    writer.writeheader()
    for row in payload.get("pending_switches", []):
        writer.writerow(
            {
                "row_type": "pending_switch",
                "device_id": row.get("device_id"),
                "management_ip": row.get("management_ip"),
                "hostname": row.get("hostname"),
                "model": row.get("model"),
                "coverage_count": row.get("coverage_count", 0),
                "capabilities": " / ".join(row.get("capabilities") or []),
                "audit_ready": row.get("audit_ready", False),
                "notes": row.get("notes", ""),
            }
        )
    for row in payload.get("invalid_switches", []):
        writer.writerow(
            {
                "row_type": "invalid_switch",
                "device_id": row.get("device_id"),
                "management_ip": row.get("management_ip"),
                "hostname": row.get("hostname"),
                "model": row.get("model"),
                "coverage_count": 0,
                "capabilities": "",
                "audit_ready": False,
                "notes": row.get("notes", ""),
            }
        )
    content = output.getvalue()
    output.close()
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=tg-switch-audit-coverage.csv"},
    )


def _build_fucheng_alignment(db: Session) -> dict:
    reason_labels = {
        "retired_or_special": "停用/拆除/未安装",
        "sub205_fact_gap": "205分平台待补平台/交换机事实",
        "sub205_pending_topology": "205分平台待补拓扑",
        "tg_fact_gap": "现有 TG 平台与交换机事实均未覆盖",
        "tg_topology_gap": "待补 250 拓扑归属",
    }
    tg_camera_fact_ips = _build_tg_camera_fact_set(db)
    switch_audit_arp_ips = _load_switch_audit_arp_ips()
    physical_camera_ids = {
        row[0]
        for row in db.execute(
            select(TopologyLink.dst_device_id)
            .where(TopologyLink.link_type == "physical", TopologyLink.dst_device_id.is_not(None))
        ).all()
        if row[0]
    }

    cards = []
    export_rows = []
    for management_ip, label in FUCHENG_PLATFORM_MAP.items():
        parent_device = db.scalar(select(AssetDevice).where(AssetDevice.management_ip == management_ip))
        if not parent_device:
            cards.append(
                {
                    "management_ip": management_ip,
                    "platform_name": label,
                    "channel_total": 0,
                    "preview_ready": 0,
                    "preview_failed": 0,
                    "reachable": 0,
                    "switch_bound": 0,
                    "switch_unbound": 0,
                    "switch_unbound_breakdown": [],
                    "sample_unbound_channels": [],
                }
            )
            continue

        channels = db.scalars(
            select(VideoChannel)
            .where(VideoChannel.parent_device_id == parent_device.id)
            .order_by(VideoChannel.id.desc())
        ).all()
        candidates_by_area, candidates_by_segment = _build_bound_switch_candidates(channels, db)
        preview_ready = sum(1 for row in channels if row.channel_status == "preview_ready")
        preview_failed = sum(1 for row in channels if row.channel_status == "preview_failed")
        reachable = sum(1 for row in channels if row.channel_status == "reachable")
        switch_bound = sum(1 for row in channels if row.camera_asset_id and row.camera_asset_id in physical_camera_ids)
        switch_unbound_rows = [
            row for row in channels if not row.camera_asset_id or row.camera_asset_id not in physical_camera_ids
        ]

        unbound_breakdown_counter = Counter()
        area_counter = Counter()
        segment_counter = Counter()
        recommended_switch_counter = Counter()
        recommended_switch_examples: dict[str, dict] = {}
        sample_unbound_channels = []
        for row in switch_unbound_rows:
            reason_code, reason_label, notes = _classify_fucheng_unbound(
                row,
                management_ip,
                tg_camera_fact_ips=tg_camera_fact_ips,
                switch_audit_arp_ips=switch_audit_arp_ips,
            )
            unbound_breakdown_counter[reason_code] += 1
            direct_area, _ = _normalize_fucheng_area(notes.get("direct_area") or "")
            camera_segment = ".".join((row.camera_ip or "").split(".")[:3]) if row.camera_ip else ""
            if direct_area:
                area_counter[direct_area] += 1
            if camera_segment:
                segment_counter[camera_segment] += 1
            candidate_switches = _recommend_switches_for_channel(
                row,
                notes,
                candidates_by_area=candidates_by_area,
                candidates_by_segment=candidates_by_segment,
            )
            for candidate in candidate_switches[:2]:
                switch_ip = candidate.get("switch_ip") or ""
                if not switch_ip:
                    continue
                recommended_switch_counter[switch_ip] += 1
                recommended_switch_examples.setdefault(
                    switch_ip,
                    {
                        "switch_ip": switch_ip,
                        "switch_name": candidate.get("switch_name") or switch_ip,
                        "reason": candidate.get("reason") or "",
                    },
                )
            export_rows.append(
                {
                    "platform_ip": management_ip,
                    "platform_name": label,
                    "channel_id": row.id,
                    "channel_no": row.channel_no,
                    "channel_name": normalize_text(row.channel_name),
                    "camera_ip": row.camera_ip or "",
                    "channel_status": row.channel_status or "",
                    "direct_area": direct_area,
                    "direct_group": normalize_text(notes.get("direct_group") or ""),
                    "reason_code": reason_code,
                    "reason_label": reason_label,
                    "in_tg_platform_export": bool(notes.get("_in_tg_platform_export")),
                    "in_switch_audit_arp": bool(notes.get("_in_switch_audit_arp")),
                    "candidate_switches": " / ".join(
                        f"{item.get('switch_ip')}({item.get('reason')})" for item in candidate_switches
                    ),
                }
            )
            if len(sample_unbound_channels) < 20:
                sample_unbound_channels.append(
                    {
                        "channel_id": row.id,
                        "channel_no": row.channel_no,
                        "channel_name": normalize_text(row.channel_name),
                        "camera_ip": row.camera_ip,
                        "channel_status": row.channel_status,
                        "direct_area": _normalize_fucheng_area(notes.get("direct_area") or "")[0],
                        "direct_group": normalize_text(notes.get("direct_group") or ""),
                        "reason_code": reason_code,
                        "reason_label": reason_label,
                        "in_tg_platform_export": bool(notes.get("_in_tg_platform_export")),
                        "in_switch_audit_arp": bool(notes.get("_in_switch_audit_arp")),
                        "candidate_switches": candidate_switches,
                    }
                )

        next_actions = _build_next_actions(management_ip, unbound_breakdown_counter, area_counter, segment_counter)
        recommended_switches = [
            {
                "switch_ip": switch_ip,
                "switch_name": recommended_switch_examples.get(switch_ip, {}).get("switch_name") or switch_ip,
                "count": count,
                "reason": recommended_switch_examples.get(switch_ip, {}).get("reason") or "",
            }
            for switch_ip, count in recommended_switch_counter.most_common(8)
        ]
        cards.append(
            {
                "management_ip": management_ip,
                "platform_name": label,
                "channel_total": len(channels),
                "preview_ready": preview_ready,
                "preview_failed": preview_failed,
                "reachable": reachable,
                "switch_bound": switch_bound,
                "switch_unbound": len(switch_unbound_rows),
                "switch_unbound_breakdown": [
                    {
                        "reason_code": reason_code,
                        "reason_label": reason_labels.get(reason_code, reason_code),
                        "count": count,
                    }
                    for reason_code, count in unbound_breakdown_counter.most_common()
                ],
                "top_areas": _compact_counter(area_counter),
                "top_segments": _compact_counter(segment_counter),
                "recommended_switches": recommended_switches,
                "next_actions": next_actions,
                "sample_unbound_channels": sample_unbound_channels,
            }
        )

    return {
        "cards": cards,
        "platform_total": len(cards),
        "channel_total": sum(item["channel_total"] for item in cards),
        "switch_bound_total": sum(item["switch_bound"] for item in cards),
        "switch_unbound_total": sum(item["switch_unbound"] for item in cards),
        "export_rows": export_rows,
    }

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.asset import AssetArea, AssetDevice, SwitchLiveProbe, TopologyLink


@dataclass
class CameraMissingMacRow:
    camera_ip: str
    camera_name: str
    area: str
    source_type: str
    notes_hint: str
    collected_mac: str
    collected_switch_ip: str
    collected_port: str
    collector: str
    verified_at: str


@dataclass
class SwitchGapRow:
    switch_ip: str
    switch_name: str
    probe_status: str
    arp_entry_count: int
    l2_mac_count: int
    direct_match_count: int
    gap_reason: str
    field_result: str
    field_note: str


def _report_dir() -> Path:
    path = settings.runtime_dir / "reports" / "field_validation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _short_hint(raw: str) -> str:
    text = (raw or "").strip().replace("\n", " ").replace("\r", " ")
    return text[:220]


def _classify_gap_reason(probe: SwitchLiveProbe, direct_match_count: int) -> str:
    if probe.probe_status == "offline":
        return "telnet_closed_or_unreachable"
    if direct_match_count > 0:
        return "has_direct_match"
    if probe.l2_mac_count >= 1000 and probe.arp_entry_count >= 10:
        return "mac_table_rich_but_camera_mac_unmatched"
    if probe.l2_mac_count >= 500:
        return "likely_aggregation_or_unknown_camera_mac"
    if probe.arp_entry_count > 0 and probe.l2_mac_count == 0:
        return "arp_only_no_mac_table"
    if probe.arp_entry_count == 0 and probe.l2_mac_count == 0:
        return "no_visible_forwarding_table"
    return "low_signal_needs_manual_review"


def main() -> int:
    db = SessionLocal()
    try:
        area_map = {
            row.id: row.display_name
            for row in db.scalars(select(AssetArea)).all()
        }
        missing_camera_rows = db.scalars(
            select(AssetDevice).where(
                AssetDevice.device_type == "camera",
                AssetDevice.device_status != "archived",
                AssetDevice.mac_address == "",
            ).order_by(AssetDevice.management_ip.asc())
        ).all()
        camera_sheet = [
            CameraMissingMacRow(
                camera_ip=row.management_ip or "",
                camera_name=row.hostname or "",
                area=area_map.get(row.area_id, ""),
                source_type=row.primary_source_type or "",
                notes_hint=_short_hint(row.notes or ""),
                collected_mac="",
                collected_switch_ip="",
                collected_port="",
                collector="",
                verified_at="",
            )
            for row in missing_camera_rows
        ]

        direct_counts = dict(
            db.execute(
                select(TopologyLink.src_device_id, func.count(TopologyLink.id))
                .where(TopologyLink.evidence_type == "direct_switch_mac_probe")
                .group_by(TopologyLink.src_device_id)
            ).all()
        )
        switch_rows = db.execute(
            select(AssetDevice, SwitchLiveProbe)
            .join(SwitchLiveProbe, SwitchLiveProbe.device_id == AssetDevice.id)
            .where(
                AssetDevice.device_type == "switch",
                AssetDevice.device_status != "archived",
                AssetDevice.management_ip.like("10.0.68.%"),
            )
            .order_by(AssetDevice.management_ip.asc())
        ).all()
        switch_sheet = [
            SwitchGapRow(
                switch_ip=device.management_ip or "",
                switch_name=device.hostname or "",
                probe_status=probe.probe_status,
                arp_entry_count=int(probe.arp_entry_count or 0),
                l2_mac_count=int(probe.l2_mac_count or 0),
                direct_match_count=int(direct_counts.get(device.id, 0)),
                gap_reason=_classify_gap_reason(probe, int(direct_counts.get(device.id, 0))),
                field_result="",
                field_note="",
            )
            for device, probe in switch_rows
            if int(direct_counts.get(device.id, 0)) == 0
        ]
    finally:
        db.close()

    out_dir = _report_dir()
    stamp = _stamp()
    camera_csv = out_dir / f"camera-missing-mac-sheet-{stamp}.csv"
    switch_csv = out_dir / f"switch-gap-sheet-{stamp}.csv"
    summary_json = out_dir / f"field-validation-summary-{stamp}.json"

    with camera_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(camera_sheet[0]).keys()))
        writer.writeheader()
        for row in camera_sheet:
            writer.writerow(asdict(row))

    with switch_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(switch_sheet[0]).keys()))
        writer.writeheader()
        for row in switch_sheet:
            writer.writerow(asdict(row))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "camera_missing_mac_count": len(camera_sheet),
        "switch_gap_count": len(switch_sheet),
        "camera_sheet": str(camera_csv),
        "switch_sheet": str(switch_csv),
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from app.models.asset import AssetDevice, SwitchLiveProbe, TopologyLink


@dataclass
class GapRow:
    management_ip: str
    hostname: str
    probe_status: str
    arp_entry_count: int
    l2_mac_count: int
    direct_match_count: int
    reason: str
    checked_at: str


def _report_paths(started_at: datetime) -> tuple[Path, Path]:
    report_dir = settings.runtime_dir / "reports" / "switch_live_probe"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d-%H%M%S-%f")
    return (
        report_dir / f"switch-gap-analysis-{stamp}.json",
        report_dir / f"switch-gap-analysis-{stamp}.csv",
    )


def _classify_reason(row: SwitchLiveProbe, direct_match_count: int) -> str:
    if row.probe_status == "offline":
        return "telnet_closed_or_unreachable"
    if direct_match_count > 0:
        return "has_direct_match"
    if row.l2_mac_count >= 1000 and row.arp_entry_count >= 10:
        return "mac_table_rich_but_camera_mac_unmatched"
    if row.l2_mac_count >= 500:
        return "likely_aggregation_or_unknown_camera_mac"
    if row.arp_entry_count > 0 and row.l2_mac_count == 0:
        return "arp_only_no_mac_table"
    if row.arp_entry_count == 0 and row.l2_mac_count == 0:
        return "no_visible_forwarding_table"
    return "low_signal_needs_manual_review"


def main() -> int:
    started_at = datetime.now()
    db = SessionLocal()
    try:
        direct_counts = dict(
            db.execute(
                select(TopologyLink.src_device_id, func.count(TopologyLink.id))
                .where(TopologyLink.evidence_type == "direct_switch_mac_probe")
                .group_by(TopologyLink.src_device_id)
            ).all()
        )
        rows = db.execute(
            select(AssetDevice, SwitchLiveProbe)
            .join(SwitchLiveProbe, SwitchLiveProbe.device_id == AssetDevice.id)
            .where(
                AssetDevice.device_type == "switch",
                AssetDevice.device_status != "archived",
                AssetDevice.management_ip.like("10.0.68.%"),
            )
            .order_by(AssetDevice.management_ip.asc())
        ).all()
        payload_rows: list[GapRow] = []
        for device, probe in rows:
            direct_match_count = int(direct_counts.get(device.id, 0))
            payload_rows.append(
                GapRow(
                    management_ip=device.management_ip or "",
                    hostname=device.hostname or "",
                    probe_status=probe.probe_status,
                    arp_entry_count=int(probe.arp_entry_count or 0),
                    l2_mac_count=int(probe.l2_mac_count or 0),
                    direct_match_count=direct_match_count,
                    reason=_classify_reason(probe, direct_match_count),
                    checked_at=probe.checked_at.isoformat(timespec="seconds") if probe.checked_at else "",
                )
            )
    finally:
        db.close()

    json_path, csv_path = _report_paths(started_at)
    summary = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "count": len(payload_rows),
        "zero_direct": sum(1 for row in payload_rows if row.direct_match_count == 0),
        "items": [asdict(row) for row in payload_rows],
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(payload_rows[0]).keys()))
        writer.writeheader()
        for row in payload_rows:
            writer.writerow(asdict(row))
    print(json.dumps({"json_report": str(json_path), "csv_report": str(csv_path), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

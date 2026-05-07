from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.asset import AssetDevice, SwitchLiveProbe
from app.services.switch_live_probe import probe_switch_live


@dataclass
class ProbeSummary:
    management_ip: str
    hostname: str
    probe_status: str
    camera_match_count: int
    arp_entry_count: int
    l2_mac_count: int
    version_text: str
    checked_at: str
    error_message: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch probe TG-NET switches and persist a report.")
    parser.add_argument("--subnet-prefix", default="10.0.68.", help="Only probe switches whose IP starts with this prefix.")
    parser.add_argument("--limit", type=int, default=12, help="Max switches per run.")
    parser.add_argument("--offset", type=int, default=0, help="Offset after sorting by management IP.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-switch timeout seconds.")
    parser.add_argument("--username", default="admin", help="Telnet username.")
    parser.add_argument("--password", default="a12345678", help="Telnet password.")
    parser.add_argument("--skip-recent-minutes", type=int, default=20, help="Skip switches probed in the last N minutes.")
    parser.add_argument("--ips", nargs="*", default=None, help="Optional explicit switch IP list.")
    return parser.parse_args()


def _should_skip_recent(row: AssetDevice, probe_map: dict[int, SwitchLiveProbe], minutes: int) -> bool:
    if minutes <= 0:
        return False
    probe = probe_map.get(row.id)
    if not probe or not probe.checked_at:
        return False
    return probe.checked_at >= datetime.now() - timedelta(minutes=minutes)


def _load_switches(args: argparse.Namespace) -> tuple[list[AssetDevice], dict[int, SwitchLiveProbe]]:
    db = SessionLocal()
    try:
        switches = db.scalars(
            select(AssetDevice)
            .where(
                AssetDevice.device_type == "switch",
                AssetDevice.device_status != "archived",
            )
            .order_by(AssetDevice.management_ip.asc())
        ).all()
        probe_rows = db.scalars(select(SwitchLiveProbe)).all()
        probe_map = {row.device_id: row for row in probe_rows}
    finally:
        db.close()

    if args.ips:
        wanted = {ip.strip() for ip in args.ips if ip and ip.strip()}
        switches = [row for row in switches if (row.management_ip or "").strip() in wanted]
    else:
        prefix = (args.subnet_prefix or "").strip()
        if prefix:
            switches = [row for row in switches if (row.management_ip or "").startswith(prefix)]

    switches = [row for row in switches if not _should_skip_recent(row, probe_map, args.skip_recent_minutes)]
    return switches[args.offset : args.offset + max(1, args.limit)], probe_map


def _report_paths(started_at: datetime) -> tuple[Path, Path]:
    report_dir = settings.runtime_dir / "reports" / "switch_live_probe"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d-%H%M%S-%f")
    return (
        report_dir / f"switch-live-probe-{stamp}.json",
        report_dir / f"switch-live-probe-{stamp}.csv",
    )


def main() -> int:
    args = _parse_args()
    started_at = datetime.now()
    switches, _ = _load_switches(args)
    if not switches:
        print("No switches matched this batch.")
        return 0

    summaries: list[ProbeSummary] = []
    db = SessionLocal()
    try:
        for switch in switches:
            result = probe_switch_live(
                db,
                switch=switch,
                username=args.username,
                password=args.password,
                timeout_seconds=args.timeout,
            )
            summaries.append(
                ProbeSummary(
                    management_ip=switch.management_ip or "",
                    hostname=switch.hostname or "",
                    probe_status=result.get("probe_status", ""),
                    camera_match_count=int(result.get("camera_match_count") or 0),
                    arp_entry_count=int(result.get("arp_entry_count") or 0),
                    l2_mac_count=int(result.get("l2_mac_count") or 0),
                    version_text=result.get("version_text", "") or "",
                    checked_at=result.get("checked_at", "") or "",
                    error_message=result.get("error_message", "") or "",
                )
            )
    finally:
        db.close()

    json_path, csv_path = _report_paths(started_at)
    payload = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(summaries),
        "hits": sum(1 for item in summaries if item.camera_match_count > 0),
        "items": [asdict(item) for item in summaries],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(summaries[0]).keys()))
        writer.writeheader()
        for item in summaries:
            writer.writerow(asdict(item))

    print(json.dumps({"json_report": str(json_path), "csv_report": str(csv_path), **payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

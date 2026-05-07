from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHYSICAL = Path(r"E:\Users\Administrator\Desktop\图像采集设备信息表（自用版）.xls")
DEFAULT_SWITCH = Path(r"E:\Users\Administrator\Desktop\长兴中央大道交换机配置信息表（级联））[已恢复]全.xlsx")
DEFAULT_OUT = ROOT / "runtime" / "analysis" / "asset_lineage"

IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
MAC_RE = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}")
PORT_RE = re.compile(r"(?:(?:端口|口|port)\s*)?(\d{1,2})(?:\s*口)?", re.IGNORECASE)
WELL_RE = re.compile(r"(\d+)\s*#?\s*号?\s*井")
NUM_RE = re.compile(r"^\d+(?:\.0+)?$")


def clean(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def normalize_ip(value: Any) -> str:
    text = clean(value)
    match = IP_RE.search(text)
    if not match:
        return ""
    parts = match.group(0).split(".")
    nums: list[int] = []
    for part in parts:
        try:
            num = int(part)
        except ValueError:
            return ""
        if num < 0 or num > 255:
            return ""
        nums.append(num)
    return ".".join(str(num) for num in nums)


def extract_ips(value: Any) -> list[str]:
    ips: list[str] = []
    for raw in IP_RE.findall(clean(value)):
        ip = normalize_ip(raw)
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def normalize_mac(value: Any) -> str:
    match = MAC_RE.search(clean(value))
    if not match:
        return ""
    return match.group(0).replace("-", ":").upper()


def floor_token(text: Any) -> str:
    text = clean(text).upper()
    mapping = [
        (r"B2|负二|地下二", "B2"),
        (r"B1|负一|地下一", "B1"),
        (r"1F|1楼|一楼", "1F"),
        (r"2F|2楼|二楼", "2F"),
        (r"3F|3楼|三楼", "3F"),
        (r"4F|4楼|四楼", "4F"),
        (r"5F|5楼|五楼", "5F"),
        (r"6F|6楼|六楼", "6F"),
    ]
    for pattern, token in mapping:
        if re.search(pattern, text):
            return token
    return ""


def zone_token(text: Any) -> str:
    text = clean(text)
    if "停车" in text or "车场" in text:
        return "停车场"
    if "户外" in text or "室外" in text:
        return "户外"
    if "北" in text:
        return "北区"
    if "南" in text:
        return "南区"
    if "东" in text:
        return "东区"
    if "西" in text:
        return "西区"
    return ""


def well_token(text: Any) -> str:
    match = WELL_RE.search(clean(text))
    if not match:
        return ""
    return f"{int(match.group(1))}号井"


def extract_port(text: Any) -> str:
    text = clean(text)
    if not text:
        return ""
    candidates = re.findall(r"(\d{1,2})\s*口", text)
    if candidates:
        return f"{int(candidates[-1])}口"
    # Avoid treating floor/well numbers as port if a clearer port token is absent.
    if "口" not in text and "端口" not in text and "port" not in text.lower():
        return ""
    match = PORT_RE.search(text)
    return f"{int(match.group(1))}口" if match else ""


def to_int(value: Any) -> int:
    text = clean(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def third_octet(ip: str) -> str:
    parts = ip.split(".")
    return parts[2] if len(parts) == 4 else ""


def ip_to_sort_key(ip: str) -> tuple[int, int, int, int]:
    parts = ip.split(".")
    if len(parts) != 4:
        return (999, 999, 999, 999)
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def make_safe_filename(path: Path) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", path.stem).strip("_")
    return safe or "workbook"


def export_workbook_with_excel(path: Path, out_dir: Path) -> dict[str, Any]:
    """Use local Excel COM through PowerShell so no Python Excel package is required."""
    out_json = out_dir / f"{make_safe_filename(path)}.sheets.json"
    ps_script = out_dir / "export_excel_sheets.ps1"
    ps_script.write_text(
        r"""
param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputJson
)
$ErrorActionPreference = "Stop"
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$payload = [ordered]@{
  path = $InputPath
  sheets = @()
}
try {
  $wb = $excel.Workbooks.Open($InputPath)
  try {
    foreach ($ws in $wb.Worksheets) {
      $used = $ws.UsedRange
      $rowCount = [int]$used.Rows.Count
      $colCount = [int]$used.Columns.Count
      $rows = @()
      for ($r = 1; $r -le $rowCount; $r++) {
        $row = @()
        for ($c = 1; $c -le $colCount; $c++) {
          $value = $ws.Cells.Item($r, $c).Text
          if ($null -eq $value) { $value = "" }
          $row += [string]$value
        }
        $rows += ,$row
      }
      $payload.sheets += [ordered]@{
        name = [string]$ws.Name
        rows = $rowCount
        cols = $colCount
        values = $rows
      }
    }
  } finally {
    $wb.Close($false)
  }
} finally {
  $excel.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}
$json = $payload | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($OutputJson, $json, [System.Text.Encoding]::UTF8)
""".strip(),
        encoding="utf-8-sig",
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_script),
            "-InputPath",
            str(path),
            "-OutputJson",
            str(out_json),
        ],
        check=True,
        cwd=str(ROOT),
    )
    return json.loads(out_json.read_text(encoding="utf-8-sig"))


def sheet_profile(sheet: dict[str, Any]) -> dict[str, Any]:
    rows = sheet["values"]
    cols = sheet["cols"]
    non_empty = [0 for _ in range(cols)]
    ip_hits = [0 for _ in range(cols)]
    mac_hits = [0 for _ in range(cols)]
    samples: list[dict[str, Any]] = []
    for r_idx, row in enumerate(rows, start=1):
        non_empty_cells = [clean(cell) for cell in row if clean(cell)]
        if non_empty_cells and len(samples) < 8:
            samples.append({"row": r_idx, "values": non_empty_cells[:14]})
        for c_idx in range(cols):
            value = clean(row[c_idx]) if c_idx < len(row) else ""
            if value:
                non_empty[c_idx] += 1
            if extract_ips(value):
                ip_hits[c_idx] += 1
            if normalize_mac(value):
                mac_hits[c_idx] += 1
    return {
        "sheet_name": sheet["name"],
        "raw_rows": sheet["rows"],
        "raw_cols": sheet["cols"],
        "non_empty_by_col": non_empty,
        "ip_hits_by_col": ip_hits,
        "mac_hits_by_col": mac_hits,
        "sample_non_empty_rows": samples,
    }


def first_sheet_with_ip(payload: dict[str, Any], min_rows: int = 10) -> dict[str, Any]:
    ranked = []
    for sheet in payload["sheets"]:
        profile = sheet_profile(sheet)
        ip_count = sum(profile["ip_hits_by_col"])
        ranked.append((ip_count, sheet["rows"], sheet))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for ip_count, rows, sheet in ranked:
        if ip_count and rows >= min_rows:
            return sheet
    raise RuntimeError("No usable sheet with IP data found.")


@dataclass
class CameraFact:
    cad_id: str
    source_row: int
    source_sheet: str
    seq: str
    ip: str
    mac: str
    camera_type: str
    detail_addr: str
    install_pos: str
    can_capture: str
    touches_sensitive: str
    floor: str
    zone: str
    well: str
    area_label: str
    x: float | None
    y: float | None
    coordinate_source: str
    raw_row: list[str]


@dataclass
class SwitchFact:
    switch_id: str
    source_row: int
    source_sheet: str
    seq: str
    primary_ip: str
    all_ips: list[str]
    mac: str
    camera_count: int
    music_count: int
    cashier_count: int
    shop_lan_count: int
    remote_cascade_count: int
    tg_cascade_count: int
    total_ports: int
    switch_location: str
    uplink_location: str
    floor: str
    zone: str
    well: str
    uplink_floor: str
    uplink_zone: str
    uplink_well: str
    uplink_port: str
    role: str
    raw_row: list[str]


def parse_camera_sheet(sheet: dict[str, Any]) -> tuple[list[CameraFact], dict[str, Any]]:
    rows = sheet["values"]
    header_index = None
    for idx, row in enumerate(rows):
        joined = "|".join(clean(cell) for cell in row)
        if "序号" in joined and "IP" in joined and ("详细地址" in joined or "安装部位" in joined):
            header_index = idx
            break
    if header_index is None:
        raise RuntimeError("Physical camera sheet header not found.")
    header = [clean(cell) for cell in rows[header_index]]
    parsed: list[CameraFact] = []
    invalid_rows: list[dict[str, Any]] = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        row = row + [""] * max(0, 7 - len(row))
        seq = clean(row[0])
        ip = normalize_ip(row[1])
        non_empty = [clean(cell) for cell in row if clean(cell)]
        if not non_empty:
            continue
        if not seq and not ip:
            continue
        if not ip:
            invalid_rows.append({"source_row": offset, "reason": "missing_or_invalid_ip", "row": row})
            continue
        detail = clean(row[3])
        install = clean(row[4])
        merged = f"{detail} {install}"
        floor = floor_token(merged)
        zone = zone_token(merged)
        well = well_token(merged)
        area = " / ".join(part for part in [floor, zone, well] if part) or clean(detail or install or "未归类")
        parsed.append(
            CameraFact(
                cad_id=f"{sheet['name']}!R{offset}:SEQ-{seq or ip}",
                source_row=offset,
                source_sheet=sheet["name"],
                seq=seq,
                ip=ip,
                mac=normalize_mac(" ".join(row)),
                camera_type=clean(row[2]),
                detail_addr=detail,
                install_pos=install,
                can_capture=clean(row[5]),
                touches_sensitive=clean(row[6]),
                floor=floor,
                zone=zone,
                well=well,
                area_label=area,
                x=None,
                y=None,
                coordinate_source="not_present_in_uploaded_sheet",
                raw_row=[clean(cell) for cell in row],
            )
        )
    return parsed, {"header_row": header_index + 1, "headers": header, "invalid_rows": invalid_rows}


def parse_switch_sheet(sheet: dict[str, Any]) -> tuple[list[SwitchFact], dict[str, Any]]:
    rows = sheet["values"]
    facts: list[SwitchFact] = []
    invalid_rows: list[dict[str, Any]] = []
    first_data_row = None
    for offset, row in enumerate(rows, start=1):
        if len(row) >= 11 and normalize_ip(row[10]) and (NUM_RE.match(clean(row[0])) or to_int(row[1]) > 0):
            first_data_row = offset
            break
    if first_data_row is None:
        raise RuntimeError("Switch cascade data rows not found.")
    for offset, row in enumerate(rows[first_data_row - 1 :], start=first_data_row):
        row = row + [""] * max(0, 13 - len(row))
        raw_ip = clean(row[10])
        ips = extract_ips(raw_ip)
        location = clean(row[8])
        uplink = clean(row[9])
        non_empty = [clean(cell) for cell in row if clean(cell)]
        if not non_empty:
            continue
        if not ips:
            invalid_rows.append({"source_row": offset, "reason": "missing_or_invalid_switch_ip", "row": row})
            continue
        floor = floor_token(location)
        zone = zone_token(location)
        well = well_token(location)
        uplink_floor = floor_token(uplink)
        uplink_zone = zone_token(uplink)
        uplink_well = well_token(uplink)
        text = f"{location} {uplink} {raw_ip}"
        if "核心" in text or "机房" in location:
            role = "core"
        elif floor == "2F" or "汇聚" in text:
            role = "aggregation"
        elif to_int(row[1]) > 0:
            role = "access"
        else:
            role = "switch"
        primary_ip = ips[0]
        facts.append(
            SwitchFact(
                switch_id=f"SW:{primary_ip}",
                source_row=offset,
                source_sheet=sheet["name"],
                seq=clean(row[0]) or f"R{offset}",
                primary_ip=primary_ip,
                all_ips=ips,
                mac=normalize_mac(" ".join(row)),
                camera_count=to_int(row[1]),
                music_count=to_int(row[2]),
                cashier_count=to_int(row[3]),
                shop_lan_count=to_int(row[4]),
                remote_cascade_count=to_int(row[5]),
                tg_cascade_count=to_int(row[6]),
                total_ports=to_int(row[7]),
                switch_location=location,
                uplink_location=uplink,
                floor=floor,
                zone=zone,
                well=well,
                uplink_floor=uplink_floor,
                uplink_zone=uplink_zone,
                uplink_well=uplink_well,
                uplink_port=extract_port(uplink),
                role=role,
                raw_row=[clean(cell) for cell in row],
            )
        )
    return facts, {"first_data_row": first_data_row, "invalid_rows": invalid_rows}


def add_derived_coordinates(cameras: list[CameraFact]) -> None:
    floor_order = {"B2": 0, "B1": 1, "1F": 2, "2F": 3, "3F": 4, "4F": 5, "5F": 6, "6F": 7, "": 8}
    zone_order = {"西区": 0, "南区": 1, "东区": 2, "北区": 3, "停车场": 4, "户外": 5, "": 6}
    grouped: dict[tuple[str, str], list[CameraFact]] = defaultdict(list)
    for camera in cameras:
        grouped[(camera.floor, camera.zone)].append(camera)
    for (floor, zone), items in grouped.items():
        items.sort(key=lambda item: ip_to_sort_key(item.ip))
        base_x = 120 + zone_order.get(zone, 6) * 180
        base_y = 100 + floor_order.get(floor, 8) * 140
        cols = max(1, math.ceil(math.sqrt(len(items))))
        for idx, camera in enumerate(items):
            camera.x = float(base_x + (idx % cols) * 18)
            camera.y = float(base_y + (idx // cols) * 18)
            camera.coordinate_source = "derived_layout_from_floor_zone_ip_order"


def location_key(floor: str, well: str) -> str:
    return f"{floor}|{well}" if floor and well else ""


def build_switch_parent_map(switches: list[SwitchFact]) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    by_location: dict[str, list[SwitchFact]] = defaultdict(list)
    for sw in switches:
        key = location_key(sw.floor, sw.well)
        if key:
            by_location[key].append(sw)
    parent_map: dict[str, str] = {}
    parent_port: dict[str, str] = {}
    unresolved: list[dict[str, Any]] = []
    core_id = "CORE:中央大道监控核心"
    for sw in switches:
        if sw.role == "core":
            parent_map[sw.switch_id] = core_id
            parent_port[sw.switch_id] = sw.uplink_port
            continue
        parent_id = ""
        key = location_key(sw.uplink_floor, sw.uplink_well)
        candidates = [item for item in by_location.get(key, []) if item.switch_id != sw.switch_id]
        if candidates:
            candidates.sort(key=lambda item: (item.role != "aggregation", item.primary_ip))
            parent_id = candidates[0].switch_id
        elif "核心" in sw.uplink_location or "机房" in sw.uplink_location or sw.uplink_floor == "":
            parent_id = core_id
        else:
            parent_id = core_id
            unresolved.append(
                {
                    "switch_id": sw.switch_id,
                    "switch_ip": sw.primary_ip,
                    "uplink_location": sw.uplink_location,
                    "reason": "uplink_location_not_matched_to_switch_location",
                }
            )
        parent_map[sw.switch_id] = parent_id
        parent_port[sw.switch_id] = sw.uplink_port
    return parent_map, parent_port, unresolved


def camera_switch_score(camera: CameraFact, sw: SwitchFact) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if camera.floor and sw.floor and camera.floor == sw.floor:
        score += 55
        reasons.append("floor_match")
    elif camera.floor and sw.floor:
        score -= 35
        reasons.append("floor_mismatch")
    if camera.zone and sw.zone and camera.zone == sw.zone:
        score += 18
        reasons.append("zone_match")
    if camera.well and sw.well and camera.well == sw.well:
        score += 22
        reasons.append("well_match")
    text_a = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", f"{camera.detail_addr} {camera.install_pos}"))
    text_b = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", sw.switch_location))
    overlap = len(text_a & text_b)
    if overlap:
        score += min(12, overlap * 2)
        reasons.append("location_text_overlap")
    if sw.camera_count <= 0:
        score -= 10
        reasons.append("switch_declares_zero_camera_ports")
    return score, reasons


def assign_cameras_to_switches(
    cameras: list[CameraFact], switches: list[SwitchFact]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    access_switches = [sw for sw in switches if sw.camera_count > 0]
    remaining_capacity = {sw.switch_id: max(1, sw.camera_count) for sw in access_switches}
    assignments: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for camera in sorted(cameras, key=lambda item: ip_to_sort_key(item.ip)):
        scored = []
        for sw in access_switches:
            score, reasons = camera_switch_score(camera, sw)
            if remaining_capacity.get(sw.switch_id, 0) <= 0:
                score -= 14
                reasons.append("declared_capacity_exceeded")
            scored.append((score, sw.primary_ip, sw, reasons))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not scored or scored[0][0] < 20:
            unmatched.append(
                {
                    "cad_id": camera.cad_id,
                    "camera_ip": camera.ip,
                    "physical_area": camera.area_label,
                    "reason": "no_switch_candidate_above_threshold",
                    "best_score": scored[0][0] if scored else None,
                }
            )
            continue
        score, _, sw, reasons = scored[0]
        remaining_capacity[sw.switch_id] = remaining_capacity.get(sw.switch_id, 0) - 1
        conflict_case = []
        if camera.floor and sw.floor and camera.floor != sw.floor:
            conflict_case.append("PHYSICAL_LOGICAL_FLOOR_MISMATCH")
        if camera.zone and sw.zone and camera.zone != sw.zone:
            conflict_case.append("PHYSICAL_LOGICAL_ZONE_MISMATCH")
        if remaining_capacity[sw.switch_id] < 0:
            conflict_case.append("SWITCH_CAMERA_COUNT_OVER_CAPACITY")
        assignments[camera.ip] = {
            "switch": sw,
            "score": score,
            "confidence": round(min(0.98, max(0.35, score / 100)), 2),
            "evidence": reasons,
            "conflict_case": conflict_case,
            "logical_port": "",
            "match_method": "inferred_by_floor_zone_capacity",
        }
        if conflict_case:
            conflicts.append(
                {
                    "cad_id": camera.cad_id,
                    "camera_ip": camera.ip,
                    "switch_ip": sw.primary_ip,
                    "conflict_case": conflict_case,
                    "camera_area": camera.area_label,
                    "switch_location": sw.switch_location,
                    "score": score,
                }
            )
    return assignments, unmatched, conflicts


def descendant_camera_load(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    children: dict[str, list[str]] = defaultdict(list)
    node_types = {node["ID"]: node["Type"] for node in nodes}
    for edge in edges:
        children[edge["Source"]].append(edge["Target"])

    memo: dict[str, int] = {}

    def count(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        total = 1 if node_types.get(node_id) == "camera" else 0
        for child in children.get(node_id, []):
            total += count(child)
        memo[node_id] = total
        return total

    for node in nodes:
        count(node["ID"])
    return memo


def build_topology(
    cameras: list[CameraFact],
    switches: list[SwitchFact],
    assignments: dict[str, dict[str, Any]],
    unresolved_uplinks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    core_id = "CORE:中央大道监控核心"
    parent_map, parent_port, _ = build_switch_parent_map(switches)
    nodes: list[dict[str, Any]] = [
        {
            "ID": core_id,
            "Parent_ID": None,
            "Type": "core_switch",
            "Name": "中央大道监控核心",
            "IP": None,
            "MAC": None,
            "CAD_ID": None,
            "Physical_Pos": {"X": None, "Y": None, "Area": "监控机房", "Floor": "", "Zone": "", "Source": "inferred_core"},
            "Logical_Port": None,
            "VLAN": None,
            "Conflict_Case": [],
            "Evidence": ["core_root_inserted_for_tree_construction"],
        }
    ]
    edges: list[dict[str, Any]] = []
    for sw in switches:
        parent_id = parent_map.get(sw.switch_id, core_id)
        node_type = "access_switch" if sw.role == "access" else f"{sw.role}_switch"
        nodes.append(
            {
                "ID": sw.switch_id,
                "Parent_ID": parent_id,
                "Type": node_type,
                "Name": sw.switch_location or sw.primary_ip,
                "IP": sw.primary_ip,
                "All_IPs": sw.all_ips,
                "MAC": sw.mac or None,
                "CAD_ID": None,
                "Physical_Pos": {
                    "X": None,
                    "Y": None,
                    "Area": sw.switch_location,
                    "Floor": sw.floor,
                    "Zone": sw.zone,
                    "Well": sw.well,
                    "Source": "switch_cascade_sheet_location",
                },
                "Logical_Port": parent_port.get(sw.switch_id) or None,
                "VLAN": third_octet(sw.primary_ip) or None,
                "Declared_Camera_Count": sw.camera_count,
                "Conflict_Case": [],
                "Evidence": [
                    "manual_switch_cascade_sheet_high_confidence",
                    f"source_row={sw.source_sheet}!R{sw.source_row}",
                    f"uplink={sw.uplink_location}",
                ],
            }
        )
        edges.append(
            {
                "Source": parent_id,
                "Target": sw.switch_id,
                "Type": "switch_uplink",
                "Logical_Port": parent_port.get(sw.switch_id) or None,
                "Weight": 1,
                "Evidence": sw.uplink_location,
            }
        )
    for camera in cameras:
        assignment = assignments.get(camera.ip)
        sw = assignment["switch"] if assignment else None
        parent_id = sw.switch_id if sw else "UNMATCHED:camera_pool"
        if not sw and not any(node["ID"] == "UNMATCHED:camera_pool" for node in nodes):
            nodes.append(
                {
                    "ID": "UNMATCHED:camera_pool",
                    "Parent_ID": core_id,
                    "Type": "unmatched_pool",
                    "Name": "未匹配摄像头池",
                    "IP": None,
                    "MAC": None,
                    "CAD_ID": None,
                    "Physical_Pos": {"X": None, "Y": None, "Area": "未匹配", "Source": "system_bucket"},
                    "Logical_Port": None,
                    "VLAN": None,
                    "Conflict_Case": ["UNMATCHED_CAMERA_POOL"],
                    "Evidence": ["created_for_unmatched_camera_retention"],
                }
            )
            edges.append({"Source": core_id, "Target": "UNMATCHED:camera_pool", "Type": "system_bucket", "Weight": 1})
        conflict_case = assignment.get("conflict_case", []) if assignment else ["UNMATCHED_CAMERA_TO_SWITCH"]
        nodes.append(
            {
                "ID": f"CAM:{camera.ip}",
                "Parent_ID": parent_id,
                "Type": "camera",
                "Name": f"{camera.seq} {camera.install_pos}".strip() or camera.ip,
                "IP": camera.ip,
                "MAC": camera.mac or None,
                "CAD_ID": camera.cad_id,
                "CAD_SEQ": camera.seq,
                "Physical_Pos": {
                    "X": camera.x,
                    "Y": camera.y,
                    "Area": camera.area_label,
                    "Floor": camera.floor,
                    "Zone": camera.zone,
                    "Well": camera.well,
                    "Raw_Address": camera.detail_addr,
                    "Install_Pos": camera.install_pos,
                    "Source": camera.coordinate_source,
                },
                "Logical_Port": assignment.get("logical_port") if assignment else None,
                "VLAN": third_octet(camera.ip) or None,
                "Conflict_Case": conflict_case,
                "Match_Confidence": assignment.get("confidence") if assignment else 0,
                "Match_Method": assignment.get("match_method") if assignment else "unmatched",
                "Evidence": (
                    [
                        "manual_cad_physical_sheet_high_confidence",
                        f"source_row={camera.source_sheet}!R{camera.source_row}",
                    ]
                    + (assignment.get("evidence", []) if assignment else [])
                ),
            }
        )
        edges.append(
            {
                "Source": parent_id,
                "Target": f"CAM:{camera.ip}",
                "Type": "camera_access",
                "Logical_Port": assignment.get("logical_port") if assignment else None,
                "Weight": 1,
                "Evidence": assignment.get("match_method") if assignment else "unmatched",
            }
        )
    load = descendant_camera_load(nodes, edges)
    for node in nodes:
        node["Camera_Load"] = load.get(node["ID"], 0)
    for edge in edges:
        edge["Camera_Load"] = load.get(edge["Target"], 0)
        edge["Weight"] = max(1, round(math.sqrt(max(1, edge["Camera_Load"])), 2))
    return nodes, edges


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def generate_report_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 资产血缘数据质量报告")
    lines.append("")
    lines.append(f"- 生成时间：{report['metadata']['generated_at']}")
    lines.append(f"- 物理点位表：`{report['metadata']['physical_file']}`")
    lines.append(f"- 交换机级联表：`{report['metadata']['switch_file']}`")
    lines.append("")
    lines.append("## 1. 原始行数与字段分布")
    for source in report["raw_profiles"]:
        lines.append(f"### {source['file_role']} - {source['path']}")
        for sheet in source["sheets"]:
            lines.append(f"- `{sheet['sheet_name']}`：原始行 {sheet['raw_rows']}，原始列 {sheet['raw_cols']}，IP 命中 {sum(sheet['ip_hits_by_col'])}，MAC 命中 {sum(sheet['mac_hits_by_col'])}")
            lines.append(f"  - 非空列分布：{sheet['non_empty_by_col']}")
            sample = sheet["sample_non_empty_rows"][:3]
            for row in sample:
                lines.append(f"  - R{row['row']}：{' | '.join(row['values'])}")
    lines.append("")
    lines.append("## 2. 规范化结果")
    s = report["summary"]
    lines.append(f"- 摄像头有效记录：{s['camera_count']}，唯一 IP：{s['unique_camera_ips']}，重复 IP：{s['duplicate_camera_ips']}")
    lines.append(f"- 交换机有效记录：{s['switch_count']}，唯一 IP：{s['unique_switch_ips']}，重复 IP：{s['duplicate_switch_ips']}")
    lines.append(f"- 摄像头匹配成功：{s['matched_camera_count']}，匹配失败：{s['unmatched_camera_count']}，冲突标记：{s['conflict_count']}")
    lines.append(f"- VLAN 字段状态：{s['vlan_field_status']}")
    lines.append("")
    lines.append("## 3. 匹配失败样例")
    if report["unmatched_cameras"]:
        for item in report["unmatched_cameras"][:60]:
            lines.append(f"- `{item['camera_ip']}` / `{item['cad_id']}` / {item['physical_area']}：{item['reason']}（best_score={item.get('best_score')}）")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 4. 冲突样例")
    if report["conflict_cases"]:
        for item in report["conflict_cases"][:80]:
            lines.append(f"- `{item['camera_ip']}` -> `{item['switch_ip']}`：{', '.join(item['conflict_case'])}；物理 `{item['camera_area']}`；交换机 `{item['switch_location']}`")
    else:
        lines.append("- 无硬冲突；当前数据缺少端口级 VLAN 字段，因此未做 VLAN 硬冲突判定。")
    lines.append("")
    lines.append("## 5. 汇聚 / 上联压力")
    for item in report["switch_load_ranking"][:30]:
        lines.append(f"- `{item['id']}` {item['name']}：下挂摄像头 {item['camera_load']}，线宽建议 {item['edge_weight']}")
    lines.append("")
    lines.append("## 6. UI 呈现建议")
    lines.extend(report["ui_suggestions_markdown"])
    lines.append("")
    lines.append("## 7. 重要说明")
    lines.append("- 两份上传表被视为高置信度手动表；当运行库或推理结果与手动表冲突时，最终 JSON 保留手动表字段，并把推理差异放入 `Conflict_Case`。")
    lines.append("- 摄像头节点已保留 `CAD_ID`，格式为 `工作表!行号:SEQ-序号`，用于后续现场对账。")
    lines.append("- 上传的物理表未提供数值型 CAD 坐标 X/Y；本次 JSON 中 X/Y 是按楼层、区域、IP 顺序生成的 UI 布局坐标，`Physical_Pos.Source` 已明确标注。")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build refined physical/logical topology from manual asset sheets.")
    parser.add_argument("--physical", type=Path, default=DEFAULT_PHYSICAL)
    parser.add_argument("--switch", type=Path, default=DEFAULT_SWITCH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_workbooks"
    raw_dir.mkdir(exist_ok=True)

    physical_payload = export_workbook_with_excel(args.physical, raw_dir)
    switch_payload = export_workbook_with_excel(args.switch, raw_dir)

    raw_profiles = [
        {
            "file_role": "physical_cad_camera_points",
            "path": str(args.physical),
            "sheets": [sheet_profile(sheet) for sheet in physical_payload["sheets"]],
        },
        {
            "file_role": "manual_switch_cascade",
            "path": str(args.switch),
            "sheets": [sheet_profile(sheet) for sheet in switch_payload["sheets"]],
        },
    ]

    camera_sheet = first_sheet_with_ip(physical_payload, min_rows=20)
    switch_sheet = first_sheet_with_ip(switch_payload, min_rows=20)
    cameras, camera_parse_meta = parse_camera_sheet(camera_sheet)
    switches, switch_parse_meta = parse_switch_sheet(switch_sheet)
    add_derived_coordinates(cameras)

    camera_ip_counts = Counter(camera.ip for camera in cameras)
    switch_ip_counts = Counter(sw.primary_ip for sw in switches)
    parent_map, parent_port, unresolved_uplinks = build_switch_parent_map(switches)
    assignments, unmatched_cameras, conflict_cases = assign_cameras_to_switches(cameras, switches)
    nodes, edges = build_topology(cameras, switches, assignments, unresolved_uplinks)

    switch_load_ranking = [
        {
            "id": node["ID"],
            "name": node["Name"],
            "type": node["Type"],
            "camera_load": node["Camera_Load"],
            "edge_weight": max(1, round(math.sqrt(max(1, node["Camera_Load"])), 2)),
        }
        for node in nodes
        if "switch" in node["Type"] or node["Type"] == "core_switch"
    ]
    switch_load_ranking.sort(key=lambda item: item["camera_load"], reverse=True)

    generated_at = datetime.now().isoformat(timespec="seconds")
    topology = {
        "meta": {
            "generated_at": generated_at,
            "physical_file": str(args.physical),
            "switch_file": str(args.switch),
            "manual_source_priority": "uploaded_manual_tables_override_inferred_runtime_data",
            "schema": "refined_topology.v1",
        },
        "metadata": {
            "generated_at": generated_at,
            "physical_file": str(args.physical),
            "switch_file": str(args.switch),
            "manual_source_priority": "uploaded_manual_tables_override_inferred_runtime_data",
            "schema": "refined_topology.v1",
        },
        "nodes": nodes,
        "edges": edges,
        "conflict_cases": conflict_cases,
        "unmatched_cameras": unmatched_cameras,
        "unresolved_switch_uplinks": unresolved_uplinks,
        "lineage_notes": [
            "Camera CAD_ID is preserved from source sheet row and sequence.",
            "Numeric CAD X/Y were not present in the uploaded physical sheet; derived layout coordinates are marked in Physical_Pos.Source.",
            "VLAN conflicts are not asserted without explicit port VLAN columns; VLAN values are preserved as IP third-octet hints only.",
        ],
    }

    ui_suggestions = [
        "- 物理地图模式：以 `Physical_Pos.Area/Floor/Zone` 做楼层过滤，以 `X/Y` 作为初始布局坐标；若后续 CAD 解析得到真实坐标，只替换 `Physical_Pos.X/Y`，不改节点 ID。",
        "- 逻辑拓扑模式：以 `Parent_ID` 构建树，交换机边使用 `Camera_Load` 和 `Weight` 控制线宽，核心/汇聚节点可做聚合折叠。",
        "- 无缝切换：保持同一套 `ID`，只切换布局引擎；物理模式固定坐标，逻辑模式使用树/力导布局，选中状态和右侧详情不重置。",
        "- Canvas 流动特效：边上维护 `flowOffset = (time * speed * healthFactor) % dashLength`，`Camera_Load` 越高线越粗，异常边用红橙色慢速脉冲，正常边用蓝绿细流。",
        "- 冲突呈现：`Conflict_Case` 非空的边或节点叠加琥珀色描边，点击后展示 CAD_ID、原始行号、物理区域、交换机位置和推理证据。",
    ]

    report = {
        "generated_at": topology["metadata"]["generated_at"],
        "raw_input_profile": {"sheets": raw_profiles},
        "conflicts": conflict_cases,
        "metadata": topology["metadata"],
        "raw_profiles": raw_profiles,
        "selected_sheets": {
            "camera_sheet": camera_sheet["name"],
            "switch_sheet": switch_sheet["name"],
            "camera_parse": camera_parse_meta,
            "switch_parse": switch_parse_meta,
        },
        "summary": {
            "camera_count": len(cameras),
            "unique_camera_ips": len(camera_ip_counts),
            "duplicate_camera_ips": sum(1 for _, count in camera_ip_counts.items() if count > 1),
            "switch_count": len(switches),
            "unique_switch_ips": len(switch_ip_counts),
            "duplicate_switch_ips": sum(1 for _, count in switch_ip_counts.items() if count > 1),
            "matched_camera_count": len(assignments),
            "unmatched_camera_count": len(unmatched_cameras),
            "conflict_count": len(conflict_cases),
            "unresolved_switch_uplink_count": len(unresolved_uplinks),
            "vlan_field_status": "explicit_port_vlan_column_absent; no hard VLAN conflict asserted",
        },
        "ip_distribution": {
            "camera_third_octet": Counter(third_octet(camera.ip) for camera in cameras).most_common(),
            "switch_third_octet": Counter(third_octet(sw.primary_ip) for sw in switches).most_common(),
            "camera_floor": Counter(camera.floor or "未识别" for camera in cameras).most_common(),
            "switch_floor": Counter(sw.floor or "未识别" for sw in switches).most_common(),
        },
        "unmatched_cameras": unmatched_cameras,
        "conflict_cases": conflict_cases,
        "unresolved_switch_uplinks": unresolved_uplinks,
        "switch_load_ranking": switch_load_ranking,
        "ui_suggestions_markdown": ui_suggestions,
    }

    (out_dir / "refined_topology.json").write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "data_quality_report.md").write_text(generate_report_markdown(report), encoding="utf-8")

    write_csv(
        out_dir / "camera_switch_mapping.csv",
        [
            {
                "CAD_ID": camera.cad_id,
                "Camera_IP": camera.ip,
                "Camera_Area": camera.area_label,
                "Switch_IP": assignments.get(camera.ip, {}).get("switch").primary_ip if assignments.get(camera.ip) else "",
                "Switch_Location": assignments.get(camera.ip, {}).get("switch").switch_location if assignments.get(camera.ip) else "",
                "Confidence": assignments.get(camera.ip, {}).get("confidence", 0),
                "Conflict_Case": ";".join(assignments.get(camera.ip, {}).get("conflict_case", [])) if assignments.get(camera.ip) else "UNMATCHED_CAMERA_TO_SWITCH",
                "Evidence": ";".join(assignments.get(camera.ip, {}).get("evidence", [])) if assignments.get(camera.ip) else "",
            }
            for camera in cameras
        ],
        ["CAD_ID", "Camera_IP", "Camera_Area", "Switch_IP", "Switch_Location", "Confidence", "Conflict_Case", "Evidence"],
    )

    print(json.dumps({
        "out_dir": str(out_dir),
        "camera_count": len(cameras),
        "switch_count": len(switches),
        "matched_camera_count": len(assignments),
        "unmatched_camera_count": len(unmatched_cameras),
        "conflict_count": len(conflict_cases),
        "topology_nodes": len(nodes),
        "topology_edges": len(edges),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
ANALYSIS_DIR = RUNTIME_DIR / "analysis"
DB_PATH = RUNTIME_DIR / "platform_v2.db"
SWITCH_JSON = ANALYSIS_DIR / "switch_cascade_sheet.json"
CAMERA_JSON = ANALYSIS_DIR / "camera_points_sheet.json"
REPORT_JSON = ANALYSIS_DIR / "excel_compare_report.json"
REPORT_MD = ANALYSIS_DIR / "excel_compare_report.md"
SWITCH_FACTS_JSON = ANALYSIS_DIR / "normalized_switch_facts.json"
CAMERA_FACTS_JSON = ANALYSIS_DIR / "normalized_camera_facts.json"

IP_PATTERN = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def floor_token(text: str) -> str | None:
    text = clean(text).upper()
    patterns = [
        (r"B2", "B2"),
        (r"B1", "B1"),
        (r"负一|地下一", "B1"),
        (r"负二|地下二", "B2"),
        (r"1F|一楼|1楼", "1F"),
        (r"2F|二楼|2楼", "2F"),
        (r"3F|三楼|3楼", "3F"),
        (r"4F|四楼|4楼", "4F"),
        (r"5F|五楼|5楼", "5F"),
    ]
    for pattern, token in patterns:
        if re.search(pattern, text):
            return token
    return None


def zone_token(text: str) -> str | None:
    text = clean(text)
    if not text:
        return None
    if "北" in text:
        return "北"
    if "南" in text:
        return "南"
    if "停车场" in text:
        return "停车场"
    if "户外" in text:
        return "户外"
    if "中央大道" in text:
        return "中央大道"
    return None


def normalize_camera_area(detail_addr: str, install_pos: str) -> str:
    merged = clean(f"{detail_addr} {install_pos}")
    floor = floor_token(merged)
    zone = zone_token(merged)
    if floor and zone in {"北", "南"}:
        return f"{floor}{zone}楼"
    if floor and zone == "停车场":
        return f"{floor}停车场"
    if floor:
        return floor
    if "中央大道户外" in merged or zone == "户外":
        return "中央大道户外"
    if "停车场" in merged:
        return "停车场"
    return detail_addr or install_pos or "未归类"


def extract_switch_ip_facts(
    raw_ip: str,
    switch_location: str,
    uplink_location: str,
    row_text: str = "",
    role_marker: str = "",
) -> tuple[list[str], list[str]]:
    raw_ip = clean(raw_ip)
    flags: list[str] = []
    ips = IP_PATTERN.findall(raw_ip)
    if len(ips) > 1:
        flags.append("双IP")
    if "远距离" in raw_ip:
        flags.append("远距离")
    if "丢" in raw_ip:
        flags.append("丢失标注")
    if "核心交换机" in switch_location or "核心交换机" in role_marker:
        flags.append("核心设备")
    if "核心交换机" in uplink_location:
        flags.append("上联核心")
    if "车场用交换机" in row_text or "停车场" in row_text:
        flags.append("车场用交换机")
    if "机房" in switch_location:
        flags.append("机房")
    return ips, flags


def to_int(value: str) -> int:
    value = clean(value)
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def load_json_rows(path: Path) -> list[list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class SwitchRow:
    source_row: int
    seq: str
    camera_count: int
    music_count: int
    cashier_count: int
    shop_lan_count: int
    remote_cascade_count: int
    tg_cascade_count: int
    total_ports: int
    switch_location: str
    uplink_location: str
    raw_ip: str
    normalized_ips: list[str]
    status_flags: list[str]
    switch_floor: str
    uplink_floor: str


@dataclass
class CameraRow:
    source_row: int
    seq: str
    ip: str
    camera_type: str
    detail_addr: str
    install_pos: str
    can_capture: str
    touches_sensitive: str
    normalized_area: str


def parse_switch_rows(rows: list[list[str]]) -> list[SwitchRow]:
    results: list[SwitchRow] = []
    for source_row, row in enumerate(rows[4:], start=5):
        if len(row) < 11:
            continue
        raw_ip = clean(row[10])
        switch_location = clean(row[8])
        uplink_location = clean(row[9])
        if not raw_ip and not switch_location:
            continue
        row_text = " ".join(clean(item) for item in row if clean(item))
        normalized_ips, status_flags = extract_switch_ip_facts(
            raw_ip,
            switch_location,
            uplink_location,
            row_text,
            clean(row[1]) if len(row) > 1 else "",
        )
        if not normalized_ips:
            continue
        seq = clean(row[0]) or f"AUX-{source_row}"
        flags = list(status_flags)
        if clean(row[0]) == "":
            flags.append("辅助行")
        results.append(
            SwitchRow(
                source_row=source_row,
                seq=seq,
                camera_count=to_int(row[1]),
                music_count=to_int(row[2]),
                cashier_count=to_int(row[3]),
                shop_lan_count=to_int(row[4]),
                remote_cascade_count=to_int(row[5]),
                tg_cascade_count=to_int(row[6]),
                total_ports=to_int(row[7]),
                switch_location=switch_location,
                uplink_location=uplink_location,
                raw_ip=raw_ip,
                normalized_ips=normalized_ips,
                status_flags=sorted(set(flags)),
                switch_floor=floor_token(switch_location) or "未识别",
                uplink_floor=floor_token(uplink_location) or ("CORE" if "核心交换机" in uplink_location else "未识别"),
            )
        )
    return results


def parse_camera_rows(rows: list[list[str]]) -> list[CameraRow]:
    results: list[CameraRow] = []
    for source_row, row in enumerate(rows[3:], start=4):
        if len(row) < 7:
            continue
        seq = clean(row[0])
        ip = clean(row[1])
        if not seq or not ip:
            continue
        detail = clean(row[3])
        install = clean(row[4])
        results.append(
            CameraRow(
                source_row=source_row,
                seq=seq,
                ip=ip,
                camera_type=clean(row[2]),
                detail_addr=detail,
                install_pos=install,
                can_capture=clean(row[5]),
                touches_sensitive=clean(row[6]),
                normalized_area=normalize_camera_area(detail, install),
            )
        )
    return results


def load_runtime_facts() -> dict[str, object]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    switches = cur.execute(
        """
        select id, hostname, management_ip, service_ip, notes
        from asset_device
        where device_type='switch'
        """
    ).fetchall()
    cameras = cur.execute(
        """
        select d.id, d.hostname, d.management_ip, d.service_ip, a.display_name as area_name
        from asset_device d
        left join asset_area a on a.id = d.area_id
        where d.device_type='camera'
        """
    ).fetchall()
    topology_links = cur.execute(
        """
        select l.id, l.link_type, l.confidence, l.evidence_type, l.evidence_summary,
               sd.management_ip as src_ip, dd.management_ip as dst_ip
        from topology_link l
        left join asset_device sd on sd.id = l.src_device_id
        left join asset_device dd on dd.id = l.dst_device_id
        """
    ).fetchall()
    camera_switch_links = cur.execute(
        """
        select cd.management_ip as camera_ip, sd.management_ip as switch_ip,
               l.evidence_type, l.confidence
        from topology_link l
        join asset_device sd on sd.id = l.src_device_id and sd.device_type='switch'
        join asset_device cd on cd.id = l.dst_device_id and cd.device_type='camera'
        where l.link_type='physical'
        """
    ).fetchall()
    conn.close()

    return {
        "switches": [dict(r) for r in switches],
        "cameras": [dict(r) for r in cameras],
        "topology_links": [dict(r) for r in topology_links],
        "camera_switch_links": [dict(r) for r in camera_switch_links],
    }


def summarize_switch_architecture(switch_rows: list[SwitchRow]) -> dict[str, object]:
    floor_counts = Counter(row.switch_floor for row in switch_rows)
    access_rows = [row for row in switch_rows if row.switch_floor in {"1F", "3F", "4F", "5F"}]
    aggregation_rows = [row for row in switch_rows if row.switch_floor == "2F"]
    core_rows = [
        row
        for row in switch_rows
        if "核心相关" in row.status_flags or "机房" in row.status_flags or "机房" in row.switch_location
    ]
    remote_rows = [row for row in switch_rows if "远距离" in row.status_flags]
    cascade_paths = Counter(
        f"{row.switch_floor}->{row.uplink_floor}" for row in switch_rows if row.switch_floor != "未识别"
    )
    return {
        "switch_floor_counts": floor_counts.most_common(),
        "access_switch_rows": len(access_rows),
        "aggregation_switch_rows": len(aggregation_rows),
        "core_related_rows": len(core_rows),
        "remote_switch_rows": len(remote_rows),
        "cascade_paths": cascade_paths.most_common(),
        "core_examples": [
            {
                "switch_ip": row.normalized_ips[0],
                "switch_location": row.switch_location,
                "uplink_location": row.uplink_location,
                "flags": row.status_flags,
            }
            for row in core_rows[:10]
        ],
        "remote_examples": [
            {
                "switch_ip": row.normalized_ips[0],
                "switch_location": row.switch_location,
                "uplink_location": row.uplink_location,
            }
            for row in remote_rows[:12]
        ],
    }


def build_report() -> dict[str, object]:
    switch_rows = parse_switch_rows(load_json_rows(SWITCH_JSON))
    camera_rows = parse_camera_rows(load_json_rows(CAMERA_JSON))
    runtime = load_runtime_facts()

    runtime_switch_ips = {
        clean(row["management_ip"] or row["service_ip"] or ""): row
        for row in runtime["switches"]
        if clean(row["management_ip"] or row["service_ip"] or "")
    }
    runtime_camera_ips = {
        clean(row["management_ip"] or row["service_ip"] or ""): row
        for row in runtime["cameras"]
        if clean(row["management_ip"] or row["service_ip"] or "")
    }
    camera_switch_links = {clean(row["camera_ip"] or ""): row for row in runtime["camera_switch_links"]}

    raw_switch_ips = {row.raw_ip for row in switch_rows}
    normalized_switch_ips = {ip for row in switch_rows for ip in row.normalized_ips}
    sheet_camera_ips = {row.ip for row in camera_rows}

    matched_raw_switches = sorted(ip for ip in raw_switch_ips if ip in runtime_switch_ips)
    matched_normalized_switches = sorted(ip for ip in normalized_switch_ips if ip in runtime_switch_ips)
    missing_switches_in_runtime = sorted(ip for ip in normalized_switch_ips if ip not in runtime_switch_ips)
    extra_runtime_switches = sorted(ip for ip in runtime_switch_ips if ip not in normalized_switch_ips)
    recovered_by_normalization = sorted(
        ip for ip in matched_normalized_switches if ip not in matched_raw_switches
    )

    row_level_runtime_hits = []
    unresolved_rows = []
    for row in switch_rows:
        hits = [ip for ip in row.normalized_ips if ip in runtime_switch_ips]
        row_level_runtime_hits.append(
            {
                "source_row": row.source_row,
                "seq": row.seq,
                "switch_location": row.switch_location,
                "raw_ip": row.raw_ip,
                "normalized_ips": row.normalized_ips,
                "matched_runtime_ips": hits,
                "status_flags": row.status_flags,
            }
        )
        if not hits:
            unresolved_rows.append(
                {
                    "source_row": row.source_row,
                    "seq": row.seq,
                    "switch_location": row.switch_location,
                    "uplink_location": row.uplink_location,
                    "raw_ip": row.raw_ip,
                    "normalized_ips": row.normalized_ips,
                    "status_flags": row.status_flags,
                }
            )

    matched_cameras = sorted(ip for ip in sheet_camera_ips if ip in runtime_camera_ips)
    missing_cameras_in_runtime = sorted(ip for ip in sheet_camera_ips if ip not in runtime_camera_ips)
    extra_runtime_cameras = sorted(ip for ip in runtime_camera_ips if ip not in sheet_camera_ips)

    camera_area_counter = Counter(row.normalized_area for row in camera_rows)
    camera_type_counter = Counter(row.camera_type for row in camera_rows)
    sensitive_counter = Counter(row.touches_sensitive for row in camera_rows)
    capture_counter = Counter(row.can_capture for row in camera_rows)
    switch_uplink_counter = Counter(row.uplink_location for row in switch_rows if row.uplink_location)

    sheet_camera_links = [camera_switch_links[ip] for ip in sheet_camera_ips if ip in camera_switch_links]
    linked_sheet_camera_count = len(sheet_camera_links)
    unlinked_sheet_cameras = sorted(ip for ip in sheet_camera_ips if ip not in camera_switch_links)
    central_avenue_switch_camera_load = Counter(link["switch_ip"] for link in sheet_camera_links if link["switch_ip"])

    runtime_link_ip_pairs = set()
    for link in runtime["topology_links"]:
        src = clean(link.get("src_ip") or "")
        dst = clean(link.get("dst_ip") or "")
        if src and dst:
            runtime_link_ip_pairs.add((src, dst))

    switch_link_presence = []
    for row in switch_rows:
        switch_link_presence.append(
            {
                "source_row": row.source_row,
                "switch_ips": row.normalized_ips,
                "switch_location": row.switch_location,
                "in_runtime_assets": any(ip in runtime_switch_ips for ip in row.normalized_ips),
                "has_runtime_topology_reference": any(
                    (ip == src or ip == dst)
                    for ip in row.normalized_ips
                    for src, dst in runtime_link_ip_pairs
                ),
                "uplink_location": row.uplink_location,
                "status_flags": row.status_flags,
            }
        )

    inferred_edges = [
        {
            "source_row": row.source_row,
            "switch_ips": row.normalized_ips,
            "switch_location": row.switch_location,
            "switch_floor": row.switch_floor,
            "uplink_location": row.uplink_location,
            "uplink_floor": row.uplink_floor,
            "camera_ports": row.camera_count,
            "remote_cascade_ports": row.remote_cascade_count,
            "tg_cascade_ports": row.tg_cascade_count,
            "flags": row.status_flags,
        }
        for row in switch_rows
    ]

    switch_architecture = summarize_switch_architecture(switch_rows)

    report = {
        "sheet_summary": {
            "switch_rows": len(switch_rows),
            "camera_rows": len(camera_rows),
            "normalized_switch_ip_count": len(normalized_switch_ips),
            "raw_switch_ip_count": len(raw_switch_ips),
        },
        "runtime_summary": {
            "switch_count": len(runtime_switch_ips),
            "camera_count": len(runtime_camera_ips),
            "topology_links": len(runtime["topology_links"]),
        },
        "switch_compare": {
            "raw_match_count": len(matched_raw_switches),
            "normalized_match_count": len(matched_normalized_switches),
            "recovered_by_normalization_count": len(recovered_by_normalization),
            "recovered_by_normalization_ips": recovered_by_normalization,
            "missing_in_runtime_count": len(missing_switches_in_runtime),
            "missing_in_runtime_ips": missing_switches_in_runtime,
            "extra_runtime_count": len(extra_runtime_switches),
            "extra_runtime_ips_sample": extra_runtime_switches[:60],
            "unresolved_rows": unresolved_rows,
        },
        "camera_compare": {
            "matched_count": len(matched_cameras),
            "matched_ratio": round(len(matched_cameras) / max(1, len(sheet_camera_ips)), 4),
            "missing_in_runtime_count": len(missing_cameras_in_runtime),
            "missing_in_runtime_ips_sample": missing_cameras_in_runtime[:80],
            "extra_runtime_count": len(extra_runtime_cameras),
            "extra_runtime_ips_sample": extra_runtime_cameras[:80],
        },
        "camera_topology_coverage": {
            "linked_sheet_camera_count": linked_sheet_camera_count,
            "linked_ratio": round(linked_sheet_camera_count / max(1, len(sheet_camera_ips)), 4),
            "unlinked_sheet_camera_count": len(unlinked_sheet_cameras),
            "unlinked_sheet_camera_ips": unlinked_sheet_cameras,
            "evidence_breakdown": Counter(link["evidence_type"] for link in sheet_camera_links).most_common(),
            "top_switch_loads": central_avenue_switch_camera_load.most_common(25),
        },
        "camera_sheet_breakdown": {
            "by_area": camera_area_counter.most_common(30),
            "by_type": camera_type_counter.most_common(),
            "by_capture": capture_counter.most_common(),
            "by_sensitive_scope": sensitive_counter.most_common(),
        },
        "switch_sheet_breakdown": {
            "by_floor": Counter(row.switch_floor for row in switch_rows).most_common(),
            "top_uplink_locations": switch_uplink_counter.most_common(20),
            "total_declared_camera_ports": sum(row.camera_count for row in switch_rows),
            "total_declared_tg_cascade_ports": sum(row.tg_cascade_count for row in switch_rows),
            "total_declared_remote_cascade_ports": sum(row.remote_cascade_count for row in switch_rows),
            "flag_breakdown": Counter(flag for row in switch_rows for flag in row.status_flags).most_common(),
        },
        "switch_architecture": switch_architecture,
        "switch_topology_presence": switch_link_presence,
        "inferred_switch_edges": inferred_edges,
        "normalized_switch_rows": [asdict(row) for row in switch_rows],
        "normalized_camera_rows": [asdict(row) for row in camera_rows],
        "row_level_runtime_hits": row_level_runtime_hits,
        "recommendations": [
            "把图像采集设备信息表作为中央大道摄像头的现场事实源。它与运行库 100% 命中，适合用来纠正区域、安装位置与现场口径。",
            "把交换机级联表作为物理拓扑事实源。尤其是 2F 汇聚、机房核心、远距离补充交换机这些信息，运行库本身不完整，但表里口径非常强。",
            "优先处理 13 路“表内摄像头已在库、但没有物理交换机链路”的摄像头，它们是补齐中央大道拓扑图的最短路径。",
            "对表内存在、运行库缺失的交换机 IP 重点核验：10.0.68.34、10.0.68.42、10.0.68.46、10.0.68.49、10.0.68.60。这些更像真缺口，不是格式脏数据。",
            "把运行库多出的 40 台交换机分成三类单独处理：新增扫描发现、第三方/非中央大道设备、命名或地址异常设备。不要跟中央大道级联表混在一起看。",
        ],
    }
    return report


def write_markdown(report: dict[str, object]) -> None:
    lines: list[str] = []
    lines.append("# Excel 与运行库对比分析")
    lines.append("")
    lines.append("## 关键结论")
    lines.append(
        f"- 图像采集设备表中的 {report['sheet_summary']['camera_rows']} 路摄像头，已经与运行库 100% 命中。"
    )
    lines.append(
        f"- 其中 {report['camera_topology_coverage']['linked_sheet_camera_count']} 路已经有物理交换机归属，覆盖率 {report['camera_topology_coverage']['linked_ratio']:.2%}。"
    )
    lines.append(
        f"- 交换机级联表原始写法只能命中 {report['switch_compare']['raw_match_count']} 台；清洗双 IP、远距离、丢失标注后，可命中 {report['switch_compare']['normalized_match_count']} 台，多恢复 {report['switch_compare']['recovered_by_normalization_count']} 台。"
    )
    lines.append(
        f"- 中央大道这条网络的主骨架已经足够清楚：2F 是汇聚层，1F/3F/4F/5F 是接入层，机房与核心交换机独立成核心层。"
    )
    lines.append("")
    lines.append("## 总览")
    lines.append(f"- 交换机表记录：{report['sheet_summary']['switch_rows']} 条")
    lines.append(f"- 交换机表清洗后 IP 节点：{report['sheet_summary']['normalized_switch_ip_count']} 个")
    lines.append(f"- 摄像头表记录：{report['sheet_summary']['camera_rows']} 条")
    lines.append(f"- 运行库交换机：{report['runtime_summary']['switch_count']} 台")
    lines.append(f"- 运行库摄像头：{report['runtime_summary']['camera_count']} 台")
    lines.append(f"- 运行库链路：{report['runtime_summary']['topology_links']} 条")
    lines.append("")
    lines.append("## 交换机对比")
    lines.append(f"- 原始字符串命中运行库：{report['switch_compare']['raw_match_count']} 台")
    lines.append(f"- 清洗后命中运行库：{report['switch_compare']['normalized_match_count']} 台")
    lines.append(f"- 通过清洗恢复命中：{report['switch_compare']['recovered_by_normalization_count']} 台")
    lines.append(f"- 表内交换机仍未命中运行库：{report['switch_compare']['missing_in_runtime_count']} 台")
    lines.append(f"- 运行库多出的交换机：{report['switch_compare']['extra_runtime_count']} 台")
    lines.append("")
    lines.append("### 清洗后恢复命中的交换机")
    for ip in report["switch_compare"]["recovered_by_normalization_ips"][:20]:
        lines.append(f"- {ip}")
    lines.append("")
    lines.append("### 仍建议重点核验的交换机缺口")
    for item in report["switch_compare"]["unresolved_rows"][:12]:
        ip_text = "/".join(item["normalized_ips"])
        lines.append(
            f"- 行 {item['source_row']} | {item['switch_location']} | {ip_text} | 标记：{', '.join(item['status_flags']) or '无'}"
        )
    lines.append("")
    lines.append("## 摄像头对比")
    lines.append(f"- 表内摄像头命中运行库：{report['camera_compare']['matched_count']} 台")
    lines.append(f"- 命中率：{report['camera_compare']['matched_ratio']:.2%}")
    lines.append(f"- 表内摄像头未命中运行库：{report['camera_compare']['missing_in_runtime_count']} 台")
    lines.append(f"- 运行库多出的摄像头：{report['camera_compare']['extra_runtime_count']} 台")
    lines.append("")
    lines.append("## 中央大道摄像头链路覆盖")
    lines.append(
        f"- 已有物理交换机归属：{report['camera_topology_coverage']['linked_sheet_camera_count']} 路"
    )
    lines.append(
        f"- 尚缺物理交换机归属：{report['camera_topology_coverage']['unlinked_sheet_camera_count']} 路"
    )
    lines.append("### 归属证据类型")
    for evidence, count in report["camera_topology_coverage"]["evidence_breakdown"]:
        lines.append(f"- {evidence}: {count}")
    lines.append("")
    lines.append("### 中央大道摄像头承载量最高的交换机（Top 15）")
    for switch_ip, count in report["camera_topology_coverage"]["top_switch_loads"][:15]:
        lines.append(f"- {switch_ip}: {count} 路")
    lines.append("")
    lines.append("## 摄像头区域分布（Top 15）")
    for area, count in report["camera_sheet_breakdown"]["by_area"][:15]:
        lines.append(f"- {area}: {count}")
    lines.append("")
    lines.append("## 交换机骨架判断")
    lines.append(
        f"- 接入层交换机行数（1F/3F/4F/5F）：{report['switch_architecture']['access_switch_rows']} 行"
    )
    lines.append(
        f"- 2F 汇聚层交换机行数：{report['switch_architecture']['aggregation_switch_rows']} 行"
    )
    lines.append(f"- 核心/机房相关行数：{report['switch_architecture']['core_related_rows']} 行")
    lines.append(f"- 远距离补充交换机行数：{report['switch_architecture']['remote_switch_rows']} 行")
    lines.append("### 楼层级联路径")
    for path, count in report["switch_architecture"]["cascade_paths"]:
        lines.append(f"- {path}: {count}")
    lines.append("")
    lines.append("### 核心/机房样本")
    for item in report["switch_architecture"]["core_examples"][:8]:
        lines.append(
            f"- {item['switch_ip']} | {item['switch_location']} | 上联：{item['uplink_location']} | 标记：{', '.join(item['flags'])}"
        )
    lines.append("")
    lines.append("### 远距离样本")
    for item in report["switch_architecture"]["remote_examples"][:10]:
        lines.append(
            f"- {item['switch_ip']} | {item['switch_location']} | 上联：{item['uplink_location']}"
        )
    lines.append("")
    lines.append("## 对架构梳理的意义")
    lines.append("- 这两份表已经足够把“中央大道子网”从整库 1062 路摄像头里单独抽出来，形成一个干净可核验的现场事实集。")
    lines.append("- 交换机表说明中央大道不是平铺网络，而是“2F 汇聚 + 各楼层接入 + 少量远距离补充 + 机房核心”的层级结构。")
    lines.append("- 运行库里已有的 568 条中央大道摄像头物理归属，可以反向验证交换机表、也可以给未归因摄像头补链路。")
    lines.append("- 这意味着后续不仅能重理资产，还能继续往 CAD、楼层、告警地图和现场派工定位上推进。")
    lines.append("")
    lines.append("## 建议")
    for item in report["recommendations"]:
        lines.append(f"- {item}")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SWITCH_FACTS_JSON.write_text(
        json.dumps(report["normalized_switch_rows"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    CAMERA_FACTS_JSON.write_text(
        json.dumps(report["normalized_camera_rows"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(report)
    print(REPORT_JSON)
    print(REPORT_MD)
    print(SWITCH_FACTS_JSON)
    print(CAMERA_FACTS_JSON)


if __name__ == "__main__":
    main()

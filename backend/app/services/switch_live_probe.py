from __future__ import annotations

import re
import socket
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import AssetDevice, NetworkPort, SwitchLiveProbe, TopologyLink, VideoChannel
from app.services.text_normalize import normalize_text


PROMPT_MARKERS = (b"Telnet>", b"#", b">")
MORE_MARKERS = ("--More--", "-- More --")
CAMERA_IP_RE = re.compile(r"^10\.0\.\d{1,3}\.\d{1,3}$")
ACCESS_PORT_RE = re.compile(r"^(?:gi|ge|fe|fa|te|xe|xg|ethernet)\S*$", re.IGNORECASE)
IAC = 255
DO = 253
DONT = 254
WILL = 251
WONT = 252
SB = 250
SE = 240


@dataclass
class ArpEntry:
    ip: str
    mac: str
    vlan: str
    port_name: str


@dataclass
class MacTableEntry:
    mac: str
    vlan: str
    port_name: str


def _normalize_mac(value: str) -> str:
    text = re.sub(r"[^0-9a-fA-F]", "", value or "").lower()
    if len(text) != 12:
        return ""
    return ":".join(text[index : index + 2] for index in range(0, 12, 2))


def _sanitize_cli_text(value: str) -> str:
    text = value or ""
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = text.replace("\x08", "")
    text = text.replace("\r", "")
    for marker in MORE_MARKERS:
        text = text.replace(marker, "")
    return text


def _is_prompt_line(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return lowered.endswith("#") or lowered.endswith(">") or lowered.startswith("telnet>")


def _looks_like_port(token: str) -> bool:
    text = (token or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"cpu", "router", "eth0", "eth1", "vlan1", "vlan2"}:
        return True
    return bool(re.match(r"^[a-z]{1,4}\d[\w/-]*$", lowered))


def _is_candidate_access_port(port_name: str) -> bool:
    text = (port_name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"cpu", "router"}:
        return False
    if lowered.startswith(("eth", "vlan", "lo", "mgmt")):
        return False
    return bool(ACCESS_PORT_RE.match(text))


def _tcp_probe(host: str, port: int, timeout_seconds: float) -> str:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            elapsed = max(1, int((time.perf_counter() - started) * 1000))
            return f"open:{elapsed}ms"
    except OSError:
        return "closed"


def _telnet_negotiate(chunk: bytes) -> tuple[bytes, bytes]:
    clean = bytearray()
    replies = bytearray()
    index = 0
    while index < len(chunk):
        byte = chunk[index]
        if byte != IAC:
            clean.append(byte)
            index += 1
            continue
        if index + 1 >= len(chunk):
            break
        command = chunk[index + 1]
        if command == IAC:
            clean.append(IAC)
            index += 2
            continue
        if command in (DO, DONT, WILL, WONT):
            if index + 2 >= len(chunk):
                break
            option = chunk[index + 2]
            if command in (DO, DONT):
                replies.extend(bytes([IAC, WONT, option]))
            else:
                replies.extend(bytes([IAC, DONT, option]))
            index += 3
            continue
        if command == SB:
            end = chunk.find(bytes([IAC, SE]), index + 2)
            if end == -1:
                break
            index = end + 2
            continue
        index += 2
    return bytes(clean), bytes(replies)


class RawTelnetSession:
    def __init__(self, host: str, timeout_seconds: float):
        self.sock = socket.create_connection((host, 23), timeout=timeout_seconds)
        self.sock.settimeout(timeout_seconds)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def write_line(self, command: str) -> None:
        self.sock.sendall(command.encode("utf-8", errors="ignore") + b"\n")

    def write_raw(self, payload: bytes) -> None:
        self.sock.sendall(payload)

    def read_until_prompt(self, timeout_seconds: float) -> str:
        chunks: list[bytes] = []
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            clean, replies = _telnet_negotiate(chunk)
            if replies:
                self.sock.sendall(replies)
            if not clean:
                continue
            chunks.append(clean)
            joined = b"".join(chunks)
            if any(marker in joined for marker in PROMPT_MARKERS):
                break
            if b"Username:" in joined or b"Password:" in joined or b"login:" in joined:
                break
            if any(marker.encode("utf-8") in joined for marker in MORE_MARKERS):
                break
        return b"".join(chunks).decode("utf-8", errors="ignore")


def _send_command(session: RawTelnetSession, command: str, timeout_seconds: float) -> str:
    session.write_line(command)
    output = session.read_until_prompt(timeout_seconds)
    page_safety = 0
    while any(marker in output for marker in MORE_MARKERS) and page_safety < 120:
        for marker in MORE_MARKERS:
            output = output.replace(marker, "")
        session.write_raw(b" ")
        output += session.read_until_prompt(timeout_seconds)
        page_safety += 1
    return _sanitize_cli_text(output)


def _run_telnet_session(host: str, username: str, password: str, timeout_seconds: float) -> tuple[str, str, str]:
    session = RawTelnetSession(host, timeout_seconds)
    try:
        banner = session.read_until_prompt(timeout_seconds)
        if not banner.strip():
            session.write_line("")
            banner = session.read_until_prompt(timeout_seconds)
        for _ in range(6):
            lowered = banner.lower()
            if "username:" in lowered or "login:" in lowered:
                session.write_line(username)
                banner = session.read_until_prompt(timeout_seconds)
                continue
            if "password:" in lowered:
                session.write_line(password)
                banner = session.read_until_prompt(timeout_seconds)
                continue
            if any(marker in lowered for marker in ("telnet>", "#", ">")):
                break
            time.sleep(0.2)
            banner += session.read_until_prompt(timeout_seconds)
        if banner.strip().endswith(">") and not banner.strip().lower().startswith("telnet>"):
            enable_output = _send_command(session, "enable", timeout_seconds)
            if "#" in enable_output:
                banner = enable_output
        _send_command(session, "terminal no length", timeout_seconds)
        version_output = _send_command(session, "show version", timeout_seconds)
        arp_output = _send_command(session, "show ip arp", timeout_seconds)
        if "unknown command" in arp_output.lower():
            arp_output = _send_command(session, "show arp", timeout_seconds)
        if "unknown command" in arp_output.lower() or "command incomplete" in arp_output.lower():
            arp_output = _send_command(session, "show arp dynamic", timeout_seconds)
        l2_output = _send_command(session, "show l2 mac", timeout_seconds)
        if "unknown command" in l2_output.lower():
            l2_output = _send_command(session, "show mac address-table", timeout_seconds)
        if "unknown command" in l2_output.lower() or "there is no matched command" in l2_output.lower():
            l2_output = _send_command(session, "show mac-address", timeout_seconds)
        if "command incomplete" in l2_output.lower():
            l2_output = _send_command(session, "show mac-address dynamic", timeout_seconds)
        try:
            session.write_line("quit")
        except OSError:
            pass
        return version_output, arp_output, l2_output
    finally:
        session.close()


def _extract_version(output: str) -> str:
    for raw_line in output.splitlines():
        line = _sanitize_cli_text(raw_line).strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("version "):
            return normalize_text(line)
        if "cos version" in lowered or "firmware version" in lowered:
            return normalize_text(line)
    return ""


def _parse_arp_entries(output: str) -> list[ArpEntry]:
    entries: list[ArpEntry] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw_line in output.splitlines():
        line = _sanitize_cli_text(raw_line).strip()
        if not line or _is_prompt_line(line):
            continue
        lowered = line.lower()
        if lowered.startswith(("ipaddr", "address ", "show ip arp", "show arp")):
            continue
        if line.startswith("="):
            continue

        parts = re.split(r"\s+", line)
        if len(parts) >= 5 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]) and _normalize_mac(parts[2]):
            entry = ArpEntry(
                ip=parts[0].strip(),
                mac=_normalize_mac(parts[2]),
                vlan="",
                port_name=parts[-1].strip(),
            )
            key = (entry.ip, entry.mac, entry.vlan, entry.port_name)
            if key not in seen:
                seen.add(key)
                entries.append(entry)
            continue

        if len(parts) >= 4 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]) and _normalize_mac(parts[1]):
            vlan = ""
            port_name = parts[2].strip() if _looks_like_port(parts[2]) or parts[2] == "---" else parts[3].strip()
            if len(parts) >= 5 and parts[2].isdigit():
                vlan = parts[2].strip()
                port_name = parts[3].strip()
            entry = ArpEntry(
                ip=parts[0].strip(),
                mac=_normalize_mac(parts[1]),
                vlan=vlan,
                port_name=port_name,
            )
            key = (entry.ip, entry.mac, entry.vlan, entry.port_name)
            if key not in seen:
                seen.add(key)
                entries.append(entry)
    return entries


def _parse_l2_rows(output: str) -> list[MacTableEntry]:
    rows: list[MacTableEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_line in output.splitlines():
        line = _sanitize_cli_text(raw_line).strip()
        if not line or _is_prompt_line(line):
            continue
        lowered = line.lower()
        if lowered.startswith(("show l2 mac", "show mac address-table")):
            continue
        if "mac address" in lowered and "ports" in lowered:
            continue
        if lowered.startswith(("vid", "vlan")) and "mac" in lowered:
            continue
        if line.startswith("="):
            continue

        pipe_match = re.match(
            r"^(\d+)\s+\|\s+([0-9A-Fa-f:.\-]{12,20})\s+\|\s+.+?\|\s+([A-Za-z0-9/_-]+)$",
            line,
        )
        if pipe_match:
            mac = _normalize_mac(pipe_match.group(2))
            if mac:
                entry = MacTableEntry(
                    vlan=pipe_match.group(1).strip(),
                    mac=mac,
                    port_name=pipe_match.group(3).strip(),
                )
                key = (entry.vlan, entry.mac, entry.port_name)
                if key not in seen:
                    seen.add(key)
                    rows.append(entry)
            continue

        parts = re.split(r"\s+", line)
        mac_index = -1
        normalized_mac = ""
        for index, token in enumerate(parts):
            normalized_mac = _normalize_mac(token)
            if normalized_mac:
                mac_index = index
                break
        if mac_index == -1:
            continue

        if mac_index == 0 and len(parts) >= 3 and parts[1].isdigit() and _looks_like_port(parts[2]):
            entry = MacTableEntry(mac=normalized_mac, vlan=parts[1].strip(), port_name=parts[2].strip())
            key = (entry.vlan, entry.mac, entry.port_name)
            if key not in seen:
                seen.add(key)
                rows.append(entry)
            continue

        vlan = ""
        for token in parts[:mac_index]:
            if token.isdigit():
                vlan = token
                break

        port_name = ""
        for token in reversed(parts[mac_index + 1 :]):
            if _looks_like_port(token):
                port_name = token.strip()
                break
        if not port_name and parts:
            port_name = parts[-1].strip()
        if not port_name:
            continue
        entry = MacTableEntry(mac=normalized_mac, vlan=vlan, port_name=port_name)
        key = (entry.vlan, entry.mac, entry.port_name)
        if key not in seen:
            seen.add(key)
            rows.append(entry)
    return rows


def _ensure_port(db: Session, switch_id: int, port_name: str, vlan_id: str) -> NetworkPort:
    port = db.scalar(
        select(NetworkPort).where(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port_name,
        )
    )
    role_guess = "camera_access_monitor" if vlan_id == "2" else "camera_access"
    if port is None:
        port = NetworkPort(
            device_id=switch_id,
            port_name=port_name,
            vlan_id=vlan_id or "",
            admin_status="up",
            oper_status="up",
            role_guess=role_guess,
        )
        db.add(port)
        db.flush()
        return port

    port.oper_status = "up"
    port.admin_status = "up"
    if vlan_id:
        port.vlan_id = vlan_id
    if not port.role_guess:
        port.role_guess = role_guess
    return port


def _has_manual_override(db: Session, camera_asset_id: int | None) -> bool:
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


def _resolve_camera_asset_id(db: Session, camera_ip: str) -> int | None:
    device = db.scalar(
        select(AssetDevice).where(
            AssetDevice.management_ip == camera_ip,
            AssetDevice.device_type == "camera",
            AssetDevice.device_status != "archived",
        )
    )
    if device:
        return device.id
    channel = db.scalar(
        select(VideoChannel).where(
            VideoChannel.camera_ip == camera_ip,
            VideoChannel.camera_asset_id.is_not(None),
        )
    )
    return channel.camera_asset_id if channel and channel.camera_asset_id else None


def _resolve_camera_asset_id_by_mac(db: Session, mac_address: str) -> int | None:
    normalized_mac = _normalize_mac(mac_address)
    if not normalized_mac:
        return None
    device = db.scalar(
        select(AssetDevice).where(
            AssetDevice.mac_address == normalized_mac,
            AssetDevice.device_type == "camera",
            AssetDevice.device_status != "archived",
        )
    )
    return device.id if device else None


def _backfill_camera_mac(db: Session, camera_asset_id: int | None, mac_address: str) -> bool:
    if not camera_asset_id:
        return False
    normalized_mac = _normalize_mac(mac_address)
    if not normalized_mac:
        return False
    camera = db.get(AssetDevice, camera_asset_id)
    if camera is None or camera.device_type != "camera":
        return False
    if _normalize_mac(camera.mac_address):
        return False
    camera.mac_address = normalized_mac
    return True


def _upsert_direct_link(
    db: Session,
    *,
    switch_id: int,
    port_id: int,
    camera_asset_id: int,
    switch_ip: str,
    port_name: str,
    camera_ip: str,
    vlan_id: str,
    checked_at: datetime,
    evidence_type: str,
    confidence: float,
    evidence_prefix: str,
) -> None:
    existing = db.scalar(
        select(TopologyLink)
        .where(
            TopologyLink.dst_device_id == camera_asset_id,
            TopologyLink.link_type == "physical",
            TopologyLink.evidence_type == evidence_type,
        )
        .order_by(TopologyLink.id.desc())
    )
    evidence_summary = normalize_text(
        f"{evidence_prefix}：{switch_ip} port {port_name} -> {camera_ip or f'camera#{camera_asset_id}'}"
        f"{f' VLAN {vlan_id}' if vlan_id else ''}；{checked_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    if existing is None:
        existing = TopologyLink(
            src_device_id=switch_id,
            src_port_id=port_id,
            dst_device_id=camera_asset_id,
            dst_port_id=None,
            link_type="physical",
            confidence=confidence,
            evidence_type=evidence_type,
            evidence_summary=evidence_summary,
        )
        db.add(existing)
        return

    existing.src_device_id = switch_id
    existing.src_port_id = port_id
    existing.dst_device_id = camera_asset_id
    existing.dst_port_id = None
    existing.link_type = "physical"
    existing.confidence = confidence
    existing.evidence_type = evidence_type
    existing.evidence_summary = evidence_summary


def _save_probe_result(
    db: Session,
    *,
    switch: AssetDevice,
    management_ip: str,
    probe_status: str,
    telnet_status: str,
    http_status: str,
    https_status: str,
    ssh_status: str,
    version_text: str,
    arp_entry_count: int,
    camera_match_count: int,
    l2_mac_count: int,
    error_message: str,
    checked_at: datetime,
) -> SwitchLiveProbe:
    row = db.scalar(select(SwitchLiveProbe).where(SwitchLiveProbe.device_id == switch.id))
    payload = {
        "device_id": switch.id,
        "management_ip": management_ip,
        "probe_status": probe_status,
        "telnet_status": telnet_status,
        "http_status": http_status,
        "https_status": https_status,
        "ssh_status": ssh_status,
        "version_text": version_text,
        "arp_entry_count": arp_entry_count,
        "camera_match_count": camera_match_count,
        "l2_mac_count": l2_mac_count,
        "error_message": normalize_text(error_message),
        "checked_at": checked_at,
    }
    if row is None:
        row = SwitchLiveProbe(**payload)
        db.add(row)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    switch.health_state = "online" if probe_status == "ok" else ("warning" if telnet_status.startswith("open") else "offline")
    return row


def probe_switch_live(
    db: Session,
    *,
    switch: AssetDevice,
    username: str = "admin",
    password: str,
    timeout_seconds: float = 4.0,
) -> dict:
    checked_at = datetime.now()
    management_ip = (switch.management_ip or "").strip()
    if not management_ip:
        raise ValueError("switch_has_no_management_ip")

    http_status = _tcp_probe(management_ip, 80, timeout_seconds)
    https_status = _tcp_probe(management_ip, 443, timeout_seconds)
    ssh_status = _tcp_probe(management_ip, 22, timeout_seconds)
    telnet_port_status = _tcp_probe(management_ip, 23, timeout_seconds)

    version_text = ""
    arp_entries: list[ArpEntry] = []
    mac_rows: list[MacTableEntry] = []
    error_message = ""
    probe_status = "warning"
    arp_match_count = 0
    mac_match_count = 0
    mac_backfill_count = 0

    if telnet_port_status.startswith("open"):
        try:
            version_output, arp_output, l2_output = _run_telnet_session(management_ip, username, password, timeout_seconds)
            version_text = _extract_version(version_output)
            arp_entries = _parse_arp_entries(arp_output)
            mac_rows = _parse_l2_rows(l2_output)
            probe_status = "ok"
            port_density = Counter(row.port_name for row in mac_rows if row.port_name)

            for entry in arp_entries:
                if not _is_candidate_access_port(entry.port_name):
                    continue
                if not CAMERA_IP_RE.match(entry.ip):
                    continue
                camera_asset_id = _resolve_camera_asset_id(db, entry.ip)
                if _backfill_camera_mac(db, camera_asset_id, entry.mac):
                    mac_backfill_count += 1
                if not camera_asset_id or _has_manual_override(db, camera_asset_id):
                    continue
                port = _ensure_port(db, switch.id, entry.port_name, entry.vlan)
                _upsert_direct_link(
                    db,
                    switch_id=switch.id,
                    port_id=port.id,
                    camera_asset_id=camera_asset_id,
                    switch_ip=management_ip,
                    port_name=entry.port_name,
                    camera_ip=entry.ip,
                    vlan_id=entry.vlan,
                    checked_at=checked_at,
                    evidence_type="direct_switch_arp_probe",
                    confidence=0.98,
                    evidence_prefix="交换机实采(ARP)",
                )
                arp_match_count += 1

            for row in mac_rows:
                if not _is_candidate_access_port(row.port_name):
                    continue
                if port_density.get(row.port_name, 0) > 6:
                    continue
                camera_asset_id = _resolve_camera_asset_id_by_mac(db, row.mac)
                if not camera_asset_id or _has_manual_override(db, camera_asset_id):
                    continue
                camera = db.get(AssetDevice, camera_asset_id)
                camera_ip = (camera.management_ip or "").strip() if camera else ""
                port = _ensure_port(db, switch.id, row.port_name, row.vlan)
                _upsert_direct_link(
                    db,
                    switch_id=switch.id,
                    port_id=port.id,
                    camera_asset_id=camera_asset_id,
                    switch_ip=management_ip,
                    port_name=row.port_name,
                    camera_ip=camera_ip,
                    vlan_id=row.vlan,
                    checked_at=checked_at,
                    evidence_type="direct_switch_mac_probe",
                    confidence=0.96,
                    evidence_prefix="交换机实采(MAC表)",
                )
                mac_match_count += 1
        except Exception as exc:  # pragma: no cover
            probe_status = "warning"
            error_message = str(exc)
    else:
        probe_status = "offline"
        error_message = "telnet_port_closed"

    probe_row = _save_probe_result(
        db,
        switch=switch,
        management_ip=management_ip,
        probe_status=probe_status,
        telnet_status=telnet_port_status,
        http_status=http_status,
        https_status=https_status,
        ssh_status=ssh_status,
        version_text=version_text,
        arp_entry_count=len(arp_entries),
        camera_match_count=arp_match_count + mac_match_count,
        l2_mac_count=len(mac_rows),
        error_message=error_message,
        checked_at=checked_at,
    )
    db.commit()
    db.refresh(probe_row)
    return {
        "device_id": switch.id,
        "management_ip": management_ip,
        "probe_status": probe_status,
        "telnet_status": telnet_port_status,
        "http_status": http_status,
        "https_status": https_status,
        "ssh_status": ssh_status,
        "version_text": version_text,
        "arp_entry_count": len(arp_entries),
        "camera_match_count": arp_match_count + mac_match_count,
        "arp_match_count": arp_match_count,
        "mac_match_count": mac_match_count,
        "camera_mac_backfill_count": mac_backfill_count,
        "l2_mac_count": len(mac_rows),
        "error_message": error_message,
        "checked_at": checked_at.isoformat(timespec="seconds"),
    }


def list_switch_probes(db: Session, switch_ids: set[int] | None = None) -> dict[int, SwitchLiveProbe]:
    stmt = select(SwitchLiveProbe)
    if switch_ids:
        stmt = stmt.where(SwitchLiveProbe.device_id.in_(switch_ids))
    rows = db.scalars(stmt).all()
    return {row.device_id: row for row in rows}

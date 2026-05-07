from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformSource(Base):
    __tablename__ = "platform_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    vendor: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    management_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    version: Mapped[str] = mapped_column(String(100), default="")
    sync_status: Mapped[str] = mapped_column(String(50), default="pending")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class CredentialRef(Base):
    __tablename__ = "credential_ref"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String(255), index=True)
    username_hint: Mapped[str] = mapped_column(String(255), default="")
    scope: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class AssetArea(Base):
    __tablename__ = "asset_area"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site: Mapped[str] = mapped_column(String(100), index=True)
    building: Mapped[str] = mapped_column(String(100), default="")
    floor: Mapped[str] = mapped_column(String(100), default="")
    zone: Mapped[str] = mapped_column(String(100), default="")
    weak_current_room: Mapped[str] = mapped_column(String(100), default="")
    display_name: Mapped[str] = mapped_column(String(255), index=True)


class AssetDevice(Base):
    __tablename__ = "asset_device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_type: Mapped[str] = mapped_column(String(50), index=True)
    vendor: Mapped[str] = mapped_column(String(100), default="", index=True)
    model: Mapped[str] = mapped_column(String(255), default="")
    serial_number: Mapped[str] = mapped_column(String(255), default="", index=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    management_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    service_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    mac_address: Mapped[str] = mapped_column(String(64), default="", index=True)
    platform_source_id: Mapped[int | None] = mapped_column(ForeignKey("platform_source.id"), nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("asset_area.id"), nullable=True)
    parent_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True)
    health_state: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    device_status: Mapped[str] = mapped_column(String(50), default="discovered")
    source_priority: Mapped[int] = mapped_column(Integer, default=100)
    primary_source_type: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NetworkPort(Base):
    __tablename__ = "network_port"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("asset_device.id"), index=True)
    port_name: Mapped[str] = mapped_column(String(100), index=True)
    port_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_type: Mapped[str] = mapped_column(String(50), default="electrical")
    admin_status: Mapped[str] = mapped_column(String(50), default="unknown")
    oper_status: Mapped[str] = mapped_column(String(50), default="unknown")
    vlan_id: Mapped[str] = mapped_column(String(50), default="")
    poe_status: Mapped[str] = mapped_column(String(50), default="")
    role_guess: Mapped[str] = mapped_column(String(50), default="")


class VideoChannel(Base):
    __tablename__ = "video_channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_device_id: Mapped[int] = mapped_column(ForeignKey("asset_device.id"), index=True)
    channel_no: Mapped[str] = mapped_column(String(50), index=True)
    channel_code: Mapped[str] = mapped_column(String(100), default="")
    channel_name: Mapped[str] = mapped_column(String(255), default="")
    camera_asset_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True)
    camera_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    protocol_type: Mapped[str] = mapped_column(String(50), default="")
    rtsp_main: Mapped[str] = mapped_column(Text, default="")
    rtsp_sub: Mapped[str] = mapped_column(Text, default="")
    snapshot_url: Mapped[str] = mapped_column(Text, default="")
    record_track_id: Mapped[str] = mapped_column(String(100), default="")
    channel_status: Mapped[str] = mapped_column(String(50), default="unknown")
    notes: Mapped[str] = mapped_column(Text, default="")


class ChannelStreamDiagnostic(Base):
    __tablename__ = "channel_stream_diagnostic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("video_channel.id"), unique=True, index=True)
    camera_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    platform_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    scan_status: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    error_class: Mapped[str] = mapped_column(String(100), default="", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    rtsp_url: Mapped[str] = mapped_column(Text, default="")
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_report: Mapped[str] = mapped_column(String(255), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SwitchLiveProbe(Base):
    __tablename__ = "switch_live_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("asset_device.id"), unique=True, index=True)
    management_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    probe_status: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    telnet_status: Mapped[str] = mapped_column(String(50), default="")
    http_status: Mapped[str] = mapped_column(String(50), default="")
    https_status: Mapped[str] = mapped_column(String(50), default="")
    ssh_status: Mapped[str] = mapped_column(String(50), default="")
    version_text: Mapped[str] = mapped_column(String(255), default="")
    arp_entry_count: Mapped[int] = mapped_column(Integer, default=0)
    camera_match_count: Mapped[int] = mapped_column(Integer, default=0)
    l2_mac_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TopologyLink(Base):
    __tablename__ = "topology_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    src_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True)
    src_port_id: Mapped[int | None] = mapped_column(ForeignKey("network_port.id"), nullable=True)
    dst_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True)
    dst_port_id: Mapped[int | None] = mapped_column(ForeignKey("network_port.id"), nullable=True)
    link_type: Mapped[str] = mapped_column(String(50), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_type: Mapped[str] = mapped_column(String(50), default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")


class NetworkTopologyDomain(Base):
    __tablename__ = "network_topology_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    site: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_report_path: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NetworkTopologyNode(Base):
    __tablename__ = "network_topology_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("network_topology_domain.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    node_key: Mapped[str] = mapped_column(String(160), index=True)
    ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    node_type: Mapped[str] = mapped_column(String(50), default="", index=True)
    layer: Mapped[str] = mapped_column(String(50), default="", index=True)
    role: Mapped[str] = mapped_column(String(80), default="", index=True)
    floor: Mapped[str] = mapped_column(String(50), default="", index=True)
    weak_current_room: Mapped[str] = mapped_column(String(120), default="")
    parent_node_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    parent_ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    camera_count: Mapped[int] = mapped_column(Integer, default=0)
    switch_count: Mapped[int] = mapped_column(Integer, default=0)
    review_status: Mapped[str] = mapped_column(String(50), default="system_built", index=True)
    flags: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    manual_note: Mapped[str] = mapped_column(Text, default="")
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_source: Mapped[str] = mapped_column(String(80), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NetworkTopologyEdge(Base):
    __tablename__ = "network_topology_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("network_topology_domain.id"), index=True)
    src_node_key: Mapped[str] = mapped_column(String(160), index=True)
    dst_node_key: Mapped[str] = mapped_column(String(160), index=True)
    src_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    dst_device_id: Mapped[int | None] = mapped_column(ForeignKey("asset_device.id"), nullable=True, index=True)
    edge_type: Mapped[str] = mapped_column(String(50), default="", index=True)
    src_port_label: Mapped[str] = mapped_column(String(120), default="")
    dst_port_label: Mapped[str] = mapped_column(String(120), default="")
    vlan_id: Mapped[str] = mapped_column(String(50), default="")
    layer_path: Mapped[str] = mapped_column(String(120), default="")
    evidence_type: Mapped[str] = mapped_column(String(80), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(50), default="system_built", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    manual_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

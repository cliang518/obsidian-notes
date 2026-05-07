from pydantic import BaseModel, Field


class RuntimeCounts(BaseModel):
    platform_sources: int = 0
    devices: int = 0
    ports: int = 0
    channels: int = 0
    links: int = 0


class PlatformSourceOut(BaseModel):
    id: int
    source_type: str
    name: str
    vendor: str
    base_url: str
    management_ip: str
    version: str
    sync_status: str

    class Config:
        from_attributes = True


class DeviceOut(BaseModel):
    id: int
    device_type: str
    vendor: str
    model: str
    serial_number: str
    hostname: str
    management_ip: str
    service_ip: str
    mac_address: str = ""
    health_state: str
    device_status: str = ""
    primary_source_type: str
    area_id: int | None = None
    area_display_name: str = ""
    parent_device_id: int | None = None
    platform_source_id: int | None = None
    source_priority: int = 100
    notes: str = ""
    live_probe_status: str = "unknown"
    live_probe_checked_at: str = ""
    live_probe_telnet_status: str = ""
    live_probe_http_status: str = ""
    live_probe_https_status: str = ""
    live_probe_ssh_status: str = ""
    live_probe_version_text: str = ""
    live_probe_arp_entry_count: int = 0
    live_probe_camera_match_count: int = 0
    live_probe_l2_mac_count: int = 0
    live_probe_error_message: str = ""
    topology_role_guess: str = ""
    topology_role_label: str = ""
    topology_gap_reason: str = ""
    topology_gap_label: str = ""
    topology_auto_flagged: bool = False
    topology_judgement_summary: str = ""

    class Config:
        from_attributes = True


class DeviceUpsert(BaseModel):
    device_type: str = "camera"
    vendor: str = ""
    model: str = ""
    serial_number: str = ""
    hostname: str = ""
    management_ip: str = ""
    service_ip: str = ""
    mac_address: str = ""
    platform_source_id: int | None = None
    area_id: int | None = None
    parent_device_id: int | None = None
    health_state: str = "unknown"
    device_status: str = "manual"
    source_priority: int = 50
    primary_source_type: str = "manual"
    notes: str = ""


class TopologyLinkOut(BaseModel):
    id: int
    src_device_id: int | None = None
    dst_device_id: int | None = None
    link_type: str
    confidence: float = Field(default=0.0)
    evidence_type: str

    class Config:
        from_attributes = True

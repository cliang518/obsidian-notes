from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.agent_service import AgentServiceRegistration
from app.models.asset import AssetDevice, PlatformSource
from app.models.control_platform import ControlPlatformRegistration
from app.models.inspection_task import InspectionTask
from app.models.mobile_channel import MobileChannelRegistration
from app.models.notification_channel import NotificationChannelRegistration
from app.models.storage_provider import StorageProviderRegistration
from app.models.user_account import UserAccount
from app.models.work_order import WorkOrder
from app.services.auth import hash_password
from app.services.source_registry import KNOWN_DEVICES, KNOWN_PLATFORM_SOURCES
from app.services.text_normalize import normalize_text


CONTROL_TRACK_SOURCE_TYPE = {
    "electrical_control_platform": "control_platform_electrical",
    "new_control_platform": "control_platform_new",
    "legacy_control_platform": "control_platform_legacy",
}


def seed_known_sources() -> None:
    db = SessionLocal()
    try:
        for source in KNOWN_PLATFORM_SOURCES:
            source = _normalize_seed_mapping(source)
            existing = db.scalar(
                select(PlatformSource).where(
                    PlatformSource.source_type == source["source_type"],
                    PlatformSource.management_ip == source["management_ip"],
                )
            )
            if existing:
                existing.name = source["name"]
                existing.vendor = source["vendor"]
                existing.base_url = source["base_url"]
                existing.version = source["version"]
                existing.notes = source["notes"]
            else:
                db.add(PlatformSource(**source, sync_status="registered"))

        db.flush()

        for device in KNOWN_DEVICES:
            device = _normalize_seed_mapping(device)
            existing = db.scalar(
                select(AssetDevice).where(
                    AssetDevice.device_type == device["device_type"],
                    AssetDevice.management_ip == device["management_ip"],
                )
            )
            if existing:
                existing.vendor = device["vendor"]
                existing.model = device["model"]
                existing.hostname = device["hostname"]
                existing.service_ip = device["service_ip"]
                existing.serial_number = device["serial_number"]
                existing.primary_source_type = device["primary_source_type"]
                existing.notes = device["notes"]
            else:
                db.add(
                    AssetDevice(
                        **device,
                        health_state="discovered",
                        device_status="registered",
                        source_priority=100,
                    )
                )

        _seed_control_platforms(db)
        _seed_agent_services(db)
        _seed_mobile_channels(db)
        _seed_notification_channels(db)
        _seed_storage_providers(db)
        _seed_user_accounts(db)
        _seed_work_orders(db)
        _seed_inspection_tasks(db)

        db.commit()
    finally:
        db.close()


def _seed_control_platforms(db) -> None:
    registrations = [
        {
            "track_key": "electrical_control_platform",
            "instance_name": "电控系统",
            "instance_code": "electrical-control-host",
            "endpoint_name": "Web 入口",
            "endpoint_path": "/Web/",
            "vlan_id": "unknown-control",
            "vlan_name": "风控/电控待确认 VLAN",
            "network_zone": "风控/电控域",
            "display_name": "电控系统",
            "platform_family": "电控 / BA",
            "vendor": "Unknown",
            "base_url": "http://10.0.71.250/Web/",
            "management_ip": "10.0.71.250",
            "username_hint": "xincheng",
            "status": "reserved",
            "next_action": "待网络接入开发主机后，对电控系统执行只读审计。",
        },
        {
            "track_key": "new_control_platform",
            "instance_name": "风控新系统",
            "instance_code": "fengkong-shared-host",
            "endpoint_name": "Web 入口",
            "endpoint_path": "/Web/",
            "vlan_id": "unknown-control",
            "vlan_name": "风控/电控待确认 VLAN",
            "network_zone": "风控/电控域",
            "display_name": "风控新系统",
            "platform_family": "风控 / BA",
            "vendor": "Unknown",
            "base_url": "http://10.0.69.100/Web/",
            "management_ip": "10.0.69.100",
            "username_hint": "dadaokt",
            "status": "reserved",
            "next_action": "待网络接入开发主机后，对风控新系统执行只读审计。",
        },
        {
            "track_key": "legacy_control_platform",
            "instance_name": "风控老系统",
            "instance_code": "fengkong-shared-host",
            "endpoint_name": "SmartEnergy 房间列表",
            "endpoint_path": "/SmartEnergy/roomlist2.jsp",
            "vlan_id": "unknown-control",
            "vlan_name": "风控/电控待确认 VLAN",
            "network_zone": "风控/电控域",
            "display_name": "风控老系统",
            "platform_family": "风控 / BA",
            "vendor": "Unknown",
            "base_url": "http://10.0.69.200/SmartEnergy/roomlist2.jsp",
            "management_ip": "10.0.69.200",
            "username_hint": "ktadmin",
            "status": "reserved",
            "next_action": "待网络接入开发主机后，对风控老系统执行只读审计。",
        },
    ]

    for registration in registrations:
        registration = _normalize_seed_mapping(registration)
        existing = db.scalar(
            select(ControlPlatformRegistration).where(
                ControlPlatformRegistration.track_key == registration["track_key"]
            )
        )
        if existing:
            existing.instance_name = registration.get("instance_name", existing.instance_name)
            existing.instance_code = registration.get("instance_code", existing.instance_code)
            existing.endpoint_name = registration.get("endpoint_name", existing.endpoint_name)
            existing.endpoint_path = registration.get("endpoint_path", existing.endpoint_path)
            existing.vlan_id = registration.get("vlan_id", existing.vlan_id)
            existing.vlan_name = registration.get("vlan_name", existing.vlan_name)
            existing.network_zone = registration.get("network_zone", existing.network_zone)
            existing.display_name = registration["display_name"]
            existing.platform_family = registration["platform_family"]
            existing.vendor = registration["vendor"]
            existing.base_url = registration.get("base_url", existing.base_url)
            existing.management_ip = registration.get("management_ip", existing.management_ip)
            existing.username_hint = registration.get("username_hint", existing.username_hint)
            existing.next_action = registration["next_action"]
            existing.status = registration["status"]
        else:
            db.add(ControlPlatformRegistration(**registration))

    db.flush()

    rows = db.scalars(select(ControlPlatformRegistration)).all()
    for row in rows:
        row.source_id = _ensure_control_source_binding(db, row)


def _seed_agent_services(db) -> None:
    agent_services = [
        {
            "service_key": "openclaw",
            "display_name": "OpenClaw Agent",
            "service_type": "rest_agent",
            "endpoint_url": "",
            "auth_mode": "token",
            "access_scope": "read_only",
            "enabled": True,
            "read_only_first": True,
            "status": "planned",
            "notes": "计划对接 OpenClaw，优先开放只读查询能力。",
        },
        {
            "service_key": "opencode-mcp",
            "display_name": "OpenCode MCP",
            "service_type": "mcp",
            "endpoint_url": "",
            "auth_mode": "token",
            "access_scope": "read_only",
            "enabled": True,
            "read_only_first": True,
            "status": "planned",
            "notes": "计划对接 OpenCode 风格 MCP 服务。",
        },
        {
            "service_key": "local-mcp-hub",
            "display_name": "本地 MCP Hub",
            "service_type": "mcp",
            "endpoint_url": "",
            "auth_mode": "none",
            "access_scope": "read_only",
            "enabled": True,
            "read_only_first": True,
            "status": "planned",
            "notes": "本地智能体总线占位，用于汇聚后续 MCP 服务。",
        },
    ]

    for item in agent_services:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(AgentServiceRegistration).where(AgentServiceRegistration.service_key == item["service_key"])
        )
        if existing:
            existing.display_name = item["display_name"]
            existing.service_type = item["service_type"]
            existing.auth_mode = item["auth_mode"]
            existing.access_scope = item["access_scope"]
            existing.read_only_first = item["read_only_first"]
            existing.notes = item["notes"]
            existing.status = existing.status or item["status"]
        else:
            db.add(AgentServiceRegistration(**item))


def _seed_mobile_channels(db) -> None:
    mobile_channels = [
        {
            "channel_key": "mobile-alert-workspace",
            "display_name": "移动告警工作台",
            "channel_type": "workspace",
            "target_platform": "企业微信 / 微信 / 飞书",
            "entry_mode": "h5",
            "deep_link_scheme": "",
            "auth_mode": "session",
            "scope": "alert_ops",
            "enabled": True,
            "mobile_first": True,
            "status": "planned",
            "notes": "承接告警确认、转派、备注、拍照。",
        },
        {
            "channel_key": "mobile-workorder-workspace",
            "display_name": "移动工单工作台",
            "channel_type": "workspace",
            "target_platform": "企业微信 / 微信 / 飞书",
            "entry_mode": "h5",
            "deep_link_scheme": "",
            "auth_mode": "session",
            "scope": "workorder_ops",
            "enabled": True,
            "mobile_first": True,
            "status": "planned",
            "notes": "承接工单执行、现场记录和上传。",
        },
        {
            "channel_key": "mobile-inspection-workspace",
            "display_name": "移动巡检工作台",
            "channel_type": "workspace",
            "target_platform": "企业微信 / 微信 / 飞书",
            "entry_mode": "h5",
            "deep_link_scheme": "",
            "auth_mode": "session",
            "scope": "inspection_ops",
            "enabled": True,
            "mobile_first": True,
            "status": "planned",
            "notes": "承接扫码定位、巡检确认和现场备注。",
        },
    ]

    for item in mobile_channels:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(MobileChannelRegistration).where(MobileChannelRegistration.channel_key == item["channel_key"])
        )
        if existing:
            existing.display_name = item["display_name"]
            existing.channel_type = item["channel_type"]
            existing.target_platform = item["target_platform"]
            existing.entry_mode = item["entry_mode"]
            existing.auth_mode = item["auth_mode"]
            existing.scope = item["scope"]
            existing.mobile_first = item["mobile_first"]
            existing.notes = item["notes"]
            existing.status = existing.status or item["status"]
        else:
            db.add(MobileChannelRegistration(**item))


def _seed_storage_providers(db) -> None:
    storage_providers = [
        {
            "provider_key": "local-runtime-storage",
            "display_name": "本地运行存储",
            "provider_type": "local_filesystem",
            "endpoint_url": "",
            "bucket_or_share": "runtime",
            "auth_mode": "none",
            "usage_scope": "runtime_cache",
            "enabled": True,
            "writable": True,
            "status": "active",
            "notes": "当前开发机运行目录与缓存目录。",
        },
        {
            "provider_key": "seaweedfs-planned",
            "display_name": "SeaweedFS 对象存储",
            "provider_type": "s3_compatible",
            "endpoint_url": "",
            "bucket_or_share": "",
            "auth_mode": "access_key",
            "usage_scope": "media_cache",
            "enabled": True,
            "writable": True,
            "status": "planned",
            "notes": "后续承接对象存储、大文件与视频缓存。",
        },
        {
            "provider_key": "nextcloud-planned",
            "display_name": "Nextcloud 协作文件入口",
            "provider_type": "webdav",
            "endpoint_url": "",
            "bucket_or_share": "",
            "auth_mode": "token",
            "usage_scope": "documents",
            "enabled": True,
            "writable": False,
            "status": "planned",
            "notes": "后续承接协作文档、资料上传和共享。",
        },
    ]

    for item in storage_providers:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(StorageProviderRegistration).where(
                StorageProviderRegistration.provider_key == item["provider_key"]
            )
        )
        if existing:
            existing.display_name = item["display_name"]
            existing.provider_type = item["provider_type"]
            existing.auth_mode = item["auth_mode"]
            existing.usage_scope = item["usage_scope"]
            existing.writable = item["writable"]
            existing.notes = item["notes"]
            existing.status = existing.status or item["status"]
        else:
            db.add(StorageProviderRegistration(**item))


def _seed_notification_channels(db) -> None:
    channels = [
        {
            "channel_key": "default-webhook",
            "display_name": "默认 Webhook 通道",
            "channel_type": "webhook",
            "endpoint_url": "",
            "auth_mode": "none",
            "target_scope": "alerts",
            "enabled": True,
            "send_resolved": True,
            "alert_cooldown_seconds": 300,
            "suppress_flap_watch": True,
            "status": "active",
            "notes": "用于承接通用告警推送和后续联调。",
        },
        {
            "channel_key": "wecom-bot",
            "display_name": "企业微信机器人",
            "channel_type": "wecom_bot",
            "endpoint_url": "",
            "auth_mode": "token",
            "target_scope": "alerts_workorders",
            "enabled": True,
            "send_resolved": True,
            "alert_cooldown_seconds": 300,
            "suppress_flap_watch": True,
            "status": "planned",
            "notes": "后续承接值班群告警、派工和恢复通知。",
        },
        {
            "channel_key": "feishu-bot",
            "display_name": "飞书机器人",
            "channel_type": "feishu_bot",
            "endpoint_url": "",
            "auth_mode": "token",
            "target_scope": "alerts_workorders",
            "enabled": True,
            "send_resolved": True,
            "alert_cooldown_seconds": 300,
            "suppress_flap_watch": True,
            "status": "planned",
            "notes": "后续承接飞书群告警和工单消息。",
        },
    ]

    for item in channels:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(NotificationChannelRegistration).where(
                NotificationChannelRegistration.channel_key == item["channel_key"]
            )
        )
        if existing:
            existing.display_name = item["display_name"]
            existing.channel_type = item["channel_type"]
            existing.endpoint_url = item["endpoint_url"]
            existing.auth_mode = item["auth_mode"]
            existing.target_scope = item["target_scope"]
            existing.enabled = item["enabled"]
            existing.send_resolved = item["send_resolved"]
            existing.alert_cooldown_seconds = item["alert_cooldown_seconds"]
            existing.suppress_flap_watch = item["suppress_flap_watch"]
            existing.status = item["status"]
            existing.notes = item["notes"]
        else:
            db.add(NotificationChannelRegistration(**item))


def _seed_user_accounts(db) -> None:
    accounts = [
        {
            "username": settings.bootstrap_admin_username,
            "display_name": "平台管理员",
            "role": "admin",
            "status": "active",
            "department": "信息弱电中心",
            "mobile": "",
            "email": "",
            "account_source": "local",
            "password_hash": hash_password(settings.bootstrap_admin_password),
            "password_ready": True,
            "notes": "V2 主平台默认管理账户占位，后续可接正式认证与年度授权联动。",
        },
        {
            "username": "manager.ops",
            "display_name": "值班主管",
            "role": "manager",
            "status": "active",
            "department": "运维班组",
            "mobile": "",
            "email": "",
            "account_source": "local",
            "password_hash": hash_password(settings.bootstrap_manager_password),
            "password_ready": True,
            "notes": "用于值班审批、告警确认和工单派发。",
        },
        {
            "username": "tech.field",
            "display_name": "现场维修员",
            "role": "technician",
            "status": "pending",
            "department": "现场维护",
            "mobile": "",
            "email": "",
            "account_source": "local",
            "password_hash": hash_password(settings.bootstrap_technician_password),
            "password_ready": True,
            "notes": "移动端维修、照片上传和巡检签到预留账户。",
        },
    ]
    for item in accounts:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(select(UserAccount).where(UserAccount.username == item["username"]))
        if existing:
            existing.display_name = item["display_name"]
            existing.role = item["role"]
            existing.status = item["status"]
            existing.department = item["department"]
            existing.account_source = item["account_source"]
            existing.password_hash = item["password_hash"]
            existing.password_ready = item["password_ready"]
            existing.notes = item["notes"]
        else:
            db.add(UserAccount(**item))


def _seed_work_orders(db) -> None:
    items = [
        {
            "title": "2F南楼视频异常复核",
            "order_type": "fault_repair",
            "status": "open",
            "priority": "high",
            "area_name": "2F南楼",
            "source_type": "alert_bridge",
            "assignee_username": "tech.field",
            "description": "针对热点摄像头抖动和视频异常进行现场复核，确认交换机端口、电源和链路状态。",
        },
        {
            "title": "205分平台归属核验",
            "order_type": "platform_audit",
            "status": "in_progress",
            "priority": "medium",
            "area_name": "205分平台",
            "source_type": "jvss_platform",
            "assignee_username": "manager.ops",
            "description": "结合 10.0.59.205 平台与交换机链路核验摄像头归属，其中 59 段按 B2 停车场处理，58 段按商场视频区处理。",
        },
    ]
    for item in items:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(WorkOrder).where(
                WorkOrder.source_alert_id.is_(None),
                WorkOrder.source_type == item["source_type"],
                WorkOrder.area_name == item["area_name"],
                WorkOrder.order_type == item["order_type"],
            )
        )
        if existing:
            existing.title = item["title"]
            existing.status = item["status"]
            existing.priority = item["priority"]
            existing.area_name = item["area_name"]
            existing.assignee_username = item["assignee_username"]
            existing.description = item["description"]
        else:
            db.add(WorkOrder(**item))


def _seed_inspection_tasks(db) -> None:
    items = [
        {
            "title": "监控交换机 VLAN 2 日巡检",
            "plan_name": "监控网络日巡检",
            "status": "scheduled",
            "area_name": "监控主干",
            "target_type": "network_segment",
            "owner_username": "manager.ops",
            "notes": "重点检查 10.0.68 管理段交换机、VLAN 2、主干光口和热点故障设备。",
        },
        {
            "title": "205分平台视频核查",
            "plan_name": "重点区域复核",
            "status": "scheduled",
            "area_name": "205分平台",
            "target_type": "video_platform",
            "owner_username": "tech.field",
            "notes": "核查 10.0.59.205 与现场摄像头分布的一致性，59 段归 B2 停车场，58 段归商场视频区。",
        },
    ]
    for item in items:
        item = _normalize_seed_mapping(item)
        existing = db.scalar(
            select(InspectionTask).where(
                InspectionTask.target_type == item["target_type"],
                InspectionTask.area_name == item["area_name"],
                InspectionTask.plan_name == item["plan_name"],
            )
        )
        if existing:
            existing.title = item["title"]
            existing.status = item["status"]
            existing.area_name = item["area_name"]
            existing.owner_username = item["owner_username"]
            existing.notes = item["notes"]
        else:
            db.add(InspectionTask(**item))


def _ensure_control_source_binding(db, registration: ControlPlatformRegistration) -> int | None:
    source_type = CONTROL_TRACK_SOURCE_TYPE.get(registration.track_key)
    if not source_type:
        return registration.source_id

    source = db.scalar(select(PlatformSource).where(PlatformSource.source_type == source_type))
    if not source:
        source = PlatformSource(
            source_type=source_type,
            name=registration.display_name,
            vendor=registration.vendor or "Unknown",
            base_url=registration.base_url,
            management_ip=registration.management_ip or f"pending-{registration.track_key}",
            version="pending-intake",
            notes=registration.notes,
            sync_status="registered",
        )
        db.add(source)
        db.flush()
    else:
        source.name = registration.display_name or source.name
        source.vendor = registration.vendor or source.vendor
        source.base_url = registration.base_url or source.base_url
        source.management_ip = registration.management_ip or source.management_ip
        source.notes = registration.notes or source.notes
        source.sync_status = "registered"

    device = db.scalar(
        select(AssetDevice).where(
            AssetDevice.primary_source_type == source_type,
            AssetDevice.device_type == "platform_node",
        )
    )
    if not device:
        db.add(
            AssetDevice(
                device_type="platform_node",
                vendor=registration.vendor or "Unknown",
                model=registration.platform_family or "Control Platform",
                hostname=registration.display_name,
                management_ip=registration.management_ip or f"pending-{registration.track_key}",
                service_ip=registration.management_ip or f"pending-{registration.track_key}",
                primary_source_type=source_type,
                notes=registration.notes,
                health_state="discovered",
                device_status="registered",
                source_priority=90,
            )
        )
        db.flush()
    else:
        device.vendor = registration.vendor or device.vendor
        device.model = registration.platform_family or device.model
        device.hostname = registration.display_name or device.hostname
        device.management_ip = registration.management_ip or device.management_ip
        device.service_ip = registration.management_ip or device.service_ip
        device.notes = registration.notes or device.notes

    return source.id


def _normalize_seed_mapping(data: dict) -> dict:
    normalized: dict = {}
    for key, value in data.items():
        normalized[key] = normalize_text(value) if isinstance(value, str) else value
    return normalized

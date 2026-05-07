from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.settings import settings


Base = declarative_base()

_db_path: Path = settings.database_path
_db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database() -> None:
    from app.models.agent_service import AgentServiceRegistration
    from app.models.asset import (
        AssetArea,
        AssetDevice,
        ChannelStreamDiagnostic,
        CredentialRef,
        NetworkPort,
        NetworkTopologyDomain,
        NetworkTopologyEdge,
        NetworkTopologyNode,
        PlatformSource,
        SwitchLiveProbe,
        TopologyLink,
        VideoChannel,
    )
    from app.models.alert import OpsAlert
    from app.models.control_domain import ControlDevice, ControlEvent, ControlMenu, ControlPoint, ControlScenario
    from app.models.control_platform import ControlPlatformRegistration
    from app.models.floor_plan import FloorPlanAnchor, FloorPlanDocument
    from app.models.integration import SourceObjectMapping, SyncJob, SyncSnapshot
    from app.models.inspection_task import InspectionTask
    from app.models.llm_config import LlmProviderConfig
    from app.models.mobile_channel import MobileChannelRegistration
    from app.models.mobile_dispatch_item import MobileDispatchItem
    from app.models.notification_channel import NotificationChannelRegistration
    from app.models.notification_delivery_log import NotificationDeliveryLog
    from app.models.storage_provider import StorageProviderRegistration
    from app.models.user_account import UserAccount
    from app.models.user_session import UserSession
    from app.models.work_order import WorkOrder

    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()


def _run_sqlite_migrations() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "user_account" in tables:
        columns = {item["name"] for item in inspector.get_columns("user_account")}
        if "password_hash" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE user_account ADD COLUMN password_hash VARCHAR(255) DEFAULT ''"))
    if "work_order" in tables:
        columns = {item["name"] for item in inspector.get_columns("work_order")}
        additions = {
            "source_alert_id": "ALTER TABLE work_order ADD COLUMN source_alert_id INTEGER",
            "topology_node_key": "ALTER TABLE work_order ADD COLUMN topology_node_key VARCHAR(160) DEFAULT ''",
            "topology_edge_id": "ALTER TABLE work_order ADD COLUMN topology_edge_id INTEGER",
            "verification_status": "ALTER TABLE work_order ADD COLUMN verification_status VARCHAR(50) DEFAULT 'pending'",
            "verified_by": "ALTER TABLE work_order ADD COLUMN verified_by VARCHAR(80) DEFAULT ''",
            "verified_at": "ALTER TABLE work_order ADD COLUMN verified_at DATETIME",
            "closed_by": "ALTER TABLE work_order ADD COLUMN closed_by VARCHAR(80) DEFAULT ''",
            "close_reason": "ALTER TABLE work_order ADD COLUMN close_reason TEXT DEFAULT ''",
            "topology_review_payload": "ALTER TABLE work_order ADD COLUMN topology_review_payload TEXT DEFAULT ''",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))
    if "ops_alert" in tables:
        columns = {item["name"] for item in inspector.get_columns("ops_alert")}
        if "linked_work_order_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE ops_alert ADD COLUMN linked_work_order_id INTEGER"))
    if "inspection_task" in tables:
        columns = {item["name"] for item in inspector.get_columns("inspection_task")}
        if "source_work_order_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE inspection_task ADD COLUMN source_work_order_id INTEGER"))
    if "mobile_dispatch_item" in tables:
        columns = {item["name"] for item in inspector.get_columns("mobile_dispatch_item")}
        additions = {
            "source_alert_id": "ALTER TABLE mobile_dispatch_item ADD COLUMN source_alert_id INTEGER",
            "source_work_order_id": "ALTER TABLE mobile_dispatch_item ADD COLUMN source_work_order_id INTEGER",
            "source_inspection_id": "ALTER TABLE mobile_dispatch_item ADD COLUMN source_inspection_id INTEGER",
            "mobile_channel_key": "ALTER TABLE mobile_dispatch_item ADD COLUMN mobile_channel_key VARCHAR(100) DEFAULT ''",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))
    if "control_platform_registration" in tables:
        columns = {item["name"] for item in inspector.get_columns("control_platform_registration")}
        additions = {
            "instance_name": "ALTER TABLE control_platform_registration ADD COLUMN instance_name VARCHAR(255) DEFAULT ''",
            "instance_code": "ALTER TABLE control_platform_registration ADD COLUMN instance_code VARCHAR(80) DEFAULT ''",
            "endpoint_name": "ALTER TABLE control_platform_registration ADD COLUMN endpoint_name VARCHAR(120) DEFAULT ''",
            "endpoint_path": "ALTER TABLE control_platform_registration ADD COLUMN endpoint_path VARCHAR(255) DEFAULT ''",
            "vlan_id": "ALTER TABLE control_platform_registration ADD COLUMN vlan_id VARCHAR(50) DEFAULT ''",
            "vlan_name": "ALTER TABLE control_platform_registration ADD COLUMN vlan_name VARCHAR(120) DEFAULT ''",
            "network_zone": "ALTER TABLE control_platform_registration ADD COLUMN network_zone VARCHAR(120) DEFAULT ''",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))
    if "notification_channel_registration" in tables:
        columns = {item["name"] for item in inspector.get_columns("notification_channel_registration")}
        additions = {
            "alert_cooldown_seconds": "ALTER TABLE notification_channel_registration ADD COLUMN alert_cooldown_seconds INTEGER DEFAULT 300",
            "suppress_flap_watch": "ALTER TABLE notification_channel_registration ADD COLUMN suppress_flap_watch BOOLEAN DEFAULT 1",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))
    if "network_topology_node" in tables:
        columns = {item["name"] for item in inspector.get_columns("network_topology_node")}
        additions = {
            "pos_x": "ALTER TABLE network_topology_node ADD COLUMN pos_x FLOAT",
            "pos_y": "ALTER TABLE network_topology_node ADD COLUMN pos_y FLOAT",
            "position_source": "ALTER TABLE network_topology_node ADD COLUMN position_source VARCHAR(80) DEFAULT ''",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))
    if "network_topology_edge" in tables:
        columns = {item["name"] for item in inspector.get_columns("network_topology_edge")}
        additions = {
            "vlan_id": "ALTER TABLE network_topology_edge ADD COLUMN vlan_id VARCHAR(50) DEFAULT ''",
        }
        with engine.begin() as conn:
            for name, sql in additions.items():
                if name not in columns:
                    conn.execute(text(sql))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.control_domain import ControlDevice, ControlEvent, ControlMenu, ControlPoint, ControlScenario
from app.models.control_platform import ControlPlatformRegistration
from app.services.text_normalize import normalize_text


router = APIRouter()


def _summary_payload(db: Session, registration_id: int | None = None) -> dict:
    registrations = db.scalars(select(ControlPlatformRegistration).order_by(ControlPlatformRegistration.track_key)).all()
    registration_map = {row.id: row for row in registrations}

    device_stmt = select(ControlDevice)
    point_stmt = select(ControlPoint)
    scenario_stmt = select(ControlScenario)
    event_stmt = select(ControlEvent)
    menu_stmt = select(ControlMenu)

    if registration_id is not None:
        device_stmt = device_stmt.where(ControlDevice.registration_id == registration_id)
        point_stmt = point_stmt.where(ControlPoint.registration_id == registration_id)
        scenario_stmt = scenario_stmt.where(ControlScenario.registration_id == registration_id)
        event_stmt = event_stmt.where(ControlEvent.registration_id == registration_id)
        menu_stmt = menu_stmt.where(ControlMenu.registration_id == registration_id)

    point_type_query = select(ControlPoint.point_type, func.count())
    scenario_type_query = select(ControlScenario.scenario_type, func.count())
    area_query = select(ControlDevice.area_hint, func.count()).where(ControlDevice.area_hint != "")

    if registration_id is not None:
        point_type_query = point_type_query.where(ControlPoint.registration_id == registration_id)
        scenario_type_query = scenario_type_query.where(ControlScenario.registration_id == registration_id)
        area_query = area_query.where(ControlDevice.registration_id == registration_id)

    point_type_rows = db.execute(
        point_type_query.group_by(ControlPoint.point_type).order_by(func.count().desc())
    ).all()
    scenario_type_rows = db.execute(
        scenario_type_query.group_by(ControlScenario.scenario_type).order_by(func.count().desc())
    ).all()
    area_rows = db.execute(
        area_query.group_by(ControlDevice.area_hint).order_by(func.count().desc())
    ).all()

    recent_devices = db.scalars(device_stmt.order_by(ControlDevice.id.desc()).limit(6)).all()
    recent_points = db.scalars(point_stmt.order_by(ControlPoint.id.desc()).limit(6)).all()
    recent_scenarios = db.scalars(scenario_stmt.order_by(ControlScenario.id.desc()).limit(6)).all()
    recent_events = db.scalars(event_stmt.order_by(ControlEvent.id.desc()).limit(6)).all()
    recent_menus = db.scalars(menu_stmt.order_by(ControlMenu.id.desc()).limit(6)).all()

    return {
        "device_count": db.scalar(select(func.count()).select_from(device_stmt.subquery())) or 0,
        "point_count": db.scalar(select(func.count()).select_from(point_stmt.subquery())) or 0,
        "scenario_count": db.scalar(select(func.count()).select_from(scenario_stmt.subquery())) or 0,
        "event_count": db.scalar(select(func.count()).select_from(event_stmt.subquery())) or 0,
        "menu_count": db.scalar(select(func.count()).select_from(menu_stmt.subquery())) or 0,
        "point_type_breakdown": [
            {"point_type": normalize_text(row[0]) or "unknown", "count": row[1]} for row in point_type_rows
        ],
        "scenario_type_breakdown": [
            {"scenario_type": normalize_text(row[0]) or "unknown", "count": row[1]} for row in scenario_type_rows
        ],
        "area_breakdown": [
            {"area_hint": normalize_text(row[0]), "count": row[1]} for row in area_rows
        ],
        "recent_devices": [
            {
                "id": row.id,
                "display_name": normalize_text(row.display_name),
                "device_type": normalize_text(row.device_type),
                "vendor": normalize_text(row.vendor),
                "area_hint": normalize_text(row.area_hint),
                "control_status": row.control_status,
                "track_label": normalize_text(registration_map[row.registration_id].display_name)
                if row.registration_id in registration_map
                else "",
            }
            for row in recent_devices
        ],
        "recent_points": [
            {
                "id": row.id,
                "display_name": normalize_text(row.display_name),
                "point_type": normalize_text(row.point_type),
                "point_code": normalize_text(row.point_code),
                "point_status": row.point_status,
                "current_value": normalize_text(row.current_value),
            }
            for row in recent_points
        ],
        "recent_scenarios": [
            {
                "id": row.id,
                "display_name": normalize_text(row.display_name),
                "scenario_type": normalize_text(row.scenario_type),
                "trigger_mode": normalize_text(row.trigger_mode),
                "scenario_status": row.scenario_status,
                "area_hint": normalize_text(row.area_hint),
            }
            for row in recent_scenarios
        ],
        "recent_events": [
            {
                "id": row.id,
                "title": normalize_text(row.title),
                "event_type": normalize_text(row.event_type),
                "severity": row.severity,
                "event_status": row.event_status,
                "triggered_at": normalize_text(row.triggered_at),
            }
            for row in recent_events
        ],
        "recent_menus": [
            {
                "id": row.id,
                "display_name": normalize_text(row.display_name),
                "menu_key": normalize_text(row.menu_key),
                "parent_menu_key": normalize_text(row.parent_menu_key),
                "route_path": normalize_text(row.route_path),
                "page_type": normalize_text(row.page_type),
            }
            for row in recent_menus
        ],
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    return _summary_payload(db)


@router.get("/registrations/{registration_id}/summary")
def registration_summary(registration_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ControlPlatformRegistration, registration_id)
    if not row:
        return {"registration_id": registration_id, "display_name": "", "track_key": "", **_summary_payload(db, registration_id)}
    return {
        "registration_id": row.id,
        "display_name": normalize_text(row.display_name),
        "track_key": row.track_key,
        **_summary_payload(db, registration_id),
    }


@router.get("/compare")
def compare_registrations(
    left_registration_id: int,
    right_registration_id: int,
    db: Session = Depends(get_db),
) -> dict:
    left_row = db.get(ControlPlatformRegistration, left_registration_id)
    right_row = db.get(ControlPlatformRegistration, right_registration_id)

    left = _summary_payload(db, left_registration_id)
    right = _summary_payload(db, right_registration_id)

    metrics = ["device_count", "point_count", "scenario_count", "event_count", "menu_count"]
    difference = {
        key: {
            "left": left[key],
            "right": right[key],
            "delta": (left[key] or 0) - (right[key] or 0),
        }
        for key in metrics
    }

    def _normalize_breakdown(items: list[dict], field: str) -> dict[str, int]:
        return {normalize_text(item.get(field)): item.get("count", 0) for item in items if normalize_text(item.get(field))}

    left_point_types = _normalize_breakdown(left["point_type_breakdown"], "point_type")
    right_point_types = _normalize_breakdown(right["point_type_breakdown"], "point_type")
    left_scenario_types = _normalize_breakdown(left["scenario_type_breakdown"], "scenario_type")
    right_scenario_types = _normalize_breakdown(right["scenario_type_breakdown"], "scenario_type")
    left_areas = _normalize_breakdown(left["area_breakdown"], "area_hint")
    right_areas = _normalize_breakdown(right["area_breakdown"], "area_hint")

    def _shared_and_unique(left_map: dict[str, int], right_map: dict[str, int]) -> dict:
        left_keys = set(left_map)
        right_keys = set(right_map)
        shared = sorted(left_keys & right_keys)
        return {
            "shared": [{"name": key, "left": left_map[key], "right": right_map[key]} for key in shared[:12]],
            "left_only": [{"name": key, "count": left_map[key]} for key in sorted(left_keys - right_keys)[:12]],
            "right_only": [{"name": key, "count": right_map[key]} for key in sorted(right_keys - left_keys)[:12]],
        }

    return {
        "left": {
            "registration_id": left_registration_id,
            "display_name": normalize_text(left_row.display_name) if left_row else "",
            "track_key": left_row.track_key if left_row else "",
            **left,
        },
        "right": {
            "registration_id": right_registration_id,
            "display_name": normalize_text(right_row.display_name) if right_row else "",
            "track_key": right_row.track_key if right_row else "",
            **right,
        },
        "difference": difference,
        "point_type_compare": _shared_and_unique(left_point_types, right_point_types),
        "scenario_type_compare": _shared_and_unique(left_scenario_types, right_scenario_types),
        "area_compare": _shared_and_unique(left_areas, right_areas),
    }


@router.get("/devices")
def list_devices(
    db: Session = Depends(get_db),
    registration_id: int | None = None,
    q: str = Query(default=""),
    limit: int = 120,
) -> list[dict]:
    stmt = select(ControlDevice)
    if registration_id:
        stmt = stmt.where(ControlDevice.registration_id == registration_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            ControlDevice.display_name.ilike(like)
            | ControlDevice.device_type.ilike(like)
            | ControlDevice.area_hint.ilike(like)
            | ControlDevice.external_key.ilike(like)
        )
    rows = db.scalars(stmt.order_by(ControlDevice.id.desc()).limit(min(max(limit, 20), 500))).all()
    return [
        {
            "id": row.id,
            "registration_id": row.registration_id,
            "display_name": normalize_text(row.display_name),
            "device_type": normalize_text(row.device_type),
            "vendor": normalize_text(row.vendor),
            "model": normalize_text(row.model),
            "area_hint": normalize_text(row.area_hint),
            "control_status": row.control_status,
            "external_key": normalize_text(row.external_key),
        }
        for row in rows
    ]


@router.get("/points")
def list_points(
    db: Session = Depends(get_db),
    registration_id: int | None = None,
    q: str = Query(default=""),
    limit: int = 160,
) -> list[dict]:
    stmt = select(ControlPoint)
    if registration_id:
        stmt = stmt.where(ControlPoint.registration_id == registration_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            ControlPoint.display_name.ilike(like)
            | ControlPoint.point_type.ilike(like)
            | ControlPoint.point_code.ilike(like)
        )
    rows = db.scalars(stmt.order_by(ControlPoint.id.desc()).limit(min(max(limit, 20), 500))).all()
    return [
        {
            "id": row.id,
            "registration_id": row.registration_id,
            "control_device_id": row.control_device_id,
            "display_name": normalize_text(row.display_name),
            "point_type": normalize_text(row.point_type),
            "point_code": normalize_text(row.point_code),
            "io_direction": row.io_direction,
            "point_status": row.point_status,
            "current_value": normalize_text(row.current_value),
            "units": normalize_text(row.units),
        }
        for row in rows
    ]


@router.get("/scenarios")
def list_scenarios(
    db: Session = Depends(get_db),
    registration_id: int | None = None,
    q: str = Query(default=""),
    limit: int = 120,
) -> list[dict]:
    stmt = select(ControlScenario)
    if registration_id:
        stmt = stmt.where(ControlScenario.registration_id == registration_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            ControlScenario.display_name.ilike(like)
            | ControlScenario.scenario_type.ilike(like)
            | ControlScenario.scenario_code.ilike(like)
            | ControlScenario.area_hint.ilike(like)
        )
    rows = db.scalars(stmt.order_by(ControlScenario.id.desc()).limit(min(max(limit, 20), 500))).all()
    return [
        {
            "id": row.id,
            "registration_id": row.registration_id,
            "display_name": normalize_text(row.display_name),
            "scenario_type": normalize_text(row.scenario_type),
            "scenario_code": normalize_text(row.scenario_code),
            "trigger_mode": normalize_text(row.trigger_mode),
            "scenario_status": row.scenario_status,
            "area_hint": normalize_text(row.area_hint),
        }
        for row in rows
    ]


@router.get("/events")
def list_events(
    db: Session = Depends(get_db),
    registration_id: int | None = None,
    q: str = Query(default=""),
    limit: int = 160,
) -> list[dict]:
    stmt = select(ControlEvent)
    if registration_id:
        stmt = stmt.where(ControlEvent.registration_id == registration_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            ControlEvent.title.ilike(like)
            | ControlEvent.event_type.ilike(like)
            | ControlEvent.event_code.ilike(like)
        )
    rows = db.scalars(stmt.order_by(ControlEvent.id.desc()).limit(min(max(limit, 20), 500))).all()
    return [
        {
            "id": row.id,
            "registration_id": row.registration_id,
            "control_device_id": row.control_device_id,
            "event_code": normalize_text(row.event_code),
            "event_type": normalize_text(row.event_type),
            "title": normalize_text(row.title),
            "severity": row.severity,
            "event_status": row.event_status,
            "triggered_at": normalize_text(row.triggered_at),
            "details": normalize_text(row.details),
        }
        for row in rows
    ]


@router.get("/menus")
def list_menus(
    db: Session = Depends(get_db),
    registration_id: int | None = None,
    q: str = Query(default=""),
    limit: int = 200,
) -> list[dict]:
    stmt = select(ControlMenu)
    if registration_id:
        stmt = stmt.where(ControlMenu.registration_id == registration_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            ControlMenu.display_name.ilike(like)
            | ControlMenu.menu_key.ilike(like)
            | ControlMenu.route_path.ilike(like)
        )
    rows = db.scalars(
        stmt.order_by(ControlMenu.sort_index.asc(), ControlMenu.id.asc()).limit(min(max(limit, 20), 500))
    ).all()
    return [
        {
            "id": row.id,
            "registration_id": row.registration_id,
            "menu_key": normalize_text(row.menu_key),
            "parent_menu_key": normalize_text(row.parent_menu_key),
            "display_name": normalize_text(row.display_name),
            "route_path": normalize_text(row.route_path),
            "page_type": normalize_text(row.page_type),
            "sort_index": row.sort_index,
            "notes": normalize_text(row.notes),
        }
        for row in rows
    ]


@router.get("/registrations/{registration_id}/menu-tree")
def registration_menu_tree(
    registration_id: int,
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(ControlMenu)
        .where(ControlMenu.registration_id == registration_id)
        .order_by(ControlMenu.sort_index.asc(), ControlMenu.id.asc())
    ).all()

    items = [
        {
            "id": row.id,
            "menu_key": normalize_text(row.menu_key),
            "parent_menu_key": normalize_text(row.parent_menu_key),
            "display_name": normalize_text(row.display_name),
            "route_path": normalize_text(row.route_path),
            "page_type": normalize_text(row.page_type),
            "sort_index": row.sort_index,
            "notes": normalize_text(row.notes),
            "children": [],
        }
        for row in rows
    ]

    item_map = {item["menu_key"] or f"row-{item['id']}": item for item in items}
    roots: list[dict] = []

    for item in items:
        parent_key = item["parent_menu_key"]
        if parent_key and parent_key in item_map and parent_key != item["menu_key"]:
            item_map[parent_key]["children"].append(item)
        else:
            roots.append(item)

    for item in items:
        item["children"].sort(key=lambda child: (child["sort_index"], child["display_name"]))

    roots.sort(key=lambda item: (item["sort_index"], item["display_name"]))

    return {
        "registration_id": registration_id,
        "root_count": len(roots),
        "menu_count": len(items),
        "roots": roots,
    }

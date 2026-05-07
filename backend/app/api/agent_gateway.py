from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.agent_service import AgentServiceRegistration
from app.schemas.agent_service import AgentServiceOut, AgentServiceUpsert
from app.services.platform_capabilities import agent_gateway_summary
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_out(row: AgentServiceRegistration) -> AgentServiceOut:
    return AgentServiceOut(
        id=row.id,
        service_key=row.service_key,
        display_name=normalize_text(row.display_name),
        service_type=row.service_type,
        endpoint_url=row.endpoint_url,
        auth_mode=row.auth_mode,
        access_scope=row.access_scope,
        enabled=row.enabled,
        read_only_first=row.read_only_first,
        status=row.status,
        notes=normalize_text(row.notes),
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(AgentServiceRegistration).order_by(AgentServiceRegistration.display_name)).all()
    base = agent_gateway_summary()
    service_type_breakdown: dict[str, int] = {}
    enabled_count = 0
    read_only_count = 0

    for row in rows:
        service_type_breakdown[row.service_type] = service_type_breakdown.get(row.service_type, 0) + 1
        if row.enabled:
            enabled_count += 1
        if row.read_only_first:
            read_only_count += 1

    base.update(
        {
            "service_count": len(rows),
            "enabled_count": enabled_count,
            "read_only_count": read_only_count,
            "service_type_breakdown": [
                {"service_type": key, "count": value}
                for key, value in sorted(service_type_breakdown.items(), key=lambda item: (-item[1], item[0]))
            ],
            "services": [_to_out(row).model_dump() for row in rows],
        }
    )
    return base


@router.get("/services", response_model=list[AgentServiceOut])
def list_services(db: Session = Depends(get_db)) -> list[AgentServiceOut]:
    rows = db.scalars(select(AgentServiceRegistration).order_by(AgentServiceRegistration.display_name)).all()
    return [_to_out(row) for row in rows]


@router.post("/services", response_model=AgentServiceOut)
def create_service(payload: AgentServiceUpsert, db: Session = Depends(get_db)) -> AgentServiceOut:
    existing = db.scalar(select(AgentServiceRegistration).where(AgentServiceRegistration.service_key == payload.service_key))
    if existing:
        raise HTTPException(status_code=409, detail="service_key_exists")

    row = AgentServiceRegistration(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/services/{service_id}", response_model=AgentServiceOut)
def update_service(service_id: int, payload: AgentServiceUpsert, db: Session = Depends(get_db)) -> AgentServiceOut:
    row = db.get(AgentServiceRegistration, service_id)
    if not row:
        raise HTTPException(status_code=404, detail="service_not_found")

    conflict = db.scalar(
        select(AgentServiceRegistration).where(
            AgentServiceRegistration.service_key == payload.service_key,
            AgentServiceRegistration.id != service_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="service_key_exists")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)

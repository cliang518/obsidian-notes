from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.storage_provider import StorageProviderRegistration
from app.schemas.storage_provider import StorageProviderOut, StorageProviderUpsert
from app.services.platform_capabilities import storage_resource_summary
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_out(row: StorageProviderRegistration) -> StorageProviderOut:
    return StorageProviderOut(
        id=row.id,
        provider_key=row.provider_key,
        display_name=normalize_text(row.display_name),
        provider_type=row.provider_type,
        endpoint_url=row.endpoint_url,
        bucket_or_share=normalize_text(row.bucket_or_share),
        auth_mode=row.auth_mode,
        usage_scope=row.usage_scope,
        enabled=row.enabled,
        writable=row.writable,
        status=row.status,
        notes=normalize_text(row.notes),
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(StorageProviderRegistration).order_by(StorageProviderRegistration.display_name)).all()
    base = storage_resource_summary()
    enabled_count = sum(1 for row in rows if row.enabled)
    writable_count = sum(1 for row in rows if row.writable)
    base.update(
        {
            "provider_count": len(rows),
            "enabled_count": enabled_count,
            "writable_count": writable_count,
            "providers": [_to_out(row).model_dump() for row in rows],
        }
    )
    return base


@router.get("/providers", response_model=list[StorageProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[StorageProviderOut]:
    rows = db.scalars(select(StorageProviderRegistration).order_by(StorageProviderRegistration.display_name)).all()
    return [_to_out(row) for row in rows]


@router.post("/providers", response_model=StorageProviderOut)
def create_provider(payload: StorageProviderUpsert, db: Session = Depends(get_db)) -> StorageProviderOut:
    existing = db.scalar(
        select(StorageProviderRegistration).where(StorageProviderRegistration.provider_key == payload.provider_key)
    )
    if existing:
        raise HTTPException(status_code=409, detail="provider_key_exists")

    row = StorageProviderRegistration(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/providers/{provider_id}", response_model=StorageProviderOut)
def update_provider(provider_id: int, payload: StorageProviderUpsert, db: Session = Depends(get_db)) -> StorageProviderOut:
    row = db.get(StorageProviderRegistration, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="provider_not_found")

    conflict = db.scalar(
        select(StorageProviderRegistration).where(
            StorageProviderRegistration.provider_key == payload.provider_key,
            StorageProviderRegistration.id != provider_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="provider_key_exists")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)

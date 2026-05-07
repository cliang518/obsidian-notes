import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.llm_config import LlmProviderConfig
from app.schemas.llm import LlmProviderOut, LlmProviderUpsert
from app.services.platform_capabilities import llm_provider_summary
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_out(row: LlmProviderConfig) -> LlmProviderOut:
    return LlmProviderOut(
        id=row.id,
        provider_key=row.provider_key,
        display_name=normalize_text(row.display_name),
        provider_type=row.provider_type,
        base_url=row.base_url,
        default_model=row.default_model,
        api_key_env_name=row.api_key_env_name,
        enabled=row.enabled,
        notes=normalize_text(row.notes),
        api_key_present=bool(row.api_key_env_name and os.getenv(row.api_key_env_name)),
    )


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    configs = db.scalars(select(LlmProviderConfig).order_by(LlmProviderConfig.display_name)).all()
    base = llm_provider_summary()
    provider_type_counts: dict[str, int] = {}
    enabled_count = 0
    key_ready_count = 0
    providers = []

    for row in configs:
        provider_type_counts[row.provider_type] = provider_type_counts.get(row.provider_type, 0) + 1
        if row.enabled:
            enabled_count += 1
        if row.api_key_env_name and os.getenv(row.api_key_env_name):
            key_ready_count += 1
        providers.append(_to_out(row).model_dump())

    base.update(
        {
            "provider_count": len(configs),
            "enabled_count": enabled_count,
            "key_ready_count": key_ready_count,
            "provider_type_breakdown": [
                {"provider_type": key, "count": value}
                for key, value in sorted(provider_type_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "providers": providers,
        }
    )
    return base


@router.get("/providers", response_model=list[LlmProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[LlmProviderOut]:
    rows = db.scalars(select(LlmProviderConfig).order_by(LlmProviderConfig.display_name)).all()
    return [_to_out(row) for row in rows]


@router.post("/providers", response_model=LlmProviderOut)
def create_provider(payload: LlmProviderUpsert, db: Session = Depends(get_db)) -> LlmProviderOut:
    existing = db.scalar(select(LlmProviderConfig).where(LlmProviderConfig.provider_key == payload.provider_key))
    if existing:
        raise HTTPException(status_code=409, detail="provider_key_exists")

    row = LlmProviderConfig(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/providers/{provider_id}", response_model=LlmProviderOut)
def update_provider(provider_id: int, payload: LlmProviderUpsert, db: Session = Depends(get_db)) -> LlmProviderOut:
    row = db.get(LlmProviderConfig, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="provider_not_found")

    conflict = db.scalar(
        select(LlmProviderConfig).where(
            LlmProviderConfig.provider_key == payload.provider_key,
            LlmProviderConfig.id != provider_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="provider_key_exists")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_out(row)

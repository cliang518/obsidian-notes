from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.settings import settings
from app.models.user_account import UserAccount
from app.schemas.system import HealthResponse
from app.services.auth import get_current_user, require_roles
from app.services.backup_service import (
    create_v2_state_backup,
    delete_v2_backup,
    list_v2_backups,
    prune_v2_backups,
    resolve_backup_path,
)
from app.services.runtime_probe import collect_runtime_snapshot


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
    )


@router.get("/runtime")
def runtime(_: UserAccount = Depends(get_current_user)) -> dict:
    return collect_runtime_snapshot()


@router.get("/backups")
def backups(
    limit: int = Query(default=20, ge=1, le=100),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    return {
        "items": list_v2_backups(limit=limit),
    }


@router.post("/backup")
def create_backup(
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    result = create_v2_state_backup()
    return {
        "ok": True,
        "backup": result,
    }


@router.post("/backups/prune")
def prune_backups(
    keep_latest: int = Query(default=20, ge=1, le=365),
    dry_run: bool = Query(default=True),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    result = prune_v2_backups(keep_latest=keep_latest, dry_run=dry_run)
    return {
        "ok": True,
        "result": result,
    }


@router.get("/backups/{filename}")
def download_backup(
    filename: str,
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> FileResponse:
    path = resolve_backup_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="backup_not_found")
    return FileResponse(path=str(path), filename=path.name, media_type="application/zip")


@router.delete("/backups/{filename}")
def delete_backup(
    filename: str,
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> dict:
    result = delete_v2_backup(filename)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="backup_not_found")
    return {
        "ok": True,
        "result": result,
    }

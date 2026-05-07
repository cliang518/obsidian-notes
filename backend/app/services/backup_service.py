from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import zipfile

from app.core.settings import settings


def backup_root_dir() -> Path:
    return settings.root_dir.parent / "backups"


def _iter_backup_sources() -> list[tuple[Path, str]]:
    root = settings.root_dir
    return [
        (root / "docs", "docs"),
        (root / "frontend" / "src", "frontend-src"),
        (root / "backend" / "app", "backend-app"),
        (root / "tools", "tools"),
        (root / "runtime" / "platform_v2.db", "runtime-platform_v2.db"),
        (root / "runtime" / "logs", "runtime-logs"),
    ]


def _write_path_to_zip(zipf: zipfile.ZipFile, source: Path, dest_prefix: str) -> None:
    if source.is_file():
        zipf.write(source, arcname=dest_prefix)
        return

    for child in source.rglob("*"):
        if child.is_file():
            rel = child.relative_to(source).as_posix()
            zipf.write(child, arcname=f"{dest_prefix}/{rel}")


def create_v2_state_backup() -> dict:
    root = backup_root_dir()
    root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = root / f"v2-state-{timestamp}.zip"

    included: list[dict] = []
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for source, dest in _iter_backup_sources():
            if not source.exists():
                continue
            _write_path_to_zip(zipf, source, dest)
            included.append(
                {
                    "source": str(source),
                    "archive_prefix": dest,
                }
            )

        manifest = {
            "timestamp": timestamp,
            "generated_at": datetime.now().isoformat(),
            "root_dir": str(settings.root_dir),
            "database_path": str(settings.database_path),
            "included": included,
            "note": "V2 source, docs, logs, and runtime database snapshot",
        }
        zipf.writestr("backup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    stat = zip_path.stat()
    return {
        "filename": zip_path.name,
        "path": str(zip_path),
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "included_count": len(included),
    }


def list_v2_backups(limit: int = 30) -> list[dict]:
    rows: list[dict] = []
    for item in _sorted_backup_files():
        stat = item.stat()
        rows.append(
            {
                "filename": item.name,
                "path": str(item),
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return rows[: max(1, min(limit, 200))]


def resolve_backup_path(filename: str) -> Path | None:
    if not filename.endswith(".zip"):
        return None
    if "/" in filename or "\\" in filename:
        return None
    path = backup_root_dir() / filename
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    root = backup_root_dir().resolve()
    if root not in resolved.parents:
        return None
    return resolved


def delete_v2_backup(filename: str) -> dict:
    path = resolve_backup_path(filename)
    if not path:
        return {"deleted": False, "filename": filename, "reason": "not_found"}

    stat = path.stat()
    path.unlink(missing_ok=False)
    return {
        "deleted": True,
        "filename": path.name,
        "size_bytes": stat.st_size,
        "deleted_at": datetime.now().isoformat(),
    }


def prune_v2_backups(keep_latest: int = 20, dry_run: bool = True) -> dict:
    keep = max(1, min(int(keep_latest), 365))
    files = _sorted_backup_files()

    keep_files = files[:keep]
    prune_files = files[keep:]

    deleted: list[str] = []
    failed: list[dict] = []
    for item in prune_files:
        if dry_run:
            deleted.append(item.name)
            continue
        try:
            item.unlink(missing_ok=False)
            deleted.append(item.name)
        except FileNotFoundError:
            failed.append({"filename": item.name, "reason": "not_found"})
        except OSError as exc:
            failed.append({"filename": item.name, "reason": str(exc)})

    return {
        "dry_run": bool(dry_run),
        "keep_latest": keep,
        "before_count": len(files),
        "kept_count": len(keep_files),
        "candidate_count": len(prune_files),
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted_filenames": deleted,
        "failed_items": failed,
    }


def _sorted_backup_files() -> list[Path]:
    root = backup_root_dir()
    if not root.exists():
        return []

    files = [item for item in root.glob("v2-state-*.zip") if item.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files

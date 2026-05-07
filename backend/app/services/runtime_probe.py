from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    import psutil
except ModuleNotFoundError:
    psutil = None

from app.core.settings import settings


def _service_status(port: int) -> dict:
    if psutil is None:
        return {
            "port": port,
            "listening": False,
            "pid": None,
            "note": "psutil_not_installed",
        }
    listening = False
    pid = None
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            listening = True
            pid = conn.pid
            break
    return {
        "port": port,
        "listening": listening,
        "pid": pid,
    }


def _top_processes(limit: int = 8) -> list[dict]:
    if psutil is None:
        return []
    items: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "create_time"]):
        try:
            info = proc.info
            rss = getattr(info.get("memory_info"), "rss", 0) or 0
            items.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "memory_mb": round(rss / 1024 / 1024, 1),
                    "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 1),
                    "create_time": info.get("create_time"),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    items.sort(key=lambda item: (item["cpu_percent"], item["memory_mb"]), reverse=True)
    return items[:limit]


def _tracked_processes() -> list[dict]:
    if psutil is None:
        return []
    tracked_names = {"python.exe", "python", "node.exe", "node", "YongjiaWeakCurrentV2Tray.exe", "YongjiaWeakCurrentV2Tray"}
    results: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "create_time"]):
        try:
            name = proc.info["name"] or ""
            if name not in tracked_names:
                continue
            rss = getattr(proc.info.get("memory_info"), "rss", 0) or 0
            results.append(
                {
                    "pid": proc.info["pid"],
                    "name": name,
                    "memory_mb": round(rss / 1024 / 1024, 1),
                    "cpu_percent": round(float(proc.info.get("cpu_percent") or 0.0), 1),
                    "create_time": proc.info.get("create_time"),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    results.sort(key=lambda item: (item["name"], item["pid"]))
    return results


def collect_runtime_snapshot() -> dict:
    disk = None
    try:
        disk = Path(settings.runtime_dir)
    except Exception:
        disk = None

    if psutil is None:
        return {
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runtime_dir": str(settings.runtime_dir),
            "database_path": str(settings.database_path),
            "cpu_percent": 0.0,
            "memory": {
                "total_gb": 0.0,
                "available_gb": 0.0,
                "used_percent": 0.0,
                "note": "psutil_not_installed",
            },
            "disk": {
                "total_gb": 0.0,
                "free_gb": 0.0,
                "used_percent": 0.0,
            },
            "services": {
                "backend_8011": _service_status(8011),
                "frontend_3011": _service_status(3011),
            },
            "tracked_processes": [],
            "top_processes": [],
        }

    vm = psutil.virtual_memory()
    disk_usage = psutil.disk_usage(str(disk.anchor or settings.runtime_dir))
    cpu_percent = psutil.cpu_percent(interval=0.25)

    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_dir": str(settings.runtime_dir),
        "database_path": str(settings.database_path),
        "cpu_percent": round(cpu_percent, 1),
        "memory": {
            "total_gb": round(vm.total / 1024 / 1024 / 1024, 2),
            "available_gb": round(vm.available / 1024 / 1024 / 1024, 2),
            "used_percent": round(vm.percent, 1),
        },
        "disk": {
            "total_gb": round(disk_usage.total / 1024 / 1024 / 1024, 2),
            "free_gb": round(disk_usage.free / 1024 / 1024 / 1024, 2),
            "used_percent": round(disk_usage.percent, 1),
        },
        "services": {
            "backend_8011": _service_status(8011),
            "frontend_3011": _service_status(3011),
        },
        "tracked_processes": _tracked_processes(),
        "top_processes": _top_processes(),
    }

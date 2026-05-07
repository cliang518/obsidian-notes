from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "runtime" / "logs"
WATCHER_LOG = LOG_DIR / "window-flash-watcher.log"
PID_FILE = LOG_DIR / "window-flash-watcher.pid"
POLL_SECONDS = 0.6

CONSOLE_NAMES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "cscript.exe",
    "wscript.exe",
    "conhost.exe",
}

IGNORE_KEYWORDS = (
    "window_flash_watcher.py",
    "get-ciminstance win32_process",
    "codex.exe app-server",
    "openai.codex",
    "npm-cli.js run build",
    "vite build",
    "tasklist /v /fo csv",
)

IGNORE_PARENT_NAMES = {
    "codex.exe",
    "conhost.exe",
}


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_log(event: str, payload: dict[str, object]) -> None:
    ensure_dirs()
    line = {
        "ts": stamp(),
        "event": event,
        **payload,
    }
    with WATCHER_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def safe_cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except Exception:
        return ""


def safe_parent(proc: psutil.Process) -> dict[str, object]:
    try:
        parent = proc.parent()
        if not parent:
            return {}
        return {
            "parent_pid": parent.pid,
            "parent_name": parent.name(),
            "parent_cmdline": safe_cmdline(parent)[:320],
        }
    except Exception:
        return {}


def should_ignore(cmdline: str) -> bool:
    lowered = cmdline.lower()
    return any(keyword in lowered for keyword in IGNORE_KEYWORDS)


def should_ignore_parent(parent_info: dict[str, object]) -> bool:
    parent_name = str(parent_info.get("parent_name") or "").lower()
    parent_cmdline = str(parent_info.get("parent_cmdline") or "").lower()
    if parent_name in IGNORE_PARENT_NAMES:
        return True
    return any(keyword in parent_cmdline for keyword in IGNORE_KEYWORDS)


def capture_console_processes() -> dict[int, dict[str, object]]:
    snapshot: dict[int, dict[str, object]] = {}
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in CONSOLE_NAMES:
                continue
            cmdline = safe_cmdline(proc)
            if should_ignore(cmdline):
                continue
            parent_info = safe_parent(proc)
            if should_ignore_parent(parent_info):
                continue
            snapshot[proc.pid] = {
                "pid": proc.pid,
                "name": name,
                "cmdline": cmdline[:500],
                "create_time": proc.info.get("create_time"),
                **parent_info,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            write_log("scan_error", {"error": repr(exc)})
    return snapshot


def main() -> int:
    ensure_dirs()
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    write_log("watcher_started", {"pid": os.getpid(), "python": sys.executable})
    known = capture_console_processes()

    try:
        while True:
            current = capture_console_processes()
            for pid, info in current.items():
                if pid not in known:
                    write_log("new_console_process", info)
            known = current
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        write_log("watcher_stopped", {"reason": "keyboard_interrupt"})
        return 0
    except Exception as exc:
        write_log("watcher_failed", {"error": repr(exc)})
        return 1
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

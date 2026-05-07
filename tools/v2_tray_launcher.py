from __future__ import annotations

import atexit
import ctypes
import msvcrt
import os
import psutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image, ImageDraw, ImageFont


if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent

RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_SRC_DIR = FRONTEND_DIR / "src"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
FRONTEND_SERVER_SCRIPT = ROOT / "tools" / "spa_static_server.py"
STOP_SCRIPT = ROOT / "stop-v2-stack.ps1"
FRONTEND_URL = "http://127.0.0.1:3011"
BACKEND_HEALTH_URL = "http://127.0.0.1:8011/api/system/health"
BACKEND_PORT = 8011
FRONTEND_PORT = 3011
SINGLETON_PORT = 39211
SERVICE_PATTERNS = {
    "backend": ["backend\\run.py"],
    "frontend": ["tools\\spa_static_server.py"],
}
STARTUP_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_VBS = STARTUP_DIR / "YongjiaWeakCurrentV2Tray.vbs"
MUTEX_NAME = "Global\\YongjiaWeakCurrentV2TraySingleton"
CREATE_NO_WINDOW = 0x08000000
WATCHDOG_INTERVAL_SECONDS = 45

backend_proc: Optional[subprocess.Popen] = None
frontend_proc: Optional[subprocess.Popen] = None
backend_log_handle = None
frontend_log_handle = None
icon_instance: Optional[pystray.Icon] = None
watchdog_thread: Optional[threading.Thread] = None
watchdog_stop_event = threading.Event()
mutex_handle = None
lock_file_handle = None
singleton_socket = None
shutdown_requested = False


def ensure_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)


def log_line(message: str) -> None:
    ensure_dirs()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with (LOG_DIR / "v2-tray.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def notify(title: str, message: str) -> None:
    if icon_instance is None:
        log_line(f"notify_skipped title={title} message={message}")
        return
    try:
        icon_instance.notify(message, title)
    except Exception as exc:  # pragma: no cover
        log_line(f"notify_failed title={title} exc={exc}")


def show_message_box(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        log_line(f"message_box_failed title={title} message={message}")


def _supports_modules(python_path: Path, modules: list[str]) -> bool:
    try:
        code = (
            "import importlib.util as u, sys;"
            f"mods={modules!r};"
            "sys.exit(0 if all(u.find_spec(m) is not None for m in mods) else 1)"
        )
        result = subprocess.run(
            [str(python_path), "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def resolve_python(required_modules: Optional[list[str]] = None) -> Path:
    required_modules = required_modules or []
    candidates = [
        BACKEND_DIR / "venv" / "Scripts" / "python.exe",
        WORKSPACE_ROOT / "backend" / "venv" / "Scripts" / "python.exe",
        Path(r"D:\Python314\python.exe"),
        Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"),
    ]
    for candidate in candidates:
        if candidate.exists() and _supports_modules(candidate, required_modules):
            return candidate
    missing = ", ".join(required_modules) or "无"
    raise FileNotFoundError(f"未找到可用 Python 运行时，缺少模块：{missing}")


def prefer_windowless_python(python_path: Path) -> Path:
    if python_path.name.lower() != "python.exe":
        return python_path
    candidate = python_path.with_name("pythonw.exe")
    if candidate.exists():
        return candidate
    return python_path


def is_single_instance() -> bool:
    global mutex_handle, lock_file_handle, singleton_socket
    try:
        singleton_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        singleton_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        singleton_socket.bind(("127.0.0.1", SINGLETON_PORT))
        singleton_socket.listen(1)
        log_line(f"singleton_socket_bound port={SINGLETON_PORT}")
    except OSError as exc:
        log_line(f"singleton_socket_busy port={SINGLETON_PORT} exc={exc}")
        try:
            if singleton_socket:
                singleton_socket.close()
        finally:
            singleton_socket = None
        return False

    mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()
    log_line(f"singleton_check last_error={last_error}")
    if last_error == 183:
        return False

    lock_path = RUNTIME_DIR / "YongjiaWeakCurrentV2Tray.lock"
    lock_file_handle = lock_path.open("a+b")
    try:
        lock_file_handle.seek(0)
        msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        log_line(f"singleton_file_lock_busy path={lock_path} exc={exc}")
        try:
            lock_file_handle.close()
        finally:
            lock_file_handle = None
        return False
    return True


def find_other_tray_processes() -> list[dict[str, object]]:
    current_pid = os.getpid()
    parent_pid = os.getppid()
    current_name = "yongjiaweakcurrentv2tray.exe"
    launcher_name = "v2_tray_launcher.py"
    current_root = str(ROOT).lower()
    matches: list[dict[str, object]] = []

    for proc in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline", "create_time"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            ppid = int(proc.info.get("ppid") or 0)
            if pid in {0, current_pid, parent_pid}:
                continue

            name = str(proc.info.get("name") or "").lower()
            exe = str(proc.info.get("exe") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()

            if getattr(sys, "frozen", False):
                looks_like_tray = current_name in name or current_name in exe
            else:
                looks_like_tray = launcher_name in cmdline
            if not looks_like_tray:
                continue

            same_workspace = current_root in exe or current_root in cmdline
            if not same_workspace and getattr(sys, "frozen", False):
                continue

            matches.append(
                {
                    "pid": pid,
                    "ppid": ppid,
                    "name": name,
                    "exe": exe,
                    "cmdline": cmdline,
                    "create_time": float(proc.info.get("create_time") or 0),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            log_line(f"tray_process_scan_failed exc={exc}")
    matches.sort(key=lambda item: (item.get("create_time") or 0, item.get("pid") or 0))
    return matches


def release_mutex() -> None:
    global mutex_handle, lock_file_handle, singleton_socket
    if singleton_socket:
        try:
            singleton_socket.close()
        finally:
            singleton_socket = None
    if lock_file_handle:
        try:
            lock_file_handle.seek(0)
            msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            lock_file_handle.close()
        finally:
            lock_file_handle = None
    if mutex_handle:
        try:
            ctypes.windll.kernel32.ReleaseMutex(mutex_handle)
            ctypes.windll.kernel32.CloseHandle(mutex_handle)
        finally:
            mutex_handle = None


def create_icon() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (8, 22, 36, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=16, fill=(18, 74, 112, 255))
    draw.ellipse((10, 10, 54, 54), fill=(247, 207, 92, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((18, 22), "YJ", fill=(7, 35, 54, 255), font=font)
    return image


def startup_enabled() -> bool:
    return STARTUP_VBS.exists()


def _startup_vbs_content() -> str:
    tray_path = ROOT / "dist" / "YongjiaWeakCurrentV2Tray.exe"
    escaped = str(tray_path).replace('"', '""')
    return "\n".join(
        [
            'Set shell = CreateObject("WScript.Shell")',
            f'shell.Run Chr(34) & "{escaped}" & Chr(34), 0, False',
            "",
        ]
    )


def install_startup(icon=None, item=None) -> None:
    try:
        ensure_dirs()
        STARTUP_VBS.write_text(_startup_vbs_content(), encoding="utf-8")
        log_line(f"startup_installed path={STARTUP_VBS}")
        notify("V2 开机启动已开启", "托盘将在当前用户登录 Windows 后自动启动。")
    except Exception as exc:
        log_line(f"startup_install_failed exc={exc}")
        notify("V2 开机启动开启失败", str(exc))


def remove_startup(icon=None, item=None) -> None:
    try:
        if STARTUP_VBS.exists():
            STARTUP_VBS.unlink()
        log_line(f"startup_removed path={STARTUP_VBS}")
        notify("V2 开机启动已关闭", "已移除启动目录中的托盘自启动项。")
    except Exception as exc:
        log_line(f"startup_remove_failed exc={exc}")
        notify("V2 开机启动关闭失败", str(exc))


def _open_log_handle(name: str):
    ensure_dirs()
    return (LOG_DIR / name).open("a", encoding="utf-8")


def _http_ok(url: str) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=4) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.5)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def wait_http(url: str, seconds: float = 12.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _http_ok(url):
            return True
        time.sleep(0.8)
    return False


def wait_port(host: str, port: int, seconds: float = 8.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _listener_pid_for_port(port: int) -> int | None:
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
                return conn.pid
    except Exception as exc:
        log_line(f"listener_pid_lookup_failed port={port} exc={exc}")
    return None


def _terminate_pid(pid: int, label: str) -> bool:
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except psutil.TimeoutExpired:
            proc.kill()
        log_line(f"{label}_terminated pid={pid}")
        return True
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return True
    except Exception as exc:
        log_line(f"{label}_terminate_failed pid={pid} exc={exc}")
    return False


def _service_keep_pids(listener_ports: list[int]) -> set[int]:
    keep_pids: set[int] = set()
    current_root = str(ROOT).lower().replace("/", "\\")
    for port in listener_ports:
        pid = _listener_pid_for_port(port)
        if not pid:
            continue
        keep_pids.add(pid)
        try:
            proc = psutil.Process(pid)
            for parent in proc.parents():
                try:
                    cmdline = " ".join(parent.cmdline()).lower().replace("/", "\\")
                    exe = str(parent.exe() or "").lower().replace("/", "\\")
                    if current_root in cmdline or current_root in exe:
                        keep_pids.add(parent.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            log_line(f"service_keep_pid_lookup_failed port={port} pid={pid} exc={exc}")
    return keep_pids


def _iter_workspace_service_processes(service_kind: Optional[str] = None) -> list[psutil.Process]:
    matches: list[psutil.Process] = []
    current_root = str(ROOT).lower()
    requested_patterns = SERVICE_PATTERNS.get(service_kind) if service_kind else None
    patterns = requested_patterns or [pattern for values in SERVICE_PATTERNS.values() for pattern in values]
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            exe = str(proc.info.get("exe") or "").lower().replace("/", "\\")
            cmdline = " ".join(proc.info.get("cmdline") or []).lower().replace("/", "\\")
            if current_root not in exe and current_root not in cmdline:
                continue
            if not any(pattern in cmdline for pattern in patterns):
                continue
            matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            log_line(f"service_process_scan_failed exc={exc}")
    return matches


def cleanup_orphan_service_processes(service_kind: Optional[str] = None) -> dict[str, object]:
    if service_kind == "backend":
        keep_pids = _service_keep_pids([BACKEND_PORT])
    elif service_kind == "frontend":
        keep_pids = _service_keep_pids([FRONTEND_PORT])
    else:
        keep_pids = _service_keep_pids([BACKEND_PORT, FRONTEND_PORT])
    cleaned: list[int] = []
    failed: list[dict[str, object]] = []
    for proc in _iter_workspace_service_processes(service_kind):
        try:
            if proc.pid in keep_pids:
                continue
            if proc.is_running():
                cmdline = " ".join(proc.cmdline())[:360]
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                cleaned.append(proc.pid)
                log_line(f"orphan_service_terminated scope={service_kind or 'all'} pid={proc.pid} cmdline={cmdline}")
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except Exception as exc:
            failed.append({"pid": proc.pid, "reason": str(exc)})
    if cleaned or failed:
        label = service_kind or "all"
        log_line(f"cleanup_orphans scope={label} cleaned={cleaned} failed={failed}")
    return {"cleaned_pids": cleaned, "failed_items": failed}


def collect_stack_status() -> dict[str, object]:
    backend_pid = _listener_pid_for_port(BACKEND_PORT)
    frontend_pid = _listener_pid_for_port(FRONTEND_PORT)
    return {
        "backend_ok": _http_ok(BACKEND_HEALTH_URL),
        "frontend_ok": _port_open("127.0.0.1", FRONTEND_PORT),
        "backend_pid": backend_pid,
        "frontend_pid": frontend_pid,
        "startup_enabled": startup_enabled(),
        "frontend_url": FRONTEND_URL,
        "backend_health_url": BACKEND_HEALTH_URL,
        "log_dir": str(LOG_DIR),
    }


def ensure_frontend_dist() -> bool:
    dist_index = FRONTEND_DIST_DIR / "index.html"
    needs_build = not dist_index.exists()

    if not needs_build and FRONTEND_SRC_DIR.exists():
        dist_timestamp = dist_index.stat().st_mtime
        latest_source = max(
            (item.stat().st_mtime for item in FRONTEND_SRC_DIR.rglob("*") if item.is_file()),
            default=0,
        )
        if latest_source > dist_timestamp:
            needs_build = True

    if not needs_build:
        return True

    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        log_line("frontend_dist_missing package_json_missing")
        return False

    build_log = _open_log_handle("frontend-build.log")
    try:
        result = subprocess.run(
            ["cmd", "/c", "npm", "run", "build"],
            cwd=str(FRONTEND_DIR),
            stdout=build_log,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except Exception as exc:
        log_line(f"frontend_build_failed exc={exc}")
        return False
    finally:
        build_log.close()

    dist_ready = dist_index.exists()
    log_line(f"frontend_build_result exit={result.returncode} dist_ready={dist_ready}")
    return result.returncode == 0 and dist_ready


def start_backend() -> bool:
    global backend_proc, backend_log_handle

    if _http_ok(BACKEND_HEALTH_URL):
        return True
    backend_listener_pid = _listener_pid_for_port(BACKEND_PORT)
    if backend_listener_pid:
        if wait_http(BACKEND_HEALTH_URL, 8):
            return True
        log_line(f"backend_listener_unhealthy pid={backend_listener_pid}")
        _terminate_pid(backend_listener_pid, "backend_listener")
    if backend_proc and backend_proc.poll() is None:
        return True

    try:
        python = prefer_windowless_python(resolve_python(["uvicorn"]))
        backend_log_handle = _open_log_handle("backend.log")
        backend_proc = subprocess.Popen(
            [
                str(python),
                str(BACKEND_DIR / "run.py"),
            ],
            cwd=str(BACKEND_DIR),
            stdout=backend_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        log_line(f"backend_started pid={backend_proc.pid}")
        return True
    except Exception as exc:
        log_line(f"backend_start_failed exc={exc}")
        notify("V2 后端启动失败", str(exc))
        return False


def start_frontend() -> bool:
    global frontend_proc, frontend_log_handle

    if not ensure_frontend_dist():
        notify("V2 前端启动失败", "前端静态构建产物不存在，自动构建也没有成功。")
        return False

    if _port_open("127.0.0.1", FRONTEND_PORT):
        return True
    if frontend_proc and frontend_proc.poll() is None:
        return True

    try:
        python = prefer_windowless_python(resolve_python([]))
        frontend_log_handle = _open_log_handle("frontend.log")
        frontend_proc = subprocess.Popen(
            [
                str(python),
                str(FRONTEND_SERVER_SCRIPT),
                "--host",
                "0.0.0.0",
                "--port",
                str(FRONTEND_PORT),
                "--dir",
                str(FRONTEND_DIST_DIR),
                "--api-host",
                "127.0.0.1",
                "--api-port",
                str(BACKEND_PORT),
            ],
            cwd=str(ROOT),
            stdout=frontend_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        log_line(f"frontend_started pid={frontend_proc.pid}")
        return True
    except Exception as exc:
        log_line(f"frontend_start_failed exc={exc}")
        notify("V2 前端启动失败", str(exc))
        return False


def start_all(icon=None, item=None) -> None:
    cleanup_orphan_service_processes()
    backend_ok = start_backend()
    if backend_ok:
        backend_ok = wait_http(BACKEND_HEALTH_URL, 12)

    frontend_ok = start_frontend()
    if frontend_ok:
        frontend_ok = wait_port("127.0.0.1", FRONTEND_PORT, 8)

    if backend_ok and frontend_ok:
        log_line("stack_started")
        notify("V2 服务已启动", "后台服务和前端页面都已就绪，可以从托盘打开平台。")
    else:
        log_line(f"stack_start_partial backend_ok={backend_ok} frontend_ok={frontend_ok}")
        notify("V2 启动异常", "部分服务未能成功启动，请查看 runtime/logs。")


def open_frontend(icon=None, item=None) -> None:
    webbrowser.open(FRONTEND_URL)


def open_logs(icon=None, item=None) -> None:
    try:
        os.startfile(str(LOG_DIR))
    except Exception as exc:
        log_line(f"open_logs_failed exc={exc}")
        notify("V2 日志目录打开失败", str(exc))


def stop_all(icon=None, item=None) -> None:
    global backend_proc, frontend_proc, backend_log_handle, frontend_log_handle

    try:
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(STOP_SCRIPT)],
            cwd=str(ROOT),
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except Exception as exc:
        log_line(f"stop_script_failed exc={exc}")

    for proc_name, proc in (("backend", backend_proc), ("frontend", frontend_proc)):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                log_line(f"{proc_name}_terminated pid={proc.pid}")
            except Exception as exc:
                log_line(f"{proc_name}_terminate_failed pid={proc.pid} exc={exc}")
                try:
                    proc.kill()
                except Exception:
                    pass

    backend_proc = None
    frontend_proc = None

    for handle_name in ("backend_log_handle", "frontend_log_handle"):
        handle = globals()[handle_name]
        if handle:
            try:
                handle.close()
            except Exception:
                pass
            globals()[handle_name] = None

    log_line("stack_stopped")
    notify("V2 服务已停止", "后台服务和前端静态服务都已停止。")


def restart_services(icon=None, item=None) -> None:
    log_line("stack_restart_requested")
    stop_all()
    cleanup_orphan_service_processes()
    start_all()


def show_status(icon=None, item=None) -> None:
    status = collect_stack_status()
    backend_state = "正常" if status["backend_ok"] else "未就绪"
    frontend_state = "正常" if status["frontend_ok"] else "未就绪"
    startup_state = "已开启" if status["startup_enabled"] else "未开启"
    message = (
        f"后端：{backend_state} / PID {status['backend_pid'] or '-'}\n"
        f"前端：{frontend_state} / PID {status['frontend_pid'] or '-'}\n"
        f"开机启动：{startup_state}\n"
        f"首页：{status['frontend_url']}\n"
        f"日志目录：{status['log_dir']}"
    )
    notify("V2 当前状态", message)
    show_message_box("V2 当前状态", message)
    log_line(
        f"status backend={backend_state} backend_pid={status['backend_pid']} frontend={frontend_state} frontend_pid={status['frontend_pid']} startup={startup_state}"
    )


def _watchdog_loop() -> None:
    log_line("watchdog_started")
    while not watchdog_stop_event.wait(WATCHDOG_INTERVAL_SECONDS):
        try:
            backend_ok = _http_ok(BACKEND_HEALTH_URL)
            frontend_ok = _port_open("127.0.0.1", FRONTEND_PORT)
            cleanup_orphan_service_processes()

            if not backend_ok:
                log_line("watchdog_backend_unhealthy")
                cleanup_orphan_service_processes("backend")
                start_backend()
                if wait_http(BACKEND_HEALTH_URL, 8):
                    notify("V2 后端已恢复", "守护线程检测到后端异常后，已经自动恢复。")

            if not frontend_ok:
                log_line("watchdog_frontend_unhealthy")
                cleanup_orphan_service_processes("frontend")
                start_frontend()
                if wait_port("127.0.0.1", FRONTEND_PORT, 8):
                    notify("V2 前端已恢复", "守护线程检测到前端异常后，已经自动恢复。")
        except Exception as exc:  # pragma: no cover
            log_line(f"watchdog_failed exc={exc}")

    log_line("watchdog_stopped")


def ensure_watchdog() -> None:
    global watchdog_thread
    if watchdog_thread and watchdog_thread.is_alive():
        return
    watchdog_stop_event.clear()
    watchdog_thread = threading.Thread(target=_watchdog_loop, name="V2TrayWatchdog", daemon=True)
    watchdog_thread.start()


def stop_watchdog() -> None:
    watchdog_stop_event.set()


def on_quit(icon: pystray.Icon, item=None) -> None:
    global shutdown_requested
    shutdown_requested = True
    stop_watchdog()
    stop_all()
    icon.stop()


def bootstrap(icon: pystray.Icon) -> None:
    log_line("tray_setup_started")
    icon.visible = True
    log_line("tray_icon_visible")
    start_all()
    ensure_watchdog()
    notify("V2 托盘已启动", "程序已缩小到系统托盘，双击或右键即可打开平台。")
    log_line("tray_setup_completed")


def build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("打开平台", open_frontend, default=True),
        pystray.MenuItem("启动服务", start_all),
        pystray.MenuItem("重启服务", restart_services),
        pystray.MenuItem("停止服务", stop_all),
        pystray.MenuItem("开启开机启动", install_startup),
        pystray.MenuItem("关闭开机启动", remove_startup),
        pystray.MenuItem("查看状态", show_status),
        pystray.MenuItem("打开日志目录", open_logs),
        pystray.MenuItem("退出托盘", on_quit),
    )


def main() -> None:
    ensure_dirs()
    log_line(
        f"tray_process_start pid={os.getpid()} ppid={os.getppid()} frozen={getattr(sys, 'frozen', False)} root={ROOT}"
    )
    other_trays = find_other_tray_processes()
    if other_trays:
        pid_summary = ",".join(str(item.get("pid")) for item in other_trays[:8])
        log_line(f"tray_duplicate_process_detected pids={pid_summary}")
        try:
            webbrowser.open(FRONTEND_URL)
        except Exception as exc:
            log_line(f"tray_duplicate_open_frontend_failed exc={exc}")
        show_message_box("V2 托盘已在运行", "检测到已有托盘实例运行，将为你打开系统首页。")
        return
    if not is_single_instance():
        log_line("tray_duplicate_instance")
        try:
            webbrowser.open(FRONTEND_URL)
        except Exception as exc:
            log_line(f"tray_duplicate_open_frontend_failed exc={exc}")
        show_message_box("V2 托盘已在运行", "V2 托盘已经在当前桌面会话中运行，将为你打开系统首页。")
        return

    atexit.register(release_mutex)
    atexit.register(stop_watchdog)

    global icon_instance
    icon_instance = pystray.Icon(
        "YongjiaWeakCurrentV2Tray",
        create_icon(),
        "永嘉集团信息弱电综合运维平台 V2",
        build_menu(),
    )
    log_line("tray_icon_run_enter")
    icon_instance.run(setup=bootstrap)
    log_line("tray_icon_run_exit")


if __name__ == "__main__":
    main()

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.core.settings import settings


SUCCESS_TTL_SECONDS = 90
FAILURE_TTL_SECONDS = 30
SNAPSHOT_DIR = settings.runtime_dir / "channel_snapshots"
LEGACY_RUNTIME_DIR = settings.root_dir.parent / "runtime"


@dataclass(frozen=True)
class SnapshotCaptureResult:
    image_path: Path
    cached: bool
    strategy: str
    captured_at: str
    source_label: str


def capture_channel_snapshot(
    *,
    channel_id: int,
    rtsp_main: str = "",
    rtsp_sub: str = "",
    legacy_snapshot_url: str = "",
    force_refresh: bool = False,
) -> SnapshotCaptureResult:
    candidates = [
        ("main", (rtsp_main or "").strip()),
        ("sub", (rtsp_sub or "").strip()),
    ]
    available_candidates = [(label, url) for label, url in candidates if url]
    if not available_candidates:
        raise RuntimeError("当前通道缺少可用的 RTSP 抓图地址。")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = SNAPSHOT_DIR / f"channel-{channel_id}.jpg"
    meta_path = SNAPSHOT_DIR / f"channel-{channel_id}.json"

    if not force_refresh:
        cached = _load_cached_result(image_path, meta_path)
        if cached is not None:
            return cached

    last_error = "未找到可用的抓图结果。"
    ffmpeg_path = _resolve_ffmpeg_path()

    for label, url in available_candidates:
        temp_path = SNAPSHOT_DIR / f"channel-{channel_id}-{uuid4().hex}.jpg"
        try:
            _run_ffmpeg_capture(ffmpeg_path, url, temp_path)
            if not temp_path.exists() or temp_path.stat().st_size <= 0:
                raise RuntimeError("FFmpeg 未生成可用图片。")
            temp_path.replace(image_path)
            captured_at = datetime.now().isoformat(timespec="seconds")
            _write_meta(
                meta_path,
                {
                    "status": "success",
                    "captured_at": captured_at,
                    "strategy": label,
                    "source_label": _mask_source(url),
                },
            )
            return SnapshotCaptureResult(
                image_path=image_path,
                cached=False,
                strategy=label,
                captured_at=captured_at,
                source_label=_mask_source(url),
            )
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc) or last_error
        finally:
            temp_path.unlink(missing_ok=True)

    _write_meta(
        meta_path,
        {
            "status": "failed",
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "error": last_error,
        },
    )
    raise RuntimeError(last_error)


def iter_channel_mjpeg(*, rtsp_main: str = "", rtsp_sub: str = ""):
    rtsp_url = (rtsp_sub or "").strip() or (rtsp_main or "").strip()
    if not rtsp_url:
        raise RuntimeError("当前通道缺少可用于实时预览的 RTSP 地址。")

    ffmpeg_path = _resolve_ffmpeg_path()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-timeout",
        "5000000",
        "-i",
        rtsp_url,
        "-an",
        "-vf",
        "fps=3,scale='min(960,iw)':-2",
        "-q:v",
        "6",
        "-f",
        "mpjpeg",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        if process.stdout is None:
            raise RuntimeError("FFmpeg 未打开实时预览输出。")
        while True:
            chunk = process.stdout.read(8192)
            if not chunk:
                break
            yield chunk
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def iter_channel_flv(*, rtsp_main: str = "", rtsp_sub: str = ""):
    rtsp_url = (rtsp_sub or "").strip() or (rtsp_main or "").strip()
    if not rtsp_url:
        raise RuntimeError("当前通道缺少可用于直播预览的 RTSP 地址。")

    ffmpeg_path = _resolve_ffmpeg_path()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-rtsp_transport",
        "tcp",
        "-timeout",
        "5000000",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-analyzeduration",
        "1000000",
        "-probesize",
        "32768",
        "-i",
        rtsp_url,
        "-an",
        "-vf",
        "fps=12,scale='min(1280,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-profile:v",
        "baseline",
        "-level",
        "4.0",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        "1800k",
        "-maxrate",
        "2200k",
        "-bufsize",
        "4400k",
        "-g",
        "24",
        "-f",
        "flv",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        if process.stdout is None:
            raise RuntimeError("FFmpeg 未打开直播预览输出。")
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def _try_legacy_snapshot(
    *,
    channel_id: int,
    image_path: Path,
    meta_path: Path,
    legacy_snapshot_url: str,
    rtsp_main: str,
    rtsp_sub: str,
) -> SnapshotCaptureResult | None:
    temp_path = SNAPSHOT_DIR / f"channel-{channel_id}-{uuid4().hex}.jpg"
    try:
        _fetch_legacy_snapshot(
            legacy_snapshot_url=legacy_snapshot_url,
            rtsp_main=rtsp_main,
            rtsp_sub=rtsp_sub,
            output_path=temp_path,
        )
        if not temp_path.exists() or temp_path.stat().st_size <= 0:
            raise RuntimeError("历史快照未返回可用图片。")
        temp_path.replace(image_path)
        captured_at = datetime.now().isoformat(timespec="seconds")
        _write_meta(
            meta_path,
            {
                "status": "success",
                "captured_at": captured_at,
                "strategy": "legacy_snapshot",
                "source_label": _mask_source(legacy_snapshot_url),
            },
        )
        return SnapshotCaptureResult(
            image_path=image_path,
            cached=False,
            strategy="legacy_snapshot",
            captured_at=captured_at,
            source_label=_mask_source(legacy_snapshot_url),
        )
    except Exception as exc:  # noqa: BLE001
        _write_meta(
            meta_path,
            {
                "status": "failed",
                "captured_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc) or "历史快照抓取失败。",
            },
        )
        return None
    finally:
        temp_path.unlink(missing_ok=True)


def _load_cached_result(image_path: Path, meta_path: Path) -> SnapshotCaptureResult | None:
    meta = _read_meta(meta_path)
    if not meta:
        return None

    captured_at = _parse_iso(meta.get("captured_at") or "")
    if captured_at is None:
        return None

    status = str(meta.get("status") or "").strip().lower()
    strategy = str(meta.get("strategy") or "").strip().lower()
    age = datetime.now() - captured_at
    if strategy not in {"main", "sub"}:
        return None

    if status == "success" and image_path.exists() and age <= timedelta(seconds=SUCCESS_TTL_SECONDS):
        return SnapshotCaptureResult(
            image_path=image_path,
            cached=True,
            strategy=strategy or "cached",
            captured_at=captured_at.isoformat(timespec="seconds"),
            source_label=str(meta.get("source_label") or ""),
        )

    if status == "failed" and age <= timedelta(seconds=FAILURE_TTL_SECONDS):
        raise RuntimeError(str(meta.get("error") or "抓图暂时失败，请稍后重试。"))

    return None


def _read_meta(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_meta(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _resolve_ffmpeg_path() -> str:
    candidates = [
        settings.runtime_dir / "ffmpeg.exe",
        LEGACY_RUNTIME_DIR / "ffmpeg.exe",
        LEGACY_RUNTIME_DIR / "ffmpeg",
        Path("ffmpeg"),
    ]
    for candidate in candidates:
        if candidate.name == "ffmpeg":
            return str(candidate)
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("未找到 ffmpeg，请先部署 ffmpeg 后再启用 RTSP 自主抓帧。")


def _run_ffmpeg_capture(ffmpeg_path: str, rtsp_url: str, output_path: Path) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    attempts = [
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-rtsp_transport",
            "tcp",
            "-timeout",
            "5000000",
            "-i",
            rtsp_url,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ],
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            rtsp_url,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ],
    ]

    last_error = ""
    for command in attempts:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=creationflags,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = f"FFmpeg 抓帧超时：{_mask_source(rtsp_url)}"
            continue
        if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return
        stderr = (completed.stderr or completed.stdout or "").strip()
        if stderr:
            last_error = stderr.splitlines()[-1].strip()

    raise RuntimeError(last_error or "FFmpeg RTSP 抓帧失败。")


def _fetch_legacy_snapshot(*, legacy_snapshot_url: str, rtsp_main: str, rtsp_sub: str, output_path: Path) -> None:
    url = (legacy_snapshot_url or "").strip()
    if not url:
        raise RuntimeError("缺少历史快照地址。")

    handlers: list[urllib.request.BaseHandler] = []
    creds = _extract_http_credentials(url) or _extract_rtsp_credentials(rtsp_main) or _extract_rtsp_credentials(rtsp_sub)
    if creds:
        username, password = creds
        parsed = urllib.parse.urlparse(url)
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        base = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}" if parsed.port else f"{parsed.scheme}://{parsed.hostname}"
        password_mgr.add_password(None, base, username, password)
        handlers.append(urllib.request.HTTPBasicAuthHandler(password_mgr))
        handlers.append(urllib.request.HTTPDigestAuthHandler(password_mgr))

    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "YongjiaWeakCurrentV2/2.0",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with opener.open(request, timeout=12) as response:
            content_type = response.headers.get_content_type()
            payload = response.read()
            if not content_type.startswith("image/") and not _looks_like_image(payload):
                raise RuntimeError(f"历史快照返回类型异常：{content_type}")
            output_path.write_bytes(payload)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"历史快照抓取失败：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"历史快照抓取失败：{exc.reason}") from exc


def _extract_http_credentials(url: str) -> tuple[str, str] | None:
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.username:
        return urllib.parse.unquote(parsed.username), urllib.parse.unquote(parsed.password or "")
    return None


def _looks_like_image(payload: bytes) -> bool:
    if not payload:
        return False
    return (
        payload.startswith(b"\xff\xd8\xff")
        or payload.startswith(b"\x89PNG\r\n\x1a\n")
        or payload.startswith(b"GIF87a")
        or payload.startswith(b"GIF89a")
        or payload.startswith(b"BM")
        or payload.startswith(b"RIFF")
    )


def _extract_rtsp_credentials(url: str) -> tuple[str, str] | None:
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.username:
        return urllib.parse.unquote(parsed.username), urllib.parse.unquote(parsed.password or "")

    raw = (url or "").strip()
    if "user=" in raw and "_password=" in raw:
        user_part = raw.split("user=", 1)[1]
        username = user_part.split("_password=", 1)[0]
        password = user_part.split("_password=", 1)[1].split("_channel=", 1)[0]
        return username, password
    return None


def _mask_source(value: str) -> str:
    source = (value or "").strip()
    if not source:
        return ""
    parsed = urllib.parse.urlparse(source)
    if parsed.username:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urllib.parse.urlunparse((parsed.scheme, f"***:***@{netloc}", parsed.path, parsed.params, parsed.query, parsed.fragment))
    if "@" in source and "://" in source:
        prefix, suffix = source.split("@", 1)
        scheme = prefix.split("://", 1)[0]
        return f"{scheme}://***@{suffix}"
    return source

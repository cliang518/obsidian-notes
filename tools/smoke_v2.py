from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


BACKEND_BASE = os.getenv("V2_BACKEND", "http://127.0.0.1:8011")
FRONTEND_BASE = os.getenv("V2_FRONTEND", "http://127.0.0.1:3011")
USERNAME = os.getenv("V2_USERNAME", "admin")
PASSWORD = os.getenv("V2_PASSWORD", "admin123")


def main() -> int:
    print(f"[smoke] backend={BACKEND_BASE}")
    print(f"[smoke] frontend={FRONTEND_BASE}")
    token = login(USERNAME, PASSWORD)

    api_checks = [
        ("/api/auth/me", "GET"),
        ("/api/system/runtime", "GET"),
        ("/api/license/status", "GET"),
        ("/api/users/summary", "GET"),
        ("/api/alerts/summary", "GET"),
        ("/api/alerts/guard-settings", "GET"),
        ("/api/work-orders/summary", "GET"),
        ("/api/inspection/summary", "GET"),
        ("/api/integrations/summary", "GET"),
        ("/api/agent-gateway/summary", "GET"),
        ("/api/notifications/summary", "GET"),
        ("/api/control-platform/summary", "GET"),
        ("/api/mobile/summary", "GET"),
        ("/api/storage/summary", "GET"),
        ("/api/learning/summary", "GET"),
        ("/api/llm/summary", "GET"),
        ("/api/assets/runtime-counts", "GET"),
        ("/api/assets/areas", "GET"),
        ("/api/assets/source-types", "GET"),
        ("/api/assets/channels?limit=1", "GET"),
        ("/api/topology/summary", "GET"),
        ("/api/floor-plans/summary", "GET"),
    ]
    page_checks = [
        "/",
        "/login",
        "/assets",
        "/alerts",
        "/topology",
        "/video",
        "/work-orders",
        "/inspection",
        "/integrations",
        "/users",
        "/license",
        "/control-platform",
        "/runtime",
        "/notifications",
        "/agents",
        "/mobile",
        "/floor-plans",
        "/learning",
        "/llm",
        "/storage",
    ]

    failures = 0
    for path, method in api_checks:
        try:
            status, size = request_json(path, token=token, method=method)
            print(f"[ok] api {method} {path} -> {status} ({size} bytes)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[fail] api {method} {path} -> {exc}")

    try:
        registrations = request_json_payload("/api/control-platform/registrations", token=token)
        if registrations:
            export_path = f"/api/control-platform/registrations/{registrations[0]['id']}/export"
            status, size = request_json(export_path, token=token, method="GET")
            print(f"[ok] api GET {export_path} -> {status} ({size} bytes)")
        if len(registrations) > 1:
            compare_path = (
                f"/api/control-domain/compare?left_registration_id={registrations[0]['id']}"
                f"&right_registration_id={registrations[1]['id']}"
            )
            status, size = request_json(compare_path, token=token, method="GET")
            print(f"[ok] api GET {compare_path} -> {status} ({size} bytes)")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"[fail] control-platform extended checks -> {exc}")

    for path in page_checks:
        try:
            status, size = request_page(path)
            print(f"[ok] page GET {path} -> {status} ({size} bytes)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[fail] page GET {path} -> {exc}")

    if failures:
        print(f"[smoke] completed with {failures} failure(s)")
        return 1

    print("[smoke] all checks passed")
    return 0


def login(username: str, password: str) -> str:
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_BASE}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            token = body.get("access_token")
            if not token:
                raise RuntimeError("login response missing access_token")
            print("[ok] login /api/auth/login")
            return token
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"login failed: HTTP {exc.code}") from exc


def request_json(path: str, token: str, method: str = "GET") -> tuple[int, int]:
    req = urllib.request.Request(
        f"{BACKEND_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = response.read()
        return response.status, len(payload)


def request_json_payload(path: str, token: str, method: str = "GET") -> object:
    req = urllib.request.Request(
        f"{BACKEND_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def request_page(path: str) -> tuple[int, int]:
    req = urllib.request.Request(f"{FRONTEND_BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = response.read()
        return response.status, len(payload)


if __name__ == "__main__":
    sys.exit(main())

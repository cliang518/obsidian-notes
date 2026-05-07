from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.license import build_signed_license  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yongjia Weak Current Ops Platform V2 License Generator")
    parser.add_argument("--request-file", required=True, help="注册请求 JSON 文件路径")
    parser.add_argument("--customer", required=True, help="授权单位")
    parser.add_argument("--contact", help="联系人")
    parser.add_argument("--expires-at", help="到期时间，例如 2027-04-09T23:59:59")
    parser.add_argument("--license-type", default="annual", help="授权类型")
    parser.add_argument("--max-devices", type=int, help="最大设备数")
    parser.add_argument("--output", help="输出授权 JSON 文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request_data = json.loads(Path(args.request_file).read_text(encoding="utf-8-sig"))
    license_data = build_signed_license(
        issued_to=args.customer,
        contact=args.contact,
        machine_code=request_data["machine_code"],
        fingerprint=request_data["fingerprint"],
        hostname=request_data["hostname"],
        expires_at=args.expires_at,
        license_type=args.license_type,
        max_devices=args.max_devices,
    )

    content = json.dumps(license_data, ensure_ascii=False, indent=2)
    if args.output:
      Path(args.output).write_text(content, encoding="utf-8")
    else:
      print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

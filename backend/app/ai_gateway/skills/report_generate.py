from __future__ import annotations


def build_report_skill_payload(payload):
    report_type = str(payload.get("report_type", "daily")).strip() or "daily"
    title_map = {
        "daily": "日报",
        "weekly": "周报",
        "monthly": "月报",
    }
    return {
        "report_type": report_type,
        "title": title_map.get(report_type, "运行报告"),
        "sections": payload.get("sections") or ["运行概况", "异常概况", "设备概况", "待办事项"],
        "period": payload.get("period") or {},
    }


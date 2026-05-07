from __future__ import annotations


def build_alert_skill_payload(summary, latest_alerts):
    return {
        "summary": {
            "open_count": summary.get("open_count", 0),
            "open_critical_count": summary.get("open_critical_count", 0),
            "strict_unresolved_count": summary.get("strict_unresolved_count", 0),
            "flap_watch_count": summary.get("flap_watch_count", 0),
        },
        "latest_alerts": latest_alerts[:5],
        "recommended_focus": "先看严重待处理和热点设备，再决定确认、恢复或派工。",
    }


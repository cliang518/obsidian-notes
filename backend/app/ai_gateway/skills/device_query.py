from __future__ import annotations


def build_device_query_payload(query, devices):
    return {
        "query": query,
        "matched_count": len(devices),
        "devices": devices[:20],
    }

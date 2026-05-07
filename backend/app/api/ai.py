from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import time
from threading import Lock
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.ai_gateway.main import get_ai_gateway
from app.ai_gateway.core.config_store import load_config, prune_service_access_events, read_service_access_events, validate_service_key
from app.ai_gateway.skills.alert_analyze import build_alert_skill_payload
from app.ai_gateway.skills.device_query import build_device_query_payload
from app.ai_gateway.skills.report_generate import build_report_skill_payload
from app.core.database import get_db
from app.core.settings import settings
from app.models.alert import OpsAlert
from app.models.asset import AssetArea, AssetDevice, ChannelStreamDiagnostic, NetworkPort, TopologyLink, VideoChannel
from app.models.mobile_channel import MobileChannelRegistration
from app.models.mobile_dispatch_item import MobileDispatchItem
from app.models.notification_channel import NotificationChannelRegistration
from app.models.notification_delivery_log import NotificationDeliveryLog
from app.models.inspection_task import InspectionTask
from app.models.user_account import UserAccount
from app.models.work_order import WorkOrder
from app.services.auth import SESSION_COOKIE_NAME, get_user_by_token, hash_password, parse_bearer_token
from app.services.text_normalize import normalize_text
from app.services.rtsp_snapshot import capture_channel_snapshot
from app.services.backup_service import create_v2_state_backup, delete_v2_backup, list_v2_backups, prune_v2_backups


router = APIRouter()
ALERT_WORK_ORDER_LOCK = Lock()
ALERT_DISPATCH_LOCK = Lock()
ALERT_INSPECTION_LOCK = Lock()
ASSET_COUNT_KEYWORDS = ("多少", "几个", "几台", "数量", "总数", "一共", "总共", "count", "how many", "total")
ASSET_DISTRIBUTION_KEYWORDS = ("分布", "类型", "构成", "占比", "分类", "统计", "明细", "breakdown", "distribution")
ASSET_KEYWORDS = ("设备", "摄像头", "交换机", "录像机", "解码器", "通道", "device", "camera", "switch", "nvr", "decoder", "channel")


class GatewayTaskRequest(BaseModel):
    task: str = Field(default="")
    task_type: str = Field(default="general")
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    title: str = ""
    requested_agent_key: str = ""
    llm_key: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class SessionCreateRequest(BaseModel):
    title: str = "AI 网关会话"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCleanupRequest(BaseModel):
    keep_latest: int = 12


class AgentRegisterRequest(BaseModel):
    agent_key: str
    display_name: str
    role: str = "specialist"
    adapter: str = "generic"
    enabled: bool = True
    protocol: str = "tool"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    endpoint_url: str = ""


class LlmRegisterRequest(BaseModel):
    llm_key: str
    provider_type: str = "custom"
    display_name: str
    enabled: bool = True
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""
    default_model: str = ""
    chat_url: str = ""
    embedding_url: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


class AlertAnalyzeRequest(BaseModel):
    task: str = "请分析当前告警情况并给出处置建议。"
    session_id: str | None = None
    llm_key: str = ""


class ReportGenerateRequest(BaseModel):
    task: str = "请生成一份平台运行报告。"
    report_type: str = "daily"
    period: dict[str, Any] = Field(default_factory=dict)
    sections: list[str] = Field(default_factory=list)
    session_id: str | None = None
    llm_key: str = ""


class DeviceQueryRequest(BaseModel):
    task: str = "请查询设备。"
    query: str = ""
    session_id: str | None = None
    llm_key: str = ""


class SnapshotCaptureRequest(BaseModel):
    task: str = "请调取摄像头快照。"
    query: str = ""
    ip: str = ""
    channel_id: int | None = None
    refresh: bool = True
    session_id: str | None = None
    llm_key: str = ""


class LogCleanupRequest(BaseModel):
    keep_days: int = 30
    max_lines: int = 5000


def _asset_area_map(db: Session) -> dict[int, str]:
    rows = db.scalars(select(AssetArea)).all()
    return {row.id: row.display_name for row in rows}


def _compact_scope_text(value: str | None) -> str:
    normalized = normalize_text(value or "").lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _scope_alias_candidates(value: str | None) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    compact_value = _compact_scope_text(text)
    aliases: list[str] = [compact_value] if compact_value else []
    parts = [_compact_scope_text(part) for part in re.split(r"[/\-\s]+", text) if _compact_scope_text(part)]
    aliases.extend(parts)
    if len(parts) >= 2:
        aliases.append("".join(parts[-2:]))
    if len(parts) >= 3:
        aliases.append("".join(parts[-3:]))
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _ip_alias_bundle(value: str | None) -> dict[str, str]:
    ip = str(value or "").strip()
    if ip.count(".") != 3:
        return {"full": ip, "compact": "", "tail": "", "tail_compact": "", "last_octet": ""}
    parts = ip.split(".")
    tail = ".".join(parts[-2:])
    return {
        "full": ip,
        "compact": ip.replace(".", ""),
        "tail": tail,
        "tail_compact": tail.replace(".", ""),
        "last_octet": parts[-1],
    }


def _root_asset_area_names(db: Session, limit: int = 80) -> list[str]:
    rows = db.scalars(select(AssetArea).order_by(AssetArea.display_name)).all()
    preferred = [str(row.display_name or "").strip() for row in rows if str(row.display_name or "").strip() and "#" not in str(row.display_name or "")]
    deduped = list(dict.fromkeys(preferred))
    return deduped[:limit]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = str(text or "").strip()
    if not content:
        return None
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _semantic_llm_adapter(preferred_llm_key: str = ""):
    gateway = get_ai_gateway()
    gateway.refresh()
    if preferred_llm_key:
        adapter = gateway.llm_pool.get(preferred_llm_key)
        if adapter and adapter.is_ready():
            return preferred_llm_key, adapter
    for row in gateway.llm_pool.list_llms():
        llm_key = str(row.get("llm_key", "")).strip()
        if llm_key and row.get("enabled") and row.get("ready"):
            adapter = gateway.llm_pool.get(llm_key)
            if adapter and adapter.is_ready():
                return llm_key, adapter
    return "", None


def _llm_asset_scope_hints(db: Session, text: str, preferred_llm_key: str = "") -> dict[str, Any] | None:
    llm_key, adapter = _semantic_llm_adapter(preferred_llm_key)
    if not adapter:
        return None
    area_hints = _root_asset_area_names(db)
    prompt = {
        "task": "extract_asset_scope",
        "query": str(text or "").strip(),
        "known_area_examples": area_hints,
        "rules": [
            "把自然语言中的楼层、南北东西、停车场、商场视频区等范围提取出来。",
            "把错别字纠正成最可能的正式区域叫法，例如 3楼北 -> 3F北楼，B2停车尝 -> B2停车场。",
            "只输出 JSON，不要解释。",
            "如果没有明确范围，scope_aliases 返回空数组。",
        ],
        "output_schema": {
            "scope_aliases": ["3F北楼"],
            "floor_tokens": ["3F"],
            "device_type": "camera",
            "intent": "count",
        },
    }
    messages = [
        {
            "role": "system",
            "content": "你是弱电运维平台的结构化查询解析器。你只能输出 JSON 对象，不能输出解释、Markdown 或额外文本。",
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    try:
        result = adapter.chat(messages, options={"temperature": 0})
    except Exception:
        return None
    parsed = _extract_json_object((result or {}).get("text", ""))
    if not parsed:
        return None
    aliases = [str(item).strip() for item in parsed.get("scope_aliases", []) if str(item).strip()]
    floor_tokens = [str(item).strip().upper() for item in parsed.get("floor_tokens", []) if str(item).strip()]
    return {
        "llm_key": llm_key,
        "scope_aliases": aliases,
        "floor_tokens": floor_tokens,
        "device_type": str(parsed.get("device_type", "")).strip(),
        "intent": str(parsed.get("intent", "")).strip(),
    }


def _match_asset_areas_from_aliases(db: Session, aliases: list[str], floor_tokens: list[str] | None = None) -> dict[str, Any] | None:
    aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
    if floor_tokens and not aliases:
        aliases.extend(str(token).strip() for token in floor_tokens if str(token).strip())
    aliases = list(dict.fromkeys(alias for alias in aliases if alias))
    if not aliases:
        return None
    merged_ids: list[int] = []
    merged_names: list[str] = []
    label = ""
    for alias in aliases:
        info = _match_asset_areas(db, alias, ASSET_COUNT_KEYWORDS, ASSET_DISTRIBUTION_KEYWORDS, ASSET_KEYWORDS)
        if not info:
            continue
        merged_ids.extend(info.get("area_ids", []))
        merged_names.extend(info.get("matched_names", []))
        if not label and info.get("display_label"):
            label = str(info.get("display_label"))
    merged_ids = list(dict.fromkeys(int(item) for item in merged_ids if item))
    merged_names = list(dict.fromkeys(str(item) for item in merged_names if str(item)))
    if not merged_ids:
        return None
    return {
        "area_ids": merged_ids,
        "matched_names": merged_names,
        "display_label": label or (merged_names[0] if len(merged_names) == 1 else "目标区域"),
        "scope_phrase": " ".join(aliases),
        "floor_tokens": floor_tokens or [],
    }


def _extract_asset_scope(text: str, count_keywords: tuple[str, ...], distribution_keywords: tuple[str, ...], asset_keywords: tuple[str, ...]) -> dict[str, Any]:
    normalized = normalize_text(text)
    lowered = normalized.lower()
    floor_tokens = list(dict.fromkeys(token.upper() for token in re.findall(r"(?i)(?:b\d+|\d+)f", lowered)))
    for floor_match in re.finditer(r"(?i)(b?\d+)\s*楼\s*([东南西北中]?)", normalized):
        floor_base = str(floor_match.group(1) or "").upper()
        if floor_base and not floor_base.endswith("F"):
            floor_base = f"{floor_base}F"
        if floor_base:
            floor_tokens.append(floor_base)
    removable = {
        *count_keywords,
        *distribution_keywords,
        *asset_keywords,
        "查询",
        "查询一下",
        "查一下",
        "查一查",
        "给我",
        "帮我",
        "请问",
        "现在",
        "当前",
        "统计",
        "统计一下",
        "统计下",
        "看看",
        "总共有",
        "总共",
        "一共有",
        "一下",
        "多少台",
        "多少个",
        "多少路",
    }
    scope_phrase = normalized
    for term in sorted(removable, key=len, reverse=True):
        if term:
            scope_phrase = re.sub(re.escape(term), " ", scope_phrase, flags=re.IGNORECASE)
    scope_phrase = scope_phrase.replace("的", " ")
    scope_phrase = re.sub(r"[，。！？、/\\|,:：;；（）()\[\]【】“”\"'‘’\-]+", " ", scope_phrase)
    scope_phrase = re.sub(r"\s+", " ", scope_phrase).strip()
    removable_compacts = sorted(
        {
            _compact_scope_text(term)
            for term in {
                *removable,
                "的",
                "摄像头总数",
                "交换机总数",
                "设备总数",
                "录像机总数",
                "解码器总数",
                "通道总数",
                "多少个头",
                "多少头",
                "几个头",
                "个头",
                "给头",
                "多少给头",
                "有多少给头",
            }
            if _compact_scope_text(term)
        },
        key=len,
        reverse=True,
    )
    semantic_stop_compacts = sorted(
        {
            _compact_scope_text(term)
            for term in (
                "摄像头",
                "交换机",
                "设备",
                "录像机",
                "解码器",
                "通道",
                "总数",
                "数量",
                "分布",
                "类型",
                "构成",
                "占比",
                "统计",
                "明细",
                "有",
                "头",
                "给",
            )
        },
        key=len,
        reverse=True,
    )

    def _clean_scope_token(raw: str) -> str:
        compact = _compact_scope_text(raw)
        for stop in removable_compacts:
            if stop and stop in compact:
                compact = compact.replace(stop, "")
        for stop in semantic_stop_compacts:
            if stop and stop in compact:
                compact = compact.replace(stop, "")
        if compact.endswith("的"):
            compact = compact[:-1]
        return compact

    tokens: list[str] = []
    for raw in scope_phrase.split():
        compact = _clean_scope_token(raw)
        if compact and compact not in {"台", "路", "个", "的"}:
            tokens.append(compact)
    attached_floor_tokens = [
        _clean_scope_token(item)
        for item in re.findall(r"(?i)(?:b\d+|\d+f)[0-9a-z\u4e00-\u9fff]+", normalized)
        if _clean_scope_token(item)
    ]
    for floor_match in re.finditer(r"(?i)(b?\d+)\s*楼\s*([东南西北中]?)", normalized):
        floor_base = str(floor_match.group(1) or "").upper()
        if floor_base and not floor_base.endswith("F"):
            floor_base = f"{floor_base}F"
        side = str(floor_match.group(2) or "").strip()
        if floor_base and side:
            side_suffix = "楼" if side != "中" else "区"
            alias = _clean_scope_token(f"{floor_base}{side}{side_suffix}")
            if alias:
                attached_floor_tokens.append(alias)
    tokens.extend(attached_floor_tokens)
    for token in floor_tokens:
        compact = _compact_scope_text(token)
        if compact and compact not in tokens:
            tokens.append(compact)
    tokens = list(dict.fromkeys(token for token in tokens if token))
    return {
        "normalized_text": normalized,
        "scope_phrase": scope_phrase,
        "floor_tokens": floor_tokens,
        "tokens": tokens,
    }


def _match_asset_areas(db: Session, text: str, count_keywords: tuple[str, ...], distribution_keywords: tuple[str, ...], asset_keywords: tuple[str, ...]) -> dict[str, Any] | None:
    scope = _extract_asset_scope(text, count_keywords, distribution_keywords, asset_keywords)
    if not scope["tokens"] and not scope["floor_tokens"]:
        return None

    rows = db.scalars(select(AssetArea).order_by(AssetArea.display_name)).all()
    floor_compacts = {_compact_scope_text(token) for token in scope["floor_tokens"] if token}
    non_floor_tokens = [token for token in scope["tokens"] if token and token not in floor_compacts]
    query_compact = _compact_scope_text(text)
    scope_compact = _compact_scope_text(scope["scope_phrase"])
    matches: list[tuple[int, AssetArea]] = []
    for row in rows:
        field_text = " ".join(
            filter(
                None,
                [
                    row.display_name,
                    row.site,
                    row.building,
                    row.floor,
                    row.zone,
                    row.weak_current_room,
                ],
            )
        )
        compact_field = _compact_scope_text(field_text)
        if not compact_field:
            continue

        alias_candidates = _scope_alias_candidates(field_text)
        for value in (row.display_name, row.site, row.building, row.floor, row.zone, row.weak_current_room):
            alias_candidates.extend(_scope_alias_candidates(value))
        alias_candidates = list(dict.fromkeys(alias for alias in alias_candidates if alias))

        score = 0
        if floor_compacts:
            floor_hits = sum(
                1
                for token in floor_compacts
                if token in compact_field or any(token in alias for alias in alias_candidates)
            )
            if floor_hits < len(floor_compacts):
                continue
            score += floor_hits * 4

        token_hits = 0
        for token in non_floor_tokens:
            if token in compact_field or any(token in alias for alias in alias_candidates):
                token_hits += 1
                score += min(len(token), 8) + 2
        if non_floor_tokens and token_hits < len(non_floor_tokens):
            continue
        if not non_floor_tokens and not floor_compacts:
            continue

        alias_bonus = 0
        if query_compact:
            for alias in alias_candidates:
                if alias and alias in query_compact:
                    alias_bonus = max(alias_bonus, min(len(alias), 24))
        if scope_compact:
            for alias in alias_candidates:
                if alias and alias in scope_compact:
                    alias_bonus = max(alias_bonus, min(len(alias), 18))
        score += alias_bonus
        score += max(0, 12 - len(row.display_name or ""))
        matches.append((score, row))

    if not matches:
        fuzzy_matches: list[tuple[float, AssetArea]] = []
        fuzzy_sources = [token for token in non_floor_tokens if token]
        if scope_compact:
            fuzzy_sources.append(scope_compact)
        if query_compact:
            fuzzy_sources.append(query_compact)
        fuzzy_sources = list(dict.fromkeys(source for source in fuzzy_sources if source))
        if fuzzy_sources:
            for row in rows:
                field_values = list(
                    filter(
                        None,
                        [
                            row.display_name,
                            row.site,
                            row.building,
                            row.floor,
                            row.zone,
                            row.weak_current_room,
                        ],
                    )
                )
                field_text = " ".join(field_values)
                compact_field = _compact_scope_text(field_text)
                if not compact_field:
                    continue
                if floor_compacts and not all(token in compact_field for token in floor_compacts):
                    continue
                alias_candidates = _scope_alias_candidates(field_text)
                for value in field_values:
                    alias_candidates.extend(_scope_alias_candidates(value))
                alias_candidates = list(dict.fromkeys(alias for alias in alias_candidates if alias))
                score = max(
                    (
                        SequenceMatcher(None, fuzzy_source, candidate).ratio()
                        for fuzzy_source in fuzzy_sources
                        for candidate in alias_candidates
                        if candidate
                    ),
                    default=0.0,
                )
                if score >= 0.58:
                    fuzzy_matches.append((score, row))
            fuzzy_matches.sort(key=lambda item: (-item[0], len(item[1].display_name or ""), item[1].display_name or ""))
            matches = [(int(score * 100), row) for score, row in fuzzy_matches[:8]]

    if not matches:
        return None

    matches.sort(key=lambda item: (-item[0], len(item[1].display_name or ""), item[1].display_name or ""))
    ordered_rows = [row for _, row in matches]
    area_ids = list(dict.fromkeys(row.id for row in ordered_rows))
    matched_names = list(dict.fromkeys(row.display_name for row in ordered_rows if row.display_name))
    root_name_candidates = [name for name in matched_names if "#" not in str(name)]
    preferred_root_names = [
        name
        for name in root_name_candidates
        if all(token in _compact_scope_text(name) for token in non_floor_tokens)
    ] if non_floor_tokens else []
    if preferred_root_names:
        display_label = sorted(preferred_root_names, key=len)[0]
    elif len(root_name_candidates) == 1:
        display_label = root_name_candidates[0]
    else:
        display_label = matched_names[0] if len(matched_names) == 1 else ""
    if not display_label:
        if scope["floor_tokens"] and not non_floor_tokens:
            display_label = f"{'/'.join(scope['floor_tokens'])}相关区域"
        elif scope["scope_phrase"]:
            display_label = f"{scope['scope_phrase']}相关区域"
        else:
            display_label = "目标区域"
    return {
        "area_ids": area_ids,
        "matched_names": matched_names,
        "display_label": display_label,
        "scope_phrase": scope["scope_phrase"],
        "floor_tokens": scope["floor_tokens"],
    }


def _requested_asset_specs(text: str, distribution_keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    specs = [
        {"keywords": ("交换机", "switch"), "key": "switches", "label": "交换机", "unit": "台", "device_type": "switch"},
        {"keywords": ("摄像头", "camera"), "key": "cameras", "label": "摄像头", "unit": "台", "device_type": "camera"},
        {"keywords": ("录像机", "nvr", "recorder"), "key": "recorders", "label": "录像机", "unit": "台", "device_type": "recorder"},
        {"keywords": ("解码器", "decoder"), "key": "decoders", "label": "解码器", "unit": "台", "device_type": "decoder"},
        {"keywords": ("设备", "device"), "key": "devices", "label": "设备", "unit": "台", "device_type": None},
        {"keywords": ("通道", "channel"), "key": "channels", "label": "通道", "unit": "路", "device_type": None},
    ]
    matched = [item for item in specs if _task_has_any(text, item["keywords"])]
    if matched:
        return matched
    if _task_has_any(text, distribution_keywords):
        return specs
    return [specs[4]]


def _asset_detail_request_flags(text: str) -> dict[str, bool]:
    lowered = str(text or "").lower()
    wants_list = any(token in lowered for token in ("列表", "列出", "清单", "明细", "逐个", "每个", "全部", "所有"))
    wants_ip_list = wants_list and any(token in lowered for token in ("ip", "地址", "管理ip", "管理地址"))
    wants_name_list = wants_list and any(token in lowered for token in ("名称", "名字", "hostname", "主机名"))
    return {
        "wants_list": wants_list,
        "wants_ip_list": wants_ip_list,
        "wants_name_list": wants_name_list,
    }


def _gateway_query_text(payload: GatewayTaskRequest) -> str:
    raw_payload = payload.payload or {}
    for key in ("ip", "query", "keyword", "management_ip", "camera_ip"):
        value = str(raw_payload.get(key, "")).strip()
        if value:
            return value
    ip_match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", payload.task or "")
    if ip_match:
        return ip_match.group(0)
    return str(payload.task or "").strip()


def _device_query_items(db: Session, keyword: str, limit: int = 30) -> list[dict[str, Any]]:
    keyword = str(keyword or "").strip()
    keyword_normalized = normalize_text(keyword)
    keyword_compact = _compact_scope_text(keyword_normalized)
    full_ip = ""
    partial_ip = ""
    compact_ip_tail = ""
    last_octet = ""
    full_ip_match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", keyword_normalized)
    if full_ip_match:
        full_ip = full_ip_match.group(1)
    partial_ip_match = re.search(r"(?<!\d)(\d{1,3}\.\d{1,3})(?!\d)", keyword_normalized)
    if partial_ip_match:
        partial_ip = partial_ip_match.group(1)
        compact_ip_tail = partial_ip.replace(".", "")
    digits_only = re.sub(r"\D+", "", keyword_normalized)
    if digits_only:
        if len(digits_only) == 5:
            compact_ip_tail = digits_only
            partial_ip = f"{digits_only[:-3]}.{digits_only[-3:]}"
        elif len(digits_only) in {3, 4}:
            last_octet = digits_only[-3:] if len(digits_only) >= 3 else digits_only
        elif len(digits_only) <= 2:
            last_octet = digits_only
    area_map = _asset_area_map(db)
    rows = db.scalars(select(AssetDevice).order_by(AssetDevice.hostname, AssetDevice.management_ip)).all()
    scored_items: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        area_name = str(area_map.get(row.area_id, ""))
        channel = db.scalar(
            select(VideoChannel)
            .where(or_(VideoChannel.camera_asset_id == row.id, VideoChannel.camera_ip == row.management_ip))
            .order_by(VideoChannel.id)
        )
        fields = [
            str(row.hostname or ""),
            str(row.management_ip or ""),
            str(row.service_ip or ""),
            str(row.mac_address or ""),
            str(row.device_type or ""),
            str(row.health_state or ""),
            area_name,
            str(row.notes or ""),
            str(channel.channel_name or "") if channel else "",
        ]
        haystack = " ".join(fields)
        compact_haystack = _compact_scope_text(haystack)
        management_ip = str(row.management_ip or "").strip()
        service_ip = str(row.service_ip or "").strip()
        ip_aliases = [management_ip, service_ip]
        compact_aliases: list[str] = []
        tail_aliases: list[str] = []
        last_octet_aliases: list[str] = []
        for value in (management_ip, service_ip):
            if value.count(".") == 3:
                compact_aliases.append(value.replace(".", ""))
                tail = ".".join(value.split(".")[-2:])
                tail_aliases.append(tail)
                tail_aliases.append(tail.replace(".", ""))
                last_octet_aliases.append(value.split(".")[-1])
        area_aliases = _scope_alias_candidates(area_name)
        name_aliases = _scope_alias_candidates(row.hostname)
        channel_aliases = _scope_alias_candidates(channel.channel_name if channel else "")
        score = 0
        if not keyword:
            score = 1
        if full_ip and full_ip in ip_aliases:
            score = max(score, 260)
        if partial_ip and any(alias == partial_ip for alias in tail_aliases):
            score = max(score, 230)
        if compact_ip_tail and any(alias == compact_ip_tail for alias in tail_aliases):
            score = max(score, 220)
        if last_octet and any(alias == last_octet for alias in last_octet_aliases):
            score = max(score, 180)
        if keyword and keyword in haystack:
            score = max(score, 170)
        if keyword and keyword.lower() in haystack.lower():
            score = max(score, 165)
        if keyword_compact and keyword_compact in compact_haystack:
            score = max(score, 160)
        if keyword_compact and any(keyword_compact == alias for alias in area_aliases + name_aliases + channel_aliases):
            score = max(score, 175)
        if keyword_compact and any(keyword_compact in alias for alias in area_aliases + name_aliases + channel_aliases):
            score = max(score, 168)
        if not score and keyword and len(keyword_compact) >= 2:
            fuzzy_candidates = [
                *name_aliases,
                *area_aliases,
                *channel_aliases,
                *[_compact_scope_text(field) for field in fields if field],
                *tail_aliases,
                *last_octet_aliases,
                *compact_aliases,
            ]
            best_ratio = max((SequenceMatcher(None, keyword_compact, candidate).ratio() for candidate in fuzzy_candidates if candidate), default=0.0)
            if best_ratio >= 0.84:
                score = 150 + int(best_ratio * 10)
            elif best_ratio >= 0.72:
                score = 120 + int(best_ratio * 10)
        if keyword and not score:
            continue
        item = {
            "id": row.id,
            "hostname": row.hostname,
            "management_ip": row.management_ip,
            "service_ip": row.service_ip,
            "device_type": row.device_type,
            "vendor": row.vendor,
            "model": row.model,
            "mac_address": row.mac_address,
            "health_state": row.health_state,
            "device_status": row.device_status,
            "area_display_name": area_map.get(row.area_id, ""),
            "primary_source_type": row.primary_source_type,
            "channel_id": channel.id if channel else None,
            "channel_name": channel.channel_name if channel else "",
            "rtsp_main": channel.rtsp_main if channel else "",
            "rtsp_sub": channel.rtsp_sub if channel else "",
            "channel_status": channel.channel_status if channel else "",
        }
        scored_items.append((score, item))
    scored_items.sort(
        key=lambda entry: (
            -entry[0],
            str(entry[1].get("management_ip") or ""),
            str(entry[1].get("hostname") or ""),
        )
    )
    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for _, item in scored_items:
        item_id = int(item.get("id") or 0)
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)
        items.append(item)
        if len(items) >= limit:
            break
    if full_ip:
        exact_items = [
            item
            for item in items
            if full_ip in {_ip_alias_bundle(item.get("management_ip")).get("full", ""), _ip_alias_bundle(item.get("service_ip")).get("full", "")}
        ]
        if exact_items:
            return exact_items[:limit]
    if partial_ip or compact_ip_tail:
        exact_tail_items = []
        target_tail = partial_ip or compact_ip_tail
        for item in items:
            bundles = (_ip_alias_bundle(item.get("management_ip")), _ip_alias_bundle(item.get("service_ip")))
            if any(target_tail in {bundle.get("tail", ""), bundle.get("tail_compact", "")} for bundle in bundles):
                exact_tail_items.append(item)
        if exact_tail_items:
            return exact_tail_items[:limit]
    return items


def _task_has_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(word in lowered for word in words)


def _infer_gateway_task_type(payload: GatewayTaskRequest) -> str:
    task_type = str(payload.task_type or "general").strip() or "general"
    text = f"{payload.task} {_gateway_query_text(payload)}"
    if _task_has_any(text, ("快照", "截图", "抓图", "抓拍", "snapshot", "capture", "取图")):
        return "snapshot_capture"
    if _task_has_any(text, ("拓扑", "链路", "交换机归属", "归属", "vlan", "端口", "topology", "switch", "link", "evidence")):
        return "topology_query"
    if _task_has_any(text, ("平台状态", "系统状态", "健康", "服务状态", "在线状态", "health", "service status", "runtime", "system status")):
        return "system_status"
    if (_task_has_any(text, ASSET_COUNT_KEYWORDS) or _task_has_any(text, ASSET_DISTRIBUTION_KEYWORDS)) and _task_has_any(text, ASSET_KEYWORDS):
        return "ops_summary"
    if _task_has_any(text, ("告警", "报警", "alert")) and _task_has_any(
        text,
        ("处置", "闭环", "跟进", "响应", "派单", "派工", "工单", "巡检", "复核", "review", "inspection", "workflow", "follow up", "response", "dispatch"),
    ):
        return "ops_summary"
    if _task_has_any(text, ("告警", "报警", "异常", "离线", "抖动", "恢复", "alert", "alarm", "offline", "flap", "recover")):
        return "alert_analyze"
    if _task_has_any(
        text,
        (
            "设备",
            "摄像头",
            "交换机",
            "录像机",
            "解码器",
            "device",
            "camera",
            "channel",
            "asset",
            "rtsp",
            "nvr",
            "decoder",
        ),
    ):
        return "device_query"
    if _task_has_any(
        text,
        (
            "用户",
            "账号",
            "权限",
            "审批",
            "通知",
            "飞书",
            "微信",
            "工单",
            "派工",
            "移动端",
            "手机端",
            "备份",
            "user",
            "account",
            "permission",
            "approval",
            "notify",
            "notification",
            "message",
            "wechat",
            "wecom",
            "feishu",
            "work order",
            "dispatch",
            "mobile",
            "app",
            "backup",
            "restore",
            "log",
            "summary",
            "module",
        ),
    ):
        return "ops_summary"
    return task_type


def _mask_rtsp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"(rtsp://)([^:/@\s]+):([^@\s]+)@", r"\1\2:***@", text, flags=re.IGNORECASE)


def _channel_rows_for_query(db: Session, keyword: str, channel_id: int | None = None, limit: int = 8) -> list[VideoChannel]:
    if channel_id:
        row = db.get(VideoChannel, channel_id)
        return [row] if row else []

    keyword = str(keyword or "").strip()
    if not keyword:
        return []

    rows: list[VideoChannel] = []
    ip_match = re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", keyword)
    if ip_match:
        rows = db.scalars(
            select(VideoChannel)
            .where(or_(VideoChannel.camera_ip == keyword, VideoChannel.channel_name == keyword))
            .order_by(VideoChannel.id)
            .limit(limit)
        ).all()
        if rows:
            return rows
        devices = db.scalars(
            select(AssetDevice)
            .where(or_(AssetDevice.management_ip == keyword, AssetDevice.service_ip == keyword))
            .order_by(AssetDevice.id)
            .limit(limit)
        ).all()
        device_ids = [row.id for row in devices]
        if device_ids:
            return db.scalars(
                select(VideoChannel)
                .where(VideoChannel.camera_asset_id.in_(device_ids))
                .order_by(VideoChannel.id)
                .limit(limit)
            ).all()

    like = f"%{keyword}%"
    return db.scalars(
        select(VideoChannel)
        .where(
            or_(
                VideoChannel.camera_ip.like(like),
                VideoChannel.channel_name.like(like),
                VideoChannel.channel_no.like(like),
                VideoChannel.notes.like(like),
            )
        )
        .order_by(VideoChannel.id)
        .limit(limit)
    ).all()


def _channel_ai_payload(db: Session, channel: VideoChannel) -> dict[str, Any]:
    parent = db.get(AssetDevice, channel.parent_device_id) if channel.parent_device_id else None
    camera = db.get(AssetDevice, channel.camera_asset_id) if channel.camera_asset_id else None
    area = None
    if camera and camera.area_id:
        area = db.get(AssetArea, camera.area_id)
    elif parent and parent.area_id:
        area = db.get(AssetArea, parent.area_id)

    access_link = None
    switch = None
    switch_port = None
    if channel.camera_asset_id:
        access_link = db.scalar(
            select(TopologyLink)
            .where(TopologyLink.dst_device_id == channel.camera_asset_id)
            .order_by(TopologyLink.confidence.desc(), TopologyLink.id.desc())
        )
        if access_link:
            switch = db.get(AssetDevice, access_link.src_device_id) if access_link.src_device_id else None
            switch_port = db.get(NetworkPort, access_link.src_port_id) if access_link.src_port_id else None

    diagnostic = db.scalar(
        select(ChannelStreamDiagnostic)
        .where(ChannelStreamDiagnostic.channel_id == channel.id)
        .order_by(ChannelStreamDiagnostic.checked_at.desc())
    )

    return {
        "channel_id": channel.id,
        "channel_no": channel.channel_no,
        "channel_name": channel.channel_name,
        "camera_ip": channel.camera_ip,
        "camera_label": (camera.hostname if camera else "") or channel.channel_name or channel.camera_ip,
        "area_display_name": area.display_name if area else "",
        "platform_ip": parent.management_ip if parent else "",
        "platform_label": (parent.hostname if parent else "") or (parent.management_ip if parent else ""),
        "channel_status": channel.channel_status,
        "has_rtsp": bool((channel.rtsp_main or "").strip() or (channel.rtsp_sub or "").strip()),
        "rtsp_main": _mask_rtsp(channel.rtsp_main),
        "rtsp_sub": _mask_rtsp(channel.rtsp_sub),
        "snapshot_url": f"/api/assets/channels/{channel.id}/snapshot.jpg",
        "live_mjpeg_url": f"/api/assets/channels/{channel.id}/mjpeg",
        "live_flv_url": f"/api/assets/channels/{channel.id}/flv",
        "switch_label": (switch.hostname if switch else "") or (switch.management_ip if switch else ""),
        "switch_ip": switch.management_ip if switch else "",
        "switch_port_name": switch_port.port_name if switch_port else "",
        "switch_vlan_id": switch_port.vlan_id if switch_port else "",
        "topology_confidence": access_link.confidence if access_link else 0,
        "topology_evidence_type": access_link.evidence_type if access_link else "",
        "stream_probe_status": diagnostic.scan_status if diagnostic else "unknown",
        "stream_probe_error_class": diagnostic.error_class if diagnostic else "",
        "stream_probe_checked_at": diagnostic.checked_at.isoformat(timespec="seconds") if diagnostic else "",
    }


def _snapshot_skill_context(
    db: Session,
    payload: GatewayTaskRequest,
    *,
    channel_id: int | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    keyword = _gateway_query_text(payload)
    requested_channel_id = channel_id or payload.payload.get("channel_id") if isinstance(payload.payload, dict) else None
    try:
        requested_channel_id = int(requested_channel_id) if requested_channel_id else None
    except (TypeError, ValueError):
        requested_channel_id = None
    channels = _channel_rows_for_query(db, keyword, channel_id=requested_channel_id, limit=8)

    if not channels:
        return {
            "tool": "snapshot_capture",
            "status": "not_found",
            "query": keyword,
            "message": f"平台资产库未找到 {keyword or '该条件'} 对应的摄像头通道，无法直接调取快照。",
            "next_actions": [
                "如果这是新摄像头，请先在资产中心新增或批量导入通道信息。",
                "如果 IP 写错，请重新输入真实摄像头 IP 或通道名称。",
                "新增后 AI 会自动通过资产库里的 RTSP 地址抓取快照。",
            ],
            "candidates": [],
        }

    channel = channels[0]
    channel_payload = _channel_ai_payload(db, channel)
    result: dict[str, Any] = {
        "tool": "snapshot_capture",
        "status": "pending",
        "query": keyword,
        "selected_channel": channel_payload,
        "candidates": [_channel_ai_payload(db, row) for row in channels],
        "image_url": "",
        "captured_at": "",
        "capture_strategy": "",
        "cached": False,
        "error_message": "",
    }

    try:
        capture = capture_channel_snapshot(
            channel_id=channel.id,
            rtsp_main=channel.rtsp_main,
            rtsp_sub=channel.rtsp_sub,
            legacy_snapshot_url=channel.snapshot_url,
            force_refresh=refresh,
        )
        result.update(
            {
                "status": "success",
                "message": f"已从 {channel.camera_ip or channel.channel_name} 的 RTSP 通道抓取快照。",
                "image_url": f"/api/assets/channels/{channel.id}/snapshot.jpg?ai_ts={int(time.time())}",
                "captured_at": capture.captured_at,
                "capture_strategy": capture.strategy,
                "cached": capture.cached,
                "source_label": capture.source_label,
            }
        )
    except Exception as exc:  # noqa: BLE001
        result.update(
            {
                "status": "failed",
                "message": f"已找到通道，但快照抓取失败：{exc}",
                "error_message": str(exc),
            }
        )
    return result


def _topology_skill_context(db: Session, payload: GatewayTaskRequest) -> dict[str, Any]:
    keyword = _gateway_query_text(payload)
    switch_count = db.query(AssetDevice).filter(AssetDevice.device_type == "switch", AssetDevice.device_status != "archived").count()
    camera_count = db.query(AssetDevice).filter(AssetDevice.device_type == "camera", AssetDevice.device_status != "archived").count()
    link_count = db.query(TopologyLink).count()
    high_confidence_count = db.query(TopologyLink).filter(TopologyLink.confidence >= 0.9).count()
    evidence_rows = db.execute(
        select(TopologyLink.evidence_type, func.count())
        .group_by(TopologyLink.evidence_type)
        .order_by(func.count().desc())
        .limit(8)
    ).all()
    vlan_rows = db.execute(
        select(NetworkPort.vlan_id, func.count())
        .where(NetworkPort.vlan_id != "")
        .group_by(NetworkPort.vlan_id)
        .order_by(func.count().desc())
        .limit(8)
    ).all()
    focus_channels = [_channel_ai_payload(db, row) for row in _channel_rows_for_query(db, keyword, limit=8)] if keyword else []
    return {
        "tool": "topology_query",
        "status": "success",
        "query": keyword,
        "summary": {
            "switch_count": switch_count,
            "camera_count": camera_count,
            "link_count": link_count,
            "high_confidence_count": high_confidence_count,
            "unverified_count": max(0, link_count - high_confidence_count),
        },
        "evidence_types": [{"type": row[0] or "unknown", "count": row[1]} for row in evidence_rows],
        "vlans": [{"vlan_id": row[0] or "unknown", "port_count": row[1]} for row in vlan_rows],
        "focus_channels": focus_channels,
    }


def _system_status_context(db: Session) -> dict[str, Any]:
    return {
        "tool": "system_status",
        "status": "success",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ai_connection": _connection_payload(limit=40),
        "counts": {
            "devices": db.query(AssetDevice).filter(AssetDevice.device_status != "archived").count(),
            "channels": db.query(VideoChannel).count(),
            "open_alerts": db.query(OpsAlert).filter(OpsAlert.status == "open").count(),
            "switches": db.query(AssetDevice).filter(AssetDevice.device_type == "switch", AssetDevice.device_status != "archived").count(),
        },
    }


def _extract_quoted_text(text: str) -> str:
    matched = re.search(r"[\"“”'‘’《〈](.{2,80}?)[\"“”'‘’》〉]", str(text or ""))
    return str(matched.group(1)).strip() if matched else ""


def _format_bytes(value: int | float | None) -> str:
    size = float(value or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.1f} {units[index]}"


def _extract_first_id(text: str, keywords: tuple[str, ...] = ()) -> int | None:
    source = str(text or "")
    if keywords:
        for keyword in keywords:
            matched = re.search(rf"{re.escape(keyword)}\s*#?\s*(\d+)", source, flags=re.IGNORECASE)
            if matched:
                return int(matched.group(1))
    matched = re.search(r"#(\d+)", source)
    if matched:
        return int(matched.group(1))
    return None


def _pick_priority(text: str) -> str:
    lowered = str(text or "").lower()
    if any(word in lowered for word in ("紧急", "critical", "urgent")):
        return "critical"
    if any(word in lowered for word in ("高", "high", "warning")):
        return "high"
    if any(word in lowered for word in ("低", "low")):
        return "low"
    return "medium"


def _pick_work_order_status(text: str) -> str:
    lowered = str(text or "").lower()
    if any(word in lowered for word in ("完成", "关闭", "解决", "恢复", "resolved", "closed", "done")):
        return "resolved"
    if any(word in lowered for word in ("处理中", "跟进", "执行中", "in progress", "processing")):
        return "in_progress"
    return "open"


def _match_user_account(db: Session, text: str) -> UserAccount | None:
    normalized = normalize_text(text).strip().lower()
    if not normalized:
        return None
    rows = db.scalars(select(UserAccount).order_by(UserAccount.updated_at.desc(), UserAccount.id.desc()).limit(50)).all()
    for row in rows:
        username = normalize_text(row.username).strip().lower()
        display_name = normalize_text(row.display_name).strip().lower()
        if username and username in normalized:
            return row
        if display_name and display_name in normalized:
            return row
    return None


def _match_notification_channel(db: Session, text: str) -> NotificationChannelRegistration | None:
    normalized = normalize_text(text).strip().lower()
    rows = db.scalars(
        select(NotificationChannelRegistration).order_by(
            NotificationChannelRegistration.enabled.desc(),
            NotificationChannelRegistration.updated_at.desc(),
        )
    ).all()
    if not normalized:
        return rows[0] if rows else None
    for row in rows:
        channel_key = normalize_text(row.channel_key).strip().lower()
        display_name = normalize_text(row.display_name).strip().lower()
        if channel_key and channel_key in normalized:
            return row
        if display_name and display_name in normalized:
            return row
    return rows[0] if len(rows) == 1 else None


def _match_work_order(db: Session, text: str) -> WorkOrder | None:
    order_id = _extract_first_id(text, ("工单", "work order", "ticket"))
    if order_id:
        return db.get(WorkOrder, order_id)
    quoted = _extract_quoted_text(text)
    if quoted:
        like = f"%{quoted}%"
        return db.scalar(select(WorkOrder).where(WorkOrder.title.ilike(like)).order_by(WorkOrder.updated_at.desc(), WorkOrder.id.desc()))
    return None


def _match_dispatch_item(db: Session, text: str) -> MobileDispatchItem | None:
    dispatch_id = _extract_first_id(text, ("派工", "dispatch"))
    return db.get(MobileDispatchItem, dispatch_id) if dispatch_id else None


def _match_alert(db: Session, text: str) -> OpsAlert | None:
    alert_id = _extract_first_id(text, ("告警", "alert"))
    if alert_id:
        return db.get(OpsAlert, alert_id)
    quoted = _extract_quoted_text(text)
    if quoted:
        like = f"%{quoted}%"
        return db.scalar(select(OpsAlert).where(OpsAlert.title.ilike(like)).order_by(OpsAlert.updated_at.desc(), OpsAlert.id.desc()))
    return None


def _match_device_for_text(db: Session, text: str) -> AssetDevice | None:
    ip_match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", str(text or ""))
    if not ip_match:
        return None
    ip = ip_match.group(0)
    return db.scalar(
        select(AssetDevice).where(
            or_(AssetDevice.management_ip == ip, AssetDevice.service_ip == ip)
        )
    )


def _default_mobile_channel_key(db: Session) -> str:
    row = db.scalar(
        select(MobileChannelRegistration)
        .where(MobileChannelRegistration.enabled.is_(True))
        .order_by(MobileChannelRegistration.updated_at.desc(), MobileChannelRegistration.id.desc())
    )
    if not row:
        row = db.scalar(select(MobileChannelRegistration).order_by(MobileChannelRegistration.updated_at.desc(), MobileChannelRegistration.id.desc()))
    return normalize_text(row.channel_key) if row else ""


def _build_action_result(
    *,
    module: str,
    action: str,
    ok: bool,
    title: str,
    detail: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "module": module,
        "action": action,
        "ok": ok,
        "title": title,
        "detail": detail,
        "data": data or {},
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_backup_action(text: str) -> dict[str, Any] | None:
    lowered = str(text or "").lower()
    if not _task_has_any(text, ("备份", "backup", "恢复点", "archive")):
        return None
    if _task_has_any(text, ("创建", "生成", "执行", "立即", "做一个", "做个", "新建", "create")):
        backup = create_v2_state_backup()
        return _build_action_result(
            module="backups",
            action="create_backup",
            ok=True,
            title="已创建系统备份",
            detail=f"已生成备份 {backup.get('filename', '')}。",
            data={"backup": backup},
        )
    if _task_has_any(text, ("清理", "修剪", "prune")):
        keep_latest = 20
        matched = re.search(r"保留\s*(\d+)\s*(个|份)?", text)
        if matched:
            keep_latest = max(1, min(int(matched.group(1)), 365))
        dry_run = not _task_has_any(text, ("正式", "立即删除", "执行删除", "确认删除", "不是演练"))
        result = prune_v2_backups(keep_latest=keep_latest, dry_run=dry_run)
        return _build_action_result(
            module="backups",
            action="prune_backups",
            ok=True,
            title="已执行备份清理检查",
            detail=f"{'演练' if dry_run else '正式'}模式下处理 {result.get('candidate_count', 0)} 份候选备份。",
            data={"result": result},
        )
    matched_filename = re.search(r"(v2-state-[\w-]+\.zip)", text, flags=re.IGNORECASE)
    if matched_filename and _task_has_any(text, ("删除", "移除", "delete", "remove")):
        result = delete_v2_backup(matched_filename.group(1))
        return _build_action_result(
            module="backups",
            action="delete_backup",
            ok=bool(result.get("deleted")),
            title="备份删除结果",
            detail="备份已删除。" if result.get("deleted") else "未找到目标备份文件。",
            data={"result": result},
        )
    return None


def _run_user_action(db: Session, text: str) -> dict[str, Any] | None:
    if not _task_has_any(text, ("用户", "账号", "权限", "审批", "user", "account", "permission", "role")):
        return None
    row = _match_user_account(db, text)
    if not row:
        if _task_has_any(text, ("审批", "通过", "禁用", "停用", "重置", "reset")):
            return _build_action_result(
                module="users",
                action="user_lookup_failed",
                ok=False,
                title="未找到目标账号",
                detail="请在指令里带上用户名或显示名称，例如：审批用户 admin 或 停用 张三。",
            )
        return None
    if _task_has_any(text, ("审批", "通过", "approve", "启用")):
        row.status = "active"
        if not row.approved_at:
            row.approved_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="users",
            action="approve_user",
            ok=True,
            title="账号已审批通过",
            detail=f"{row.display_name or row.username} 已切换为 active。",
            data={"user": {"id": row.id, "username": row.username, "status": row.status}},
        )
    if _task_has_any(text, ("禁用", "停用", "disable")):
        row.status = "disabled"
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="users",
            action="disable_user",
            ok=True,
            title="账号已停用",
            detail=f"{row.display_name or row.username} 已切换为 disabled。",
            data={"user": {"id": row.id, "username": row.username, "status": row.status}},
        )
    if _task_has_any(text, ("重置密码", "重置", "reset password", "reset")):
        temp_password = f"{row.role}123"
        row.password_hash = hash_password(temp_password)
        row.password_ready = True
        db.commit()
        return _build_action_result(
            module="users",
            action="reset_password",
            ok=True,
            title="账号密码已重置",
            detail=f"{row.display_name or row.username} 的临时密码已重置为 {temp_password}。",
            data={"user": {"id": row.id, "username": row.username}, "temporary_password": temp_password},
        )
    return None


def _run_notification_action(db: Session, text: str) -> dict[str, Any] | None:
    if not _task_has_any(text, ("通知", "飞书", "微信", "企业微信", "webhook", "notify", "notification", "message")):
        return None
    from app.api.notifications import _create_delivery_log, _event_kind_for_alert, _event_marker_for_alert, _post_notification  # noqa: PLC0415

    if _task_has_any(text, ("测试", "联通", "试一下", "试试", "test", "ping")):
        channel = _match_notification_channel(db, text)
        if not channel:
            return _build_action_result(
                module="notifications",
                action="test_notification_channel",
                ok=False,
                title="未找到通知通道",
                detail="请先在通知配置里建立通道，或在指令里写出 channel_key / 显示名称。",
            )
        title = "永嘉弱电综合运维平台通知联调"
        message = "这是一条来自 AI 助手的测试消息，用于验证通知通道是否可达。"
        payload = {
            "event": "platform_notification_test",
            "channel_key": channel.channel_key,
            "channel_type": channel.channel_type,
            "title": title,
            "message": message,
            "target_scope": channel.target_scope,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        result = _post_notification(channel, payload)
        channel.last_checked_at = datetime.utcnow()
        if result.get("ok"):
            channel.status = "active" if channel.enabled else channel.status
        elif channel.status == "active":
            channel.status = "testing"
        log_row = _create_delivery_log(
            db,
            channel=channel,
            title=title,
            message=message,
            ok=bool(result.get("ok")),
            detail=str(result.get("detail", "")),
            status_code=result.get("status_code"),
        )
        db.commit()
        db.refresh(channel)
        db.refresh(log_row)
        return _build_action_result(
            module="notifications",
            action="test_notification_channel",
            ok=bool(result.get("ok")),
            title="通知通道联通测试已执行",
            detail=str(result.get("detail", "")) or "已记录测试结果。",
            data={
                "channel": {"id": channel.id, "channel_key": channel.channel_key, "display_name": channel.display_name},
                "delivery_log": {"id": log_row.id, "status_code": log_row.status_code, "ok": log_row.ok},
            },
        )

    if _task_has_any(text, ("发送告警通知", "分发告警", "推送告警", "dispatch alerts", "send alerts")):
        channels = db.scalars(select(NotificationChannelRegistration).where(NotificationChannelRegistration.enabled.is_(True))).all()
        alerts = db.scalars(select(OpsAlert).order_by(desc(OpsAlert.updated_at), OpsAlert.id.desc()).limit(20)).all()
        if not channels:
            return _build_action_result(
                module="notifications",
                action="dispatch_alert_notifications",
                ok=False,
                title="没有可用通知通道",
                detail="请先在通知配置中启用至少一个通知通道。",
            )
        sent = 0
        simulated = 0
        for alert in alerts:
            event_kind = _event_kind_for_alert(alert)
            if not event_kind:
                continue
            marker = _event_marker_for_alert(alert, event_kind)
            for channel in channels:
                title = f"{'告警恢复' if event_kind == 'alert_resolved' else '告警通知'} / {normalize_text(alert.title)}"
                message = normalize_text(alert.message or alert.evidence_summary or alert.title)
                payload = {
                    "event": event_kind,
                    "marker": marker,
                    "channel_key": channel.channel_key,
                    "title": title,
                    "message": message,
                    "severity": alert.severity,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                }
                result = _post_notification(channel, payload)
                _create_delivery_log(
                    db,
                    channel=channel,
                    title=title,
                    message=message,
                    ok=bool(result.get("ok")),
                    detail=str(result.get("detail", "")),
                    status_code=result.get("status_code"),
                    event_type=f"manual_{event_kind}",
                )
                if channel.endpoint_url:
                    sent += 1
                else:
                    simulated += 1
        db.commit()
        return _build_action_result(
            module="notifications",
            action="dispatch_alert_notifications",
            ok=True,
            title="已执行告警通知分发",
            detail=f"本次共处理 {len(alerts)} 条最近告警，命中 {len(channels)} 个通道，真实发送 {sent} 次，模拟记录 {simulated} 次。",
            data={"channel_count": len(channels), "alert_count": len(alerts), "sent": sent, "simulated": simulated},
        )
    return None


def _ensure_work_order_from_alert(
    db: Session,
    *,
    alert: OpsAlert,
    text: str,
    assignee: UserAccount | None = None,
) -> tuple[WorkOrder, bool]:
    with ALERT_WORK_ORDER_LOCK:
        existing = db.scalar(select(WorkOrder).where(WorkOrder.source_alert_id == alert.id).order_by(WorkOrder.id.desc()))
        if existing:
            return existing, False
        device = db.get(AssetDevice, alert.asset_device_id) if alert.asset_device_id else None
        area_name = ""
        if device and device.area_id:
            area = db.get(AssetArea, device.area_id)
            area_name = area.display_name if area else ""
        picked_priority = _pick_priority(text)
        row = WorkOrder(
            title=normalize_text(alert.title or f"告警 #{alert.id}"),
            order_type="fault_repair",
            status=_pick_work_order_status(text),
            priority=picked_priority if picked_priority != "medium" else (alert.severity if alert.severity in {"critical", "high", "medium", "low"} else "medium"),
            area_name=normalize_text(area_name),
            source_type="ops_alert",
            source_alert_id=alert.id,
            asset_device_id=alert.asset_device_id,
            assignee_username=assignee.username if assignee else "",
            description=normalize_text(alert.message or alert.evidence_summary or alert.title),
        )
        if row.status == "resolved":
            row.resolved_at = datetime.utcnow()
        db.add(row)
        db.flush()
        alert.linked_work_order_id = row.id
        db.commit()
        db.refresh(row)
        return row, True


def _ensure_dispatch_from_alert(
    db: Session,
    *,
    alert: OpsAlert,
    text: str,
    channel_key: str,
    assignee: UserAccount | None = None,
) -> tuple[MobileDispatchItem, bool]:
    with ALERT_DISPATCH_LOCK:
        existing = db.scalar(select(MobileDispatchItem).where(MobileDispatchItem.source_alert_id == alert.id))
        if existing:
            return existing, False
        device = db.get(AssetDevice, alert.asset_device_id) if alert.asset_device_id else None
        area_name = ""
        if device and device.area_id:
            area = db.get(AssetArea, device.area_id)
            area_name = normalize_text(area.display_name if area else "")
        row = MobileDispatchItem(
            dispatch_type="alert",
            status="queued",
            priority=alert.severity if alert.severity in {"critical", "high", "medium", "low"} else "medium",
            title=normalize_text(alert.title or f"告警 #{alert.id}"),
            area_name=area_name,
            device_label=normalize_text((device.hostname if device else "") or (device.management_ip if device else "") or alert.title),
            source_alert_id=alert.id,
            assignee_username=assignee.username if assignee else "",
            mobile_channel_key=channel_key,
            summary=normalize_text(alert.message or alert.evidence_summary or alert.title),
            latest_note=_extract_quoted_text(text),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, True


def _ensure_inspection_from_work_order(
    db: Session,
    *,
    work_order: WorkOrder,
) -> tuple[InspectionTask, bool]:
    with ALERT_INSPECTION_LOCK:
        latest_task = db.scalar(
            select(InspectionTask).where(InspectionTask.source_work_order_id == work_order.id).order_by(InspectionTask.id.desc())
        )
        if latest_task:
            return latest_task, False
        task = InspectionTask(
            title=f"{normalize_text(work_order.title)} 巡检复核",
            plan_name="工单复核",
            status="scheduled",
            area_name=normalize_text(work_order.area_name),
            target_type="work_order_followup",
            source_work_order_id=work_order.id,
            owner_username=normalize_text(work_order.assignee_username),
            result_summary="",
            notes=normalize_text(work_order.description or work_order.resolution_note),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task, True


def _run_alert_response_action(db: Session, text: str) -> dict[str, Any] | None:
    if not _task_has_any(text, ("告警", "报警", "alert")):
        return None
    if not _task_has_any(text, ("处置", "闭环", "跟进", "响应", "派单", "派工", "一键处理", "巡检", "复核", "review", "inspection", "follow up", "response", "workflow")):
        return None
    alert = _match_alert(db, text)
    if not alert:
        return _build_action_result(
            module="ops_response",
            action="alert_response_workflow",
            ok=False,
            title="未找到目标告警",
            detail="请先明确告警编号，例如：对告警 962 进行处置闭环。",
        )
    assignee = _match_user_account(db, text)
    channel_key = _default_mobile_channel_key(db)
    work_order, work_order_created = _ensure_work_order_from_alert(db, alert=alert, text=text, assignee=assignee)
    dispatch_item, dispatch_created = _ensure_dispatch_from_alert(
        db,
        alert=alert,
        text=text,
        channel_key=channel_key,
        assignee=assignee,
    )
    inspection_task = None
    inspection_created = False
    if _task_has_any(text, ("巡检", "复核", "inspection", "review")):
        inspection_task, inspection_created = _ensure_inspection_from_work_order(db, work_order=work_order)
    return _build_action_result(
        module="ops_response",
        action="alert_response_workflow",
        ok=True,
        title="告警处置链已建立",
        detail=(
            f"告警 #{alert.id} 已关联工单 #{work_order.id} 与派工项 #{dispatch_item.id}。"
            f"{' 本次新建工单。' if work_order_created else ' 工单沿用已有记录。'}"
            f"{' 本次新建派工。' if dispatch_created else ' 派工沿用已有记录。'}"
            f"{'' if inspection_task is None else (' 本次新建复核巡检。' if inspection_created else ' 复核巡检沿用已有任务。')}"
        ),
        data={
            "source_alert_id": alert.id,
            "work_order": {"id": work_order.id, "title": work_order.title, "status": work_order.status, "created": work_order_created},
            "dispatch_item": {"id": dispatch_item.id, "status": dispatch_item.status, "created": dispatch_created},
            "inspection_task": (
                {
                    "id": inspection_task.id,
                    "title": inspection_task.title,
                    "status": inspection_task.status,
                    "created": inspection_created,
                }
                if inspection_task
                else None
            ),
            "mobile_channel_key": channel_key,
        },
    )


def _run_work_order_action(db: Session, text: str) -> dict[str, Any] | None:
    if not _task_has_any(text, ("工单", "报修", "维修单", "work order", "ticket")):
        return None
    if _task_has_any(text, ("创建", "新建", "生成", "create")):
        if _task_has_any(text, ("告警", "报警", "alert")):
            alert = _match_alert(db, text)
            if not alert:
                return _build_action_result(
                    module="work_orders",
                    action="create_work_order_from_alert",
                    ok=False,
                    title="未找到目标告警",
                    detail="请先明确告警编号，例如：为告警 962 创建工单。",
                )
            assignee = _match_user_account(db, text)
            row, created = _ensure_work_order_from_alert(db, alert=alert, text=text, assignee=assignee)
            if not created:
                return _build_action_result(
                    module="work_orders",
                    action="create_work_order_from_alert",
                    ok=True,
                    title="告警工单已存在",
                    detail=f"告警 #{alert.id} 已关联工单 #{row.id}。",
                    data={"work_order": {"id": row.id, "title": row.title, "status": row.status}},
                )
            return _build_action_result(
                module="work_orders",
                action="create_work_order_from_alert",
                ok=True,
                title="已从告警创建工单",
                detail=f"告警 #{alert.id} 已生成工单 #{row.id}。",
                data={"work_order": {"id": row.id, "title": row.title, "status": row.status}, "source_alert_id": alert.id},
            )
        title = _extract_quoted_text(text)
        if not title:
            cleaned = re.sub(r".*?(创建|新建|生成)\s*(一条|一个)?\s*(工单|报修|维修单)", "", text, flags=re.IGNORECASE).strip(" ：:，,。")
            title = cleaned[:120]
        if not title:
            return _build_action_result(
                module="work_orders",
                action="create_work_order",
                ok=False,
                title="缺少工单标题",
                detail="请把工单标题放到引号里，例如：创建工单“2F南楼21#现场复核”。",
            )
        device = _match_device_for_text(db, text)
        area_name = ""
        if device and device.area_id:
            area = db.get(AssetArea, device.area_id)
            area_name = area.display_name if area else ""
        assignee = _match_user_account(db, text)
        row = WorkOrder(
            title=title,
            order_type="fault_repair",
            status=_pick_work_order_status(text),
            priority=_pick_priority(text),
            area_name=area_name,
            source_type="ai_assistant",
            asset_device_id=device.id if device else None,
            assignee_username=assignee.username if assignee else "",
            description=normalize_text(text),
        )
        if row.status == "resolved":
            row.resolved_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="work_orders",
            action="create_work_order",
            ok=True,
            title="工单已创建",
            detail=f"已创建工单 #{row.id}：{row.title}。",
            data={"work_order": {"id": row.id, "title": row.title, "status": row.status}},
        )
    row = _match_work_order(db, text)
    if not row:
        if _task_has_any(text, ("完成", "关闭", "解决", "派工", "巡检", "复核", "update")):
            return _build_action_result(
                module="work_orders",
                action="work_order_lookup_failed",
                ok=False,
                title="未找到目标工单",
                detail="请在指令里带上工单编号，例如：完成工单 12，或 为工单 12 创建派工。",
            )
        return None
    if _task_has_any(text, ("巡检", "复核", "inspection")):
        existing = db.scalar(select(MobileDispatchItem.id).where(MobileDispatchItem.source_work_order_id == row.id))
        task, created = _ensure_inspection_from_work_order(db, work_order=row)
        if not created:
            return _build_action_result(
                module="work_orders",
                action="create_inspection_from_work_order",
                ok=True,
                title="巡检复核已存在",
                detail=f"工单 #{row.id} 已有关联巡检任务 #{task.id}。",
                data={"inspection_task_id": task.id, "dispatch_linked": bool(existing)},
            )
        return _build_action_result(
            module="work_orders",
            action="create_inspection_from_work_order",
            ok=True,
            title="已生成工单复核巡检",
            detail=f"工单 #{row.id} 已生成巡检任务 #{task.id}。",
            data={"inspection_task_id": task.id},
        )
    if _task_has_any(text, ("完成", "关闭", "解决", "恢复", "resolved", "close", "done", "处理")):
        row.status = _pick_work_order_status(text)
        quoted = _extract_quoted_text(text)
        if quoted and quoted != row.title:
            row.resolution_note = quoted
        if row.status == "resolved":
            row.resolved_at = datetime.utcnow()
        else:
            row.resolved_at = None
        assignee = _match_user_account(db, text)
        if assignee:
            row.assignee_username = assignee.username
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="work_orders",
            action="update_work_order",
            ok=True,
            title="工单状态已更新",
            detail=f"工单 #{row.id} 已更新为 {row.status}。",
            data={"work_order": {"id": row.id, "title": row.title, "status": row.status}},
        )
    return None


def _run_mobile_action(db: Session, text: str) -> dict[str, Any] | None:
    if not _task_has_any(text, ("派工", "移动", "手机端", "dispatch", "mobile")):
        return None
    channel_key = _default_mobile_channel_key(db)
    assignee = _match_user_account(db, text)
    if _task_has_any(text, ("工单", "work order")) and _task_has_any(text, ("创建", "生成", "派", "下发", "dispatch")):
        order = _match_work_order(db, text)
        if not order:
            return _build_action_result(
                module="mobile",
                action="create_dispatch_from_work_order",
                ok=False,
                title="未找到目标工单",
                detail="请先明确工单编号，例如：为工单 12 创建派工。",
            )
        existing = db.scalar(select(MobileDispatchItem).where(MobileDispatchItem.source_work_order_id == order.id))
        if existing:
            return _build_action_result(
                module="mobile",
                action="create_dispatch_from_work_order",
                ok=True,
                title="工单派工已存在",
                detail=f"工单 #{order.id} 已关联派工项 #{existing.id}。",
                data={"dispatch_item_id": existing.id},
            )
        row = MobileDispatchItem(
            dispatch_type="work_order",
            status="queued",
            priority=order.priority,
            title=normalize_text(order.title),
            area_name=normalize_text(order.area_name),
            device_label="",
            source_work_order_id=order.id,
            assignee_username=assignee.username if assignee else normalize_text(order.assignee_username),
            mobile_channel_key=channel_key,
            summary=normalize_text(order.description or order.title),
            latest_note=_extract_quoted_text(text),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="mobile",
            action="create_dispatch_from_work_order",
            ok=True,
            title="已创建移动派工",
            detail=f"工单 #{order.id} 已生成派工项 #{row.id}。",
            data={"dispatch_item_id": row.id, "mobile_channel_key": channel_key},
        )
    if _task_has_any(text, ("告警", "报警", "alert")) and _task_has_any(text, ("创建", "生成", "派", "下发", "dispatch")):
        alert = _match_alert(db, text)
        if not alert:
            return _build_action_result(
                module="mobile",
                action="create_dispatch_from_alert",
                ok=False,
                title="未找到目标告警",
                detail="请先明确告警编号，例如：为告警 164 创建派工。",
            )
        row, created = _ensure_dispatch_from_alert(db, alert=alert, text=text, channel_key=channel_key, assignee=assignee)
        if not created:
            return _build_action_result(
                module="mobile",
                action="create_dispatch_from_alert",
                ok=True,
                title="告警派工已存在",
                detail=f"告警 #{alert.id} 已关联派工项 #{row.id}。",
                data={"dispatch_item_id": row.id},
            )
        return _build_action_result(
            module="mobile",
            action="create_dispatch_from_alert",
            ok=True,
            title="已从告警创建派工",
            detail=f"告警 #{alert.id} 已生成派工项 #{row.id}。",
            data={"dispatch_item_id": row.id, "source_alert_id": alert.id, "mobile_channel_key": channel_key},
        )
    row = _match_dispatch_item(db, text)
    if row and _task_has_any(text, ("完成", "接单", "处理中", "关闭", "completed", "acknowledged", "in progress")):
        if _task_has_any(text, ("完成", "关闭", "completed")):
            row.status = "completed"
            row.completed_at = datetime.utcnow()
        elif _task_has_any(text, ("处理中", "执行中", "in progress")):
            row.status = "in_progress"
            if row.acknowledged_at is None:
                row.acknowledged_at = datetime.utcnow()
            row.completed_at = None
        else:
            row.status = "acknowledged"
            if row.acknowledged_at is None:
                row.acknowledged_at = datetime.utcnow()
            row.completed_at = None
        if assignee:
            row.assignee_username = assignee.username
        note = _extract_quoted_text(text)
        if note:
            row.latest_note = note
        db.commit()
        db.refresh(row)
        return _build_action_result(
            module="mobile",
            action="update_dispatch_item",
            ok=True,
            title="移动派工状态已更新",
            detail=f"派工项 #{row.id} 已更新为 {row.status}。",
            data={"dispatch_item_id": row.id, "status": row.status},
        )
    return None


def _collect_ops_actions(db: Session, payload: GatewayTaskRequest) -> list[dict[str, Any]]:
    text = f"{payload.task} {_gateway_query_text(payload)}".strip()
    if not text:
        return []
    actions: list[dict[str, Any]] = []
    for runner in (_run_backup_action,):
        result = runner(text)
        if result:
            actions.append(result)
    skip_workflow_runners = False
    for runner in (_run_user_action, _run_notification_action, _run_alert_response_action, _run_work_order_action, _run_mobile_action):
        if skip_workflow_runners and runner in (_run_work_order_action, _run_mobile_action):
            continue
        result = runner(db, text)
        if result:
            actions.append(result)
            if runner is _run_alert_response_action:
                skip_workflow_runners = True
    return actions


def _ops_summary_context(db: Session, payload: GatewayTaskRequest) -> dict[str, Any]:
    text = f"{payload.task} {_gateway_query_text(payload)}"
    sections: list[dict[str, Any]] = []
    actions = _collect_ops_actions(db, payload)

    asset_message = ""
    if (_task_has_any(text, ASSET_COUNT_KEYWORDS) or _task_has_any(text, ASSET_DISTRIBUTION_KEYWORDS)) and _task_has_any(text, ASSET_KEYWORDS):
        scope_info = _match_asset_areas(db, text, ASSET_COUNT_KEYWORDS, ASSET_DISTRIBUTION_KEYWORDS, ASSET_KEYWORDS)
        semantic_scope = None
        if not scope_info or ("楼" in text or "层" in text or any(word in text for word in ("北", "南", "东", "西", "停车场"))):
            semantic_scope = _llm_asset_scope_hints(db, text, preferred_llm_key=str(payload.llm_key or "").strip())
            if semantic_scope:
                llm_scope_info = _match_asset_areas_from_aliases(db, semantic_scope.get("scope_aliases", []), semantic_scope.get("floor_tokens", []))
                if llm_scope_info:
                    scope_info = llm_scope_info
        device_query = db.query(AssetDevice).filter(AssetDevice.device_status != "archived")
        if scope_info:
            device_query = device_query.filter(AssetDevice.area_id.in_(scope_info["area_ids"]))

        camera_rows = device_query.filter(AssetDevice.device_type == "camera").with_entities(AssetDevice.id, AssetDevice.management_ip).all()
        camera_asset_ids = [row[0] for row in camera_rows if row[0]]
        camera_ips = [str(row[1] or "").strip() for row in camera_rows if str(row[1] or "").strip()]
        if scope_info and (camera_asset_ids or camera_ips):
            channel_conditions = []
            if camera_asset_ids:
                channel_conditions.append(VideoChannel.camera_asset_id.in_(camera_asset_ids))
            if camera_ips:
                channel_conditions.append(VideoChannel.camera_ip.in_(camera_ips))
            channel_count = db.query(func.count(func.distinct(VideoChannel.id))).filter(or_(*channel_conditions)).scalar() or 0
        elif scope_info:
            channel_count = 0
        else:
            channel_count = db.query(VideoChannel).count()

        summary = {
            "devices": device_query.count(),
            "switches": device_query.filter(AssetDevice.device_type == "switch").count(),
            "cameras": len(camera_rows),
            "recorders": device_query.filter(AssetDevice.device_type == "recorder").count(),
            "decoders": device_query.filter(AssetDevice.device_type == "decoder").count(),
            "channels": channel_count,
        }
        requested_specs = _requested_asset_specs(text, ASSET_DISTRIBUTION_KEYWORDS)
        detail_flags = _asset_detail_request_flags(text)
        area_map = _asset_area_map(db) if detail_flags["wants_list"] else {}
        focus_items: list[dict[str, Any]] = [
            {"id": spec["key"], "title": f"{spec['label']}总数", "subtitle": f"{summary[spec['key']]} {spec['unit']}"}
            for spec in requested_specs
        ]
        primary_spec = requested_specs[0]
        breakdown_rows: list[tuple[str, int]] = []
        if scope_info and primary_spec["key"] != "channels":
            breakdown_query = (
                db.query(AssetArea.display_name, func.count(AssetDevice.id))
                .join(AssetDevice, AssetDevice.area_id == AssetArea.id)
                .filter(
                    AssetDevice.device_status != "archived",
                    AssetDevice.area_id.in_(scope_info["area_ids"]),
                )
            )
            if primary_spec["device_type"]:
                breakdown_query = breakdown_query.filter(AssetDevice.device_type == primary_spec["device_type"])
            breakdown_rows = (
                breakdown_query.group_by(AssetArea.display_name).order_by(desc(func.count(AssetDevice.id)), AssetArea.display_name).limit(8).all()
            )
            focus_items.extend(
                {
                    "id": f"area-{index}",
                    "title": area_name,
                    "subtitle": f"{count} {primary_spec['unit']}{primary_spec['label']}",
                }
                for index, (area_name, count) in enumerate(breakdown_rows, start=1)
            )
            if breakdown_rows:
                if len(breakdown_rows) == 1:
                    asset_message = f"{breakdown_rows[0][0]}当前共有 {summary[primary_spec['key']]} {primary_spec['unit']}{primary_spec['label']}。"
                else:
                    detail_text = "、".join(f"{area_name} {count}{primary_spec['unit']}" for area_name, count in breakdown_rows[:4])
                    asset_message = f"{scope_info['display_label']}当前共有 {summary[primary_spec['key']]} {primary_spec['unit']}{primary_spec['label']}，包含 {detail_text}。"
        if scope_info and detail_flags["wants_list"] and primary_spec["key"] != "channels":
            detail_query = (
                db.query(AssetDevice)
                .filter(
                    AssetDevice.device_status != "archived",
                    AssetDevice.area_id.in_(scope_info["area_ids"]),
                )
                .order_by(AssetDevice.area_id.asc(), AssetDevice.hostname.asc(), AssetDevice.management_ip.asc())
            )
            if primary_spec["device_type"]:
                detail_query = detail_query.filter(AssetDevice.device_type == primary_spec["device_type"])
            detail_rows = detail_query.limit(240).all()
            detail_items = []
            for row in detail_rows:
                area_name = str(area_map.get(row.area_id, "")) if row.area_id else ""
                channel = db.scalar(
                    select(VideoChannel)
                    .where(or_(VideoChannel.camera_asset_id == row.id, VideoChannel.camera_ip == row.management_ip))
                    .order_by(VideoChannel.id)
                )
                ip_value = str(row.management_ip or row.service_ip or "").strip() or "-"
                if detail_flags["wants_ip_list"]:
                    subtitle = ip_value
                    if area_name:
                        subtitle = f"{subtitle} / {area_name}"
                elif detail_flags["wants_name_list"]:
                    subtitle = f"{row.hostname or row.management_ip or '未命名'} / {area_name or '未归属区域'}"
                else:
                    subtitle = f"{ip_value} / {area_name or '未归属区域'}"
                detail_items.append(
                    {
                        "id": f"asset-{row.id}",
                        "title": row.hostname or channel.channel_name or row.management_ip or f"设备 {row.id}",
                        "subtitle": subtitle,
                        "updated_at": "",
                    }
                )
            if detail_items:
                focus_items.extend(detail_items)
                listed_count = len(detail_items)
                if detail_flags["wants_ip_list"]:
                    asset_message = (
                        f"{scope_info['display_label']}当前共有 {summary[primary_spec['key']]} {primary_spec['unit']}{primary_spec['label']}，"
                        f"已在结果展示区按列表展示 {listed_count} 条 IP 明细。"
                    )
                else:
                    asset_message = (
                        f"{scope_info['display_label']}当前共有 {summary[primary_spec['key']]} {primary_spec['unit']}{primary_spec['label']}，"
                        f"已在结果展示区按列表展示 {listed_count} 条明细。"
                    )
        if not asset_message:
            asset_scope_label = f"{scope_info['display_label']}" if scope_info else "当前"
            if _task_has_any(text, ASSET_DISTRIBUTION_KEYWORDS):
                asset_message = (
                    f"{asset_scope_label}设备分布：交换机 {summary['switches']} 台，摄像头 {summary['cameras']} 台，"
                    f"录像机 {summary['recorders']} 台，解码器 {summary['decoders']} 台，通道 {summary['channels']} 路。"
                )
            else:
                asset_message = f"{asset_scope_label}共有 {summary[primary_spec['key']]} {primary_spec['unit']}{primary_spec['label']}。"
        sections.append(
            {
                "module": "assets",
                "label": "资产概况",
                "summary": {
                    **summary,
                    "matched_areas": len(breakdown_rows) if breakdown_rows else (len(scope_info["matched_names"]) if scope_info else 0),
                },
                "items": focus_items,
                "message": asset_message,
                "scope_label": scope_info["display_label"] if scope_info else "",
                "matched_areas": [row[0] for row in breakdown_rows] if breakdown_rows else (scope_info["matched_names"] if scope_info else []),
                "semantic_scope": semantic_scope or {},
            }
        )

    if _task_has_any(text, ("用户", "账号", "权限", "审批", "user", "account", "permission", "approval", "role", "roles")):
        rows = db.scalars(select(UserAccount).order_by(UserAccount.updated_at.desc()).limit(6)).all()
        sections.append(
            {
                "module": "users",
                "label": "用户与权限",
                "summary": {
                    "total": db.query(UserAccount).count(),
                    "active": db.query(UserAccount).filter(UserAccount.status == "active").count(),
                    "pending": db.query(UserAccount).filter(UserAccount.status == "pending").count(),
                },
                "items": [
                    {
                        "id": row.id,
                        "title": row.display_name or row.username,
                        "subtitle": f"{row.role} / {row.status}",
                        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
                    }
                    for row in rows
                ],
            }
        )

    if _task_has_any(text, ("通知", "飞书", "微信", "企业微信", "webhook", "消息", "notify", "notification", "message", "wechat", "wecom", "feishu")):
        channels = db.scalars(select(NotificationChannelRegistration).order_by(NotificationChannelRegistration.updated_at.desc()).limit(6)).all()
        delivery_rows = db.scalars(select(NotificationDeliveryLog).order_by(NotificationDeliveryLog.created_at.desc()).limit(20)).all()
        sections.append(
            {
                "module": "notifications",
                "label": "通知配置",
                "summary": {
                    "channels": db.query(NotificationChannelRegistration).count(),
                    "enabled": db.query(NotificationChannelRegistration).filter(NotificationChannelRegistration.enabled.is_(True)).count(),
                    "deliveries": len(delivery_rows),
                    "failed": sum(1 for row in delivery_rows if not row.ok),
                },
                "items": [
                    {
                        "id": row.id,
                        "title": row.display_name or row.channel_key,
                        "subtitle": f"{row.channel_type} / {'启用' if row.enabled else '停用'} / {row.status}",
                        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
                    }
                    for row in channels
                ],
            }
        )

    if _task_has_any(text, ("工单", "维修单", "报修", "work order", "repair order", "ticket", "dispatch")):
        rows = db.scalars(select(WorkOrder).order_by(WorkOrder.updated_at.desc()).limit(6)).all()
        sections.append(
            {
                "module": "work_orders",
                "label": "工单概况",
                "summary": {
                    "total": db.query(WorkOrder).count(),
                    "open": db.query(WorkOrder).filter(WorkOrder.status == "open").count(),
                    "in_progress": db.query(WorkOrder).filter(WorkOrder.status == "in_progress").count(),
                    "resolved": db.query(WorkOrder).filter(WorkOrder.status == "resolved").count(),
                },
                "items": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "subtitle": f"{row.priority} / {row.status} / {row.area_name or '未分区'}",
                        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
                    }
                    for row in rows
                ],
            }
        )

    if _task_has_any(text, ("派工", "移动端", "手机端", "移动", "dispatch", "mobile", "phone", "app")):
        channel_rows = db.scalars(select(MobileChannelRegistration).order_by(MobileChannelRegistration.updated_at.desc()).limit(4)).all()
        dispatch_rows = db.scalars(select(MobileDispatchItem).order_by(MobileDispatchItem.updated_at.desc()).limit(6)).all()
        sections.append(
            {
                "module": "mobile",
                "label": "移动派工",
                "summary": {
                    "channels": db.query(MobileChannelRegistration).count(),
                    "enabled": db.query(MobileChannelRegistration).filter(MobileChannelRegistration.enabled.is_(True)).count(),
                    "dispatch_total": db.query(MobileDispatchItem).count(),
                    "dispatch_active": db.query(MobileDispatchItem).filter(MobileDispatchItem.status.in_(["queued", "acknowledged", "in_progress"])).count(),
                },
                "items": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "subtitle": f"{row.priority} / {row.status} / {row.assignee_username or '未派人'}",
                        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
                    }
                    for row in dispatch_rows
                ]
                + [
                    {
                        "id": f"channel-{row.id}",
                        "title": row.display_name or row.channel_key,
                        "subtitle": f"通道 / {'启用' if row.enabled else '停用'} / {row.status}",
                        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
                    }
                    for row in channel_rows
                ],
            }
        )

    if _task_has_any(text, ("备份", "恢复点", "回滚", "backup", "rollback", "restore point", "restore", "archive", "recovery")):
        backups = list_v2_backups(limit=6)
        sections.append(
            {
                "module": "backups",
                "label": "系统备份",
                "summary": {
                    "total": len(list_v2_backups(limit=100)),
                    "latest": backups[0]["filename"] if backups else "",
                },
                "items": [
                    {
                        "id": item.get("filename", ""),
                        "title": item.get("filename", ""),
                        "subtitle": _format_bytes(item.get("size_bytes")),
                        "updated_at": item.get("updated_at", ""),
                    }
                    for item in backups
                ],
            }
        )

    primary_section = sections[0] if sections else {}
    primary_items = primary_section.get("items", []) if isinstance(primary_section, dict) else []
    return {
        "tool": "ops_summary",
        "status": "action_executed" if actions else ("success" if sections else "not_matched"),
        "query": text.strip(),
        "sections": sections,
        "message": asset_message,
        "matched_count": len(sections),
        "scope_label": primary_section.get("scope_label", "") if isinstance(primary_section, dict) else "",
        "item_count": len(primary_items),
        "primary_section": primary_section.get("module", "") if isinstance(primary_section, dict) else "",
        "actions": actions,
        "executed_action_count": len(actions),
    }


def _feature_guide_context(payload: GatewayTaskRequest) -> dict[str, Any]:
    text = f"{payload.task} {_gateway_query_text(payload)}"
    guide_groups = [
        (
            ("导入", "批量导入", "excel", "表格", "新增摄像头"),
            {
                "module": "资产中心 / 现场核实",
                "intent": "导入与新增设备",
                "steps": [
                    "进入资产中心，先新增单个设备，或使用现场核实模板批量导入摄像头与交换机信息。",
                    "摄像头导入后补齐 IP、RTSP 主码流、区域、平台来源；交换机导入后补齐管理 IP、端口、VLAN。",
                    "导入完成后运行取流诊断与交换机实采，AI 助手才能继续提供快照、拓扑和归属分析。",
                ],
                "entrypoints": [
                    "/assets/devices",
                    "/assets/field-validation/import-camera-sheet",
                    "/assets/field-validation/import-switch-gap-sheet",
                ],
            },
        ),
        (
            ("导出", "备份", "恢复", "下载"),
            {
                "module": "系统与数据导出",
                "intent": "导出与备份",
                "steps": [
                    "资产、告警和拓扑都支持导出；系统备份在系统模块中执行。",
                    "如果是导出未归因链路，请使用 VLAN 归属导出；如果是导出告警，请走告警中心导出。",
                    "重要修改前先做系统备份，便于回滚。",
                ],
                "entrypoints": [
                    "/system/backup",
                    "/alerts/export.csv",
                    "/topology/vlan-attribution/unattributed.csv",
                ],
            },
        ),
        (
            ("删除", "禁用", "停用", "清理"),
            {
                "module": "高风险操作引导",
                "intent": "删除与清理",
                "steps": [
                    "设备删除建议先归档而不是物理删除，避免链路、工单和告警历史断裂。",
                    "告警支持批量删除和历史清理，系统日志支持定期清理。",
                    "AI 助手已经可以直接执行备份、审批、通知测试和派工等安全动作；涉及删库删档这类高风险操作仍建议人工确认后再执行。",
                ],
                "entrypoints": [
                    "/assets/devices/{device_id}",
                    "/alerts/bulk-action",
                    "/alerts/cleanup",
                    "/ai/logs/cleanup",
                ],
            },
        ),
        (
            ("用户", "人员", "账号", "权限", "注册"),
            {
                "module": "用户与权限",
                "intent": "账号和权限管理",
                "steps": [
                    "人员管理支持账号创建、审批、禁用、重置密码以及角色矩阵查看。",
                    "新用户可自主注册，管理员在后台审批后分配权限。",
                    "AI 助手现在可以直接审批账号、停用账号和重置密码；更细的角色矩阵设计仍建议在人员管理页面核对后再落地。",
                ],
                "entrypoints": [
                    "/users/summary",
                    "/users/accounts",
                    "/users/role-matrix",
                ],
            },
        ),
        (
            ("通知", "微信", "飞书", "企业微信", "消息"),
            {
                "module": "通知中心",
                "intent": "通知渠道与告警推送",
                "steps": [
                    "先在通知配置中建立渠道，再测试连通性，最后开启告警分发。",
                    "抖动类告警建议走汇总推送，不建议逐条实时轰炸。",
                    "AI 助手现在既能给推送策略建议，也能直接执行渠道联通测试和一次性告警分发。",
                ],
                "entrypoints": [
                    "/notifications/channels",
                    "/notifications/channels/{channel_id}/test",
                    "/notifications/dispatch-alerts",
                ],
            },
        ),
        (
            ("移动", "手机", "派工", "维修"),
            {
                "module": "移动端与派工",
                "intent": "移动巡检与派工",
                "steps": [
                    "移动模块支持从告警、工单和巡检生成派工事项，并追踪上传结果。",
                    "如果要给维修人员用，先配置移动通道，再生成派工项。",
                    "AI 助手现在可以直接从工单或告警生成派工，并更新派工状态；后续接入照片、说明和月报，可以沿着这一条链继续扩展。",
                ],
                "entrypoints": [
                    "/mobile/summary",
                    "/mobile/dispatch-board",
                    "/mobile/dispatch-items",
                ],
            },
        ),
    ]
    matched = []
    for keywords, guide in guide_groups:
        if _task_has_any(text, keywords):
            matched.append(guide)
    return {
        "tool": "feature_guide",
        "status": "success",
        "query": text.strip(),
        "matched_count": len(matched),
        "guides": matched,
        "all_tools_url": "/api/ai/tools",
    }


def _alert_skill_context(db: Session) -> dict[str, Any]:
    latest_rows = db.scalars(select(OpsAlert).order_by(desc(OpsAlert.last_seen_at), desc(OpsAlert.id)).limit(12)).all()
    open_count = db.query(OpsAlert).filter(OpsAlert.status == "open").count()
    critical_open_count = db.query(OpsAlert).filter(OpsAlert.status == "open", OpsAlert.severity == "critical").count()
    flap_watch_count = db.query(OpsAlert).filter(OpsAlert.attribution_type == "network_flap_watch").count()
    return build_alert_skill_payload(
        {
            "open_count": open_count,
            "open_critical_count": critical_open_count,
            "strict_unresolved_count": open_count,
            "flap_watch_count": flap_watch_count,
        },
        [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "severity": row.severity,
                "source_type": row.source_type,
                "attribution_type": row.attribution_type,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else "",
            }
            for row in latest_rows
        ],
    )


def _enrich_gateway_context(payload: GatewayTaskRequest, db: Session) -> GatewayTaskRequest:
    payload.context = dict(payload.context or {})
    if payload.context.get("skill_payload"):
        return payload

    task_type = _infer_gateway_task_type(payload)
    payload.task_type = task_type
    if task_type == "snapshot_capture":
        refresh = bool((payload.payload or {}).get("refresh", True))
        payload.context["skill_payload"] = _snapshot_skill_context(payload=payload, db=db, refresh=refresh)
        payload.context["display_type"] = "snapshot_card"
    elif task_type == "device_query":
        keyword = _gateway_query_text(payload)
        devices = _device_query_items(db, keyword, limit=30)
        channels = [_channel_ai_payload(db, row) for row in _channel_rows_for_query(db, keyword, limit=12)]
        payload.context["skill_payload"] = {
            **build_device_query_payload(keyword, devices),
            "channels": channels,
            "matched_channel_count": len(channels),
        }
        payload.context["display_type"] = "device_cards"
    elif task_type == "alert_analyze":
        payload.context["skill_payload"] = _alert_skill_context(db)
        payload.context["display_type"] = "alert_cards"
    elif task_type == "report_generate":
        report_payload = {
            "task": payload.task,
            "report_type": str((payload.payload or {}).get("report_type") or (payload.payload or {}).get("period") or "daily"),
            "period": payload.payload or {},
            "sections": (payload.payload or {}).get("sections") or [],
        }
        payload.context["skill_payload"] = build_report_skill_payload(report_payload)
        payload.context["display_type"] = "report_card"
    elif task_type == "topology_query":
        payload.context["skill_payload"] = _topology_skill_context(db, payload)
        payload.context["display_type"] = "topology_card"
    elif task_type == "system_status":
        payload.context["skill_payload"] = _system_status_context(db)
        payload.context["display_type"] = "system_status_card"
    elif task_type == "ops_summary":
        payload.context["skill_payload"] = _ops_summary_context(db, payload)
        payload.context["display_type"] = "ops_summary_card"
    else:
        guide_payload = _feature_guide_context(payload)
        if guide_payload.get("matched_count", 0):
            payload.context["skill_payload"] = guide_payload
            payload.context["display_type"] = "feature_guide_card"
    return payload


def _looks_like_plain_api_key(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", text):
        return False
    return len(text) > 24 or "-" in text or "." in text or bool(re.search(r"[a-z]{6,}", text))


def _run_gateway(payload: GatewayTaskRequest) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    try:
        task = payload.model_dump()
        if task.get("payload"):
            task.setdefault("context", {})
            task["context"].setdefault("payload", task["payload"])
        return gateway.task_router.route(task)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "gateway_route_failed", "message": str(exc)}) from exc


def _safe_service_keys(config: dict[str, Any]) -> list[dict[str, Any]]:
    safe_rows = []
    for row in config.get("service_keys", []) or []:
        safe_rows.append(
            {
                "key_id": row.get("key_id", ""),
                "display_name": row.get("display_name", ""),
                "enabled": bool(row.get("enabled", False)),
                "allowed_clients": row.get("allowed_clients", []) or [],
                "scopes": row.get("scopes", []) or [],
                "key_mask": "********" if str(row.get("key", "")).strip() else "",
            }
        )
    return safe_rows


def _safe_llm_item(item: dict[str, Any]) -> dict[str, Any]:
    safe = dict(item or {})
    api_key = str(safe.pop("api_key", "") or "").strip()
    safe["api_key_present"] = bool(api_key or safe.get("api_key_present"))
    if api_key:
        safe["api_key_mask"] = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) >= 8 else "已保存"
    return safe


def _tail_text_file(path: Path, limit: int = 100) -> list[str]:
    limit = max(1, min(int(limit or 100), 500))
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _connection_payload(limit: int = 80) -> dict[str, Any]:
    config = load_config()
    events = read_service_access_events(limit=limit)
    accepted = [event for event in events if event.get("result") == "accepted"]
    last_event = accepted[-1] if accepted else None
    last_seen_at = str((last_event or {}).get("timestamp") or "")
    parsed = _parse_timestamp(last_seen_at)
    age_seconds = int((datetime.now(timezone.utc) - parsed).total_seconds()) if parsed else None
    live = age_seconds is not None and age_seconds <= 600
    connected = age_seconds is not None and age_seconds <= 86400
    service_keys = _safe_service_keys(config)
    return {
        "status": "live" if live else ("connected" if connected else "standby"),
        "online": connected,
        "live": live,
        "status_label": "实时在线" if live else ("已连接" if connected else "已配置待心跳"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "last_seen_at": last_seen_at,
        "last_seen_age_seconds": age_seconds,
        "last_client_host": (last_event or {}).get("client_host", ""),
        "last_path": (last_event or {}).get("path", ""),
        "recent_access": events[-20:],
        "service_keys": service_keys,
        "gateway_url": "http://192.168.119.149:8011/api/ai/gateway",
        "summary_url": "http://192.168.119.149:8011/api/ai/summary",
        "frontend_url": "http://192.168.119.149:3011/ai-gateway",
    }


def require_ai_access(required_scope: str):
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
        access_token: str | None = Query(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        client_host = request.client.host if request.client else ""
        provided_key = str(request.headers.get("x-ai-gateway-key") or request.headers.get("X-AI-Gateway-Key") or "").strip()
        if not provided_key:
            for raw_name, raw_value in request.scope.get("headers", []):
                if raw_name.lower() in {b"x-ai-gateway-key", b"x_ai_gateway_key"}:
                    provided_key = raw_value.decode("utf-8", errors="ignore").strip()
                    break
        if not provided_key:
            bearer_token = parse_bearer_token(authorization)
            if bearer_token and bearer_token.startswith("yj-ai-"):
                provided_key = bearer_token
        if provided_key:
            access = validate_service_key(provided_key, client_host, required_scope)
            if access and access.get("allowed"):
                return {
                    "auth_type": "service_key",
                    "key_id": access.get("key_id", ""),
                    "client_host": client_host,
                    "scope": required_scope,
                }
            if access and access.get("reason") == "scope_denied":
                raise HTTPException(status_code=403, detail="ai_gateway_scope_denied")
            if access and access.get("reason") == "client_denied":
                raise HTTPException(status_code=403, detail="ai_gateway_client_denied")
            raise HTTPException(status_code=401, detail="ai_gateway_key_invalid")

        token = parse_bearer_token(authorization) or access_token or session_cookie
        user = get_user_by_token(db, token)
        if not user:
            raise HTTPException(status_code=401, detail="authentication_required")
        if user.status != "active":
            raise HTTPException(status_code=403, detail="account_not_active")
        return {
            "auth_type": "user",
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "scope": required_scope,
        }

    return dependency


@router.get("/summary")
def ai_summary(_: dict[str, Any] = Depends(require_ai_access("summary"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    data = gateway.summary()
    data["service_keys"] = _safe_service_keys(load_config())
    data["connection"] = _connection_payload(limit=80)
    return data


@router.get("/connection")
def ai_connection(_: dict[str, Any] = Depends(require_ai_access("summary"))) -> dict[str, Any]:
    return _connection_payload(limit=120)


@router.get("/tools")
def ai_tools(_: dict[str, Any] = Depends(require_ai_access("summary"))) -> dict[str, Any]:
    return {
        "items": [
            {
                "tool": "snapshot_capture",
                "label": "摄像头快照调取",
                "task_type": "snapshot_capture",
                "description": "根据 IP、通道 ID 或通道名称查询资产库，并通过平台 RTSP 抓图链路生成快照。",
                "payload_fields": ["ip", "query", "channel_id", "refresh"],
            },
            {
                "tool": "device_query",
                "label": "设备资产查询",
                "task_type": "device_query",
                "description": "查询摄像头、交换机、录像机、平台节点、区域和 RTSP 信息。",
                "payload_fields": ["ip", "query"],
            },
            {
                "tool": "alert_analyze",
                "label": "告警分析",
                "task_type": "alert_analyze",
                "description": "汇总当前告警、严重告警和网络抖动观察状态。",
                "payload_fields": ["query"],
            },
            {
                "tool": "report_generate",
                "label": "报告生成",
                "task_type": "report_generate",
                "description": "生成日报、周报、月报等弱电运维报告。",
                "payload_fields": ["report_type", "sections"],
            },
            {
                "tool": "topology_query",
                "label": "拓扑链路查询",
                "task_type": "topology_query",
                "description": "查询摄像头与交换机归属、VLAN、链路证据和置信度。",
                "payload_fields": ["ip", "query"],
            },
            {
                "tool": "system_status",
                "label": "系统状态",
                "task_type": "system_status",
                "description": "查询平台资产数量、告警数量和 AI 网关连接状态。",
                "payload_fields": [],
            },
            {
                "tool": "ops_summary",
                "label": "模块概况",
                "task_type": "ops_summary",
                "description": "查询用户权限、通知配置、工单、移动派工和系统备份等模块概况。",
                "payload_fields": ["query"],
            },
        ]
    }


@router.get("/logs")
def ai_logs(
    limit: int = Query(default=120, ge=1, le=500),
    _: dict[str, Any] = Depends(require_ai_access("logs")),
) -> dict[str, Any]:
    log_dir = settings.runtime_dir / "logs"
    return {
        "access_events": read_service_access_events(limit=limit),
        "ai_gateway_log_tail": _tail_text_file(log_dir / "ai_gateway.log", limit=limit),
        "tray_log_tail": _tail_text_file(log_dir / "v2-tray.log", limit=limit),
    }


@router.post("/logs/cleanup")
def cleanup_ai_logs(
    payload: LogCleanupRequest,
    _: dict[str, Any] = Depends(require_ai_access("logs_cleanup")),
) -> dict[str, Any]:
    return {
        "access_log": prune_service_access_events(keep_days=payload.keep_days, max_lines=payload.max_lines),
        "keep_days": payload.keep_days,
        "max_lines": payload.max_lines,
    }


@router.post("/gateway")
def run_gateway(
    payload: GatewayTaskRequest,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_ai_access("gateway")),
) -> dict[str, Any]:
    return _run_gateway(_enrich_gateway_context(payload, db))


@router.get("/agents/register")
def list_agents(_: dict[str, Any] = Depends(require_ai_access("agents"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    return {"items": gateway.agent_registry.list_agents()}


@router.post("/agents/register")
def register_agent(payload: AgentRegisterRequest, _: dict[str, Any] = Depends(require_ai_access("agents"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    try:
        item = gateway.agent_registry.register(payload.model_dump())
        gateway.refresh()
        return {"item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": "智能体注册参数不合法"}) from exc


@router.get("/llm/register")
def list_llms(_: dict[str, Any] = Depends(require_ai_access("llms"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    return {"items": gateway.llm_pool.list_llms()}


@router.post("/llm/register")
def register_llm(payload: LlmRegisterRequest, _: dict[str, Any] = Depends(require_ai_access("llms"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    item_payload = payload.model_dump()
    if _looks_like_plain_api_key(payload.api_key_env):
        if not item_payload.get("api_key"):
            item_payload["api_key"] = item_payload["api_key_env"]
        item_payload["api_key_env"] = ""
    if not str(item_payload.get("api_key", "")).strip():
        item_payload.pop("api_key", None)
    item = gateway.llm_pool.register(item_payload)
    gateway.refresh()
    return {"item": _safe_llm_item(item)}


@router.delete("/llm/register/{llm_key:path}")
def delete_llm(llm_key: str, _: dict[str, Any] = Depends(require_ai_access("llms"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    gateway.refresh()
    try:
        result = gateway.llm_pool.delete(llm_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "llm_not_found", "message": "模型适配器不存在"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": "模型适配器标识不能为空"}) from exc
    gateway.refresh()
    return result


@router.post("/llm/register/{llm_key:path}/delete")
def delete_llm_by_post(llm_key: str, _: dict[str, Any] = Depends(require_ai_access("llms"))) -> dict[str, Any]:
    return delete_llm(llm_key, _)


@router.get("/session")
def list_sessions(_: dict[str, Any] = Depends(require_ai_access("session")), limit: int = Query(default=50)) -> dict[str, Any]:
    gateway = get_ai_gateway()
    return {"items": gateway.context_manager.list_sessions(limit=limit)}


@router.get("/session/{session_id}")
def get_session(session_id: str, _: dict[str, Any] = Depends(require_ai_access("session"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    session = gateway.context_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": "会话不存在"})
    return session


@router.post("/session")
def create_session(payload: SessionCreateRequest, _: dict[str, Any] = Depends(require_ai_access("session"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    return gateway.context_manager.create_session(title=payload.title, metadata=payload.metadata)


@router.delete("/session/{session_id}")
def delete_session(session_id: str, _: dict[str, Any] = Depends(require_ai_access("session"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    removed = gateway.context_manager.delete_session(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": "会话不存在"})
    return {"deleted": True, "session_id": session_id}


@router.post("/session/cleanup-test")
def cleanup_test_sessions(payload: SessionCleanupRequest, _: dict[str, Any] = Depends(require_ai_access("session"))) -> dict[str, Any]:
    gateway = get_ai_gateway()
    return gateway.context_manager.cleanup_test_sessions(keep_latest=payload.keep_latest)


@router.post("/alerts/analyze")
def analyze_alerts(payload: AlertAnalyzeRequest, db: Session = Depends(get_db), _: dict[str, Any] = Depends(require_ai_access("alert_analyze"))) -> dict[str, Any]:
    skill_context = _alert_skill_context(db)
    task = GatewayTaskRequest(
        task=payload.task,
        task_type="alert_analyze",
        session_id=payload.session_id,
        llm_key=payload.llm_key,
        context={"skill_payload": skill_context},
    )
    return _run_gateway(task)


@router.post("/reports/generate")
def generate_report(payload: ReportGenerateRequest, _: dict[str, Any] = Depends(require_ai_access("report_generate"))) -> dict[str, Any]:
    skill_context = build_report_skill_payload(payload.model_dump())
    task = GatewayTaskRequest(
        task=payload.task,
        task_type="report_generate",
        session_id=payload.session_id,
        llm_key=payload.llm_key,
        context={"skill_payload": skill_context},
    )
    return _run_gateway(task)


@router.post("/device/query")
def query_device(payload: DeviceQueryRequest, db: Session = Depends(get_db), _: dict[str, Any] = Depends(require_ai_access("device_query"))) -> dict[str, Any]:
    keyword = str(payload.query or "").strip()
    filtered = _device_query_items(db, keyword, limit=30)
    channels = [_channel_ai_payload(db, row) for row in _channel_rows_for_query(db, keyword, limit=12)]
    skill_context = {**build_device_query_payload(keyword, filtered), "channels": channels, "matched_channel_count": len(channels)}
    task = GatewayTaskRequest(
        task=payload.task or f"请查询设备：{keyword}",
        task_type="device_query",
        session_id=payload.session_id,
        llm_key=payload.llm_key,
        context={"skill_payload": skill_context},
    )
    return _run_gateway(task)


@router.post("/snapshot/capture")
def capture_snapshot(
    payload: SnapshotCaptureRequest,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_ai_access("device_query")),
) -> dict[str, Any]:
    keyword = str(payload.ip or payload.query or "").strip()
    task = GatewayTaskRequest(
        task=payload.task or f"请调取摄像头快照：{keyword}",
        task_type="snapshot_capture",
        session_id=payload.session_id,
        llm_key=payload.llm_key,
        payload={
            "ip": payload.ip,
            "query": keyword,
            "channel_id": payload.channel_id,
            "refresh": payload.refresh,
        },
    )
    task.context["skill_payload"] = _snapshot_skill_context(
        db,
        task,
        channel_id=payload.channel_id,
        refresh=payload.refresh,
    )
    task.context["display_type"] = "snapshot_card"
    return _run_gateway(task)

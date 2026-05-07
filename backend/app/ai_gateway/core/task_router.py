from __future__ import annotations

import json
from typing import Any

from app.ai_gateway.core.config_store import load_config
from app.ai_gateway.core.logging import get_ai_gateway_logger


logger = get_ai_gateway_logger()


def _truncate_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_skill_payload(skill_payload: dict[str, Any], llm_key: str) -> dict[str, Any]:
    tool = str((skill_payload or {}).get("tool") or "").strip()
    if not tool:
        return {}

    if tool == "snapshot_capture":
        selected = dict(skill_payload.get("selected_channel") or {})
        return {
            "tool": tool,
            "status": skill_payload.get("status", ""),
            "query": skill_payload.get("query", ""),
            "message": skill_payload.get("message", ""),
            "capture_strategy": skill_payload.get("capture_strategy", ""),
            "selected_channel": {
                "camera_ip": selected.get("camera_ip", ""),
                "camera_label": selected.get("camera_label", ""),
                "area_display_name": selected.get("area_display_name", ""),
                "switch_label": selected.get("switch_label", ""),
                "switch_port_name": selected.get("switch_port_name", ""),
                "channel_status": selected.get("channel_status", ""),
            },
        }

    if tool == "device_query":
        devices = list(skill_payload.get("devices") or skill_payload.get("results") or [])[:5]
        channels = list(skill_payload.get("channels") or [])[:4]
        return {
            "tool": tool,
            "query": skill_payload.get("query", ""),
            "matched_device_count": skill_payload.get("matched_device_count", len(devices)),
            "matched_channel_count": skill_payload.get("matched_channel_count", len(channels)),
            "devices": [
                {
                    "hostname": row.get("hostname", ""),
                    "management_ip": row.get("management_ip", ""),
                    "device_type": row.get("device_type", ""),
                    "health_state": row.get("health_state", ""),
                    "area_display_name": row.get("area_display_name", ""),
                }
                for row in devices
            ],
            "channels": [
                {
                    "camera_ip": row.get("camera_ip", ""),
                    "camera_label": row.get("camera_label", ""),
                    "area_display_name": row.get("area_display_name", ""),
                    "channel_status": row.get("channel_status", ""),
                }
                for row in channels
            ],
        }

    if tool == "alert_analyze":
        alerts = list(skill_payload.get("alerts") or skill_payload.get("latest_alerts") or [])[:6]
        return {
            "tool": tool,
            "summary": dict(skill_payload.get("summary") or {}),
            "alerts": [
                {
                    "title": row.get("title", ""),
                    "severity": row.get("severity", ""),
                    "status": row.get("status", ""),
                    "attribution_type": row.get("attribution_type", ""),
                }
                for row in alerts
            ],
        }

    if tool == "topology_query":
        focus = list(skill_payload.get("focus_channels") or [])[:6]
        return {
            "tool": tool,
            "status": skill_payload.get("status", ""),
            "query": skill_payload.get("query", ""),
            "summary": dict(skill_payload.get("summary") or {}),
            "focus_channels": [
                {
                    "camera_ip": row.get("camera_ip", ""),
                    "camera_label": row.get("camera_label", ""),
                    "switch_label": row.get("switch_label", ""),
                    "switch_port_name": row.get("switch_port_name", ""),
                    "topology_confidence": row.get("topology_confidence", 0),
                }
                for row in focus
            ],
        }

    if tool == "system_status":
        return {
            "tool": tool,
            "checked_at": skill_payload.get("checked_at", ""),
            "counts": dict(skill_payload.get("counts") or {}),
            "ai_connection": {
                "status": (skill_payload.get("ai_connection") or {}).get("status", ""),
                "status_label": (skill_payload.get("ai_connection") or {}).get("status_label", ""),
                "last_seen_at": (skill_payload.get("ai_connection") or {}).get("last_seen_at", ""),
            },
        }

    if tool == "ops_summary":
        sections = list(skill_payload.get("sections") or [])[:5]
        return {
            "tool": tool,
            "status": skill_payload.get("status", ""),
            "query": skill_payload.get("query", ""),
            "message": skill_payload.get("message", ""),
            "matched_count": skill_payload.get("matched_count", len(sections)),
            "scope_label": skill_payload.get("scope_label", ""),
            "item_count": skill_payload.get("item_count", 0),
            "primary_section": skill_payload.get("primary_section", ""),
            "sections": [
                {
                    "module": row.get("module", ""),
                    "label": row.get("label", ""),
                    "message": row.get("message", ""),
                    "scope_label": row.get("scope_label", ""),
                    "summary": dict(row.get("summary") or {}),
                    "items": [
                        {
                            "title": item.get("title", ""),
                            "subtitle": _truncate_text(item.get("subtitle", ""), 80),
                        }
                        for item in list(row.get("items") or [])[:12]
                    ],
                }
                for row in sections
            ],
        }

    if tool == "feature_guide":
        guides = list(skill_payload.get("guides") or [])[:5]
        return {
            "tool": tool,
            "matched_count": skill_payload.get("matched_count", len(guides)),
            "guides": [
                {
                    "module": row.get("module", ""),
                    "intent": row.get("intent", ""),
                    "steps": [_truncate_text(step, 90) for step in list(row.get("steps") or [])[:3]],
                }
                for row in guides
            ],
        }

    compact = json.loads(json.dumps(skill_payload, ensure_ascii=False, default=str))
    if llm_key == "minimax":
        compact_text = json.dumps(compact, ensure_ascii=False, default=str)
        return {"tool": tool, "summary": _truncate_text(compact_text, 1800)}
    return compact


class TaskRouter:
    def __init__(self, context_manager, agent_registry, llm_pool) -> None:
        self.context_manager = context_manager
        self.agent_registry = agent_registry
        self.llm_pool = llm_pool

    def route(self, task: dict) -> dict:
        config = load_config()
        gateway_config = config.get("gateway", {})
        skills = list(config.get("skills", []))
        session = self.context_manager.get_or_create_session(
            task.get("session_id"),
            title=str(task.get("title", "")).strip() or str(task.get("task_type", "AI 网关任务")),
            metadata={"source": "ai_gateway"},
        )
        task["session_id"] = session["session_id"]
        task["session_messages"] = list(session.get("messages", []) or [])[-8:]
        self.context_manager.append_message(session["session_id"], "user", task)

        coordinator_key = str(gateway_config.get("coordinator_key", "openclaw")).strip() or "openclaw"
        coordinator = self.agent_registry.get(coordinator_key)
        if coordinator is None:
            raise RuntimeError("coordinator_not_available")

        decision = coordinator.decide(
            task,
            self.agent_registry.list_agents(),
            skills,
            default_llm_key=str(gateway_config.get("default_llm_key", "")).strip(),
        )

        llm_result = self._maybe_call_llm(decision, task)
        context = {
            "decision": decision,
            "session": session,
            "recent_memory": self.context_manager.recent_memory(limit=10),
            "task_options": task.get("options") or {},
            "task_context": task.get("context") or {},
        }
        chosen_agent = self.agent_registry.get(decision["chosen_agent_key"]) or coordinator
        execution = chosen_agent.execute(task, context, llm_result=llm_result)
        coordinator_result = coordinator.execute(task, {**context, "decision": decision}, llm_result=None)

        result = {
            "session_id": session["session_id"],
            "decision": decision,
            "coordinator": coordinator_result,
            "execution": execution,
            "llm": llm_result or {},
            "task_context": task.get("context") or {},
        }
        self.context_manager.append_message(session["session_id"], "assistant", result)
        self.context_manager.remember("task_route", result)
        logger.info(
            "AI 网关任务完成: session=%s task_type=%s agent=%s",
            session["session_id"],
            task.get("task_type"),
            decision["chosen_agent_key"],
        )
        return result

    def _maybe_call_llm(self, decision: dict, task: dict):
        llm_key = str(decision.get("chosen_llm_key", "")).strip()
        if not llm_key:
            return None
        adapter = self.llm_pool.get(llm_key)
        if adapter is None or not adapter.is_ready():
            return {
                "llm_key": llm_key,
                "status": "skipped",
                "reason": "adapter_not_ready",
            }
        messages = [
            {
                "role": "system",
                "content": "你是永嘉集团弱电运维平台 V2 的 AI 网关执行模型。请结合会话上下文、设备资产、告警、拓扑和任务数据，输出简洁可靠、可执行的中文结论。不要输出 <think>、推理过程或内部分析，只输出给运维人员看的最终答案。",
            },
        ]
        history_limit = 2 if llm_key == "minimax" else 6
        content_limit = 1200 if llm_key == "minimax" else 3000
        for row in list(task.get("session_messages") or [])[-history_limit:]:
            role = "assistant" if row.get("role") == "assistant" else "user"
            content = row.get("content")
            if not isinstance(content, str):
                content = str(content)[:content_limit]
            messages.append({"role": role, "content": content})
        skill_payload = (task.get("context") or {}).get("skill_payload") or {}
        if skill_payload:
            compact_payload = _compact_skill_payload(skill_payload, llm_key)
            max_context_chars = 2200 if llm_key == "minimax" else 5000
            context_text = json.dumps(compact_payload, ensure_ascii=False, default=str)[:max_context_chars]
            messages.append(
                {
                    "role": "system",
                    "content": f"以下是平台工具已经查到或执行出的真实结果，回答必须以它为准，不要臆造 NVR、SDK 或让用户重复提供已存在的信息：{context_text}",
                }
            )
        messages.append({"role": "user", "content": str(task.get("task") or task.get("prompt") or task)})
        try:
            return adapter.chat(messages, options=task.get("options") or {})
        except Exception as exc:
            logger.exception("LLM 调用失败: %s", exc)
            return {
                "llm_key": llm_key,
                "status": "failed",
                "reason": str(exc),
            }

from __future__ import annotations

from app.ai_gateway.agents.base import BaseAgent


class OpenClawAgent(BaseAgent):
    def decide(self, task, available_agents, skills, default_llm_key=""):
        requested_agent_key = str(task.get("requested_agent_key", "")).strip()
        task_type = str(task.get("task_type", "")).strip() or "general"
        skill_map = {
            str(skill.get("skill_key", "")).strip(): str(skill.get("default_agent_key", "")).strip()
            for skill in skills
            if skill.get("skill_key")
        }
        chosen_agent_key = requested_agent_key or skill_map.get(task_type) or ("codex" if task_type in {"device_query", "code_execute"} else "openclaw")
        known_keys = {item.get("agent_key") for item in available_agents if item.get("enabled")}
        if chosen_agent_key not in known_keys:
            chosen_agent_key = "openclaw"
        return {
            "coordinator_key": self.agent_key,
            "task_type": task_type,
            "chosen_agent_key": chosen_agent_key,
            "chosen_llm_key": str(task.get("llm_key", "")).strip() or default_llm_key,
            "decision_reason": self._decision_reason(task_type, chosen_agent_key, requested_agent_key),
            "always_involved": True,
        }

    def execute(self, task, context, llm_result=None):
        return {
            "agent_key": self.agent_key,
            "role": self.role,
            "status": "completed",
            "summary": llm_result.get("text") if llm_result else "OpenClaw 已完成任务决策与汇总。",
            "decision": context.get("decision", {}),
            "task_context": context.get("task_context", {}),
            "memory_hint": "本次结果已写入 AI 网关记忆流。",
        }

    def _decision_reason(self, task_type, chosen_agent_key, requested_agent_key):
        if requested_agent_key:
            return f"收到显式指定智能体 {requested_agent_key}，由 OpenClaw 审核后放行。"
        if task_type == "device_query":
            return "设备查询更偏执行与检索，先路由给 Codex。"
        if task_type == "alert_analyze":
            return "告警分析需要协调者做判断与归纳，优先由 OpenClaw 处理。"
        if task_type == "report_generate":
            return "报告生成需要汇总多源上下文，优先由 OpenClaw 编排。"
        if chosen_agent_key == "codex":
            return "任务偏执行落地，交给 Codex。"
        return "未命中特定策略，保持 OpenClaw 直接处理。"

from __future__ import annotations

from app.ai_gateway.agents.base import BaseAgent


class CodexAgent(BaseAgent):
    def execute(self, task, context, llm_result=None):
        task_type = str(task.get("task_type", "")).strip() or "general"
        if llm_result and llm_result.get("text"):
            summary = llm_result["text"]
        elif task_type == "device_query":
            summary = "Codex 已完成设备查询执行建议，可根据返回结果继续筛选或跳转资产。"
        else:
            summary = "Codex 已接收执行任务，可继续落代码、接口或查询逻辑。"
        return {
            "agent_key": self.agent_key,
            "role": self.role,
            "status": "completed",
            "summary": summary,
            "task_type": task_type,
            "task_context": context.get("task_context", {}),
            "context_keys": sorted(context.keys()),
            "capabilities": self.capabilities,
        }

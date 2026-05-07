from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.agent_key = str(config.get("agent_key", "")).strip()
        self.display_name = str(config.get("display_name", self.agent_key)).strip()
        self.role = str(config.get("role", "specialist")).strip()
        self.capabilities = list(config.get("capabilities", []) or [])
        self.protocol = str(config.get("protocol", "tool")).strip()
        self.description = str(config.get("description", "")).strip()

    @abstractmethod
    def execute(self, task: dict[str, Any], context: dict[str, Any], llm_result: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class GenericSpecialistAgent(BaseAgent):
    def execute(self, task: dict[str, Any], context: dict[str, Any], llm_result: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "role": self.role,
            "status": "completed",
            "summary": f"{self.display_name} 已接收任务，但当前为通用占位执行者。",
            "capabilities": self.capabilities,
            "task_echo": task,
            "context_keys": sorted(context.keys()),
            "llm_result": llm_result or {},
        }


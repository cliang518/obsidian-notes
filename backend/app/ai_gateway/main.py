from __future__ import annotations

from functools import lru_cache

from app.ai_gateway.core.agent_registry import AgentRegistry
from app.ai_gateway.core.config_store import ensure_bootstrap, load_config
from app.ai_gateway.core.context_manager import ContextManager
from app.ai_gateway.core.llm_pool import LLMPool
from app.ai_gateway.core.task_router import TaskRouter
from app.ai_gateway.protocols.a2a import a2a_descriptor
from app.ai_gateway.protocols.mcp import mcp_descriptor
from app.ai_gateway.protocols.tool_protocol import tool_protocol_descriptor


class AIGatewayApplication:
    def __init__(self) -> None:
        ensure_bootstrap()
        config = load_config()
        memory_window = int(config.get("gateway", {}).get("memory_window", 20) or 20)
        self.context_manager = ContextManager(memory_window=memory_window)
        self.agent_registry = AgentRegistry()
        self.llm_pool = LLMPool()
        self.task_router = TaskRouter(self.context_manager, self.agent_registry, self.llm_pool)

    def refresh(self) -> None:
        config = load_config()
        memory_window = int(config.get("gateway", {}).get("memory_window", 20) or 20)
        self.context_manager.memory_window = memory_window
        self.agent_registry.refresh()
        self.llm_pool.refresh()

    def summary(self) -> dict:
        config = load_config()
        return {
            "gateway": config.get("gateway", {}),
            "agents": self.agent_registry.list_agents(),
            "llms": self.llm_pool.list_llms(),
            "protocols": [mcp_descriptor(), a2a_descriptor(), tool_protocol_descriptor()],
            "skills": config.get("skills", []),
            "recent_memory": self.context_manager.recent_memory(limit=10),
        }


@lru_cache(maxsize=1)
def get_ai_gateway() -> AIGatewayApplication:
    return AIGatewayApplication()

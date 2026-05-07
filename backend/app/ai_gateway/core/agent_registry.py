from __future__ import annotations

from app.ai_gateway.agents.base import BaseAgent, GenericSpecialistAgent
from app.ai_gateway.agents.codex_agent import CodexAgent
from app.ai_gateway.agents.openclaw_agent import OpenClawAgent
from app.ai_gateway.core.config_store import load_config, upsert_list_item


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._agent_configs: list[dict] = []
        self.refresh()

    def refresh(self) -> None:
        config = load_config()
        self._agents = {}
        self._agent_configs = []
        for row in config.get("agents", []):
            agent = self._build_agent(row)
            self._agents[agent.agent_key] = agent
            self._agent_configs.append(dict(row))

    def list_agents(self) -> list[dict]:
        return [dict(item) for item in self._agent_configs]

    def get(self, agent_key: str):
        return self._agents.get(agent_key)

    def register(self, payload: dict) -> dict:
        agent_key = str(payload.get("agent_key", "")).strip()
        role = str(payload.get("role", "")).strip()
        if role == "coordinator" and agent_key != "openclaw":
            raise ValueError("only_openclaw_can_be_coordinator")
        item = upsert_list_item("agents", payload, "agent_key")
        self.refresh()
        return item

    def _build_agent(self, row: dict):
        adapter = str(row.get("adapter", "")).strip() or str(row.get("agent_key", "")).strip()
        if adapter == "openclaw":
            return OpenClawAgent(row)
        if adapter == "codex":
            return CodexAgent(row)
        return GenericSpecialistAgent(row)


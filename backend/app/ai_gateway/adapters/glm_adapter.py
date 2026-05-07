from __future__ import annotations

from typing import Any

from app.ai_gateway.adapters.custom_adapter import CustomRestAdapter


class GlmAdapter(CustomRestAdapter):
    def __init__(self, llm_key: str, config: dict[str, Any]) -> None:
        super().__init__(llm_key, config)
        self.options.setdefault("temperature", 0.2)
        self.options.setdefault("max_retries", 3)

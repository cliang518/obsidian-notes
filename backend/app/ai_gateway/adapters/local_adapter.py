from __future__ import annotations

from typing import Any

from app.ai_gateway.adapters.custom_adapter import CustomRestAdapter


class LocalAdapter(CustomRestAdapter):
    def __init__(self, llm_key: str, config: dict[str, Any]) -> None:
        super().__init__(llm_key, config)
        self.options.setdefault("temperature", 0.2)
        self.options.setdefault("max_retries", 1)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

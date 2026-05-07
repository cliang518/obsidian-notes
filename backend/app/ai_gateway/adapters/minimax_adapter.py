from __future__ import annotations

from typing import Any

from app.ai_gateway.adapters.custom_adapter import CustomRestAdapter


class MiniMaxAdapter(CustomRestAdapter):
    def __init__(self, llm_key: str, config: dict[str, Any]) -> None:
        super().__init__(llm_key, config)
        self.options.setdefault("max_retries", 4)

    def chat(self, messages: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
        return super().chat(self._normalize_messages(messages), options=options)

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        system_parts: list[str] = []

        for row in messages or []:
            role = str((row or {}).get("role") or "user").strip() or "user"
            content = (row or {}).get("content") or ""
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
                continue
            normalized.append({"role": role, "content": content})

        if system_parts:
            normalized.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
        return normalized

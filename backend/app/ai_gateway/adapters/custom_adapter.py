from __future__ import annotations

from typing import Any

from app.ai_gateway.adapters.base import BaseLLMAdapter


class CustomRestAdapter(BaseLLMAdapter):
    def chat(self, messages: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
        endpoint = str((options or {}).get("chat_url") or self.config.get("chat_url") or f"{self.base_url}/chat/completions")
        payload = {
            "model": (options or {}).get("model") or self.default_model,
            "messages": messages,
            **self.options,
            **(options or {}),
        }
        data = self._post_json(endpoint, payload)
        return {
            "llm_key": self.llm_key,
            "provider_type": self.provider_type,
            "model": payload.get("model"),
            "text": self._extract_text(data),
            "raw": data,
        }

    def embeddings(self, text: str) -> dict[str, Any]:
        endpoint = str(self.config.get("embedding_url") or f"{self.base_url}/embeddings")
        payload = {
            "model": self.config.get("embedding_model") or self.default_model,
            "input": text,
        }
        data = self._post_json(endpoint, payload)
        vector = []
        if isinstance(data.get("data"), list) and data["data"]:
            vector = data["data"][0].get("embedding") or []
        return {"llm_key": self.llm_key, "vector": vector, "raw": data}

    def models(self) -> list[dict[str, Any]]:
        model_name = self.default_model or f"{self.provider_type}-default"
        return [{"id": model_name, "label": model_name, "provider_type": self.provider_type}]


from __future__ import annotations

from app.ai_gateway.adapters.base import BaseLLMAdapter


class AnthropicAdapter(BaseLLMAdapter):
    def chat(self, messages, options=None):
        endpoint = str(self.config.get("chat_url") or f"{self.base_url}/messages")
        payload = {
            "model": (options or {}).get("model") or self.default_model,
            "messages": messages,
            **self.options,
            **(options or {}),
        }
        api_key = self.get_api_key()
        data = self._post_json(
            endpoint,
            payload,
            extra_headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        return {
            "llm_key": self.llm_key,
            "provider_type": self.provider_type,
            "model": payload.get("model"),
            "text": self._extract_text(data),
            "raw": data,
        }

    def embeddings(self, text):
        return {"llm_key": self.llm_key, "vector": [], "raw": {"detail": "anthropic_embeddings_not_configured", "input": text}}

    def models(self):
        model_name = self.default_model or "anthropic-default"
        return [{"id": model_name, "label": model_name, "provider_type": self.provider_type}]

from __future__ import annotations

import re

from app.ai_gateway.adapters.anthropic_adapter import AnthropicAdapter
from app.ai_gateway.adapters.custom_adapter import CustomRestAdapter
from app.ai_gateway.adapters.deepseek_adapter import DeepSeekAdapter
from app.ai_gateway.adapters.glm_adapter import GlmAdapter
from app.ai_gateway.adapters.local_adapter import LocalAdapter
from app.ai_gateway.adapters.minimax_adapter import MiniMaxAdapter
from app.ai_gateway.adapters.openai_adapter import OpenAIAdapter
from app.ai_gateway.core.config_store import delete_list_item, load_config, upsert_list_item


class LLMPool:
    def __init__(self) -> None:
        self._configs: list[dict] = []
        self._adapters: dict[str, object] = {}
        self.refresh()

    def refresh(self) -> None:
        self._configs = []
        self._adapters = {}
        config = load_config()
        for row in config.get("llms", []):
            row = self._normalize_secret_fields(dict(row))
            llm_key = str(row.get("llm_key", "")).strip()
            if not llm_key:
                continue
            adapter = self._build_adapter(llm_key, row)
            self._configs.append(dict(row))
            self._adapters[llm_key] = adapter

    def list_llms(self) -> list[dict]:
        rows = []
        for row in self._configs:
            adapter = self._adapters.get(str(row.get("llm_key", "")).strip())
            safe_row = dict(row)
            api_key = str(safe_row.pop("api_key", "") or "").strip()
            safe_row["api_key_present"] = bool(api_key or (adapter and adapter.get_api_key()))
            safe_row["api_key_mask"] = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) >= 8 else ("已保存" if api_key else "")
            rows.append(
                {
                    **safe_row,
                    "ready": adapter.is_ready() if adapter else False,
                    "models": adapter.models() if adapter else [],
                }
            )
        return rows

    def get(self, llm_key: str):
        return self._adapters.get(llm_key)

    def register(self, payload: dict) -> dict:
        item = upsert_list_item("llms", payload, "llm_key")
        self.refresh()
        return item

    def delete(self, llm_key: str) -> dict:
        result = delete_list_item("llms", llm_key, "llm_key")
        self.refresh()
        return result

    def _build_adapter(self, llm_key: str, row: dict):
        provider_type = str(row.get("provider_type", "")).strip()
        factory = {
            "openai": OpenAIAdapter,
            "anthropic": AnthropicAdapter,
            "glm": GlmAdapter,
            "minimax": MiniMaxAdapter,
            "deepseek": DeepSeekAdapter,
            "local": LocalAdapter,
            "custom": CustomRestAdapter,
            "rest": CustomRestAdapter,
        }.get(provider_type, CustomRestAdapter)
        return factory(llm_key, row)

    def _normalize_secret_fields(self, row: dict) -> dict:
        api_key_env = str(row.get("api_key_env", "") or "").strip()
        if api_key_env and not row.get("api_key") and self._looks_like_plain_api_key(api_key_env):
            row["api_key"] = api_key_env
            row["api_key_env"] = ""
        return row

    def _looks_like_plain_api_key(self, value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", text):
            return False
        return len(text) > 24 or "-" in text or "." in text or bool(re.search(r"[a-z]{6,}", text))

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any
from urllib import error, request


class BaseLLMAdapter(ABC):
    def __init__(self, llm_key: str, config: dict[str, Any]) -> None:
        self.llm_key = llm_key
        self.config = config
        self.provider_type = str(config.get("provider_type", "")).strip()
        self.base_url = str(config.get("base_url", "")).strip().rstrip("/")
        self.default_model = str(config.get("default_model", "")).strip()
        self.api_key_env = str(config.get("api_key_env", "")).strip()
        self.api_key = str(config.get("api_key", "")).strip()
        self.options = dict(config.get("options", {}) or {})

    @abstractmethod
    def chat(self, messages: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def embeddings(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def models(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def is_ready(self) -> bool:
        if not self.config.get("enabled", False):
            return False
        if self.api_key:
            return bool(self.base_url)
        if self.api_key_env:
            return bool(os.getenv(self.api_key_env))
        return bool(self.base_url)

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.getenv(self.api_key_env) if self.api_key_env else ""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _post_json(self, url: str, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        req = request.Request(url=url, data=body, headers=headers, method="POST")
        max_retries = int(self.options.get("max_retries", 2) or 2)
        retry_statuses = {408, 409, 425, 429, 500, 502, 503, 504, 529}
        last_error = ""
        for attempt in range(max(1, max_retries + 1)):
            try:
                with request.urlopen(req, timeout=60) as resp:
                    text = resp.read().decode("utf-8")
                return json.loads(text) if text else {}
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = f"HTTP {exc.code}: {detail or exc.reason}"
                if exc.code not in retry_statuses or attempt >= max_retries:
                    raise RuntimeError(last_error) from exc
                time.sleep(min(1.5 * (attempt + 1), 5))
            except error.URLError as exc:
                last_error = f"URL error: {exc.reason}"
                if attempt >= max_retries:
                    raise RuntimeError(last_error) from exc
                time.sleep(min(1.5 * (attempt + 1), 5))
        raise RuntimeError(last_error or "LLM request failed")

    def _extract_text(self, payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return self._clean_model_text(payload["output_text"])
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] or {}
            message = first.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return self._clean_model_text(content)
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                return self._clean_model_text("\n".join(parts))
        content = payload.get("content")
        if isinstance(content, str):
            return self._clean_model_text(content)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return self._clean_model_text("\n".join(parts))
        return ""

    def _clean_model_text(self, text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", str(text or ""), flags=re.IGNORECASE).strip()

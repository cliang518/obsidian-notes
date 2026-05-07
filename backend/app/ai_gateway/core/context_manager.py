from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.ai_gateway.core.config_store import MEMORY_DIR, SESSIONS_DIR, ensure_bootstrap
from app.ai_gateway.core.logging import get_ai_gateway_logger


logger = get_ai_gateway_logger()


class ContextManager:
    def __init__(self, memory_window: int = 20) -> None:
        ensure_bootstrap()
        self.memory_window = max(1, int(memory_window or 20))
        self.memory_file: Path = MEMORY_DIR / "memory.jsonl"

    def create_session(self, title: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        session_id = uuid4().hex
        payload = {
            "session_id": session_id,
            "title": title or "未命名会话",
            "metadata": metadata or {},
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._save_session(payload)
        return payload

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        ensure_bootstrap()
        rows: list[dict[str, Any]] = []
        for path in SESSIONS_DIR.glob("*.json"):
            try:
                session = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            messages = list(session.get("messages", []) or [])
            user_messages = [row for row in messages if row.get("role") == "user"]
            assistant_messages = [row for row in messages if row.get("role") == "assistant"]
            first_task = user_messages[0].get("content") if user_messages else {}
            last_task = user_messages[-1].get("content") if user_messages else {}
            last_assistant = assistant_messages[-1].get("content") if assistant_messages else {}
            task_type = ""
            title_hint = ""
            if isinstance(last_task, dict):
                task_type = str(last_task.get("task_type") or "")
                title_hint = str(last_task.get("task") or "")
            elif isinstance(last_task, str):
                title_hint = last_task
            if not task_type and isinstance(first_task, dict):
                task_type = str(first_task.get("task_type") or "")
            display_title = title_hint.strip() or session.get("title", "未命名会话")
            if len(display_title) > 42:
                display_title = display_title[:42] + "..."
            rows.append(
                {
                    "session_id": session.get("session_id", path.stem),
                    "title": session.get("title", "未命名会话"),
                    "display_title": display_title,
                    "task_type": task_type or str((session.get("metadata") or {}).get("task_type") or "general"),
                    "metadata": session.get("metadata", {}),
                    "message_count": len(messages),
                    "user_message_count": len(user_messages),
                    "assistant_message_count": len(assistant_messages),
                    "created_at": session.get("created_at", ""),
                    "updated_at": session.get("updated_at", ""),
                    "last_task": title_hint,
                    "last_status": self._status_from_assistant(last_assistant),
                }
            )
        rows.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return rows[: max(1, min(int(limit or 50), 200))]

    def get_or_create_session(self, session_id: str | None, title: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if session_id:
            found = self.get_session(session_id)
            if found:
                return found
        return self.create_session(title=title, metadata=metadata)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.exception("读取 AI 会话失败: %s", exc)
            return None

    def delete_session(self, session_id: str) -> bool:
        path = self._session_path(session_id)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

    def cleanup_test_sessions(self, *, keep_latest: int = 12) -> dict[str, Any]:
        sessions = self.list_sessions(limit=200)
        protected = {row["session_id"] for row in sessions[: max(0, keep_latest)]}
        removed: list[str] = []
        for row in sessions:
            session_id = row.get("session_id", "")
            title = f"{row.get('title', '')} {row.get('display_title', '')} {row.get('last_task', '')}".lower()
            looks_like_test = any(word in title for word in ("你好", "测试", "test", "hello")) or int(row.get("message_count") or 0) <= 2
            if session_id and session_id not in protected and looks_like_test and self.delete_session(session_id):
                removed.append(session_id)
        return {"removed_count": len(removed), "removed_session_ids": removed, "kept_latest": keep_latest}

    def append_message(self, session_id: str, role: str, content: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self.get_or_create_session(session_id)
        message = {
            "role": role,
            "content": content,
            "extra": extra or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        messages = list(session.get("messages", []))
        messages.append(message)
        session["messages"] = messages[-self.memory_window :]
        session["updated_at"] = datetime.utcnow().isoformat()
        self._save_session(session)
        return session

    def remember(self, memory_type: str, payload: dict[str, Any]) -> None:
        item = {
            "memory_type": memory_type,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        with self.memory_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    def recent_memory(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.memory_file.exists():
            return []
        rows = self.memory_file.read_text(encoding="utf-8").splitlines()
        result = []
        for line in rows[-max(1, limit) :]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result

    def _session_path(self, session_id: str) -> Path:
        ensure_bootstrap()
        return SESSIONS_DIR / f"{session_id}.json"

    def _save_session(self, session: dict[str, Any]) -> None:
        path = self._session_path(session["session_id"])
        path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _status_from_assistant(content: Any) -> str:
        if not isinstance(content, dict):
            return ""
        llm = content.get("llm") or {}
        if isinstance(llm, dict) and llm.get("status"):
            return str(llm.get("status"))
        skill_payload = ((content.get("task_context") or {}).get("skill_payload") or {})
        if isinstance(skill_payload, dict) and skill_payload.get("status"):
            return str(skill_payload.get("status"))
        return "completed"

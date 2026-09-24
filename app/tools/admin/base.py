"""
Admin Tool Base Class
======================
Abstract base for all admin tools. Each tool wraps an existing admin API
endpoint, providing a structured interface for LLM function calling.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional


class AdminTool(ABC):
    """Base class for admin tools used by the Admin Agent."""

    # Tool identity
    name: str = ""
    description: str = ""  # English description for LLM
    description_th: str = ""  # Thai description for UI display
    category: str = ""  # grouping: mapping, rule, example, onboarding, analysis, system

    # Which DB the tool's tables live in: "config" (mappings, rules, examples) or "app" (chat history, feedback)
    database: str = "config"

    # Safety
    requires_confirmation: bool = False  # If True, agent asks user to confirm before executing

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool parameters (OpenAI function calling format).

        Returns:
            Dict with 'type', 'properties', 'required' keys.
        """
        ...

    @abstractmethod
    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        """Execute the tool with given parameters.

        Args:
            params: Validated parameters matching parameters_schema.
            db: SQLAlchemy session on the tool's `database` — callers get one from tool_session().

        Returns:
            Dict with at least:
                - success: bool
                - message: str (Thai)
                - data: Any (optional result data)
        """
        ...

    def get_spec(self) -> Dict[str, Any]:
        """Get tool specification for LLM function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }


@contextmanager
def tool_session(tool: AdminTool):
    """A session on the DB the tool's tables live in. The caller's own session is not it:
    the Admin Agent holds an app-DB session, config tables live in the config DB."""
    from app.db import session as db_session
    db = (db_session.SessionLocal if tool.database == "app" else db_session.ConfigSessionLocal)()
    try:
        yield db
    finally:
        db.close()


def audit_change(**kwargs) -> None:
    """config_audit_log lives in the app DB; a config tool's own session is the config DB."""
    from app.db import session as db_session
    from app.services.audit_service import AuditService
    db = db_session.SessionLocal()
    try:
        AuditService(db).log_change(**kwargs)
    finally:
        db.close()


def duplicate(row, label: str, **content) -> Dict[str, Any]:
    """The "already there" answer of an add tool, about `row`. It goes to the agent's model: a row's content only
    while it is in use (status active) — a proposal or a rejected row is named by id and status, nothing it says
    (Plan 8.1 readers rule; second review round). `label` names what was asked for, from the request itself."""
    status = getattr(row, "status", None) or "active"
    if status != "active":
        return {"success": False, "data": {"id": row.id, "status": status},
                "message": f"{label} มีแถวสถานะ {status} อยู่แล้ว (id={row.id}) — ตัดสินที่หน้า admin / คิวข้อเสนอ "
                           "ไม่ใช่เพิ่มซ้ำ"}
    return {"success": False, "data": {"id": row.id, "status": status, **content},
            "message": f"{label} มีอยู่แล้ว (id={row.id})"}

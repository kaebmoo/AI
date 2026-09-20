"""
What may leave for a caller outside the process (Plan 7 hardening)
===================================================================
``POST /api/v1/query`` and the external MCP facade answer callers we do not run: a portal, an LLM
holding its own key. The engine's own prose is not safe for them — a query that ran and returned no
rows puts the **whole SQL** in its explanation (``hybrid_flow``), a query that failed puts the text
of the exception (file paths, table names) in ``error`` and in the explanation. So on those channels
a failure is one *code* and one *fixed message* from this table, and the engine's prose is passed on
only for a result that actually has rows.

Internal channels (chat, telegram, admin) are unchanged: there the SQL and the real error are what
the person needs to see.
"""

from typing import Any, Dict, Optional, Tuple

# code → (HTTP-equivalent status, message). The only error texts these channels ever return.
ERRORS: Dict[str, Tuple[int, str]] = {
    "unauthorized": (401, "API key ใช้ไม่ได้"),
    "rate_limited": (429, "API key เกิน rate limit หรือโควตารายวัน — ลองใหม่ภายหลัง"),
    "invalid_scope": (400, "scope ใช้กับ context นี้ไม่ได้ (key ที่ context ไม่ได้ประกาศ หรือค่าไม่ถูกต้อง) — ไม่ตอบแบบไม่มี scope"),
    "context_not_allowed": (403, "API key นี้ไม่มีสิทธิ์ใช้ context ที่ขอ — ดู list_contexts"),
    "policy_refused": (403, "context นี้ไม่เปิดให้ใช้ผ่าน MCP (นโยบายข้อมูลของ source ไม่อนุญาตให้ส่งออกไปยังโมเดลภายนอก)"),
    "invalid_arguments": (400, "argument ของ tool ไม่ถูกต้อง (เช่น question ว่าง)"),
    "duplicate_request": (409, "คำถามเดียวกันกำลังประมวลผลอยู่ — รอสักครู่แล้วถามใหม่"),
    # the source is mid-publish or failed verification: the reason names file paths, the meaning does not
    "source_unavailable": (503, "แหล่งข้อมูลของ context นี้ยังไม่พร้อมใช้งาน (ข้อมูลอาจกำลังถูก publish) — กรุณาถามใหม่อีกครั้ง"),
    "query_failed": (422, "ตอบคำถามนี้ไม่ได้ — ลองถามให้เจาะจงขึ้น หรือระบุ context"),
    "internal_error": (500, "เกิดข้อผิดพลาดภายใน"),
}

NO_DATA = "ไม่พบข้อมูลที่ตรงกับเงื่อนไข"


class Refused(Exception):
    """A refusal already reduced to one of the codes above."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def message(code: str) -> str:
    return ERRORS[code][1]


def status(code: str) -> int:
    return ERRORS[code][0]


def find(exc: BaseException, kinds) -> Optional[BaseException]:
    """`exc` or the first thing inside its (nested) exception groups that is one of `kinds`."""
    if isinstance(exc, kinds):
        return exc
    for inner in getattr(exc, "exceptions", None) or ():
        found = find(inner, kinds)
        if found is not None:
            return found
    return None


def code_for(exc: BaseException, named_in_rights: bool = False) -> str:
    """The code for a raised failure. `named_in_rights`: the caller named a context its key may use —
    then a refusal from the context itself is the policy, not a wrong name (no existence oracle)."""
    from pydantic import ValidationError

    from app.core.llm_policy import LLMPolicyError
    from app.services.data_sources import ScopeError
    from app.services.database_adapter import SourceUnavailable
    from app.services.workspaces import ContextNotAllowed

    if isinstance(exc, Refused):
        return exc.code
    if isinstance(exc, ValidationError):  # SimpleQueryRequest: empty question, …
        return "invalid_arguments"
    if find(exc, ScopeError):
        return "invalid_scope"
    if find(exc, LLMPolicyError):
        return "policy_refused"
    if find(exc, ContextNotAllowed):
        return "policy_refused" if named_in_rights else "context_not_allowed"
    if find(exc, SourceUnavailable):
        return "source_unavailable"
    return "internal_error"


def result_code(raw_error: Optional[str]) -> str:
    """The code for a QueryResult that came back with `error` set — its text is the engine's, not ours."""
    return raw_error if raw_error in ERRORS else "query_failed"


def explanation_text(query_result: Any) -> str:
    """The explanation as text: a structured explanation (text + chart config) is a dict, and str(dict)
    is not an answer."""
    explanation = getattr(query_result, "explanation", None)
    if isinstance(explanation, dict):
        explanation = explanation.get("explanation")
    return str(explanation or "")


def safe_answer(query_result: Any) -> str:
    """The answer text for an outside caller: the engine's prose only for a result WITH rows."""
    if query_result is None:
        return message("query_failed")
    if query_result.error:
        return message(result_code(query_result.error))
    return explanation_text(query_result) if query_result.data else NO_DATA

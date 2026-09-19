"""
LLM data policy (Plan 7 Phase 4.5)
===================================
What of a source's data may reach an LLM provider — ``data_sources.llm_data_policy``:

- ``full``            rows, sample values, looked-up values may be sent (behaviour before Phase 4.5)
- ``aggregated_only`` like schema_only, except that the rows of an aggregate query may be explained by the LLM
- ``schema_only``     the provider sees schema + question + written knowledge; nothing read from the rows

Enforced at two ends, so a caller in between needs no knowledge of it:
- the sink: ``AIProvider`` wraps every provider method with ``guard_call`` (app/providers/base.py)
- the sources of values (sample values, value lookup, value verifier, onboarding) return nothing

The policy of the running request lives in ``request_llm_policy`` (set by QueryEngine, like
request_scope). Unreadable / unknown policy = schema_only. No policy set (admin flows, scripts) = the
provider is not restricted; those flows are covered at the source of the values (``policy_for_table``).
"""

import inspect
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

FULL = "full"
AGGREGATED_ONLY = "aggregated_only"
SCHEMA_ONLY = "schema_only"
POLICIES = (FULL, AGGREGATED_ONLY, SCHEMA_ONLY)


class LLMPolicyError(PermissionError):
    """The source's policy forbids this provider call → HTTP 403, never retried with another payload."""


def normalize(value: Any) -> str:
    return value if value in POLICIES else SCHEMA_ONLY


def parse_allowlist(raw: Any) -> Optional[frozenset]:
    """NULL = any provider; a list = only these; anything unreadable = none (fail closed)."""
    if raw is None or raw == "":
        return None
    try:
        names = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(names, list) and all(isinstance(n, str) for n in names):
            return frozenset(names)
    except ValueError:
        pass
    return frozenset()


@dataclass
class RequestPolicy:
    policy: str = FULL
    providers: Optional[frozenset] = None  # provider names allowed for this source; None = any
    source: str = ""
    question: str = ""
    taint: set = field(default_factory=set)  # values read from result rows during this request


request_llm_policy: ContextVar[Optional[RequestPolicy]] = ContextVar("request_llm_policy", default=None)


def restricted() -> bool:
    state = request_llm_policy.get()
    return state is not None and state.policy != FULL


# ponytail: keyword check, not a parser — a query is "aggregate" when it groups or uses SUM/COUNT/AVG.
# MIN/MAX return a single real row value, so they don't count. Upgrade: k-anonymity (group size >= k)
# needs COUNT(*) per group in the executed SQL — with column classification (D5, deferred).
_AGGREGATE_RE = re.compile(r"\bGROUP\s+BY\b|\b(?:SUM|COUNT|AVG)\s*\(", re.IGNORECASE)


def is_aggregate_sql(sql: Optional[str]) -> bool:
    return bool(sql and _AGGREGATE_RE.search(sql))


def rows_may_reach_llm(sql: Optional[str]) -> bool:
    state = request_llm_policy.get()
    if state is None or state.policy == FULL:
        return True
    return state.policy == AGGREGATED_ONLY and is_aggregate_sql(sql)


def _taint(rows: Any) -> None:
    state = request_llm_policy.get()
    if state is None or not isinstance(rows, list):
        return
    for row in rows:
        for value in (row.values() if isinstance(row, dict) else ()):
            text = str(value)
            # short values ("A", 7, 2025) would match schema text by accident; the question's own words are the caller's
            if value is not None and not isinstance(value, bool) and len(text) >= (3 if isinstance(value, str) else 5) \
                    and text not in state.question:
                state.taint.add(text)


_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\d[\d.,]{2,}")


def scrub_error(message: Any) -> str:
    """A DB error can quote a row value (DuckDB: Could not convert string 'X'); identifiers stay."""
    return _LITERAL_RE.sub("?", str(message))


class PolicyMCPClient:
    """The request's MCP client under a restricted policy: rows read by execute_query are remembered
    (the provider guard refuses any payload carrying one) and its errors lose their literals."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        result = await self._inner.call_tool(tool_name, arguments)
        if tool_name != "execute_query":
            return result
        try:
            payload = json.loads(result) if isinstance(result, str) else result
        except ValueError:
            return result
        if isinstance(payload, dict) and payload.get("error"):
            payload["error"] = scrub_error(payload["error"])
            return json.dumps(payload, ensure_ascii=False, default=str)
        if not rows_may_reach_llm(arguments.get("sql")):
            _taint(payload.get("data") if isinstance(payload, dict) else payload)
        return result


_SQL_BLOCK_RE = re.compile(r"```sql.*?```", re.DOTALL | re.IGNORECASE)


def history_without_answers(history: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """Earlier assistant turns carry explanations of earlier results — keep only their SQL."""
    if not history:
        return history
    kept = []
    for msg in history:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            kept.append(msg)
        elif msg.get("role") in ("assistant", "model") and isinstance(msg.get("content"), str):
            sql = "\n".join(_SQL_BLOCK_RE.findall(msg["content"]))
            if sql:
                kept.append({"role": msg["role"], "content": sql})
    return kept


def no_llm_explanation(question: str, sql: str, data: List[Dict]) -> Any:
    from app.services.ai.template_answer import build_template_answer

    return build_template_answer(question, sql, data) or {"explanation": f"พบข้อมูล {len(data)} รายการ"}


async def guard_call(provider, method: str, fn, args: tuple, kwargs: dict) -> Any:
    """Every provider call of every AIProvider subclass goes through here (see AIProvider.__init_subclass__)."""
    state = request_llm_policy.get()
    if state is None:
        return await fn(provider, *args, **kwargs)
    if state.providers is not None and provider.name not in state.providers:
        raise LLMPolicyError(f"provider '{provider.name}' ไม่อยู่ใน llm_provider_allowlist ของ source '{state.source}'")
    if state.policy == FULL:
        return await fn(provider, *args, **kwargs)

    bound = inspect.signature(fn).bind(provider, *args, **kwargs)
    call = bound.arguments
    if method == "generate_sql":  # tool loop: tool results (rows, sample values) go back to the provider
        raise LLMPolicyError(f"tool loop ใช้ไม่ได้กับ source '{state.source}' (llm_data_policy={state.policy})")
    if method == "explain_result" and not rows_may_reach_llm(call.get("sql")):
        return no_llm_explanation(call.get("question", ""), call.get("sql", ""), call.get("data") or [])
    if "history" in call:
        call["history"] = history_without_answers(call["history"])
    if method != "explain_result":  # an allowed explain_result carries its rows by design
        payload = "\n".join(str(v) for k, v in call.items() if k != "self")
        if any(value in payload for value in state.taint):
            raise LLMPolicyError(f"payload มีค่าจากผลลัพธ์ของ source '{state.source}' (llm_data_policy={state.policy})")
    return await fn(*bound.args, **bound.kwargs)

"""
Questions across several contexts (Plan 7 Phase 5)
====================================================
"รายได้และค่าใช้จ่ายเดือนนี้" needs two contexts; the router picks one and the other half is dropped
silently. Here such a question is split into one sub-question per context, every sub-question runs
through ``QueryEngine.query`` unchanged (scope, allowlist, pinned, llm policy, audit and cache are
its), and the answers are put together **by code** — no JOIN across sources, no LLM in the combine
step, no number that didn't come out of a sub-question's own SQL.

    candidates (deterministic)  →  split (one LLM call, sees the question + the candidates' names)
        →  sub-questions in parallel  →  template + optional ratio / difference computed here

Off unless ``admin_config.multi_context_workspaces`` (JSON list of workspace names) names the
workspace. Never crosses a workspace, never leaves the caller's allowlist. A caller that names a
context stays on the single-context path. Stateless: no history — the only entry point is /api/v1/query.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from app.core import outbound
from app.core.llm_policy import AGGREGATED_ONLY, FULL, SCHEMA_ONLY, LLMPolicyError, RequestPolicy, normalize, request_llm_policy
from app.services import query_audit
from app.services.data_sources import ScopeError, source_resolver
from app.services.workspaces import DEFAULT_WORKSPACE, ContextNotAllowed

logger = logging.getLogger(__name__)

CONFIG_KEY = "multi_context_workspaces"
MAX_PARTS = 4
_STRICTNESS = {FULL: 0, AGGREGATED_ONLY: 1, SCHEMA_ONLY: 2}
_REFUSALS = (ScopeError, ContextNotAllowed, LLMPolicyError)  # the caller's request is refused — whole question

SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "parts": {"type": "array", "items": {"type": "object", "properties": {
            "context": {"type": "string"}, "question": {"type": "string"}}, "required": ["context", "question"]}},
        "operation": {"type": "string", "enum": ["none", "ratio", "difference"]},
        "operands": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["parts", "operation"],
}

SPLIT_SYSTEM = (
    "You split one business question into sub-questions, one per data context. Reply with JSON only.\n"
    "Rules:\n"
    "- Use only the context names listed. At most one sub-question per context.\n"
    "- If ONE context answers the whole question, return that single part (question unchanged).\n"
    "- Each sub-question is a complete Thai question on its own: copy the period, organisation, product "
    "and every other filter of the original into each one; ask only for that context's measure.\n"
    "- Never put a number in a sub-question that is not in the original. Never answer the question.\n"
    '- "operation": "ratio" (parts[a] ÷ parts[b]) or "difference" (parts[a] − parts[b]) ONLY when the '
    'original explicitly asks for a ratio / difference between two parts; then "operands": [a, b] '
    '(0-based, in the order the original states them). Otherwise "none".\n'
    'Output: {"parts": [{"context": "...", "question": "..."}], "operation": "none", "operands": []}'
)


@dataclass
class Part:
    context: str
    question: str
    display_name: str = ""
    result: Any = None  # QueryEngineResult
    error: Optional[str] = None       # the engine's own words — for the audit row and the log only
    error_code: Optional[str] = None  # … the same failure as one outbound code (app/core/outbound.py)

    @property
    def code(self) -> Optional[str]:
        """The failure as an outside caller sees it — a failure whose code nobody set is still a failure."""
        return self.error_code or ("query_failed" if self.error else None)

    @property
    def ok(self) -> bool:
        return self.error is None and self.result is not None and bool(self.result.query_result.data)

    @property
    def period(self) -> Optional[int]:
        as_of = getattr(self.result, "data_as_of", None)
        return as_of.get("period") if isinstance(as_of, dict) else None


@dataclass
class MultiResult:
    parts: List[Part]
    answer: str
    computed: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    request_group: str = ""

    @property
    def context_name(self) -> str:
        return "+".join(p.context for p in self.parts)


@dataclass
class SingleContext:
    """The split said one context answers it all — run the ordinary pipeline there."""
    context: str


def enabled_workspaces(admin_config) -> FrozenSet[str]:
    """Unreadable = off."""
    try:
        names = json.loads(admin_config.get_config(CONFIG_KEY, "") or "[]")
        return frozenset(n for n in names if isinstance(n, str)) if isinstance(names, list) else frozenset()
    except Exception:
        return frozenset()


def _workspaces(config_engine=None) -> Dict[int, str]:
    from sqlalchemy import text
    from app.services.workspaces import _config_engine
    with (config_engine or _config_engine()).connect() as conn:
        return {row[0]: row[1] for row in conn.execute(text("SELECT id, name FROM workspaces WHERE is_active = 1"))}


def candidates(question: str, contexts: List[Dict], allowed: Optional[FrozenSet[str]],
               workspaces: Dict[int, str], enabled: FrozenSet[str]) -> List[Dict]:
    """Contexts of ONE enabled workspace whose own keyword is in the question — deterministic.

    "Own" = no other usable context of that workspace lists it: the markers every feed context
    shares ("feed", "dashboard") say nothing about which one is meant. Fewer than two = not a
    multi-context question. Contexts outside the caller's allowlist are not even looked at."""
    q = question.lower()
    by_workspace: Dict[str, List[Dict]] = {}
    for ctx in contexts:
        if allowed is not None and ctx.get("name") not in allowed:
            continue
        ws_id = ctx.get("workspace_id")
        workspace = DEFAULT_WORKSPACE if ws_id is None else workspaces.get(ws_id)
        if workspace in enabled:
            by_workspace.setdefault(workspace, []).append(ctx)
    best: List[Dict] = []
    for group in by_workspace.values():
        keywords = {c["name"]: {str(k).lower() for k in (c.get("keywords") or []) if isinstance(k, str)} for c in group}
        found = [c for c in group
                 if any(k in q and not any(k in other for name, other in keywords.items() if name != c["name"])
                        for k in keywords[c["name"]])]
        if len(found) > len(best):
            best = found
    return best[:MAX_PARTS] if len(best) >= 2 else []


def _strictest(sources) -> RequestPolicy:
    """The split call sees no data, but it is a provider call made for these sources: the strictest of
    their policies, and a provider every one of them allows (none in common = refused)."""
    policy, providers = FULL, None
    for source in sources:
        p = normalize(getattr(source, "llm_data_policy", None))
        policy = p if _STRICTNESS[p] > _STRICTNESS[policy] else policy
        allow = getattr(source, "llm_providers", None)
        if allow is not None:
            allow = allow if isinstance(allow, frozenset) else frozenset()
            providers = allow if providers is None else providers & allow
    return RequestPolicy(policy=policy, providers=providers, source="+".join(str(s.name) for s in sources))


def parse_split(raw: Any, names: List[str]) -> Optional[Dict[str, Any]]:
    """The split as (parts, operation, operands) — or None: anything off is no split at all."""
    if isinstance(raw, str):
        try:
            text_ = raw.strip()
            raw = json.loads(text_[text_.index("{"):text_.rindex("}") + 1])
        except ValueError:
            return None
    if not isinstance(raw, dict) or not isinstance(raw.get("parts"), list) or not 1 <= len(raw["parts"]) <= len(names):
        return None
    parts, seen = [], set()
    for item in raw["parts"]:
        context = item.get("context") if isinstance(item, dict) else None
        sub = item.get("question") if isinstance(item, dict) else None
        if context not in names or context in seen or not isinstance(sub, str) or not 0 < len(sub.strip()) <= 1000:
            return None
        seen.add(context)
        parts.append((context, sub.strip()))
    operation, operands = raw.get("operation", "none"), raw.get("operands") or []
    if operation not in ("ratio", "difference") or len(parts) < 2:
        return {"parts": parts, "operation": "none", "operands": []}
    if (not isinstance(operands, list) or len(operands) != 2 or operands[0] == operands[1]
            or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(parts) for i in operands)):
        return {"parts": parts, "operation": "none", "operands": []}
    return {"parts": parts, "operation": operation, "operands": operands}


async def _split(engine, question: str, found: List[Dict], provider: Optional[str]) -> Optional[Dict[str, Any]]:
    sources = [source_resolver.for_context(c["name"]) for c in found]  # unscoped: policy only — sub-questions enforce scope
    state = _strictest(sources)
    state.question = question
    if state.providers is not None and not state.providers:
        raise LLMPolicyError("source ของคำถามนี้ไม่มี LLM provider ที่อนุญาตร่วมกัน")
    ai_config = engine.admin_config.get_ai_config() if engine.admin_config else {}
    instance, _ = engine._provider_for(provider, ai_config, {}, state.providers, state.source)
    cheap = instance.get_model("cheap")
    if cheap:
        instance.model = cheap
    listing = "\n".join(
        f"- {c['name']}: {c.get('display_name') or ''} — {c.get('description') or ''} "
        f"(keywords: {', '.join(str(k) for k in (c.get('keywords') or []))})" for c in found)
    prompt = f"Question: {question}\n\nContexts:\n{listing}"
    token = request_llm_policy.set(state)  # outside QueryEngine.query nothing else would hold this call to a policy
    try:
        raw = await instance.generate_structured(prompt, SPLIT_SCHEMA, system_prompt=SPLIT_SYSTEM, schema_name="split")
        if raw is None:
            raw = await instance.generate_content(prompt, system_prompt=SPLIT_SYSTEM)
    finally:
        request_llm_policy.reset(token)
    return parse_split(raw, [c["name"] for c in found])


def _scalar(part: Part) -> Optional[float]:
    # ponytail: "the" number of a part = the only float in its single row. An int is a period, a code or a
    # count — never taken for the measure (review 2026-09-19: a lone `SELECT month` would have been divided).
    # Two measures in one row = not computable here; the parts still show both.
    rows = part.result.query_result.data if part.ok else None
    if not rows or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    floats = [v for v in rows[0].values() if isinstance(v, float) and v == v and abs(v) != float("inf")]
    return floats[0] if len(floats) == 1 else None


def compute(parts: List[Part], operation: str, operands: List[int]) -> Optional[Dict[str, Any]]:
    """ratio / difference of two parts, in code. Only when every part answered, both are one number,
    and both sources stand at the same latest period (owner's decision 2026-09-19)."""
    if operation not in ("ratio", "difference") or not all(p.ok for p in parts):
        return None
    a, b = parts[operands[0]], parts[operands[1]]
    x, y = _scalar(a), _scalar(b)
    if x is None or y is None or a.period != b.period or (operation == "ratio" and y == 0):
        return None
    return {"operation": operation, "operands": [a.context, b.context], "values": [x, y],
            "value": x / y if operation == "ratio" else x - y}


def _text(explanation: Any) -> str:
    if isinstance(explanation, dict):
        explanation = explanation.get("explanation")
    return str(explanation or "").strip()


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


def combine(parts: List[Part], computed: Optional[Dict[str, Any]], wanted: str) -> (str, List[str]):
    """The answer text — every number under the context, sub-question and period it came from."""
    ok = [p for p in parts if p.ok]
    warnings: List[str] = []
    lines = [f"คำถามนี้ใช้ข้อมูลจาก {len(parts)} แหล่ง — ตัวเลขแต่ละส่วนมาจากแหล่งของตัวเอง ไม่ได้รวมกันในฐานข้อมูล"]
    if len(ok) < len(parts):
        warnings.append(f"ตอบได้ {len(ok)} จาก {len(parts)} ส่วน — ส่วนที่ตอบไม่ได้ระบุไว้ด้านล่าง คำตอบนี้จึงไม่ครบ")
        lines.append(f"⚠️ {warnings[-1]}")
    for i, part in enumerate(parts, 1):
        period = f" — ข้อมูลถึงงวด {part.period}" if part.period else ""
        lines.append(f"\n**{i}. {part.display_name or part.context} (`{part.context}`){period}**\nคำถามย่อย: {part.question}")
        if part.ok:
            lines.append(_text(part.result.query_result.explanation) or f"พบข้อมูล {len(part.result.query_result.data)} รายการ")
        else:
            # the text of the failure stays in part.error (audit, log): this answer leaves the process
            lines.append("⚠️ ส่วนนี้ตอบไม่ได้: "
                         + (outbound.message(part.code) if part.code else outbound.NO_DATA))
    if computed:
        x, y = computed["values"]
        a, b = computed["operands"]
        if computed["operation"] == "ratio":
            lines.append(f"\n**คำนวณจากผลข้างต้น:** `{a}` ÷ `{b}` = {_fmt(x)} ÷ {_fmt(y)} = **{computed['value']:,.4f}**")
        else:
            lines.append(f"\n**คำนวณจากผลข้างต้น:** `{a}` − `{b}` = {_fmt(x)} − {_fmt(y)} = **{_fmt(computed['value'])}**\n"
                         "(ส่วนต่างของตัวเลขจากสองแหล่งข้อมูล — ไม่ใช่กำไร / EBT ทางการ)")
    elif wanted in ("ratio", "difference"):
        warnings.append("ไม่ได้คำนวณข้ามแหล่งข้อมูล: ต้องได้ค่าเดียวจากทุกส่วน และงวดล่าสุดของแหล่งข้อมูลต้องเท่ากัน")
        lines.append(f"\n⚠️ {warnings[-1]}")
    periods = {p.context: p.period for p in ok if p.period}
    if len(set(periods.values())) > 1:
        warnings.append("งวดข้อมูลล่าสุดของแต่ละแหล่งไม่เท่ากัน (" + ", ".join(f"{c} {v}" for c, v in periods.items())
                        + ") — ตรวจงวดของแต่ละตัวเลขก่อนเปรียบเทียบ")
        lines.append(f"\n⚠️ {warnings[-1]}")
    return "\n".join(lines), warnings


async def answer(engine, question: str, *, scope: Optional[Dict[str, Any]] = None,
                 allowed_contexts: Optional[FrozenSet[str]] = None, user_id: Optional[int] = None,
                 api_key_id: Optional[int] = None, channel: Optional[str] = None, provider: Optional[str] = None):
    """MultiResult, SingleContext (the split chose one context), or None = not a multi-context question.

    Raises what QueryEngine.query raises for a refused request (ScopeError 400, ContextNotAllowed /
    LLMPolicyError 403) — a refusal of any sub-question refuses the whole question."""
    enabled = enabled_workspaces(engine.admin_config)
    if not enabled:
        return None
    start = time.time()
    found = candidates(question, engine.schema_service.get_all_contexts(), allowed_contexts, _workspaces(), enabled)
    if not found:
        return None
    try:
        split = await _split(engine, question, found, provider)
    except _REFUSALS:
        raise
    except Exception as exc:  # the split is an optimisation of routing — its failure is not the caller's failure
        # ERROR, not warning: the question now gets today's single-context answer (one half of it) — a source
        # that doesn't resolve or a provider that is down must be seen by whoever runs the service
        logger.error("multi-context split failed (%s: %s) — single-context path", type(exc).__name__, exc)
        return None
    if split is None:
        logger.warning("multi-context split unusable — single-context path")
        return None
    if len(split["parts"]) == 1:
        return SingleContext(context=split["parts"][0][0])

    names = {c["name"]: c.get("display_name") or "" for c in found}
    parts = [Part(context=c, question=q, display_name=names[c]) for c, q in split["parts"]]
    group = uuid.uuid4().hex[:16]
    results = await asyncio.gather(*(
        engine.query(p.question, provider=provider, context=p.context, scope=scope, allowed_contexts=allowed_contexts,
                     user_id=user_id, api_key_id=api_key_id, channel=channel, request_group=group)
        for p in parts), return_exceptions=True)
    refusal = next((r for r in results if isinstance(r, _REFUSALS)), None)
    # one sub-question without its audit row makes the whole answer untraceable: none of it leaves
    unaudited = next((r for r in results if isinstance(r, query_audit.AuditUnavailable)), None)
    for part, result in zip(parts, results):
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result  # cancellation
            part.error = str(result) or type(result).__name__  # as the single-context endpoint reports it
            part.error_code = outbound.code_for(result)
            logger.warning("multi-context part %s failed: %s", part.context, result)
        else:
            part.result = result
            part.error = result.query_result.error or None
            part.error_code = outbound.result_code(part.error) if part.error else None

    elapsed = (time.time() - start) * 1000
    computed = None if refusal else compute(parts, split["operation"], split["operands"])
    text_, warnings = combine(parts, computed, split["operation"])
    written = True
    if engine.db is not None:  # the parent row; the sub-questions wrote theirs under the same request_group
        written = await asyncio.to_thread(
            query_audit.record, engine.db, None, scope, user_id=user_id, api_key_id=api_key_id, channel=channel,
            question=question, context_name="+".join(p.context for p in parts), request_group=group,
            workspace=engine._workspace(parts[0].context), execution_time_ms=elapsed,
            row_count=sum(len(p.result.query_result.data or []) for p in parts if p.result is not None),
            error=(f"{type(refusal).__name__}: {refusal}"[:2000] if refusal
                   else "; ".join(f"{p.context}: {p.error}" for p in parts if p.error)[:2000] or None))
    if refusal:
        raise refusal
    if unaudited is not None:
        raise unaudited
    if not written and api_key_id is not None:
        raise query_audit.AuditUnavailable(f"query_audit (parent row) not written for api_key_id={api_key_id}")
    return MultiResult(parts=parts, answer=text_, computed=computed, warnings=warnings,
                       execution_time_ms=elapsed, request_group=group)


async def ask(engine, question: str, context: Optional[str] = None, **kwargs):
    """What an entry point calls instead of engine.query: MultiResult for a multi-context question, else the
    ordinary QueryEngineResult. kwargs: scope, allowed_contexts, user_id, api_key_id, channel, provider."""
    if not context:  # a named context is always the single-context path
        multi = await answer(engine, question, **kwargs)
        if isinstance(multi, MultiResult):
            return multi
        if multi is not None:  # the split chose one context for the whole question
            context = multi.context
    return await engine.query(question=question, context=context, **kwargs)

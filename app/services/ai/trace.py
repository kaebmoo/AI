"""Single-line JSON query trace (PLAN F7.3) — log-based observability.

One `query_trace {...}` line per request, emitted by QueryEngine (so cache
hits are traced too). No DB storage, no dashboard — a full observability
platform (Langfuse/OTel) is a deferred decision.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QueryTrace:
    request_id: str
    question_preview: str  # first 80 chars only — never the full question (PII)
    context: str = ""
    provider: str = ""
    attempts: int = 0
    stages: dict = field(default_factory=dict)   # {"rag": 0.12, "sql_gen": 2.1, ...}
    usage: list = field(default_factory=list)    # per-stage TokenUsage dicts
    cache_hit: bool = False
    error: str = ""
    total_s: float = 0.0


def new_trace(question: str) -> QueryTrace:
    """Create a trace, using the middleware request id when available."""
    try:
        from app.core.logging import request_id_var
        request_id = request_id_var.get() or str(uuid.uuid4())
    except Exception:
        request_id = str(uuid.uuid4())
    return QueryTrace(request_id=request_id, question_preview=question[:80])


def emit(trace: QueryTrace) -> None:
    """Log the trace as one parseable JSON line."""
    logger.info("query_trace %s", json.dumps(asdict(trace), ensure_ascii=False, default=str))


def record_usage(trace_or_list, stage: str, provider, attempt: int = 0) -> None:
    """Append provider.last_usage (if any) to the trace usage list."""
    usage = getattr(provider, "last_usage", None)
    if usage is None:
        return
    entry = {
        "stage": stage,
        "attempt": attempt,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read": usage.cache_read_input_tokens,
        "cache_creation": usage.cache_creation_input_tokens,
    }
    target = trace_or_list.usage if isinstance(trace_or_list, QueryTrace) else trace_or_list
    target.append(entry)

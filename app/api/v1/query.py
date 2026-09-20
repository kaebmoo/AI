"""
Simplified Query API
=====================
Stateless query endpoint for external integrations (OpenMiniCrew, API clients).
No conversation management, no chart sessions — just question → answer.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_config_db
from app.core.llm_policy import LLMPolicyError
from app.services.data_sources import ScopeError
from app.services.workspaces import ContextNotAllowed, allowed_contexts
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────

class SimpleQueryRequest(BaseModel):
    question: str = Field(..., description="Question in Thai or English", min_length=1)
    context: Optional[str] = Field(None, description="Data context name (auto-detect if omitted)")
    format: str = Field("text", description="Response format: text, json, markdown")
    include_sql: bool = Field(False, description="Include generated SQL in response")
    include_data: bool = Field(False, description="Include raw data rows in response")
    max_rows: int = Field(20, description="Max data rows to return", ge=1, le=1000)
    # F11: portal integration — both optional so the contract never breaks
    pinned_filters: Optional[Dict[str, Any]] = Field(
        None, description="Filters pinned by the caller (e.g. dashboard period). Logged only — use scope")
    # Plan 7 Phase 3 (D3=A): enforced at the SQL layer; a key the context doesn't declare = 400
    scope: Optional[Dict[str, Any]] = Field(
        None, description="Row scope enforced at the SQL layer, e.g. {\"year_month\": 202607}")
    source: Optional[str] = Field(None, description="Caller identifier for audit (e.g. 'portal')")


class SimpleQueryResponse(BaseModel):
    answer: str = Field(..., description="Thai text answer")
    context: str = Field("", description="Data context used")
    sql: Optional[str] = Field(None, description="Generated SQL (if include_sql=True)")
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Raw data rows")
    row_count: Optional[int] = Field(None, description="Total row count")
    execution_time_ms: float = Field(0, description="Total execution time in ms")
    error: Optional[str] = Field(None, description="Error message if query failed")
    # Plan 7: freshness of the file-source build the answer came from; null = legacy business DB
    data_as_of: Optional[Dict[str, Any]] = Field(
        None, description="{period, built_at, build_id} from the verified manifest (file source only)")
    # Plan 7 Phase 5: a question answered from several contexts — one entry per context, each with its own
    # sub-question, answer, freshness (and sql / data when asked for); null = a single-context answer
    parts: Optional[List[Dict[str, Any]]] = Field(None, description="Per-context parts of a multi-context answer")
    computed: Optional[Dict[str, Any]] = Field(None, description="ratio / difference computed from two parts, in code")


class ContextInfo(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""


def _find_refusal(exc: BaseException):
    """A ScopeError / ContextNotAllowed / LLMPolicyError anywhere inside (nested) exception groups, else None."""
    if isinstance(exc, (ScopeError, ContextNotAllowed, LLMPolicyError)):
        return exc
    for inner in getattr(exc, "exceptions", None) or ():
        found = _find_refusal(inner)
        if found is not None:
            return found
    return None


def _multi_response(multi, request_body: SimpleQueryRequest) -> SimpleQueryResponse:
    parts = []
    for part in multi.parts:
        qr = part.result.query_result if part.result is not None else None
        rows = (qr.data or []) if qr is not None else []
        entry = {"context": part.context, "question": part.question, "answer": _part_answer(qr),
                 "row_count": len(rows), "error": part.error,
                 "data_as_of": part.result.data_as_of if part.result is not None else None}
        if request_body.include_sql:
            entry["sql"] = qr.sql_query if qr is not None else None
        if request_body.include_data:
            entry["data"] = rows[:request_body.max_rows]
        parts.append(entry)
    return SimpleQueryResponse(
        answer=multi.answer, context=multi.context_name, row_count=sum(p["row_count"] for p in parts),
        execution_time_ms=round(multi.execution_time_ms, 1), parts=parts, computed=multi.computed,
        error="; ".join(multi.warnings) if any(p["error"] for p in parts) else None,
    )


def _part_answer(qr) -> str:
    explanation = getattr(qr, "explanation", None)
    if isinstance(explanation, dict):
        explanation = explanation.get("explanation")
    return str(explanation or "")


async def run_simple_query(request_body: SimpleQueryRequest, *, user_id, api_key_id, allowed, channel: str,
                           db, admin_config, mcp_client=None):
    """What POST /api/v1/query and the external MCP facade both run: (response, raw engine result).
    A refusal is raised as itself (ScopeError / ContextNotAllowed / LLMPolicyError), unwrapped from any
    ExceptionGroup; every other failure is the caller's to present."""
    from app.services.query_engine import QueryEngine

    async def ask(mcp):
        from app.services import multi_context  # Phase 5: off unless the workspace is enabled in admin_config
        engine = QueryEngine(mcp_client=mcp, db_session=db, admin_config=admin_config)
        return await multi_context.ask(engine, request_body.question, request_body.context,
                                       user_id=user_id, scope=request_body.scope,
                                       allowed_contexts=allowed, api_key_id=api_key_id, channel=channel)

    try:
        if mcp_client:
            result = await ask(mcp_client)
        else:
            from app.services.mcp_client import MCPClientService
            mcp_client = MCPClientService()
            async with mcp_client.connected():
                result = await ask(mcp_client)
    except Exception as e:
        # the endpoint's own MCP session (no shared client) runs in an anyio TaskGroup, which
        # wraps a refusal in an ExceptionGroup — it must still be 400 / 403, not 200 with an error text
        refusal = _find_refusal(e)
        if refusal is not None and refusal is not e:
            raise refusal from e
        raise

    if not hasattr(result, "query_result"):
        return _multi_response(result, request_body), result

    # QueryEngineResult has .query_result (QueryResult) + .context_name + .execution_time_ms
    qr = result.query_result
    data_rows = qr.data if qr.data else []
    row_count = len(data_rows)
    if request_body.max_rows and len(data_rows) > request_body.max_rows:
        data_rows = data_rows[:request_body.max_rows]

    answer = qr.explanation or qr.error or "ไม่สามารถตอบได้"
    if not isinstance(answer, str):
        answer = str(answer)

    return SimpleQueryResponse(
        answer=answer,
        context=result.context_name or request_body.context or "",
        sql=qr.sql_query if request_body.include_sql else None,
        data=data_rows if request_body.include_data else None,
        row_count=row_count,
        execution_time_ms=round(result.execution_time_ms, 1),
        error=qr.error if qr.error else None,
        data_as_of=result.data_as_of,
    ), result


def _rest_channel(source: Optional[str]) -> str:
    """The caller's `source` is the audit channel — except names the server itself writes ('mcp…')."""
    if source and source.strip().lower().startswith("mcp"):
        return f"api:{source}"
    return source or "api"


# ── Endpoints ─────────────────────────────────────────────

@router.post("/", response_model=SimpleQueryResponse)
async def simple_query(
    request_body: SimpleQueryRequest,
    http_request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    admin_config = Depends(deps.get_admin_config_service),
):
    """Execute a simple query — no conversation, no chart. Returns answer + optional SQL/data."""
    start_time = time.time()

    if request_body.source or request_body.pinned_filters or request_body.scope:
        # pinned_filters: provenance only (D3=A — superseded by scope, kept during the transition)
        logger.info(
            f"Query from source={request_body.source or '-'} scope={request_body.scope or {}} "
            f"pinned_filters={request_body.pinned_filters or {}} user={current_user.id}"
        )

    try:
        # Plan 7 Phase 4a: what this caller's API key may reach (None = session user / unrestricted key)
        api_key = getattr(http_request.state, "api_key", None)
        response, _ = await run_simple_query(
            request_body, user_id=current_user.id, api_key_id=getattr(api_key, "id", None),
            allowed=allowed_contexts(api_key), channel=_rest_channel(request_body.source),
            db=db, admin_config=admin_config,
            mcp_client=getattr(http_request.app.state, "mcp_client", None))  # same as the chat endpoint
        return response
    except ScopeError as e:  # never answered unscoped — the caller asked for a scope we can't enforce
        raise HTTPException(status_code=400, detail=str(e))
    except (ContextNotAllowed, LLMPolicyError) as e:  # outside the key's rights / the source's policy — never re-routed silently
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Simple query failed: {e}")
        return SimpleQueryResponse(
            answer=f"เกิดข้อผิดพลาด: {str(e)}",
            context=request_body.context or "",
            execution_time_ms=round(execution_time_ms, 1),
            error=str(e),
        )


def contexts_for(allowed, config_db) -> List[ContextInfo]:
    """Active contexts, in routing order — only the names in `allowed` when it is not None."""
    from sqlalchemy import text
    rows = config_db.execute(text(
        "SELECT name, display_name, description FROM schema_contexts "
        "WHERE is_active = 1 ORDER BY priority DESC, id")).fetchall()
    return [ContextInfo(name=name or "", display_name=display_name or "", description=description or "")
            for name, display_name, description in rows if allowed is None or name in allowed]


@router.get("/contexts", response_model=List[ContextInfo])
async def list_contexts(
    db: Session = Depends(get_config_db),
    x_api_key: Optional[str] = Depends(deps.api_key_header),
    app_db: Session = Depends(deps.get_db),
):
    """List available data contexts. Public — no auth required.
    Sent with a workspace-bound API key (Phase 4a) it lists only what that key can use."""
    allowed = None
    if x_api_key:
        from app.services.api_key_service import APIKeyService
        allowed = allowed_contexts(APIKeyService(app_db).validate_key(x_api_key))

    try:
        return contexts_for(allowed, db)
    except Exception as e:
        logger.error(f"Failed to list contexts: {e}")
        return []

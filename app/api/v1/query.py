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
        from app.services.query_engine import QueryEngine

        # Plan 7 Phase 4a: what this caller's API key may reach (None = session user / unrestricted key)
        api_key = getattr(http_request.state, "api_key", None)
        allowed = allowed_contexts(api_key)
        audit_as = {"api_key_id": getattr(api_key, "id", None), "channel": request_body.source or "api"}

        # Get MCP client from app state (same as chat endpoint)
        mcp_client = getattr(http_request.app.state, "mcp_client", None)
        if mcp_client:
            engine = QueryEngine(mcp_client=mcp_client, db_session=db, admin_config=admin_config)
            result = await engine.query(
                question=request_body.question,
                context=request_body.context,
                user_id=current_user.id,
                scope=request_body.scope,
                allowed_contexts=allowed,
                **audit_as,
            )
        else:
            from app.services.mcp_client import MCPClientService
            mcp_client = MCPClientService()
            async with mcp_client.connected():
                engine = QueryEngine(mcp_client=mcp_client, db_session=db, admin_config=admin_config)
                result = await engine.query(
                    question=request_body.question,
                    context=request_body.context,
                    user_id=current_user.id,
                    scope=request_body.scope,
                    allowed_contexts=allowed,
                    **audit_as,
                )

        # QueryEngineResult has .query_result (QueryResult) + .context_name + .execution_time_ms
        qr = result.query_result

        # Extract data
        data_rows = qr.data if qr.data else []
        row_count = len(data_rows)

        # Truncate data if needed
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
        )

    except ScopeError as e:  # never answered unscoped — the caller asked for a scope we can't enforce
        raise HTTPException(status_code=400, detail=str(e))
    except ContextNotAllowed as e:  # outside the key's workspace/allowlist — refused, never re-routed silently
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        # the endpoint's own MCP session (no app.state.mcp_client) runs in an anyio TaskGroup, which
        # wraps a refusal in an ExceptionGroup — it must still be 400 / 403, not 200 with an error text
        refusal = _find_refusal(e)
        if refusal is not None:
            raise HTTPException(status_code=400 if isinstance(refusal, ScopeError) else 403, detail=str(refusal))
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Simple query failed: {e}")
        return SimpleQueryResponse(
            answer=f"เกิดข้อผิดพลาด: {str(e)}",
            context=request_body.context or "",
            execution_time_ms=round(execution_time_ms, 1),
            error=str(e),
        )


@router.get("/contexts", response_model=List[ContextInfo])
async def list_contexts(
    db: Session = Depends(get_config_db),
    x_api_key: Optional[str] = Depends(deps.api_key_header),
    app_db: Session = Depends(deps.get_db),
):
    """List available data contexts. Public — no auth required.
    Sent with a workspace-bound API key (Phase 4a) it lists only what that key can use."""
    from sqlalchemy import text
    allowed = None
    if x_api_key:
        from app.services.api_key_service import APIKeyService
        allowed = allowed_contexts(APIKeyService(app_db).validate_key(x_api_key))

    try:
        # Actual columns: name, display_name, description (NOT context_name, display_name_th)
        result = db.execute(text(
            "SELECT name, display_name, description FROM schema_contexts "
            "WHERE is_active = 1 ORDER BY priority DESC, id"
        ))
        rows = result.fetchall()
        columns = list(result.keys())

        return [
            ContextInfo(
                name=dict(zip(columns, r)).get("name", ""),
                display_name=dict(zip(columns, r)).get("display_name", ""),
                description=dict(zip(columns, r)).get("description", "") or "",
            )
            for r in rows
            if allowed is None or dict(zip(columns, r)).get("name", "") in allowed
        ]
    except Exception as e:
        logger.error(f"Failed to list contexts: {e}")
        return []

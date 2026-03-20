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


class SimpleQueryResponse(BaseModel):
    answer: str = Field(..., description="Thai text answer")
    context: str = Field("", description="Data context used")
    sql: Optional[str] = Field(None, description="Generated SQL (if include_sql=True)")
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Raw data rows")
    row_count: Optional[int] = Field(None, description="Total row count")
    execution_time_ms: float = Field(0, description="Total execution time in ms")
    error: Optional[str] = Field(None, description="Error message if query failed")


class ContextInfo(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""


# ── Endpoints ─────────────────────────────────────────────

@router.post("/", response_model=SimpleQueryResponse)
async def simple_query(
    request_body: SimpleQueryRequest,
    http_request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """Execute a simple query — no conversation, no chart. Returns answer + optional SQL/data."""
    start_time = time.time()

    try:
        from app.services.query_engine import QueryEngine

        # Get MCP client from app state (same as chat endpoint)
        mcp_client = getattr(http_request.app.state, "mcp_client", None)
        if not mcp_client:
            from app.services.mcp_client import MCPClientService
            mcp_client = MCPClientService()

        engine = QueryEngine(mcp_client=mcp_client, db_session=db)

        result = await engine.query(
            question=request_body.question,
            context=request_body.context,
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
        )

    except Exception as e:
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
    db: Session = Depends(deps.get_db),
):
    """List available data contexts. Public — no auth required."""
    from sqlalchemy import text

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
        ]
    except Exception as e:
        logger.error(f"Failed to list contexts: {e}")
        return []

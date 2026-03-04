from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import uuid
import logging
from datetime import datetime

from app.api import deps

logger = logging.getLogger(__name__)
from app.models.user import User
from app.models.chat import ChatHistory
from app.schemas.chat import ChatRequest, ChatResponse, DataWarning, TrainingRequest
from app.services.ai_service import AIService
from app.services.schema_service import SchemaService
from app.services.query_engine import QueryEngine, QueryEngineResult, detect_context_from_question
from app.config import settings


router = APIRouter()

# =============================================================================
# Context & Metadata API
# =============================================================================

@router.get("/contexts", response_model=List[Dict[str, Any]])
def get_contexts(
    schema_service: SchemaService = Depends(deps.get_schema_service),
    current_user: User = Depends(deps.get_current_user)
):
    """Get all available data contexts"""
    try:
        contexts = schema_service.get_all_contexts()
        return contexts
    except Exception as e:
        logger.error(f"Error fetching contexts: {e}")
        return [
            {'name': 'revenue', 'display_name': 'รายได้', 'description': 'ข้อมูลรายได้'},
            {'name': 'expense', 'display_name': 'ค่าใช้จ่าย', 'description': 'ข้อมูลค่าใช้จ่าย'}
        ]

@router.post("/refresh")
def refresh_metadata(
    schema_service: SchemaService = Depends(deps.get_schema_service),
    current_user: User = Depends(deps.require_admin)
):
    """Force refresh of schema metadata and contexts"""
    try:
        schema_service.refresh_cache()
        schema_service.refresh_context_cache()
        return {"message": "Metadata and Contexts refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Helpers
# =============================================================================

def _get_conversation_history(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> tuple:
    """Get conversation history and previous chats from DB."""
    history = []
    previous_chats = []

    if conversation_id:
        previous_chats = db.query(ChatHistory).filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id
        ).order_by(ChatHistory.created_at.desc()).limit(5).all()

        for chat_entry in reversed(previous_chats):
            if chat_entry.question:
                history.append({"role": "user", "content": chat_entry.question})
            if chat_entry.ai_response:
                content = chat_entry.ai_response
                if chat_entry.generated_sql:
                    content += f"\n\n```sql\n{chat_entry.generated_sql}\n```"
                history.append({"role": "assistant", "content": content})

    return history, previous_chats


def _resolve_context_with_history(
    request_context: str,
    question: str,
    previous_chats: list,
    history: list,
    schema_service: SchemaService,
) -> tuple:
    """
    Resolve context with conversation history awareness.
    Returns (context_name, history) — history may be cleared on context change.
    """
    if request_context:
        context_name = request_context
        logger.info(f"Using explicit context: {context_name}")

        # If context changed from previous conversation → clear history
        if history and previous_chats:
            prev_context = getattr(previous_chats[0], 'context_name', None)
            if prev_context and prev_context != context_name:
                logger.info(f"Context changed: '{prev_context}' → '{context_name}' — clearing conversation history")
                history = []
        return context_name, history

    # Auto-detect
    previous_context = getattr(previous_chats[0], 'context_name', None) if previous_chats else None
    detected_context = detect_context_from_question(question, schema_service)

    if detected_context and detected_context != previous_context:
        context_name = detected_context
        logger.info(f"Auto-detected context: {context_name} for question: {question[:50]}...")
    elif previous_context:
        context_name = previous_context
        logger.info(f"Maintaining previous context: {context_name} for follow-up: {question[:50]}...")
    else:
        context_name = detected_context
        logger.info(f"Using detected context: {context_name} for question: {question[:50]}...")

    return context_name, history


def _save_history(
    db: Session,
    user_id: int,
    conversation_id: str,
    engine_result: QueryEngineResult,
) -> ChatHistory:
    """Save query result to chat history."""
    result = engine_result.query_result

    # Extract clean text from explanation (handle both str and dict)
    if isinstance(result.explanation, dict):
        ai_response_text = result.explanation.get("explanation", str(result.explanation))
    else:
        ai_response_text = result.explanation if result.explanation else ""

    chat_entry = ChatHistory(
        user_id=user_id,
        conversation_id=conversation_id,
        question=result.question,
        generated_sql=result.sql_query,
        sql_result_summary=str(result.data)[:1000] if result.data else None,
        ai_response=ai_response_text if not result.error else f"Error: {result.error}",
        execution_time_ms=engine_result.execution_time_ms,
        tokens_used=result.tokens_used,
        context_name=engine_result.context_name
    )
    db.add(chat_entry)
    db.commit()
    db.refresh(chat_entry)

    return chat_entry


def _format_response(
    chat_entry: ChatHistory,
    conversation_id: str,
    engine_result: QueryEngineResult,
) -> dict:
    """Format QueryEngineResult into API response dict."""
    result = engine_result.query_result

    # Retry history
    retry_history_response = None
    if result.retry_history:
        retry_history_response = [
            {
                "attempt": r.get("attempt", 0),
                "error_type": r.get("error_type", "unknown"),
                "error": r.get("error", ""),
                "sql": r.get("sql")
            }
            for r in result.retry_history
        ]

    # Warnings
    warnings_response = None
    if engine_result.warnings:
        warnings_response = [
            {"code": w.code, "message": w.message, "severity": w.severity}
            for w in engine_result.warnings
        ]

    # Confidence
    confidence_response = None
    if result.confidence:
        confidence_response = {
            "score": result.confidence.score,
            "level": result.confidence.level,
            "level_th": result.confidence.level_th,
            "color": result.confidence.color,
            "factors": result.confidence.factors,
            "recommendation": result.confidence.recommendation
        }

    # Visualization
    visualization_response = None
    chart_config_response = None
    if isinstance(result.explanation, dict):
        visualization_response = result.explanation.get("visualization")
        chart_config_response = result.explanation.get("chart_config")
        logger.info(f"AI Response - visualization: {visualization_response}, chart_config: {chart_config_response}")

    return {
        "id": chat_entry.id,
        "conversation_id": conversation_id,
        "question": result.question,
        "answer": chat_entry.ai_response,
        "sql_query": result.sql_query,
        "data": result.data,
        "execution_time_ms": engine_result.execution_time_ms,
        "retry_count": result.retry_count,
        "retry_history": retry_history_response,
        "warnings": warnings_response,
        "confidence": confidence_response,
        "visualization": visualization_response,
        "chart_config": chart_config_response
    }


# =============================================================================
# Main Chat Endpoint — delegates to QueryEngine
# =============================================================================

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """
    Process a natural language question about revenue/sales.
    1. Verify user permission
    2. Convert Question -> SQL & Explain (QueryEngine)
    3. Save History
    """
    # 1. Conversation ID
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # 2. Get history
    history, previous_chats = _get_conversation_history(db, conversation_id, current_user.id)

    # 3. Resolve context (with history-aware logic)
    db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    schema_service = SchemaService(db_path=db_path)
    context_name, history = _resolve_context_with_history(
        request.context, request.question, previous_chats, history, schema_service
    )

    # 4. Execute query via QueryEngine
    mcp_client = deps.get_mcp_client(current_request)
    engine = QueryEngine(mcp_client=mcp_client, db_session=db)
    engine_result = await engine.query(
        question=request.question,
        provider=request.provider,
        context=context_name,
        mode=request.mode or "hybrid",
        history=history,
        max_retries=request.max_retries,
    )

    # 5. Save history
    chat_entry = _save_history(db, current_user.id, conversation_id, engine_result)

    # 6. Format response
    return _format_response(chat_entry, conversation_id, engine_result)


# =============================================================================
# History Endpoint
# =============================================================================

@router.get("/history", response_model=List[ChatResponse])
def get_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get chat history for the current user."""
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    ).order_by(ChatHistory.created_at.desc()).offset(skip).limit(limit).all()

    results = []
    for c in chats:
        results.append({
            "id": c.id,
            "question": c.question,
            "answer": c.ai_response,
            "sql_query": c.generated_sql,
            "data": None,
            "execution_time_ms": c.execution_time_ms or 0
        })
    return results


# =============================================================================
# Training Endpoint
# =============================================================================

from app.models.feedback_models import GoldenExample

@router.post("/train")
async def train_model(
    request: TrainingRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    default_ai_service: AIService = Depends(deps.get_ai_service),
    db: Session = Depends(deps.get_db)
):
    """
    Train RAG with Correct SQL
    - Admins: Validates & Trains immediately (Active).
    - Users: Submits for review (Inactive).
    """
    try:
        mcp_client = deps.get_mcp_client(current_request)
        try:
            check_res = await mcp_client.call_tool("execute_query", {"sql": request.sql, "limit": 1})
            if isinstance(check_res, dict) and check_res.get('error'):
                raise ValueError(f"Invalid SQL: {check_res['error']}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid SQL: {str(e)}")

        is_admin = getattr(current_user, 'is_superuser', False) or getattr(current_user, 'role', '') == 'admin'

        existing = db.query(GoldenExample).filter(GoldenExample.question_pattern == request.question).first()

        if existing:
            existing.expected_sql = request.sql
            existing.is_active = is_admin
            existing.updated_at = datetime.utcnow()
            if is_admin:
                existing.added_by = current_user.id
            db_item = existing
        else:
            db_item = GoldenExample(
                question_pattern=request.question,
                expected_sql=request.sql,
                category=request.context,
                is_active=is_admin,
                added_by=current_user.id
            )
            db.add(db_item)

        db.commit()
        db.refresh(db_item)

        if is_admin:
            success = default_ai_service.train(request.question, request.sql)
            if success:
                return {"success": True, "message": "Admin: System trained and saved successfully"}
            else:
                return {"success": True, "message": "Saved to DB, but Vector training failed (check logs)"}
        else:
            return {"success": True, "message": "Suggestion submitted for review. Thank you!"}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

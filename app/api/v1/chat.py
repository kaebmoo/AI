from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import asyncio
import uuid
import json
import logging
from datetime import datetime

from app.api import deps

logger = logging.getLogger(__name__)
from app.models.user import User
from app.models.chat import ChatHistory
from app.models.conversation import Conversation
from app.schemas.chat import ChatRequest, ChatResponse, DataWarning, TrainingRequest
from app.services.ai_service import AIService
from app.services.data_sources import SourceBoundMCPClient, source_resolver
from app.services.schema_service import SchemaService
from app.services.query_engine import (QueryEngine, QueryEngineResult, context_keyword_hits,
                                       detect_context_from_question)
from app.services.ai.thai_year import period_th
from app.services.retention import EXPIRED_ANSWER, stores_results
from app.services.intent_classifier import classify_intent
from app.providers.chart_postprocessor import enrich_chart_config, resolve_max_series_warning
from app.models.chat_session import ChatSessionData
from app.models.feedback_models import ChartFeedbackEvent
from app.services.chart import decide_chart_structure
from app.services.chart.profiler import DEFAULT_MAX_SERIES
from app.config import settings
from app.core.time_utils import utcnow


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

def _resolve_conversation(
    db: Session,
    conversation_id: str | None,
    user_id: int,
) -> str:
    """
    Resolve or create a Conversation record.
    - If conversation_id is provided: verify ownership, return it.
    - If not: create a new Conversation, return its id.
    """
    if conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conv:
            if conv.user_id != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to access this conversation")
            return conversation_id
        # conversation_id given but not in DB (legacy or external)
        # Create a new record with that id
        conv = Conversation(id=conversation_id, user_id=user_id)
        db.add(conv)
        try:
            db.commit()
        except Exception:
            db.rollback()
        return conversation_id

    # No conversation_id → create new
    conv = Conversation(user_id=user_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv.id


def _update_conversation_meta(
    db: Session,
    conversation_id: str,
    question: str,
):
    """Update conversation title (if first message) and metadata."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    if not conv:
        return

    # Auto-generate title from first question
    if conv.title is None and question:
        title = question[:60]
        if len(question) > 60:
            title += "..."
        conv.title = title

    conv.message_count = (conv.message_count or 0) + 1
    conv.updated_at = utcnow()
    db.commit()


def _get_conversation_history(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> tuple:
    """
    Get conversation history as native multi-turn messages.

    Each assistant turn is a concise summary (SQL + brief result) so the LLM
    sees real conversation turns instead of a flattened text blob.
    Window size is configurable via MAX_HISTORY_MESSAGES.
    """
    history = []
    previous_chats = []

    if conversation_id:
        limit = settings.MAX_HISTORY_MESSAGES
        previous_chats = db.query(ChatHistory).filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id
        ).order_by(ChatHistory.created_at.desc()).limit(limit).all()

        for chat_entry in reversed(previous_chats):
            if chat_entry.question:
                history.append({"role": "user", "content": chat_entry.question})
            # Build concise assistant message: SQL + brief result summary
            if chat_entry.generated_sql or chat_entry.ai_response:
                parts = []
                if chat_entry.generated_sql:
                    parts.append(f"```sql\n{chat_entry.generated_sql}\n```")
                # an expired answer is a tombstone, not something "I said before": drop it from the
                # history rather than let a model read it as the previous turn's content
                if chat_entry.ai_response and chat_entry.ai_response != EXPIRED_ANSWER:
                    # Keep explanation concise — first 300 chars
                    explanation = chat_entry.ai_response[:300]
                    if len(chat_entry.ai_response) > 300:
                        explanation += "…"
                    parts.append(explanation)
                if parts:  # an expired answer with no SQL leaves nothing to say — skip the turn
                    history.append({"role": "assistant", "content": "\n\n".join(parts)})

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


# =============================================================================
# Which data source answered — and where else the question could be answered from
# =============================================================================

def _same_context(a: Optional[str], b: Optional[str]) -> bool:
    # stored names are spelled with a space or an underscore ('transfer price' / 'transfer_price')
    return bool(a and b) and a.replace("_", " ").lower() == b.replace("_", " ").lower()


def _others(hits: Dict[str, Dict[str, Any]], context_name: Optional[str]) -> List[Dict[str, Any]]:
    """The contexts other than context_name whose keywords the question names — the router's order, best first."""
    ranked = sorted(hits.items(), key=lambda kv: len(kv[1]["keywords"]) + kv[1]["priority"] * 0.1, reverse=True)
    return [{"context": name, "display_name": hit.get("display_name") or name,
             "description": hit.get("description"), "keywords": hit["keywords"]}
            for name, hit in ranked if not _same_context(name, context_name)]


def _answer_source(engine_result: QueryEngineResult, question: str, schema_service: SchemaService) -> Optional[dict]:
    """What the chat shows above an answer: the context it was read from, how far that data runs, and up to three
    other contexts the question's keywords also match (one tap re-asks there). Without it a user who picked — or
    was routed to — the wrong context could not tell: "ข้อมูล EBT เป็นอย่างไรบ้าง" on the revenue feed came back as
    revenue named "EBT", and on pl_costtype as an empty month (2026-10-22). Never fails the answer."""
    name = engine_result.context_name
    if not name:
        return None
    try:
        info = schema_service.get_context_info(name) or {}
        return {
            "context": name,
            "display_name": info.get("display_name") or name,
            "description": info.get("description"),
            "data_period": engine_result.data_period,
            "data_period_th": period_th(engine_result.data_period),
            "alternatives": _others(context_keyword_hits(question, schema_service), name)[:3],
        }
    except Exception as e:
        logger.warning(f"Failed to describe the answer's source (non-fatal): {e}")
        return None


def _context_mismatch(request_context: Optional[str], question: str, schema_service: SchemaService) -> Optional[dict]:
    """The user picked a context none of whose keywords the question names, while other contexts' keywords are
    there — e.g. "EBT" asked with the revenue feed selected. Returns the warning for the answer and a note for the
    prompt (say the data is not here rather than rename another column as the thing asked); None otherwise,
    including auto mode, where the router already went where the keywords point.

    ponytail: keyword evidence only, as good as the contexts' keyword lists — a generic keyword ("ค่า" inside
    "มูลค่า") can warn needlessly. It warns and answers rather than blocking for that reason; admins tune the
    lists in Admin → Contexts."""
    if not request_context:
        return None
    hits = context_keyword_hits(question, schema_service)
    if any(_same_context(name, request_context) for name in hits):
        return None
    others = _others(hits, request_context)
    if not others:
        return None
    keywords = list(dict.fromkeys(kw for other in others for kw in other["keywords"]))
    quoted = ", ".join(f"“{kw}”" for kw in keywords)
    names = ", ".join(other["display_name"] for other in others)
    try:
        selected = (schema_service.get_context_info(request_context) or {}).get("display_name") or request_context
    except Exception:
        selected = request_context
    return {
        "warning": {
            "code": "context_mismatch",
            "severity": "important",
            "message": (f"คำถามมีคำว่า {quoted} ซึ่งไม่อยู่ในแหล่งข้อมูลที่เลือก ({selected}) แต่ตรงกับ {names} — "
                        f"คำตอบนี้อาจไม่ใช่สิ่งที่ถาม ลองถามจากแหล่งที่แนะนำด้านล่าง"),
        },
        "prompt_note": (f"**แหล่งข้อมูลอาจไม่ตรงกับคำถาม:** คำถามมีคำว่า {quoted} ซึ่งเป็นคำของแหล่งข้อมูลอื่น ({names}) "
                        f"ไม่ใช่ของแหล่งที่ผู้ใช้เลือก ({selected}). ถ้าตารางของแหล่งนี้ไม่มีข้อมูลหรือตัวชี้วัดที่ถามจริง "
                        f"ให้ตอบตรง ๆ ว่าแหล่งข้อมูลนี้ไม่มีข้อมูลนั้น และแนะนำให้ถามจาก {names} — "
                        f"ห้ามนำคอลัมน์อื่นมาตั้งชื่อหรืออธิบายว่าเป็นสิ่งที่ถาม (เช่น ห้ามเรียกรายได้ว่า EBT)"),
    }


def _add_source(response_data: dict, engine_result: QueryEngineResult, question: str,
                schema_service: SchemaService, mismatch: Optional[dict]) -> dict:
    """Attach the source block (and the mismatch warning, first) — before _persist_render_payload, so a
    reloaded conversation shows them too."""
    response_data["source"] = _answer_source(engine_result, question, schema_service)
    if mismatch:
        response_data["warnings"] = [mismatch["warning"]] + list(response_data.get("warnings") or [])
    return response_data


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
        sql_result_summary=(str(result.data)[:1000]
                            if result.data and stores_results(engine_result.context_name) else None),
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
    admin_config=None,
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

    # Visualization + display hints
    visualization_response = None
    chart_config_response = None
    display_hint_response = None
    hierarchy_columns_response = None
    if isinstance(result.explanation, dict):
        visualization_response = result.explanation.get("visualization")
        chart_config_response = result.explanation.get("chart_config")
        display_hint_response = result.explanation.get("display_hint")
        hierarchy_columns_response = result.explanation.get("hierarchy_columns")
        logger.info(f"AI Response - visualization: {visualization_response}, display_hint: {display_hint_response}, hierarchy_columns: {hierarchy_columns_response}")

        # Wave 4: enrich_chart_config (called deep inside the provider, no DB
        # access) only ever sees DEFAULT_MAX_SERIES — override with the real
        # 3-tier-resolved value now that we have admin_config in scope.
        if admin_config is not None and isinstance(chart_config_response, dict):
            resolved_max_series = admin_config.get_chart_max_series()
            chart_config_response["max_series"] = resolved_max_series
            chart_spec = chart_config_response.get("chart_spec")
            if isinstance(chart_spec, dict) and isinstance(chart_spec.get("series"), dict):
                chart_spec["series"]["top_n"] = max(1, resolved_max_series - 1)
            cat_col = chart_config_response.get("category_column") or ""
            ser_col = chart_config_response.get("series_column") or ""
            viz = visualization_response or ""
            if not (viz in ("pie_chart", "donut_chart") and ser_col):
                # pie+series keeps its "not supported" warning untouched — anything
                # else recomputes against the real threshold
                max_series_warning = resolve_max_series_warning(
                    result.data or [], cat_col, ser_col, viz, resolved_max_series
                )
                if max_series_warning:
                    chart_config_response["warning"] = max_series_warning
                elif str(chart_config_response.get("warning", "")).startswith("แสดง Top-"):
                    del chart_config_response["warning"]

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
        "chart_config": chart_config_response,
        "display_hint": display_hint_response,
        "hierarchy_columns": hierarchy_columns_response,
        "is_chart_only": False,
    }


def _persist_render_payload(db: Session, chat_entry: ChatHistory, response_data: dict) -> None:
    """
    F12: เก็บ payload ที่ client เห็นจริงลง chat_history (เรียกหลัง _format_response เสมอ
    เพราะ _format_response mutate chart_config — max_series override + warning recompute)
    Non-fatal: ล้มเหลวแค่ log warning ห้ามทำให้ response พัง
    """
    try:
        data = response_data.get("data") or []
        max_rows = settings.HISTORY_RENDER_MAX_ROWS
        truncated = len(data) > max_rows

        meta = {
            "visualization": response_data.get("visualization"),
            "chart_config": response_data.get("chart_config"),
            "display_hint": response_data.get("display_hint"),
            "hierarchy_columns": response_data.get("hierarchy_columns"),
            "warnings": response_data.get("warnings"),
            "confidence": response_data.get("confidence"),
            "source": response_data.get("source"),
            "data_truncated": truncated,
            "total_rows": len(data),
        }
        chat_entry.render_meta = json.dumps(meta, ensure_ascii=False, default=str)
        chat_entry.result_data = (
            json.dumps(data[:max_rows], ensure_ascii=False, default=str)
            if data and stores_results(chat_entry.context_name) else None
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to persist render payload (non-fatal): {e}")


def _save_session_data(db: Session, conversation_id: str, data: list, columns: list, chart_config: dict = None):
    """Upsert last query data for chart-only re-render."""
    existing = db.query(ChatSessionData).filter(
        ChatSessionData.conversation_id == conversation_id
    ).first()

    cfg_json = json.dumps(chart_config, ensure_ascii=False, default=str) if chart_config else None
    data_json = json.dumps(data, ensure_ascii=False, default=str)
    cols_json = json.dumps(columns)

    if existing:
        existing.last_data = data_json
        existing.last_columns = cols_json
        existing.last_chart_config = cfg_json
        existing.row_count = len(data)
        existing.updated_at = utcnow()
    else:
        db.add(ChatSessionData(
            conversation_id=conversation_id,
            last_data=data_json,
            last_columns=cols_json,
            last_chart_config=cfg_json,
            row_count=len(data),
        ))
    db.commit()


def _get_session_data(db: Session, conversation_id: str) -> dict:
    """Get last query data for chart-only re-render. Returns dict or None."""
    row = db.query(ChatSessionData).filter(
        ChatSessionData.conversation_id == conversation_id
    ).first()
    if not row:
        return None
    return {
        "data": json.loads(row.last_data),
        "columns": json.loads(row.last_columns),
        "chart_config": json.loads(row.last_chart_config) if row.last_chart_config else None,
    }


def _log_chart_feedback_event(
    db: Session,
    conversation_id: str,
    user_id: int | None,
    question: str,
    intent: dict,
    prev_config: dict,
    enriched: dict,
    data: list,
) -> None:
    """Persist chart-switch decision facts for later feedback analysis."""
    try:
        chart_config = enriched.get("chart_config") or {}
        max_series = chart_config.get("max_series")
        decision = decide_chart_structure(
            data=data,
            category_column=prev_config.get("category_column") or chart_config.get("category_column"),
            series_column=prev_config.get("series_column") or chart_config.get("series_column"),
            measure_column=prev_config.get("measure_column") or chart_config.get("measure_column"),
            visualization=prev_config.get("visualization") or enriched.get("visualization"),
            max_series=int(max_series) if max_series else DEFAULT_MAX_SERIES,
            requested_type=intent.get("requested_type"),
            title=prev_config.get("title", ""),
        )
        profile = decision.profile
        profile_payload = {
            "row_count": len(data),
            "columns": profile.columns,
            "column_roles": profile.column_roles,
            "cardinality": profile.cardinality,
            "temporal_columns": profile.temporal_columns,
            "categorical_columns": profile.categorical_columns,
            "quantitative_columns": profile.quantitative_columns,
            "negative_columns": profile.negative_columns,
            "measure_column": profile.measure_column,
            "matrix_shape": profile.matrix_shape,
        }
        decision_payload = {
            "category_column": decision.category_column,
            "series_column": decision.series_column,
            "measure_column": decision.measure_column,
            "visualization": decision.visualization,
            "available_types": decision.available_types,
            "warning": decision.warning,
            "warnings": decision.warnings,
            "chart_spec": decision.chart_spec,
        }
        db.add(ChartFeedbackEvent(
            conversation_id=conversation_id,
            user_id=user_id,
            question=question,
            requested_type=intent.get("requested_type"),
            resolved_type=decision.visualization,
            requested_type_accepted=decision.requested_type_accepted,
            requested_type_vetoed=decision.requested_type_vetoed,
            profile_json=json.dumps(profile_payload, ensure_ascii=False, default=str),
            decision_json=json.dumps(decision_payload, ensure_ascii=False, default=str),
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to log chart feedback event (non-fatal): {e}")


def _persist_chart_only_switch(db: Session, conversation_id: str, enriched: dict) -> None:
    """
    F12 Phase C: chart-only switches (_handle_chart_only) don't create a new
    ChatHistory row, so a plain reload would show the chart type from before
    the switch. Update visualization/chart_config on the latest row's
    render_meta so the switch survives a reload.
    Non-fatal: ล้มเหลวแค่ log warning ห้ามทำให้ response พัง
    """
    try:
        # A later text-only/error turn (render_meta set, result_data NULL) must
        # not shadow the earlier turn that actually holds the chart being
        # switched — require result_data too, not just render_meta.
        chat_entry = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.conversation_id == conversation_id,
                ChatHistory.render_meta.isnot(None),
                ChatHistory.result_data.isnot(None),
            )
            .order_by(ChatHistory.created_at.desc())
            .first()
        )
        if not chat_entry:
            return
        meta = json.loads(chat_entry.render_meta)
        meta["visualization"] = enriched.get("visualization")
        meta["chart_config"] = enriched.get("chart_config")
        chat_entry.render_meta = json.dumps(meta, ensure_ascii=False, default=str)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to persist chart-only switch (non-fatal): {e}")


def _handle_chart_only(
    db: Session,
    conversation_id: str,
    question: str,
    intent: dict,
    admin_config=None,
    user_id: int | None = None,
) -> dict:
    """Handle chart-only intent — return enriched chart config with existing session data."""
    session = _get_session_data(db, conversation_id)

    if not session or not session.get("data"):
        return {
            "id": None,
            "conversation_id": conversation_id,
            "question": question,
            "answer": "ยังไม่มีข้อมูลจากการสนทนานี้ครับ กรุณาถามข้อมูลก่อน แล้วค่อยขอเปลี่ยนรูปแบบกราฟได้เลย",
            "sql_query": None,
            "data": None,
            "execution_time_ms": 0.0,
            "is_chart_only": True,
        }

    prev_config = session.get("chart_config") or {}
    mock_result = {
        # Keep the previous/provider visualization as a hint. The user's
        # toolbar choice is passed separately so the shared engine can
        # validate it against the full result shape and explain any veto.
        "visualization": prev_config.get("visualization"),
        "chart_config": {
            "category_column": prev_config.get("category_column"),
            "measure_column": prev_config.get("measure_column"),
            "series_column": prev_config.get("series_column"),
        }
    }
    enriched = enrich_chart_config(
        parsed_result=mock_result,
        data=session["data"],
        chart_title=prev_config.get("title", ""),
        max_series=admin_config.get_chart_max_series() if admin_config is not None else None,
        requested_type=intent.get("requested_type"),
    )
    _log_chart_feedback_event(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        question=question,
        intent=intent,
        prev_config=prev_config,
        enriched=enriched,
        data=session["data"],
    )
    _persist_chart_only_switch(db, conversation_id, enriched)

    return {
        "id": None,
        "conversation_id": conversation_id,
        "question": question,
        "answer": "",
        "sql_query": None,
        "data": session["data"],
        "execution_time_ms": 0.0,
        "visualization": enriched.get("visualization"),
        "chart_config": enriched.get("chart_config"),
        "is_chart_only": True,
    }


# =============================================================================
# Main Chat Endpoint — delegates to QueryEngine
# =============================================================================

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    schema_service: SchemaService = Depends(deps.get_schema_service),
    db: Session = Depends(deps.get_db),
    admin_config = Depends(deps.get_admin_config_service),
):
    """
    Process a natural language question about revenue/sales.
    1. Verify user permission
    2. Convert Question -> SQL & Explain (QueryEngine)
    3. Save History
    """
    # 1. Resolve or create Conversation
    conversation_id = _resolve_conversation(db, request.conversation_id, current_user.id)

    # 2. Chart-only intent detection
    intent = classify_intent(request.question)
    if intent["is_chart_request"] and intent["confidence"] == "high":
        return _handle_chart_only(
            db, conversation_id, request.question, intent, admin_config, current_user.id
        )

    # 3. Get history
    history, previous_chats = _get_conversation_history(db, conversation_id, current_user.id)

    # 4. Resolve context (with history-aware logic)
    context_name, history = _resolve_context_with_history(
        request.context, request.question, previous_chats, history, schema_service
    )

    # 5. Execute query via QueryEngine
    mismatch = _context_mismatch(request.context, request.question, schema_service)
    mcp_client = deps.get_mcp_client(current_request)
    engine = QueryEngine(mcp_client=mcp_client, db_session=db, admin_config=admin_config)
    engine_result = await engine.query(
        question=request.question,
        provider=request.provider,
        context=context_name,
        mode=request.mode or "hybrid",
        history=history,
        max_retries=request.max_retries,
        conversation_id=conversation_id,
        user_id=current_user.id,
        channel="chat",
        prompt_note=mismatch["prompt_note"] if mismatch else None,
    )

    # 6. Save session data for chart-only re-render (non-fatal)
    result = engine_result.query_result
    if result.data and not result.error and stores_results(engine_result.context_name):
        try:
            columns = list(result.data[0].keys()) if result.data else []
            existing_cfg = result.explanation.get("chart_config") if isinstance(result.explanation, dict) else {}
            _save_session_data(db, conversation_id, result.data, columns, existing_cfg)
        except Exception as e:
            logger.warning(f"Failed to save session data (non-fatal): {e}")

    # 7. Save history
    chat_entry = _save_history(db, current_user.id, conversation_id, engine_result)

    # 8. Update conversation metadata (title, message_count, updated_at)
    _update_conversation_meta(db, conversation_id, request.question)

    # 9. Format response
    response_data = _format_response(chat_entry, conversation_id, engine_result, admin_config)
    _add_source(response_data, engine_result, request.question, schema_service, mismatch)
    _persist_render_payload(db, chat_entry, response_data)
    return response_data


# =============================================================================
# SSE Streaming Endpoint
# =============================================================================

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    schema_service: SchemaService = Depends(deps.get_schema_service),
    db: Session = Depends(deps.get_db),
    admin_config = Depends(deps.get_admin_config_service),
):
    """
    Stream chat responses via Server-Sent Events (SSE).
    Events: status, data_ready, answer, done, error
    """
    conversation_id = _resolve_conversation(db, request.conversation_id, current_user.id)

    # Chart-only intent detection (same as /chat endpoint)
    intent = classify_intent(request.question)

    history, previous_chats = _get_conversation_history(db, conversation_id, current_user.id)

    context_name, history = _resolve_context_with_history(
        request.context, request.question, previous_chats, history, schema_service
    )

    # Queue for pushing SSE events from on_status callback
    event_queue: asyncio.Queue = asyncio.Queue()

    def on_status(status):
        """Push status updates to SSE queue."""
        try:
            event_queue.put_nowait({
                "event": "status",
                "data": {
                    "status": status.status,
                    "message": status.message,
                    "attempt": status.attempt,
                    "max_attempts": status.max_attempts,
                }
            })
        except Exception:
            pass

    async def generate_events():
        """SSE event generator."""
        query_task = None
        try:
            # Chart-only: skip QueryEngine, return session data directly
            if intent["is_chart_request"] and intent["confidence"] == "high":
                chart_response = _handle_chart_only(
                    db, conversation_id, request.question, intent, admin_config, current_user.id
                )
                yield _sse_format("answer", chart_response)
                yield _sse_format("done", {"id": None, "conversation_id": conversation_id})
                return

            # Send initial event
            yield _sse_format("status", {"status": "started", "message": "Processing query..."})

            # Run query in background task
            mismatch = _context_mismatch(request.context, request.question, schema_service)
            mcp_client = deps.get_mcp_client(current_request)
            engine = QueryEngine(mcp_client=mcp_client, db_session=db, admin_config=admin_config)

            # Start query as a task
            query_task = asyncio.create_task(engine.query(
                question=request.question,
                provider=request.provider,
                context=context_name,
                mode=request.mode or "hybrid",
                history=history,
                max_retries=request.max_retries,
                conversation_id=conversation_id,
                on_status=on_status,
                user_id=current_user.id,
                channel="chat",
                prompt_note=mismatch["prompt_note"] if mismatch else None,
            ))

            # Stream status events while query runs
            while not query_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    yield _sse_format(event["event"], event["data"])
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"

            # Drain events pushed just before the task finished
            while not event_queue.empty():
                event = event_queue.get_nowait()
                yield _sse_format(event["event"], event["data"])

            # Get result
            engine_result = query_task.result()

            # Send data event (if SQL executed successfully with data)
            result = engine_result.query_result
            if result.data and not result.error:
                yield _sse_format("data_ready", {
                    "sql_query": result.sql_query,
                    "data": result.data,
                    "row_count": len(result.data),
                })

            # Save history
            chat_entry = _save_history(db, current_user.id, conversation_id, engine_result)

            # Update conversation metadata (title, message_count, updated_at)
            _update_conversation_meta(db, conversation_id, request.question)

            # Save session data for chart-only re-render (non-fatal)
            if result.data and not result.error and stores_results(engine_result.context_name):
                try:
                    columns = list(result.data[0].keys()) if result.data else []
                    existing_cfg = result.explanation.get("chart_config") if isinstance(result.explanation, dict) else {}
                    _save_session_data(db, conversation_id, result.data, columns, existing_cfg)
                except Exception as e:
                    logger.warning(f"Failed to save session data (non-fatal): {e}")

            # Send full response
            response_data = _format_response(chat_entry, conversation_id, engine_result, admin_config)
            _add_source(response_data, engine_result, request.question, schema_service, mismatch)
            _persist_render_payload(db, chat_entry, response_data)
            yield _sse_format("answer", response_data)

            # Done
            yield _sse_format("done", {"id": chat_entry.id, "conversation_id": conversation_id})

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield _sse_format("error", {"message": str(e)})
        finally:
            # Client disconnect closes this generator (GeneratorExit/cancel) —
            # stop the in-flight LLM query instead of burning tokens
            if query_task is not None and not query_task.done():
                query_task.cancel()
                logger.info("SSE client disconnected — query task cancelled")

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


def _sse_format(event: str, data: dict) -> str:
    """Format data as SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


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

from app.services.feedback_service import save_training  # the one path a correction is saved by (chat + feedback)

@router.post("/train")
async def train_model(
    request: TrainingRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    default_ai_service: AIService = Depends(deps.get_ai_service),
    db: Session = Depends(deps.get_config_db),  # golden_examples live in config.db (was get_db: failed since the 3-DB split)
):
    """
    Train RAG with Correct SQL
    - Admins: Validates & Trains immediately (Active) — the example is theirs (manual).
    - Users: Submits for review — a `learned` / `proposed` example (Plan 8.1), kept out of prompt and RAG until a
      person takes it; a user never changes an example someone else decided (it used to switch an admin's off).
    """
    try:
        mcp_client = deps.get_mcp_client(current_request)
        # REMAIN-9.2: run the SQL on the context's own source (a file source in-process), and read
        # the payload — call_tool returns it as JSON text, so a dict check never saw a failure
        source = source_resolver.for_context(request.context)
        client = SourceBoundMCPClient(mcp_client, source) if source.adapter is not None else mcp_client
        try:
            raw = await client.call_tool("execute_query", {"sql": request.sql, "limit": 1})
            check_res = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid SQL: {str(e)}")
        if not isinstance(check_res, dict) or not check_res.get("success"):
            error = check_res.get("error") or check_res.get("issues") if isinstance(check_res, dict) else check_res
            raise HTTPException(status_code=400, detail=f"Invalid SQL: {error}")

        is_admin = getattr(current_user, 'is_superuser', False) or getattr(current_user, 'role', '') == 'admin'

        save_training(db, request.question, request.sql, request.context, current_user.id, is_admin)

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

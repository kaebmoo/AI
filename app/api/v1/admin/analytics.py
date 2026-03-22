"""Operational and analytics admin endpoints."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.config import settings
from app.db.session import business_engine, config_engine
from app.models.schema_models import SchemaBusinessRule, SchemaMetadata, SchemaSemanticMapping
from app.models.user import User
from app.schemas.admin_schemas import DashboardStatsResponse
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService
from app.services.vanna_service import VannaService

router = APIRouter()


@router.post("/refresh-cache", response_model=dict)
def refresh_schema_cache(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Refresh schema cache after metadata updates. Admin only."""
    schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
    schema_service.refresh_cache()
    clear_query_cache()
    return {
        "status": "success",
        "message": "Schema cache refreshed and query cache cleared. Changes take effect immediately.",
    }


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    current_user: User = Depends(deps.require_admin),
    config_db: Session = Depends(deps.get_config_db),
    app_db: Session = Depends(deps.get_db),
):
    """Get dashboard statistics."""
    return DashboardStatsResponse(
        total_users=app_db.query(User).count(),
        total_mappings=config_db.query(SchemaSemanticMapping).count(),
        total_rules=config_db.query(SchemaBusinessRule).count(),
        total_columns=config_db.query(SchemaMetadata).count(),
    )


@router.post("/sync-brain", response_model=dict)
def sync_brain_knowledge(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Trigger Vanna brain sync. Admin only."""
    try:
        vanna = VannaService(config={
            "path": settings.VANNA_CHROMA_PATH,
            "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD,
        })
        vanna.sync_brain(service)
        return {"status": "success", "message": "Brain sync completed successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/clear-query-cache", response_model=dict)
def clear_query_cache_endpoint(
    current_user: User = Depends(deps.require_admin),
):
    """Clear the in-memory query result cache."""
    cleared = clear_query_cache()
    return {"status": "success", "entries_cleared": cleared}


@router.get("/query-logs")
def get_query_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    context: Optional[str] = None,
    user_id: Optional[int] = None,
    feedback_only: bool = Query(False, description="Only show queries with feedback"),
    thumbs_down_only: bool = Query(False, description="Only show thumbs-down queries"),
    has_error: bool = Query(False, description="Only show queries with errors"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get paginated query logs with optional feedback join. Admin only."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import FeedbackRating, UserFeedback
    from app.models.user import User as UserModel

    query = db.query(ChatHistory, UserFeedback).outerjoin(UserFeedback, ChatHistory.id == UserFeedback.chat_id).order_by(ChatHistory.created_at.desc())

    if date_from:
        try:
            query = query.filter(ChatHistory.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(ChatHistory.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    if context:
        query = query.filter(ChatHistory.context_name == context)
    if user_id:
        query = query.filter(ChatHistory.user_id == user_id)
    if feedback_only:
        query = query.filter(UserFeedback.id != None)
    if thumbs_down_only:
        query = query.filter(UserFeedback.rating == FeedbackRating.THUMBS_DOWN)
    if has_error:
        query = query.filter((ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == ""))

    total = query.count()
    rows = query.offset(skip).limit(limit).all()

    user_ids = list({row[0].user_id for row in rows if row[0].user_id})
    user_map = {}
    if user_ids:
        users = db.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
        user_map = {user.id: user.email for user in users}

    items = []
    for chat, feedback in rows:
        item = {
            "id": chat.id,
            "user_id": chat.user_id,
            "user_email": user_map.get(chat.user_id, "unknown"),
            "question": chat.question,
            "generated_sql": chat.generated_sql,
            "sql_result_summary": (chat.sql_result_summary or "")[:500],
            "ai_response": (chat.ai_response or "")[:300],
            "tokens_used": chat.tokens_used,
            "execution_time_ms": chat.execution_time_ms,
            "context_name": chat.context_name,
            "feedback_rating": chat.feedback_rating,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        }
        item["feedback"] = {
            "id": feedback.id,
            "rating": feedback.rating.value if feedback.rating else None,
            "category": feedback.feedback_category.value if feedback.feedback_category else None,
            "text": feedback.feedback_text,
            "reviewed": feedback.reviewed_at is not None,
        } if feedback else None
        items.append(item)

    return {"total": total, "items": items}


@router.get("/feedback-details/{feedback_id}")
def get_feedback_details(
    feedback_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get full feedback details including complete chat history."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import UserFeedback

    feedback = db.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    chat = db.query(ChatHistory).filter(ChatHistory.id == feedback.chat_id).first()
    return {
        "feedback": {
            "id": feedback.id,
            "rating": feedback.rating.value if feedback.rating else None,
            "category": feedback.feedback_category.value if feedback.feedback_category else None,
            "text": feedback.feedback_text,
            "reviewed_at": str(feedback.reviewed_at) if feedback.reviewed_at else None,
            "reviewed_by": feedback.reviewed_by,
            "created_at": str(feedback.created_at) if feedback.created_at else None,
        },
        "chat": {
            "id": chat.id,
            "question": chat.question,
            "generated_sql": chat.generated_sql,
            "sql_result_summary": chat.sql_result_summary,
            "ai_response": chat.ai_response,
            "tokens_used": chat.tokens_used,
            "execution_time_ms": chat.execution_time_ms,
            "context_name": chat.context_name,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        } if chat else None,
    }


@router.get("/query-analytics")
def get_query_analytics(
    period: str = Query("7d", description="Period: 7d, 30d, 90d"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get aggregated query analytics."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import FeedbackRating, UserFeedback

    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = datetime.utcnow() - timedelta(days=days)

    total = db.query(ChatHistory).filter(ChatHistory.created_at >= since).count()
    errors = db.query(ChatHistory).filter(
        ChatHistory.created_at >= since,
        (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == ""),
    ).count()
    thumbs_down = db.query(UserFeedback).filter(
        UserFeedback.created_at >= since,
        UserFeedback.rating == FeedbackRating.THUMBS_DOWN,
    ).count()
    total_feedback = db.query(UserFeedback).filter(UserFeedback.created_at >= since).count()

    context_rows = db.query(ChatHistory.context_name, func.count(ChatHistory.id)).filter(
        ChatHistory.created_at >= since
    ).group_by(ChatHistory.context_name).all()
    context_distribution = {(context_name or "unknown"): count for context_name, count in context_rows}

    category_rows = db.query(UserFeedback.feedback_category, func.count(UserFeedback.id)).filter(
        UserFeedback.created_at >= since,
        UserFeedback.rating == FeedbackRating.THUMBS_DOWN,
    ).group_by(UserFeedback.feedback_category).all()
    error_categories = {}
    for category, count in category_rows:
        cat_name = category.value if category else "unspecified"
        error_categories[cat_name] = count

    return {
        "period": period,
        "total_queries": total,
        "error_count": errors,
        "error_rate": round(errors / total, 3) if total > 0 else 0,
        "thumbs_down_count": thumbs_down,
        "thumbs_down_rate": round(thumbs_down / total_feedback, 3) if total_feedback > 0 else 0,
        "total_feedback": total_feedback,
        "context_distribution": context_distribution,
        "error_categories": error_categories,
    }

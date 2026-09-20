"""Operational and analytics admin endpoints."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api import deps
from app.config import settings
from app.db.session import business_engine, config_engine
from app.models.schema_models import (
    DataWarningModel,
    QueryComplexityPattern,
    SchemaBusinessRule,
    SchemaMetadata,
    SchemaSemanticMapping,
)
from app.models.user import User
from app.schemas.admin_schemas import DashboardStatsResponse
from app.services.admin_config_service import AdminConfigService
from app.services.feedback_service import FeedbackService
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService
from app.services.vanna_service import VannaService
from app.core.time_utils import utcnow

router = APIRouter()


@router.post("/refresh-cache", response_model=dict)
def refresh_schema_cache(
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
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
    _current_user: User = Depends(deps.require_admin),
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


@router.get("/dashboard-overview", response_model=dict)
def get_dashboard_overview(
    _current_user: User = Depends(deps.require_admin),
    config_db: Session = Depends(deps.get_config_db),
    app_db: Session = Depends(deps.get_db),
):
    """Get a blended admin dashboard view-model backed by runtime data."""
    from app.models.chat import ChatHistory

    feedback_service = FeedbackService(app_db)
    config_service = AdminConfigService(config_db)

    now = utcnow()
    since_7d = now - timedelta(days=7)

    total_queries_7d = app_db.query(ChatHistory).filter(ChatHistory.created_at >= since_7d).count()
    error_count_7d = app_db.query(ChatHistory).filter(
        ChatHistory.created_at >= since_7d,
        (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == ""),
    ).count()
    averages = app_db.query(
        func.avg(ChatHistory.execution_time_ms),
        func.avg(ChatHistory.tokens_used),
    ).filter(ChatHistory.created_at >= since_7d).one()
    avg_execution_time_ms_7d = round(float(averages[0] or 0), 1)
    avg_tokens_used_7d = int(round(float(averages[1] or 0), 0))

    context_rows = app_db.execute(text("""
        SELECT COALESCE(context_name, 'unknown') AS context_name, COUNT(*) AS count
        FROM chat_history
        WHERE created_at >= :since
        GROUP BY context_name
        ORDER BY count DESC
        LIMIT 5
    """), {"since": since_7d}).fetchall()
    top_contexts_7d = [{
        "context_name": row[0] or "unknown",
        "count": row[1],
    } for row in context_rows]

    feedback_stats = feedback_service.get_statistics(days=30)
    pending_reviews = feedback_service.get_pending_reviews(limit=5)
    trending_queries = feedback_service.get_trending_queries(days=7, limit=5)
    effective_ai = config_service.get_effective_ai_state()

    context_counts = config_db.execute(text("""
        SELECT
            COUNT(*) AS total_contexts,
            SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_contexts
        FROM schema_contexts
    """)).fetchone()
    total_contexts = int((context_counts[0] or 0) if context_counts else 0)
    active_contexts = int((context_counts[1] or 0) if context_counts else 0)

    total_users = app_db.query(User).count()
    total_mappings = config_db.query(SchemaSemanticMapping).count()
    total_rules = config_db.query(SchemaBusinessRule).count()
    total_columns = config_db.query(SchemaMetadata).count()
    active_warnings = config_db.query(DataWarningModel).filter(DataWarningModel.is_active == True).count()
    active_patterns = config_db.query(QueryComplexityPattern).filter(QueryComplexityPattern.is_active == True).count()

    pending_review_items = [{
        "id": feedback.id,
        "question": chat.question,
        "rating": feedback.rating.value if feedback.rating else None,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    } for feedback, chat in pending_reviews]

    alerts = []
    if effective_ai["fallback_in_use"]:
        alerts.append({
            "level": "warning",
            "title": "AI config is using fallback values",
            "message": "Provider or model metadata is not fully loading from ai_providers/ai_models, so the UI is falling back to legacy config values.",
            "href": "/models",
        })
    if not effective_ai["provider_alignment"]:
        alerts.append({
            "level": "warning",
            "title": "Default provider is out of sync",
            "message": "The default provider from admin_config does not match the provider table flag.",
            "href": "/providers",
        })
    if not effective_ai["model_alignment"]:
        alerts.append({
            "level": "warning",
            "title": "Default model is out of sync",
            "message": "The default model from admin_config does not match the provider's default model row.",
            "href": "/models",
        })
    if feedback_stats.get("pending_reviews", 0) > 0:
        alerts.append({
            "level": "info",
            "title": "Pending feedback needs review",
            "message": f"There are {feedback_stats['pending_reviews']} feedback items waiting for admin review.",
            "href": "/feedback",
        })
    if active_warnings > 0:
        alerts.append({
            "level": "info",
            "title": "Data warnings are active",
            "message": f"{active_warnings} warning rules are active. Review if operators are seeing repeated data-quality warnings.",
            "href": "/data-warnings",
        })
    if total_queries_7d > 0 and error_count_7d / total_queries_7d >= 0.1:
        alerts.append({
            "level": "warning",
            "title": "Query error rate is elevated",
            "message": f"{error_count_7d} of the last {total_queries_7d} queries failed to produce SQL.",
            "href": "/query-logs",
        })

    return {
        "generated_at": now.isoformat(),
        "effective_ai": effective_ai,
        "usage": {
            "total_queries_7d": total_queries_7d,
            "error_count_7d": error_count_7d,
            "error_rate_7d": round(error_count_7d / total_queries_7d, 3) if total_queries_7d else 0,
            "avg_execution_time_ms_7d": avg_execution_time_ms_7d,
            "avg_tokens_used_7d": avg_tokens_used_7d,
            "top_contexts_7d": top_contexts_7d,
        },
        "feedback": {
            "total_feedback_30d": feedback_stats.get("total_feedback", 0),
            "thumbs_up_30d": feedback_stats.get("thumbs_up", 0),
            "thumbs_down_30d": feedback_stats.get("thumbs_down", 0),
            "satisfaction_rate_30d": feedback_stats.get("satisfaction_rate", 0),
            "pending_reviews": feedback_stats.get("pending_reviews", 0),
            "pending_review_items": pending_review_items,
            "trending_queries_7d": trending_queries,
            "category_breakdown": feedback_stats.get("category_breakdown", {}),
        },
        "data_admin": {
            "total_users": total_users,
            "total_mappings": total_mappings,
            "total_rules": total_rules,
            "total_columns": total_columns,
            "total_contexts": total_contexts,
            "active_contexts": active_contexts,
            "active_warnings": active_warnings,
            "active_patterns": active_patterns,
        },
        "alerts": alerts,
    }


@router.post("/sync-brain", response_model=dict)
def sync_brain_knowledge(
    _current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Trigger Vanna brain sync. Admin only. One brain per active workspace (Plan 7 Phase 4b)."""
    try:
        from sqlalchemy import text as _text
        try:
            with service.engine.connect() as conn:
                workspaces = [row[0] for row in conn.execute(_text("SELECT name FROM workspaces WHERE is_active = 1 ORDER BY id"))]
        except Exception:  # registry not migrated: the single brain, as before
            workspaces = [None]
        for workspace in workspaces or [None]:
            VannaService(config={
                "path": settings.VANNA_CHROMA_PATH,
                "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD,
                "workspace": workspace,
            }).sync_brain(service)

        # Record sync timestamp
        try:
            config_svc = AdminConfigService()
            try:
                config_svc.set_config(
                    'last_brain_sync_at',
                    utcnow().isoformat(),
                    config_type='system',
                    category='system',
                )
            finally:
                config_svc.close()
        except Exception:
            pass

        return {"status": "success", "message": "Brain sync completed successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/clear-query-cache", response_model=dict)
def clear_query_cache_endpoint(
    _current_user: User = Depends(deps.require_admin),
):
    """Clear the in-memory query result cache."""
    cleared = clear_query_cache()
    return {"status": "success", "entries_cleared": cleared}


@router.get("/query-audit")
def get_query_audit(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=5000),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[int] = None,
    api_key_id: Optional[int] = None,
    workspace: Optional[str] = None,
    context: Optional[str] = None,
    channel: Optional[str] = None,  # chat / telegram / report_export / report_download / an API caller's source
    request_group: Optional[str] = None,  # Phase 5: a multi-context question and its sub-questions
    has_error: bool = Query(False, description="Only refusals / failures"),
    q: Optional[str] = Query(None, description="Text in the question or the SQL"),
    format: str = Query("json", pattern="^(json|csv)$"),
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Phase 4.5: who asked what, under which key / workspace / scope, what SQL ran, which columns and how
    many rows came back — every channel (chat, /api/v1/query, telegram, xlsx export and download). `format=csv` exports the same filter."""
    from app.models.query_audit import QueryAudit

    from app.services.query_audit import ensure_table
    ensure_table(db.get_bind())  # an app DB nobody has asked anything of yet / a table from before Phase 5
    query = db.query(QueryAudit).order_by(QueryAudit.created_at.desc(), QueryAudit.id.desc())
    try:
        if date_from:
            query = query.filter(QueryAudit.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.filter(QueryAudit.created_at <= datetime.fromisoformat(date_to))
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from / date_to ต้องเป็น ISO 8601")  # an audit never guesses the range
    for column, value in ((QueryAudit.user_id, user_id), (QueryAudit.api_key_id, api_key_id),
                          (QueryAudit.workspace, workspace), (QueryAudit.context_name, context),
                          (QueryAudit.request_group, request_group)):
        if value is not None:
            query = query.filter(column == value)
    if channel is not None:  # 'mcp' also finds 'mcp:<client>' (Phase 6: the client's self-reported name)
        query = query.filter((QueryAudit.channel == channel) | QueryAudit.channel.startswith(channel + ":", autoescape=True))
    if has_error:
        query = query.filter(QueryAudit.error.isnot(None))
    if q:
        query = query.filter(QueryAudit.question.contains(q) | QueryAudit.sql_query.contains(q))

    total = query.count()
    columns = [c.name for c in QueryAudit.__table__.columns]
    items = [{c: getattr(row, c) for c in columns} for row in query.offset(skip).limit(limit)]
    if format == "csv":
        import csv
        import io

        from fastapi.responses import Response
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        # the question is whatever a caller typed: a cell starting with = + - @ is a formula to a spreadsheet
        writer.writerows({k: "'" + v if isinstance(v, str) and v.lstrip()[:1] in ("=", "+", "-", "@") else v
                          for k, v in item.items()} for item in items)
        return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",  # BOM: Excel + Thai
                        headers={"Content-Disposition": "attachment; filename=query_audit.csv"})
    return {"total": total, "skip": skip, "limit": limit, "items": items}


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
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get paginated query logs with optional feedback join. Admin only."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import FeedbackRating, UserFeedback

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
        users = db.query(User).filter(User.id.in_(user_ids)).all()
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
    _current_user: User = Depends(deps.require_admin),
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
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get aggregated query analytics."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import FeedbackRating, UserFeedback

    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = utcnow() - timedelta(days=days)

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

    context_rows = db.execute(text("""
        SELECT COALESCE(context_name, 'unknown') AS context_name, COUNT(*) AS count
        FROM chat_history
        WHERE created_at >= :since
        GROUP BY context_name
    """), {"since": since}).fetchall()
    context_distribution = {(context_name or "unknown"): count for context_name, count in context_rows}

    category_rows = db.execute(text("""
        SELECT feedback_category, COUNT(*) AS count
        FROM user_feedback
        WHERE created_at >= :since
          AND rating = :rating
        GROUP BY feedback_category
    """), {"since": since, "rating": FeedbackRating.THUMBS_DOWN.value}).fetchall()
    error_categories = {}
    for category, count in category_rows:
        cat_name = str(category) if category else "unspecified"
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

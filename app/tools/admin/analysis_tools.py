"""
Analysis Tools — Query logs & feedback analysis
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool


class AnalyzeQueryLogsTool(AdminTool):
    name = "analyze_query_logs"
    description = "Analyze recent query logs: error rates, common failures, context distribution. Optionally filter by date range or context."
    description_th = "วิเคราะห์ query logs: อัตรา error, ปัญหาที่พบบ่อย, การกระจายตาม context"
    category = "analysis"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of past days to analyze (default: 7)",
                    "default": 7
                },
                "context_name": {
                    "type": "string",
                    "description": "Filter by specific context"
                },
                "errors_only": {
                    "type": "boolean",
                    "description": "Show only queries with errors",
                    "default": False
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.chat import ChatHistory
        from datetime import datetime, timedelta

        days = params.get("days", 7)
        since = datetime.utcnow() - timedelta(days=days)

        query = db.query(ChatHistory).filter(ChatHistory.created_at >= since)

        if params.get("context_name"):
            query = query.filter(ChatHistory.context_name == params["context_name"])

        all_chats = query.order_by(ChatHistory.created_at.desc()).all()

        total = len(all_chats)
        errors = [c for c in all_chats if getattr(c, "error", None)]
        error_count = len(errors)

        # Context distribution
        context_counts = {}
        for c in all_chats:
            ctx = getattr(c, "context_name", "unknown") or "unknown"
            context_counts[ctx] = context_counts.get(ctx, 0) + 1

        # Recent errors (last 10)
        recent_errors = []
        for c in errors[:10]:
            recent_errors.append({
                "id": c.id,
                "question": c.question[:100] if c.question else "",
                "error": str(getattr(c, "error", ""))[:200],
                "context": getattr(c, "context_name", ""),
                "created_at": str(c.created_at),
            })

        return {
            "success": True,
            "message": f"วิเคราะห์ {total} queries ใน {days} วัน: error rate {error_count}/{total}",
            "data": {
                "total_queries": total,
                "error_count": error_count,
                "error_rate": round(error_count / total, 3) if total > 0 else 0,
                "context_distribution": context_counts,
                "recent_errors": recent_errors,
                "period_days": days,
            }
        }


class ReviewFeedbackTool(AdminTool):
    name = "review_feedback"
    description = "Review recent user feedback (thumbs down, categories). Shows questions, SQL, and feedback details."
    description_th = "ดู feedback จากผู้ใช้ (thumbs down, หมวดหมู่) พร้อมรายละเอียด"
    category = "analysis"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of past days to review (default: 7)",
                    "default": 7
                },
                "thumbs_down_only": {
                    "type": "boolean",
                    "description": "Show only negative feedback",
                    "default": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results",
                    "default": 20
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.feedback_models import UserFeedback, FeedbackRating
        from app.models.chat import ChatHistory
        from datetime import datetime, timedelta

        days = params.get("days", 7)
        limit = params.get("limit", 20)
        since = datetime.utcnow() - timedelta(days=days)

        query = db.query(UserFeedback, ChatHistory).join(
            ChatHistory, UserFeedback.chat_id == ChatHistory.id
        ).filter(UserFeedback.created_at >= since)

        if params.get("thumbs_down_only", True):
            query = query.filter(UserFeedback.rating == FeedbackRating.THUMBS_DOWN)

        results = query.order_by(UserFeedback.created_at.desc()).limit(limit).all()

        feedback_list = []
        for fb, chat in results:
            feedback_list.append({
                "feedback_id": fb.id,
                "chat_id": chat.id,
                "rating": fb.rating.value if fb.rating else None,
                "category": fb.feedback_category.value if fb.feedback_category else None,
                "feedback_text": fb.feedback_text,
                "question": chat.question[:150] if chat.question else "",
                "generated_sql": getattr(chat, "generated_sql", "")[:300] if getattr(chat, "generated_sql", None) else "",
                "context": getattr(chat, "context_name", ""),
                "reviewed": fb.reviewed_at is not None,
                "created_at": str(fb.created_at),
            })

        return {
            "success": True,
            "message": f"พบ {len(feedback_list)} feedback ใน {days} วัน",
            "data": feedback_list,
            "total": len(feedback_list),
        }

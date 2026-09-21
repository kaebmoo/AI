from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.feedback_models import UserFeedback, FeedbackRating, FeedbackCategory, GoldenExample
from app.models.chat import ChatHistory
from app.core.time_utils import utcnow
from app.services.provenance import ACTIVE, MANUAL

class FeedbackService:
    def __init__(self, db: Session):
        self.db = db
    
    def submit_feedback(
        self,
        chat_id: int,
        rating: FeedbackRating,
        category: Optional[FeedbackCategory] = None,
        feedback_text: Optional[str] = None
    ) -> UserFeedback:
        """Submit user feedback for a chat response"""
        
        feedback = UserFeedback(
            chat_id=chat_id,
            rating=rating,
            feedback_category=category,
            feedback_text=feedback_text,
            created_at=utcnow()
        )
        
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        
        return feedback
    
    def get_pending_reviews(self, limit: int = 50) -> List[Tuple[UserFeedback, ChatHistory]]:
        """Get feedback pending review"""
        return self.db.query(UserFeedback, ChatHistory).join(
            ChatHistory, UserFeedback.chat_id == ChatHistory.id
        ).filter(
            UserFeedback.reviewed_at == None
        ).order_by(
            UserFeedback.created_at.desc()
        ).limit(limit).all()

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics"""
        from datetime import timedelta
        
        since = utcnow() - timedelta(days=days)
        
        # Base query for time range
        base_query = self.db.query(UserFeedback).filter(UserFeedback.created_at >= since)
        
        # 1. Total Feedback
        total_feedback = base_query.count()
        
        if total_feedback == 0:
            return {
                "total_feedback": 0,
                "thumbs_up": 0,
                "thumbs_down": 0,
                "satisfaction_rate": 0.0,
                "category_breakdown": {},
                "pending_reviews": 0
            }
            
        # 2. Counts by Rating
        thumbs_up = base_query.filter(UserFeedback.rating == FeedbackRating.THUMBS_UP).count()
        thumbs_down = base_query.filter(UserFeedback.rating == FeedbackRating.THUMBS_DOWN).count()
        
        # 3. Satisfaction Rate
        satisfaction_rate = (thumbs_up / total_feedback) * 100 if total_feedback > 0 else 0.0
        
        # 4. Category Breakdown
        # Manual aggregation for SQLite compatibility (and simplicity)
        category_counts = {}
        feedbacks_with_category = base_query.filter(UserFeedback.feedback_category != None).all()
        for fb in feedbacks_with_category:
            cat = fb.feedback_category.value if hasattr(fb.feedback_category, 'value') else str(fb.feedback_category)
            category_counts[cat] = category_counts.get(cat, 0) + 1
            
        # 5. Pending Reviews (All time)
        pending_reviews = self.db.query(UserFeedback).filter(UserFeedback.reviewed_at == None).count()
        
        return {
            "total_feedback": total_feedback,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "satisfaction_rate": round(satisfaction_rate, 2),
            "category_breakdown": category_counts,
            "pending_reviews": pending_reviews
        }

    def review_feedback(
        self,
        feedback_id: int,
        reviewer_id: int,
        notes: Optional[str] = None,
        is_golden_example: bool = False,
        config_db: Optional[Session] = None,
    ) -> UserFeedback:
        """Review feedback and optionally create golden example.

        The example goes to config.db (`config_db`; it used to go through the app.db session, which has no
        golden_examples table) and is the reviewer's own — manual, active (Plan 8.1)."""
        feedback = self.db.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError("Feedback not found")
            
        feedback.reviewed_by = reviewer_id
        feedback.reviewed_at = utcnow()
        feedback.review_notes = notes
        feedback.is_golden_example = is_golden_example
        
        # Create Golden Example if requested
        if is_golden_example:
            config = config_db or self.db
            chat = self.db.query(ChatHistory).filter(ChatHistory.id == feedback.chat_id).first()
            if chat:
                # Check if already exists to avoid duplicates
                existing = config.query(GoldenExample).filter(
                    GoldenExample.question_pattern == chat.question
                ).first()
                
                if not existing:
                    golden = GoldenExample(
                        chat_id=chat.id,
                        question_pattern=chat.question,
                        expected_sql=chat.generated_sql,  # (was chat.sql_query — no such column) 
                        # Ideally admin should provide correct SQL if the original was wrong.
                        # For now, using generated SQL. In future, allow admin to override.
                        category=feedback.feedback_category,
                        added_by=reviewer_id,
                        is_active=True,
                        source=MANUAL,
                        status=ACTIVE,
                    )
                    config.add(golden)
                    if config is not self.db:
                        config.commit()

        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def get_trending_queries(self, days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Get trending user queries"""
        from datetime import timedelta
        from sqlalchemy import func
        
        since = utcnow() - timedelta(days=days)
        
        # Aggregate by question text
        # Note: In production, might want to normalize text (trim, lower, remove punctuation)
        results = self.db.query(
            ChatHistory.question,
            func.count(ChatHistory.id).label('count')
        ).filter(
            ChatHistory.created_at >= since
        ).group_by(
            ChatHistory.question
        ).order_by(
            func.count(ChatHistory.id).desc()
        ).limit(limit).all()
        
        return [
            {"question": r.question, "count": r.count}
            for r in results
        ]

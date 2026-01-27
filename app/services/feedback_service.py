from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.feedback_models import UserFeedback, FeedbackRating, FeedbackCategory, GoldenExample
from app.models.chat import ChatHistory

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
            created_at=datetime.utcnow()
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

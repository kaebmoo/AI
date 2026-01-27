from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from app.models.chat import ChatHistory
from app.core.logging import logging

logger = logging.getLogger(__name__)

class TrendingService:
    """
    Service to analyze trending queries and topics.
    """
    def __init__(self, db: Session):
        self.db = db
        
    def get_top_questions(self, limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get most frequent questions in the last N days.
        Basic implementation using exact match grouping.
        In a real system, would use semantic clustering.
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        results = self.db.query(
            ChatHistory.question,
            func.count(ChatHistory.id).label('count')
        ).filter(
            ChatHistory.created_at >= start_date
        ).group_by(
            ChatHistory.question
        ).order_by(
            desc('count')
        ).limit(limit).all()
        
        return [
            {"question": r.question, "count": r.count}
            for r in results
        ]
        
    def get_recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent questions that resulted in errors.
        """
        results = self.db.query(ChatHistory).filter(
            ChatHistory.error_message.isnot(None)
        ).order_by(
            ChatHistory.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                "question": r.question, 
                "error": r.error_message,
                "created_at": r.created_at
            }
            for r in results
        ]

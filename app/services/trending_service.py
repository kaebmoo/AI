from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from app.models.chat import ChatHistory
from app.models.feedback_models import TrendingQuery
from app.core.logging import logging

logger = logging.getLogger(__name__)

class TrendingService:
    """
    Service to analyze trending queries and topics.
    """
    def __init__(self, db: Session):
        self.db = db
        
    def update_trending_queries(self):
        """
        Calculate and update trending queries for today.
        Should be run periodically (e.g. daily cron).
        """
        today = datetime.utcnow().date()
        date_start = datetime.combine(today, datetime.min.time())
        
        # 1. Clear existing for this timeframe to allow re-run
        self.db.query(TrendingQuery).filter(TrendingQuery.date >= date_start).delete()
        
        # 2. Top queries from ChatHistory (Last 7 days for better trend)
        since = datetime.utcnow() - timedelta(days=7)
        
        raw_trends = self.db.query(
            ChatHistory.question,
            func.count(ChatHistory.id).label('count')
        ).filter(
            ChatHistory.created_at >= since
        ).group_by(
            ChatHistory.question
        ).having(
            func.count(ChatHistory.id) > 1 
        ).all()
        
        # 3. Insert into TrendingQuery
        for r in raw_trends:
            # Normalize: strip whitespace
            q_text = r.question.strip() if r.question else ""
            if not q_text:
                continue
                
            entry = TrendingQuery(
                question=q_text,
                count=r.count,
                date=date_start
            )
            self.db.add(entry)
            
        self.db.commit()

    def get_top_questions(self, limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get most frequent questions from pre-calculated table.
        Fallback to direct aggregation if table is empty.
        """
        # Try fetching from TrendingQuery first (snapshot of today)
        today = datetime.utcnow().date()
        date_start = datetime.combine(today, datetime.min.time())
        
        trending = self.db.query(TrendingQuery).filter(
            TrendingQuery.date >= date_start
        ).order_by(
            TrendingQuery.count.desc()
        ).limit(limit).all()
        
        if trending:
            return [
                {"question": t.question, "count": t.count}
                for t in trending
            ]
            
        # Fallback to direct aggregation if periodic job hasn't run
        return self._get_top_questions_direct(limit, days)

    def _get_top_questions_direct(self, limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
        """Direct aggregation (fallback)"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        results = self.db.query(
            ChatHistory.question,
            func.count(ChatHistory.id).label('count')
        ).filter(
            ChatHistory.created_at >= start_date
        ).group_by(
            ChatHistory.question
        ).order_by(
            func.count(ChatHistory.id).desc()
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

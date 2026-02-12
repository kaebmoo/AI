from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.feedback_models import FeedbackRating, FeedbackCategory, UserFeedback
from app.services.feedback_service import FeedbackService
from app.services.trending_service import TrendingService
from app.services.ai_service import AIService

router = APIRouter()



@router.get("/pending", response_model=List[dict])
def get_pending_reviews(
    limit: int = 50,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get pending feedback for admin review.
    """
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not authorized")
         
    service = FeedbackService(db)
    pending = service.get_pending_reviews(limit=limit)
    
    # Transform to simple dict for JSON response
    # In a real app, use Pydantic schemas
    return [
        {
            "id": f.id,
            "chat_id": f.chat_id,
            "rating": f.rating,
            "feedback_text": f.feedback_text,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "question": c.question,
            "ai_response": c.ai_response
        }
        for f, c in pending
    ]

@router.get("/stats", response_model=dict)
def get_feedback_statistics(
    days: int = 30,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get aggregated feedback statistics.
    """
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not authorized")
         
    service = FeedbackService(db)
    service = FeedbackService(db)
    return service.get_statistics(days=days)

class ReviewFeedbackRequest(BaseModel):
    notes: Optional[str] = None
    is_golden_example: bool = False

@router.post("/{feedback_id}/review", response_model=dict)
def review_feedback(
    feedback_id: int,
    request: ReviewFeedbackRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Review feedback and verify action.
    """
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not authorized")
         
    service = FeedbackService(db)
    try:
        feedback = service.review_feedback(
            feedback_id=feedback_id,
            reviewer_id=current_user.id,
            notes=request.notes,
            is_golden_example=request.is_golden_example
        )
        
        return {
            "status": "reviewed",
            "reviewed_by": current_user.email,
            "reviewed_at": feedback.reviewed_at.isoformat(),
            "is_golden_example": feedback.is_golden_example
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/trending", response_model=List[dict])
def get_trending_queries(
    days: int = 7,
    limit: int = 10,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get trending queries from chat history.
    """
    # Assuming trending is public or admin only? User said "For UX improvement", so likely public or authenticated user.
    # Allowing any authenticated user.
    
    service = TrendingService(db)
    return service.get_top_questions(days=days, limit=limit)

@router.get("/admin/dashboard", response_model=dict)
def get_admin_dashboard(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get consolidated admin dashboard data.
    """
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not authorized")
         
    service = FeedbackService(db)
    
    stats = service.get_statistics(days=30)
    pending = service.get_pending_reviews(limit=10)
    trending = service.get_trending_queries(days=7, limit=5)
    
    # Format pending for dashboard
    formatted_pending = [
        {
            "id": f.id,
            "question": c.question,
            "rating": f.rating,
            "feedback_text": f.feedback_text,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f, c in pending
    ]
    
    return {
        "feedback_stats": stats,
        "pending_reviews": formatted_pending,
        "trending_queries": trending,
        # Placeholder for future metrics
        "slow_queries": []
    }

@router.post("/trending/update", response_model=dict)
def update_trending_queries(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Force update of trending queries (Admin only).
    """
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not authorized")
         
    service = TrendingService(db)
    service.update_trending_queries()
    return {"status": "updated"}

@router.post("/{chat_id}", response_model=dict)
def submit_feedback(
    chat_id: int,
    rating: FeedbackRating,
    category: Optional[FeedbackCategory] = None,
    feedback_text: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Submit feedback for a specific chat message.
    If Admin submits THUMBS_UP, auto-train the AI.
    """
    service = FeedbackService(db)
    
    try:
        feedback = service.submit_feedback(
            chat_id=chat_id,
            rating=rating,
            category=category,
            feedback_text=feedback_text
        )
        
        response_msg = "Feedback submitted successfully"
        
        # Auto-Training for Admins (Priority 2 Improvement)
        if current_user.role == "admin" and rating == FeedbackRating.THUMBS_UP:
            from app.models.chat import ChatHistory
            chat = db.query(ChatHistory).filter(ChatHistory.id == chat_id).first()
            
            if chat and chat.generated_sql:
                try:
                    # Train Vanna
                    ai_service.train(question=chat.question, sql_query=chat.generated_sql)
                    response_msg += " (Auto-trained)"
                except Exception as e:
                    print(f"Auto-train failed: {e}")
                    # Don't fail the feedback submission just because training failed
                    
        return {"message": response_msg, "id": feedback.id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not submit feedback: {str(e)}"
        )

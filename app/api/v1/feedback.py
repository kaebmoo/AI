from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.feedback_models import FeedbackRating, FeedbackCategory, UserFeedback
from app.services.feedback_service import FeedbackService

router = APIRouter()

@router.post("/{chat_id}", response_model=dict)
def submit_feedback(
    chat_id: int,
    rating: FeedbackRating,
    category: Optional[FeedbackCategory] = None,
    feedback_text: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Submit feedback for a specific chat message.
    """
    service = FeedbackService(db)
    
    # Verify chat ownership (or admin)
    # Ideally should check if chat_id belongs to current_user
    # For now assuming valid chat_id passed from frontend
    
    try:
        feedback = service.submit_feedback(
            chat_id=chat_id,
            rating=rating,
            category=category,
            feedback_text=feedback_text
        )
        return {"message": "Feedback submitted successfully", "id": feedback.id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not submit feedback: {str(e)}"
        )

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

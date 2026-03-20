"""
Unit Tests for Feedback Service
================================
"""

import pytest
from datetime import datetime, timedelta

from app.services.feedback_service import FeedbackService
from app.models.feedback_models import (
    UserFeedback,
    FeedbackRating,
    FeedbackCategory,
    GoldenExample
)
from app.models.chat import ChatHistory


class TestFeedbackService:
    """Test cases for FeedbackService"""

    def test_submit_feedback_thumbs_up(self, db_session, test_chat):
        """Test submitting positive feedback"""
        service = FeedbackService(db_session)

        feedback = service.submit_feedback(
            chat_id=test_chat.id,
            rating=FeedbackRating.THUMBS_UP
        )

        assert feedback is not None
        assert feedback.chat_id == test_chat.id
        assert feedback.rating == FeedbackRating.THUMBS_UP
        assert feedback.created_at is not None

    def test_submit_feedback_thumbs_down_with_category(self, db_session, test_chat):
        """Test submitting negative feedback with category"""
        service = FeedbackService(db_session)

        feedback = service.submit_feedback(
            chat_id=test_chat.id,
            rating=FeedbackRating.THUMBS_DOWN,
            category=FeedbackCategory.WRONG_DATA,
            feedback_text="ข้อมูลไม่ตรงกับความเป็นจริง"
        )

        assert feedback is not None
        assert feedback.rating == FeedbackRating.THUMBS_DOWN
        assert feedback.feedback_category == FeedbackCategory.WRONG_DATA
        assert feedback.feedback_text == "ข้อมูลไม่ตรงกับความเป็นจริง"

    def test_get_pending_reviews(self, db_session, test_chat):
        """Test getting pending reviews"""
        service = FeedbackService(db_session)

        # Create some feedback
        service.submit_feedback(
            chat_id=test_chat.id,
            rating=FeedbackRating.THUMBS_DOWN,
            category=FeedbackCategory.SQL_ERROR
        )

        pending = service.get_pending_reviews(limit=10)

        assert len(pending) > 0
        # Each item should have feedback and chat
        assert pending[0][0] is not None  # feedback
        assert pending[0][1] is not None  # chat

    def test_get_pending_reviews_excludes_reviewed(self, db_session, test_chat):
        """Test that reviewed feedback is not in pending"""
        service = FeedbackService(db_session)

        # Create reviewed feedback
        feedback = UserFeedback(
            chat_id=test_chat.id,
            rating=FeedbackRating.THUMBS_DOWN,
            created_at=datetime.utcnow(),
            reviewed_at=datetime.utcnow(),  # Already reviewed
            reviewed_by=1
        )
        db_session.add(feedback)
        db_session.commit()

        pending = service.get_pending_reviews()

        # Should not include reviewed feedback
        feedback_ids = [f.id for f, c in pending]
        assert feedback.id not in feedback_ids


class TestFeedbackCategories:
    """Test feedback category enums"""

    def test_all_categories_exist(self):
        """Test all expected categories exist"""
        expected_categories = [
            "WRONG_DATA",
            "INCOMPLETE",
            "HARD_TO_UNDERSTAND",
            "SLOW",
            "SQL_ERROR",
            "PERFECT",
            "OTHER"
        ]

        for cat_name in expected_categories:
            assert hasattr(FeedbackCategory, cat_name)

    def test_rating_values(self):
        """Test rating enum values"""
        assert FeedbackRating.THUMBS_UP.value == "thumbs_up"
        assert FeedbackRating.THUMBS_DOWN.value == "thumbs_down"


class TestGoldenExample:
    """Test GoldenExample model"""

    def test_create_golden_example(self, db_session, test_chat):
        """Test creating a golden example"""
        example = GoldenExample(
            chat_id=test_chat.id,
            question_pattern="รายได้รวมเดือน X",
            expected_sql="SELECT SUM(REVENUE_VALUE) FROM revenue WHERE MONTH=X",
            category="monthly_revenue",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(example)
        db_session.commit()

        assert example.id is not None
        assert example.is_active is True

    def test_query_active_examples(self, db_session, test_chat):
        """Test querying active golden examples"""
        # Create active and inactive examples
        active = GoldenExample(
            chat_id=test_chat.id,
            question_pattern="Active example",
            expected_sql="SELECT 1",
            category="test",
            is_active=True,
            created_at=datetime.utcnow()
        )
        inactive = GoldenExample(
            chat_id=test_chat.id,
            question_pattern="Inactive example",
            expected_sql="SELECT 2",
            category="test",
            is_active=False,
            created_at=datetime.utcnow()
        )
        db_session.add_all([active, inactive])
        db_session.commit()

        # Query active only
        active_examples = db_session.query(GoldenExample).filter(
            GoldenExample.is_active == True
        ).all()

        assert len(active_examples) == 1
        assert active_examples[0].question_pattern == "Active example"

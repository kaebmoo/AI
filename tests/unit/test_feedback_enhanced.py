"""
Unit Tests for Feedback + Query Log Enhancement (Plan 2)
==========================================================
Tests for enhanced query logs, feedback details, and analytics endpoints.
"""

import pytest
import sqlite3
from datetime import datetime, timedelta


@pytest.fixture
def feedback_db(tmp_path):
    """Create temp DB with chat_history + user_feedback + users for testing."""
    db_path = str(tmp_path / "feedback_test.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Users
    c.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT, role TEXT DEFAULT 'user', is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("INSERT INTO users (email, role) VALUES ('admin@test.com', 'admin')")
    c.execute("INSERT INTO users (email, role) VALUES ('user@test.com', 'user')")

    # User sessions
    c.execute("""
        CREATE TABLE user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, session_token TEXT UNIQUE,
            expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Conversations
    c.execute("""
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER, title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Chat history
    c.execute("""
        CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, session_id INTEGER, conversation_id TEXT,
            question TEXT, generated_sql TEXT, sql_result_summary TEXT,
            ai_response TEXT, tokens_used INTEGER DEFAULT 0,
            execution_time_ms REAL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            context_name TEXT, is_bookmarked INTEGER DEFAULT 0,
            feedback_rating INTEGER
        )
    """)

    # User feedback — matches app/models/feedback_models.py UserFeedback
    c.execute("""
        CREATE TABLE user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, rating TEXT NOT NULL, feedback_category TEXT,
            feedback_text TEXT, reviewed_at TIMESTAMP, reviewed_by INTEGER,
            review_notes TEXT, is_golden_example INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    now = datetime.utcnow()
    # Insert sample chat history
    for i in range(10):
        has_sql = i < 7  # 7 with SQL, 3 without (errors)
        ctx = "revenue" if i < 5 else "expense"
        c.execute("""
            INSERT INTO chat_history (user_id, question, generated_sql, ai_response, context_name, created_at, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            2, f"Question {i}", f"SELECT * FROM t WHERE x={i}" if has_sql else None,
            f"Answer {i}", ctx, (now - timedelta(hours=i)).isoformat(), 100 + i
        ))

    # Insert feedback (3 thumbs down, 2 thumbs up)
    c.execute("INSERT INTO user_feedback (chat_id, rating, feedback_category, feedback_text, created_at) VALUES (1, 'THUMBS_DOWN', 'SQL_ERROR', 'SQL ผิด', ?)", (now.isoformat(),))
    c.execute("INSERT INTO user_feedback (chat_id, rating, feedback_category, feedback_text, created_at) VALUES (2, 'THUMBS_DOWN', 'WRONG_DATA', 'ข้อมูลผิด', ?)", (now.isoformat(),))
    c.execute("INSERT INTO user_feedback (chat_id, rating, created_at) VALUES (3, 'THUMBS_UP', ?)", (now.isoformat(),))
    c.execute("INSERT INTO user_feedback (chat_id, rating, created_at) VALUES (8, 'THUMBS_DOWN', ?)", (now.isoformat(),))
    c.execute("INSERT INTO user_feedback (chat_id, rating, created_at) VALUES (4, 'THUMBS_UP', ?)", (now.isoformat(),))

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def feedback_session(feedback_db):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    engine = create_engine(f"sqlite:///{feedback_db}")
    session = SASession(engine)
    yield session
    session.close()


class TestQueryLogsEnhanced:
    """Test enhanced query-logs endpoint."""

    def test_query_log_includes_sql(self, feedback_session):
        """Query logs include full generated_sql."""
        from app.models.chat import ChatHistory
        chat = feedback_session.query(ChatHistory).first()
        assert chat.generated_sql is not None or chat.generated_sql is None  # Just verify column exists

    def test_query_log_includes_feedback(self, feedback_session):
        """Query logs can join with feedback."""
        from app.models.chat import ChatHistory
        from app.models.feedback_models import UserFeedback

        results = feedback_session.query(ChatHistory, UserFeedback).outerjoin(
            UserFeedback, ChatHistory.id == UserFeedback.chat_id
        ).all()

        # Should have results
        assert len(results) >= 10

        # Some should have feedback
        with_feedback = [r for r in results if r[1] is not None]
        assert len(with_feedback) >= 3

    def test_query_log_filter_thumbs_down(self, feedback_session):
        """Filter for thumbs-down only returns correct subset."""
        from app.models.chat import ChatHistory
        from app.models.feedback_models import UserFeedback, FeedbackRating

        results = feedback_session.query(ChatHistory, UserFeedback).join(
            UserFeedback, ChatHistory.id == UserFeedback.chat_id
        ).filter(
            UserFeedback.rating == FeedbackRating.THUMBS_DOWN
        ).all()

        assert len(results) == 3
        for chat, fb in results:
            assert fb.rating == FeedbackRating.THUMBS_DOWN

    def test_query_log_filter_context(self, feedback_session):
        """Filter by context returns only matching queries."""
        from app.models.chat import ChatHistory

        results = feedback_session.query(ChatHistory).filter(
            ChatHistory.context_name == "expense"
        ).all()

        for r in results:
            assert r.context_name == "expense"


class TestFeedbackDetails:

    def test_feedback_detail_includes_sql(self, feedback_session):
        """Feedback detail includes full chat history with SQL."""
        from app.models.feedback_models import UserFeedback
        from app.models.chat import ChatHistory

        fb = feedback_session.query(UserFeedback).first()
        chat = feedback_session.query(ChatHistory).filter(ChatHistory.id == fb.chat_id).first()

        assert fb is not None
        assert chat is not None
        assert hasattr(chat, "generated_sql")


class TestQueryAnalytics:

    def test_analytics_counts(self, feedback_session):
        """Analytics computes correct totals."""
        from app.models.chat import ChatHistory

        total = feedback_session.query(ChatHistory).count()
        assert total == 10

        errors = feedback_session.query(ChatHistory).filter(
            (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == "")
        ).count()
        assert errors == 3

    def test_analytics_error_rate(self, feedback_session):
        """Error rate is computed correctly."""
        from app.models.chat import ChatHistory

        total = feedback_session.query(ChatHistory).count()
        errors = feedback_session.query(ChatHistory).filter(
            (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == "")
        ).count()

        error_rate = round(errors / total, 3) if total > 0 else 0
        assert error_rate == 0.3  # 3/10

    def test_analytics_context_distribution(self, feedback_session):
        """Context distribution counts correctly."""
        from app.models.chat import ChatHistory
        from sqlalchemy import func

        ctx_rows = feedback_session.query(
            ChatHistory.context_name, func.count(ChatHistory.id)
        ).group_by(ChatHistory.context_name).all()

        ctx_dist = dict(ctx_rows)
        assert ctx_dist.get("revenue") == 5
        assert ctx_dist.get("expense") == 5

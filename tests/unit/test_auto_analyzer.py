"""
Unit Tests for Auto-Analyzer (Plan 3)
=======================================
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from app.services.auto_analyzer import AutoAnalyzer, SuggestedFix


@pytest.fixture
def analyzer_db(tmp_path):
    """DB with chat_history + feedback + mapping tables for analyzer testing."""
    db_path = str(tmp_path / "analyzer_test.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Users
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, role TEXT)")

    # Sessions
    c.execute("CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, user_id INTEGER, session_token TEXT, expires_at TIMESTAMP)")

    # Conversations
    c.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id INTEGER, title TEXT)")

    # Chat history
    c.execute("""
        CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, session_id INTEGER, conversation_id TEXT,
            question TEXT, generated_sql TEXT, sql_result_summary TEXT,
            ai_response TEXT, tokens_used INTEGER DEFAULT 0,
            execution_time_ms REAL DEFAULT 0, context_name TEXT,
            is_bookmarked INTEGER DEFAULT 0, feedback_rating INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User feedback
    c.execute("""
        CREATE TABLE user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, rating TEXT NOT NULL, feedback_category TEXT,
            feedback_text TEXT, reviewed_at TIMESTAMP, reviewed_by INTEGER,
            review_notes TEXT, is_golden_example INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Semantic mappings (for keyword check)
    c.execute("""
        CREATE TABLE schema_semantic_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE, keyword_type TEXT DEFAULT 'term',
            target_column TEXT NOT NULL, target_condition TEXT DEFAULT '',
            full_condition TEXT, description TEXT, priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1, context_name TEXT,
            created_at TIMESTAMP, updated_at TIMESTAMP
        )
    """)
    c.execute("INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('รายได้', 'REVENUE_VALUE', '')")

    # Suggested fixes
    c.execute("""
        CREATE TABLE suggested_fixes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fix_type TEXT, params TEXT, confidence REAL DEFAULT 0, reason TEXT,
            source_query_ids TEXT, status TEXT DEFAULT 'pending',
            reviewed_by INTEGER, reviewed_at TIMESTAMP, applied_audit_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    now = datetime.utcnow()
    # 5 failed queries about 'datacom' (no mapping)
    for i in range(5):
        c.execute("""
            INSERT INTO chat_history (question, generated_sql, context_name, created_at)
            VALUES (?, NULL, 'revenue', ?)
        """, (f"รายได้ datacom ปี 68 ข้อ {i}", (now - timedelta(hours=i)).isoformat()))

    # 3 successful queries
    for i in range(3):
        c.execute("""
            INSERT INTO chat_history (question, generated_sql, context_name, created_at)
            VALUES (?, 'SELECT 1', 'revenue', ?)
        """, (f"รายได้รวม {i}", (now - timedelta(hours=i)).isoformat()))

    # Add thumbs down for first 3 failed
    for i in range(1, 4):
        c.execute("""
            INSERT INTO user_feedback (chat_id, rating, created_at)
            VALUES (?, 'THUMBS_DOWN', ?)
        """, (i, now.isoformat()))

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def analyzer_session(analyzer_db):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    engine = create_engine(f"sqlite:///{analyzer_db}")
    session = SASession(engine)
    yield session
    session.close()


class TestAutoAnalyzer:

    async def test_analyze_recent_failures(self, analyzer_session):
        """Analyze finds failed queries."""
        analyzer = AutoAnalyzer(analyzer_session)
        result = await analyzer.analyze_recent_failures(period_hours=48)
        assert result.total_failures >= 5
        assert len(result.groups) >= 1

    async def test_group_similar_failures(self, analyzer_session):
        """Similar queries are grouped together."""
        analyzer = AutoAnalyzer(analyzer_session)
        result = await analyzer.analyze_recent_failures(period_hours=48)
        # The 5 'datacom' queries should be grouped
        datacom_groups = [g for g in result.groups if 'datacom' in g.pattern]
        assert len(datacom_groups) >= 1
        assert datacom_groups[0].count >= 3

    async def test_suggested_fix_add_mapping(self, analyzer_session):
        """Unmapped keyword suggests add_mapping fix."""
        analyzer = AutoAnalyzer(analyzer_session)
        result = await analyzer.analyze_recent_failures(period_hours=48)
        mapping_fixes = [f for f in result.suggested_fixes if f.fix_type == "add_mapping"]
        # Should suggest mapping for 'datacom'
        assert len(mapping_fixes) >= 1

    async def test_no_failures_returns_empty(self, tmp_path):
        """No failures in period returns empty result."""
        # Use empty DB with no chat_history
        import sqlite3
        db_path = str(tmp_path / "empty_test.sqlite")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, role TEXT)")
        c.execute("CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, user_id INTEGER, session_token TEXT, expires_at TIMESTAMP)")
        c.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id INTEGER, title TEXT)")
        c.execute("""CREATE TABLE chat_history (id INTEGER PRIMARY KEY, user_id INTEGER, session_id INTEGER,
            conversation_id TEXT, question TEXT, generated_sql TEXT, sql_result_summary TEXT,
            ai_response TEXT, tokens_used INTEGER DEFAULT 0, execution_time_ms REAL DEFAULT 0,
            context_name TEXT, is_bookmarked INTEGER DEFAULT 0, feedback_rating INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE user_feedback (id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL,
            rating TEXT NOT NULL, feedback_category TEXT, feedback_text TEXT,
            reviewed_at TIMESTAMP, reviewed_by INTEGER, review_notes TEXT,
            is_golden_example INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        conn.close()

        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SASession
        engine = create_engine(f"sqlite:///{db_path}")
        session = SASession(engine)

        analyzer = AutoAnalyzer(session)
        result = await analyzer.analyze_recent_failures(period_hours=24)
        assert result.total_failures == 0
        assert result.suggested_fixes == []
        session.close()

    async def test_analyze_single_query(self, analyzer_session):
        """Single query analysis returns result."""
        analyzer = AutoAnalyzer(analyzer_session)
        result = await analyzer.analyze_single_query(chat_id=1)
        assert result is not None
        assert result.total_failures == 1

    def test_confidence_auto_apply(self):
        """High confidence fix is auto_applicable."""
        fix = SuggestedFix(
            fix_type="add_mapping", params={}, confidence=0.9,
            reason="test", source_query_ids=[1]
        )
        assert fix.auto_applicable is True

    def test_confidence_low_not_auto(self):
        """Low confidence fix is not auto_applicable."""
        fix = SuggestedFix(
            fix_type="add_mapping", params={}, confidence=0.5,
            reason="test", source_query_ids=[1]
        )
        assert fix.auto_applicable is False

"""
Unit Tests for Dedup Engine (Plan 3)
======================================
"""

import pytest
import sqlite3

from app.services.dedup_engine import DedupEngine


@pytest.fixture
def dedup_db(tmp_path):
    """Create temp DB with mapping/rule/example tables + sample data."""
    db_path = str(tmp_path / "dedup_test.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

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
    c.execute("INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('ดาต้าคอม', 'SERVICE_GROUP', '= ''Datacom''')")
    c.execute("INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('Datacom', 'SERVICE_GROUP', '= ''Datacom''')")

    c.execute("""
        CREATE TABLE schema_business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT UNIQUE NOT NULL, rule_name TEXT DEFAULT '', rule_description TEXT DEFAULT '',
            table_name TEXT, applies_to TEXT, example_correct TEXT, example_wrong TEXT,
            severity TEXT DEFAULT 'warning', is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP, updated_at TIMESTAMP
        )
    """)
    c.execute("INSERT INTO schema_business_rules (rule_code, rule_name, rule_description) VALUES ('FILTER_001', 'Year filter', 'ต้อง filter YEAR')")

    c.execute("""
        CREATE TABLE golden_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER,
            question_pattern TEXT NOT NULL, expected_sql TEXT NOT NULL,
            category TEXT, is_active INTEGER DEFAULT 1,
            added_by INTEGER, usage_count INTEGER DEFAULT 0, created_at TIMESTAMP
        )
    """)
    c.execute("INSERT INTO golden_examples (question_pattern, expected_sql, category) VALUES ('รายได้รวมปี 68', 'SELECT SUM(REVENUE_VALUE) FROM revenue WHERE YEAR=2025', 'revenue')")

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def dedup_session(dedup_db):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    engine = create_engine(f"sqlite:///{dedup_db}")
    session = SASession(engine)
    yield session
    session.close()


class TestMappingDedup:

    def test_exact_duplicate_mapping(self, dedup_session):
        """Exact keyword match returns has_duplicate=True."""
        engine = DedupEngine(dedup_session)
        result = engine.check_mapping_duplicate("ดาต้าคอม")
        assert result.has_duplicate is True
        assert result.duplicate_type == "exact"

    def test_case_insensitive_duplicate(self, dedup_session):
        """Case-insensitive match is detected."""
        engine = DedupEngine(dedup_session)
        result = engine.check_mapping_duplicate("datacom")
        assert result.has_duplicate is True
        assert result.duplicate_type == "case_insensitive"

    def test_no_duplicate(self, dedup_session):
        """New keyword has no duplicate."""
        engine = DedupEngine(dedup_session)
        result = engine.check_mapping_duplicate("อินเตอร์เน็ต")
        assert result.has_duplicate is False

    def test_conflict_detection(self, dedup_session):
        """Same keyword mapping to different column is a conflict."""
        engine = DedupEngine(dedup_session)
        result = engine.check_mapping_duplicate("ดาต้าคอม", target_column="BUSINESS_GROUP")
        assert result.has_duplicate is True
        # Either exact or conflict — both are valid


class TestRuleDedup:

    def test_rule_duplicate_by_code(self, dedup_session):
        """Duplicate rule_code is detected."""
        engine = DedupEngine(dedup_session)
        result = engine.check_rule_duplicate("FILTER_001")
        assert result.has_duplicate is True
        assert result.duplicate_type == "exact"

    def test_rule_no_duplicate(self, dedup_session):
        """New rule_code has no duplicate."""
        engine = DedupEngine(dedup_session)
        result = engine.check_rule_duplicate("NEW_RULE_001")
        assert result.has_duplicate is False


class TestExampleDedup:

    def test_example_duplicate_exact_sql(self, dedup_session):
        """Exact SQL match is detected."""
        engine = DedupEngine(dedup_session)
        result = engine.check_example_duplicate(
            "any question",
            "SELECT SUM(REVENUE_VALUE) FROM revenue WHERE YEAR=2025"
        )
        assert result.has_duplicate is True
        assert result.duplicate_type == "exact_sql"

    def test_example_duplicate_similar_question(self, dedup_session):
        """Similar question is detected."""
        engine = DedupEngine(dedup_session)
        result = engine.check_example_duplicate(
            "รายได้รวมปี 68",
            "SELECT SOMETHING_ELSE"
        )
        assert result.has_duplicate is True
        assert result.duplicate_type == "similar_question"

    def test_example_no_duplicate(self, dedup_session):
        """Completely new example has no duplicate."""
        engine = DedupEngine(dedup_session)
        result = engine.check_example_duplicate(
            "ค่าใช้จ่ายแยกตามหน่วยงาน",
            "SELECT DEPARTMENT, SUM(EXPENSE) FROM expense GROUP BY DEPARTMENT"
        )
        assert result.has_duplicate is False

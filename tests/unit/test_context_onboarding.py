"""
Unit Tests: Context Onboarding System
======================================
Tests for DataInspector, ConfigGenerator, ConfigApplicator, ConfigValidator,
ContextOnboardingService, and LLMAnalyzer (mocked).
"""
import json
import os
import sqlite3
import tempfile

import pytest
from tests.unit import knowledge_db

from app.services.context_onboarding import (
    ConfigApplicator,
    ConfigBundle,
    ConfigGenerator,
    ConfigValidator,
    ContextOnboardingService,
    DataInspector,
    LLMAnalyzer,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def business_db():
    """Create temp SQLite business DB with test data."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    conn = sqlite3.connect(path)

    # Config tables
    conn.execute("""
        CREATE TABLE schema_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE, display_name TEXT, main_view TEXT,
            keywords TEXT, instruction_th TEXT, instruction_en TEXT,
            is_active INTEGER DEFAULT 1, priority INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE schema_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT, column_name TEXT, display_name_th TEXT,
            description TEXT, is_summable INTEGER DEFAULT 0,
            is_groupable INTEGER DEFAULT 0, special_notes TEXT,
            data_type TEXT, dimension_group TEXT, updated_at TEXT,
            UNIQUE(table_name, column_name)
        )
    """)
    conn.execute("""
        CREATE TABLE schema_business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT UNIQUE, rule_name TEXT, rule_description TEXT,
            table_name TEXT, example_correct TEXT, example_wrong TEXT,
            severity TEXT DEFAULT 'warning', inject_mode TEXT DEFAULT 'schema_context',
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE golden_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_pattern TEXT, expected_sql TEXT,
            category TEXT, is_active INTEGER DEFAULT 1, usage_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE schema_semantic_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE, keyword_type TEXT DEFAULT 'term',
            target_column TEXT, target_condition TEXT,
            context_name TEXT, is_active INTEGER DEFAULT 1, priority INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE master_hierarchy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_name TEXT, level INTEGER, level_label_th TEXT,
            level_label_en TEXT, level_columns TEXT, detection_keywords TEXT,
            is_active INTEGER DEFAULT 1, source TEXT, parent_column TEXT, source_view TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE data_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, keywords TEXT, exclude_keywords TEXT,
            columns_to_check TEXT, message TEXT, severity TEXT DEFAULT 'info',
            context_name TEXT, is_active INTEGER DEFAULT 1
        )
    """)

    # test_revenue: long_table
    conn.execute("""
        CREATE TABLE test_revenue (
            revenue_value REAL, business_unit TEXT, report_month TEXT, report_year INTEGER
        )
    """)
    conn.executemany("INSERT INTO test_revenue VALUES (?,?,?,?)", [
        (100.0, "Mobile", "01", 2025),
        (200.0, "Fixed", "01", 2025),
        (150.0, "Mobile", "02", 2025),
        (180.0, "Fixed", "02", 2025),
    ])

    # test_pl: semi_crosstab (P&L-like)
    # Need >20 distinct values in amount_value for value_col detection (distinct_count > 20)
    conn.execute("""
        CREATE TABLE test_pl (
            amount_value REAL, main_group TEXT, sub_group TEXT, report_month TEXT
        )
    """)
    import random
    random.seed(42)
    pl_rows = []
    sub_groups = ["บริการ A", "บริการ B", "บริการ C", "บริการ D"]
    for month in ["01", "02", "03", "04", "05", "06"]:
        for sg in sub_groups:
            pl_rows.append((random.uniform(800, 1500), "01.รายได้", sg, month))
            pl_rows.append((-random.uniform(500, 900), "02.ต้นทุน", sg, month))
            pl_rows.append((random.uniform(100, 600), "03.กำไรขั้นต้น", sg, month))
    conn.executemany("INSERT INTO test_pl VALUES (?,?,?,?)", pl_rows)

    # test_wide: wide_table (need >2 numeric cols with >20 distinct values each)
    conn.execute("""
        CREATE TABLE test_wide (
            revenue REAL, cost REAL, profit REAL, department TEXT
        )
    """)
    wide_rows = []
    depts = ["A", "B", "C", "D", "E"]
    for d in depts:
        for i in range(10):
            r = random.uniform(500, 5000)
            c = random.uniform(300, 3000)
            wide_rows.append((r, c, r - c, d))
    conn.executemany("INSERT INTO test_wide VALUES (?,?,?,?)", wide_rows)

    conn.commit()
    conn.close()
    knowledge_db.add_provenance(path)  # Plan 8.1 columns + proposal queue
    yield path
    os.close(fd)
    os.unlink(path)


MOCK_ANALYSIS = {
    "data_structure": {
        "type": "long_table",
        "explanation": "Single value column, all rows are revenue",
        "value_columns": ["revenue_value"],
        "critical_rule": None,
    },
    "context": {
        "name": "test_revenue",
        "display_name_th": "รายได้ทดสอบ",
        "display_name_en": "Test Revenue",
        "keywords": ["รายได้", "revenue", "test"],
        "instruction_th": "ข้อมูลรายได้สำหรับทดสอบ",
        "instruction_en": "Test revenue data",
    },
    "schema_metadata": [
        {
            "column_name": "revenue_value",
            "display_name_th": "มูลค่ารายได้",
            "description": "ยอดรายได้",
            "is_summable": True,
            "is_groupable": False,
            "special_notes": "",
        }
    ],
    "business_rules": [
        {
            "rule_code": "TEST_001",
            "rule_name": "ทดสอบ",
            "rule_description": "rule ทดสอบ",
            "severity": "warning",
            "example_correct": "SELECT SUM(revenue_value) FROM test_revenue",
            "example_wrong": "SELECT revenue_value FROM test_revenue",
            "inject_mode": "schema_context",
        }
    ],
    "golden_examples": [
        {
            "question": "รายได้รวม",
            "sql": "SELECT SUM(revenue_value) FROM test_revenue",
            "category": "test",
        }
    ],
    "semantic_mappings": [
        {
            "keyword": "มือถือ",
            "keyword_type": "term",
            "target_column": "business_unit",
            "target_condition": "business_unit = 'Mobile'",
        }
    ],
    "hierarchy": [
        {
            "level": 0,
            "label_th": "กลุ่มธุรกิจ",
            "level_columns": "business_unit",
            "detection_keywords": ["กลุ่มธุรกิจ"],
        }
    ],
    "data_warnings": [
        {
            "code": "test_warn",
            "message": "เตือนทดสอบ",
            "severity": "info",
            "context_name": "test_revenue",
        }
    ],
}


# ============================================================
# T1: DataInspector
# ============================================================

class TestDataInspector:
    def test_inspect_long_table(self, business_db):
        """T1.1: long_table detection."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_revenue")
        assert result.detected_structure == "long_table"
        assert result.row_count == 4
        assert len(result.columns) == 4

    def test_inspect_semi_crosstab(self, business_db):
        """T1.2: semi_crosstab detection with mixed +/- signs."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_pl")
        assert result.detected_structure == "semi_crosstab"
        # Cross-column analysis should flag mixed signs
        has_semi = any(
            ca.likely_semi_crosstab
            for ca in result.cross_analyses
        )
        assert has_semi, "Should detect semi-crosstab via mixed +/- signs"

    def test_inspect_wide_table(self, business_db):
        """T1.3: wide_table detection (multiple numeric cols)."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_wide")
        assert result.detected_structure == "wide_table"

    def test_inspect_nonexistent(self, business_db):
        """T1.4: nonexistent table raises Exception."""
        inspector = DataInspector(business_db)
        with pytest.raises(Exception):
            inspector.inspect("nonexistent_table")

    def test_inspect_column_profiles(self, business_db):
        """T1.5: column profiles have distinct_count."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_revenue")
        for col in result.columns:
            assert col.distinct_count >= 0

    def test_inspect_time_column_detection(self, business_db):
        """T1.6: time-related columns detected."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_revenue")
        time_cols = [c.name for c in result.columns if c.is_time_column]
        assert "report_month" in time_cols or "report_year" in time_cols

    def test_inspect_numeric_prefix_detection(self, business_db):
        """T1.7: numeric prefix detection in main_group."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_pl")
        main_group_col = next(
            (c for c in result.columns if c.name == "main_group"), None
        )
        assert main_group_col is not None
        assert main_group_col.has_numeric_prefix is True

    def test_inspection_to_dict(self, business_db):
        """T1.8: to_dict() produces JSON-serializable output."""
        inspector = DataInspector(business_db)
        result = inspector.inspect("test_revenue")
        d = result.to_dict()
        # Should not raise
        json.dumps(d, ensure_ascii=False)
        assert "view_name" in d
        assert "columns" in d


# ============================================================
# T2: ConfigGenerator
# ============================================================

class TestConfigGenerator:
    def test_generate_produces_sql(self, business_db):
        """T2.1: generate() produces SQL statements and summary."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        assert isinstance(bundle, ConfigBundle)
        assert len(bundle.sql_statements) > 0
        assert bundle.summary != ""

    def test_generate_covers_all_tables(self, business_db):
        """T2.2: SQL covers all 7 config tables."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        sql_text = "\n".join(bundle.sql_statements)
        assert "schema_contexts" in sql_text
        assert "schema_metadata" in sql_text
        assert "schema_business_rules" in sql_text
        assert "golden_examples" in sql_text
        assert "schema_semantic_mapping" in sql_text
        assert "master_hierarchy" in sql_text
        assert "data_warnings" in sql_text

    def test_generate_escapes_quotes(self):
        """T2.3: single quotes in data don't break SQL."""
        analysis = {
            **MOCK_ANALYSIS,
            "context": {
                **MOCK_ANALYSIS["context"],
                "display_name_th": "O'Brien's Test",
            },
        }
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(analysis)
        # Should not crash
        assert len(bundle.sql_statements) > 0

    def test_generate_empty_analysis(self):
        """T2.4: empty analysis doesn't crash."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate({})
        assert isinstance(bundle, ConfigBundle)


# ============================================================
# T3: ConfigApplicator
# ============================================================

class TestConfigApplicator:
    def test_apply_dry_run(self, business_db):
        """T3.1: dry_run=True returns preview, DB unchanged."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        applicator = ConfigApplicator(business_db)

        result = applicator.apply(bundle, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["sql_count"] > 0

        # DB should not have the test context
        conn = sqlite3.connect(business_db)
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_contexts WHERE name = 'test_revenue'"
        ).fetchone()
        conn.close()
        assert row[0] == 0

    def test_apply_real(self, business_db):
        """T3.2: dry_run=False inserts data into DB."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        applicator = ConfigApplicator(business_db)

        result = applicator.apply(bundle, dry_run=False)
        assert result["status"] == "applied"
        assert result["success"] > 0

        # Verify data is in DB
        conn = sqlite3.connect(business_db)
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_contexts WHERE name = 'test_revenue'"
        ).fetchone()
        conn.close()
        assert row[0] >= 1

    def test_apply_invalid_sql(self, business_db):
        """T3.3: invalid SQL doesn't crash, errors are reported."""
        bundle = ConfigBundle(
            sql_statements=["INSERT INTO nonexistent_table VALUES (1)"],
            summary="test",
        )
        applicator = ConfigApplicator(business_db)
        result = applicator.apply(bundle, dry_run=False)
        assert len(result["errors"]) > 0

    def test_apply_sql_statements(self, business_db):
        """T3.extra: apply_sql_statements() works directly."""
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        applicator = ConfigApplicator(business_db)

        result = applicator.apply_sql_statements(bundle.sql_statements)
        assert result["status"] == "applied"
        assert result["success"] > 0


# ============================================================
# T4: ConfigValidator
# ============================================================

class TestConfigValidator:
    @pytest.mark.asyncio
    async def test_validate_with_config(self, business_db):
        """T4.1: validate passes when config exists."""
        # First apply config
        gen = ConfigGenerator("test_revenue")
        bundle = gen.generate(MOCK_ANALYSIS)
        applicator = ConfigApplicator(business_db)
        applicator.apply(bundle, dry_run=False)

        # Now validate
        validator = ConfigValidator(business_db)
        result = await validator.validate("test_revenue", [])
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_without_config(self, business_db):
        """T4.2: validate fails when no config exists."""
        validator = ConfigValidator(business_db)
        result = await validator.validate("no_such_view", [])
        assert result.passed is False


# ============================================================
# T5: ContextOnboardingService
# ============================================================

class TestContextOnboardingService:
    def test_generate_config_requires_view_name(self, business_db):
        """T5.1: generate_config() without view_name raises TypeError."""
        service = ContextOnboardingService(business_db)
        with pytest.raises(TypeError):
            service.generate_config(MOCK_ANALYSIS)

    def test_generate_config_with_view_name(self, business_db):
        """T5.2: generate_config() with view_name returns ConfigBundle."""
        service = ContextOnboardingService(business_db)
        bundle = service.generate_config(MOCK_ANALYSIS, view_name="v_test")
        assert isinstance(bundle, ConfigBundle)
        sql_text = "\n".join(bundle.sql_statements)
        assert "v_test" in sql_text

    def test_list_available_views(self, business_db):
        """T5.3: list_available_views() returns dict without config tables."""
        service = ContextOnboardingService(business_db)
        result = service.list_available_views()
        assert "unconfigured" in result
        assert "configured" in result

        all_names = [v["name"] for v in result["unconfigured"] + result["configured"]]
        # Config tables should not appear
        assert "schema_contexts" not in all_names
        assert "schema_metadata" not in all_names
        assert "golden_examples" not in all_names

        # Business tables should appear
        assert "test_revenue" in all_names
        assert "test_pl" in all_names

    def test_apply_sql_statements(self, business_db):
        """T5.4: apply_sql_statements() via service works."""
        service = ContextOnboardingService(business_db, config_db_path=business_db)  # single-file fixture
        bundle = service.generate_config(MOCK_ANALYSIS, view_name="test_revenue")
        result = service.apply_sql_statements(bundle.sql_statements)
        assert result["status"] == "applied"


# ============================================================
# T6: LLMAnalyzer (mock only)
# ============================================================

class TestLLMAnalyzer:
    def test_build_prompt(self, business_db):
        """T6.1: build_prompt() includes view_name and structure."""
        inspector = DataInspector(business_db)
        inspection = inspector.inspect("test_revenue")

        analyzer = LLMAnalyzer(business_db)
        prompt = analyzer.build_prompt(inspection)
        assert "test_revenue" in prompt
        assert "long_table" in prompt

    def test_parse_response_valid_json(self, business_db):
        """T6.2: _parse_response() parses valid JSON."""
        analyzer = LLMAnalyzer(business_db)
        result = analyzer._parse_response('{"context": {"name": "test"}}')
        assert result["context"]["name"] == "test"

    def test_parse_response_code_block(self, business_db):
        """T6.3: _parse_response() extracts JSON from code block."""
        analyzer = LLMAnalyzer(business_db)
        result = analyzer._parse_response('```json\n{"context": {"name": "test"}}\n```')
        assert result["context"]["name"] == "test"

    def test_parse_response_invalid(self, business_db):
        """T6.4: _parse_response() raises ValueError for non-JSON."""
        analyzer = LLMAnalyzer(business_db)
        with pytest.raises((ValueError, Exception)):
            analyzer._parse_response("this is not json at all!!!")


class TestOnboardingWritesConfigDb:
    """REMAIN-9.1: the facade inspects the business DB but applies/validates on the config DB."""

    def test_default_targets_config_db_not_business_db(self, business_db, tmp_path, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "CONFIG_DB_URL", f"sqlite:///{tmp_path / 'config.db'}")  # not the dev's .env
        service = ContextOnboardingService(business_db)
        config_path = settings.CONFIG_DB_URL.replace("sqlite:///", "")
        assert service.applicator.db_path == config_path != business_db
        assert service.validator.db_path == config_path

    @pytest.mark.asyncio
    async def test_apply_and_validate_on_separate_config_db(self, business_db, tmp_path):
        import shutil
        config_db = str(tmp_path / "config.sqlite")
        shutil.copy(business_db, config_db)  # same config tables, separate file
        service = ContextOnboardingService(business_db, config_db_path=config_db)
        bundle = service.generate_config(MOCK_ANALYSIS, view_name="test_revenue")
        assert service.apply(bundle, dry_run=False)["errors"] == []

        count = "SELECT COUNT(*) FROM schema_contexts WHERE main_view = 'test_revenue'"
        assert sqlite3.connect(config_db).execute(count).fetchone()[0] == 1
        assert sqlite3.connect(business_db).execute(count).fetchone()[0] == 0  # business DB untouched
        assert (await service.validate("test_revenue")).passed is True


class TestAdminAgentOnboardingTools:
    """REMAIN-9.7: the admin-agent tools passed a session as the DB path and called missing methods."""

    @pytest.fixture
    def engines(self, business_db, monkeypatch):
        from sqlalchemy import create_engine
        engine = create_engine(f"sqlite:///{business_db}")  # single-file fixture: data + config tables
        monkeypatch.setattr("app.db.session.business_engine", engine)
        monkeypatch.setattr("app.db.session.config_engine", engine)
        monkeypatch.setattr("app.api.v1.admin._shared.mark_brain_dirty", lambda: None)
        return business_db

    @pytest.mark.asyncio
    async def test_inspect_view(self, engines):
        from app.tools.admin.onboarding_tools import InspectViewTool
        out = await InspectViewTool().execute({"view_name": "test_revenue"}, db=object())
        assert out["success"] and out["data"]["row_count"] > 0

    @pytest.mark.asyncio
    async def test_run_onboarding_dry_run(self, engines, monkeypatch):
        from unittest.mock import AsyncMock
        from app.tools.admin.onboarding_tools import RunOnboardingTool
        monkeypatch.setattr(ContextOnboardingService, "analyze", AsyncMock(return_value=MOCK_ANALYSIS))
        monkeypatch.setattr(ConfigApplicator, "__init__", lambda self, db_path=None: setattr(self, "db_path", engines))
        out = await RunOnboardingTool().execute({"view_name": "test_revenue", "dry_run": True}, db=object())
        assert out["success"] and out["data"]["status"] == "dry_run" and out["data"]["sql_count"] > 0

    @pytest.mark.asyncio
    async def test_validate_config(self, engines):
        from app.tools.admin.onboarding_tools import ValidateConfigTool
        sqlite3.connect(engines).execute(
            "INSERT INTO schema_contexts (name, main_view) VALUES ('ctx_t', 'test_revenue')").connection.commit()
        out = await ValidateConfigTool().execute({"context_name": "ctx_t"}, db=object())
        assert out["success"] and out["data"]["context_name"] == "ctx_t"
        missing = await ValidateConfigTool().execute({"context_name": "nope"}, db=object())
        assert missing["success"] is False

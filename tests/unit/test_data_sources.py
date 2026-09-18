"""
Plan 7 Phase 1: source registry + per-request resolver.

- resolver picks the engine from context → source; legacy contexts keep the old DB
- file-source execution goes through the F4 validator; legacy-only data tools fail closed
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.services.data_sources import LEGACY_SOURCE, SourceBoundMCPClient, SourceResolver
from app.services.database_adapter import DuckDBFileAdapter
from scripts.migrate_data_sources import migrate

COLUMNS = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"},
           {"name": "revenue", "type": "DOUBLE"}]
TABLES = [{"table_name": "feed_x_fact_bu_monthly", "file_name": "fact_bu_monthly.csv", "columns": COLUMNS}]


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "latest"
    root.mkdir()
    (root / "fact_bu_monthly.csv").write_text(
        "year_month,bu,revenue\n202607,01.A,100.5\n202608,01.A,200.25\n202608,02.B,50\n"
    )
    return root


@pytest.fixture
def adapter(source_root, tmp_path):
    return DuckDBFileAdapter("t", str(source_root), TABLES, str(tmp_path / "cache"))


@pytest.fixture
def config_engine(tmp_path, source_root):
    """Config DB with two contexts: 'revenue' (legacy) and 'feed_x' (file source)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, main_view TEXT, "
                          "is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_contexts (name, main_view) VALUES "
                          "('revenue', 'revenue_search'), ('feed_x', 'feed_x_fact_bu_monthly')"))
    migrate(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO data_sources (name, source_type, root_path) VALUES ('df_x', 'duckdb_file', :r)"),
                     {"r": str(source_root)})
        sid = conn.execute(text("SELECT id FROM data_sources WHERE name='df_x'")).scalar_one()
        conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (:s, :t, :f, :c)"),
                     {"s": sid, "t": TABLES[0]["table_name"], "f": TABLES[0]["file_name"], "c": json.dumps(COLUMNS)})
        conn.execute(text("UPDATE schema_contexts SET source_id = :s WHERE name = 'feed_x'"), {"s": sid})
    return engine


@pytest.fixture
def resolver(config_engine, tmp_path):
    return SourceResolver(config_engine=config_engine, cache_dir=str(tmp_path / "cache"))


class TestMigration:
    def test_existing_contexts_bound_to_legacy_and_idempotent(self, config_engine):
        migrate(config_engine)  # second run: no error, no duplicate legacy row
        with config_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM data_sources WHERE name='legacy'")).scalar() == 1
            src = conn.execute(text("SELECT ds.name FROM schema_contexts sc JOIN data_sources ds "
                                    "ON ds.id = sc.source_id WHERE sc.name='revenue'")).scalar()
        assert src == "legacy"


class TestResolver:
    def test_file_source_context_gets_duckdb_engine(self, resolver):
        src = resolver.for_context("feed_x")
        assert src.source_type == "duckdb_file"
        assert src.engine.dialect.name == "duckdb"
        rows = src.adapter.execute_query("SELECT bu, revenue FROM feed_x_fact_bu_monthly WHERE year_month = 202607")
        assert rows == [{"bu": "01.A", "revenue": 100.5}]

    def test_legacy_context_keeps_business_db(self, resolver):
        from app.db.session import business_engine
        src = resolver.for_context("revenue")
        assert src is LEGACY_SOURCE
        assert src.engine is business_engine

    def test_unknown_or_missing_context_is_legacy(self, resolver):
        assert resolver.for_context("nope") is LEGACY_SOURCE
        assert resolver.for_context(None) is LEGACY_SOURCE

    def test_unmigrated_config_db_is_legacy(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1)"))
        assert SourceResolver(config_engine=engine).for_context("revenue") is LEGACY_SOURCE

    def test_adapter_cached_until_registration_changes(self, resolver, config_engine):
        a1 = resolver.for_context("feed_x").adapter
        assert resolver.for_context("feed_x").adapter is a1
        with config_engine.begin() as conn:
            conn.execute(text("UPDATE source_tables SET table_name = 'feed_x_renamed'"))
        a2 = resolver.for_context("feed_x").adapter
        assert a2 is not a1
        assert a2.execute_query("SELECT COUNT(*) AS n FROM feed_x_renamed")[0]["n"] == 3

    def test_name_variants_resolve_like_get_context_info(self, resolver):
        # get_context_info accepts 'feed x' for 'feed_x' — the data must follow the same row,
        # not fall back to legacy while the prompt describes the file source
        assert resolver.for_context("feed x").source_type == "duckdb_file"

    def test_dangling_source_id_fails_loud(self, resolver, config_engine):
        with config_engine.begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET source_id = 999 WHERE name = 'feed_x'"))
        with pytest.raises(ValueError, match="missing data source"):
            resolver.for_context("feed_x")

    def test_inactive_file_source_fails_loud_not_legacy(self, resolver, config_engine):
        with config_engine.begin() as conn:
            conn.execute(text("UPDATE data_sources SET is_active = 0 WHERE name = 'df_x'"))
        with pytest.raises(ValueError, match="inactive"):
            resolver.for_context("feed_x")


class TestSourceBoundMCPClient:
    def _client(self, resolver):
        inner = MagicMock()
        inner.call_tool = AsyncMock(return_value='{"valid": true}')
        return SourceBoundMCPClient(inner, resolver.for_context("feed_x")), inner

    def test_execute_query_runs_in_process_with_mcp_payload(self, resolver):
        client, inner = self._client(resolver)
        out = json.loads(asyncio.run(client.call_tool("execute_query", {
            "sql": "SELECT MAX(year_month) AS latest FROM feed_x_fact_bu_monthly", "limit": 1000, "validate_first": False,
        })))
        assert out["success"] is True and out["data"] == [{"latest": 202608}] and out["truncated"] is False
        inner.call_tool.assert_not_called()

    def test_validates_even_when_caller_skips_validation(self, resolver):
        client, _ = self._client(resolver)
        out = json.loads(asyncio.run(client.call_tool("execute_query", {
            "sql": "DELETE FROM feed_x_fact_bu_monthly", "validate_first": False,
        })))
        assert out["success"] is False and out["error"] == "SQL validation failed"

    def test_legacy_only_data_tools_fail_closed(self, resolver):
        client, inner = self._client(resolver)
        out = json.loads(asyncio.run(client.call_tool("get_sample_values", {"column_name": "bu"})))
        assert out["success"] is False
        inner.call_tool.assert_not_called()

    def test_other_tools_delegate_to_mcp(self, resolver):
        client, inner = self._client(resolver)
        assert asyncio.run(client.call_tool("validate_sql", {"sql": "SELECT 1"})) == '{"valid": true}'
        inner.call_tool.assert_awaited_once()


class TestPromptDialect:
    def test_duckdb_source_gets_duckdb_rules(self, adapter):
        from app.services.schema.prompt_builder import get_syntax_rules
        service = MagicMock(business_engine=adapter.engine)
        assert "DuckDB" in get_syntax_rules(service, "thai") and "//" in get_syntax_rules(service, "thai")

    def test_legacy_rules_unchanged(self):
        from app.db.session import business_engine
        from app.services.schema.prompt_builder import get_syntax_rules
        service = MagicMock(business_engine=business_engine)
        service.engine.name = "sqlite"
        assert get_syntax_rules(service, "thai").lstrip().startswith("**. SQLite Syntax:**")

    def test_schema_service_inspects_duckdb_views(self, adapter):
        from app.services.schema_service import SchemaService
        svc = SchemaService(db_engine=create_engine("sqlite://"), business_engine=adapter.engine)
        assert [c["name"] for c in svc.get_table_info("feed_x_fact_bu_monthly")] == ["year_month", "bu", "revenue"]


class TestQueryEngineWiring:
    def test_file_context_routes_ai_service_and_prompt_to_source(self, resolver):
        from app.providers.base import QueryResult
        from app.services import query_engine as qe

        qe._query_cache.clear()
        qe._dedup_store.clear()
        admin_config = MagicMock()
        admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
        admin_config.get_feature_flags.return_value = {}
        admin_config.get_provider_record.return_value = None
        mcp = MagicMock()
        engine = qe.QueryEngine(mcp_client=mcp, admin_config=admin_config)

        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        ai_service = MagicMock()
        ai_service.query_hybrid = AsyncMock(return_value=QueryResult(
            question="q", sql_query="SELECT 1", data=[], explanation="", tokens_used=0, provider="matcha"))
        schema_cls = MagicMock()
        schema_cls.return_value.build_system_prompt.return_value = "prompt"
        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])

        with patch.object(qe, "source_resolver", resolver), \
             patch.object(qe.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe, "AIService", return_value=ai_service) as ai_cls, \
             patch.object(qe, "SchemaService", schema_cls), \
             patch.object(qe, "WarningDetector", return_value=warning_detector) as wd_cls:
            asyncio.run(engine.query("q", context="feed_x"))

        bound = ai_cls.call_args.kwargs["mcp_client"]
        assert isinstance(bound, SourceBoundMCPClient) and bound._inner is mcp
        assert schema_cls.call_args.kwargs["business_engine"].dialect.name == "duckdb"
        assert ai_service.query_hybrid.call_args.kwargs["schema_service"] is schema_cls.return_value
        assert wd_cls.call_args.kwargs["mcp_client"] is bound
        qe._query_cache.clear()
        qe._dedup_store.clear()

"""
Plan 7 Phase 3: the caller's scope is enforced at the SQL layer (file source and legacy).

Exit criteria: scope year_month=202607 → "latest" is 202607, not 202608; scope org A asking
about org B → 0 rows / refused; an undeclared scope key → ScopeError (HTTP 400).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.services.data_sources import ScopeError, SourceBoundMCPClient, SourceResolver, request_scope
from scripts.migrate_data_sources import migrate

FACT = [{"name": "year_month", "type": "BIGINT"}, {"name": "cost_center", "type": "VARCHAR"},
        {"name": "revenue", "type": "DOUBLE"}]
BU = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"}, {"name": "revenue", "type": "DOUBLE"}]
DIM = [{"name": "cost_center", "type": "VARCHAR"}, {"name": "name", "type": "VARCHAR"}]
TABLES = [
    {"table_name": "feed_x_fact_org", "file_name": "fact_org.csv", "columns": FACT},
    {"table_name": "feed_x_fact_bu", "file_name": "fact_bu.csv", "columns": BU},    # no org column
    {"table_name": "feed_x_dim_org", "file_name": "dim_org.csv", "columns": DIM},   # no period column
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "latest"
    root.mkdir()
    (root / "fact_org.csv").write_text("year_month,cost_center,revenue\n202607,A,10\n202607,B,20\n202608,A,40\n202608,B,80\n")
    (root / "fact_bu.csv").write_text("year_month,bu,revenue\n202607,1.X,30\n202608,1.X,120\n")
    (root / "dim_org.csv").write_text("cost_center,name\nA,Org A\nB,Org B\n")

    biz = tmp_path / "biz.sqlite"  # legacy business DB
    engine = create_engine(f"sqlite:///{biz}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE revenue (YEAR INT, DIV TEXT, V REAL)"))
        conn.execute(text("INSERT INTO revenue VALUES (2024, 'D1', 1), (2025, 'D1', 2), (2025, 'D2', 4)"))
        conn.execute(text("CREATE VIEW revenue_search AS SELECT YEAR AS year, DIV AS division, V AS revenue FROM revenue"))
        conn.execute(text("CREATE VIEW v_other AS SELECT * FROM revenue"))
    monkeypatch.setattr("app.db.session.business_engine", engine)

    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, main_view TEXT, "
                          "is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_contexts (name, main_view) VALUES "
                          "('revenue', 'revenue_search'), ('feed_x', 'feed_x_fact_org'), ('expense', 'v_other')"))
    migrate(config)
    with config.begin() as conn:
        conn.execute(text("INSERT INTO data_sources (name, source_type, root_path) VALUES ('df_x', 'duckdb_file', :r)"),
                     {"r": str(root)})
        for t in TABLES:
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) "
                              "VALUES (2, :t, :f, :c)"), {"t": t["table_name"], "f": t["file_name"], "c": json.dumps(t["columns"])})
        conn.execute(text("UPDATE schema_contexts SET source_id = 2, "
                          "scope_columns = '{\"year_month\": \"year_month\", \"org_code\": \"cost_center\"}' "
                          "WHERE name = 'feed_x'"))
        conn.execute(text("UPDATE schema_contexts SET scope_columns = '{\"year\": \"year\"}' WHERE name = 'revenue'"))
    return SourceResolver(config_engine=config, cache_dir=str(tmp_path / "cache"))


def resolve(resolver, context, scope):
    token = request_scope.set(scope)
    try:
        return resolver.for_context(context)
    finally:
        request_scope.reset(token)


LATEST = "SELECT MAX(year_month) AS m FROM feed_x_fact_org"


class TestFileSourceScope:
    def test_latest_period_is_the_scoped_one(self, env):
        assert env.for_context("feed_x").adapter.execute_query(LATEST) == [{"m": 202608}]
        scoped = resolve(env, "feed_x", {"year_month": 202607})
        assert scoped.adapter.execute_query(LATEST) == [{"m": 202607}]
        # the prompt side (SchemaService data range/samples) reads through the same scope
        with scoped.engine.connect() as conn:
            assert conn.execute(text(LATEST)).scalar() == 202607
            assert conn.execute(text("SELECT MAX(year_month) FROM feed_x_fact_bu")).scalar() == 202607

    def test_other_org_gets_zero_rows(self, env):
        scoped = resolve(env, "feed_x", {"org_code": "A"})
        a = scoped.adapter
        assert a.execute_query("SELECT SUM(revenue) AS s FROM feed_x_fact_org WHERE cost_center = 'B'") == [{"s": None}]
        assert a.execute_query("SELECT DISTINCT cost_center FROM feed_x_fact_org") == [{"cost_center": "A"}]
        # a table the org scope can't filter (no cost_center) is refused, and empty underneath
        with pytest.raises(PermissionError):
            a.execute_query("SELECT SUM(revenue) FROM feed_x_fact_bu")
        with scoped.engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM feed_x_fact_bu")).scalar() == 0

    def test_prompt_note_names_the_tables_and_an_unusable_main_view(self, env):
        note = resolve(env, "feed_x", {"org_code": "A"}).adapter.scope_note
        assert "org_code = A" in note and "feed_x_dim_org" in note and "ใช้ไม่ได้" not in note
        with env._engine().begin() as conn:  # a main view the org scope can't filter
            conn.execute(text("UPDATE schema_contexts SET main_view = 'feed_x_fact_bu' WHERE name = 'feed_x'"))
        assert "feed_x_fact_bu และตารางอื่นนอกรายการข้างบน **ใช้ไม่ได้**" in \
            resolve(env, "feed_x", {"org_code": "A"}).adapter.scope_note

    @pytest.mark.parametrize("sql", [
        "SELECT SUM(revenue) FROM main.feed_x_fact_org",
        'SELECT SUM(revenue) FROM "main"."feed_x_fact_org"',
        "SELECT (SELECT SUM(revenue) FROM main.feed_x_fact_org) AS s",
        "WITH t AS (SELECT * FROM main.feed_x_fact_org) SELECT SUM(revenue) FROM t",
        "SELECT * FROM temp.feed_x_fact_org",
    ])
    def test_qualified_names_cannot_read_around_the_scope(self, env, sql):
        with pytest.raises(PermissionError):
            resolve(env, "feed_x", {"org_code": "A"}).adapter.execute_query(sql)

    def test_both_keys_and_lists(self, env):
        a = resolve(env, "feed_x", {"year_month": [202607, 202608], "org_code": ["B"]}).adapter
        assert a.execute_query("SELECT SUM(revenue) AS s FROM feed_x_fact_org") == [{"s": 100.0}]

    def test_quote_in_value_is_data_not_sql(self, env):
        a = resolve(env, "feed_x", {"org_code": "A' OR '1'='1"}).adapter
        assert a.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_org") == [{"n": 0}]

    def test_scope_changes_the_cache_version(self, env):
        base = env.for_context("feed_x").version
        v1 = resolve(env, "feed_x", {"year_month": 202607}).version
        v2 = resolve(env, "feed_x", {"year_month": 202608}).version
        assert len({base, v1, v2}) == 3

    def test_unscoped_resolution_is_unchanged(self, env):
        from app.services.database_adapter import DuckDBFileAdapter
        assert type(env.for_context("feed_x").adapter) is DuckDBFileAdapter
        assert env.for_context("revenue").adapter is None  # legacy stays on the MCP path


class TestScopeErrors:
    @pytest.mark.parametrize("scope", [
        {"division": "A"},                      # not declared by the context
        {"year_month": 2026.07}, {"year_month": True}, {"org_code": {"a": 1}},
        {"org_code": []}, {"org_code": [["A"]]}, {"org_code": "A\x00"},
    ])
    def test_refused(self, env, scope):
        with pytest.raises(ScopeError):
            resolve(env, "feed_x", scope)

    def test_context_without_scope_columns_refuses_any_scope(self, env):
        with pytest.raises(ScopeError):
            resolve(env, "expense", {"year": 2025})


class TestLegacyScope:
    def test_main_view_filtered_in_process(self, env):
        scoped = resolve(env, "revenue", {"year": 2025})
        a = scoped.adapter
        assert a.engine_name == "sqlite"
        assert a.execute_query("SELECT SUM(revenue) AS s, MIN(year) AS y FROM revenue_search") == [{"s": 6.0, "y": 2025}]
        with scoped.engine.connect() as conn:  # prompt side
            assert conn.execute(text("SELECT MIN(year) FROM revenue_search")).scalar() == 2025

    @pytest.mark.parametrize("sql", [
        "SELECT SUM(V) FROM revenue",                   # raw table behind the view
        "SELECT SUM(V) FROM v_other",                   # another context's view
        "SELECT SUM(revenue) FROM main.revenue_search",
        "SELECT name FROM sqlite_master",
        "SELECT * FROM pragma_table_info('revenue')",
    ])
    def test_anything_but_the_scoped_view_is_refused(self, env, sql):
        with pytest.raises(PermissionError):
            resolve(env, "revenue", {"year": 2025}).adapter.execute_query(sql)

    def test_every_other_table_is_shadowed_empty(self, env):
        """Defense in depth (review): even SQL that got past the gate would read nothing else."""
        with resolve(env, "revenue", {"year": 2025}).engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM revenue")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM v_other")).scalar() == 0
            assert conn.execute(text("SELECT SUM(revenue) FROM revenue_search")).scalar() == 6.0

    def test_goes_through_the_f4_validator(self, env):
        from app.services.database_adapter import execute_select
        out = execute_select(resolve(env, "revenue", {"year": 2025}).adapter, "DELETE FROM revenue")
        assert out["success"] is False


class TestQueryEngineScope:
    def _engine(self):
        from app.services import query_engine as qe
        admin_config = MagicMock()
        admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
        admin_config.get_feature_flags.return_value = {}
        admin_config.get_provider_record.return_value = None
        return qe, qe.QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)

    def test_scope_reaches_the_source_prompt_and_cache(self, env):
        from app.providers.base import QueryResult
        qe, engine = self._engine()
        qe._query_cache.clear()
        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        ai_service = MagicMock()
        ai_service.query_hybrid = AsyncMock(return_value=QueryResult(
            question="q", sql_query="SELECT 1", data=[{"n": 1}], explanation="", tokens_used=0, provider="matcha"))
        schema_cls = MagicMock()
        schema_cls.return_value.build_system_prompt.return_value = "prompt"
        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])

        def ask(scope):
            with patch.object(qe, "source_resolver", env), \
                 patch.object(qe.provider_registry, "create_provider", return_value=provider), \
                 patch.object(qe, "AIService", return_value=ai_service) as ai_cls, \
                 patch.object(qe, "SchemaService", schema_cls), \
                 patch.object(qe, "WarningDetector", return_value=warning_detector):
                qe._dedup_store.clear()
                asyncio.run(engine.query("q", context="revenue", scope=scope))
                return ai_cls

        ai_cls = ask({"year": 2025})
        bound = ai_cls.call_args.kwargs["mcp_client"]
        assert isinstance(bound, SourceBoundMCPClient) and bound._source.adapter.engine_name == "sqlite"
        assert "year = 2025" in ai_service.query_hybrid.call_args.kwargs["system_prompt"]
        ask({"year": 2025})
        assert ai_service.query_hybrid.await_count == 1  # same scope → cached
        ask({"year": 2024})
        assert ai_service.query_hybrid.await_count == 2  # another scope is another answer
        assert request_scope.get() is None  # reset after the request
        qe._query_cache.clear()
        qe._dedup_store.clear()


def test_contract_scope_columns_are_synced(tmp_path):
    from app.services.datafeed_knowledge import sync_knowledge
    config = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, display_name TEXT, "
                          "description TEXT, main_view TEXT, is_active BOOLEAN, priority INTEGER, keywords TEXT, "
                          "instruction_th TEXT, updated_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, description TEXT, "
                          "data_type TEXT, is_summable BOOLEAN, is_groupable BOOLEAN)"))
        conn.execute(text("CREATE TABLE vanna_documentation (doc_key TEXT, title TEXT, content TEXT, category TEXT, "
                          "context_name TEXT, is_active INTEGER)"))
    migrate(config)
    contract = {"domain": "x", "schema_version": "1", "primary_dataset": "f", "datasets": [],
                "scope_columns": {"year_month": "time_key"}}
    with config.begin() as conn:
        sync_knowledge(conn, "x", contract)
    with config.connect() as conn:
        assert json.loads(conn.execute(text("SELECT scope_columns FROM schema_contexts")).scalar()) == {"year_month": "time_key"}


class TestCteScoping:
    """Review finding (HIGH): a CTE inside a subquery legitimised an outer reference of the same
    name — scoped legacy SQL could read raw tables / sqlite_master. CTEs are lexically scoped now."""

    @pytest.mark.parametrize("sql", [
        "SELECT SUM(V) AS s FROM revenue WHERE 1 IN (WITH revenue AS (SELECT 1) SELECT * FROM revenue)",
        "SELECT SUM(V) AS s FROM v_other WHERE 1 IN (WITH v_other AS (SELECT 1) SELECT * FROM v_other)",
        "SELECT name, sql FROM sqlite_master WHERE 1 IN (WITH sqlite_master AS (SELECT 1) SELECT * FROM sqlite_master)",
        "SELECT * FROM (SELECT SUM(V) AS s FROM revenue) q, (WITH revenue AS (SELECT 1 AS x) SELECT x FROM revenue) r",
        "SELECT year FROM revenue_search GROUP BY year HAVING year IN "
        "(SELECT YEAR FROM revenue WHERE 1 IN (WITH revenue AS (SELECT 1) SELECT * FROM revenue))",
        "WITH x AS (SELECT * FROM revenue) SELECT SUM(V) FROM x",       # CTE body reads a raw table
        "WITH revenue AS (SELECT * FROM revenue) SELECT SUM(V) FROM revenue",  # non-recursive self-reference
        "WITH a AS (SELECT * FROM b), b AS (SELECT 1 AS x) SELECT * FROM a",   # a body can't see a later CTE
    ])
    def test_legacy_bypasses_refused(self, env, sql):
        from app.services.database_adapter import execute_select
        out = execute_select(resolve(env, "revenue", {"year": 2025}).adapter, sql)
        assert out["success"] is False and not out["data"]

    def test_file_source_bypass_refused(self, env):
        with pytest.raises(PermissionError):
            resolve(env, "feed_x", {"org_code": "A"}).adapter.execute_query(
                "SELECT SUM(revenue) FROM feed_x_fact_bu WHERE 1 IN (WITH feed_x_fact_bu AS (SELECT 1) SELECT * FROM feed_x_fact_bu)")
        with pytest.raises(PermissionError):  # unscoped gate had the same flaw (system views)
            env.for_context("feed_x").adapter.execute_query(
                "SELECT * FROM duckdb_settings WHERE 1 IN (WITH duckdb_settings AS (SELECT 1) SELECT * FROM duckdb_settings)")

    @pytest.mark.parametrize("sql,expected", [
        ("WITH a AS (SELECT year, revenue FROM revenue_search), b AS (SELECT SUM(revenue) AS s FROM a) SELECT s FROM b",
         [{"s": 6.0}]),
        ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT COUNT(*) AS c FROM r",
         [{"c": 3}]),
        ("SELECT (WITH t AS (SELECT revenue FROM revenue_search) SELECT SUM(revenue) FROM t) AS s", [{"s": 6.0}]),
        ("SELECT year FROM revenue_search UNION SELECT year FROM revenue_search", [{"year": 2025}]),
    ])
    def test_legit_ctes_still_work(self, env, sql, expected):
        assert resolve(env, "revenue", {"year": 2025}).adapter.execute_query(sql) == expected

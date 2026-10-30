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

from app.services.data_sources import (ScopeError, SourceBoundMCPClient, SourceResolver, plan_where_error,
                                       plan_where_unsafe, request_scope, scope_filters)
from scripts.migrate_data_sources import migrate
from tests.unit import knowledge_db

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
    knowledge_db.add_provenance(config)  # Plan 8.1 columns
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

    def test_a_key_declared_under_several_names_filters_each_table_on_its_own(self, env, tmp_path):
        # an org snapshot dates its rows by effective_month: with one name per key it was closed under every
        # period scope, and with it the way from a cost center to its organisation ("ค่าใช้จ่ายของน่าน", 2026-10-22)
        (tmp_path / "latest" / "dim_snap.csv").write_text(
            "effective_month,cost_center,unit\n202607,A,Nan\n202608,A,Nan\n202607,B,Phrae\n")
        snap = [{"name": "effective_month", "type": "BIGINT"}, {"name": "cost_center", "type": "VARCHAR"},
                {"name": "unit", "type": "VARCHAR"}]
        with env._engine().begin() as conn:
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) "
                              "VALUES (2, 'feed_x_dim_snap', 'dim_snap.csv', :c)"), {"c": json.dumps(snap)})
        join = ("SELECT SUM(f.revenue) AS s FROM feed_x_fact_org f JOIN feed_x_dim_snap d "
                "ON d.cost_center = f.cost_center AND d.effective_month = f.year_month WHERE d.unit = 'Nan'")
        with pytest.raises(PermissionError):  # one name: the snapshot is closed
            resolve(env, "feed_x", {"year_month": 202607}).adapter.execute_query(join)
        with env._engine().begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET scope_columns = :m WHERE name = 'feed_x'"),
                         {"m": json.dumps({"year_month": ["year_month", "effective_month"], "org_code": "cost_center"})})
        assert resolve(env, "feed_x", {"year_month": 202607}).adapter.execute_query(join) == [{"s": 10}]
        scoped = resolve(env, "feed_x", {"year_month": 202607, "org_code": "B"}).adapter
        assert scoped.execute_query(join) == [{"s": None}]  # Nan is org A: outside the scope
        assert scoped.execute_query("SELECT effective_month, cost_center FROM feed_x_dim_snap") == \
            [{"effective_month": 202607, "cost_center": "B"}]
        # a table with none of a key's names is still closed, and a malformed declaration is refused
        with pytest.raises(PermissionError):
            scoped.execute_query("SELECT * FROM feed_x_fact_bu")
        with env._engine().begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET scope_columns = '{\"year_month\": [\"year_month\", 7]}' "
                              "WHERE name = 'feed_x'"))
        with pytest.raises(ScopeError):
            resolve(env, "feed_x", {"year_month": 202607})

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
    knowledge_db.add_provenance(config)  # Plan 8.1 columns
    contract = {"domain": "x", "schema_version": "1", "primary_dataset": "f", "datasets": [],
                "scope_columns": {"year_month": "time_key"}}
    with config.begin() as conn:
        sync_knowledge(conn, "x", contract)
    with config.connect() as conn:
        assert json.loads(conn.execute(text("SELECT scope_columns FROM schema_contexts")).scalar()) == {"year_month": "time_key"}


# --- scope_plan_tables: a plan's targets are published for the year (portal, feed_sales, 2026-10-30) ---------
# The portal sends year_month = January last year … the report's month. A target table cut to those months gave
# "เป้า ม.ค.-ธ.ค. 2569" as nine months (2,169.67 vs 2,892.88 ล้านบาท) and the model called it the whole year.

TGT = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"}, {"name": "target", "type": "DOUBLE"}]
MIX = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"}, {"name": "metric", "type": "VARCHAR"},
       {"name": "amount", "type": "DOUBLE"}]
MAPPING = {"year_month": "year_month", "org_code": "cost_center"}
COLUMNS = {"tgt": ["year_month", "bu"], "mix": ["year_month", "metric"], "fact": ["year_month", "cost_center"]}
PLANS = {"tgt": None, "mix": "metric = 'target'"}


class TestPlanFilters:
    def test_a_plan_table_is_filtered_on_whole_years(self):
        f = scope_filters({"year_month": [202501, 202509, 202609]}, MAPPING, COLUMNS, PLANS)
        assert f["tgt"] == '("year_month" BETWEEN 202501 AND 202512 OR "year_month" BETWEEN 202601 AND 202612)'
        assert f["mix"] == ('(((metric = \'target\') AND ("year_month" BETWEEN 202501 AND 202512 OR "year_month" '
                            'BETWEEN 202601 AND 202612)) OR "year_month" IN (202501, 202509, 202609))')
        assert f["fact"] == '"year_month" IN (202501, 202509, 202609)'

    def test_one_month_opens_its_year(self):
        f = scope_filters({"year_month": 202609}, MAPPING, COLUMNS, PLANS)
        assert f["tgt"] == '("year_month" BETWEEN 202601 AND 202612)' and f["fact"] == '"year_month" = 202609'

    @pytest.mark.parametrize("plans", [None, {}])
    def test_without_plan_tables_nothing_changes(self, plans):
        scope = {"year_month": [202508, 202609]}
        assert scope_filters(scope, MAPPING, COLUMNS, plans) == scope_filters(scope, MAPPING, COLUMNS) == {
            t: '"year_month" IN (202508, 202609)' for t in COLUMNS}

    @pytest.mark.parametrize("value", [2026, [202609, 2026], 202613, "202609"])
    def test_a_value_that_is_not_yyyymm_opens_nothing(self, value):
        f = scope_filters({"year_month": value}, {"year_month": "year_month"}, {"tgt": ["year_month"]}, {"tgt": None})
        assert "BETWEEN" not in f["tgt"]

    def test_other_keys_still_filter_a_plan_table(self):
        f = scope_filters({"year_month": 202609, "org_code": "A"}, MAPPING,
                          {"tgt": ["year_month", "cost_center"], "mix": ["year_month"]}, PLANS)
        assert f == {"tgt": '"cost_center" = \'A\' AND ("year_month" BETWEEN 202601 AND 202612)'}

    @pytest.mark.parametrize("where", [
        "metric = 'target') OR (1=1", "1=1; DROP TABLE x", "metric IN (SELECT 1)", "metric = 'a' -- x",
        "metric = 'a' /* x */", "metric = 'x", "", None, 1])
    def test_a_where_that_could_leave_its_parentheses_is_unsafe(self, where):
        assert plan_where_unsafe(where)

    @pytest.mark.parametrize("where, ok", [
        ("metric = 'target'", True), ("metric = 'it''s; -- fine'", True), ("(metric = 'target') OR (amount > 0)", True),
        ("metric", False), ("amount", False), ("nope = 1", False), ("read_csv('x') IS NULL", False)])
    def test_a_declared_where_must_bind_as_one_boolean(self, where, ok):
        cols = {"year_month": "BIGINT", "metric": "VARCHAR", "amount": "DOUBLE"}
        assert (plan_where_error(where, cols) is None) is ok


@pytest.fixture
def plan_env(env, tmp_path):
    """feed_x with a target table (2025-12 … 2027-01) and a table of actuals to 202608 beside targets for 2026."""
    root = tmp_path / "latest"
    (root / "fact_tgt.csv").write_text("year_month,bu,target\n202512,1.X,5\n" + "".join(
        f"2026{m:02d},1.X,{m}\n" for m in range(1, 13)) + "202701,1.X,1000\n")
    (root / "fact_mix.csv").write_text("year_month,bu,metric,amount\n" + "".join(
        f"2026{m:02d},1.X,target,{m}\n" for m in range(1, 13)) + "202607,1.X,actual,70\n202608,1.X,actual,80\n")
    with env._engine().begin() as conn:
        for table, file, cols in (("feed_x_fact_tgt", "fact_tgt.csv", TGT), ("feed_x_fact_mix", "fact_mix.csv", MIX)):
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (2, :t, :f, :c)"),
                         {"t": table, "f": file, "c": json.dumps(cols)})
        conn.execute(text("UPDATE schema_contexts SET scope_plan_tables = :p WHERE name = 'feed_x'"), {"p": json.dumps(
            {"feed_x_fact_tgt": {}, "feed_x_fact_mix": {"where": "metric = 'target'"}})})
    return env


PORTAL = {"year_month": [202501 + i for i in range(12)] + [202601 + i for i in range(7)]}  # Jan 2025 … Jul 2026


class TestPlanTablesScope:
    def test_the_whole_year_of_targets_is_seen(self, plan_env):
        a = resolve(plan_env, "feed_x", PORTAL).adapter
        assert a.execute_query("SELECT SUM(target) AS s FROM feed_x_fact_tgt WHERE year_month BETWEEN 202601 AND 202612") \
            == [{"s": 78.0}]  # 1 + … + 12, not 1 + … + 7

    def test_actuals_stop_at_the_scope_month(self, plan_env):
        a = resolve(plan_env, "feed_x", PORTAL).adapter
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_mix WHERE metric = 'actual'") == [{"m": 202607}]
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_mix WHERE metric = 'target'") == [{"m": 202612}]
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_org") == [{"m": 202607}]
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_bu") == [{"m": 202607}]

    def test_a_year_outside_the_scope_stays_unseen(self, plan_env):
        a = resolve(plan_env, "feed_x", PORTAL).adapter
        assert a.execute_query("SELECT MIN(year_month) AS lo, MAX(year_month) AS hi FROM feed_x_fact_tgt") == \
            [{"lo": 202512, "hi": 202612}]  # 2027's target is next year's plan
        assert a.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_tgt WHERE year_month >= 202701") == [{"n": 0}]

    def test_an_org_scope_still_closes_a_target_table_without_an_org_column(self, plan_env):
        a = resolve(plan_env, "feed_x", {**PORTAL, "org_code": "A"}).adapter
        with pytest.raises(PermissionError):
            a.execute_query("SELECT SUM(target) FROM feed_x_fact_tgt")

    def test_the_model_is_told(self, plan_env):
        from app.services.data_sources import request_plan_tables
        token = request_scope.set(PORTAL)
        try:
            note = plan_env.for_context("feed_x").adapter.scope_note
            assert request_plan_tables.get() == {"feed_x_fact_tgt": None, "feed_x_fact_mix": "metric = 'target'"}
        finally:
            request_scope.reset(token)
        assert "feed_x_fact_mix (เฉพาะแถวที่ metric = 'target'); feed_x_fact_tgt" in note
        assert "ครบ 12 เดือน**ของปี 2025 (พ.ศ. 2568), 2026 (พ.ศ. 2569)" in note
        assert "ยอดจริงมีถึง 202607" in note and "ห้ามเรียกว่า \"ทั้งปี\"" in note

    def test_no_declaration_means_the_months_as_before(self, plan_env):
        with plan_env._engine().begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET scope_plan_tables = NULL"))
        a = resolve(plan_env, "feed_x", PORTAL).adapter
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_tgt") == [{"m": 202607}]
        assert "ตารางเป้า" not in a.scope_note

    @pytest.mark.parametrize("declared", [
        '{"feed_x_fact_mix": {"where": "metric = \'target\') OR (1=1"}}', '{"feed_x_fact_mix": {"when": "x"}}',
        '{"feed_x_fact_mix": 1}', '["feed_x_fact_mix"]', "not json"])
    def test_a_bad_entry_opens_nothing(self, plan_env, declared):
        with plan_env._engine().begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET scope_plan_tables = :p"), {"p": declared})
        a = resolve(plan_env, "feed_x", PORTAL).adapter
        assert a.execute_query("SELECT MAX(year_month) AS m FROM feed_x_fact_mix") == [{"m": 202607}]


    def test_the_note_reaches_the_ai_call_and_is_reset_after(self, plan_env):
        """The resolver sets request_plan_tables; pass 1 / pass 2 read it through hybrid_flow.scope_note()."""
        from app.providers.base import QueryResult
        from app.services.ai import hybrid_flow
        from app.services.data_sources import request_plan_tables
        qe, engine = TestQueryEngineScope()._engine()
        seen = []

        async def query_hybrid(**kwargs):
            seen.append(hybrid_flow.scope_note())
            return QueryResult(question="q", sql_query="SELECT 1", data=[{"n": 1}], explanation="", tokens_used=0,
                               provider="matcha")

        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        ai_service = MagicMock()
        ai_service.query_hybrid = AsyncMock(side_effect=query_hybrid)
        schema_cls = MagicMock()
        schema_cls.return_value.build_system_prompt.return_value = "prompt"
        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])
        with patch.object(qe, "source_resolver", plan_env), \
             patch.object(qe.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe, "AIService", return_value=ai_service), \
             patch.object(qe, "SchemaService", schema_cls), \
             patch.object(qe, "WarningDetector", return_value=warning_detector):
            qe._query_cache.clear()
            qe._dedup_store.clear()
            asyncio.run(engine.query("เป้าทั้งปี", context="feed_x", scope=PORTAL))
            qe._query_cache.clear()
            qe._dedup_store.clear()
        assert len(seen) == 1 and "ตารางเป้า/แผน** feed_x_fact_mix" in seen[0]
        assert request_plan_tables.get() is None

def test_contract_plan_tables_are_synced(tmp_path, caplog):
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
    knowledge_db.add_provenance(config)
    cols = [{"name": "year_month", "dtype": "Int64"}, {"name": "metric", "dtype": "string"},
            {"name": "amount", "dtype": "double"}]
    contract = {"domain": "x", "schema_version": "1", "primary_dataset": "f", "scope_columns": {"year_month": "year_month"},
                "datasets": [{"name": "f", "columns": cols}, {"name": "tgt", "columns": cols},
                             {"name": "dim", "columns": [{"name": "bu", "dtype": "string"}]}],
                "scope_plan_tables": {"tgt": {}, "f": {"where": "metric = 'target'"}, "dim": {}, "nope": {},
                                      "bad": {"where": "metric"}}}
    contract["datasets"].append({"name": "bad", "columns": cols})

    def stored():
        with config.connect() as conn:
            raw = conn.execute(text("SELECT scope_plan_tables FROM schema_contexts")).scalar()
        return raw and json.loads(raw)

    with config.begin() as conn:
        sync_knowledge(conn, "x", contract)
    assert stored() == {"feed_x_tgt": {}, "feed_x_f": {"where": "metric = 'target'"}}  # dim / nope / bad left out
    assert {"scope_plan_tables.dim", "scope_plan_tables.nope", "scope_plan_tables.bad"} <= {
        r.getMessage().split(" of ")[0] for r in caplog.records}
    del contract["scope_plan_tables"]  # the contract withdraws it: so does the context
    with config.begin() as conn:
        sync_knowledge(conn, "x", contract)
    assert stored() is None


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


class TestPinnedForRestrictedKeys:
    """Plan 7 Phase 4a (review): for a key bound to a workspace/allowlist, a legacy context is its
    main view and nothing else — until now only the prompt said so, and an unknown context fell
    back to the whole legacy DB."""

    def _pinned(self, resolver, context, scope=None):
        from app.services.data_sources import request_pinned

        pin, tok = request_pinned.set(True), request_scope.set(scope)
        try:
            return resolver.for_context(context)
        finally:
            request_scope.reset(tok)
            request_pinned.reset(pin)

    def test_legacy_context_reads_its_main_view_only(self, env):
        source = self._pinned(env, "expense")  # main view v_other
        assert source.adapter.execute_query("SELECT COUNT(*) AS n FROM v_other") == [{"n": 3}]
        for sql in ("SELECT SUM(revenue) FROM revenue_search",  # another context's view
                    "SELECT SUM(V) FROM revenue", "SELECT name FROM sqlite_master"):
            with pytest.raises(PermissionError):
                source.adapter.execute_query(sql)
        with source.engine.connect() as conn:  # and behind the gate the others are empty
            assert conn.execute(text("SELECT COUNT(*) FROM revenue_search")).scalar() == 0
        assert "v_other" in source.adapter.scope_note

    @pytest.mark.parametrize("context", ["nope", "expense ", "Expense", None, ""])
    def test_a_context_that_does_not_resolve_is_refused_not_served_from_the_legacy_db(self, env, context):
        from app.services.workspaces import ContextNotAllowed

        with pytest.raises(ContextNotAllowed):
            self._pinned(env, context)

    def test_scope_and_file_sources_are_as_before(self, env):
        scoped = self._pinned(env, "revenue", {"year": 2025})
        assert scoped.adapter.execute_query("SELECT SUM(revenue) AS s FROM revenue_search") == [{"s": 6.0}]
        assert self._pinned(env, "feed_x").adapter.engine_name == "duckdb"  # its views are the allowlist already

    def test_unrestricted_callers_are_untouched(self, env):
        assert env.for_context("expense").adapter is None and env.for_context("nope").adapter is None

    def test_the_engine_pins_restricted_requests(self, env):
        from app.services.data_sources import request_pinned
        from app.services import query_engine as qe

        seen = {}

        async def fake(self, *args, **kwargs):
            seen["pinned"] = request_pinned.get()
            return "done"

        with patch.object(qe.QueryEngine, "_query", fake):
            engine = qe.QueryEngine(mcp_client=MagicMock(), admin_config=MagicMock())
            asyncio.run(engine.query("q", allowed_contexts=frozenset({"expense"})))
            assert seen["pinned"] is True
            asyncio.run(engine.query("q"))
            assert seen["pinned"] is False and request_pinned.get() is False

"""
Plan 7 Phase 4.5 — llm_data_policy per source, enforced at the provider layer.

The trap: every value in the test source is a sentinel; the provider's HTTP boundary (httpx) is faked
and records every request. Under schema_only no request may carry a sentinel — through the whole
QueryEngine pipeline, and for a caller that hands rows to the provider directly.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.core import llm_policy
from app.core.llm_policy import (AGGREGATED_ONLY, FULL, SCHEMA_ONLY, LLMPolicyError, PolicyMCPClient,
                                 RequestPolicy, request_llm_policy)
from app.providers.matcha_provider import MatchaProvider
from app.services.data_sources import SourceResolver, policy_for_table
from scripts.migrate_data_sources import migrate
from tests.unit import knowledge_db

S_DIV, S_DIV2, S_NUM, S_LOOKUP, S_ANSWER = "ZQXDIVALPHA", "ZQXDIVBETA", 918273645.55, "ZQXLOOKUP", "ZQXANSWER 777123"
SENTINELS = (S_DIV, S_DIV2, "918273645", S_LOOKUP, S_ANSWER)
COLUMNS = [{"name": "year_month", "type": "BIGINT"}, {"name": "division", "type": "VARCHAR"},
           {"name": "revenue", "type": "DOUBLE"}]
SQL = "SELECT division, revenue FROM feed_x_fact"


class FakeLLM:
    """Stands in for httpx.AsyncClient: records every request body, answers like the gateway."""

    def __init__(self):
        self.requests = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.requests.append(json)
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": f"```sql\n{SQL}\n```\nคำอธิบาย"}}],
                                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return response

    def sent(self) -> str:
        return json.dumps(self.requests, ensure_ascii=False, default=str)


@pytest.fixture
def fake_llm():
    fake = FakeLLM()
    with patch("app.providers.matcha_provider.httpx.AsyncClient", fake):
        yield fake


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "latest"
    root.mkdir()
    (root / "fact.csv").write_text(f"year_month,division,revenue\n202607,{S_DIV},{S_NUM}\n202607,{S_DIV2},{S_NUM}\n")
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, main_view TEXT, "
                          "display_name TEXT, is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_contexts (name, main_view, display_name) VALUES ('feed_x', 'feed_x_fact', 'X')"))
        conn.execute(text("CREATE TABLE master_hierarchy (context_name TEXT, level INT, level_label_th TEXT, "
                          "level_columns TEXT, is_active BOOLEAN)"))
    migrate(config)
    knowledge_db.add_provenance(config)  # Plan 8.1 columns
    with config.begin() as conn:
        conn.execute(text("INSERT INTO data_sources (name, source_type, root_path) VALUES ('df_x', 'duckdb_file', :r)"),
                     {"r": str(root)})
        conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (2, 'feed_x_fact', "
                          "'fact.csv', :c)"), {"c": json.dumps(COLUMNS)})
        conn.execute(text("UPDATE schema_contexts SET source_id = 2"))
    monkeypatch.setattr("app.db.session.config_engine", config)
    return config, SourceResolver(config_engine=config, cache_dir=str(tmp_path / "cache"))


def set_policy(config, policy, providers=None):
    with config.begin() as conn:
        conn.execute(text("UPDATE data_sources SET llm_data_policy = :p, llm_provider_allowlist = :a WHERE name = 'df_x'"),
                     {"p": policy, "a": providers})


def ask(resolver, history=None, mode="hybrid", provider=None, flags=None):
    """One question through the real QueryEngine → AIService → MatchaProvider; only httpx and MCP are fake."""
    from app.services import query_engine as qe
    from app.services.ai import hierarchy_context
    from app.services.schema.service import SchemaService

    qe._query_cache.clear()
    qe._dedup_store.clear()
    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha", "matcha_api_url": "http://llm.test"}
    admin_config.get_feature_flags.return_value = {"value_verification_enabled": False, **(flags or {})}
    admin_config.get_provider_record.return_value = None
    mcp = MagicMock()
    mcp.servers = {"nt-query": object()}
    mcp.call_tool = AsyncMock(return_value=json.dumps({"valid": True}))
    mcp.get_tools = AsyncMock(return_value=[])
    warning_detector = MagicMock()
    warning_detector.detect = AsyncMock(return_value=[])
    lookup = [{"keyword": "x", "column_name": "division", "column_value": S_LOOKUP, "table_name": "feed_x_fact"}]
    engine = qe.QueryEngine(mcp_client=mcp, admin_config=admin_config)
    # hermetic: only matcha has a key here, whatever the developer's .env holds
    kwargs = lambda name, *a, **k: {"api_key": "k" if name == "matcha" else "", "api_url": "http://llm.test", "model": "m"}  # noqa: E731
    with patch.object(qe, "source_resolver", resolver), \
         patch.object(qe, "_build_provider_kwargs", kwargs), \
         patch("app.services.data_sources.source_resolver", resolver), \
         patch.object(qe, "WarningDetector", return_value=warning_detector), \
         patch.object(qe, "workspace_of_context", return_value=None), \
         patch.object(hierarchy_context, "extract_keywords_from_question", return_value=["x"]), \
         patch.object(SchemaService, "search_keyword_index", return_value=lookup):
        return asyncio.run(engine.query("รายได้แยกตามสายงาน", context="feed_x", history=history, mode=mode,
                                        provider=provider, provider_kwargs={"api_key": "k"}))


HISTORY = [{"role": "user", "content": "ก่อนหน้า"},
           {"role": "assistant", "content": f"```sql\nSELECT 1\n```\n\n{S_ANSWER}"}]


class TestSchemaOnlyPipeline:
    def test_full_is_unchanged_and_the_trap_sees_the_values(self, env, fake_llm):
        """The trap works: under `full` (every source before Phase 4.5) the same run does carry the values."""
        _config, resolver = env
        result = ask(resolver, history=HISTORY)
        assert result.query_result.data and result.llm_policy == FULL
        sent = fake_llm.sent()
        for sentinel in SENTINELS:  # sample values + result rows, result numbers, value lookup, chat history
            assert sentinel in sent, sentinel

    def test_schema_only_sends_no_value_in_any_request(self, env, fake_llm):
        config, resolver = env
        set_policy(config, SCHEMA_ONLY)
        result = ask(resolver, history=HISTORY)
        assert [row["division"] for row in result.query_result.data] == [S_DIV, S_DIV2]  # the caller still gets its rows
        assert result.llm_policy == SCHEMA_ONLY
        assert fake_llm.requests, "SQL generation still goes to the provider"
        sent = fake_llm.sent()
        assert "feed_x_fact" in sent and "division" in sent and "รายได้แยกตามสายงาน" in sent  # schema + question
        for sentinel in SENTINELS:
            assert sentinel not in sent, sentinel
        assert len(fake_llm.requests) == 1  # no explanation request at all
        assert "2" in str(result.query_result.explanation)  # told without the LLM

    def test_rag_context_is_not_retrieved(self, env, fake_llm):
        """The brain holds golden SQL generated from the source's control totals (real group codes/labels)."""
        golden = {"ddl": [], "doc": [f"กลุ่ม {S_DIV2}"], "sql": [f"SELECT SUM(revenue) FROM feed_x_fact WHERE division = '{S_DIV}'"]}
        vanna = MagicMock()
        vanna.get_rag_context.return_value = golden
        config, resolver = env
        with patch("app.services.ai.service.VannaService", MagicMock(return_value=vanna)):
            ask(resolver)
            assert S_DIV in json.dumps(fake_llm.requests[0], ensure_ascii=False)  # full: retrieved, as before
            fake_llm.requests.clear()
            set_policy(config, SCHEMA_ONLY)
            ask(resolver)
        assert fake_llm.requests and S_DIV not in fake_llm.sent() and S_DIV2 not in fake_llm.sent()

    def test_intent_of_an_earlier_turn_is_not_carried_in(self, env, fake_llm):
        """intent_state is keyed by conversation only: turn 1 on a `full` source may have stored looked-up values."""
        from app.services.ai import intent_state

        config, resolver = env
        set_policy(config, SCHEMA_ONLY)
        flags = {"two_pass_enabled": True, "intent_state_enabled": True}
        stored = {"intent_type": "lookup", "metrics": [], "filters": [{"column": "division", "operator": "=", "value": S_LOOKUP}]}
        with patch.object(intent_state, "get_intent", return_value=stored), patch.object(intent_state, "set_intent"):
            ask(resolver, history=HISTORY, flags=flags)
            assert fake_llm.requests and S_LOOKUP not in fake_llm.sent()
            fake_llm.requests.clear()
            set_policy(config, FULL)
            ask(resolver, history=HISTORY, flags=flags)
        assert S_LOOKUP in json.dumps(fake_llm.requests[0], ensure_ascii=False)  # full: carried, as before

    def test_two_pass_sends_no_value_either(self, env, fake_llm):
        config, resolver = env
        set_policy(config, SCHEMA_ONLY)
        ask(resolver, history=HISTORY, flags={"two_pass_enabled": True})
        assert fake_llm.requests
        for sentinel in SENTINELS:
            assert sentinel not in fake_llm.sent(), sentinel

    def test_unreadable_policy_is_the_strictest(self, env, fake_llm):
        config, resolver = env
        for broken in (None, "everything"):
            fake_llm.requests.clear()
            set_policy(config, broken)
            assert ask(resolver).llm_policy == SCHEMA_ONLY
            assert S_DIV not in fake_llm.sent()

    def test_tool_loop_is_refused(self, env, fake_llm):
        config, resolver = env
        set_policy(config, SCHEMA_ONLY)
        with pytest.raises(LLMPolicyError):
            ask(resolver, mode="mcp")
        assert fake_llm.requests == []

    def test_policy_change_invalidates_the_cached_answer(self, env, fake_llm):
        from app.services import query_engine as qe
        config, resolver = env
        ask(resolver)
        set_policy(config, SCHEMA_ONLY)
        engine = qe.QueryEngine(mcp_client=MagicMock(), admin_config=MagicMock())
        key = next(iter(qe._query_cache))
        with patch.object(qe, "source_resolver", resolver):
            cached = qe._cache_get(key)
            policy, _ = qe._source_policy(resolver.for_context(cached.context_name))
        assert cached.llm_policy == FULL and policy == SCHEMA_ONLY  # _query treats the mismatch as a miss
        engine.close()


class TestAggregatedOnly:
    def test_detail_rows_stay_in_and_aggregates_may_be_explained(self, env, fake_llm):
        config, resolver = env
        set_policy(config, AGGREGATED_ONLY)
        ask(resolver)
        assert len(fake_llm.requests) == 1 and S_DIV not in fake_llm.sent()  # SELECT division, revenue = detail rows

        fake_llm.requests.clear()
        aggregate = "SELECT division, SUM(revenue) AS total FROM feed_x_fact GROUP BY division"
        with patch(f"{__name__}.SQL", aggregate):
            ask(resolver)
        assert len(fake_llm.requests) == 2 and S_DIV in json.dumps(fake_llm.requests[1], ensure_ascii=False)
        assert S_DIV not in json.dumps(fake_llm.requests[0], ensure_ascii=False)  # still no samples / lookup

    def test_aggregate_detection(self):
        assert llm_policy.is_aggregate_sql("select a, sum(b) from t group by a")
        assert llm_policy.is_aggregate_sql("SELECT COUNT (*) FROM t")
        assert not llm_policy.is_aggregate_sql("SELECT name, salary FROM t")
        assert not llm_policy.is_aggregate_sql("SELECT MAX(salary) FROM t")  # one person's real value
        assert not llm_policy.is_aggregate_sql("SELECT name, salary, COUNT(*) OVER () FROM t")  # detail rows + a window
        assert not llm_policy.is_aggregate_sql("SELECT t.*, (SELECT SUM(x) FROM o) AS total FROM t")
        assert not llm_policy.is_aggregate_sql("select * from (select a, sum(b) from t group by a)")
        assert not llm_policy.is_aggregate_sql(None)


def under(policy, providers=None, question=""):
    return request_llm_policy.set(RequestPolicy(policy=policy, providers=providers, source="df_x", question=question))


class TestProviderLayer:
    """A caller that forgot the policy: whatever it hands the provider, nothing leaves."""

    ROWS = [{"division": S_DIV, "revenue": S_NUM}]

    def test_explain_result_called_directly(self, fake_llm):
        provider = MatchaProvider("k", "http://llm.test")
        token = under(SCHEMA_ONLY)
        try:
            explanation = asyncio.run(provider.explain_result("q", SQL, self.ROWS, "sys"))
        finally:
            request_llm_policy.reset(token)
        assert fake_llm.requests == [] and explanation
        asyncio.run(provider.explain_result("q", SQL, self.ROWS, "sys"))  # no policy in force = as before
        assert S_DIV in fake_llm.sent()

    def test_every_subclass_is_guarded(self, fake_llm):
        from app.providers.base import AIProvider
        from app.providers.registry import provider_registry

        class Later(AIProvider):  # a provider added after Phase 4.5 knows nothing about the policy
            name = "later"
            sent = []

            async def generate_sql(self, question, system_prompt, tools, history=[]):
                self.sent.append(question)

            async def explain_result(self, question, sql, data, system_prompt, **kwargs):
                self.sent.append(data)

            async def generate_content(self, prompt, system_prompt=None, history=None):
                self.sent.append((prompt, history))

        for cls in [Later, *provider_registry.providers.values()]:
            for method in ("generate_sql", "explain_result", "generate_content", "generate_structured"):
                if method in cls.__dict__:
                    assert getattr(cls.__dict__[method], "_llm_guarded", False), (cls.__name__, method)
        token = under(SCHEMA_ONLY)
        try:
            asyncio.run(Later().explain_result("q", SQL, self.ROWS, "sys"))
            with pytest.raises(LLMPolicyError):
                asyncio.run(Later().generate_sql("q", "sys", []))
            asyncio.run(Later().generate_content("p", history=HISTORY))
        finally:
            request_llm_policy.reset(token)
        assert Later.sent == [("p", [HISTORY[0], {"role": "assistant", "content": "```sql\nSELECT 1\n```"}])]

    def test_rows_read_in_the_request_cannot_be_put_in_a_prompt(self, fake_llm):
        inner = MagicMock()
        inner.call_tool = AsyncMock(return_value=json.dumps({"success": True, "data": self.ROWS}))
        provider = MatchaProvider("k", "http://llm.test")

        async def forgetful_caller():
            rows = json.loads(await PolicyMCPClient(inner).call_tool("execute_query", {"sql": SQL}))["data"]
            await provider.generate_content(f"สรุปให้หน่อย: {rows}")

        token = under(SCHEMA_ONLY)
        try:
            with pytest.raises(LLMPolicyError):
                asyncio.run(forgetful_caller())
        finally:
            request_llm_policy.reset(token)
        assert fake_llm.requests == []

    def test_execution_error_loses_its_literals(self):
        inner = MagicMock()
        inner.call_tool = AsyncMock(return_value=json.dumps(
            {"success": False, "error": f"Conversion Error: Could not convert string '{S_DIV}' to INT32 (918273645.55)"}))
        token = under(SCHEMA_ONLY)
        try:
            result = asyncio.run(PolicyMCPClient(inner).call_tool("execute_query", {"sql": SQL}))
        finally:
            request_llm_policy.reset(token)
        assert S_DIV not in result and "918273645" not in result and "Conversion Error" in result

    def test_value_verifier_gives_no_hint(self):
        from app.services.value_verifier import ValueVerifier
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(return_value=json.dumps({"success": True, "data": [{"division": S_DIV}]}))
        token = under(SCHEMA_ONLY)
        try:
            result = asyncio.run(ValueVerifier(mcp, "feed_x_fact").verify("SELECT 1 FROM feed_x_fact WHERE division = 'x'", "q"))
        finally:
            request_llm_policy.reset(token)
        assert not result.needs_retry and not result.hint_text and mcp.call_tool.await_count == 0


class TestProviderAllowlist:
    def test_provider_outside_the_allowlist(self, env, fake_llm):
        config, resolver = env
        set_policy(config, FULL, '["claude"]')
        with pytest.raises(LLMPolicyError):  # named by the caller → refused, never switched silently
            ask(resolver, provider="matcha")
        with pytest.raises(LLMPolicyError):  # default provider not allowed and the allowed one isn't configured
            ask(resolver)
        assert fake_llm.requests == []
        set_policy(config, FULL, '["matcha"]')
        assert ask(resolver).provider_used == "matcha" and fake_llm.requests

    def test_guard_refuses_even_if_the_engine_was_bypassed(self, fake_llm):
        token = under(FULL, providers=frozenset({"claude"}))
        try:
            with pytest.raises(LLMPolicyError):
                asyncio.run(MatchaProvider("k", "http://llm.test").generate_content("p"))
        finally:
            request_llm_policy.reset(token)
        assert fake_llm.requests == []

    def test_broken_allowlist_allows_nobody(self):
        assert llm_policy.parse_allowlist(None) is None
        assert llm_policy.parse_allowlist('["matcha"]') == frozenset({"matcha"})
        assert llm_policy.parse_allowlist("matcha") == frozenset() == llm_policy.parse_allowlist('{"a": 1}')


class TestRegistry:
    def test_migration_keeps_every_existing_source_full_and_is_idempotent(self, env):
        config, resolver = env
        migrate(config)
        with config.connect() as conn:
            assert {r[0] for r in conn.execute(text("SELECT llm_data_policy FROM data_sources"))} == {FULL}
        assert resolver.for_context("feed_x").llm_data_policy == FULL

    def test_policy_for_table(self, env):
        config, _ = env
        assert policy_for_table("feed_x_fact", config) == FULL and policy_for_table("revenue_search", config) == FULL
        set_policy(config, AGGREGATED_ONLY)
        assert policy_for_table("feed_x_fact", config) == AGGREGATED_ONLY
        assert policy_for_table("revenue_search", config) == FULL  # the legacy source has its own policy
        with config.begin() as conn:
            conn.execute(text("UPDATE data_sources SET llm_data_policy = 'schema_only' WHERE name = 'legacy'"))
        assert policy_for_table("revenue_search", config) == SCHEMA_ONLY

    def test_registry_without_the_columns_behaves_as_before(self, tmp_path):
        config = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
        with config.begin() as conn:
            conn.execute(text("CREATE TABLE data_sources (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN)"))
            conn.execute(text("CREATE TABLE source_tables (source_id INT, table_name TEXT, is_active BOOLEAN)"))
            conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT)"))
        assert policy_for_table("anything", config) == FULL

    def test_an_engine_that_is_not_the_config_db_is_unreadable_not_unmigrated(self, tmp_path):
        """SchemaService's standalone fallback hands over the business DB: no registry there ≠ nobody restricted."""
        from app.services.data_sources import policy_for_context

        business = create_engine(f"sqlite:///{tmp_path / 'biz.sqlite'}")
        with business.begin() as conn:
            conn.execute(text("CREATE TABLE revenue (v REAL)"))
        assert policy_for_table("revenue", business) == SCHEMA_ONLY == policy_for_context("revenue", business)


class TestValuesAreNotCopiedOutOfARestrictedSource:
    """Phase 4.5 item 7: onboarding, admin schema pages, keyword index and hierarchy lookup obey the same policy."""

    @pytest.fixture
    def legacy(self, tmp_path, monkeypatch):
        biz = tmp_path / "biz.sqlite"
        engine = create_engine(f"sqlite:///{biz}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE v_x (division TEXT, year INT, month INT, amount REAL)"))
            conn.execute(text("INSERT INTO v_x VALUES (:a, 2026, 1, :n), (:b, 2026, 2, :n)"), {"a": S_DIV, "b": S_DIV2, "n": S_NUM})
        config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
        with config.begin() as conn:
            conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, main_view TEXT, is_active BOOLEAN DEFAULT 1)"))
            conn.execute(text("INSERT INTO schema_contexts (name, main_view) VALUES ('x', 'v_x')"))
            conn.execute(text("CREATE TABLE keyword_value_index (keyword TEXT, column_name TEXT, column_value TEXT, "
                              "table_name TEXT, context_name TEXT)"))
        migrate(config)
        monkeypatch.setattr("app.db.session.config_engine", config)
        return str(biz), engine, config

    @staticmethod
    def tighten(config, policy=SCHEMA_ONLY):
        with config.begin() as conn:
            conn.execute(text("UPDATE data_sources SET llm_data_policy = :p WHERE name = 'legacy'"), {"p": policy})

    def test_onboarding_inspection_carries_no_value(self, legacy):
        from app.services.context_onboarding import DataInspector, LLMAnalyzer

        biz, _engine, config = legacy
        full = json.dumps(DataInspector(biz).inspect("v_x").to_dict(), ensure_ascii=False, default=str)
        assert S_DIV in full and "918273645" in full  # as before for a `full` source
        self.tighten(config)
        inspection = DataInspector(biz).inspect("v_x")
        told = json.dumps(inspection.to_dict(), ensure_ascii=False, default=str)
        assert "division" in told and '"row_count": 2' in told  # the structure is still there to work with
        prompt = LLMAnalyzer(biz).build_prompt(inspection)
        for sentinel in (S_DIV, S_DIV2, "918273645"):
            assert sentinel not in told and sentinel not in prompt, sentinel

    def test_sample_values_for_admin_pages(self, legacy):
        from app.services.schema.service import SchemaService

        _biz, engine, config = legacy
        service = SchemaService(db_engine=config, business_engine=engine)
        assert S_DIV in service.get_sample_values("v_x")["division"]
        self.tighten(config, AGGREGATED_ONLY)
        assert service.get_sample_values("v_x") == {}  # suggest-mappings / dimension-families get nothing to send

    def test_keyword_index_is_not_built_and_is_emptied(self, legacy):
        from app.services.schema import keyword_index
        from app.services.schema.service import SchemaService

        _biz, engine, config = legacy
        service = SchemaService(db_engine=config, business_engine=engine)
        with patch.object(keyword_index, "get_searchable_columns", return_value=["division"]):
            assert keyword_index.build_keyword_index(service, "x", "v_x") > 0
            self.tighten(config)
            assert keyword_index.build_keyword_index(service, "x", "v_x") == 0
        with config.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM keyword_value_index")).scalar() == 0

    def test_tightening_through_the_api_empties_the_index_at_once(self, legacy):
        from sqlalchemy.orm import sessionmaker

        from app.api.v1.admin import sources as api

        _biz, _engine, config = legacy
        with config.begin() as conn:
            conn.execute(text("INSERT INTO keyword_value_index VALUES ('k', 'division', :v, 'v_x', 'x')"), {"v": S_DIV})
        db = sessionmaker(bind=config)()
        with patch.object(api, "clear_query_cache"):
            done = api.set_source_policy("legacy", api.SourcePolicyRequest(llm_data_policy="schema_only"), MagicMock(), db)
        assert done["keyword_index_rows_removed"] == 1

    def test_policy_for_context(self, legacy):
        from app.services.data_sources import policy_for_context

        _biz, _engine, config = legacy
        assert policy_for_context("x", config) == FULL and policy_for_context("unknown", config) == FULL
        self.tighten(config)
        assert policy_for_context("x", config) == SCHEMA_ONLY
        assert policy_for_context("unknown", config) == SCHEMA_ONLY  # an unbound context reads the legacy DB

"""
Plan 7 Phase 5 — questions across several contexts (app/services/multi_context.py).

The orchestrator is a caller that holds the results of several sources at once: the tests below pin
what it may never do — reach a context outside the allowlist / the workspace, make a provider call
outside a policy, let a value of a restricted source reach a provider, compute across parts that
failed or stand at different periods, or answer as if complete when a part is missing.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.core.llm_policy import FULL, SCHEMA_ONLY, LLMPolicyError
from app.providers.base import QueryResult
from app.core import outbound
from app.services import multi_context as mc
from app.services.data_sources import ScopeError, SourceResolver
from app.services.query_engine import QueryEngineResult
from app.services.workspaces import ContextNotAllowed
from scripts.migrate_data_sources import migrate
from tests.unit import knowledge_db

WORKSPACES = {1: "default", 2: "nt-report"}
CONTEXTS = [
    {"name": "revenue", "workspace_id": 1, "keywords": ["รายได้", "กำไร"]},
    {"name": "expense", "workspace_id": None, "keywords": ["ค่าใช้จ่าย"]},  # NULL = default
    {"name": "feed_revenue", "workspace_id": 2, "display_name": "Feed revenue", "keywords": ["รายได้", "feed", "dashboard"]},
    {"name": "feed_expense", "workspace_id": 2, "display_name": "Feed expense", "keywords": ["ค่าใช้จ่าย", "feed", "dashboard"]},
    {"name": "feed_ebt", "workspace_id": 2, "keywords": ["ebt", "กำไร", "feed", "dashboard"]},
]
NT = frozenset({"nt-report"})


def names(found):
    return [c["name"] for c in found]


class TestCandidates:
    def test_two_contexts_with_their_own_keyword(self):
        assert names(mc.candidates("รายได้และค่าใช้จ่ายเดือนนี้", CONTEXTS, None, WORKSPACES, NT)) == ["feed_revenue", "feed_expense"]

    def test_shared_markers_do_not_make_a_question_multi_context(self):
        assert mc.candidates("รายได้ feed dashboard ล่าสุด", CONTEXTS, None, WORKSPACES, NT) == []

    def test_workspace_that_is_not_enabled(self):
        assert mc.candidates("รายได้และค่าใช้จ่าย", CONTEXTS, None, WORKSPACES, frozenset()) == []

    def test_never_across_workspaces(self):
        """'รายได้' of default + 'ebt' of nt-report: no workspace has two candidates."""
        contexts = [c for c in CONTEXTS if c["name"] in ("revenue", "feed_ebt")]
        assert mc.candidates("รายได้และ ebt", contexts, None, WORKSPACES, frozenset({"default", "nt-report"})) == []

    def test_context_outside_the_allowlist_is_not_a_candidate(self):
        allowed = frozenset({"feed_revenue", "feed_ebt"})
        assert mc.candidates("รายได้และค่าใช้จ่าย", CONTEXTS, allowed, WORKSPACES, NT) == []
        assert names(mc.candidates("รายได้ ค่าใช้จ่าย และ ebt", CONTEXTS, allowed, WORKSPACES, NT)) == ["feed_revenue", "feed_ebt"]

    def test_unreadable_flag_is_off(self):
        config = MagicMock()
        for raw in ("", "not json", '"nt-report"', None):
            config.get_config.return_value = raw
            assert mc.enabled_workspaces(config) == frozenset()
        config.get_config.return_value = '["nt-report"]'
        assert mc.enabled_workspaces(config) == NT


class TestParseSplit:
    NAMES = ["feed_revenue", "feed_expense"]

    def test_valid(self):
        raw = {"parts": [{"context": "feed_revenue", "question": "รายได้"}, {"context": "feed_expense", "question": "ค่าใช้จ่าย"}],
               "operation": "ratio", "operands": [0, 1]}
        assert mc.parse_split(raw, self.NAMES) == {"parts": [("feed_revenue", "รายได้"), ("feed_expense", "ค่าใช้จ่าย")],
                                                   "operation": "ratio", "operands": [0, 1]}
        assert mc.parse_split("```json\n" + json.dumps(raw) + "\n```", self.NAMES)["operation"] == "ratio"

    @pytest.mark.parametrize("parts", [
        [{"context": "feed_sales", "question": "x"}, {"context": "feed_revenue", "question": "y"}],  # not a candidate
        [{"context": "feed_revenue", "question": "x"}, {"context": "feed_revenue", "question": "y"}],  # twice
        [{"context": "feed_revenue", "question": ""}],
        [{"context": "feed_revenue"}],
        [], "nope",
    ])
    def test_anything_off_is_no_split(self, parts):
        assert mc.parse_split({"parts": parts, "operation": "none"}, self.NAMES) is None

    @pytest.mark.parametrize("operation,operands", [("ratio", [0, 0]), ("ratio", [0, 5]), ("ratio", [0]), ("sum", [0, 1]),
                                                     ("difference", [True, 0]), ("ratio", "01")])
    def test_bad_operation_is_no_operation(self, operation, operands):
        raw = {"parts": [{"context": n, "question": "q"} for n in self.NAMES], "operation": operation, "operands": operands}
        assert mc.parse_split(raw, self.NAMES)["operation"] == "none"


def part(context, rows, period=202608, error=None):
    result = QueryEngineResult(query_result=QueryResult(question="q", sql_query="SELECT 1", data=rows, explanation={"explanation": f"คำตอบของ {context}"},
                                                         tokens_used=0, provider="matcha", error=error),
                               context_name=context, data_as_of={"period": period} if period else None)
    return mc.Part(context=context, question=f"คำถามของ {context}", result=result, error=error)


class TestComputeAndCombine:
    def test_ratio_and_difference_in_code(self):
        parts = [part("a", [{"time_key": 202608, "v": 300.0}]), part("b", [{"v": 200.0}])]
        assert mc.compute(parts, "ratio", [0, 1])["value"] == 1.5
        assert mc.compute(parts, "difference", [1, 0])["value"] == -100.0
        text_, _ = mc.combine(parts, mc.compute(parts, "difference", [0, 1]), "difference")
        assert "100.00" in text_ and "ไม่ใช่กำไร / EBT ทางการ" in text_

    def test_not_computed_across_different_periods(self):
        parts = [part("a", [{"v": 300.0}], period=202608), part("b", [{"v": 200.0}], period=202607)]
        assert mc.compute(parts, "ratio", [0, 1]) is None
        text_, warnings = mc.combine(parts, None, "ratio")
        assert "งวดข้อมูลล่าสุดของแต่ละแหล่งไม่เท่ากัน" in text_ and "a 202608" in text_ and "b 202607" in text_
        assert any("ไม่ได้คำนวณ" in w for w in warnings)

    @pytest.mark.parametrize("rows", [[], [{"v": 1.0}, {"v": 2.0}], [{"v": 1.0, "w": 2.0}], [{"v": "text"}], [{"v": 0.0}],
                                      [{"month": 7}], [{"v": float("nan")}], [{"v": float("inf")}], [{"v": True}]])
    def test_not_computed_without_one_number_per_part(self, rows):
        assert mc.compute([part("a", [{"v": 5.0}]), part("b", rows)], "ratio", [0, 1]) is None

    def test_a_failed_part_is_said_and_nothing_is_computed(self):
        parts = [part("a", [{"v": 300.0}]), part("b", [], error="ข้อมูลกำลังถูก publish")]
        assert mc.compute(parts, "difference", [0, 1]) is None
        text_, warnings = mc.combine(parts, None, "difference")
        # hardening: the part's own words stay in part.error (audit / log) — the answer leaves the process
        assert "ตอบได้ 1 จาก 2 ส่วน" in text_ and "ข้อมูลกำลังถูก publish" not in text_
        assert "ส่วนนี้ตอบไม่ได้: " + outbound.message("query_failed") in text_
        assert "คำนวณจากผลข้างต้น" not in text_ and warnings

    def test_every_part_carries_its_origin(self):
        text_, warnings = mc.combine([part("a", [{"v": 1.0}]), part("b", [{"v": 2.0}])], None, "none")
        for expected in ("`a`", "`b`", "คำถามของ a", "คำตอบของ b", "ข้อมูลถึงงวด 202608"):
            assert expected in text_
        assert warnings == []


def source(policy=FULL, providers=None, name="s"):
    return SimpleNamespace(name=name, llm_data_policy=policy, llm_providers=providers)


class TestSplitPolicy:
    def test_strictest_policy_and_intersection_of_providers(self):
        state = mc._strictest([source(FULL, frozenset({"matcha", "claude"})), source(SCHEMA_ONLY, frozenset({"matcha"})), source()])
        assert state.policy == SCHEMA_ONLY and state.providers == frozenset({"matcha"})
        assert mc._strictest([source(), source()]).providers is None
        assert mc._strictest([source("whatever")]).policy == SCHEMA_ONLY  # unknown = strictest
        assert mc._strictest([source(providers=["matcha"])]).providers == frozenset()  # not a frozenset = nobody

    def test_no_provider_in_common_is_refused_before_any_call(self):
        engine = fake_engine()
        sources = {"feed_revenue": source(providers=frozenset({"claude"})), "feed_expense": source(providers=frozenset({"matcha"}))}
        with patch.object(mc, "source_resolver", MagicMock(for_context=lambda n: sources[n])), patch.object(mc, "_workspaces", return_value=WORKSPACES):
            with pytest.raises(LLMPolicyError):
                asyncio.run(mc.answer(engine, "รายได้และค่าใช้จ่าย"))
        engine._provider_for.assert_not_called()


def fake_engine(split=None, results=None, enabled='["nt-report"]'):
    """QueryEngine stand-in: the split provider returns `split`; query() returns results[context] (or raises it)."""
    engine = MagicMock()
    engine.db = None
    engine.admin_config.get_config.return_value = enabled
    engine.admin_config.get_ai_config.return_value = {}
    engine.schema_service.get_all_contexts.return_value = CONTEXTS
    provider = MagicMock()
    provider.get_model.return_value = None
    provider.generate_structured = AsyncMock(return_value=split)
    engine._provider_for.return_value = (provider, "matcha")
    engine.provider = provider

    async def query(question, context=None, **kwargs):
        engine.calls.append({"question": question, "context": context, **kwargs})
        outcome = (results or {}).get(context)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    engine.calls = []
    engine.query = query
    return engine


def run(engine, question="รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569", **kwargs):
    with patch.object(mc, "source_resolver", MagicMock(for_context=lambda n: source(name=n))), \
         patch.object(mc, "_workspaces", return_value=WORKSPACES):
        return asyncio.run(mc.ask(engine, question, **kwargs))


SPLIT = {"parts": [{"context": "feed_revenue", "question": "รายได้เดือนกรกฎาคม 2569"},
                   {"context": "feed_expense", "question": "ค่าใช้จ่ายเดือนกรกฎาคม 2569"}], "operation": "difference", "operands": [0, 1]}


class TestAnswer:
    def test_flag_off_is_the_single_context_path_and_no_provider_call(self):
        engine = fake_engine(SPLIT, {None: "single"}, enabled="")
        assert run(engine, scope={"year_month": 202607}) == "single"
        engine._provider_for.assert_not_called()
        assert engine.calls == [{"question": "รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569", "context": None, "scope": {"year_month": 202607}}]

    def test_a_named_context_is_always_the_single_context_path(self):
        engine = fake_engine(SPLIT, {"feed_revenue": "single"})
        with patch.object(mc, "answer", AsyncMock()) as answer:
            assert asyncio.run(mc.ask(engine, "รายได้และค่าใช้จ่าย", "feed_revenue")) == "single"
        answer.assert_not_called()

    def test_sub_questions_run_through_the_engine_with_the_callers_scope_and_allowlist(self):
        results = {"feed_revenue": part("feed_revenue", [{"v": 300.0}]).result, "feed_expense": part("feed_expense", [{"v": 200.0}]).result}
        engine = fake_engine(SPLIT, results)
        allowed = frozenset({"feed_revenue", "feed_expense"})
        multi = run(engine, scope={"year_month": 202607}, allowed_contexts=allowed, user_id=7, api_key_id=3, channel="portal")
        assert isinstance(multi, mc.MultiResult) and multi.context_name == "feed_revenue+feed_expense"
        assert multi.computed["value"] == 100.0
        assert [(c["context"], c["question"]) for c in engine.calls] == [(p["context"], p["question"]) for p in SPLIT["parts"]]
        for call in engine.calls:
            assert call["scope"] == {"year_month": 202607} and call["allowed_contexts"] == allowed
            assert call["user_id"] == 7 and call["api_key_id"] == 3 and call["channel"] == "portal"
            assert call["request_group"] == multi.request_group != ""

    def test_the_split_sees_only_contexts_the_caller_may_use(self):
        engine = fake_engine(SPLIT, {c: part(c, [{"v": 1.0}]).result for c in ("feed_revenue", "feed_expense")})
        run(engine, "รายได้ ค่าใช้จ่าย และ ebt", allowed_contexts=frozenset({"feed_revenue", "feed_expense"}))
        prompt = engine.provider.generate_structured.call_args.args[0]
        assert "feed_revenue" in prompt and "feed_expense" in prompt
        assert "feed_ebt" not in prompt and "expense:" not in prompt.replace("feed_expense:", "")

    @pytest.mark.parametrize("refusal", [ScopeError("scope ไม่รู้จัก"), ContextNotAllowed("นอกสิทธิ์"), LLMPolicyError("policy")])
    def test_a_refused_sub_question_refuses_the_whole_question(self, refusal):
        engine = fake_engine(SPLIT, {"feed_revenue": part("feed_revenue", [{"v": 300.0}]).result, "feed_expense": refusal})
        with pytest.raises(type(refusal)):
            run(engine)

    def test_a_failed_sub_question_is_reported_not_guessed(self):
        engine = fake_engine(SPLIT, {"feed_revenue": part("feed_revenue", [{"v": 300.0}]).result, "feed_expense": RuntimeError("gateway timeout")})
        multi = run(engine)
        assert multi.computed is None and "ตอบได้ 1 จาก 2 ส่วน" in multi.answer
        # hardening: the exception's text is reported in the audit row and the log, never in the answer
        assert "gateway timeout" not in multi.answer and outbound.message("internal_error") in multi.answer
        assert multi.parts[1].error == "gateway timeout" and multi.parts[1].code == "internal_error"

    def test_split_that_names_one_context_routes_there_with_the_original_question(self):
        one = {"parts": [{"context": "feed_expense", "question": "เขียนใหม่"}], "operation": "none"}
        engine = fake_engine(one, {"feed_expense": "single"})
        assert run(engine) == "single"
        assert [(c["context"], c["question"]) for c in engine.calls] == [("feed_expense", "รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569")]

    @pytest.mark.parametrize("split", [None, {"parts": [{"context": "feed_sales", "question": "x"}, {"context": "feed_revenue", "question": "y"}]}])
    def test_unusable_split_falls_back_to_the_single_context_path(self, split):
        engine = fake_engine(split, {None: "single"})
        engine.provider.generate_content = AsyncMock(return_value="ไม่ใช่ JSON")
        assert run(engine) == "single"
        assert [c["context"] for c in engine.calls] == [None]

    def test_parent_and_sub_questions_share_a_request_group_in_the_audit(self, tmp_path):
        from sqlalchemy.orm import Session
        from app.models.query_audit import QueryAudit

        app_db = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
        with app_db.begin() as conn:  # a query_audit table from before Phase 5
            conn.execute(text("CREATE TABLE query_audit (id INTEGER PRIMARY KEY, created_at DATETIME, user_id INTEGER, api_key_id INTEGER, "
                              "channel VARCHAR, workspace VARCHAR, context_name VARCHAR, scope TEXT, question TEXT, sql_query TEXT, "
                              "result_columns TEXT, row_count INTEGER, provider VARCHAR, llm_policy VARCHAR, cache_hit BOOLEAN, "
                              "error TEXT, execution_time_ms FLOAT)"))
        engine = fake_engine(SPLIT, {"feed_revenue": part("feed_revenue", [{"v": 300.0}]).result,
                                     "feed_expense": part("feed_expense", [{"v": 200.0}]).result})
        with Session(app_db) as db:
            engine.db = db
            engine._workspace = lambda name: "nt-report"
            multi = run(engine, channel="portal", user_id=7)
            row = db.query(QueryAudit).one()
        assert row.request_group == multi.request_group and row.context_name == "feed_revenue+feed_expense"
        assert row.question == "รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569" and row.row_count == 2 and row.channel == "portal"
        assert row.error is None and row.sql_query is None  # the SQL lives on the sub-questions' rows


# ── Sentinel at the provider's HTTP boundary: source A = full, source B = schema_only ─────────────

A_DIV, A_NUM, B_DIV, B_NUM = "ZQXALPHAOPEN", 111222333.25, "ZQXBETASECRET", 987654321.75
B_SENTINELS = (B_DIV, "987654321")


class FakeLLM:
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
        sent = str(json)
        if "You split one business question" in sent:
            content = ('{"parts": [{"context": "feed_a", "question": "รายได้รวมของ A"}, {"context": "feed_b", "question": "ค่าใช้จ่ายรวมของ B"}], '
                       '"operation": "ratio", "operands": [0, 1]}')
        else:
            table = "feed_b_fact" if "ค่าใช้จ่ายรวมของ B" in sent else "feed_a_fact"
            content = f"```sql\nSELECT division, amount FROM {table}\n```\nคำอธิบาย"
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return response


@pytest.fixture
def two_sources(tmp_path, monkeypatch):
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, main_view TEXT, display_name TEXT, "
                          "description TEXT, keywords TEXT, priority INT DEFAULT 1, is_active BOOLEAN DEFAULT 1, workspace_id INT)"))
        conn.execute(text("CREATE TABLE master_hierarchy (context_name TEXT, level INT, level_label_th TEXT, level_columns TEXT, is_active BOOLEAN)"))
        conn.execute(text("CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (1, 'default')"))
    migrate(config)
    knowledge_db.add_provenance(config)  # Plan 8.1 columns
    columns = json.dumps([{"name": "division", "type": "VARCHAR"}, {"name": "amount", "type": "DOUBLE"}])
    for i, (letter, div, num, keyword, policy) in enumerate((("a", A_DIV, A_NUM, "รายได้", FULL), ("b", B_DIV, B_NUM, "ค่าใช้จ่าย", SCHEMA_ONLY)), start=2):
        root = tmp_path / letter
        root.mkdir()
        (root / "fact.csv").write_text(f"division,amount\n{div},{num}\n")
        with config.begin() as conn:
            conn.execute(text("INSERT INTO data_sources (id, name, source_type, root_path, llm_data_policy) VALUES (:i, :n, 'duckdb_file', :r, :p)"),
                         {"i": i, "n": f"df_{letter}", "r": str(root), "p": policy})
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (:i, :t, 'fact.csv', :c)"),
                         {"i": i, "t": f"feed_{letter}_fact", "c": columns})
            conn.execute(text("INSERT INTO schema_contexts (name, main_view, display_name, keywords, source_id, workspace_id) VALUES (:n, :v, :n, :k, :i, 1)"),
                         {"n": f"feed_{letter}", "v": f"feed_{letter}_fact", "k": json.dumps([keyword], ensure_ascii=False), "i": i})
    monkeypatch.setattr("app.db.session.config_engine", config)
    return config, SourceResolver(config_engine=config, cache_dir=str(tmp_path / "cache"))


def test_no_value_of_the_restricted_source_reaches_a_provider(two_sources):
    """Real QueryEngine → AIService → MatchaProvider for the split and both sub-questions; only httpx and MCP are fake."""
    from app.services import query_engine as qe
    from app.services.schema.service import SchemaService

    config, resolver = two_sources
    qe._query_cache.clear()
    qe._dedup_store.clear()
    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha", "matcha_api_url": "http://llm.test"}
    admin_config.get_feature_flags.return_value = {"value_verification_enabled": False}
    admin_config.get_provider_record.return_value = None
    admin_config.get_config.return_value = '["default"]'
    mcp = MagicMock()
    mcp.servers = {"nt-query": object()}
    mcp.call_tool = AsyncMock(return_value=json.dumps({"valid": True}))
    mcp.get_tools = AsyncMock(return_value=[])
    warning_detector = MagicMock()
    warning_detector.detect = AsyncMock(return_value=[])
    engine = qe.QueryEngine(mcp_client=mcp, admin_config=admin_config)
    engine._schema_service = SchemaService(db_engine=config, business_engine=config)
    fake = FakeLLM()
    # hermetic: only matcha has a key here, whatever the developer's .env holds
    kwargs = lambda name, *a, **k: {"api_key": "k" if name == "matcha" else "", "api_url": "http://llm.test", "model": "m"}  # noqa: E731
    with patch("app.providers.matcha_provider.httpx.AsyncClient", fake), \
         patch.object(qe, "source_resolver", resolver), patch.object(mc, "source_resolver", resolver), \
         patch("app.services.data_sources.source_resolver", resolver), \
         patch.object(qe, "_build_provider_kwargs", kwargs), \
         patch.object(qe, "WarningDetector", return_value=warning_detector), \
         patch.object(qe, "workspace_of_context", return_value=None), \
         patch.object(mc, "_workspaces", return_value={1: "default"}):
        multi = asyncio.run(mc.ask(engine, "อัตราส่วนรายได้ต่อค่าใช้จ่าย"))

    assert isinstance(multi, mc.MultiResult) and [p.context for p in multi.parts] == ["feed_a", "feed_b"]
    assert multi.parts[1].result.query_result.data == [{"division": B_DIV, "amount": B_NUM}]  # the caller still gets B's rows
    assert multi.parts[1].result.llm_policy == SCHEMA_ONLY and multi.parts[0].result.llm_policy == FULL
    assert multi.computed["value"] == A_NUM / B_NUM  # computed in code, not by a provider
    sent = json.dumps(fake.requests, ensure_ascii=False, default=str)
    assert A_DIV in sent, "the trap works: A is `full`, its values do travel"
    for sentinel in B_SENTINELS:
        assert sentinel not in sent, sentinel
    split_requests = [r for r in fake.requests if "You split one business question" in str(r)]
    assert split_requests and all(A_DIV not in str(r) for r in split_requests)  # the split sees no data at all


def test_admin_switches_a_workspace_on_and_off(tmp_path):
    """PUT /admin/workspaces/{id}/multi-context keeps the JSON list that enabled_workspaces reads."""
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    from app.api.v1.admin.workspaces import WorkspaceMultiContext, set_multi_context
    from app.services.admin_config_service import AdminConfigService

    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (1, 'default'), (2, 'nt-report')"))
        conn.execute(text("CREATE TABLE admin_config (id INTEGER PRIMARY KEY, config_key TEXT UNIQUE, config_value TEXT, config_type TEXT, "
                          "category TEXT, description TEXT, is_active BOOLEAN DEFAULT 1, updated_by TEXT, "
                          "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"))
    admin = SimpleNamespace(email="admin@test")
    with Session(config) as db:
        assert mc.enabled_workspaces(AdminConfigService(db)) == frozenset()  # nothing set = off
        assert set_multi_context(2, WorkspaceMultiContext(enabled=True), admin, db)["enabled_workspaces"] == ["nt-report"]
        set_multi_context(1, WorkspaceMultiContext(enabled=True), admin, db)
        assert mc.enabled_workspaces(AdminConfigService(db)) == frozenset({"default", "nt-report"})
        assert set_multi_context(1, WorkspaceMultiContext(enabled=False), admin, db)["enabled_workspaces"] == ["nt-report"]
        assert mc.enabled_workspaces(AdminConfigService(db)) == NT
        with pytest.raises(HTTPException):
            set_multi_context(9, WorkspaceMultiContext(enabled=True), admin, db)

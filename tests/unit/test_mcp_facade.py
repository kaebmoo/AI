"""Plan 7 Phase 6 — external MCP facade (/api/v1/mcp, stateless Streamable HTTP).

Driven end to end with the SDK's own client over ASGI: gate (every request, not 'at initialize'),
one usage per tool call on the REST counters, the key's rights ∩ 'full' policy, fixed error texts,
no SQL, and the engine's ContextVars under two keys at once.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.routing import Route

from app.api.v1 import mcp_facade
from app.core.llm_policy import LLMPolicyError
from app.db.base_class import Base
from app.models.api_key import APIKeyUsage
from app.models.user import User
from app.services.api_key_service import APIKeyService
from app.services.data_sources import ScopeError, request_pinned, request_scope
from app.services.workspaces import ContextNotAllowed
from scripts.migrate_data_sources import migrate as migrate_sources
from scripts.migrate_workspaces import migrate_config

URL = "http://localhost:8000/api/v1/mcp"
_REAL_ENABLED = mcp_facade._enabled  # the fixture switches the flag on


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Temp app + config DBs behind app.db.session; keys: a (feed_sales + feed_secret), b (hr), plain (unbound)."""
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, display_name TEXT, "
                          "description TEXT, main_view TEXT, is_active BOOLEAN DEFAULT 1, priority INTEGER DEFAULT 0, "
                          "keywords TEXT, source_id INTEGER)"))
        conn.execute(text("INSERT INTO schema_contexts (name, display_name, description) VALUES "
                          "('feed_sales', 'ยอดขาย', 'sales'), ('feed_secret', 'ลับ', 'restricted source'), "
                          "('hr_payroll', 'เงินเดือน', 'hr'), ('revenue', 'รายได้', 'legacy')"))
    migrate_sources(config)
    migrate_config(config)
    with config.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (name) VALUES ('nt-report'), ('hr')"))
        conn.execute(text("INSERT INTO data_sources (name, source_type, llm_data_policy) VALUES ('secret', 'duckdb_file', 'aggregated_only')"))
        conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name='nt-report') WHERE name LIKE 'feed_%'"))
        conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name='hr') WHERE name = 'hr_payroll'"))
        conn.execute(text("UPDATE schema_contexts SET source_id = (SELECT id FROM data_sources WHERE name='secret') WHERE name = 'feed_secret'"))
        ws = dict(conn.execute(text("SELECT name, id FROM workspaces")).fetchall())

    app_engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(app_engine)
    Session = sessionmaker(bind=app_engine)
    import app.db.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", Session)
    monkeypatch.setattr(session_module, "ConfigSessionLocal", sessionmaker(bind=config))
    monkeypatch.setattr(session_module, "config_engine", config)
    monkeypatch.setattr(mcp_facade, "_enabled", lambda: True)

    keys = {}
    with Session() as db:
        user = User(email="mcp@example.com", display_name="MCP", is_active=True, role="user")
        db.add(user)
        db.commit()
        service = APIKeyService(db)
        for name, workspace, scopes in (("a", "nt-report", "query"), ("b", "hr", "query"), ("plain", None, "query"),
                                        ("noscope", "nt-report", "reports")):
            raw, row = service.create_key(user.id, name, scopes=scopes, workspace_id=ws.get(workspace), rate_limit_per_minute=0)
            keys[name] = SimpleNamespace(raw=raw, id=row.id)
        raw, row = service.create_key(user.id, "listed", allowed_contexts='["hr_payroll"]', rate_limit_per_minute=0)
        keys["listed"] = SimpleNamespace(raw=raw, id=row.id)  # allowlist only, no workspace
        user_id = user.id
    return SimpleNamespace(config=config, Session=Session, keys=keys, user_id=user_id)


def _app():
    server, asgi = mcp_facade.build()

    @asynccontextmanager
    async def lifespan(_app):
        async with server.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.state.mcp_client = MagicMock(name="shared-internal-mcp-client")
    app.router.routes.append(Route(mcp_facade.PATH, endpoint=asgi))
    return app


@asynccontextmanager
async def _client(app, key, **headers):
    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers=headers, timeout=timeout, auth=auth)

    sent = {"X-API-Key": key, **headers} if key else headers
    async with streamablehttp_client(URL, headers=sent, httpx_client_factory=factory) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _run(coro_fn):
    async def main():
        app = _app()
        async with app.router.lifespan_context(app):
            return await coro_fn(app)
    return asyncio.run(main())


def _result(context="feed_sales", policy="full", error=None, data=None, explanation="ยอดขาย 10 บาท"):
    qr = SimpleNamespace(explanation=explanation, error=error, data=data or [], sql_query="SELECT secret_sql FROM t")
    return SimpleNamespace(query_result=qr, context_name=context, execution_time_ms=5.0,
                           data_as_of={"period": 202608, "built_at": "x", "build_id": "b"}, llm_policy=policy)


class _Group(Exception):  # shape of (Base)ExceptionGroup on every supported Python
    def __init__(self, message, exceptions):
        super().__init__(message)
        self.exceptions = exceptions


def _usage(world, key):
    with world.Session() as db:
        row = db.query(APIKeyUsage).filter(APIKeyUsage.api_key_id == world.keys[key].id).first()
        return row.request_count if row else 0


def _raw_post(app, key=None, method="POST", body=None):
    async def go():
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if key:
            headers["X-API-Key"] = key
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
            return await client.request(method, "/api/v1/mcp", headers=headers, json=body or {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_contexts", "arguments": {}}})
    return go()


class TestGate:
    def test_no_key_bad_key_unbound_key_and_wrong_scope_never_reach_the_transport(self, world):
        async def check(app):
            statuses = {}
            for name, key in (("none", None), ("bad", "ntai_nope"), ("plain", world.keys["plain"].raw),
                              ("noscope", world.keys["noscope"].raw)):
                statuses[name] = (await _raw_post(app, key)).status_code  # tools/call with NO handshake
            return statuses
        assert _run(check) == {"none": 401, "bad": 401, "plain": 401, "noscope": 401}

    def test_a_session_without_a_key_sees_no_tool_list(self, world):
        async def check(app):
            async with _client(app, None) as session:
                await session.list_tools()
        with pytest.raises(BaseException) as caught:
            _run(check)
        assert "401" in repr(getattr(caught.value, "exceptions", [caught.value]))

    def test_off_by_default_is_404_and_get_delete_are_405(self, world, monkeypatch):
        async def check(app):
            return [(await _raw_post(app, world.keys["a"].raw, method=m)).status_code for m in ("GET", "DELETE", "POST")]
        assert _run(check) == [405, 405, 200]
        monkeypatch.setattr(mcp_facade, "_enabled", lambda: False)
        assert _run(check) == [404, 404, 404]

    def test_flag_reads_admin_config_and_fails_closed(self, world):
        for config, expected in ((MagicMock(**{"get_config.return_value": "true"}), True),
                                 (MagicMock(**{"get_config.return_value": "false"}), False),
                                 (MagicMock(**{"get_config.side_effect": RuntimeError("config DB down")}), False)):
            with patch("app.services.admin_config_service.AdminConfigService", return_value=config):
                assert _REAL_ENABLED() is expected
            config.close.assert_called_once()

    def test_foreign_host_and_any_browser_origin_are_refused(self, world):
        async def check(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                base = {"X-API-Key": world.keys["a"].raw, "Accept": "application/json, text/event-stream"}
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                evil_host = await client.post("http://evil.example/api/v1/mcp", headers=base, json=body)
                origin = await client.post(URL, headers={**base, "Origin": "http://localhost:3000"}, json=body)
                return evil_host.status_code, origin.status_code
        assert _run(check) == (421, 403)

    def test_revoked_key_stops_working_inside_an_open_client_session(self, world):
        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                assert not (await session.call_tool("list_contexts", {})).isError
                with world.Session() as db:
                    APIKeyService(db).revoke_key(world.keys["a"].id)
                await session.call_tool("list_contexts", {})
        with pytest.raises(BaseException) as caught:
            _run(check)
        assert "401" in repr(getattr(caught.value, "exceptions", [caught.value]))


class TestTools:
    def test_exactly_three_tools_and_no_foreign_context_name_anywhere(self, world):
        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                tools = (await session.list_tools()).tools
                listing = await session.call_tool("list_contexts", {})
                return tools, listing
        tools, listing = _run(check)
        assert sorted(t.name for t in tools) == ["ask", "list_contexts", "source_status"]
        # feed_secret: inside the key's workspace but its source is aggregated_only → does not exist on this channel
        assert [c["name"] for c in listing.structuredContent["contexts"]] == ["feed_sales"]
        everything = json.dumps([t.model_dump() for t in tools], default=str) + listing.content[0].text
        assert "hr_payroll" not in everything and "revenue" not in everything

    def test_one_tool_call_is_one_usage_and_the_handshake_is_free(self, world):
        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                await session.list_tools()
                before = _usage(world, "a")
                await session.call_tool("list_contexts", {})
                await session.call_tool("source_status", {"context": "feed_sales"})
                return before, _usage(world, "a")
        assert _run(check) == (0, 2)

    def test_daily_quota_is_shared_with_rest_and_is_a_readable_error(self, world):
        with world.Session() as db:
            db.query(type(APIKeyService(db).authenticate(world.keys["a"].raw))).filter_by(id=world.keys["a"].id).update({"rate_limit_per_day": 1})
            db.commit()
            APIKeyService(db).track_usage(world.keys["a"].id)  # the one request of the day, spent over REST

        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return await session.call_tool("list_contexts", {})
        result = _run(check)
        assert result.isError and result.structuredContent["error"]["code"] == "rate_limited"

    def test_ask_goes_through_the_shared_entry_with_the_usable_set_and_never_returns_sql(self, world):
        asked = AsyncMock(return_value=_result(data=[{"v": 1}, {"v": 2}]))

        async def check(app):
            async with _client(app, world.keys["a"].raw, **{"User-Agent": "claude-code/2.1 (x; <script>)"}) as session:
                return await session.call_tool("ask", {"question": "ยอดขาย", "scope": {"year_month": 202608}, "include_data": True})
        with patch("app.services.multi_context.ask", asked), patch("app.services.query_engine.QueryEngine"):
            result = _run(check)
        kwargs = asked.call_args.kwargs
        assert kwargs["allowed_contexts"] == frozenset({"feed_sales"}) and kwargs["scope"] == {"year_month": 202608}
        assert kwargs["channel"] == "mcp:claude-code/2.1" and kwargs["api_key_id"] == world.keys["a"].id
        payload = result.structuredContent
        assert not result.isError and payload["answer"] == "ยอดขาย 10 บาท" and payload["data"] == [{"v": 1}, {"v": 2}]
        assert payload["data_as_of"]["period"] == 202608
        assert "secret_sql" not in result.model_dump_json() and "sql" not in payload

    def test_a_structured_explanation_is_returned_as_its_text(self, world):
        structured = _result(data=[{"v": 5}], explanation={"explanation": "รายได้ 5 บาท", "chart_config": {"x": 1}})

        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return await session.call_tool("ask", {"question": "q"})
        with patch("app.services.multi_context.ask", AsyncMock(return_value=structured)), patch("app.services.query_engine.QueryEngine"):
            result = _run(check)
        assert result.structuredContent["answer"] == "รายได้ 5 บาท" == result.content[0].text

    @pytest.mark.parametrize("raised, context, code", [
        (ScopeError("คอลัมน์ภายใน [secret_col] scripts/x.py"), None, "invalid_scope"),
        (ContextNotAllowed("hr_payroll"), "hr_payroll", "context_not_allowed"),
        (ContextNotAllowed("nope"), "does_not_exist", "context_not_allowed"),  # same answer: no existence oracle
        (ContextNotAllowed("feed_secret"), "feed_secret", "policy_refused"),   # in the key's rights, source not 'full'
        (LLMPolicyError("source 'secret' …"), None, "policy_refused"),
        (_Group("tg", [ScopeError("x")]), None, "invalid_scope"),  # anyio TaskGroup wraps what is raised inside
        (RuntimeError("duckdb: /Users/seal/private/path.db SELECT secret_sql"), None, "internal_error"),
    ])
    def test_refusals_and_failures_are_fixed_texts(self, world, raised, context, code):
        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return await session.call_tool("ask", {"question": "q", **({"context": context} if context else {})})
        with patch("app.services.multi_context.ask", AsyncMock(side_effect=raised)), patch("app.services.query_engine.QueryEngine"):
            result = _run(check)
        assert result.isError and result.structuredContent["error"]["code"] == code
        dumped = result.model_dump_json()
        assert "secret" not in dumped and "/Users" not in dumped and "hr_payroll" not in dumped

    @pytest.mark.parametrize("engine_result, code", [
        (_result(policy="aggregated_only"), "policy_refused"),  # defence in depth behind the usable set
        (_result(policy=None), "policy_refused"),
        (_result(error="no such table: secret_sql", explanation="เกิดข้อผิดพลาด: secret_sql"), "query_failed"),
        (_result(error="duplicate_request", explanation="คำถามซ้ำ"), "duplicate_request"),
    ])
    def test_an_answer_that_must_not_leave_is_discarded(self, world, engine_result, code):
        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return await session.call_tool("ask", {"question": "q"})
        with patch("app.services.multi_context.ask", AsyncMock(return_value=engine_result)), patch("app.services.query_engine.QueryEngine"):
            result = _run(check)
        assert result.isError and result.structuredContent["error"]["code"] == code
        assert "secret_sql" not in result.model_dump_json() and "ยอดขาย" not in result.model_dump_json()

    def test_a_failed_part_of_a_multi_context_answer_keeps_its_reason_inside(self, world):
        from app.services.multi_context import MultiResult, Part
        good = Part(context="feed_sales", question="ยอดขาย", display_name="ยอดขาย", result=_result())
        bad = Part(context="feed_sales", question="x", display_name="x", error="Binder Error: secret_sql /Users/p")
        multi = MultiResult(parts=[good, bad], answer="ส่วนนี้ตอบไม่ได้: Binder Error: secret_sql /Users/p", computed=None,
                            warnings=["ตอบได้ 1 จาก 2 ส่วน"], execution_time_ms=1.0, request_group="g")

        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return await session.call_tool("ask", {"question": "q"})
        with patch("app.services.multi_context.ask", AsyncMock(return_value=multi)), patch("app.services.query_engine.QueryEngine"):
            result = _run(check)
        assert not result.isError and result.structuredContent["parts"][1]["error"] == "query_failed"
        assert "secret_sql" not in result.model_dump_json() and "/Users" not in result.model_dump_json()

    def test_source_status_checks_rights_before_resolving_and_hides_the_reason(self, world):
        resolver = MagicMock()
        resolver.for_context.side_effect = RuntimeError("/Users/seal/DataFeed/dist missing")

        async def check(app):
            async with _client(app, world.keys["a"].raw) as session:
                return [await session.call_tool("source_status", {"context": c}) for c in ("Feed_Sales ", "hr_payroll", "feed_secret")]
        with patch("app.services.data_sources.source_resolver", resolver):
            mine, foreign, restricted = _run(check)
        assert mine.structuredContent["context"] == "feed_sales" and mine.structuredContent["status"] == "unavailable"
        assert "/Users" not in mine.model_dump_json()
        assert foreign.structuredContent["error"]["code"] == "context_not_allowed"
        assert restricted.structuredContent["error"]["code"] == "policy_refused"
        assert [c.args[0] for c in resolver.for_context.call_args_list] == ["feed_sales"]


class TestPolicyReader:
    def test_strict_unlike_policy_for_context(self, world):
        assert mcp_facade.full_policy_contexts(world.config) == {"feed_sales", "hr_payroll", "revenue"}
        with world.config.begin() as conn:
            conn.execute(text("UPDATE data_sources SET llm_data_policy = NULL WHERE name = 'legacy'"))
        assert "revenue" not in mcp_facade.full_policy_contexts(world.config)

    def test_unmigrated_registry_or_unreadable_config_is_nothing(self, tmp_path):
        bare = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
        with bare.begin() as conn:  # a registry from before Phase 4.5: no llm_data_policy column
            conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1, source_id INTEGER)"))
            conn.execute(text("CREATE TABLE data_sources (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1)"))
            conn.execute(text("INSERT INTO data_sources (name) VALUES ('legacy')"))
            conn.execute(text("INSERT INTO schema_contexts (name) VALUES ('revenue')"))
        assert mcp_facade.full_policy_contexts(bare) == frozenset()
        assert mcp_facade.full_policy_contexts(create_engine("sqlite://")) == frozenset()


class TestIsolation:
    def test_two_keys_at_once_each_see_their_own_scope_and_nothing_stays_behind(self, world):
        """The real QueryEngine.query sets/resets the ContextVars; the transport runs each call in its own task."""
        from app.services.query_engine import QueryEngine
        seen = {}

        async def fake_query(self, question, *args, **kwargs):
            await asyncio.sleep(0.05)  # both calls are inside query() at the same time
            seen[question] = (request_scope.get(), request_pinned.get())
            return _result(context=question)

        async def check(app):
            async def one(key, question, scope):
                async with _client(app, world.keys[key].raw) as session:
                    return await session.call_tool("ask", {"question": question, "scope": scope})
            await asyncio.gather(one("a", "feed_sales", {"year_month": 1}), one("b", "hr_payroll", {"year_month": 2}))
            return request_scope.get(), request_pinned.get()

        with patch.object(QueryEngine, "_query", fake_query), patch.object(QueryEngine, "_audit", AsyncMock()), \
                patch("app.services.multi_context.answer", AsyncMock(return_value=None)), \
                patch("app.services.admin_config_service.AdminConfigService", MagicMock()):
            after = _run(check)
        assert seen == {"feed_sales": ({"year_month": 1}, True), "hr_payroll": ({"year_month": 2}, True)}
        assert after == (None, False)


class TestRestSideOfTheSameChange:
    def test_rest_cannot_forge_the_mcp_audit_channel(self):
        from app.api.v1.query import _rest_channel
        assert [_rest_channel(s) for s in (None, "portal", "mcp", "MCP:claude")] == ["api", "portal", "api:mcp", "api:MCP:claude"]

    def test_authenticate_has_no_side_effects_validate_key_still_counts(self, world):
        with world.Session() as db:
            service = APIKeyService(db)
            assert service.authenticate(world.keys["a"].raw).id == world.keys["a"].id
            assert service.authenticate(world.keys["a"].raw).last_used_at is None
            assert service.validate_key(world.keys["a"].raw).last_used_at is not None
            assert service.authenticate("ntai_nope") is None

    def test_key_surface_knows_the_mcp_path_and_nothing_near_it(self):
        from fastapi import HTTPException
        from app.api.deps import enforce_key_surface
        key = SimpleNamespace(workspace_id=1, allowed_contexts=None)
        enforce_key_surface(key, "/api/v1/mcp")
        for path in ("/api/v1/mcpx", "/api/v1/chat", "/api/v1/admin/mcp"):
            with pytest.raises(HTTPException):
                enforce_key_surface(key, path)


class TestReviewFindings:
    """Independent review of fd67d07 — each of these passed through the first version."""

    def _ask(self, world, engine_result, arguments=None, key="a"):
        async def check(app):
            async with _client(app, world.keys[key].raw) as session:
                return await session.call_tool("ask", arguments or {"question": "q"})
        with patch("app.services.multi_context.ask", AsyncMock(return_value=engine_result)), patch("app.services.query_engine.QueryEngine"):
            return _run(check)

    def test_the_no_data_text_of_the_engine_quotes_the_sql_and_never_leaves(self, world):
        """hybrid_flow: a query that ran and matched nothing explains itself WITH the SQL, error=None."""
        empty = _result(data=[], explanation="ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\nSELECT secret_sql FROM t\n```")
        result = self._ask(world, empty)
        assert not result.isError and result.structuredContent["answer"] == mcp_facade.NO_DATA
        assert "secret_sql" not in result.model_dump_json()

    def test_an_answer_with_rows_that_still_quotes_the_sql_is_discarded(self, world):
        result = self._ask(world, _result(data=[{"v": 1}], explanation="ดูจาก SELECT secret_sql FROM t"))
        assert result.isError and result.structuredContent["error"]["code"] == "query_failed"
        fenced = self._ask(world, _result(data=[{"v": 1}], explanation="```SQL\nSELECT 1\n```"))
        assert fenced.isError and "SELECT" not in fenced.model_dump_json()

    def test_parts_a_failed_one_with_a_result_an_empty_one_and_the_row_cap_per_ask(self, world, monkeypatch):
        from app.services.multi_context import MultiResult, Part
        monkeypatch.setattr(mcp_facade.settings, "MCP_MAX_ROWS", 6)
        rows = [{"v": i} for i in range(10)]
        good = Part(context="feed_sales", question="a", display_name="a", result=_result(data=rows))
        failed = Part(context="feed_sales", question="b", display_name="b", error="boom /Users/p",
                      result=_result(data=rows, error="boom /Users/p", explanation="เกิดข้อผิดพลาด: boom /Users/p secret_tbl"))
        empty = Part(context="feed_sales", question="c", display_name="c",
                     result=_result(data=[], explanation="ไม่พบ\n```sql\nSELECT secret_sql FROM t\n```"))
        multi = MultiResult(parts=[good, failed, empty], answer="1. ยอดขาย 10 บาท\n2. ⚠️ ส่วนนี้ตอบไม่ได้: boom /Users/p", computed=None,
                            warnings=["ตอบได้ 1 จาก 3 ส่วน"], execution_time_ms=1.0, request_group="g")
        result = self._ask(world, multi, {"question": "q", "include_data": True})
        a, b, c = result.structuredContent["parts"]
        assert not result.isError and len(a["data"]) == 2  # 6 rows per ask over 3 parts
        assert b["answer"] == mcp_facade.ERRORS["query_failed"][1] and b["error"] == "query_failed" and "data" not in b
        assert c["answer"] == mcp_facade.NO_DATA
        dumped = result.model_dump_json()
        assert "/Users" not in dumped and "secret" not in dumped

    def test_an_empty_question_is_a_readable_error(self, world):
        result = self._ask(world, _result(), {"question": ""})
        assert result.isError and result.structuredContent["error"]["code"] == "invalid_arguments"

    def test_closing_a_workspace_cuts_off_an_allowlist_only_key_too(self, world):
        async def check(app):
            async with _client(app, world.keys["listed"].raw) as session:
                before = await session.call_tool("list_contexts", {})
                with world.config.begin() as conn:
                    conn.execute(text("UPDATE workspaces SET is_active = 0 WHERE name = 'hr'"))
                return before, await session.call_tool("list_contexts", {}), await session.call_tool("source_status", {"context": "hr_payroll"})
        before, after, status = _run(check)
        assert [c["name"] for c in before.structuredContent["contexts"]] == ["hr_payroll"]
        assert after.structuredContent["contexts"] == [] and status.structuredContent["error"]["code"] == "policy_refused"

    def test_two_key_headers_are_refused(self, world):
        async def check(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                headers = [("X-API-Key", world.keys["a"].raw), ("X-API-Key", world.keys["b"].raw),
                           ("Accept", "application/json, text/event-stream")]
                return (await client.post(URL, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})).status_code
        assert _run(check) == 401

    def test_a_parallel_burst_is_counted_call_by_call_and_stops_at_the_daily_limit(self, world):
        from app.models.api_key import APIKey

        async def burst(app):
            async def one():
                async with _client(app, world.keys["a"].raw) as session:
                    return (await session.call_tool("list_contexts", {})).isError
            return await asyncio.gather(*(one() for _ in range(12)))
        assert _run(burst) == [False] * 12 and _usage(world, "a") == 12  # no lost update, no IntegrityError on the first row
        with world.Session() as db:
            db.query(APIKey).filter_by(id=world.keys["b"].id).update({"rate_limit_per_day": 3})
            db.commit()

        async def limited(app):
            async def one():
                async with _client(app, world.keys["b"].raw) as session:
                    return (await session.call_tool("list_contexts", {})).isError
            return await asyncio.gather(*(one() for _ in range(12)))
        assert _run(limited).count(False) <= 3

    def test_an_expired_key_and_a_deactivated_owner_stop_at_the_gate(self, world):
        from datetime import timedelta
        from app.core.time_utils import utcnow
        from app.models.api_key import APIKey

        async def status(app):
            return (await _raw_post(app, world.keys["a"].raw)).status_code
        assert _run(status) == 200
        with world.Session() as db:
            db.query(APIKey).filter_by(id=world.keys["a"].id).update({"expires_at": utcnow() - timedelta(minutes=1)})
            db.commit()
        assert _run(status) == 401
        with world.Session() as db:
            db.query(APIKey).filter_by(id=world.keys["a"].id).update({"expires_at": None})
            db.query(User).filter_by(id=world.user_id).update({"is_active": False})
            db.commit()
        assert _run(status) == 401

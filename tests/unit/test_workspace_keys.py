"""Plan 7 Phase 4a — workspace + scoped API key.

Exit: a key of workspace A cannot reach a context of workspace B (403) — named explicitly or
through auto-routing — and cannot leave /api/v1/query. Keys issued before Phase 4 (no workspace,
no allowlist) and session users behave exactly as before.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.workspaces import ContextNotAllowed, allowed_contexts, check_context
from scripts.migrate_workspaces import migrate_config


@pytest.fixture
def config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, is_active BOOLEAN DEFAULT 1, "
                          "priority INTEGER DEFAULT 0, keywords TEXT)"))
        conn.execute(text("INSERT INTO schema_contexts (name, keywords, priority) VALUES "
                          "('revenue', '[\"รายได้\"]', 10), ('feed_sales', '[\"ยอดขาย\"]', 1), "
                          "('transfer price', '[\"transfer\"]', 0), ('hr_payroll', '[\"เงินเดือน\", \"รายได้\"]', 5)"))
    migrate_config(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (name) VALUES ('nt-report'), ('hr')"))
        conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name='nt-report') WHERE name IN ('feed_sales', 'transfer price')"))
        conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name='hr') WHERE name = 'hr_payroll'"))
    return engine


def _ws(engine, name):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM workspaces WHERE name = :n"), {"n": name}).scalar_one()


def _key(workspace_id=None, allowed=None):
    return SimpleNamespace(workspace_id=workspace_id, allowed_contexts=json.dumps(allowed) if allowed is not None else None)


class TestMigration:
    def test_existing_contexts_land_in_the_default_workspace_and_rerun_is_a_noop(self, config):
        migrate_config(config)
        with config.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM workspaces WHERE name = 'default'")).scalar_one() == 1
            assert conn.execute(text("SELECT w.name FROM schema_contexts sc JOIN workspaces w ON w.id = sc.workspace_id "
                                     "WHERE sc.name = 'revenue'")).scalar_one() == "default"
            assert conn.execute(text("SELECT COUNT(*) FROM schema_contexts WHERE workspace_id IS NULL")).scalar_one() == 0


class TestAllowedContexts:
    def test_no_key_and_pre_phase4_keys_are_unrestricted(self, config):
        assert allowed_contexts(None, config) is None
        assert allowed_contexts(_key(), config) is None
        assert allowed_contexts(SimpleNamespace(), config) is None  # a row loaded before the columns existed

    def test_workspace_key_sees_its_workspace_only(self, config):
        assert allowed_contexts(_key(_ws(config, "nt-report")), config) == {"feed sales", "transfer price"}

    def test_allowlist_narrows_inside_the_workspace_never_widens(self, config):
        key = _key(_ws(config, "nt-report"), ["feed_sales", "hr_payroll"])
        assert allowed_contexts(key, config) == {"feed sales"}

    def test_context_created_after_the_migration_belongs_to_default(self, config):
        from app.services.workspaces import resolve_key_binding, workspace_of_context

        with config.begin() as conn:  # what a new registration / the admin UI inserts: no workspace_id
            conn.execute(text("INSERT INTO schema_contexts (name) VALUES ('feed_new')"))
        default = _ws(config, "default")
        assert allowed_contexts(_key(default), config) == {"revenue", "feed new"}
        assert resolve_key_binding("default", ["feed_new"], config)[0] == default
        assert workspace_of_context("feed_new", config) == "default"
        assert "feed new" not in allowed_contexts(_key(_ws(config, "nt-report")), config)

    def test_inactive_context_is_not_allowed(self, config):
        with config.begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET is_active = 0 WHERE name = 'feed_sales'"))
        assert allowed_contexts(_key(_ws(config, "nt-report")), config) == {"transfer price"}

    @pytest.mark.parametrize("raw", ["not json", '{"a": 1}', "[1, 2]", '"feed_sales"'])
    def test_broken_allowlist_fails_closed(self, config, raw):
        key = SimpleNamespace(workspace_id=None, allowed_contexts=raw)
        assert allowed_contexts(key, config) == frozenset()

    def test_unreachable_config_fails_closed(self):
        assert allowed_contexts(_key(1), create_engine("sqlite://")) == frozenset()

    def test_check_context_matches_underscore_and_space_spellings(self):
        check_context("transfer_price", frozenset({"transfer price"}))
        check_context("anything", None)
        with pytest.raises(ContextNotAllowed):
            check_context("hr_payroll", frozenset({"transfer price"}))


class TestQueryEngine:
    def _ask(self, contexts, **kwargs):
        from app.providers.base import QueryResult
        from app.services import query_engine as qe

        admin_config = MagicMock()
        admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
        admin_config.get_feature_flags.return_value = {}
        admin_config.get_provider_record.return_value = None
        engine = qe.QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        ai_service = MagicMock()
        ai_service.query_hybrid = AsyncMock(return_value=QueryResult(
            question="q", sql_query="SELECT 1", data=[{"n": 1}], explanation="", tokens_used=0, provider="matcha"))
        schema_cls = MagicMock()
        schema_cls.return_value.build_system_prompt.return_value = "prompt"
        engine._schema_service = MagicMock()
        engine._schema_service.get_all_contexts.return_value = contexts
        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])
        with patch.object(qe.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe, "AIService", return_value=ai_service), \
             patch.object(qe, "SchemaService", schema_cls), \
             patch.object(qe, "WarningDetector", return_value=warning_detector):
            qe._dedup_store.clear()
            return asyncio.run(engine.query(**kwargs)), ai_service

    CONTEXTS = [{"name": "revenue", "keywords": ["รายได้"], "priority": 10},
                {"name": "hr_payroll", "keywords": ["เงินเดือน", "รายได้"], "priority": 5},
                {"name": "feed_sales", "keywords": ["ยอดขาย"], "priority": 1}]

    def setup_method(self):
        from app.services import query_engine as qe
        qe._query_cache.clear()

    teardown_method = setup_method

    def test_named_context_outside_the_allowlist_is_refused_before_any_llm_call(self):
        with pytest.raises(ContextNotAllowed):
            self._ask(self.CONTEXTS, question="เงินเดือนรวม", context="hr_payroll", allowed_contexts=frozenset({"feed sales"}))

    def test_auto_route_stays_inside_the_allowlist(self):
        # 'รายได้' routes to revenue (priority 10) for everyone else; this key may only see hr_payroll
        result, _ = self._ask(self.CONTEXTS, question="รายได้เดือนนี้", allowed_contexts=frozenset({"hr payroll"}))
        assert result.context_name == "hr_payroll"
        result, _ = self._ask(self.CONTEXTS, question="รายได้เดือนนี้")
        assert result.context_name == "revenue"  # unrestricted: as before

    def test_no_keyword_match_falls_back_inside_the_allowlist_not_to_revenue(self):
        result, _ = self._ask(self.CONTEXTS, question="สวัสดี", allowed_contexts=frozenset({"feed sales"}))
        assert result.context_name == "feed_sales"

    def test_empty_allowlist_reaches_nothing(self):
        with pytest.raises(ContextNotAllowed):
            self._ask(self.CONTEXTS, question="รายได้", allowed_contexts=frozenset())

    def test_cached_answer_of_another_context_is_not_served_to_a_restricted_key(self):
        _, ai = self._ask(self.CONTEXTS, question="รายได้เดือนนี้")  # unrestricted → revenue, cached
        result, ai2 = self._ask(self.CONTEXTS, question="รายได้เดือนนี้", allowed_contexts=frozenset({"hr payroll"}))
        assert result.context_name == "hr_payroll" and ai2.query_hybrid.await_count == 1


class TestEndpoint:
    def _call(self, api_key, context=None, side_effect=None):
        from app.api.v1 import query as query_api

        request = SimpleNamespace(state=SimpleNamespace(api_key=api_key), app=SimpleNamespace(state=SimpleNamespace(mcp_client=MagicMock())))
        body = query_api.SimpleQueryRequest(question="เงินเดือนรวม", context=context)
        engine = MagicMock()
        engine.query = AsyncMock(side_effect=side_effect)
        with patch("app.services.query_engine.QueryEngine", return_value=engine):
            return asyncio.run(query_api.simple_query(body, request, current_user=SimpleNamespace(id=1), db=MagicMock(),
                                                      admin_config=MagicMock())), engine

    def test_key_of_workspace_a_asking_for_a_context_of_b_gets_403(self, config):
        with patch("app.services.workspaces._config_engine", return_value=config):
            with pytest.raises(HTTPException) as exc:
                self._call(_key(_ws(config, "nt-report")), context="hr_payroll",
                           side_effect=ContextNotAllowed("hr_payroll"))
        assert exc.value.status_code == 403

    def _refused(self, api_key_state):
        """Run the endpoint with an engine that refuses → (403, kwargs the engine was called with)."""
        from app.api.v1 import query as query_api

        request = SimpleNamespace(state=api_key_state, app=SimpleNamespace(state=SimpleNamespace(mcp_client=MagicMock())))
        engine = MagicMock()
        engine.query = AsyncMock(side_effect=ContextNotAllowed("stop"))
        with patch("app.services.query_engine.QueryEngine", return_value=engine), pytest.raises(HTTPException) as exc:
            asyncio.run(query_api.simple_query(query_api.SimpleQueryRequest(question="q"), request,
                                               current_user=SimpleNamespace(id=1), db=MagicMock(), admin_config=MagicMock()))
        assert exc.value.status_code == 403
        return engine.query.call_args.kwargs

    def test_the_keys_allowlist_is_what_the_engine_receives(self, config):
        with patch("app.services.workspaces._config_engine", return_value=config):
            kwargs = self._refused(SimpleNamespace(api_key=_key(_ws(config, "nt-report"))))
        assert kwargs["allowed_contexts"] == {"feed sales", "transfer price"}

    def test_session_user_is_unrestricted(self):
        assert self._refused(SimpleNamespace())["allowed_contexts"] is None


class TestRestrictedKeyStaysOnTheQueryApi:
    """/chat, /admin, … take a context too and know nothing about allowlists."""

    @pytest.mark.parametrize("path,ok", [("/api/v1/query/", True), ("/api/v1/query/contexts", True),
                                         ("/api/v1/chat/stream", False), ("/api/v1/admin/contexts", False),
                                         ("/api/v1/queryx", False)])
    def test_paths(self, path, ok):
        from app.api.deps import enforce_key_surface

        restricted, legacy = _key(1), _key()
        enforce_key_surface(legacy, path)  # pre-Phase-4 keys: everywhere, as before
        if ok:
            enforce_key_surface(restricted, path)
        else:
            with pytest.raises(HTTPException) as exc:
                enforce_key_surface(restricted, path)
            assert exc.value.status_code == 403

    def test_the_403_survives_the_auth_dependency(self):
        """get_current_user wraps key auth in `except Exception` and falls through to session auth."""
        from app.api import deps

        request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat/stream"), state=SimpleNamespace(), headers={})
        service = MagicMock()
        service.validate_key.return_value = _key(1)
        with patch("app.services.api_key_service.APIKeyService", return_value=service), pytest.raises(HTTPException) as exc:
            deps.get_current_user(request, token=None, bearer_token=None, x_api_key="ntai_x", db=MagicMock())
        assert exc.value.status_code == 403
        service.track_usage.assert_not_called()


class TestIssuingKeys:
    """Admin issues a key bound to a workspace (+ optional allowlist); a binding that can never
    work is refused at issue time, not discovered as 403s later."""

    def test_binding_resolves_names(self, config):
        from app.services.workspaces import resolve_key_binding

        ws_id, raw = resolve_key_binding("nt-report", ["feed_sales"], config)
        assert ws_id == _ws(config, "nt-report") and json.loads(raw) == ["feed_sales"]
        assert resolve_key_binding(None, None, config) == (None, None)  # unrestricted, as before
        assert resolve_key_binding("hr", None, config) == (_ws(config, "hr"), None)

    @pytest.mark.parametrize("workspace,contexts", [
        ("nope", None),                 # unknown workspace
        ("nt-report", ["hr_payroll"]),  # context of another workspace
        ("nt-report", ["missing"]),     # unknown context
        (None, ["missing"]),
        ("nt-report", []),              # a key that can reach nothing
    ])
    def test_impossible_binding_is_refused(self, config, workspace, contexts):
        from app.services.workspaces import resolve_key_binding

        with pytest.raises(ValueError):
            resolve_key_binding(workspace, contexts, config)

    def test_inactive_workspace_reaches_nothing(self, config):
        with config.begin() as conn:
            conn.execute(text("UPDATE workspaces SET is_active = 0 WHERE name = 'nt-report'"))
        assert allowed_contexts(_key(_ws(config, "nt-report")), config) == frozenset()

    def test_created_key_carries_the_binding(self, tmp_path):
        from sqlalchemy.orm import sessionmaker
        from app.db.base_class import Base
        from app.models.api_key import APIKey, APIKeyUsage
        from app.services.api_key_service import APIKeyService

        engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
        Base.metadata.create_all(engine, tables=[APIKey.__table__, APIKeyUsage.__table__])
        db = sessionmaker(bind=engine)()
        raw, key = APIKeyService(db).create_key(user_id=1, name="portal", workspace_id=7, allowed_contexts='["feed_sales"]')
        loaded = APIKeyService(db).validate_key(raw)
        assert (loaded.workspace_id, loaded.allowed_contexts) == (7, '["feed_sales"]')


class TestWorkspaceAdmin:
    def _db(self, config):
        from sqlalchemy.orm import sessionmaker
        return sessionmaker(bind=config)()

    def test_create_list_move_deactivate(self, config):
        from app.api.v1.admin import workspaces as api

        db, admin = self._db(config), SimpleNamespace(id=1)
        created = api.create_workspace(api.WorkspaceCreate(name="finance"), admin, db)
        with pytest.raises(HTTPException) as exc:
            api.create_workspace(api.WorkspaceCreate(name="finance"), admin, db)
        assert exc.value.status_code == 409

        api.move_contexts(created["id"], api.WorkspaceContexts(contexts=["transfer price"]), admin, db)
        listing = {w["name"]: w["contexts"] for w in api.list_workspaces(admin, db)}
        assert listing["finance"] == ["transfer price"] and listing["nt-report"] == ["feed_sales"]
        # the nt-report key lost the context that moved away
        assert allowed_contexts(_key(_ws(config, "nt-report")), config) == {"feed sales"}

        with pytest.raises(HTTPException) as exc:  # all or nothing
            api.move_contexts(created["id"], api.WorkspaceContexts(contexts=["feed_sales", "nope"]), admin, db)
        assert exc.value.status_code == 400
        assert allowed_contexts(_key(_ws(config, "nt-report")), config) == {"feed sales"}

        api.deactivate_workspace(created["id"], admin, db)
        assert allowed_contexts(_key(created["id"]), config) == frozenset()
        with pytest.raises(HTTPException):
            api.deactivate_workspace(_ws(config, "default"), admin, db)

    def test_workspace_name_is_a_slug(self):
        from pydantic import ValidationError
        from app.api.v1.admin.workspaces import WorkspaceCreate

        with pytest.raises(ValidationError):
            WorkspaceCreate(name="Bad Name; DROP")

    def test_issuing_a_key_with_an_impossible_binding_is_400(self, config):
        from app.api.v1.admin import api_keys as api
        from app.schemas.admin_schemas import APIKeyCreateRequest

        with patch("app.services.workspaces._config_engine", return_value=config), pytest.raises(HTTPException) as exc:
            api.create_api_key(APIKeyCreateRequest(name="k", workspace="nt-report", allowed_contexts=["hr_payroll"]),
                               SimpleNamespace(id=1), MagicMock())
        assert exc.value.status_code == 400


class TestContextListing:
    def test_restricted_key_lists_only_what_it_can_use(self, config):
        from sqlalchemy.orm import sessionmaker
        from app.api.v1 import query as query_api

        db = sessionmaker(bind=config)()
        with config.begin() as conn:
            conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN display_name TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN description TEXT"))
        service = MagicMock()
        service.validate_key.return_value = _key(_ws(config, "nt-report"))
        with patch("app.services.workspaces._config_engine", return_value=config), \
             patch("app.services.api_key_service.APIKeyService", return_value=service):
            mine = asyncio.run(query_api.list_contexts(db=db, x_api_key="ntai_x", app_db=MagicMock()))
            everyone = asyncio.run(query_api.list_contexts(db=db, x_api_key=None, app_db=MagicMock()))
        assert {c.name for c in mine} == {"feed_sales", "transfer price"}
        assert {c.name for c in everyone} == {"revenue", "feed_sales", "transfer price", "hr_payroll"}  # public, as before

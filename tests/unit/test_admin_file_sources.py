"""Plan 7 Phase 4d (REMAIN-9.6) — admin pages see a file-source context's files, not the stale
copy of the same table names that F10 imported into the legacy business DB."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.data_sources import registered_tables
from tests.unit.test_scope import env  # noqa: F401 — fixture: legacy DB + file source 'feed_x'

ADMIN = SimpleNamespace(id=1)


@pytest.fixture
def stale_copy(env):  # noqa: F811
    """The imported copy: same table name as the file-source view, other columns, old rows."""
    import app.db.session as session
    with session.business_engine.begin() as conn:
        conn.execute(text("CREATE TABLE feed_x_fact_org (year_month INT, old_column TEXT)"))
        conn.execute(text("INSERT INTO feed_x_fact_org VALUES (202605, 'stale')"))
    return env


def test_registry_lists_file_source_tables_with_their_context(stale_copy):
    tables = registered_tables(stale_copy._engine())
    assert set(tables) == {"feed_x_fact_org", "feed_x_fact_bu", "feed_x_dim_org"}
    assert tables["feed_x_fact_org"]["context"] == "feed_x"
    assert [c["name"] for c in tables["feed_x_fact_org"]["columns"]] == ["year_month", "cost_center", "revenue"]
    assert registered_tables(create_engine("sqlite://")) == {}  # registry not migrated


def test_schema_browser_inspects_the_files(stale_copy):
    from app.api.v1.admin import schema as api
    from app.db.session import business_engine
    from app.services.schema_service import SchemaService

    legacy = SchemaService(db_engine=stale_copy._engine(), business_engine=business_engine)
    with patch("app.services.data_sources.source_resolver", stale_copy):
        file_side = api.service_for_table("feed_x_fact_org", legacy)
        assert [c["name"] for c in file_side.get_table_info("feed_x_fact_org")] == ["year_month", "cost_center", "revenue"]
        assert api.service_for_table("revenue_search", legacy) is legacy  # legacy tables: as before
        assert set(api.list_tables(ADMIN, legacy)) >= {"revenue_search", "feed_x_fact_bu", "feed_x_dim_org"}


def test_onboarding_refuses_a_contract_driven_table(stale_copy):
    """Onboarding inspects the legacy DB: on a feed table it would read the stale copy and overwrite
    the knowledge generated from the contract."""
    from app.api.v1.admin import onboarding as api

    with patch("app.api.v1.admin.onboarding.registered_tables", return_value=registered_tables(stale_copy._engine())):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.onboard_context(api.OnboardingRequest(view_name="feed_x_fact_org"), ADMIN, MagicMock()))
    assert exc.value.status_code == 400 and "sources/register" in exc.value.detail


def test_brain_ddl_of_a_file_source_comes_from_the_registry(stale_copy):
    from app.services import vanna_service as vs
    from app.db.session import business_engine

    trained = []
    brain = vs.VannaService.__new__(vs.VannaService)
    brain.train = lambda ddl=None, **_: trained.append(ddl)
    service = SimpleNamespace(engine=stale_copy._engine(), business_engine=business_engine)
    brain._sync_ddl(service)
    feed = next(d for d in trained if "feed_x_fact_org" in d)
    assert "cost_center" in feed and "old_column" not in feed
    assert any("revenue_search" in d for d in trained)  # legacy views: from the business DB, as before

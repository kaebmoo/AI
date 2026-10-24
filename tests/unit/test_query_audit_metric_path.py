"""Metric compiler paths survive auditing, cache hits and legacy app schemas."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.api.v1.admin import analytics
from app.core.time_utils import utcnow
from app.models.query_audit import QueryAudit
from app.models.user import User
from app.providers.base import QueryResult
from app.schemas.admin_schemas import DashboardStatsResponse
from app.services import query_audit
from app.services import query_engine as qe
from app.services.data_sources import LEGACY_SOURCE, ScopeError
from scripts.migrate_query_audit_metric_path import migrate


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    qe._query_cache.clear()
    qe._dedup_store.clear()
    with Session(engine) as session:
        yield session
    engine.dispose()
    qe._query_cache.clear()
    qe._dedup_store.clear()


def old_table(engine, request_group=True):
    """Create the pre-metric-path schema without invoking the current model."""
    optional = ", request_group VARCHAR" if request_group else ""
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE query_audit (
            id INTEGER PRIMARY KEY, created_at DATETIME, user_id INTEGER, api_key_id INTEGER,
            channel VARCHAR, workspace VARCHAR, context_name VARCHAR, scope TEXT, question TEXT,
            sql_query TEXT, result_columns TEXT, row_count INTEGER, provider VARCHAR,
            llm_policy VARCHAR, cache_hit BOOLEAN, error TEXT, execution_time_ms FLOAT
        """ + optional + ")"))
        conn.execute(text("INSERT INTO query_audit (id, context_name, question) VALUES (1, 'revenue', 'old question')"))


@pytest.mark.parametrize("request_group", [True, False], ids=["missing-metric-path", "missing-both"])
def test_migrate_old_table_is_idempotent(db, capsys, request_group):
    engine = db.get_bind()
    old_table(engine, request_group=request_group)
    migrate(engine)
    assert capsys.readouterr().out == "Added query_audit.metric_path.\nMigration complete (idempotent).\n"
    columns = {c["name"]: str(c["type"]) for c in inspect(engine).get_columns("query_audit")}
    assert columns["metric_path"] == "TEXT" and columns["request_group"] == "VARCHAR"
    with engine.connect() as conn:
        before = conn.execute(text("SELECT * FROM query_audit")).fetchall()
        assert conn.execute(text("SELECT id, question, metric_path FROM query_audit")).one() == (1, "old question", None)
    migrate(engine)
    assert capsys.readouterr().out == "query_audit.metric_path already present.\nMigration complete (idempotent).\n"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT * FROM query_audit")).fetchall() == before


def test_migrate_empty_database_creates_table(db, capsys):
    migrate(db.get_bind())
    assert "metric_path" in {c["name"] for c in inspect(db.get_bind()).get_columns("query_audit")}
    assert db.query(QueryAudit).count() == 0
    assert capsys.readouterr().out == "Added query_audit.metric_path.\nMigration complete (idempotent).\n"


@pytest.mark.parametrize("path", ["compiled:ebt", "declined:shape:ordering:revenue", None])
def test_record_upgrades_old_table_and_writes_path(db, path):
    old_table(db.get_bind())
    assert query_audit.record(db, context_name="revenue", question="new question", metric_path=path) is True
    old, new = db.query(QueryAudit).order_by(QueryAudit.id).all()
    assert old.question == "old question" and old.metric_path is None
    assert new.question == "new question" and new.metric_path == path


ANSWER = QueryResult(question="ยอดขายเดือนนี้", sql_query="SELECT total FROM t", data=[{"total": 2}],
                     explanation="", tokens_used=0, provider="matcha")


def run(db, stages=None, raises=None, **kwargs):
    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
    admin_config.get_feature_flags.return_value = {}
    admin_config.get_provider_record.return_value = None
    engine = qe.QueryEngine(mcp_client=MagicMock(), db_session=db, admin_config=admin_config)
    engine._schema_service = MagicMock()
    engine._schema_service.build_system_prompt.return_value = "prompt"
    provider = MagicMock()
    provider.get_model.return_value = None

    async def hybrid(**kw):
        kw["trace"].stages.update(stages or {})
        if raises is not None:
            raise raises
        return ANSWER

    ai_service = MagicMock()
    ai_service.query_hybrid = AsyncMock(side_effect=hybrid)
    detector = MagicMock()
    detector.detect = AsyncMock(return_value=[])
    resolver = MagicMock()
    resolver.for_context.return_value = LEGACY_SOURCE
    qe._dedup_store.clear()
    with patch.object(qe, "source_resolver", resolver), patch.object(qe, "stores_results", return_value=True), \
         patch.object(qe, "workspace_of_context", return_value="nt-report"), \
         patch.object(qe.provider_registry, "create_provider", return_value=provider), \
         patch.object(qe, "AIService", return_value=ai_service), patch.object(qe, "WarningDetector", return_value=detector):
        return asyncio.run(engine.query("ยอดขายเดือนนี้", context="revenue", **kwargs))


@pytest.mark.parametrize("stages, expected", [
    ({"metric_compiled": "ebt"}, "compiled:ebt"),
    ({"metric_declined": "shape:ordering:revenue"}, "declined:shape:ordering:revenue"),
    ({"metric_compiled": "revenue", "metric_declined": "no_metric"}, "compiled:revenue"),
    ({}, None),
])
def test_engine_trace_reaches_result_and_audit(db, stages, expected):
    result = run(db, stages=stages)
    assert result.metric_path == expected
    row = db.query(QueryAudit).one()
    assert row.metric_path == expected and row.cache_hit is False


@pytest.mark.parametrize("stages, expected", [
    ({"metric_compiled": "ebt"}, "compiled:ebt"),
    ({"metric_declined": "no_metric"}, "declined:no_metric"),
])
def test_cache_hit_preserves_metric_path(db, stages, expected):
    first = run(db, stages=stages)
    second = run(db, raises=AssertionError("cache miss"))
    assert first.metric_path == second.metric_path == expected
    assert first.cache_hit is False and second.cache_hit is True
    rows = db.query(QueryAudit).order_by(QueryAudit.id).all()
    assert [(r.metric_path, r.cache_hit) for r in rows] == [(expected, False), (expected, True)]


@pytest.mark.parametrize("error", [ScopeError("refused"), RuntimeError("failed")])
def test_exception_or_refusal_has_no_metric_path(db, error):
    with pytest.raises(type(error), match=str(error)):
        run(db, stages={"metric_declined": "no_metric"}, raises=error)
    row = db.query(QueryAudit).one()
    assert row.metric_path is None and row.error.startswith(type(error).__name__)


def test_metric_path_stats_filters_counts_and_orders_reasons(db):
    query_audit.ensure_table(db.get_bind())
    now = utcnow()
    since = now - timedelta(days=7)

    def add(path, count=1, context="feed_sales", channel="chat", created_at=now):
        db.add_all([QueryAudit(context_name=context, channel=channel, metric_path=path, created_at=created_at)
                    for _ in range(count)])

    add("compiled:ebt", 2)
    add("compiled:revenue", channel=None)
    add("compiled:boundary", created_at=since)
    add(None)
    for path in ["", "other", "compiled", "declined", "Compiled:ebt"]:
        add(path)
    for reason, count in [("zulu", 6), ("shape:ordering:revenue", 5), ("delta", 4),
                          ("charlie", 3), ("bravo", 2), ("alpha", 1)]:
        add(f"declined:{reason}", count)
    add(None, context="revenue", channel=None)
    for reason in ["zeta", "alpha", "beta"]:
        add(f"declined:{reason}", context="revenue")
    add("compiled:old", created_at=since - timedelta(microseconds=1))
    add("declined:old", created_at=since - timedelta(days=1))
    for channel in ["report_download", "report_export", "dsr_erase"]:
        add("compiled:excluded", channel=channel)
        add("declined:excluded", channel=channel)
        add(None, channel=channel)
        add("compiled:excluded", channel=channel, context="excluded_only")
    add("compiled:ebt", context=None)
    db.commit()

    assert analytics._metric_path_stats(db, since) == {
        "feed_sales": {"compiled": 4, "declined": 21, "none": 6, "top_declined": [
            {"reason": "zulu", "count": 6},
            {"reason": "shape:ordering:revenue", "count": 5},
            {"reason": "delta", "count": 4},
            {"reason": "charlie", "count": 3},
            {"reason": "bravo", "count": 2},
        ]},
        "revenue": {"compiled": 0, "declined": 3, "none": 1, "top_declined": [
            {"reason": "alpha", "count": 1},
            {"reason": "beta", "count": 1},
            {"reason": "zeta", "count": 1},
        ]},
    }


def test_dashboard_stats_upgrades_old_table(db):
    old_table(db.get_bind())
    User.__table__.create(db.get_bind())
    now = utcnow()
    with db.get_bind().begin() as conn:
        conn.execute(text("UPDATE query_audit SET created_at = :now, channel = NULL"), {"now": now})
    config_db = MagicMock()
    config_db.query.return_value.count.side_effect = [2, 3, 4]
    with patch.object(analytics, "utcnow", return_value=now):
        result = analytics.get_dashboard_stats(_current_user=MagicMock(), config_db=config_db, app_db=db)
    assert isinstance(result, DashboardStatsResponse)
    assert result.model_dump() == {
        "total_users": 0, "total_mappings": 2, "total_rules": 3, "total_columns": 4,
        "metric_path": {"revenue": {"compiled": 0, "declined": 0, "none": 1, "top_declined": []}},
    }
    assert db.query(QueryAudit).one().metric_path is None

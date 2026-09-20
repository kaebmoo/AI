"""Plan 7 Phase 4.5 — retention of stored result rows (purge job + "don't store" mode)."""

import os
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.time_utils import utcnow
from app.db.base_class import Base
from app.models.chat import ChatHistory
from app.models.chat_session import ChatSessionData
from app.services import retention
from scripts.migrate_workspaces import migrate as migrate_workspaces

NOW = utcnow()


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    import app.models  # noqa: F401 — every table of the app DB (FK targets)
    app_engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(app_engine)
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_contexts (name) VALUES ('revenue'), ('feed_x')"))
    migrate_workspaces(config)
    with config.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (name) VALUES ('short')"))
        conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name = 'short') "
                          "WHERE name = 'feed_x'"))
    monkeypatch.setattr(retention, "_global_settings", lambda: (30, True))
    monkeypatch.setattr(retention, "TEMP_EXPORT_DIR", str(tmp_path / "nt_reports"))
    return sessionmaker(bind=app_engine)(), config


def add(db, age_days, context="revenue"):
    row = ChatHistory(user_id=1, question="q", generated_sql="SELECT 1", ai_response="คำตอบ", context_name=context,
                      sql_result_summary="[{'a': 1}]", result_data='[{"a": 1}]', render_meta='{"total_rows": 1}',
                      created_at=NOW - timedelta(days=age_days))
    db.add(row)
    db.commit()
    return row.id


def test_purge_drops_old_rows_keeps_metadata_and_is_idempotent(dbs, tmp_path):
    db, config = dbs
    old, fresh = add(db, 31), add(db, 29)
    db.add_all([ChatSessionData(conversation_id="old", last_data="[1]", last_columns="[]", updated_at=NOW - timedelta(days=40)),
                ChatSessionData(conversation_id="new", last_data="[1]", last_columns="[]", updated_at=NOW)])
    db.commit()
    os.makedirs(retention.TEMP_EXPORT_DIR)
    stale, recent = (os.path.join(retention.TEMP_EXPORT_DIR, n) for n in ("old.csv", "new.csv"))
    for path in (stale, recent):
        open(path, "w").close()
    os.utime(stale, (time.time() - 40 * 86400,) * 2)

    done = retention.purge_results(db, config, now=NOW)
    assert done == {"chat_history": 1, "chat_session_data": 1, "query_correction_log": 0, "temp_files": 1}
    purged, kept = db.get(ChatHistory, old), db.get(ChatHistory, fresh)
    assert purged.result_data is None and purged.sql_result_summary is None
    # hardening: the answer is business data in prose and expires with the rows; the rest stays
    assert (purged.question, purged.generated_sql, purged.render_meta) == ("q", "SELECT 1", '{"total_rows": 1}')
    assert purged.ai_response == retention.EXPIRED_ANSWER and kept.ai_response == "คำตอบ"
    assert kept.result_data and kept.sql_result_summary
    assert [r.conversation_id for r in db.query(ChatSessionData)] == ["new"]
    assert not os.path.exists(stale) and os.path.exists(recent)
    assert not any(retention.purge_results(db, config, now=NOW).values())  # nothing left to do


def test_workspace_override_and_zero_means_never(dbs, monkeypatch):
    db, config = dbs
    with config.begin() as conn:
        conn.execute(text("UPDATE workspaces SET result_retention_days = 7 WHERE name = 'short'"))
    short_old, short_new, default_mid = add(db, 8, "feed_x"), add(db, 6, "feed_x"), add(db, 8, "revenue")
    assert retention.purge_results(db, config, now=NOW)["chat_history"] == 1
    assert db.get(ChatHistory, short_old).result_data is None
    assert db.get(ChatHistory, short_new).result_data and db.get(ChatHistory, default_mid).result_data

    monkeypatch.setattr(retention, "_global_settings", lambda: (0, True))  # global off, the override still runs
    ancient = add(db, 4000, "revenue")
    add(db, 9, "feed_x")
    assert retention.purge_results(db, config, now=NOW)["chat_history"] == 1
    assert db.get(ChatHistory, ancient).result_data


def test_correction_log_is_purged_when_it_exists(dbs):
    db, config = dbs
    db.execute(text("CREATE TABLE query_correction_log (id INTEGER PRIMARY KEY, correct_value TEXT, created_at TIMESTAMP)"))
    db.execute(text("INSERT INTO query_correction_log (correct_value, created_at) VALUES ('v', :old), ('v', :new)"),
               {"old": retention._stamp(NOW - timedelta(days=31)), "new": retention._stamp(NOW)})
    db.commit()
    assert retention.purge_results(db, config, now=NOW)["query_correction_log"] == 1


def test_store_result_data_off_globally_or_per_workspace(dbs, monkeypatch):
    _db, config = dbs
    assert retention.stores_results("revenue", config) and retention.stores_results(None, config)
    with config.begin() as conn:
        conn.execute(text("UPDATE workspaces SET store_result_data = 0 WHERE name = 'short'"))
    assert not retention.stores_results("feed_x", config) and retention.stores_results("revenue", config)
    monkeypatch.setattr(retention, "_global_settings", lambda: (30, False))
    assert not retention.stores_results("revenue", config)
    with config.begin() as conn:
        conn.execute(text("UPDATE workspaces SET store_result_data = 1 WHERE name = 'short'"))
    assert retention.stores_results("feed_x", config)  # the workspace's own answer wins both ways


def test_global_settings_parse_what_the_admin_api_stores(monkeypatch):
    values = {}
    svc = type("Svc", (), {"get_config": lambda self, key, *a: values.get(key), "close": lambda self: None})
    monkeypatch.setattr("app.services.admin_config_service.AdminConfigService", svc)
    assert retention._global_settings() == (30, True)  # nothing configured = the owner's default
    values.update(result_retention_days="90.0", store_result_data="false")
    assert retention._global_settings() == (90, False)
    values.update(result_retention_days="0", store_result_data="true")
    assert retention._global_settings() == (0, True)
    values.update(result_retention_days="soon")
    assert retention._global_settings() == (30, True)


def test_chat_history_is_written_without_rows_when_storing_is_off(dbs):
    from app.api.v1 import chat
    from app.providers.base import QueryResult
    from app.services.query_engine import QueryEngineResult

    db, _config = dbs
    result = QueryEngineResult(context_name="feed_x", query_result=QueryResult(
        question="q", sql_query="SELECT 1", data=[{"secret": "ZQX"}], explanation="พบ 1 รายการ", tokens_used=0, provider="m"))
    with patch.object(chat, "stores_results", return_value=False):
        entry = chat._save_history(db, 1, None, result)
        chat._persist_render_payload(db, entry, {"data": [{"secret": "ZQX"}], "visualization": "table"})
    assert entry.sql_result_summary is None and entry.result_data is None
    assert entry.generated_sql == "SELECT 1" and "total_rows" in entry.render_meta
    with patch.object(chat, "stores_results", return_value=True):
        entry = chat._save_history(db, 1, None, result)
        chat._persist_render_payload(db, entry, {"data": [{"secret": "ZQX"}]})
    assert "ZQX" in entry.sql_result_summary and "ZQX" in entry.result_data


def test_query_cache_holds_no_rows_when_storing_is_off():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.providers.base import QueryResult
    from app.services import query_engine as qe
    from app.services.data_sources import LEGACY_SOURCE

    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
    admin_config.get_feature_flags.return_value = {}
    admin_config.get_provider_record.return_value = None
    engine = qe.QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
    engine._schema_service = MagicMock()
    engine._schema_service.build_system_prompt.return_value = "prompt"
    provider = MagicMock()
    provider.get_model.return_value = None
    ai_service = MagicMock()
    ai_service.query_hybrid = AsyncMock(return_value=QueryResult(
        question="q", sql_query="SELECT 1", data=[{"n": 1}], explanation="", tokens_used=0, provider="matcha"))
    detector = MagicMock()
    detector.detect = AsyncMock(return_value=[])
    resolver = MagicMock()
    resolver.for_context.return_value = LEGACY_SOURCE
    for stores, cached in ((False, 0), (True, 1)):
        qe._query_cache.clear()
        qe._dedup_store.clear()
        with patch.object(qe, "source_resolver", resolver), patch.object(qe, "stores_results", return_value=stores), \
             patch.object(qe.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe, "AIService", return_value=ai_service), patch.object(qe, "WarningDetector", return_value=detector):
            asyncio.run(engine.query("q", context="revenue"))
        assert len(qe._query_cache) == cached
    qe._query_cache.clear()
    qe._dedup_store.clear()


def test_the_answer_expires_on_the_same_clock_as_the_rows(dbs, monkeypatch):
    """The answer text is the business data written out in prose — it cannot outlive the rows."""
    db, config = dbs
    with config.begin() as conn:
        conn.execute(text("UPDATE workspaces SET result_retention_days = 7 WHERE name = 'short'"))
    short_old, short_new = add(db, 8, "feed_x"), add(db, 6, "feed_x")
    # an old row whose result data was already purged before this change: only the answer is left to do
    answer_only = add(db, 31)
    db.get(ChatHistory, answer_only).result_data = None
    db.get(ChatHistory, answer_only).sql_result_summary = None
    db.commit()

    assert retention.purge_results(db, config, now=NOW)["chat_history"] == 2
    assert db.get(ChatHistory, short_old).ai_response == retention.EXPIRED_ANSWER
    assert db.get(ChatHistory, answer_only).ai_response == retention.EXPIRED_ANSWER
    assert db.get(ChatHistory, short_new).ai_response == "คำตอบ"
    assert not any(retention.purge_results(db, config, now=NOW).values())  # idempotent

    monkeypatch.setattr(retention, "_global_settings", lambda: (0, True))  # 0 = keep forever
    ancient = add(db, 4000)
    assert retention.purge_results(db, config, now=NOW)["chat_history"] == 0
    assert db.get(ChatHistory, ancient).ai_response == "คำตอบ"


def test_an_expired_answer_is_not_handed_to_the_model_as_the_previous_turn(dbs):
    """It is a tombstone, not something the assistant said — a follow-up must not read it as context."""
    from app.api.v1.chat import _get_conversation_history

    db, _config = dbs
    for minute, (answer, sql) in enumerate(((retention.EXPIRED_ANSWER, "SELECT 1"), ("รายได้ 5 บาท", "SELECT 2"),
                                            (retention.EXPIRED_ANSWER, None))):
        db.add(ChatHistory(user_id=1, conversation_id="c", question="q", generated_sql=sql,
                           ai_response=answer, created_at=NOW + timedelta(minutes=minute)))
    db.commit()

    history, _rows = _get_conversation_history(db, "c", 1)
    said = [turn["content"] for turn in history if turn["role"] == "assistant"]
    assert retention.EXPIRED_ANSWER not in " ".join(said)
    assert said == ["```sql\nSELECT 1\n```", "```sql\nSELECT 2\n```\n\nรายได้ 5 บาท"]  # no empty turn

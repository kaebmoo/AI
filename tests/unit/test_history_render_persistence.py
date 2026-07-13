"""
F12: Tests for chat_history render payload persistence (render_meta/result_data)
and its restore path via GET /conversations/{id}.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.api.v1.chat import _persist_render_payload, _persist_chart_only_switch
from app.api.v1.conversations import _safe_json
from app.config import settings
from app.models.chat import ChatHistory
from app.models.conversation import Conversation
from app.models.session import UserSession


# ============================================================
# _persist_render_payload
# ============================================================

def _make_chat_entry(db_session, user_id):
    entry = ChatHistory(
        user_id=user_id,
        question="รายได้รวม",
        generated_sql="SELECT 1",
        ai_response="รายได้รวม 100 บาท",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


class TestPersistRenderPayload:
    def test_full_response_persists_all_fields(self, db_session, test_user):
        chat_entry = _make_chat_entry(db_session, test_user.id)
        response_data = {
            "data": [{"month": 1, "total": 100}, {"month": 2, "total": 200}],
            "visualization": "bar_chart",
            "chart_config": {"category_column": "month", "measure_column": "total", "max_series": 5},
            "display_hint": "flat",
            "hierarchy_columns": None,
            "warnings": [{"code": "w1", "message": "msg", "severity": "info"}],
            "confidence": {"score": 90, "level": "high", "level_th": "สูง", "color": "green", "factors": [], "recommendation": "ok"},
        }

        _persist_render_payload(db_session, chat_entry, response_data)

        meta = json.loads(chat_entry.render_meta)
        assert meta["visualization"] == "bar_chart"
        assert meta["chart_config"]["max_series"] == 5
        assert meta["display_hint"] == "flat"
        assert meta["hierarchy_columns"] is None
        assert meta["warnings"] == response_data["warnings"]
        assert meta["confidence"] == response_data["confidence"]
        assert meta["data_truncated"] is False
        assert meta["total_rows"] == 2

        stored_data = json.loads(chat_entry.result_data)
        assert stored_data == response_data["data"]

    def test_row_cap_truncates_and_flags(self, db_session, test_user, monkeypatch):
        monkeypatch.setattr(settings, "HISTORY_RENDER_MAX_ROWS", 1000)
        chat_entry = _make_chat_entry(db_session, test_user.id)
        big_data = [{"i": i} for i in range(1500)]
        response_data = {"data": big_data, "visualization": "bar_chart", "chart_config": {}}

        _persist_render_payload(db_session, chat_entry, response_data)

        meta = json.loads(chat_entry.render_meta)
        assert meta["data_truncated"] is True
        assert meta["total_rows"] == 1500

        stored_data = json.loads(chat_entry.result_data)
        assert len(stored_data) == 1000

    def test_text_only_response_has_null_result_data(self, db_session, test_user):
        chat_entry = _make_chat_entry(db_session, test_user.id)
        response_data = {"data": None, "visualization": None, "chart_config": None}

        _persist_render_payload(db_session, chat_entry, response_data)

        assert chat_entry.result_data is None
        meta = json.loads(chat_entry.render_meta)
        assert meta["visualization"] is None
        assert meta["total_rows"] == 0

    def test_commit_failure_is_non_fatal_and_rolls_back(self):
        chat_entry = MagicMock()
        db = MagicMock()
        db.commit.side_effect = Exception("db exploded")

        # Must not raise
        _persist_render_payload(db, chat_entry, {"data": [{"a": 1}], "visualization": "bar_chart"})

        db.rollback.assert_called_once()


# ============================================================
# _safe_json
# ============================================================

class TestSafeJson:
    def test_none_returns_default(self):
        assert _safe_json(None) is None
        assert _safe_json(None, {}) == {}

    def test_empty_string_returns_default(self):
        assert _safe_json("") is None

    def test_valid_json_parses(self):
        assert _safe_json('{"a": 1}') == {"a": 1}

    def test_corrupted_json_returns_default_not_raise(self):
        assert _safe_json("{broken") is None
        assert _safe_json("{broken", {}) == {}


# ============================================================
# _persist_chart_only_switch (Phase C)
# ============================================================

class TestPersistChartOnlySwitch:
    def test_updates_latest_row_render_meta(self, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="chart switch")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        entry = ChatHistory(
            user_id=test_user.id,
            conversation_id=conv.id,
            question="รายได้รวม",
            ai_response="ตอบ",
            render_meta=json.dumps({
                "visualization": "bar_chart",
                "chart_config": {"category_column": "month"},
                "total_rows": 3,
            }, ensure_ascii=False),
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        _persist_chart_only_switch(
            db_session, conv.id,
            {"visualization": "pie_chart", "chart_config": {"category_column": "month", "max_series": 5}},
        )

        db_session.refresh(entry)
        meta = json.loads(entry.render_meta)
        assert meta["visualization"] == "pie_chart"
        assert meta["chart_config"]["max_series"] == 5
        # Untouched fields survive the update
        assert meta["total_rows"] == 3

    def test_no_render_meta_row_does_not_crash(self, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="no render_meta yet")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        # No ChatHistory row at all for this conversation
        _persist_chart_only_switch(db_session, conv.id, {"visualization": "pie_chart", "chart_config": {}})
        # Just must not raise

    def test_commit_failure_is_non_fatal(self, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="commit fails")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        entry = ChatHistory(
            user_id=test_user.id,
            conversation_id=conv.id,
            question="q",
            ai_response="a",
            render_meta=json.dumps({"visualization": "bar_chart"}),
        )
        db_session.add(entry)
        db_session.commit()

        with pytest.MonkeyPatch.context() as mp:
            def boom():
                raise Exception("db exploded")
            mp.setattr(db_session, "commit", boom)
            # Must not raise
            _persist_chart_only_switch(db_session, conv.id, {"visualization": "pie_chart", "chart_config": {}})


# ============================================================
# GET /conversations/{id} — restore path
# ============================================================

@pytest.fixture
def conv_auth(client, test_user, db_session):
    session = UserSession(
        user_id=test_user.id,
        session_token="conv_render_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "conv_render_token"
    return client


class TestConversationRestoreEndpoint:
    def test_legacy_row_null_render_fields_no_error(self, conv_auth, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="legacy")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        entry = ChatHistory(
            user_id=test_user.id,
            conversation_id=conv.id,
            question="เก่า",
            ai_response="คำตอบเก่า",
        )
        db_session.add(entry)
        db_session.commit()

        resp = conv_auth.get(f"/api/v1/conversations/{conv.id}")
        assert resp.status_code == 200
        msg = resp.json()["messages"][0]
        assert msg["data"] is None
        assert msg["visualization"] is None
        assert msg["chart_config"] is None
        assert msg["data_truncated"] is False

    def test_corrupted_render_meta_returns_none_not_500(self, conv_auth, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="broken")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        entry = ChatHistory(
            user_id=test_user.id,
            conversation_id=conv.id,
            question="พัง",
            ai_response="คำตอบ",
            render_meta="{broken",
            result_data="{broken",
        )
        db_session.add(entry)
        db_session.commit()

        resp = conv_auth.get(f"/api/v1/conversations/{conv.id}")
        assert resp.status_code == 200
        msg = resp.json()["messages"][0]
        assert msg["data"] is None
        assert msg["visualization"] is None

    def test_full_render_payload_restored(self, conv_auth, db_session, test_user):
        conv = Conversation(user_id=test_user.id, title="full")
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        meta = {
            "visualization": "pie_chart",
            "chart_config": {"category_column": "month", "max_series": 5},
            "display_hint": "flat",
            "hierarchy_columns": ["a", "b"],
            "warnings": [{"code": "w", "message": "m", "severity": "info"}],
            "confidence": {"score": 80},
            "data_truncated": False,
            "total_rows": 1,
        }
        entry = ChatHistory(
            user_id=test_user.id,
            conversation_id=conv.id,
            question="เต็ม",
            ai_response="คำตอบเต็ม",
            render_meta=json.dumps(meta, ensure_ascii=False),
            result_data=json.dumps([{"month": 1, "total": 100}], ensure_ascii=False),
        )
        db_session.add(entry)
        db_session.commit()

        resp = conv_auth.get(f"/api/v1/conversations/{conv.id}")
        assert resp.status_code == 200
        msg = resp.json()["messages"][0]
        assert msg["data"] == [{"month": 1, "total": 100}]
        assert msg["visualization"] == "pie_chart"
        assert msg["chart_config"]["max_series"] == 5
        assert msg["hierarchy_columns"] == ["a", "b"]
        assert msg["data_truncated"] is False

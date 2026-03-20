"""
Plan 1: Admin Agent API Integration Tests
==========================================
Tests the admin agent API endpoints with auth checks.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime


class TestAdminAgentAPI:
    """Integration tests for POST /admin/agent/chat and /confirm."""

    def test_agent_chat_no_auth(self, client):
        """POST /admin/agent/chat without auth → 401."""
        resp = client.post("/api/v1/admin/agent/chat", json={"message": "test"})
        assert resp.status_code == 401

    def test_agent_chat_user_role(self, client, test_session, db_session):
        """POST /admin/agent/chat with non-admin user → 403."""
        db_session.refresh(test_session)
        client.headers["X-Session-Token"] = test_session.session_token
        resp = client.post("/api/v1/admin/agent/chat", json={"message": "test"})
        assert resp.status_code == 403

    def test_agent_chat_admin_success(self, client, admin_user, db_session):
        """POST /admin/agent/chat as admin → 200 with response."""
        from app.models.session import UserSession

        session = UserSession(
            user_id=admin_user.id,
            session_token="admin_token_xyz",
            platform="web",
            expires_at=datetime.utcnow() + __import__("datetime").timedelta(hours=24),
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()
        client.headers["X-Session-Token"] = "admin_token_xyz"

        mock_result = {
            "response": "ค้นหา mapping สำหรับ datacom ไม่พบ",
            "tool_calls": [],
            "pending_confirmation": None,
            "conversation_id": 1,
        }

        with patch("app.api.v1.admin_agent.AdminAgent") as MockAgent:
            instance = MockAgent.return_value
            instance.chat = AsyncMock(return_value=mock_result)
            resp = client.post(
                "/api/v1/admin/agent/chat",
                json={"message": "มี mapping สำหรับ datacom ไหม"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data

    def test_agent_chat_with_conversation_id(self, client, admin_user, db_session):
        """POST /admin/agent/chat with conversation_id → uses history."""
        from app.models.session import UserSession

        session = UserSession(
            user_id=admin_user.id,
            session_token="admin_conv_token",
            platform="web",
            expires_at=datetime.utcnow() + __import__("datetime").timedelta(hours=24),
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()
        client.headers["X-Session-Token"] = "admin_conv_token"

        mock_result = {
            "response": "เพิ่ม mapping เรียบร้อย",
            "tool_calls": [{"tool_name": "add_mapping", "tool_args": {"keyword": "datacom"}, "result": {"success": True}}],
            "pending_confirmation": None,
            "conversation_id": 42,
        }

        with patch("app.api.v1.admin_agent.AdminAgent") as MockAgent:
            instance = MockAgent.return_value
            instance.chat = AsyncMock(return_value=mock_result)
            resp = client.post(
                "/api/v1/admin/agent/chat",
                json={"message": "เพิ่ม mapping datacom", "conversation_id": 42},
            )

        assert resp.status_code == 200

    def test_agent_confirm_action(self, client, admin_user, db_session):
        """POST /admin/agent/chat/{id}/confirm → executes pending action."""
        from app.models.session import UserSession

        session = UserSession(
            user_id=admin_user.id,
            session_token="admin_confirm_token",
            platform="web",
            expires_at=datetime.utcnow() + __import__("datetime").timedelta(hours=24),
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()
        client.headers["X-Session-Token"] = "admin_confirm_token"

        mock_result = {
            "response": "เพิ่ม mapping เรียบร้อยแล้ว",
            "tool_calls": [{"tool_name": "add_mapping", "tool_args": {"keyword": "datacom"}, "result": {"success": True}}],
            "pending_confirmation": None,
            "conversation_id": 1,
        }

        with patch("app.api.v1.admin_agent.AdminAgent") as MockAgent:
            instance = MockAgent.return_value
            instance.confirm_action = AsyncMock(return_value=mock_result)
            resp = client.post(
                "/api/v1/admin/agent/chat/1/confirm",
                json={"confirmed": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data

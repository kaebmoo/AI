"""
Unit Tests for Admin Agent Dispatcher (Plan 1)
================================================
Tests for the admin agent service logic (tool selection, confirmation flow, conversation).
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from tests.unit import knowledge_db


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def agent_db(tmp_path):
    """Create temp DB with both config tables and agent tables."""
    import sqlite3
    db_path = str(tmp_path / "agent_test.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Admin agent tables
    c.execute("""
        CREATE TABLE admin_agent_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE admin_agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT DEFAULT '',
            tool_name TEXT,
            tool_args TEXT,
            tool_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Config tables — match actual ORM models
    c.execute("""
        CREATE TABLE schema_semantic_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            keyword_type TEXT DEFAULT 'term',
            target_column TEXT NOT NULL,
            target_condition TEXT NOT NULL DEFAULT '',
            full_condition TEXT,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            context_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('test', 'COL', '= ''val''')")

    conn.commit()
    conn.close()
    knowledge_db.add_provenance(db_path)  # Plan 8.1 columns the models select
    return db_path


@pytest.fixture
def agent_session(agent_db):
    """Create SQLAlchemy session from temp DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{agent_db}")
    session = SASession(engine)
    # the agent opens a session per tool (tool_session) — keep those on the temp DB too
    factory = sessionmaker(bind=engine)
    with patch("app.db.session.ConfigSessionLocal", factory), patch("app.db.session.SessionLocal", factory):
        yield session
    session.close()


def _mock_llm_tool_call(tool_name, tool_args):
    """Helper: mock LLM response that calls a tool."""
    return json.dumps({"tool_call": {"name": tool_name, "arguments": tool_args}})


def _mock_llm_text(text):
    """Helper: mock LLM response with plain text."""
    return text


# ── Agent Tests ───────────────────────────────────────────

class TestAdminAgent:

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_selects_search_mapping_tool(self, mock_llm, agent_session):
        """Agent selects search_mappings when asked about mappings."""
        mock_llm.return_value = {
            "text": "",
            "tool_calls": [{"name": "search_mappings", "arguments": {"keyword": "datacom"}}],
            "tokens_used": 100,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result = await agent.chat("มี mapping สำหรับ datacom ไหม", user_id=1)

        assert result["conversation_id"] > 0
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "search_mappings"

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_selects_add_mapping_tool(self, mock_llm, agent_session):
        """Agent selects add_mapping when asked to add."""
        mock_llm.return_value = {
            "text": "",
            "tool_calls": [{"name": "add_mapping", "arguments": {
                "keyword": "datacom",
                "target_column": "SERVICE_GROUP",
                "target_value": "Datacom",
            }}],
            "tokens_used": 100,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result = await agent.chat("เพิ่ม mapping datacom ไป service_group", user_id=1)

        # add_mapping requires confirmation
        assert result["pending_confirmation"] is not None
        assert result["pending_confirmation"]["tool_name"] == "add_mapping"

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_asks_confirmation_before_add(self, mock_llm, agent_session):
        """Tools with requires_confirmation=True trigger confirmation flow."""
        mock_llm.return_value = {
            "text": "",
            "tool_calls": [{"name": "add_rule", "arguments": {
                "rule_code": "TEST_001",
                "description": "test rule",
                "rule_category": "filter",
            }}],
            "tokens_used": 100,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result = await agent.chat("เพิ่ม rule TEST_001", user_id=1)

        assert result["pending_confirmation"] is not None
        assert result["tool_calls"] == []  # Not executed yet

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_executes_after_confirmation(self, mock_llm, agent_session):
        """After confirmation, pending tool is executed."""
        # First: set up a pending action
        mock_llm.return_value = {
            "text": "",
            "tool_calls": [{"name": "add_mapping", "arguments": {
                "keyword": "new_kw",
                "target_column": "COL",
                "target_value": "val",
            }}],
            "tokens_used": 100,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result1 = await agent.chat("เพิ่ม mapping new_kw", user_id=1)
        conv_id = result1["conversation_id"]

        # Then: confirm
        result2 = await agent.confirm_action(conv_id, user_id=1)

        assert len(result2["tool_calls"]) == 1
        assert result2["tool_calls"][0]["result"]["success"] is True

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_direct_answer(self, mock_llm, agent_session):
        """Agent answers directly when no tool is needed."""
        mock_llm.return_value = {
            "text": "MCP คือ Model Context Protocol ใช้สำหรับเชื่อมต่อ AI กับ tools ภายนอก",
            "tool_calls": [],
            "tokens_used": 50,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result = await agent.chat("MCP คืออะไร", user_id=1)

        assert "MCP" in result["response"]
        assert result["tool_calls"] == []
        assert result["pending_confirmation"] is None

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_no_suitable_tool(self, mock_llm, agent_session):
        """Agent handles requests outside its capabilities."""
        mock_llm.return_value = {
            "text": "ขออภัย ระบบไม่สามารถสั่งอาหารได้ ระบบนี้ใช้สำหรับจัดการ configuration ของ NT AI เท่านั้น",
            "tool_calls": [],
            "tokens_used": 50,
        }

        from app.services.admin_agent import AdminAgent
        agent = AdminAgent(agent_session)
        result = await agent.chat("ช่วยสั่งอาหารหน่อย", user_id=1)

        assert "ไม่สามารถ" in result["response"] or "ขออภัย" in result["response"]

    @patch("app.services.admin_agent.AdminAgent._call_llm")
    async def test_agent_saves_conversation(self, mock_llm, agent_session):
        """Conversation and messages are persisted to DB."""
        mock_llm.return_value = {
            "text": "สวัสดีครับ",
            "tool_calls": [],
            "tokens_used": 30,
        }

        from app.services.admin_agent import AdminAgent
        from app.models.admin_agent import AdminAgentConversation, AdminAgentMessage

        agent = AdminAgent(agent_session)
        result = await agent.chat("สวัสดี", user_id=1)

        conv_id = result["conversation_id"]

        # Verify conversation exists
        conv = agent_session.query(AdminAgentConversation).filter(
            AdminAgentConversation.id == conv_id
        ).first()
        assert conv is not None
        assert conv.user_id == 1

        # Verify messages exist
        messages = agent_session.query(AdminAgentMessage).filter(
            AdminAgentMessage.conversation_id == conv_id
        ).all()
        assert len(messages) >= 2  # user + assistant
        roles = [m.role for m in messages]
        assert "user" in roles
        assert "assistant" in roles

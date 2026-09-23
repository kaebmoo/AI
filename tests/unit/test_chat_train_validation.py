"""REMAIN-9.2: /chat/train rejects SQL that fails on the context's own source."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1 import chat
from app.schemas.chat import TrainingRequest
from app.services.data_sources import LEGACY_SOURCE, SourceBoundMCPClient


def _train(payload, context="revenue", source=LEGACY_SOURCE):
    mcp = MagicMock()
    mcp.call_tool = AsyncMock(return_value=json.dumps(payload))  # MCP returns JSON text
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None  # no example yet
    with patch.object(chat.deps, "get_mcp_client", return_value=mcp), \
         patch.object(chat.source_resolver, "for_context", return_value=source):
        result = asyncio.run(chat.train_model(
            TrainingRequest(question="q", sql="SELECT x FROM t", context=context), MagicMock(),
            MagicMock(role="user", is_superuser=False), MagicMock(), db))
    return result, mcp, db


def test_failing_sql_is_rejected_before_saving():
    with pytest.raises(HTTPException) as exc:
        _train({"success": False, "error": "no such table: t", "data": []})
    assert exc.value.status_code == 400 and "no such table" in exc.value.detail


def test_valid_sql_is_saved():
    result, mcp, db = _train({"success": True, "data": [], "row_count": 0})
    assert result["success"] and db.add.called
    mcp.call_tool.assert_awaited_once()


def test_file_source_context_validates_on_its_own_source():
    source = MagicMock(adapter=MagicMock())
    with patch.object(SourceBoundMCPClient, "call_tool", AsyncMock(return_value=json.dumps(
            {"success": False, "error": "Only registered views can be queried on a file source: t"}))) as bound:
        with pytest.raises(HTTPException):
            _train({"success": True}, context="feed_revenue", source=source)
    bound.assert_awaited_once()

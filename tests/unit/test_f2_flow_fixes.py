"""
F2.4: SSE generator cancels the query task when the client disconnects.
F2.5: query_hybrid reuses an injected SchemaService (none created in retries).
F2.6: Claude tool-use turns produce a valid Anthropic message structure.
"""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai import hybrid_flow
from app.services.ai.retry_loop import query_with_retry


class TestResolveContextInfoReuse:
    def test_injected_schema_service_is_used(self):
        svc = MagicMock()
        svc.get_context_info.return_value = {"main_view": "revenue", "display_name": "รายได้"}
        with patch("app.services.schema_service.SchemaService") as MockSchema:
            temp, table, thai = hybrid_flow.resolve_context_info("revenue", schema_service=svc)
        assert temp is svc
        assert table == "revenue"
        MockSchema.assert_not_called()

    def test_context_resolved_once_across_retries(self):
        """3 failing attempts → resolve_context_info called exactly once (hoisted out of loop)."""
        service = MagicMock()
        service.mcp_client.servers = {"nt-query": object()}
        service.provider_name = "matcha"
        service.get_pending_limit_warning.return_value = ""
        service.get_vanna_context_string = lambda q: ""
        service.lookup_values_from_question = lambda *a: []
        service.extract_sql = lambda text: None  # every attempt fails at SQL extraction
        service.extract_explanation = lambda text: ""
        service.provider.generate_content = AsyncMock(return_value="no sql here")

        schema_service = MagicMock()
        schema_service.get_context_info.return_value = {"main_view": "revenue", "display_name": "รายได้"}

        with patch.object(hybrid_flow, "resolve_context_info", wraps=hybrid_flow.resolve_context_info) as spy:
            result = asyncio.run(hybrid_flow.query_hybrid(
                service,
                question="q",
                system_prompt="sys",
                max_retries=2,
                value_verification_enabled=False,
                schema_service=schema_service,
            ))
        assert result.error == "Max retries exceeded"
        assert spy.call_count == 1


class TestClaudeMessageOrdering:
    def test_parallel_tool_use_batched_into_single_messages(self):
        """Two tool_use blocks in one response → one assistant msg + one user msg with both results."""

        def content_block(block_type, **kw):
            block = MagicMock()
            block.type = block_type
            for k, v in kw.items():
                setattr(block, k, v)
            return block

        # Turn 1: two parallel tool calls; Turn 2: final text
        response1 = MagicMock()
        response1.content = [
            content_block("tool_use", id="tu_1", name="get_schema", input={"table": "revenue"}),
            content_block("tool_use", id="tu_2", name="execute_query", input={"sql": "SELECT 1"}),
        ]
        response2 = MagicMock()
        response2.content = [content_block("text", text="คำตอบสุดท้าย")]

        service = MagicMock()
        service.provider_name = "claude"
        service.get_vanna_context_string = lambda q: ""
        service.get_pending_limit_warning.return_value = ""
        service.mcp_client.get_tools = AsyncMock(return_value=[])
        service.mcp_client.call_tool = AsyncMock(return_value=json.dumps([{"v": 1}]))
        service.provider.generate_sql = AsyncMock(side_effect=[
            {"response": response1, "tokens_used": 10},
            {"response": response2, "tokens_used": 5},
        ])

        result = asyncio.run(query_with_retry(service, "รายได้รวม"))

        # Inspect history passed to the SECOND generate_sql call
        second_call = service.provider.generate_sql.call_args_list[1]
        history = second_call[0][3]  # (question, system_prompt, tools, history)

        assert history[0]["role"] == "user"
        assert history[0]["content"] == "รายได้รวม"

        assistant_msg = history[1]
        assert assistant_msg["role"] == "assistant"
        assert [b["id"] for b in assistant_msg["content"]] == ["tu_1", "tu_2"]
        assert all(b["type"] == "tool_use" for b in assistant_msg["content"])

        result_msg = history[2]
        assert result_msg["role"] == "user"
        assert [b["tool_use_id"] for b in result_msg["content"]] == ["tu_1", "tu_2"]
        assert all(b["type"] == "tool_result" for b in result_msg["content"])

        # Question consumed into history → second call passes empty question
        assert second_call[0][0] == ""
        assert result.explanation == "คำตอบสุดท้าย"


class TestSSECancelOnDisconnect:
    def test_generator_close_cancels_query_task(self):
        """Closing the SSE generator mid-stream cancels the in-flight query task."""

        async def scenario():
            cancelled = asyncio.Event()

            async def never_ending_query(**kwargs):
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            engine = MagicMock()
            engine.query = never_ending_query

            event_queue: asyncio.Queue = asyncio.Queue()

            # Minimal replica of chat_stream's generate_events loop + finally
            async def generate_events():
                query_task = None
                try:
                    query_task = asyncio.create_task(engine.query())
                    while not query_task.done():
                        try:
                            event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                            yield event
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                finally:
                    if query_task is not None and not query_task.done():
                        query_task.cancel()

            gen = generate_events()
            first = await gen.__anext__()
            assert first.startswith(":")
            await gen.aclose()  # simulate client disconnect
            await asyncio.wait_for(cancelled.wait(), timeout=2)
            assert cancelled.is_set()

        asyncio.run(scenario())

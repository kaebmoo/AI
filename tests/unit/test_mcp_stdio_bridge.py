"""Plan 7 hardening — the stdio bridge Claude Desktop talks to (scripts/mcp_stdio_bridge.py).

Desktop launches local processes only, so the bridge is what it launches. Driven here the way
Desktop drives it (an MCP client on its stdio side) against the real facade over ASGI: the tools
are the server's, a refusal arrives whole, and a key that cannot be used stops the process with a
readable line instead of pretending to work.
"""

import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.memory import create_connected_server_and_client_session

from scripts import mcp_stdio_bridge as bridge
from tests.unit.test_mcp_facade import URL, _Group, _app, _result, world  # noqa: F401  (world: fixture)


def _run(key, body, upstream_url=URL):
    """The bridge in front of the facade: Desktop ↔ (stdio) bridge ↔ (HTTP over ASGI) /api/v1/mcp."""
    async def main():
        app = _app()

        def factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers=headers,
                                     timeout=timeout, auth=auth)

        async with app.router.lifespan_context(app):
            with patch.object(bridge, "streamablehttp_client",
                              partial(streamablehttp_client, httpx_client_factory=factory)):
                async with create_connected_server_and_client_session(
                        bridge.build_server(upstream_url, key)) as desktop:
                    return await body(desktop)
    return asyncio.run(main())


class TestBridge:
    def test_the_tools_are_the_servers_own_not_a_list_in_the_bridge(self, world):  # noqa: F811
        listed = _run(world.keys["a"].raw, lambda desktop: desktop.list_tools())
        assert {tool.name for tool in listed.tools} == {"ask", "list_contexts", "source_status"}
        source = (bridge.__file__ and open(bridge.__file__, encoding="utf-8").read())
        assert "source_status" not in source and "list_contexts" not in source  # nothing hardcoded here

    def test_an_answer_passes_through_whole(self, world):  # noqa: F811
        with patch("app.services.multi_context.ask", AsyncMock(return_value=_result(data=[{"v": 1}]))), \
                patch("app.services.query_engine.QueryEngine"):
            result = _run(world.keys["a"].raw, lambda d: d.call_tool("ask", {"question": "ยอดขาย"}))
        assert not result.isError and result.structuredContent["answer"] == "ยอดขาย 10 บาท"
        assert result.structuredContent["data_as_of"]["period"] == 202608
        assert "secret_sql" not in result.model_dump_json()

    def test_a_refusal_arrives_as_the_facade_wrote_it(self, world):  # noqa: F811
        """@server.call_tool() would have rebuilt this as isError=False with its own text."""
        result = _run(world.keys["a"].raw, lambda d: d.call_tool("source_status", {"context": "hr_payroll"}))
        assert result.isError and result.structuredContent["error"]["code"] == "context_not_allowed"
        assert result.structuredContent["error"]["http_status"] == 403

    def test_a_key_that_cannot_be_used_stops_the_process_with_a_reason(self, world):  # noqa: F811
        with pytest.raises(SystemExit) as exit_:
            _run("ntai_" + "0" * 64, lambda d: d.list_tools())
        assert "API key ใช้ไม่ได้" in str(exit_.value) and "NT_AI_API_KEY" in str(exit_.value)
        assert "ntai_0000" not in str(exit_.value)  # the key itself is never in the message

    @pytest.mark.parametrize("status,expected", [
        (401, "API key ใช้ไม่ได้"), (404, "mcp_external_enabled"), (503, "HTTP 503"), (None, "ต่อไม่ได้")])
    def test_every_way_it_can_fail_says_what_to_do(self, status, expected):
        failure = httpx.HTTPStatusError("x", request=MagicMock(), response=MagicMock(status_code=status)) \
            if status else ConnectionRefusedError("nope")
        # the real client raises out of a task group — the reason must be found inside it
        with pytest.raises(SystemExit) as exit_:
            bridge._die(_Group("unhandled", [failure]), "http://127.0.0.1:8000/api/v1/mcp")
        assert expected in str(exit_.value) and "127.0.0.1:8000" in str(exit_.value)

    def test_main_refuses_to_start_without_a_key(self, monkeypatch):
        monkeypatch.setenv("NT_AI_API_KEY", "  ")
        with pytest.raises(SystemExit) as exit_:
            bridge.main()
        assert "NT_AI_API_KEY" in str(exit_.value)

    def test_the_url_comes_from_the_environment(self, monkeypatch):
        seen = {}
        monkeypatch.setenv("NT_AI_API_KEY", "ntai_x")
        monkeypatch.setenv("NT_AI_BASE_URL", "https://ai.example.com/")
        monkeypatch.setattr(bridge, "anyio", MagicMock(run=lambda fn, url, key: seen.update(url=url, key=key)))
        bridge.main()
        assert seen == {"url": "https://ai.example.com/api/v1/mcp", "key": "ntai_x"}

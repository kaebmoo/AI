"""Claude Desktop ↔ the external MCP facade (Plan 7 hardening)

Claude Desktop only launches local processes and speaks stdio to them; it cannot reach
``http://localhost`` itself. The facade at ``POST /api/v1/mcp`` speaks Streamable HTTP and wants
``X-API-Key`` on every request. This is the adapter between the two, and nothing else: it declares
no tools of its own, hardcodes no names, and passes a tool error on whole — whatever the facade
answers is what the model sees. Every rule (key, workspace, allowlist, scope, data policy, quota,
audit) stays on the server side, where it can be enforced.

    export NT_AI_API_KEY=ntai_...                  # a key bound to a workspace/allowlist, scope 'query'
    export NT_AI_BASE_URL=http://127.0.0.1:8000    # optional — this is the default
    python scripts/mcp_stdio_bridge.py

The key is read from the environment, put in a header and written nowhere: not to a file, not to
the log, not into an error message. ⚠️ What the facade answers goes to the model behind the client
you connect — use a key whose workspace you are willing to send there.

Set it up in Claude Desktop: docs/manuals/manual_mcp_external.md
"""

import os
import sys
from contextlib import asynccontextmanager

import anyio
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

NAME = "nt-ai-assistant"
DEFAULT_URL = "http://127.0.0.1:8000"


def _flatten(exc: BaseException):
    """Every exception in a (nested) exception group — the client's task group buries the real one."""
    yield exc
    for inner in getattr(exc, "exceptions", None) or ():
        yield from _flatten(inner)


def _http_status(exc: BaseException):
    for item in _flatten(exc):
        response = getattr(item, "response", None)
        status = getattr(response, "status_code", None)
        if status:
            return status
    return None


def _die(exc: BaseException, url: str) -> None:
    """One readable line on stderr — Claude Desktop shows it in the server's log. Never the key."""
    status = _http_status(exc)
    if status == 401:
        reason = "API key ใช้ไม่ได้ — ตรวจค่า NT_AI_API_KEY (key ต้องผูก workspace/allowlist และมี scope 'query')"
    elif status == 404:
        reason = "ปลายทางไม่เปิดให้ใช้ — admin ต้องเปิด flag mcp_external_enabled"
    elif status:
        reason = f"ปลายทางตอบ HTTP {status}"
    else:
        reason = f"ต่อไม่ได้ ({type(exc).__name__})"
    sys.exit(f"nt-ai bridge: {reason} [{url}]")


@asynccontextmanager
async def upstream(url: str, key: str):
    """One request, one authenticated session — the facade is stateless, it keeps nothing between calls."""
    try:
        async with streamablehttp_client(url, headers={"X-API-Key": key}) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — the task group re-raises everything it wrapped
        _die(exc, url)


def build_server(url: str, key: str) -> Server:
    server = Server(NAME)

    @server.list_tools()
    async def list_tools():
        async with upstream(url, key) as session:
            return (await session.list_tools()).tools

    async def call_tool(request: types.CallToolRequest) -> types.ServerResult:
        """The raw handler on purpose: @server.call_tool() rebuilds the result with isError=False and
        turns an exception into its own text — a refusal must reach the model exactly as the facade
        wrote it (code + fixed message), and nothing of ours may be added to it."""
        async with upstream(url, key) as session:
            result = await session.call_tool(request.params.name, request.params.arguments or {})
        return types.ServerResult(result)

    server.request_handlers[types.CallToolRequest] = call_tool
    return server


async def serve(url: str, key: str) -> None:
    server = build_server(url, key)
    async with upstream(url, key) as session:  # fail now, with a reason, not on the first question
        await session.list_tools()

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    key = os.environ.get("NT_AI_API_KEY", "").strip()
    if not key:
        sys.exit("nt-ai bridge: ตั้งค่า NT_AI_API_KEY ก่อน (ดู docs/manuals/manual_mcp_external.md)")
    url = os.environ.get("NT_AI_BASE_URL", DEFAULT_URL).strip().rstrip("/") + "/api/v1/mcp"
    anyio.run(serve, url, key)


if __name__ == "__main__":
    main()

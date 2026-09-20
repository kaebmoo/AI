"""Example client of the external MCP facade (Plan 7 Phase 6) — also the latency probe.

    export NT_AI_API_KEY=ntai_...            # a key bound to a workspace / allowlist, scope 'query'
    python scripts/mcp_client_example.py list
    python scripts/mcp_client_example.py status feed_revenue
    python scripts/mcp_client_example.py ask "รายได้รวมเดือนล่าสุด" [--context feed_revenue] [--scope '{"year_month": 202608}'] [--data]
    python scripts/mcp_client_example.py bench "คำถาม" --n 20     # MCP vs POST /api/v1/query, same key and question

The key travels in the X-API-Key header of every request; nothing is kept on the server between calls.
A wrong key is HTTP 401 (the session dies); everything else comes back as a tool error with a code.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def call(url: str, key: str, tool: str, arguments: dict):
    async with streamablehttp_client(url, headers={"X-API-Key": key}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments)


async def bench(base: str, key: str, question: str, context, n: int):
    """Same question both ways; after the first answer both hit the 30-minute query cache, so the
    difference is the transport. One MCP session for all calls (what a desktop client does)."""
    body = {"question": question, **({"context": context} if context else {})}
    rest, mcp = [], []
    async with httpx.AsyncClient(timeout=300) as http:
        await http.post(f"{base}/api/v1/query/", headers={"X-API-Key": key}, json=body)  # warm the cache
        async with streamablehttp_client(f"{base}/api/v1/mcp", headers={"X-API-Key": key}) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for _ in range(n):  # alternate so drift hits both
                    start = time.perf_counter()
                    (await http.post(f"{base}/api/v1/query/", headers={"X-API-Key": key}, json=body)).raise_for_status()
                    rest.append((time.perf_counter() - start) * 1000)
                    await asyncio.sleep(5.1)  # past the 5 s duplicate-request window
                    start = time.perf_counter()
                    result = await session.call_tool("ask", body)
                    mcp.append((time.perf_counter() - start) * 1000)
                    if result.isError:
                        sys.exit(f"ask failed: {result.content[0].text}")
                    await asyncio.sleep(5.1)
    for name, values in (("REST", rest), ("MCP ", mcp)):
        ordered = sorted(values)
        print(f"{name} n={n} P50={statistics.median(ordered):.1f} ms  P95={ordered[max(0, int(n * 0.95) - 1)]:.1f} ms  max={ordered[-1]:.1f} ms")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["list", "status", "ask", "bench"])
    parser.add_argument("text", nargs="?")
    parser.add_argument("--base", default=os.environ.get("NT_AI_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--context")
    parser.add_argument("--scope", type=json.loads)
    parser.add_argument("--data", action="store_true")
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()
    key = os.environ.get("NT_AI_API_KEY") or sys.exit("set NT_AI_API_KEY")

    if args.command == "bench":
        return asyncio.run(bench(args.base, key, args.text, args.context, args.n))
    tool, arguments = {
        "list": ("list_contexts", {}),
        "status": ("source_status", {"context": args.text}),
        "ask": ("ask", {k: v for k, v in (("question", args.text), ("context", args.context), ("scope", args.scope),
                                          ("include_data", args.data)) if v}),
    }[args.command]
    try:
        result = asyncio.run(call(f"{args.base}/api/v1/mcp", key, tool, arguments))
    except BaseException as exc:  # anyio wraps the HTTP 401 / 404 in an ExceptionGroup
        leaves = getattr(exc, "exceptions", [exc])
        sys.exit(f"connection refused by the server: {leaves[0]}")
    print(("ERROR " if result.isError else "") + result.content[0].text)
    if result.structuredContent:
        print(json.dumps(result.structuredContent, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

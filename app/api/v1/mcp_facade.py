"""
External MCP facade (Plan 7 Phase 6)
====================================
Three tools for callers OUTSIDE the process — ask / list_contexts / source_status — over stateless
Streamable HTTP at /api/v1/mcp. A thin layer on the entry POST /api/v1/query already uses
(run_simple_query → multi_context.ask → QueryEngine.query): allowlist, scope, pinning, llm policy,
audit, cache and multi-context come from there. The internal stdio MCP servers (raw SQL, sample
values, admin writes) are never proxied, and the facade makes no provider call of its own.

The caller is an LLM holding its own key, so on this channel:
  - every HTTP request passes the gate (key active, owner active, 'query' scope, bound to a
    workspace/allowlist) — no key = 401 before the transport; nothing is remembered between requests
  - every tool call is one usage, counted exactly like one REST request (validate_key + track_usage)
  - a context whose source policy is not 'full' — or unreadable — does not exist here (fail closed):
    what we return enters a model we do not control
  - SQL is never returned, and no exception text reaches the client: fixed code + message only
    (argument-type errors and unknown tool names are answered by the SDK before a tool runs: they
    echo the caller's own input, nothing of ours, and cost no usage)
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Optional

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.config import settings
from app.core.llm_policy import FULL, LLMPolicyError, normalize
from app.services.data_sources import LEGACY, ScopeError
from app.services.workspaces import ContextNotAllowed, allowed_contexts, canonical_context, is_restricted

logger = logging.getLogger(__name__)

PATH = f"{settings.API_V1_STR}/mcp"
FLAG = "mcp_external_enabled"  # admin_config feature flag, default off: POST /admin/config/features/{FLAG}/toggle

# code → (HTTP-equivalent status, message). The only error texts a client ever sees.
ERRORS = {
    "unauthorized": (401, "API key ใช้ไม่ได้"),
    "rate_limited": (429, "API key เกิน rate limit หรือโควตารายวัน — ลองใหม่ภายหลัง"),
    "invalid_scope": (400, "scope ใช้กับ context นี้ไม่ได้ (key ที่ context ไม่ได้ประกาศ หรือค่าไม่ถูกต้อง) — ไม่ตอบแบบไม่มี scope"),
    "context_not_allowed": (403, "API key นี้ไม่มีสิทธิ์ใช้ context ที่ขอ — ดู list_contexts"),
    "policy_refused": (403, "context นี้ไม่เปิดให้ใช้ผ่าน MCP (นโยบายข้อมูลของ source ไม่อนุญาตให้ส่งออกไปยังโมเดลภายนอก)"),
    "invalid_arguments": (400, "argument ของ tool ไม่ถูกต้อง (เช่น question ว่าง)"),
    "duplicate_request": (409, "คำถามเดียวกันกำลังประมวลผลอยู่ — รอสักครู่แล้วถามใหม่"),
    "source_unavailable": (503, "แหล่งข้อมูลของ context นี้ยังไม่พร้อมใช้งาน"),
    "query_failed": (422, "ตอบคำถามนี้ไม่ได้ — ลองถามให้เจาะจงขึ้น หรือระบุ context"),
    "internal_error": (500, "เกิดข้อผิดพลาดภายใน"),
}


NO_DATA = "ไม่พบข้อมูลที่ตรงกับเงื่อนไข"


class Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Principal:
    """Plain values, read while the auth session was open — an ORM APIKey does not survive its session."""
    api_key_id: int
    user_id: int
    allowed: FrozenSet[str]  # the key's rights (workspace ∩ allowlist), stored names
    usable: FrozenSet[str]   # … of which the source policy is 'full': what exists on this channel


def full_policy_contexts(config_engine=None) -> FrozenSet[str]:
    """Active contexts of an active workspace whose (active) source has llm_data_policy 'full'. Strict on purpose — unlike
    data_sources.policy_for_context, an unmigrated registry, a missing row or any error = nothing."""
    if config_engine is None:
        from app.db.session import config_engine
    try:
        with config_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT sc.name, ds.llm_data_policy FROM schema_contexts sc JOIN data_sources ds "
                "ON ds.id = COALESCE(sc.source_id, (SELECT id FROM data_sources WHERE name = :legacy)) "
                # an allowlist-only key is not tied to a workspace: closing the workspace must still cut it off
                "JOIN workspaces w ON w.id = COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) "
                "WHERE sc.is_active = 1 AND ds.is_active = 1 AND w.is_active = 1"), {"legacy": LEGACY}).fetchall()
    except Exception as exc:
        logger.error("MCP: source policies unreadable (%s) — every context refused", exc)
        return frozenset()
    return frozenset(name for name, policy in rows if normalize(policy) == FULL)


def authenticate(raw_key: Optional[str], count: bool) -> Principal:
    """Sync (run in a thread). count=False: the gate, no side effects. count=True: one tool call = one
    usage, the same unit and counters as one REST request. Raises Refused."""
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.services.api_key_service import APIKeyService

    db = SessionLocal()
    try:
        service = APIKeyService(db)
        api_key = service.authenticate(raw_key or "")
        if api_key is None:
            raise Refused("unauthorized")
        owner = db.query(User).filter(User.id == api_key.user_id).first()
        # a key held outside our servers must be bound on purpose: unrestricted keys never work here
        if (owner is None or not owner.is_active or not service.has_scope(api_key, "query")
                or not is_restricted(api_key)):
            raise Refused("unauthorized")
        if count:
            if service.validate_key(raw_key) is None:  # it authenticated a moment ago: this is the rate limit
                raise Refused("rate_limited")
            service.track_usage(api_key.id)
            if service.usage_today(api_key.id) > api_key.rate_limit_per_day:  # a parallel burst passed the check together
                raise Refused("rate_limited")
        allowed = allowed_contexts(api_key)  # frozenset for a restricted key; unreadable = empty
        return Principal(api_key_id=api_key.id, user_id=api_key.user_id, allowed=allowed,
                         usable=allowed & full_policy_contexts())
    finally:
        db.close()


def _enabled() -> bool:
    from app.services.admin_config_service import AdminConfigService
    config = AdminConfigService()
    try:
        return config.get_config(FLAG, "false") == "true"
    except Exception as exc:
        logger.error("MCP: flag unreadable (%s) — off", exc)
        return False
    finally:
        config.close()


class Gate:
    """Pure ASGI, in front of the transport: nothing unauthenticated reaches it. Stateless transport
    serves tools/call without any handshake, so this runs on EVERY request, not 'at initialize'."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if not await anyio.to_thread.run_sync(_enabled):
            return await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
        if scope["method"] != "POST":  # stateless: nothing to stream on GET, no session to DELETE
            return await JSONResponse({"detail": "Method Not Allowed"}, status_code=405,
                                      headers={"Allow": "POST"})(scope, receive, send)
        keys = [v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"x-api-key"]
        try:
            if len(keys) != 1:  # two headers: the gate and the tool would each pick their own
                raise Refused("unauthorized")
            await anyio.to_thread.run_sync(authenticate, keys[0], False)
        except Refused:
            return await JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)(scope, receive, send)
        except Exception as exc:  # fail closed
            logger.error("MCP gate failed: %s", exc)
            return await JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)


def _error(code: str, request_id: Optional[str] = None) -> CallToolResult:
    status, message = ERRORS[code]
    body = {"code": code, "http_status": status, "message": message}
    if request_id:
        body["request_id"] = request_id
    return CallToolResult(isError=True, content=[TextContent(type="text", text=f"{code}: {message}")],
                          structuredContent={"error": body})


def _ok(payload: Dict[str, Any], text_: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text_)], structuredContent=payload)


def _find(exc: BaseException, kinds) -> Optional[BaseException]:
    if isinstance(exc, kinds):
        return exc
    for inner in getattr(exc, "exceptions", None) or ():
        found = _find(inner, kinds)
        if found is not None:
            return found
    return None


def _code_for(exc: BaseException, named_in_rights: bool) -> str:
    from app.services.database_adapter import SourceUnavailable

    if isinstance(exc, Refused):
        return exc.code
    if isinstance(exc, ValidationError):  # SimpleQueryRequest: empty question, …
        return "invalid_arguments"
    if _find(exc, ScopeError):
        return "invalid_scope"
    if _find(exc, LLMPolicyError):
        return "policy_refused"
    if _find(exc, ContextNotAllowed):
        # inside the key's rights but not 'full' → say so; anything else gets ONE answer, whether the
        # context exists or not (no existence oracle)
        return "policy_refused" if named_in_rights else "context_not_allowed"
    if _find(exc, SourceUnavailable):
        return "source_unavailable"
    return "internal_error"


def _client_label(request) -> str:
    """Self-reported, for the audit trail only — never for a decision."""
    agent = (request.headers.get("user-agent") or "").split(" ")[0]
    return re.sub(r"[^A-Za-z0-9._/-]", "", agent)[:40]


def _in_rights(context: Optional[str], principal: Optional[Principal]) -> bool:
    if not context or principal is None:
        return False
    try:
        canonical_context(context, principal.allowed)
        return True
    except ContextNotAllowed:
        return False


async def _run(ctx: Context, body, context: Optional[str] = None) -> CallToolResult:
    """Auth + count, run the tool body, map every failure to a fixed error."""
    request = ctx.request_context.request
    request_id = getattr(request.state, "request_id", None)
    principal = None
    try:
        principal = await anyio.to_thread.run_sync(authenticate, request.headers.get("x-api-key"), True)
        return await body(principal, request)
    except Exception as exc:
        code = _code_for(exc, _in_rights(context, principal))
        log = logger.error if code == "internal_error" else logger.info
        log("MCP tool refused/failed [%s] request_id=%s: %s: %s", code, request_id, type(exc).__name__, exc)
        return _error(code, request_id)


def build() -> tuple:
    """(FastMCP, ASGI app for the route). A new pair per app: session_manager.run() works once per instance."""
    split = lambda raw: [item.strip() for item in raw.split(",") if item.strip()]  # noqa: E731
    server = FastMCP(
        "nt-ai-assistant", stateless_http=True,
        instructions="ถามข้อมูลการเงินของ NT เป็นภาษาไทย: list_contexts ดูชุดข้อมูลที่ key นี้ใช้ได้, ask ถามคำถาม, "
                     "source_status ดูงวดข้อมูลล่าสุด. ตัวเลขทุกตัวมาจากระบบ — อย่าคำนวณหรือประมาณเพิ่มเอง.",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=split(settings.MCP_ALLOWED_HOSTS), allowed_origins=split(settings.MCP_ALLOWED_ORIGINS)))

    @server.tool()
    async def ask(ctx: Context, question: str, context: Optional[str] = None,
                  scope: Optional[Dict[str, Any]] = None, include_data: bool = False) -> CallToolResult:
        """ถามคำถามเป็นภาษาธรรมชาติ (ไทย/อังกฤษ) แล้วได้คำตอบพร้อมงวดข้อมูล (data_as_of). แต่ละครั้งเป็นคำถามเดี่ยว
        ไม่มีประวัติสนทนา — ใส่บริบทที่จำเป็นในคำถามให้ครบ. context: ชื่อจาก list_contexts (ไม่ใส่ = ระบบเลือกเอง).
        scope: ตัวกรองแถว เช่น {"year_month": 202607} — ใช้ได้เฉพาะ key ที่ context ประกาศ. include_data: ขอแถวผลลัพธ์
        (จำกัดจำนวนแถว) นอกเหนือจากข้อความคำตอบ."""
        async def body(principal: Principal, request) -> CallToolResult:
            from app.api.v1.query import SimpleQueryRequest, run_simple_query
            from app.db.session import SessionLocal
            from app.services.admin_config_service import AdminConfigService

            label = _client_label(request)
            db, admin_config = SessionLocal(), AdminConfigService()
            try:
                response, result = await run_simple_query(
                    SimpleQueryRequest(question=question, context=context, scope=scope, include_data=include_data,
                                       include_sql=False, max_rows=settings.MCP_MAX_ROWS),
                    user_id=principal.user_id, api_key_id=principal.api_key_id, allowed=principal.usable,
                    channel=f"mcp:{label}" if label else "mcp", db=db, admin_config=admin_config,
                    mcp_client=getattr(request.app.state, "mcp_client", None))
            finally:
                admin_config.close()
                db.close()
            return _answer(response, result)

        return await _run(ctx, body, context)

    @server.tool()
    async def list_contexts(ctx: Context) -> CallToolResult:
        """ชุดข้อมูล (context) ที่ API key นี้ใช้ผ่าน MCP ได้: name, display_name, description."""
        async def body(principal: Principal, request) -> CallToolResult:
            def read():
                from app.api.v1.query import contexts_for
                from app.db.session import ConfigSessionLocal
                with ConfigSessionLocal() as config_db:
                    return [c.model_dump() for c in contexts_for(principal.usable, config_db)]
            contexts = await anyio.to_thread.run_sync(read)
            return _ok({"contexts": contexts}, "\n".join(
                f"- {c['name']}: {c['display_name']} — {c['description']}" for c in contexts) or "(ไม่มี context ที่ใช้ได้)")

        return await _run(ctx, body)

    @server.tool()
    async def source_status(ctx: Context, context: str) -> CallToolResult:
        """สถานะและความสดของข้อมูลของ context: พร้อมใช้งานไหม และข้อมูลถึงงวดไหน (data_as_of)."""
        async def body(principal: Principal, request) -> CallToolResult:
            name = canonical_context(context, principal.usable)  # rights first — then, and only then, resolve

            def read():
                from app.services.data_sources import source_resolver
                try:
                    source = source_resolver.for_context(name)
                    manifest = (source.adapter.manifest or {}) if source.adapter else {}
                    return {"status": "ok", "source_kind": "file" if source.adapter else "legacy",
                            "data_as_of": source.data_as_of, "schema_version": manifest.get("schema_version")}
                except Exception as exc:  # never the reason: it names paths
                    logger.warning("MCP source_status(%s): %s", name, exc)
                    return {"status": "unavailable", "source_kind": None, "data_as_of": None, "schema_version": None}
            status = {"context": name, **await anyio.to_thread.run_sync(read)}
            period = (status["data_as_of"] or {}).get("period")
            return _ok(status, f"{name}: {status['status']}" + (f", ข้อมูลถึงงวด {period}" if period else ""))

        return await _run(ctx, body, context)

    return server, Gate(StreamableHTTPASGIApp(_session_manager(server)))


def _session_manager(server: FastMCP):
    server.streamable_http_app()  # creates server.session_manager; we route to its ASGI handler ourselves (no 307)
    return server.session_manager


def _answer(response, result) -> CallToolResult:
    """REST's response minus everything that must not leave on this channel: SQL, raw error text —
    and any answer produced under a policy other than 'full' (defence in depth behind `usable`).
    The engine's prose is kept only for a result WITH rows: its 'no data' text quotes the SQL, and
    the text of a failed result quotes the exception."""
    from app.api.v1.query import _part_answer

    parts = getattr(result, "parts", None)
    produced = [p.result for p in parts if p.result is not None] if parts is not None else [result]
    if any(getattr(r, "llm_policy", None) != FULL for r in produced):
        raise Refused("policy_refused")
    if parts is None and response.error:
        raise Refused("duplicate_request" if response.error == "duplicate_request" else "query_failed")

    payload = response.model_dump(exclude={"sql", "error"}, exclude_none=True)
    if parts is None:
        # a structured explanation (text + chart config) reaches REST as str(dict); an LLM client gets the text
        answer = (_part_answer(result.query_result) or payload["answer"]) if result.query_result.data else NO_DATA
    else:
        answer = payload["answer"]  # multi_context.combine: explanations of parts with rows + fixed templates
        share = max(1, settings.MCP_MAX_ROWS // max(1, len(parts)))  # MCP_MAX_ROWS is per ask, not per part
        for entry, part in zip(payload.get("parts") or [], parts):
            entry.pop("sql", None)
            if "data" in entry:
                entry["data"] = entry["data"][:share]
            if part.error:
                answer = answer.replace(part.error, ERRORS["query_failed"][1])
                entry.update(error="query_failed", answer=ERRORS["query_failed"][1])
                entry.pop("data", None)
            elif not part.ok:
                entry["answer"] = NO_DATA
    payload["answer"] = answer

    # last guard: whatever the prose above came from, the SQL that ran is not in what leaves
    leaving = json.dumps(payload, ensure_ascii=False, default=str)
    ran = [sql for sql in (getattr(getattr(r, "query_result", None), "sql_query", None) for r in produced) if sql]
    if "```sql" in leaving.lower() or any(sql in leaving or sql in answer for sql in ran):
        raise Refused("query_failed")
    return _ok(payload, answer)

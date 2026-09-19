"""
NT AI Assistant - Query Engine
=================================
Core orchestrator for query processing.
Can be called from Web API, Telegram, tests, or scripts.

Usage:
    engine = QueryEngine(mcp_client=mcp, db_session=db)
    result = await engine.query("รายได้เดือนนี้เท่าไหร่")
"""

import hashlib
import json
import os
import time
import uuid
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable

from sqlalchemy.orm import Session

from app.providers.base import QueryResult
from app.providers.registry import provider_registry
from app.services.ai_service import AIService
from app.services.mcp_client import MCPClientService
from app.services.admin_config_service import AdminConfigService
from app.core.llm_policy import FULL, LLMPolicyError, PolicyMCPClient, RequestPolicy, history_without_answers, normalize, request_llm_policy
from app.services.data_sources import SourceBoundMCPClient, request_pinned, request_scope, source_resolver
from app.services.retention import stores_results
from app.services.workspaces import canonical_context, check_context, workspace_of_context
from app.services.schema_service import SchemaService
from app.services.warning_detector import WarningDetector
from app.services.query_classifier import query_classifier
from app.schemas.chat import DataWarning
from app.config import settings

logger = logging.getLogger(__name__)


def detect_context_from_question(question: str, schema_service: SchemaService = None, allowed=None) -> str:
    """
    Auto-detect context from user's question using DB keywords.

    Standalone function — usable from chat.py or anywhere without QueryEngine instance.
    """
    question_lower = question.lower()
    context_scores = {}

    def usable(contexts):
        # Phase 4a: a restricted key routes among its own contexts only (allowed = normalised names)
        if allowed is None:
            return contexts
        return [c for c in contexts if c.get('name') in allowed]

    if schema_service:
        try:
            contexts = usable(schema_service.get_all_contexts())
            for ctx in contexts:
                ctx_name = ctx.get('name')
                ctx_keywords = ctx.get('keywords', [])
                priority = ctx.get('priority', 0)

                if isinstance(ctx_keywords, list) and ctx_keywords:
                    score = sum(1 for kw in ctx_keywords if kw.lower() in question_lower)
                    if score > 0:
                        context_scores[ctx_name] = score + (priority * 0.1)
        except Exception:
            pass

    if context_scores:
        return max(context_scores, key=context_scores.get)

    if schema_service:
        try:
            contexts = usable(schema_service.get_all_contexts())
            if contexts:
                return contexts[0].get('name', 'revenue')
        except Exception:
            pass

    if allowed is not None:  # never fall back to a context the key can't use
        from app.services.workspaces import ContextNotAllowed
        raise ContextNotAllowed("API key นี้ไม่มี context ที่ใช้ได้")
    return "revenue"


# ---------------------------------------------------------------------------
# In-memory query result cache (TTL-based)
# ---------------------------------------------------------------------------
_query_cache: Dict[str, Dict[str, Any]] = {}
_QUERY_CACHE_TTL = 1800  # 30 minutes
_QUERY_CACHE_MAX = 500  # max entries before eviction


# ---------------------------------------------------------------------------
# Thai year normalization — expand 2-digit Thai year to 4-digit
# ---------------------------------------------------------------------------
# Pattern explanation:
#   Group 1 — year keyword (longest-first to prevent partial match):
#     ปีงบประมาณ | ปีงบ | ปี\s*พ\.?\s*ศ\.? | พ\.?\s*ศ\.? | ปี
#   \s* — optional whitespace between keyword and number
#   Group 2 — exactly 2 digits
#   (?!\d) — NOT followed by another digit (prevents matching "ปี 2568")
_THAI_YEAR_RE = re.compile(
    r'(ปีงบประมาณ|ปีงบ|ปี\s*พ\.?\s*ศ\.?|พ\.?\s*ศ\.?|ปี)\s*(\d{2})(?!\d)'
)

# Valid 2-digit range: 40-99 → พ.ศ. 2540-2599 (ค.ศ. 1997-2056)
_THAI_YEAR_MIN = 40
_THAI_YEAR_MAX = 99


def _replace_thai_year(match: re.Match) -> str:
    """Replace 2-digit Thai year with 4-digit equivalent.

    Example: "ปี 68" → "ปี 2568" (68 + 2500)
    Only converts if the 2-digit number is in [40, 99].
    Numbers outside this range are left untouched.
    """
    prefix = match.group(1)
    year_2d = int(match.group(2))
    if _THAI_YEAR_MIN <= year_2d <= _THAI_YEAR_MAX:
        return prefix + ' ' + str(year_2d + 2500)
    return match.group(0)  # Outside valid range — don't normalize


def _normalize_question(q: str) -> str:
    """Normalize question for cache key comparison.

    Steps (order matters):
    1. Strip + lowercase
    2. Remove Thai particles & filler words
    3. Expand 2-digit Thai year → 4-digit (e.g. "ปี 68" → "ปี 2568")
    4. Collapse whitespace

    This is used ONLY for cache key generation.
    The original question is always sent to the LLM unchanged.
    """
    q = q.strip().lower()
    # Step 2: Remove Thai particles & filler words that don't change meaning
    particles = [
        'ครับ', 'ค่ะ', 'คะ', 'นะ', 'จ้า', 'จ้ะ', 'จ๊ะ',
        'หน่อย', 'ด้วย', 'ให้หน่อย', 'ได้ไหม', 'ได้มั้ย', 'ได้เปล่า',
        'อยากรู้', 'อยากทราบ', 'อยากดู',
        'ช่วย', 'ขอ', 'บอก', 'แสดง', 'ดู', 'หา',
    ]
    for p in particles:
        q = q.replace(p, '')
    # Step 3: Normalize 2-digit Thai year → 4-digit
    q = _THAI_YEAR_RE.sub(_replace_thai_year, q)
    # Step 4: Collapse whitespace
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def _cache_key(question: str, provider: str, context: str) -> str:
    """Create a deterministic cache key from question + provider + context."""
    normalized = _normalize_question(question)
    raw = f"{normalized}|{provider}|{context}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Any]:
    """Get from cache if not expired."""
    entry = _query_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _QUERY_CACHE_TTL:
        return entry["result"]
    if entry:
        del _query_cache[key]
    return None


def _cache_set(key: str, result: Any) -> None:
    """Store result in cache. Evict oldest if over limit."""
    if len(_query_cache) >= _QUERY_CACHE_MAX:
        oldest_key = min(_query_cache, key=lambda k: _query_cache[k]["ts"])
        del _query_cache[oldest_key]
    _query_cache[key] = {"result": result, "ts": time.time()}


def clear_query_cache() -> int:
    """Clear all entries from query result cache. Returns number of entries cleared."""
    count = len(_query_cache)
    _query_cache.clear()
    return count


# ---------------------------------------------------------------------------
# Request dedup — prevent identical questions within a short window
# ---------------------------------------------------------------------------
_dedup_store: Dict[str, float] = {}


def _dedup_mark(user_question: str, provider: str, user_id: Optional[int] = None) -> Optional[str]:
    """Mark this request in the dedup store. Returns the key, or None if duplicate.

    Scoped per-user so two users asking the same question don't block each other.
    """
    from app.config import settings as _settings
    ttl = getattr(_settings, "DEDUP_TTL_SECONDS", 5.0)
    key = hashlib.md5(f"{user_id}|{_normalize_question(user_question)}|{provider}".encode()).hexdigest()
    now = time.time()
    # Prune expired entries (lazy cleanup)
    expired = [k for k, ts in _dedup_store.items() if now - ts > ttl]
    for k in expired:
        del _dedup_store[k]
    if key in _dedup_store:
        return None
    _dedup_store[key] = now
    return key


def _dedup_release(key: str) -> None:
    """Release a dedup mark early (request failed — allow immediate retry)."""
    _dedup_store.pop(key, None)


def _source_policy(source) -> tuple:
    """(llm_data_policy, provider allowlist) of a resolved source. The resolver only ever produces a known
    policy string and frozenset|None; anything else (a stand-in object) reads as schema_only / no allowlist."""
    providers = getattr(source, "llm_providers", None)
    return normalize(getattr(source, "llm_data_policy", None)), providers if isinstance(providers, frozenset) else None


@dataclass
class QueryEngineResult:
    """Combined result from QueryEngine — wraps QueryResult + extras"""
    query_result: QueryResult
    context_name: str = "revenue"
    warnings: List[DataWarning] = field(default_factory=list)
    execution_time_ms: float = 0.0
    provider_used: str = ""
    source_version: str = ""  # Plan 7: source + verified build the answer was read from
    data_as_of: Optional[Dict[str, Any]] = None  # Plan 7: manifest period/built_at/build_id; None = legacy
    llm_policy: str = FULL  # Phase 4.5: the source's llm_data_policy this answer was produced under


# ---------------------------------------------------------------------------
# Provider kwargs resolution: DB → .env → hardcoded fallback
# ---------------------------------------------------------------------------
# Hardcoded fallback for 3 built-in providers — new providers use ai_providers table
_ENV_FALLBACK = {
    "claude":  {"api_key_attr": "ANTHROPIC_API_KEY", "model_attr": "CLAUDE_MODEL"},
    "gemini":  {"api_key_attr": "GOOGLE_AI_API_KEY", "model_attr": "GEMINI_MODEL"},
    "matcha":  {"api_key_attr": "MATCHA_AI_API_KEY", "model_attr": "MATCHA_MODEL",
                "api_url_attr": "MATCHA_API_URL"},
}


def _build_provider_kwargs(
    provider_name: str,
    ai_config: dict,
    admin_config_service: Optional[AdminConfigService] = None,
) -> dict:
    """
    Build provider kwargs with 3-tier resolution:
    1. DB (ai_providers table) → resolve env var name → get actual value from os.environ
    2. .env via settings object (for known providers)
    3. Empty string (provider.is_configured() returns False → skip)
    """
    kwargs: Dict[str, Any] = {}
    api_key_env_var = None
    api_url_env_var = None
    default_api_url = None
    provider_record = None
    owns_admin_config = False

    # === Tier 1: Try DB for env var names ===
    try:
        if admin_config_service is None:
            admin_config_service = AdminConfigService()
            owns_admin_config = True

        provider_record = admin_config_service.get_provider_record(provider_name)
        if provider_record and provider_record.get("is_active"):
            api_key_env_var = provider_record.get("api_key_env_var")
            api_url_env_var = provider_record.get("api_url_env_var")
            default_api_url = provider_record.get("default_api_url")
    except Exception as e:
        logger.debug(f"DB lookup failed for provider '{provider_name}': {e}")
    finally:
        if owns_admin_config and admin_config_service is not None:
            admin_config_service.close()

    # === Resolve API Key ===
    if api_key_env_var:
        kwargs["api_key"] = (
            os.environ.get(api_key_env_var, "")
            or getattr(settings, api_key_env_var, "")
        )
    else:
        fallback = _ENV_FALLBACK.get(provider_name, {})
        attr = fallback.get("api_key_attr")
        kwargs["api_key"] = getattr(settings, attr, "") if attr else ""

    # === Resolve API URL (if provider needs it) ===
    if api_url_env_var:
        kwargs["api_url"] = (
            ai_config.get(f"{provider_name}_api_url")
            or os.environ.get(api_url_env_var, "")
            or getattr(settings, api_url_env_var, "")
            or default_api_url
            or ""
        )
    else:
        fallback = _ENV_FALLBACK.get(provider_name, {})
        attr = fallback.get("api_url_attr")
        if attr:
            kwargs["api_url"] = (
                ai_config.get(f"{provider_name}_api_url")
                or getattr(settings, attr, "")
            )

    # === Resolve Model: admin_config → .env settings → "" ===
    model_key = f"{provider_name}_model"
    model = ai_config.get(model_key)
    if not model:
        fallback = _ENV_FALLBACK.get(provider_name, {})
        attr = fallback.get("model_attr")
        model = getattr(settings, attr, "") if attr else ""
    kwargs["model"] = model or ""

    # === Provider-specific extras from admin_config ===
    # e.g. "claude_extended_thinking" → "extended_thinking"
    skip_suffixes = {"enabled", "model", "api_url"}
    for key, value in ai_config.items():
        if key.startswith(f"{provider_name}_"):
            param_name = key[len(provider_name) + 1:]
            if param_name not in skip_suffixes:
                kwargs[param_name] = value

    return kwargs


class QueryEngine:
    """
    Core orchestrator — can be called from Web, Telegram, or API.

    Usage:
        engine = QueryEngine(mcp_client=mcp, db_session=db)
        result = await engine.query("รายได้เดือนนี้เท่าไหร่")
    """

    def __init__(
        self,
        mcp_client: MCPClientService,
        db_session: Session = None,
        admin_config: AdminConfigService = None,
    ):
        self.mcp_client = mcp_client
        self.db = db_session
        # Track ownership: a self-created AdminConfigService owns a config-DB
        # session that must be closed via close() (endpoints inject one instead)
        self._owns_admin_config = admin_config is None
        self.admin_config = admin_config or AdminConfigService()  # Uses config DB session
        self._schema_service = None

    def close(self) -> None:
        """Release the self-created config-DB session (no-op when injected)."""
        if self._owns_admin_config and self.admin_config:
            self.admin_config.close()

    @property
    def schema_service(self) -> SchemaService:
        if not self._schema_service:
            from app.db.session import config_engine, business_engine
            self._schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
        return self._schema_service

    async def query(
        self,
        question: str,
        provider: str = None,
        context: str = None,
        mode: str = "hybrid",
        history: List[Dict] = None,
        max_retries: int = 3,
        conversation_id: str = None,
        provider_kwargs: Dict = None,
        on_status: Callable = None,
        user_id: Optional[int] = None,
        scope: Optional[Dict[str, Any]] = None,
        allowed_contexts: Optional[frozenset] = None,
    ) -> QueryEngineResult:
        """
        Main entry point.

        allowed_contexts (Plan 7 Phase 4a): normalised names the caller's API key may use (None =
        unrestricted). A named context outside it raises ContextNotAllowed (403); auto-routing and
        the cache stay inside it.

        scope (Plan 7 Phase 3): row filter enforced at the SQL layer for this request,
        e.g. {"year_month": 202607} — every source resolution sees it (ScopeError = 400).

        Args:
            question: User's natural language question
            provider: Provider name override (claude/gemini/matcha)
            context: Data context override (revenue/expense/etc.)
            mode: "hybrid" (default) or "mcp"
            history: Conversation history
            max_retries: Max retry attempts
            conversation_id: For tracking
            provider_kwargs: Extra kwargs for provider creation (api_key, model, etc.)

        Returns:
            QueryEngineResult with query_result + warnings + context
        """
        token = request_scope.set(scope or None)
        pin = request_pinned.set(allowed_contexts is not None)  # restricted key: see data_sources.request_pinned
        llm = request_llm_policy.set(None)  # Phase 4.5: set once the context's source is known (_execute_query)
        try:
            return await self._query(question, provider, context, mode, history, max_retries,
                                     conversation_id, provider_kwargs, on_status, user_id, scope, allowed_contexts)
        finally:
            request_llm_policy.reset(llm)
            request_pinned.reset(pin)
            request_scope.reset(token)

    async def _query(self, question, provider, context, mode, history, max_retries,
                     conversation_id, provider_kwargs, on_status, user_id, scope, allowed_contexts=None) -> QueryEngineResult:
        """Body of query() — runs with request_scope set."""
        start_time = time.time()
        if context:  # before the cache, before any LLM call — and only the stored name travels on
            context = canonical_context(context, allowed_contexts)
        provider_kwargs = provider_kwargs or {}

        # Load config once
        ai_config = self.admin_config.get_ai_config() if self.admin_config else {}
        feature_flags = self.admin_config.get_feature_flags() if self.admin_config else {}

        # --- Query Result Cache: first-turn questions only ---
        # SQL depends on conversation history (follow-up filter inheritance),
        # so caching with history would leak results across conversations.
        use_cache = not history
        selected_provider_name = provider or ai_config.get("default_provider", settings.AI_PROVIDER)
        context_name_for_cache = context or "auto"
        # scope in the key: the same question under another scope is another answer (unscoped keys unchanged)
        scope_key = json.dumps(scope, sort_keys=True, default=str) if scope else ""
        if scope_key:
            context_name_for_cache += "|" + scope_key
        if allowed_contexts is not None:  # "auto" routes differently under another allowlist
            context_name_for_cache += "|allow:" + "\x1f".join(sorted(allowed_contexts))
        qcache_key = _cache_key(question, selected_provider_name, context_name_for_cache)
        if use_cache:
            cached = _cache_get(qcache_key)
            # Plan 7: an answer read from another source — or an older build of it — is a miss
            if cached is not None:
                current = source_resolver.for_context(cached.context_name)
                policy, providers = _source_policy(current)
                # Phase 4.5: an answer produced under another policy, or by a provider the source no longer allows
                if (cached.source_version != current.version or cached.llm_policy != policy
                        or (providers is not None and cached.provider_used not in providers)):
                    cached = None
            if cached is not None:
                from dataclasses import replace
                from app.services.ai.trace import emit, new_trace
                logger.info(f"QueryEngine: Cache HIT for question (key={qcache_key[:12]}…)")
                trace = new_trace(question)
                trace.cache_hit = True
                trace.provider = selected_provider_name
                trace.context = cached.context_name
                trace.total_s = round(time.time() - start_time, 4)
                emit(trace)
                # replace() = shallow copy — don't mutate the shared cached object
                return replace(cached, execution_time_ms=(time.time() - start_time) * 1000)

        # --- Request dedup: block identical requests within N seconds ---
        dedup_key = _dedup_mark(question + scope_key, selected_provider_name, user_id)
        if dedup_key is None:
            logger.warning(f"QueryEngine: Dedup — duplicate request blocked: {question[:50]}…")
            return QueryEngineResult(
                query_result=QueryResult(
                    question=question, sql_query="", data=[],
                    explanation="คำถามซ้ำ กรุณารอสักครู่แล้วลองใหม่",
                    tokens_used=0, provider=selected_provider_name,
                    error="duplicate_request"
                ),
                # REMAIN-9.3: the dataclass default "revenue" would be saved to chat history and
                # steer the follow-up into the wrong context
                context_name=self._resolve_context(question, context, history, allowed_contexts),
                execution_time_ms=(time.time() - start_time) * 1000,
                provider_used=selected_provider_name,
            )

        try:
            engine_result = await self._execute_query(
                question=question,
                provider=provider,
                context=context,
                mode=mode,
                history=history,
                max_retries=max_retries,
                provider_kwargs=provider_kwargs,
                on_status=on_status,
                ai_config=ai_config,
                feature_flags=feature_flags,
                use_cache=use_cache,
                qcache_key=qcache_key,
                start_time=start_time,
                conversation_id=conversation_id,
                allowed_contexts=allowed_contexts,
            )
        except BaseException:
            _dedup_release(dedup_key)  # failed — allow immediate retry
            raise

        if engine_result.query_result.error:
            _dedup_release(dedup_key)
        return engine_result

    async def _execute_query(
        self,
        question: str,
        provider: Optional[str],
        context: Optional[str],
        mode: str,
        history: Optional[List[Dict]],
        max_retries: int,
        provider_kwargs: Dict,
        on_status: Optional[Callable],
        ai_config: dict,
        feature_flags: dict,
        use_cache: bool,
        qcache_key: str,
        start_time: float,
        conversation_id: Optional[str] = None,
        allowed_contexts: Optional[frozenset] = None,
    ) -> QueryEngineResult:
        """Query pipeline after cache/dedup gates (split out so dedup can wrap it)."""
        # 1. Detect context → its data source (Plan 7): legacy = business DB เดิม via MCP,
        # file source = DuckDB in-process. Everything below reads through these two.
        context_name = self._resolve_context(question, context, history, allowed_contexts)
        source = source_resolver.for_context(context_name)
        if source.adapter is None:
            schema_service, mcp_client = self.schema_service, self.mcp_client
        else:
            from app.db.session import config_engine
            schema_service = SchemaService(db_engine=config_engine, business_engine=source.engine)
            mcp_client = SourceBoundMCPClient(self.mcp_client, source)

        # Phase 4.5: from here on every provider call of this request is held to the source's policy
        llm_policy, llm_providers = _source_policy(source)
        request_llm_policy.set(RequestPolicy(policy=llm_policy, providers=llm_providers,
                                             source=str(source.name), question=question))
        if llm_policy != FULL:
            mcp_client = PolicyMCPClient(mcp_client)
            # earlier answers explain earlier rows, and two-pass writes the history into the prompt text
            # itself (build_history_context) where the provider guard can't tell it from the question
            history = history_without_answers(history)

        # 2. Resolve provider
        selected_provider = provider or ai_config.get("default_provider", settings.AI_PROVIDER)

        # Build provider kwargs dynamically: DB → .env → hardcoded fallback
        resolved_kwargs = _build_provider_kwargs(
            selected_provider,
            ai_config,
            admin_config_service=self.admin_config,
        )
        # Caller overrides take precedence
        for k, v in resolved_kwargs.items():
            provider_kwargs.setdefault(k, v)

        provider_instance = provider_registry.create_provider(selected_provider, **provider_kwargs)
        if not provider_instance or not provider_instance.is_configured():
            # Try fallback
            provider_instance = provider_registry.get_fallback(selected_provider, **provider_kwargs)

        if not provider_instance:
            raise ValueError(f"No available provider for '{selected_provider}'")

        if llm_providers is not None and provider_instance.name in llm_providers:
            selected_provider = provider_instance.name  # get_fallback may have switched — the cache check reads it
        elif llm_providers is not None:
            if provider:  # the caller named it — refuse, never switch silently
                raise LLMPolicyError(f"provider '{provider}' ไม่อยู่ใน llm_provider_allowlist ของ source '{source.name}'")
            provider_instance = None
            for name in sorted(llm_providers):
                candidate = provider_registry.create_provider(
                    name, **_build_provider_kwargs(name, ai_config, admin_config_service=self.admin_config))
                if candidate and candidate.is_configured():
                    provider_instance, selected_provider = candidate, name
                    break
            if provider_instance is None:
                raise LLMPolicyError(f"ไม่มี provider ใน llm_provider_allowlist ของ source '{source.name}' ที่พร้อมใช้")

        # Tier-based cost control: classify query complexity and select model
        tier_enabled = feature_flags.get("tier_classification_enabled", False) if self.admin_config else False
        force_tier = feature_flags.get("force_tier", None) if self.admin_config else None
        if tier_enabled or force_tier:
            tier = query_classifier.classify(question, force_tier=force_tier)
            tier_model = provider_instance.get_model(tier)
            if tier_model and tier_model != provider_instance.model:
                logger.info(f"Tier classification: '{tier}' → switching model from '{provider_instance.model}' to '{tier_model}'")
                provider_instance.model = tier_model

        # Resolve cheap model for lightweight stages (intent extraction, explanation)
        cheap_model = provider_instance.get_model("cheap")
        if cheap_model and cheap_model != provider_instance.model:
            logger.info(f"Per-stage model: cheap='{cheap_model}', default='{provider_instance.model}'")
        else:
            cheap_model = None  # same as default — no swap needed

        ai_service = AIService(provider=provider_instance, mcp_client=mcp_client,
                               workspace=workspace_of_context(context_name))  # RAG retrieves from that workspace's brain

        # 3. Build system prompt
        system_prompt = schema_service.build_system_prompt(
            ai_provider=selected_provider,
            include_samples=llm_policy == FULL,  # also part of the prompt cache key
            language="thai",
            context_name=context_name,
            rag_enabled=True,
        )
        system_prompt += getattr(source.adapter, "scope_note", "")  # Phase 3: rows are pre-filtered

        # 4. Execute query

        from app.services.ai.trace import emit, new_trace
        trace = new_trace(question)
        trace.provider = selected_provider
        trace.context = context_name

        if mode == "hybrid":
            result = await ai_service.query_hybrid(
                question=question,
                system_prompt=system_prompt,
                max_retries=max_retries,
                history=history,
                on_status=on_status or (lambda status: logger.info(
                    f"QueryEngine status: attempt={status.attempt}/{status.max_attempts}, "
                    f"status={status.status}, message={status.message}"
                )),
                context_name=context_name,
                two_pass_enabled=feature_flags.get("two_pass_enabled", False),
                value_lookup_enabled=feature_flags.get("value_lookup_enabled", False),
                value_verification_enabled=feature_flags.get("value_verification_enabled", True),
                cheap_model=cheap_model,
                schema_service=schema_service,
                trace=trace,
                template_answers_enabled=feature_flags.get("template_answers_enabled", False),
                conversation_id=conversation_id,
                intent_state_enabled=feature_flags.get("intent_state_enabled", False),
                escalation_ladder_enabled=feature_flags.get("escalation_ladder_enabled", False),
                escalation_tool_loop_enabled=feature_flags.get("escalation_tool_loop_enabled", False),
                latency_budget_s=float(feature_flags.get("query_latency_budget_s", 45) or 45),
            )
        else:
            result = await ai_service.query_with_retry(
                question=question,
                max_retries=max_retries,
                history=history,
                explain=True,
                context_name=context_name,
            )

        # 5. Detect warnings
        warning_detector = WarningDetector(
            mcp_client=mcp_client,
            schema_service=schema_service,
        )
        warnings = await warning_detector.detect(
            data=result.data,
            sql_query=result.sql_query,
            context_name=context_name,
        )

        execution_time = (time.time() - start_time) * 1000

        trace.error = result.error or ""
        trace.total_s = round(execution_time / 1000, 4)
        emit(trace)

        # 6. Return combined result
        engine_result = QueryEngineResult(
            query_result=result,
            context_name=context_name,
            warnings=warnings,
            execution_time_ms=execution_time,
            provider_used=selected_provider,
            source_version=source.version,
            data_as_of=source.data_as_of,
            llm_policy=llm_policy,
        )

        # --- Query Result Cache: store successful result ---
        if use_cache and result.data and not result.error and stores_results(context_name):
            _cache_set(qcache_key, engine_result)
            logger.info(f"QueryEngine: Cached result (key={qcache_key[:12]}…, rows={len(result.data)})")

        return engine_result

    def _resolve_context(
        self,
        question: str,
        explicit_context: str = None,
        history: List[Dict] = None,
        allowed_contexts: Optional[frozenset] = None,
    ) -> str:
        """
        Determine data context from question + history.

        Priority:
        1. Explicit context from request
        2. Auto-detect from question keywords (DB-driven)
        3. Previous conversation context (from history)
        4. Default to highest-priority context from DB
        """
        if explicit_context:
            return explicit_context

        # Auto-detect from question
        detected = detect_context_from_question(question, self.schema_service, allowed_contexts)
        check_context(detected, allowed_contexts)  # whatever the router did, never outside the allowlist

        # If history has context info, consider maintaining it
        # (simple heuristic: if detected is just default and history suggests otherwise)

        return detected

    def _detect_context_from_question(self, question: str) -> str:
        """Auto-detect context — delegates to standalone function."""
        return detect_context_from_question(question, self.schema_service)

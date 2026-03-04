"""
NT AI Assistant - Query Engine
=================================
Core orchestrator for query processing.
Can be called from Web API, Telegram, tests, or scripts.

Usage:
    engine = QueryEngine(mcp_client=mcp, db_session=db)
    result = await engine.query("รายได้เดือนนี้เท่าไหร่")
"""

import time
import uuid
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.providers.base import QueryResult
from app.providers.registry import provider_registry
from app.services.ai_service import AIService
from app.services.mcp_client import MCPClientService
from app.services.admin_config_service import AdminConfigService
from app.services.schema_service import SchemaService
from app.services.warning_detector import WarningDetector
from app.services.query_classifier import query_classifier
from app.schemas.chat import DataWarning
from app.config import settings

logger = logging.getLogger(__name__)


def detect_context_from_question(question: str, schema_service: SchemaService = None) -> str:
    """
    Auto-detect context from user's question using DB keywords.

    Standalone function — usable from chat.py or anywhere without QueryEngine instance.
    """
    question_lower = question.lower()
    context_scores = {}

    if schema_service:
        try:
            contexts = schema_service.get_all_contexts()
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
            contexts = schema_service.get_all_contexts()
            if contexts:
                return contexts[0].get('name', 'revenue')
        except Exception:
            pass

    return "revenue"


@dataclass
class QueryEngineResult:
    """Combined result from QueryEngine — wraps QueryResult + extras"""
    query_result: QueryResult
    context_name: str = "revenue"
    warnings: List[DataWarning] = field(default_factory=list)
    execution_time_ms: float = 0.0
    provider_used: str = ""


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
        self.admin_config = admin_config or (AdminConfigService(db_session) if db_session else None)
        self._schema_service = None

    @property
    def schema_service(self) -> SchemaService:
        if not self._schema_service:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            self._schema_service = SchemaService(db_path=db_path)
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
    ) -> QueryEngineResult:
        """
        Main entry point.

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
        start_time = time.time()
        provider_kwargs = provider_kwargs or {}

        # Load config once
        ai_config = self.admin_config.get_ai_config() if self.admin_config else {}
        feature_flags = self.admin_config.get_feature_flags() if self.admin_config else {}

        # 1. Resolve provider
        selected_provider = provider or ai_config.get("default_provider", settings.AI_PROVIDER)

        # Build provider kwargs from admin config + settings
        if selected_provider == "claude":
            provider_kwargs.setdefault("api_key", settings.ANTHROPIC_API_KEY)
            provider_kwargs.setdefault("model", ai_config.get("claude_model", settings.CLAUDE_MODEL))
            provider_kwargs.setdefault("extended_thinking", ai_config.get("claude_extended_thinking", False))
            provider_kwargs.setdefault("thinking_budget_tokens", ai_config.get("claude_thinking_budget_tokens", 8000))
        elif selected_provider == "gemini":
            provider_kwargs.setdefault("api_key", settings.GOOGLE_AI_API_KEY)
            provider_kwargs.setdefault("model", ai_config.get("gemini_model", settings.GEMINI_MODEL))
        elif selected_provider == "matcha":
            provider_kwargs.setdefault("api_key", settings.MATCHA_AI_API_KEY)
            provider_kwargs.setdefault("api_url", ai_config.get("matcha_api_url") or settings.MATCHA_API_URL)
            provider_kwargs.setdefault("model", ai_config.get("matcha_model", settings.MATCHA_MODEL))

        provider_instance = provider_registry.create_provider(selected_provider, **provider_kwargs)
        if not provider_instance or not provider_instance.is_configured():
            # Try fallback
            provider_instance = provider_registry.get_fallback(selected_provider, **provider_kwargs)

        if not provider_instance:
            raise ValueError(f"No available provider for '{selected_provider}'")

        # Tier-based cost control: classify query complexity and select model
        tier_enabled = feature_flags.get("tier_classification_enabled", False) if self.admin_config else False
        force_tier = feature_flags.get("force_tier", None) if self.admin_config else None
        if tier_enabled or force_tier:
            tier = query_classifier.classify(question, force_tier=force_tier)
            tier_model = provider_instance.get_model(tier)
            if tier_model and tier_model != provider_instance.model:
                logger.info(f"Tier classification: '{tier}' → switching model from '{provider_instance.model}' to '{tier_model}'")
                provider_instance.model = tier_model

        ai_service = AIService(provider=provider_instance, mcp_client=self.mcp_client)

        # 2. Detect context
        context_name = self._resolve_context(question, context, history)

        # 3. Build system prompt
        system_prompt = self.schema_service.build_system_prompt(
            ai_provider=selected_provider,
            include_samples=True,
            language="thai",
            context_name=context_name,
            rag_enabled=True,
        )

        # 4. Execute query

        if mode == "hybrid":
            result = await ai_service.query_hybrid(
                question=question,
                system_prompt=system_prompt,
                max_retries=max_retries,
                history=history,
                on_status=lambda status: logger.info(
                    f"QueryEngine status: attempt={status.attempt}/{status.max_attempts}, "
                    f"status={status.status}, message={status.message}"
                ),
                context_name=context_name,
                two_pass_enabled=feature_flags.get("two_pass_enabled", False),
                value_lookup_enabled=feature_flags.get("value_lookup_enabled", False),
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
            mcp_client=self.mcp_client,
            schema_service=self.schema_service,
        )
        warnings = await warning_detector.detect(
            data=result.data,
            sql_query=result.sql_query,
            context_name=context_name,
        )

        execution_time = (time.time() - start_time) * 1000

        # 6. Return combined result
        return QueryEngineResult(
            query_result=result,
            context_name=context_name,
            warnings=warnings,
            execution_time_ms=execution_time,
            provider_used=selected_provider,
        )

    def _resolve_context(
        self,
        question: str,
        explicit_context: str = None,
        history: List[Dict] = None,
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
        detected = self._detect_context_from_question(question)

        # If history has context info, consider maintaining it
        # (simple heuristic: if detected is just default and history suggests otherwise)

        return detected

    def _detect_context_from_question(self, question: str) -> str:
        """Auto-detect context — delegates to standalone function."""
        return detect_context_from_question(question, self.schema_service)

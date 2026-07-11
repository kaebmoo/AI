"""
NT AI Assistant - Claude Provider
===================================
Anthropic Claude API implementation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Union

from app.providers.base import AIProvider
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import (
    parse_explanation_response,
    enforce_time_series_rule,
    enforce_dimension_family_rule,
    build_explain_prompt,
    enrich_chart_config,
)
from app.config import settings

logger = logging.getLogger(__name__)


class ClaudeProvider(AIProvider):
    """Claude API provider"""

    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 8000,
    ):
        self.api_key = api_key
        self.model = model
        self.extended_thinking = extended_thinking
        self.thinking_budget_tokens = thinking_budget_tokens
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    @ai_retry
    async def generate_sql(self, question: str, system_prompt: str, tools: List[Dict], history: List[Dict] = []) -> Dict[str, Any]:

        system_prompt += "\nUse the provided tools to fetch database schema, find values, or execute SQL queries. Do not make up schema."

        messages = []
        for msg in history:
            if msg.get("role") and msg.get("content"):
                messages.append({"role": msg.get("role"), "content": msg.get("content")})

        # In tool-use turns the question is already in history — an empty user
        # message would be rejected by the Anthropic API
        if question:
            messages.append({"role": "user", "content": question})

        # Sanitize tools for Anthropic format
        sanitized_tools = []
        for t in tools:
            sanitized_tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t["input_schema"]
            })

        # Prompt caching: system prompt as content blocks with cache_control
        system_with_cache = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # Prompt caching: mark last tool with cache_control as breakpoint
        if sanitized_tools:
            sanitized_tools[-1]["cache_control"] = {"type": "ephemeral"}

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_with_cache,
            tools=sanitized_tools,
            messages=messages,
            temperature=0,  # Deterministic SQL generation (Claude 4.5+ rejects temperature+top_p together)
        )

        # Log prompt caching metrics
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        cache_created = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        if cache_created or cache_read:
            logger.info(
                f"Claude cache — created: {cache_created}, "
                f"read: {cache_read}, input: {response.usage.input_tokens}"
            )

        return {
            "response": response,
            "tokens_used": tokens_used
        }

    @ai_retry
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None, hierarchy_info: Optional[list] = None, schema_metadata: Optional[list] = None) -> Union[str, Dict]:
        prompt = build_explain_prompt(
            question=question, sql=sql, data=data,
            dimension_families=dimension_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )
        # Prompt caching: system prompt with cache_control
        system_with_cache = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system_with_cache,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3  # Slightly varied but stable explanations
        )

        # Log prompt caching metrics
        cache_created = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        if cache_created or cache_read:
            logger.info(
                f"Claude cache (explain) — created: {cache_created}, "
                f"read: {cache_read}, input: {response.usage.input_tokens}"
            )

        content = response.content[0].text

        # Use shared post-processor
        time_columns = [m['column_name'] for m in schema_metadata
                        if m.get('dimension_group') == 'time_period'] if schema_metadata else None
        parsed_result = parse_explanation_response(content)
        parsed_result = enforce_time_series_rule(parsed_result, time_columns=time_columns)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)
        parsed_result = enrich_chart_config(
            parsed_result=parsed_result,
            data=data,
            schema_metadata=schema_metadata,
            chart_title=parsed_result.get("chart_title", ""),
        )
        return parsed_result

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        # Extended Thinking support
        THINKING_SUPPORTED_PREFIXES = ("claude-sonnet-4", "claude-opus-4", "claude-haiku-4")
        model_supports_thinking = any(self.model.startswith(p) for p in THINKING_SUPPORTED_PREFIXES)
        use_thinking = self.extended_thinking and model_supports_thinking

        # Prompt caching: system prompt with cache_control
        sys_content = system_prompt or ""
        if sys_content:
            sys_content = [
                {
                    "type": "text",
                    "text": sys_content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # Build messages: native multi-turn history + current prompt
        messages = []
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "system": sys_content,
            "messages": messages,
        }

        if use_thinking:
            kwargs["max_tokens"] = self.thinking_budget_tokens + 2000
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget_tokens}
            logger.info(f"ClaudeProvider: Extended Thinking enabled (budget={self.thinking_budget_tokens}, model={self.model})")
        else:
            kwargs["max_tokens"] = 4000
            kwargs["temperature"] = 0.3  # Stable intent extraction
            if self.extended_thinking and not model_supports_thinking:
                logger.warning(f"ClaudeProvider: Extended Thinking requested but model={self.model} does not support it, using standard mode")

        response = await self.client.messages.create(**kwargs)

        # Extract text blocks only (skip thinking blocks)
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

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
    build_dimension_family_prompt,
)
from app.config import settings

logger = logging.getLogger(__name__)


class ClaudeProvider(AIProvider):
    """Claude API provider"""

    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
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

    def get_model(self, tier: str = "default") -> str:
        if tier == "cheap":
            return "claude-haiku-3-5-20241022"
        return self.model

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
            messages=messages
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
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None) -> Union[str, Dict]:
        data_sample = data[:30]
        family_prompt = build_dimension_family_prompt(dimension_families) if dimension_families else ""
        prompt = f"""Question: {question}
SQL: {sql}
Results (First 30 rows):
{json.dumps(data_sample, ensure_ascii=False, indent=2)}

Format numbers nicely. Summary only if many rows.
{family_prompt}

Ensure the "explanation" value is formatted as **beautiful Markdown**:
- Use `###` for main summaries and `####` for subsections.
- Use **bold text** (`**value**`) to highlight key metrics and numbers.
- Use bullet points (`-`) when listing multiple items (e.g., breakdown by group).
- Use blockquotes (`>`) to emphasize key insights or the most important finding.
- Keep the language natural and strictly in **Thai**.

Example of good Markdown formatting for "explanation":
"### สรุปยอดขาย\n\nยอดขายรวมทั้งหมดคือ **1,500,000 บาท** โดยแบ่งตามแผนกดังนี้:\n- **แผนก IT**: 800,000 บาท\n- **แผนก HR**: 500,000 บาท\n- **แผนก Sales**: 200,000 บาท\n\n> 💡 **Highlight**: แผนก IT มียอดขายสูงสุด คิดเป็นสัดส่วนมากกว่า 50% ของยอดขายทั้งหมด"

CRITICAL: You must analyze the data and recommend the best visualization type.
Return the result as a JSON object with these keys:
1. "explanation": The beautifully formatted Thai markdown explanation.
2. "visualization": One of ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'table', 'single_value', 'grouped_bar']
3. "chart_config": Object with column mappings for the chart:
   - "category_column": The column name for X-axis labels (the PRIMARY grouping)
   - "measure_column": The column name for Y-axis values (e.g., total, sum, amount)
   - "series_column": (optional) The column for SECONDARY grouping/comparison (e.g., month, year for time comparison)
4. "display_hint": How to display the TABLE (separate from chart). Choose ONE:
   - 'hierarchical': Use when data has MULTIPLE categorical (non-time) columns where one is the parent of another.
     Rule: If the columns represent a HIERARCHY (e.g., BUSINESS_GROUP > SERVICE_GROUP, or division > department > section),
     always use 'hierarchical' — even if there are only 2 levels.
     This is the correct choice when the question asks to show data grouped by a higher-level category.
   - 'crosstab': Use ONLY when comparing values ACROSS a time dimension (month, quarter, year) OR when
     the question explicitly asks to compare one category against another (e.g., "compare groups by section").
     Do NOT use 'crosstab' for parent-child hierarchy data.
   - 'flat': Use for single-dimension data or when already aggregated to one level.
5. "hierarchy_columns": (REQUIRED if display_hint='hierarchical') Array of actual column names ordered from HIGHEST (parent) to LOWEST (child) level.
   Example: BUSINESS_GROUP is parent, SERVICE_GROUP is child → ["BUSINESS_GROUP", "SERVICE_GROUP"]
   Example: division > department > section → ["division", "department", "section"]

IMPORTANT for time-based comparisons:
- **CRITICAL**: If a Time column exists (Month, Year, Date), YOU MUST USE IT AS 'category_column' (X-axis).
- **Comparison**: Use the other dimension (Department, Account, Section) as 'series_column' (Legend).
     - **Legend Rule**: Prefer DESCRIPTIVE columns (e.g., 'department_name', 'account_name') over ID/Code columns (e.g., 'gl_code', 'id') for better readability.
     - If < 5 series: Suggest 'grouped_bar' or 'line_chart'
     - If > 5 series: Suggest 'stacked_bar' (to avoid clutter)
- **Exception**: Only use Time as Series if explicitly asked to "Compare Years" (Year-over-Year).

Example for hierarchical data (show all services inside each group):
{{
  "explanation": "### ยอดขายแยกตามแผนก\n\nยอดขายรวม...",
  "visualization": "bar_chart",
  "chart_config": {{
    "category_column": "service_group",
    "measure_column": "total_revenue"
  }},
  "display_hint": "hierarchical",
  "hierarchy_columns": ["business_unit", "service_group", "product_name"]
}}

Example for time comparison (grouped bar) - showing each category with bars for each month:
{{
  "explanation": "### ค่าใช้จ่ายแยกตามเดือน\n\nค่าใช้จ่ายรวม...",
  "visualization": "grouped_bar",
  "chart_config": {{
    "category_column": "เดือน",
    "measure_column": "ยอดค่าใช้จ่าย",
    "series_column": "หมวดบัญชี"
  }},
  "display_hint": "crosstab"
}}
"""
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
            messages=[{"role": "user", "content": prompt}]
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
        parsed_result = parse_explanation_response(content)
        parsed_result = enforce_time_series_rule(parsed_result)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)
        return parsed_result

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        # Extended Thinking support
        THINKING_SUPPORTED_PREFIXES = ("claude-sonnet-4", "claude-opus-4")
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
            if self.extended_thinking and not model_supports_thinking:
                logger.warning(f"ClaudeProvider: Extended Thinking requested but model={self.model} does not support it, using standard mode")

        response = await self.client.messages.create(**kwargs)

        # Extract text blocks only (skip thinking blocks)
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

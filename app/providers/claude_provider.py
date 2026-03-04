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
from app.providers.chart_postprocessor import parse_explanation_response, enforce_time_series_rule
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

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            tools=sanitized_tools,
            messages=messages
        )

        return {
            "response": response,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens
        }

    @ai_retry
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> Union[str, Dict]:
        data_sample = data[:30]
        prompt = f"""Question: {question}
SQL: {sql}
Results (First 30 rows):
{json.dumps(data_sample, ensure_ascii=False, indent=2)}

Format numbers nicely. Summary only if many rows.

CRITICAL: You must analyze the data and recommend the best visualization type.
Return the result as a JSON object with these keys:
1. "explanation": The Thai explanation text.
2. "visualization": One of ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'table', 'single_value', 'grouped_bar']
3. "chart_config": Object with column mappings for the chart:
   - "category_column": The column name for X-axis labels (the PRIMARY grouping)
   - "measure_column": The column name for Y-axis values (e.g., total, sum, amount)
   - "series_column": (optional) The column for SECONDARY grouping/comparison (e.g., month, year for time comparison)

IMPORTANT for time-based comparisons:
- **CRITICAL**: If a Time column exists (Month, Year, Date), YOU MUST USE IT AS 'category_column' (X-axis).
- **Comparison**: Use the other dimension (Department, Account, Section) as 'series_column' (Legend).
     - **Legend Rule**: Prefer DESCRIPTIVE columns (e.g., 'department_name', 'account_name') over ID/Code columns (e.g., 'gl_code', 'id') for better readability.
     - If < 5 series: Suggest 'grouped_bar' or 'line_chart'
     - If > 5 series: Suggest 'stacked_bar' (to avoid clutter)
- **Exception**: Only use Time as Series if explicitly asked to "Compare Years" (Year-over-Year).

Example for simple bar chart:
{{
  "explanation": "ยอดขายแยกตามแผนก...",
  "visualization": "bar_chart",
  "chart_config": {{
    "category_column": "department_name",
    "measure_column": "total_sales"
  }}
}}

Example for time comparison (grouped bar) - showing each category with bars for each month:
{{
  "explanation": "ค่าใช้จ่ายรายหมวดบัญชี แยกตามเดือน...",
  "visualization": "grouped_bar",
  "chart_config": {{
    "category_column": "เดือน",
    "measure_column": "ยอดค่าใช้จ่าย",
    "series_column": "หมวดบัญชี"
  }}
}}
"""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.content[0].text

        # Use shared post-processor
        parsed_result = parse_explanation_response(content)
        parsed_result = enforce_time_series_rule(parsed_result)
        return parsed_result

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Extended Thinking support
        THINKING_SUPPORTED_PREFIXES = ("claude-sonnet-4", "claude-opus-4")
        model_supports_thinking = any(self.model.startswith(p) for p in THINKING_SUPPORTED_PREFIXES)
        use_thinking = self.extended_thinking and model_supports_thinking

        kwargs = {
            "model": self.model,
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": prompt}],
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

"""
NT AI Assistant - Matcha Provider
===================================
Matcha AI (OpenAI Compatible) implementation via NT Gateway.
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Union

import httpx

from app.providers.base import AIProvider
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import (
    parse_explanation_response,
    enforce_time_series_rule,
    enforce_dimension_family_rule,
    build_dimension_family_prompt,
    auto_detect_chart_config,
)
from app.config import settings

logger = logging.getLogger(__name__)


class MatchaProvider(AIProvider):
    """Matcha AI (OpenAI Compatible)"""

    name = "matcha"

    def __init__(self, api_key: str, api_url: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_url)

    def get_model(self, tier: str = "default") -> str:
        if tier == "cheap":
            return "gpt-4o-mini"
        return self.model

    @ai_retry
    async def generate_sql(self, question: Optional[str], system_prompt: str, tools: List[Dict], history: List[Dict] = []) -> Dict[str, Any]:

        # Convert tools to OpenAI format
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"]
                }
            })

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            new_msg = {k: v for k, v in msg.items() if k in ['role', 'content', 'tool_calls', 'tool_call_id', 'name']}
            messages.append(new_msg)

        if question:
            messages.append({"role": "user", "content": question})

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        payload = {
            'model': self.model,
            'messages': messages,
            'tool_choice': 'auto',
            'temperature': 0.1
        }

        if openai_tools:
            payload['tools'] = openai_tools

        async with httpx.AsyncClient(verify=settings.MATCHA_SSL_VERIFY, timeout=settings.MATCHA_TIMEOUT) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()

        return {
            "response": result,
            "tokens_used": result.get('usage', {}).get('total_tokens', 0)
        }

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """Explain result using Matcha/OpenAI and return Config"""

        data_preview = json.dumps(data[:5], ensure_ascii=False, default=str)
        family_prompt = build_dimension_family_prompt(dimension_families) if dimension_families else ""

        prompt = f"""
Query: {question}
SQL: {sql}

Data Preview:
{data_preview}
{family_prompt}

Based on the data, provide:
1. A brief explanation of the trends/values (in Thai).
   - IMPORTANT: Format the explanation as **beautiful Markdown**.
   - Use `###` for headings, **bold text** for important metrics/numbers.
   - Use bullet points (`-`) for multiple items.
   - Use blockquotes (`>`) to emphasize key insights.
2. The BEST chart type to visualize this (bar_chart, line_chart, pie_chart, grouped_bar, stacked_bar, table, single_value).
3. The configuration:
   - category_column: X-axis (Grouping). Rule: Use 'month' for trends, 'department'/'group' for comparison.
   - measure_column: Y-axis (Value).
   - series_column: Comparison/Legend (Optional). Rule: If comparing multiple groups over time, use this. Prefer NAME columns over CODE columns.
4. display_hint: How to render the table. Choose ONE:
   - 'hierarchical': Use when data has MULTIPLE categorical (non-time) columns where one is the parent of another.
     Rule: If the columns represent a HIERARCHY (e.g., BUSINESS_GROUP > SERVICE_GROUP, or division > department > section),
     always use 'hierarchical' — even if there are only 2 levels.
     Do NOT use crosstab for parent-child hierarchy data without time dimension.
   - 'crosstab': Use ONLY when comparing values ACROSS a time dimension (month, quarter, year) OR when
     user explicitly asks to compare one category against another.
   - 'flat': simple flat rows — single dimension or already one-level data.
5. hierarchy_columns: (REQUIRED if display_hint='hierarchical') Actual column names ordered HIGHEST (parent) to LOWEST (child).
   Example: BUSINESS_GROUP > SERVICE_GROUP → ["BUSINESS_GROUP", "SERVICE_GROUP"]

IMPORTANT: Return VALID JSON only. Do not wrap in markdown unless necessary.
Structure:
{{
  "explanation": "### สรุปข้อมูล\\n\\nรายได้รวม **...",
  "visualization": "...",
  "chart_config": {{
      "category_column": "...",
      "measure_column": "...",
      "series_column": "..."
  }},
  "display_hint": "hierarchical",
  "hierarchy_columns": ["...", "...", "..."]
}}
"""
        response_text = await self.generate_content(prompt, system_prompt)

        # Use shared post-processor
        parsed_result = parse_explanation_response(response_text)
        parsed_result = enforce_time_series_rule(parsed_result)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)

        # Fallback: If no chart_config, try to infer from data
        if "chart_config" not in parsed_result and data and len(data) > 0:
            logger.info("Matcha: No chart_config found, attempting auto-detection")
            parsed_result = auto_detect_chart_config(data, parsed_result)

        return parsed_result

    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Matcha/OpenAI-compatible API"""
        logger.info(f"MatchaProvider.generate_content called")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': 0.1
        }

        try:
            async with httpx.AsyncClient(verify=settings.MATCHA_SSL_VERIFY, timeout=settings.MATCHA_TIMEOUT) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()

            content = result['choices'][0]['message']['content']
            return content

        except Exception as e:
            logger.error(f"MatchaProvider: API call failed: {type(e).__name__}: {e}")
            raise

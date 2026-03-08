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
    build_explain_prompt,
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

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None, hierarchy_info: Optional[list] = None, schema_metadata: Optional[list] = None) -> Dict[str, Any]:
        """Explain result using Matcha/OpenAI and return Config"""
        prompt = build_explain_prompt(
            question=question, sql=sql, data=data,
            dimension_families=dimension_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )
        response_text = await self.generate_content(prompt, system_prompt)

        # Use shared post-processor
        time_columns = [m['column_name'] for m in schema_metadata
                        if m.get('dimension_group') == 'time_period'] if schema_metadata else None
        parsed_result = parse_explanation_response(response_text)
        parsed_result = enforce_time_series_rule(parsed_result, time_columns=time_columns)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)

        # Fallback: If no chart_config, try to infer from data
        if "chart_config" not in parsed_result and data and len(data) > 0:
            logger.info("Matcha: No chart_config found, attempting auto-detection")
            parsed_result = auto_detect_chart_config(data, parsed_result, schema_metadata=schema_metadata)

        return parsed_result

    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        """Generate content using Matcha/OpenAI-compatible API with optional native multi-turn history."""
        logger.info(f"MatchaProvider.generate_content called")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
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

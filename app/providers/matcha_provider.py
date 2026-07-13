"""
NT AI Assistant - Matcha Provider
===================================
Matcha AI (OpenAI Compatible) implementation via NT Gateway.
"""

import json
import logging
from typing import Dict, List, Optional, Any

import httpx

from app.providers.base import AIProvider, TokenUsage
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import (
    build_explain_prompt,
    postprocess_chart_result,
)
from app.config import settings

logger = logging.getLogger(__name__)

# One-time debug log when the gateway omits the usage field
_no_usage_logged = False


class MatchaProvider(AIProvider):
    """Matcha AI (OpenAI Compatible)"""

    name = "matcha"

    def __init__(self, api_key: str, api_url: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        # None = unknown, True/False = remembered gateway capability for json_schema
        self._supports_json_schema = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_url)

    def _record_usage(self, result: Dict) -> None:
        """Populate last_usage from an OpenAI-compatible response (usage may be null/absent)."""
        usage = result.get("usage") or {}
        if not usage:
            global _no_usage_logged
            if not _no_usage_logged:
                logger.debug("Matcha gateway returned no usage field — token counts will be 0")
                _no_usage_logged = True
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        if not (input_tokens or output_tokens) and usage.get("total_tokens"):
            # Gateway sent only total_tokens — keep the total honest (booked as input)
            input_tokens = usage["total_tokens"]
        self.last_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
        )

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
            'temperature': 0,   # Deterministic SQL generation
            'top_p': 0.05,      # Narrow probability space for consistency
        }

        if openai_tools:
            payload['tools'] = openai_tools

        self.last_usage = None
        async with httpx.AsyncClient(verify=settings.MATCHA_SSL_VERIFY, timeout=settings.MATCHA_TIMEOUT) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()

        self._record_usage(result)
        return {
            "response": result,
            # From normalized usage — result["usage"] may be null (crashes .get)
            # or lack total_tokens even when prompt/completion counts exist
            "tokens_used": self.last_usage.total if self.last_usage else 0,
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

        return postprocess_chart_result(
            response_text,
            data=data,
            dimension_families=dimension_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )

    async def generate_structured(self, prompt: str, schema: Dict[str, Any], system_prompt: Optional[str] = None, schema_name: str = "result") -> Optional[Dict]:
        """Structured output via response_format json_schema, falling back to json_object.

        Gateway capability is remembered per instance so we don't probe every call.
        """
        async def _post(payload):
            headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}
            async with httpx.AsyncClient(verify=settings.MATCHA_SSL_VERIFY, timeout=settings.MATCHA_TIMEOUT) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        self.last_usage = None
        try:
            result = None
            if self._supports_json_schema is not False:
                try:
                    result = await _post({
                        "model": self.model, "messages": messages, "temperature": 0,
                        "response_format": {"type": "json_schema", "json_schema": {
                            "name": schema_name, "schema": schema, "strict": True}},
                    })
                    self._supports_json_schema = True
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (400, 422):
                        logger.info("Matcha gateway rejected json_schema — falling back to json_object")
                        self._supports_json_schema = False
                    else:
                        raise

            if result is None:
                # json_object mode + schema embedded in the prompt
                schema_prompt = f"{prompt}\n\nตอบเป็น JSON object ตาม schema นี้เท่านั้น:\n{json.dumps(schema, ensure_ascii=False)}"
                messages[-1] = {"role": "user", "content": schema_prompt}
                result = await _post({
                    "model": self.model, "messages": messages, "temperature": 0,
                    "response_format": {"type": "json_object"},
                })

            self._record_usage(result)
            content = result["choices"][0]["message"]["content"]
            return self._validate_required(json.loads(content), schema)
        except Exception as e:
            logger.warning(f"MatchaProvider.generate_structured failed: {e}")
            return None

    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        """Generate content using Matcha/OpenAI-compatible API with optional native multi-turn history."""
        logger.info("MatchaProvider.generate_content called")

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
            'temperature': 0.3  # Stable intent extraction / explanations
        }

        self.last_usage = None
        try:
            async with httpx.AsyncClient(verify=settings.MATCHA_SSL_VERIFY, timeout=settings.MATCHA_TIMEOUT) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()

            self._record_usage(result)
            content = result['choices'][0]['message']['content']
            return content

        except Exception as e:
            logger.error(f"MatchaProvider: API call failed: {type(e).__name__}: {e}")
            raise

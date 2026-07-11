"""
NT AI Assistant - Gemini Provider
===================================
Google Gemini API implementation.
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union

from app.providers.base import AIProvider, TokenUsage
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import (
    parse_explanation_response,
    enforce_time_series_rule,
    enforce_dimension_family_rule,
    build_explain_prompt,
    enrich_chart_config,
)

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Google Gemini API provider"""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def _run_async(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def _record_usage(self, response) -> None:
        """Populate last_usage from google-genai response.usage_metadata."""
        meta = getattr(response, "usage_metadata", None)
        self.last_usage = TokenUsage(
            input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
            cache_read_input_tokens=getattr(meta, "cached_content_token_count", 0) or 0,
            model=self.model,
        )

    @ai_retry
    async def generate_sql(self, question: str, system_prompt: str, tools: List[Dict], history: List[Dict] = []) -> Dict[str, Any]:
        from google.genai import types

        # Convert tools to Gemini format
        gemini_tools = []
        for t in tools:
            gemini_tools.append(types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t['name'],
                    description=t['description'],
                    parameters=t['input_schema']
                )
            ]))

        contents = []
        for msg in history:
            role = msg.get("role")

            if role == "model":
                parts = []
                if "parts_raw" in msg:
                    # Restore from raw dicts (preserving thought_signature)
                    for p_dict in msg["parts_raw"]:
                        try:
                            if hasattr(types.Part, 'from_dict'):
                                parts.append(types.Part.from_dict(p_dict))
                                continue
                        except Exception:
                            pass

                        # Fallback: Manual construction
                        try:
                            parts.append(types.Part(**p_dict))
                            continue
                        except Exception:
                            pass

                        # Last resort: Build Part manually
                        part = types.Part()
                        if "text" in p_dict:
                            part.text = p_dict["text"]
                        if "function_call" in p_dict:
                            fc = p_dict["function_call"]
                            part.function_call = types.FunctionCall(
                                name=fc["name"],
                                args=fc.get("args", {})
                            )
                        if "thought_signature" in p_dict:
                            try:
                                part.thought_signature = p_dict["thought_signature"]
                            except AttributeError:
                                pass
                        parts.append(part)

                elif "parts" in msg:
                    for p in msg["parts"]:
                        if "function_call" in p:
                            fc = p["function_call"]
                            parts.append(types.Part(
                                function_call=types.FunctionCall(
                                    name=fc["name"],
                                    args=fc["args"]
                                )
                            ))
                        elif "text" in p:
                            parts.append(types.Part(text=p["text"]))

                contents.append(types.Content(role="model", parts=parts))

            elif role == "function":
                parts = [types.Part(
                    function_response=types.FunctionResponse(
                        name=msg["name"],
                        response=msg["content"]
                    )
                )]
                contents.append(types.Content(role="tool", parts=parts))

            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg.get("content", ""))]
                ))

        if question:
            contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

        def call_api():
            config_kwargs = {
                "system_instruction": system_prompt,
                "tools": gemini_tools,
                "temperature": 0.0,
                "top_p": 0.05,  # Narrow probability space for consistency
                "top_k": 1,     # Select highest-probability token only
            }

            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except (AttributeError, TypeError):
                pass

            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs)
            )

        self.last_usage = None
        response = await self._run_async(call_api)
        self._record_usage(response)

        tokens = 0
        if response.usage_metadata:
            tokens = (response.usage_metadata.prompt_token_count or 0) + (response.usage_metadata.candidates_token_count or 0)

        return {
            "response": response,
            "tokens_used": tokens
        }

    @ai_retry
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None, hierarchy_info: Optional[list] = None, schema_metadata: Optional[list] = None) -> Union[str, Dict]:
        prompt = build_explain_prompt(
            question=question, sql=sql, data=data,
            dimension_families=dimension_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )

        def call_api():
            return self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"system_instruction": system_prompt, "temperature": 0.3}
            )

        self.last_usage = None
        response = await self._run_async(call_api)
        self._record_usage(response)
        text = response.text

        # Use shared post-processor
        time_columns = [m['column_name'] for m in schema_metadata
                        if m.get('dimension_group') == 'time_period'] if schema_metadata else None
        parsed_result = parse_explanation_response(text)
        parsed_result = enforce_time_series_rule(parsed_result, time_columns=time_columns)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)
        parsed_result = enrich_chart_config(
            parsed_result=parsed_result,
            data=data,
            schema_metadata=schema_metadata,
            chart_title=parsed_result.get("chart_title", ""),
        )
        return parsed_result

    async def generate_structured(self, prompt: str, schema: Dict[str, Any], system_prompt: Optional[str] = None, schema_name: str = "result") -> Optional[Dict]:
        """Structured output via response_mime_type=application/json.

        Decision: schema goes into the prompt rather than response_schema —
        converting arbitrary JSON Schema to google-genai's Schema type is
        version-fragile; JSON mime + prompt schema is reliable across versions.
        """
        import json as _json

        def call_api():
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
                response_mime_type="application/json",
            )
            schema_prompt = f"{prompt}\n\nReturn ONLY a JSON object matching this schema:\n{_json.dumps(schema, ensure_ascii=False)}"
            return self.client.models.generate_content(model=self.model, contents=schema_prompt, config=config)

        self.last_usage = None
        try:
            response = await self._run_async(call_api)
            self._record_usage(response)
            text = response.text if response and hasattr(response, "text") else ""
            return self._validate_required(_json.loads(text), schema)
        except Exception as e:
            logger.warning(f"GeminiProvider.generate_structured failed: {e}")
            return None

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        """Generate content using Gemini API with optional native multi-turn history."""
        logger.info(f"GeminiProvider.generate_content called")

        def call_api():
            try:
                from google.genai import types

                # Build native multi-turn contents
                contents = []
                if history:
                    for msg in history:
                        role = "model" if msg.get("role") == "assistant" else "user"
                        content = msg.get("content", "")
                        if content:
                            contents.append(types.Content(
                                role=role,
                                parts=[types.Part(text=content)]
                            ))
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                ))

                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3  # Stable intent extraction
                ) if system_prompt else types.GenerateContentConfig(temperature=0.3)

                result = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config
                )

                return result

            except Exception as e:
                logger.error(f"GeminiProvider: API call failed: {type(e).__name__}: {e}")
                raise

        self.last_usage = None
        try:
            response = await self._run_async(call_api)
            self._record_usage(response)
            text = response.text if response and hasattr(response, 'text') else ""
            return text
        except Exception as e:
            logger.error(f"GeminiProvider: _run_async failed: {type(e).__name__}: {e}")
            raise

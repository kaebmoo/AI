"""
NT AI Assistant - Gemini Provider
===================================
Google Gemini API implementation.
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union

from app.providers.base import AIProvider
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import parse_explanation_response, enforce_time_series_rule

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

    def get_model(self, tier: str = "default") -> str:
        if tier == "cheap":
            return "gemini-2.0-flash-exp"
        return self.model

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def _run_async(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

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
                "temperature": 0.0
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

        response = await self._run_async(call_api)

        tokens = 0
        if response.usage_metadata:
            tokens = response.usage_metadata.prompt_token_count + response.usage_metadata.candidates_token_count

        return {
            "response": response,
            "tokens_used": tokens
        }

    @ai_retry
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> Union[str, Dict]:
        prompt = f"""Question: {question}
SQL: {sql}
Results: {json.dumps(data[:30], ensure_ascii=False)}

Explain in Thai.
CRITICAL: You must analyze the data and recommend the best visualization type.
Return the result as a JSON object with these keys:
1. "explanation": The Thai explanation text.
2. "visualization": One of ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'donut_chart', 'table', 'single_value', 'grouped_bar']
3. "chart_config": Object with column mappings for the chart:
   - "category_column": The column name for X-axis labels (the PRIMARY grouping)
   - "measure_column": The column name for Y-axis values (e.g., total, sum, amount)
   - "series_column": (optional) The column for SECONDARY grouping/comparison

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

Example for comparison (grouped bar):
{{
  "explanation": "เปรียบเทียบยอดขาย...",
  "visualization": "grouped_bar",
  "chart_config": {{
    "category_column": "month",
    "measure_column": "revenue",
    "series_column": "department"
  }}
}}
"""

        def call_api():
            return self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"system_instruction": system_prompt}
            )

        response = await self._run_async(call_api)
        text = response.text

        # Use shared post-processor
        parsed_result = parse_explanation_response(text)
        parsed_result = enforce_time_series_rule(parsed_result)
        return parsed_result

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Gemini API"""
        logger.info(f"GeminiProvider.generate_content called")

        def call_api():
            try:
                from google.genai import types

                config = types.GenerateContentConfig(
                    system_instruction=system_prompt
                ) if system_prompt else None

                result = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )

                return result

            except Exception as e:
                logger.error(f"GeminiProvider: API call failed: {type(e).__name__}: {e}")
                raise

        try:
            response = await self._run_async(call_api)
            text = response.text if response and hasattr(response, 'text') else ""
            return text
        except Exception as e:
            logger.error(f"GeminiProvider: _run_async failed: {type(e).__name__}: {e}")
            raise

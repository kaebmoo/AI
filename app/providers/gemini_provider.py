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
from app.providers.chart_postprocessor import (
    parse_explanation_response,
    enforce_time_series_rule,
    enforce_dimension_family_rule,
    build_dimension_family_prompt,
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
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None) -> Union[str, Dict]:
        family_prompt = build_dimension_family_prompt(dimension_families) if dimension_families else ""
        prompt = f"""Question: {question}
SQL: {sql}
Results: {json.dumps(data[:30], ensure_ascii=False)}

Explain in Thai.
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
2. "visualization": One of ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'donut_chart', 'table', 'single_value', 'grouped_bar']
3. "chart_config": Object with column mappings for the chart:
   - "category_column": The column name for X-axis labels (the PRIMARY grouping)
   - "measure_column": The column name for Y-axis values (e.g., total, sum, amount)
   - "series_column": (optional) The column for SECONDARY grouping/comparison
4. "display_hint": How to display the TABLE (separate from chart). Choose ONE:
   - 'hierarchical': Use when data has MULTIPLE categorical (non-time) columns where one is the parent of another.
     Rule: If the columns represent a HIERARCHY (e.g., BUSINESS_GROUP > SERVICE_GROUP, or division > department > section),
     always use 'hierarchical' — even if there are only 2 levels.
     Do NOT use 'crosstab' for parent-child hierarchy data without time dimension.
   - 'crosstab': Use ONLY when comparing values ACROSS a time dimension (month, quarter, year) OR when
     the question explicitly asks to compare one distinct category against another.
   - 'flat': Use for single-dimension data or when already aggregated to one level.
5. "hierarchy_columns": (REQUIRED if display_hint='hierarchical') Array of actual column names ordered HIGHEST (parent) to LOWEST (child).
   Example: BUSINESS_GROUP is parent, SERVICE_GROUP is child → ["BUSINESS_GROUP", "SERVICE_GROUP"]
   Example: division > department > section → ["division", "department", "section"]

IMPORTANT for time-based comparisons:
- **CRITICAL**: If a Time column exists (Month, Year, Date), YOU MUST USE IT AS 'category_column' (X-axis).
- **Comparison**: Use the other dimension (Department, Account, Section) as 'series_column' (Legend).
     - **Legend Rule**: Prefer DESCRIPTIVE columns (e.g., 'department_name', 'account_name') over ID/Code columns (e.g., 'gl_code', 'id') for better readability.
     - If < 5 series: Suggest 'grouped_bar' or 'line_chart'
     - If > 5 series: Suggest 'stacked_bar' (to avoid clutter)
- **Exception**: Only use Time as Series if explicitly asked to "Compare Years" (Year-over-Year).

Example for hierarchical data:
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

Example for comparison (grouped bar):
{{
  "explanation": "### เปรียบเทียบยอดขาย\n\nยอดขายรวม...",
  "visualization": "grouped_bar",
  "chart_config": {{
    "category_column": "month",
    "measure_column": "revenue",
    "series_column": "department"
  }},
  "display_hint": "crosstab"
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
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)
        return parsed_result

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
                    system_instruction=system_prompt
                ) if system_prompt else None

                result = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
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

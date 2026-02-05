
"""
NT AI Assistant - AI Service
==================================
Service for interacting with AI API providers via MCP (Model Context Protocol).

Supports:
- Claude API (Anthropic)
- Google AI / Gemini API
- Matcha AI (OpenAI Compatible)

Usage:
    # Service should be instantiated with an active MCP Client
    ai_service = AIService(provider="claude", api_key="...", mcp_client=global_mcp_client)
    result = await ai_service.query("Request...")
"""

import json
import sqlite3
import re
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.mcp_client import MCPClientService

logger = logging.getLogger(__name__)

# Retry Configuration
def create_retry_decorator():
    """Create retry decorator with standard configuration"""
    exceptions_to_retry = [
        httpx.TimeoutException, 
        httpx.ConnectError,
        httpx.ReadTimeout
    ]
    
    try:
        import anthropic
        exceptions_to_retry.extend([
            anthropic.RateLimitError, 
            anthropic.APIError,
            anthropic.APIConnectionError
        ])
    except ImportError:
        pass
        
    try:
        from google.api_core import exceptions as google_exceptions
        exceptions_to_retry.extend([
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError
        ])
    except ImportError:
        pass

    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(tuple(exceptions_to_retry)),
        reraise=True
    )

ai_retry = create_retry_decorator()

@dataclass
class ConfidenceResult:
    """Confidence score for query result"""
    score: int
    level: str  # high, medium, low, very_low
    level_th: str
    color: str  # green, yellow, orange, red
    factors: List[Dict]
    recommendation: str

@dataclass
class QueryResult:
    """Result from AI query"""
    question: str
    sql_query: str
    data: List[Dict]
    explanation: Union[str, Dict]  # Can be str or dict with visualization/chart_config
    tokens_used: int
    provider: str
    raw_response: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    retry_history: Optional[List[Dict]] = None
    confidence: Optional[ConfidenceResult] = None

@dataclass
class RetryStatus:
    """Status update during retry process"""
    attempt: int
    max_attempts: int
    status: str
    message: str
    sql_query: Optional[str] = None
    error: Optional[str] = None

class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    async def generate_sql(self, question: str, system_prompt: str, tools: List[Dict], history: List[Dict] = []) -> Dict[str, Any]:
        """Generate SQL from question using Tools"""
        pass
    
    @abstractmethod
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        """Explain query result"""
        pass

    @abstractmethod
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate generic content"""
        pass

class ClaudeProvider(AIProvider):
    """Claude API provider"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
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

        # Convert MCP tools format to Anthropic tools format if needed
        # MCP tools are already relatively compatible but might need adjustment
        # Anthropic expects: name, description, input_schema
        # Sanitizing to permit only these fields to prevent 400 errors (e.g. from extra 'custom' fields)
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
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        # Simplified explanation logic without complex token estimation for now
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
        # Parse JSON if possible, otherwise return text
        parsed_result = {"explanation": content}
        try:
            # 1. Try pure JSON
            parsed_result = json.loads(content)
        except:
            try:
                # 2. Try to extract JSON from Markdown code blocks
                match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
                if match:
                    parsed_result = json.loads(match.group(1))
                else:
                    # 3. Try to find first { and last }
                    match = re.search(r'(\{.*\})', content, re.DOTALL)
                    if match:
                        parsed_result = json.loads(match.group(1))
            except:
                pass
        
        # Post-process to enforce Time-Series Rule (Code Level)
        try:
             # Ensure we have a dict
             if isinstance(parsed_result, str):
                  parsed_result = {"explanation": parsed_result}
                  
             if "chart_config" in parsed_result:
                 config = parsed_result["chart_config"]
                 cat = config.get("category_column", "").lower()
                 series = config.get("series_column", "").lower()
                 
                 time_keys = ['month', 'year', 'date', 'day', 'time', 'quarter', 'week', 'hour', 'minute', 'second', 'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'งวด', 'เวลา']
                 
                 is_series_time = any(t in series for t in time_keys)
                 is_cat_time = any(t in cat for t in time_keys)
                 
                 # If Series is Time BUT Category is NOT Time -> SWAP
                 print(f"\n[DEBUG] Parsing Config: Cat='{cat}', Series='{series}'")
                 print(f"[DEBUG] TimeKeys: {time_keys}")
                 print(f"[DEBUG] IsSeriesTime={is_series_time}, IsCatTime={is_cat_time}")
                 
                 if is_series_time and not is_cat_time:
                     print(f"[DEBUG] >>> SWAPPING DETECTED! <<<<")
                     logger.info(f"Generated Chart Config violates Time-Series Rule. Swapping {cat} <-> {series}")
                     config["category_column"] = config["series_column"]
                     config["series_column"] = cat
                     # Force Stacked Bar if swappping happened and was grouped_bar (optional, but safer)
                     if parsed_result.get("visualization") == "grouped_bar":
                          parsed_result["visualization"] = "stacked_bar"
                 else:
                     print(f"[DEBUG] No Swap Needed.")

             return parsed_result
        except Exception as e:
            print(f"[DEBUG] CRITICAL ERROR IN PARSING: {e}")
            logger.error(f"Error processing AI result: {e}")
            return {"explanation": content}

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

class GeminiProvider(AIProvider):
    """Google Gemini API provider"""
    
    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            # We use the Async client if available, or wrap calls
            # google.genai 0.5+ has async support?
            # For safety, let's assuming we might need to run in thread if SDK is sync
            # checking SDK... google-genai Client is sync? 
            # Actually, let's use the REST API via httpx for true async if SDK is problematic,
            # BUT for now let's assume standard google.genai usage.
            # If standard Client is sync, we wrap in asyncio.to_thread
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
            # MCP input_schema is JSON Schema
            # Gemini expects specific structure
            gemini_tools.append(types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t['name'],
                    description=t['description'],
                    parameters=t['input_schema'] 
                )
            ]))
            
        contents = []
        contents = []
        for msg in history:
            role = msg.get("role")
            
            if role == "model":
                parts = []
                if "parts_raw" in msg:
                    # Restore from raw dicts (preserving thought_signature)
                    for p_dict in msg["parts_raw"]:
                        # Try from_dict first (preserves all fields including thought_signature)
                        try:
                            if hasattr(types.Part, 'from_dict'):
                                parts.append(types.Part.from_dict(p_dict))
                                continue
                        except Exception:
                            pass

                        # Fallback: Manual construction
                        try:
                            # Try direct instantiation with dict unpacking
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
                        # Try to set thought_signature if the SDK supports it
                        if "thought_signature" in p_dict:
                            try:
                                part.thought_signature = p_dict["thought_signature"]
                            except AttributeError:
                                pass
                        parts.append(part)

                elif "parts" in msg:
                    # Legacy/Fallback manual construction
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
                # Reconstruct Function Response
                # Must use role='tool' to be recognized as a Function Response Turn
                # role='user' is treated as User Turn, leaving the previous Call hanging.
                
                parts = [types.Part(
                    function_response=types.FunctionResponse(
                        name=msg["name"],
                        response=msg["content"] # Dict
                    )
                )]
                contents.append(types.Content(role="tool", parts=parts))
                
            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg.get("content", ""))]
                ))
            elif role == "model":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=msg.get("content", ""))]
                ))

        
        # Determine if we should append the question
        # If history already has the user question as the first item, we might not need to append it again if question is None
        # But our loop logic passes 'working_question' which becomes None.
        if question:
             contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

        def call_api():
            # Build config with thinking disabled to avoid thought_signature issues
            config_kwargs = {
                "system_instruction": system_prompt,
                "tools": gemini_tools,
                "temperature": 0.0
            }

            # Try to disable thinking for models that support it (Gemini 2.5+)
            # This prevents thought_signature requirements in function calls
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except (AttributeError, TypeError):
                # SDK version doesn't support ThinkingConfig, skip
                pass

            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs)
            )

        response = await self._run_async(call_api)
        
        # Calculate tokens if available
        tokens = 0
        if response.usage_metadata:
            tokens = response.usage_metadata.prompt_token_count + response.usage_metadata.candidates_token_count

        return {
            "response": response,
            "tokens_used": tokens
        }

    @ai_retry
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
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
        # Parse JSON if possible, otherwise return text
        parsed_result = {"explanation": text}
        try:
            # 1. Try pure JSON
            parsed_result = json.loads(text)
        except:
            try:
                # 2. Try to extract JSON from Markdown code blocks
                match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
                if match:
                    parsed_result = json.loads(match.group(1))
                else:
                    # 3. Try to find first { and last }
                    match = re.search(r'(\{.*\})', text, re.DOTALL)
                    if match:
                        parsed_result = json.loads(match.group(1))
            except:
                pass

        # Post-process to enforce Time-Series Rule (Code Level)
        try:
             # Ensure we have a dict
             if isinstance(parsed_result, str):
                  parsed_result = {"explanation": parsed_result}
                  
             if "chart_config" in parsed_result:
                 config = parsed_result["chart_config"]
                 cat = config.get("category_column", "").lower()
                 series = config.get("series_column", "").lower()
                 
                 time_keys = ['month', 'year', 'date', 'day', 'time', 'quarter', 'week', 'เดือน', 'ปี', 'วันที่']
                 
                 is_series_time = any(t in series for t in time_keys)
                 is_cat_time = any(t in cat for t in time_keys)
                 
                 # If Series is Time BUT Category is NOT Time -> SWAP
                 print(f"DEBUG CHECK: Cat={cat}, Series={series}, IsSeriesTime={is_series_time}, IsCatTime={is_cat_time}")
                 if is_series_time and not is_cat_time:
                     print(f"DEBUG: SWAPPING {cat} <-> {series}")
                     logger.info(f"Generated Chart Config violates Time-Series Rule. Swapping {cat} <-> {series}")
                     config["category_column"] = config["series_column"]
                     config["series_column"] = cat
                     # Force Stacked Bar if swappping happened and was grouped_bar (optional, but safer)
                     if parsed_result.get("visualization") == "grouped_bar":
                          parsed_result["visualization"] = "stacked_bar"

             return parsed_result
        except Exception as e:
            print(f"DEBUG ERROR: {e}")
            logger.error(f"Error processing AI result: {e}")
            return {"explanation": text}

    @ai_retry
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Gemini API"""
        logger.info(f"GeminiProvider.generate_content called")
        logger.info(f"  - model: {self.model}")
        logger.info(f"  - prompt length: {len(prompt) if prompt else 0}")
        logger.info(f"  - system_prompt length: {len(system_prompt) if system_prompt else 0}")

        def call_api():
            try:
                from google.genai import types
                logger.info("GeminiProvider: Creating config...")

                # Build config properly
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt
                ) if system_prompt else None

                logger.info(f"GeminiProvider: Calling API with model={self.model}...")
                result = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )

                response_text = result.text if result and hasattr(result, 'text') else ""
                logger.info(f"GeminiProvider: API returned, text length={len(response_text)}")
                return result

            except Exception as e:
                logger.error(f"GeminiProvider: API call failed: {type(e).__name__}: {e}")
                raise

        try:
            response = await self._run_async(call_api)
            text = response.text if response and hasattr(response, 'text') else ""
            logger.info(f"GeminiProvider: Returning text length={len(text)}")
            return text
        except Exception as e:
            logger.error(f"GeminiProvider: _run_async failed: {type(e).__name__}: {e}")
            raise

class MatchaProvider(AIProvider):
    """Matcha AI (OpenAI Compatible)"""
    
    def __init__(self, api_key: str, api_url: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        
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
            # PRESERVE CRITICAL FIELDS for OpenAI/Matcha
            # Simpler copy to avoid missing fields
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
        
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            
        return {
            "response": result, # Raw OpenAI response dict
            "tokens_used": result.get('usage', {}).get('total_tokens', 0)
        }

    # ... Implement explain and generate_content similarly using AsyncClient ...
    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> Dict[str, Any]:
        """Explain result using Matcha/OpenAI and return Config"""
        
        # 1. Prepare Data Preview
        data_preview = json.dumps(data[:5], ensure_ascii=False, default=str)
        
        # 2. Construct Prompt
        prompt = f"""
Query: {question}
SQL: {sql}

Data Preview:
{data_preview}

Based on the data, provide:
1. A brief explanation of the trends/values.
2. The BEST chart type to visualize this (bar_chart, line_chart, pie_chart, grouped_bar, stacked_bar, table, single_value).
3. The configuration:
   - category_column: X-axis (Grouping)
   - measure_column: Y-axis (Value)
   - series_column: Comparison/Legend (Optional)
"""
        # 3. Call API
        response_text = await self.generate_content(prompt, system_prompt)
        
        # 4. Parse JSON
        parsed_result = {"explanation": response_text}
        try:
            # Try pure JSON
            parsed_result = json.loads(response_text)
        except:
            try:
                # Try Markdown JSON
                match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    parsed_result = json.loads(match.group(1))
                else:
                    # Try find {}
                    match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                    if match:
                        parsed_result = json.loads(match.group(1))
            except:
                pass

        # 5. Post-process to enforce Time-Series Rule (Code Level)
        try:
             # Ensure we have a dict
             if isinstance(parsed_result, str):
                  parsed_result = {"explanation": parsed_result}
                  
             if "chart_config" in parsed_result:
                 config = parsed_result["chart_config"]
                 cat = config.get("category_column", "").lower()
                 series = config.get("series_column", "").lower()
                 
                 time_keys = ['month', 'year', 'date', 'day', 'time', 'quarter', 'week', 'hour', 'minute', 'second', 'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'งวด', 'เวลา']
                 
                 is_series_time = any(t in series for t in time_keys)
                 is_cat_time = any(t in cat for t in time_keys)
                 
                 # If Series is Time BUT Category is NOT Time -> SWAP
                 print(f"DEBUG CHECK (Matcha): Cat={cat}, Series={series}, IsSeriesTime={is_series_time}, IsCatTime={is_cat_time}")
                 if is_series_time and not is_cat_time:
                     print(f"DEBUG (Matcha): SWAPPING {cat} <-> {series}")
                     logger.info(f"Matcha: Generated Chart Config violates Time-Series Rule. Swapping {cat} <-> {series}")
                     config["category_column"] = config["series_column"]
                     config["series_column"] = cat
                     # Force Stacked Bar if swappping happened and was grouped_bar
                     if parsed_result.get("visualization") == "grouped_bar":
                          parsed_result["visualization"] = "stacked_bar"

             return parsed_result
        except Exception as e:
            logger.error(f"Matcha: Error processing result: {e}")
            return {"explanation": response_text}
    
    async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Matcha/OpenAI-compatible API"""
        logger.info(f"MatchaProvider.generate_content called")
        logger.info(f"  - model: {self.model}")
        logger.info(f"  - prompt length: {len(prompt) if prompt else 0}")

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
            async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
                logger.info(f"MatchaProvider: Calling API at {self.api_url}...")
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()

            content = result['choices'][0]['message']['content']
            logger.info(f"MatchaProvider: API returned, text length={len(content)}")
            return content

        except Exception as e:
            logger.error(f"MatchaProvider: API call failed: {type(e).__name__}: {e}")
            raise


class AIService:
    """Async AI Service integrating MCP"""
    
    def __init__(
        self,
        provider: str,
        api_key: str,
        mcp_client: MCPClientService,
        model: Optional[str] = None,
        **kwargs
    ):
        self.provider_name = provider
        self.mcp_client = mcp_client
        
        if provider == "claude":
            self.provider = ClaudeProvider(api_key, model) if model else ClaudeProvider(api_key)
        elif provider == "gemini":
            self.provider = GeminiProvider(api_key, model) if model else GeminiProvider(api_key)
        elif provider == "matcha":
             self.provider = MatchaProvider(api_key, kwargs.get("api_url"), model) if model else MatchaProvider(api_key, kwargs.get("api_url"))
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        return await self.provider.explain_result(question, sql, data, system_prompt)
            
    async def query_with_retry(
        self,
        question: str,
        max_retries: int = 3,
        history: List[Dict] = [],
        on_status: Optional[Callable[[RetryStatus], None]] = None,
        explain: bool = True,
        context_name: str = "revenue"
    ) -> QueryResult:
        
        # 1. Get Tools
        tools = await self.mcp_client.get_tools()
        
        # 2. Main Loop (Model <-> Tools)
        # We handle up to max_turns for tool usage (e.g. get_schema -> get_values -> execute_sql)
        max_turns = 20
        current_history = list(history)
        
        # Initial System Prompt
        system_prompt = "You are a helpful data assistant. Use the available tools to answer the user's question. Always validate your understanding of the schema first."
        
        sql_query = None
        data = []
        explanation = ""
        total_tokens = 0
        
        working_question = question

        for turn in range(max_turns):
            logger.info(f"AIService Turn {turn}/{max_turns} for provider {self.provider_name}")
            
            # Call AI
            result = await self.provider.generate_sql(working_question, system_prompt, tools, current_history)
            response = result["response"]
            total_tokens += result["tokens_used"]
            
            # Check for tool calls
            tool_calls = []
            
            # Parse response based on provider
            if self.provider_name == "claude":
                # Anthropic object
                for content in response.content:
                    if content.type == "text" and content.text:
                         pass # Just thought process
                    elif content.type == "tool_use":
                        tool_calls.append({
                            "id": content.id,
                            "name": content.name,
                            "args": content.input
                        })
                
                # Check if done (no tool calls, just text?) 
                # Actually Claude stops at tool_use. We must run tool and recurse.
                if not tool_calls:
                     # Final answer
                     text = response.content[0].text if response.content else ""
                     explanation = text
                     break
                     
            elif self.provider_name == "gemini":
                # Google object
                candidate = response.candidates[0]
                for part in candidate.content.parts:
                    if part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "args": part.function_call.args
                        })
                if not tool_calls:
                     # Final answer
                     explanation = candidate.content.parts[0].text if candidate.content.parts else ""
                     break
            
            elif self.provider_name == "matcha":
                # OpenAI Dict
                msg = response['choices'][0]['message']
                if msg.get('tool_calls'):
                    # Ensure User question is in history before tools if it's the first turn
                    if turn == 0 and working_question:
                        current_history.append({"role": "user", "content": working_question})
                        working_question = None

                    # Append Assistant Message ONCE containing all tool calls
                    current_history.append(msg)
                    
                    for tc in msg['tool_calls']:
                        tool_calls.append({
                            "id": tc['id'],
                            "name": tc['function']['name'],
                            "args": json.loads(tc['function']['arguments'])
                        })
                else:
                    explanation = msg.get('content', "")
                    break

            # Execute Tools
            for call in tool_calls:
                 # Notify status
                 if on_status:
                     on_status(RetryStatus(turn, max_turns, "executing", f"Calling tool: {call['name']}"))
                 
                 # Capture SQL if this is execution
                 if call['name'] == 'execute_query':
                     sql_query = call['args'].get('sql') or call['args'].get('query')
                     
                 try:
                     logger.info(f"Calling tool {call['name']} with args: {call['args']}")
                     tool_result = await self.mcp_client.call_tool(call['name'], call['args'])
                     
                     # If execute query, we got data!
                     if call['name'] == 'execute_query':
                         try:
                             if isinstance(tool_result, str): # Parse JSON if it looks like one
                                 import ast
                                 # Or json.loads
                                 data = json.loads(tool_result)
                         except:
                             pass
                 except Exception as e:
                     tool_result = f"Error: {str(e)}"
                     logger.error(f"Tool execution error: {tool_result}")

                 # Add to history for next turn
                 if self.provider_name == "claude":
                     current_history.append({"role": "assistant", "content": [
                         {"type": "tool_use", "id": call['id'], "name": call['name'], "input": call['args']}
                     ]})
                     current_history.append({"role": "user", "content": [
                         {"type": "tool_result", "tool_use_id": call['id'], "content": str(tool_result)}
                     ]})
                 
                 elif self.provider_name == "gemini":
                     # Gemini uses 'user' role for function responses
                     # We need to store enough info for generate_sql to reconstruct types.Part
                     
                     # 1. Store the Model's Function Call (if not already stored explicitly)
                     # In Gemini, the 'response' object itself contains the candidate execution.
                     # We need to make sure we keep track of what the model *just* said.
                     # But current_history logic is additive.
                     
                     # Check if we just added the model's turn?
                     # Distinct from Matcha/Claude, Gemini SDK often manages history via ChatSession.
                     # But here we are doing stateless generate_content calls.
                     
                     # Ensure User question is the VERY FIRST item in history if this is the first turn
                     if turn == 0 and working_question:
                         current_history.append({"role": "user", "content": working_question})
                         working_question = None

                     # We need to append the MODEL's function call message first if this is the first tool in this turn
                     # But tool_calls list comes from ONE model response.
                     # So we should append the model response ONCE.
                     
                     # Check if the last message in history is this model response
                     last_msg = current_history[-1] if current_history else None
                     model_msg_marker = f"__gemini_model_turn_{turn}__"
                     
                     if not last_msg or last_msg.get("internal_id") != model_msg_marker:
                         # Store the ORIGINAL parts from the candidate to preserve thought_signature
                         # We can't easily serialize types.Part but we can try to keep it in memory
                         # or serialize to dict if the SDK supports it.
                         # Better: Store the whole part if possible, or convert to dict using .to_dict()
                         
                         model_parts_data = []
                         # We iterate through the original response parts to find the function calls
                         # The 'response' object is available here
                         # CAUTION: 'response' variable holds the GenerateContentResponse
                         
                         matched_parts = []
                         if response.candidates and response.candidates[0].content:
                             for p in response.candidates[0].content.parts:
                                 # We want to keep all parts (thought + function_call)
                                 # We need to serialize them for history
                                 # Check if .to_dict() exists
                                 # Try to serialize using to_dict() first (preserves thought_signature)
                                 try:
                                     if hasattr(p, "to_dict"):
                                         matched_parts.append(p.to_dict())
                                         continue
                                 except Exception:
                                     pass

                                 # Fallback manual construction - include thought_signature if present
                                 part_dict = {}

                                 if p.function_call:
                                     part_dict["function_call"] = {
                                         "name": p.function_call.name,
                                         "args": dict(p.function_call.args) if p.function_call.args else {}
                                     }

                                 if hasattr(p, 'text') and p.text:
                                     part_dict["text"] = p.text

                                 # CRITICAL: Preserve thought_signature if present
                                 if hasattr(p, 'thought_signature') and p.thought_signature:
                                     part_dict["thought_signature"] = p.thought_signature

                                 # Also check for thought field
                                 if hasattr(p, 'thought') and p.thought:
                                     part_dict["thought"] = p.thought

                                 if part_dict:
                                     matched_parts.append(part_dict)
                         
                         if matched_parts:
                            current_history.append({
                                "role": "model",
                                "parts_raw": matched_parts, # Store raw dicts
                                "internal_id": model_msg_marker
                            })
                     
                     # 2. Append the Tool Response
                     # Gemini expects response in 'user' role usually, or specific structure
                     # Ensure content is a Dict
                     tool_content = tool_result
                     if isinstance(tool_result, str):
                         try:
                             tool_content = json.loads(tool_result)
                         except:
                             pass
                     
                     # Check if it is a list or primitive, wrap it
                     if not isinstance(tool_content, dict):
                         tool_content = {"result": tool_content}

                     current_history.append({
                         "role": "function", # Internal marker we process in generate_sql
                         "name": call['name'],
                         "content": tool_content
                     })

                 elif self.provider_name == "matcha":
                     # For Matcha, we ONLY append the tool output here
                     # The Assistant message was already appended before the loop
                     current_history.append({
                         "role": "tool",
                         "tool_call_id": call['id'],
                         "content": str(tool_result)
                     })
        
        # Fallback if loop finished without explanation
        if not explanation and total_tokens > 0:
            explanation = "I apologize, but I was unable to complete the analysis within the allowed number of steps. The request required exploring too much schema information."

        # Append Limit Warning if triggered
        if getattr(self, '_pending_limit_warning', None):
            explanation += self._pending_limit_warning

        return QueryResult(
            question=question,
            sql_query=sql_query,
            data=data if isinstance(data, list) else [],
            explanation=explanation,
            tokens_used=total_tokens,
            provider=self.provider_name
        )

    async def query_hybrid(
        self,
        question: str,
        system_prompt: str,
        max_retries: int = 2,
        history: List[Dict] = None,
        on_status: Optional[Callable[[RetryStatus], None]] = None,
        context_name: str = "revenue"
    ) -> QueryResult:
        """
        Hybrid Mode: Static prompt + MCP validation/execution

        Flow:
        1. AI generates SQL using static schema prompt (1 API call)
        2. MCP validate_sql checks the SQL
        3. MCP execute_query runs the SQL
        4. If error, AI fixes and retries (max 2 retries)

        Cost: 2-4 API calls vs 13+ calls in full MCP mode
        """
        sql_query = None
        data = []
        explanation = ""
        total_tokens = 0
        retry_history = []

        # Verify MCP client is connected
        if not self.mcp_client.servers:
            logger.error("Hybrid Mode: MCP client has no connected servers!")
            return QueryResult(
                question=question,
                sql_query="",
                data=[],
                explanation="ระบบ MCP ไม่ได้เชื่อมต่อ กรุณาลองใหม่อีกครั้ง",
                tokens_used=0,
                provider=self.provider_name,
                error="MCP client not connected"
            )

        logger.info(f"Hybrid Mode: MCP connected to {list(self.mcp_client.servers.keys())}")

        for attempt in range(max_retries + 1):
            if on_status:
                on_status(RetryStatus(attempt, max_retries, "generating", f"Generating SQL (attempt {attempt + 1})"))

            # Build prompt for AI
            # Get main table for context
            context_table = "v_expense_mart" if context_name == "expense" else "revenue_search"
            context_thai = "ค่าใช้จ่าย" if context_name == "expense" else "รายได้"

            # Build conversation history context
            history_context = ""
            if history and len(history) > 0:
                history_lines = []
                for i, msg in enumerate(history[-6:]):  # Last 3 pairs (6 messages)
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        history_lines.append(f"คำถามก่อนหน้า: {content}")
                    elif role == "assistant":
                        # Extract SQL from previous response if available
                        # Try markdown format first
                        sql_match = re.search(r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
                        if sql_match:
                            sql_preview = sql_match.group(1).strip()
                            # Show full SQL (truncated if too long) so AI can see filters
                            history_lines.append(f"SQL ที่ใช้:\n{sql_preview[:500]}")
                        else:
                            # Try old format (Context SQL: ...)
                            old_format = re.search(r'\(Context SQL:\s*(.*?)\)', content, re.DOTALL)
                            if old_format:
                                history_lines.append(f"SQL ที่ใช้:\n{old_format.group(1).strip()[:500]}")
                            else:
                                # Just show summary of response
                                history_lines.append(f"คำตอบ: {content[:150]}...")

                if history_lines:
                    history_context = "\n\n**บริบทจากการสนทนาก่อนหน้า:**\n" + "\n".join(history_lines)
                    history_context += "\n\n**กฎจัดการ Filter (ดูจาก SQL ก่อนหน้า):**\n"
                    history_context += "- ถ้า User ระบุค่าใหม่สำหรับ Column เดิม → **REPLACE** filter นั้น\n"
                    history_context += "- ถ้า User เพิ่มเงื่อนไข Column ใหม่ → **MERGE** (AND) เข้าไป\n"
                    history_context += "- ถ้า User พูดว่า 'ทั้งหมด/ภาพรวม' → **RESET** filter ทั้งหมด"
                    logger.info(f"Hybrid Mode: Using conversation history with {len(history_lines)} context items")

            if attempt == 0:
                user_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

สร้าง SQL query และอธิบายผลลัพธ์เป็นภาษาไทย
สำคัญ: ต้องใช้ตาราง {context_table} เท่านั้น

ตอบในรูปแบบ:
```sql
<SQL query here>
```

**คำอธิบาย:** <explanation here>"""
            else:
                # Retry with error context
                last_error = retry_history[-1] if retry_history else {}
                user_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

SQL ก่อนหน้ามีปัญหา:
```sql
{last_error.get('sql', '')}
```
Error: {last_error.get('error', '')}

กรุณาแก้ไข SQL และอธิบายผลลัพธ์เป็นภาษาไทย
สำคัญ: ต้องใช้ตาราง {context_table} เท่านั้น

ตอบในรูปแบบ:
```sql
<SQL query ที่แก้ไขแล้ว>
```

**คำอธิบาย:** <explanation here>"""

            try:
                # Step 1: AI generates SQL (single call, no tools)
                logger.info(f"Hybrid Mode: Generating SQL (attempt {attempt + 1})")
                logger.info(f"Hybrid Mode: Provider={self.provider_name}, user_prompt_len={len(user_prompt)}, system_prompt_len={len(system_prompt) if system_prompt else 0}")

                try:
                    response_text = await self.provider.generate_content(user_prompt, system_prompt)
                except Exception as gen_error:
                    logger.error(f"Hybrid Mode: generate_content raised exception: {type(gen_error).__name__}: {gen_error}")
                    retry_history.append({"sql": "", "error": f"generate_content error: {str(gen_error)}"})
                    continue

                logger.info(f"Hybrid Mode: Got response_text (len={len(response_text) if response_text else 0})")
                if response_text:
                    logger.info(f"Hybrid Mode: response_text preview: {response_text[:300]}...")
                total_tokens += 500  # Estimate, actual depends on provider

                # Step 2: Parse SQL from response
                sql_query = self._extract_sql(response_text)
                explanation = self._extract_explanation(response_text)

                if not sql_query:
                    logger.warning("Could not extract SQL from AI response")
                    retry_history.append({"sql": "", "error": "Could not extract SQL from response"})
                    continue

                logger.info(f"Extracted SQL: {sql_query[:100]}...")

                # Step 3: Validate SQL using MCP
                if on_status:
                    on_status(RetryStatus(attempt, max_retries, "validating", "Validating SQL"))

                try:
                    validation_result = await self.mcp_client.call_tool("validate_sql", {"sql": sql_query})
                    logger.info(f"Hybrid Mode: Validation result: {validation_result}")

                    if not validation_result:
                        logger.warning("Empty validation result from MCP")
                        retry_history.append({"sql": sql_query, "error": "MCP validation returned empty result"})
                        continue

                    validation = json.loads(validation_result) if isinstance(validation_result, str) else validation_result
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse validation result: {e}")
                    retry_history.append({"sql": sql_query, "error": f"Validation parse error: {str(e)}"})
                    continue
                except Exception as e:
                    logger.error(f"Validation tool call failed: {e}")
                    retry_history.append({"sql": sql_query, "error": f"Validation error: {str(e)}"})
                    continue

                if not validation.get("valid", False):
                    issues = validation.get("issues", [])
                    logger.warning(f"SQL validation failed: {issues}")
                    retry_history.append({"sql": sql_query, "error": f"Validation failed: {issues}"})
                    continue

                # Step 4: Execute SQL using MCP
                if on_status:
                    on_status(RetryStatus(attempt, max_retries, "executing", "Executing SQL"))

                logger.info(f"Hybrid Mode: Executing SQL: {sql_query}")

                try:
                    exec_result = await self.mcp_client.call_tool("execute_query", {
                        "sql": sql_query,
                        "limit": 1000,
                        "validate_first": False  # Already validated
                    })
                    logger.info(f"Hybrid Mode: Execution result length: {len(exec_result) if exec_result else 0}")
                    logger.info(f"Hybrid Mode: Execution result preview: {exec_result[:500] if exec_result else 'None'}...")

                    if not exec_result:
                        logger.warning("Empty execution result from MCP")
                        retry_history.append({"sql": sql_query, "error": "MCP execution returned empty result"})
                        continue

                    exec_data = json.loads(exec_result) if isinstance(exec_result, str) else exec_result
                    
                    # Logic to warn user if LIMIT is hit
                    if isinstance(exec_data, list) and len(exec_data) >= 1000:
                        logger.warning("Query hit the 1000 row limit.")
                        limit_warning = "\n\n⚠️ **คำเตือน:** ข้อมูลมีจำนวนมากและถูกจำกัดการแสดงผลที่ 1,000 รายการ อาจมีข้อมูลบางส่วนขาดหายไป กรุณาเพิ่มเงื่อนไขการค้นหา (เช่น ระบุเดือน หรือ ฝ่าย) เพื่อให้ได้ข้อมูลที่ครบถ้วนครับ"
                        # We will append this to the final explanation later or store it
                        # For now, let's prepend/append it to any explanation generated subsequently
                        # Or set a flag. Ideally, explanation is generated in next turn or extracted.
                        # Simplest: Append to the LAST tool result content so that the Model *sees* it and explains it?
                        # No, the user wants to see it.
                        # Let's append it to the explanation variable if it exists, or ensure it's added to the final output.
                        # Since explanation comes from the Model *reading* the data, the Model *might* not mention it unless told.
                        # Better strategy: Inject it into the system explanation logic OR directly modify the result object if possible.
                        # But QueryResult is just data.
                        # Let's modify the 'explanation' string at the end of the method.
                        
                        # Hack: Store it in a temporary variable to append at the return statement
                        self._pending_limit_warning = limit_warning

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse execution result: {e}")
                    retry_history.append({"sql": sql_query, "error": f"Execution parse error: {str(e)}"})
                    continue
                except Exception as e:
                    logger.error(f"Execution tool call failed: {e}")
                    retry_history.append({"sql": sql_query, "error": f"Execution error: {str(e)}"})
                    continue

                if not exec_data.get("success", False):
                    error_msg = exec_data.get("error", "Unknown execution error")
                    logger.warning(f"SQL execution failed: {error_msg}")
                    retry_history.append({"sql": sql_query, "error": f"Execution failed: {error_msg}"})
                    continue

                # Success!
                data = exec_data.get("data", [])
                row_count = exec_data.get("row_count", 0)
                columns = exec_data.get("columns", [])
                logger.info(f"Hybrid Mode: Success! Got {len(data)} rows (row_count={row_count}, columns={columns})")

                # Log sample data if available
                if data:
                    logger.info(f"Hybrid Mode: First row sample: {data[0]}")
                else:
                    logger.warning(f"Hybrid Mode: Query returned 0 rows - SQL may not match any data")

                # Enhance explanation based on actual data
                if not data:
                    # No data found - add note to explanation
                    explanation = f"ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\n{sql_query}\n```\n\nอาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา\n- ชื่อคอลัมน์หรือค่าที่ใช้ค้นหาอาจไม่ถูกต้อง"
                elif len(data) > 0:
                    # Call explain_result to get visualization and chart_config
                    try:
                        explanation = await self.provider.explain_result(question, sql_query, data, system_prompt)
                        logger.info(f"Hybrid Mode: Got explanation with visualization: {type(explanation)}")
                    except Exception as explain_error:
                        logger.warning(f"Could not get explanation: {explain_error}")
                        explanation = f"พบข้อมูล {len(data)} รายการ"

                # Step 5: Calculate confidence score using validation MCP
                confidence_result = None
                try:
                    if "nt-validation" in self.mcp_client.servers:
                        validation_summary = await self.mcp_client.call_tool(
                            "get_validation_summary",
                            {
                                "sql": sql_query,
                                "question": question,
                                "context_name": context_name,
                                "has_similar_example": False,  # TODO: Check golden examples
                                "example_similarity": 0.0,
                                "execution_success": True,
                                "result_row_count": len(data)
                            }
                        )
                        if validation_summary:
                            summary_data = json.loads(validation_summary) if isinstance(validation_summary, str) else validation_summary
                            conf = summary_data.get("confidence", {})
                            confidence_result = ConfidenceResult(
                                score=conf.get("score", 0),
                                level=conf.get("level", "medium"),
                                level_th=conf.get("level_th", "ปานกลาง"),
                                color=conf.get("color", "yellow"),
                                factors=conf.get("factors", []),
                                recommendation=conf.get("recommendation", "")
                            )
                            logger.info(f"Hybrid Mode: Confidence score = {confidence_result.score}% ({confidence_result.level})")
                except Exception as conf_error:
                    logger.warning(f"Could not calculate confidence: {conf_error}")

                return QueryResult(
                    question=question,
                    sql_query=sql_query,
                    data=data,
                    explanation=explanation,
                    tokens_used=total_tokens,
                    provider=self.provider_name,
                    retry_count=attempt,
                    retry_history=retry_history if retry_history else None,
                    confidence=confidence_result
                )

            except Exception as e:
                logger.error(f"Hybrid Mode error: {e}")
                retry_history.append({"sql": sql_query or "", "error": str(e)})

        # All retries failed
        return QueryResult(
            question=question,
            sql_query=sql_query or "",
            data=[],
            explanation=f"ไม่สามารถสร้าง SQL ที่ถูกต้องได้หลังจากลอง {max_retries + 1} ครั้ง",
            tokens_used=total_tokens,
            provider=self.provider_name,
            error="Max retries exceeded",
            retry_count=max_retries + 1,
            retry_history=retry_history
        )

    def _extract_sql(self, text: str) -> Optional[str]:
        """Extract SQL from AI response"""
        import re

        # Try to find SQL in code block
        sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        # Try generic code block
        code_match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()

        # Try to find SELECT statement directly
        select_match = re.search(r'(SELECT\s+.*?(?:;|$))', text, re.DOTALL | re.IGNORECASE)
        if select_match:
            sql = select_match.group(1).strip()
            # Remove trailing explanation if any
            if '\n\n' in sql:
                sql = sql.split('\n\n')[0]
            return sql.rstrip(';') + '' if not sql.endswith(';') else sql

        return None

    def _extract_explanation(self, text: str) -> str:
        """Extract explanation from AI response"""
        import re

        # Remove SQL code blocks
        text_without_sql = re.sub(r'```sql.*?```', '', text, flags=re.DOTALL | re.IGNORECASE)
        text_without_sql = re.sub(r'```.*?```', '', text_without_sql, flags=re.DOTALL)

        # Look for explanation marker
        explanation_match = re.search(r'\*\*คำอธิบาย:?\*\*\s*(.*)', text_without_sql, re.DOTALL)
        if explanation_match:
            return explanation_match.group(1).strip()

        # Return remaining text as explanation
        cleaned = text_without_sql.strip()
        if cleaned:
            return cleaned

        return "ดำเนินการสำเร็จ"

    async def suggest_mappings(self, columns: List[Dict], samples: Dict[str, List]) -> List[Dict[str, str]]:
        """
        Suggest column name mappings (aliases) using AI.

        Args:
            columns: List of column info dicts with 'name' and 'type'
            samples: Dict mapping column names to sample values

        Returns:
            List of suggestions with 'col', 'alias', and 'reason'
        """
        try:
            # Build prompt
            column_info = []
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                sample_vals = samples.get(col_name, [])[:3]  # First 3 samples
                column_info.append(f"- {col_name} ({col_type}): {sample_vals}")

            column_text = "\n".join(column_info)

            prompt = f"""ต้องการตั้งชื่อ alias (Suggested Alias) ภาษาอังกฤษที่เหมาะสมสำหรับคอลัมน์เหล่านี้ แบบ Snake Case เท่านั้น:

{column_text}

กรุณาแนะนำ alias ที่:
1. สั้น กระชับ ไม่เกิน 3-4 คำ
2. เข้าใจง่าย เหมาะกับการใช้งานทั่วไป
3. เป็นภาษาอังกฤษที่ถูกต้อง

ตอบในรูปแบบ JSON array:
```json
[
  {{"col": "column_name", "alias": "sugestion_name", "reason": "short reason"}},
  ...
]
```"""

            # Call AI with simple prompt (no tools needed)
            result = await self.provider.generate_content(prompt, system_prompt="คุณเป็น AI ที่ช่วยตั้งชื่อคอลัมน์ภาษาไทยให้เหมาะสม")

            # Extract JSON from response
            import json
            import re

            # Find JSON block
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', result, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group(1))
                return suggestions

            # Try parsing whole response as JSON
            try:
                suggestions = json.loads(result)
                if isinstance(suggestions, list):
                    return suggestions
            except:
                pass

            # Fallback: generate simple mappings
            return [
                {
                    'col': col['name'],
                    'alias': col['name'].lower().replace('_', ' '),
                    'reason': 'ชื่อเดิมโดยแปลง underscore เป็น space'
                }
                for col in columns
            ]

        except Exception as e:
            logger.error(f"Error in suggest_mappings: {e}")
            # Fallback: return original names
            return [
                {
                    'col': col['name'],
                    'alias': col['name'],
                    'reason': 'ไม่สามารถสร้างคำแนะนำได้ ใช้ชื่อเดิม'
                }
                for col in columns
            ]


# Factories
def create_claude_service(api_key: str, mcp_client: MCPClientService, model: Optional[str] = None) -> AIService:
    return AIService("claude", api_key, mcp_client, model)

def create_gemini_service(api_key: str, mcp_client: MCPClientService, model: Optional[str] = None) -> AIService:
    return AIService("gemini", api_key, mcp_client, model)

def create_matcha_service(api_key: str, api_url: str, mcp_client: MCPClientService, model: Optional[str] = None) -> AIService:
    return AIService("matcha", api_key, mcp_client, model, api_url=api_url)


"""
NT AI Assistant - AI Service
==================================
Service for interacting with AI API providers via MCP (Model Context Protocol).

Supports:
- Claude API (Anthropic)
- Google AI / Gemini API
- Matcha AI (OpenAI Compatible)

Usage:
    # New style (recommended): use provider registry
    from app.providers.registry import provider_registry
    provider = provider_registry.create_provider("claude", api_key="...")
    ai_service = AIService(provider=provider, mcp_client=global_mcp_client)

    # Legacy style (still supported): use factory functions
    ai_service = create_claude_service(api_key="...", mcp_client=global_mcp_client)
"""

import asyncio
import json
import re
import logging
from typing import Dict, List, Optional, Any, Callable, Union

from app.services.mcp_client import MCPClientService
# Optional import - VannaService may not be available
try:
    from app.services.vanna_service import VannaService
    HAS_VANNA = True
except ImportError:
    HAS_VANNA = False
    VannaService = None
from app.config import settings

# ============================================================
# Re-export from providers package for backward compatibility
# ============================================================
from app.providers.base import AIProvider, ConfidenceResult, QueryResult, RetryStatus  # noqa: F401
from app.providers.claude_provider import ClaudeProvider  # noqa: F401
from app.providers.gemini_provider import GeminiProvider  # noqa: F401
from app.providers.matcha_provider import MatchaProvider  # noqa: F401
from app.providers.retry_config import ai_retry, create_retry_decorator  # noqa: F401

logger = logging.getLogger(__name__)

# ============================================================
# Column Hierarchies — ป้องกัน OR ข้ามระดับ
# ============================================================
# Loaded from master_hierarchy table (DB-driven).
# Fallback to hardcoded defaults if DB not available.
# Admin can edit via Admin UI or import_master_data.py.

_HIERARCHY_CACHE: Dict[str, List[Dict]] = {}
_HIERARCHY_CACHE_TS: float = 0.0
_HIERARCHY_CACHE_TTL: float = 3600.0  # 1 hour


def _load_hierarchies_from_db() -> Dict[str, List[Dict]]:
    """Load hierarchy definitions from master_hierarchy table."""
    import time as _time
    global _HIERARCHY_CACHE, _HIERARCHY_CACHE_TS

    now = _time.time()
    if _HIERARCHY_CACHE and (now - _HIERARCHY_CACHE_TS) < _HIERARCHY_CACHE_TTL:
        return _HIERARCHY_CACHE

    try:
        import sqlite3
        db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT context_name, level, level_label_th, level_label_en, level_columns, detection_keywords "
            "FROM master_hierarchy WHERE is_active = 1 ORDER BY context_name, level"
        ).fetchall()
        conn.close()

        result: Dict[str, List[Dict]] = {}
        for ctx, level, label_th, label_en, columns_json, keywords_json in rows:
            result.setdefault(ctx, []).append({
                "level": level,
                "columns": json.loads(columns_json),
                "label_th": label_th,
                "label_en": label_en,
                "detection_keywords": json.loads(keywords_json),
            })

        if result:
            _HIERARCHY_CACHE = result
            _HIERARCHY_CACHE_TS = now
            logger.info(f"Loaded hierarchies from DB: {list(result.keys())}")
            return result
    except Exception as e:
        logger.warning(f"Could not load hierarchies from DB: {e}, using fallback")

    return _HARDCODED_HIERARCHIES


# Fallback if master_hierarchy table doesn't exist yet
_HARDCODED_HIERARCHIES: Dict[str, List[Dict]] = {
    "pl_costtype": [
        {"level": 0, "columns": ["business_unit"],
         "label_th": "กลุ่มธุรกิจ", "label_en": "Business Unit",
         "detection_keywords": ["กลุ่มธุรกิจ", "business unit", "ธุรกิจ"]},
        {"level": 1, "columns": ["service_group"],
         "label_th": "กลุ่มบริการ", "label_en": "Service Group",
         "detection_keywords": ["กลุ่มบริการ", "service group"]},
        {"level": 2, "columns": ["product_name"],
         "label_th": "ผลิตภัณฑ์/บริการ", "label_en": "Product",
         "detection_keywords": ["ผลิตภัณฑ์", "product", "สินค้า"]},
    ],
    "revenue": [
        {"level": 0, "columns": ["BUSINESS_GROUP", "BUSINESS"],
         "label_th": "กลุ่มธุรกิจ", "label_en": "Business Group",
         "detection_keywords": ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"]},
        {"level": 1, "columns": ["SERVICE_GROUP"],
         "label_th": "กลุ่มบริการ", "label_en": "Service Group",
         "detection_keywords": ["กลุ่มบริการ", "service group", "กลุ่ม"]},
        {"level": 2, "columns": ["PRODUCT_NAME", "PRODUCT"],
         "label_th": "ผลิตภัณฑ์/บริการ", "label_en": "Product/Service",
         "detection_keywords": ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ", "service"]},
    ],
}


def get_column_hierarchies() -> Dict[str, List[Dict]]:
    """Get hierarchy definitions — DB-first with hardcoded fallback."""
    return _load_hierarchies_from_db()


# Backward compat alias
COLUMN_HIERARCHIES = _HARDCODED_HIERARCHIES  # static reference for imports


class AIService:
    """Async AI Service integrating MCP"""

    def __init__(
        self,
        provider,  # AIProvider instance OR str (legacy)
        api_key: str = None,
        mcp_client: MCPClientService = None,
        model: Optional[str] = None,
        **kwargs
    ):
        # Support both new and legacy constructors
        if isinstance(provider, str):
            # Legacy: provider is a string name
            self.provider_name = provider
            self.mcp_client = mcp_client if mcp_client is not None else api_key  # legacy compat: api_key might be mcp_client
            self._init_legacy_provider(provider, api_key, model, **kwargs)
        elif isinstance(provider, AIProvider):
            # New style: provider is an AIProvider instance
            self.provider = provider
            self.provider_name = provider.name
            self.mcp_client = mcp_client if mcp_client is not None else api_key
        else:
            raise ValueError(f"provider must be str or AIProvider, got {type(provider)}")

        # Initialize Vanna RAG
        try:
            self.vanna = VannaService(config={
                "path": settings.VANNA_CHROMA_PATH,
                "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
            })
        except Exception:
            self.vanna = None

    def _init_legacy_provider(self, provider_name: str, api_key: str, model: Optional[str], **kwargs):
        """Legacy constructor: create provider from string name"""
        if provider_name == "claude":
            self.provider = ClaudeProvider(
                api_key,
                model or "claude-sonnet-4-20250514",
                extended_thinking=kwargs.get("extended_thinking", False),
                thinking_budget_tokens=kwargs.get("thinking_budget_tokens", 8000),
            )
        elif provider_name == "gemini":
            self.provider = GeminiProvider(api_key, model) if model else GeminiProvider(api_key)
        elif provider_name == "matcha":
            self.provider = MatchaProvider(api_key, kwargs.get("api_url"), model) if model else MatchaProvider(api_key, kwargs.get("api_url"))
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None, hierarchy_info: Optional[list] = None, schema_metadata: Optional[list] = None) -> str:
        return await self.provider.explain_result(question, sql, data, system_prompt, dimension_families=dimension_families, hierarchy_info=hierarchy_info, schema_metadata=schema_metadata)

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
        max_turns = 20
        current_history = list(history)

        system_prompt = "You are a helpful data assistant. Use the available tools to answer the user's question. Always validate your understanding of the schema first."

        sql_query = None
        data = []
        explanation = ""
        total_tokens = 0

        working_question = question

        # Inject Vanna RAG Context into System Prompt
        try:
            rag_context = self._get_vanna_context_string(question)
            if rag_context:
                system_prompt += f"\n\n{rag_context}"
                logger.info(f"Injected Vanna RAG Context ({len(rag_context)} chars)")
        except Exception as e:
            logger.error(f"Failed to get Vanna context: {e}")

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
                for content in response.content:
                    if content.type == "text" and content.text:
                        pass
                    elif content.type == "tool_use":
                        tool_calls.append({
                            "id": content.id,
                            "name": content.name,
                            "args": content.input
                        })

                if not tool_calls:
                    text = response.content[0].text if response.content else ""
                    explanation = text
                    break

            elif self.provider_name == "gemini":
                candidate = response.candidates[0]
                for part in candidate.content.parts:
                    if part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "args": part.function_call.args
                        })
                if not tool_calls:
                    explanation = candidate.content.parts[0].text if candidate.content.parts else ""
                    break

            elif self.provider_name == "matcha":
                msg = response['choices'][0]['message']
                if msg.get('tool_calls'):
                    if turn == 0 and working_question:
                        current_history.append({"role": "user", "content": working_question})
                        working_question = None

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
                if on_status:
                    on_status(RetryStatus(turn, max_turns, "executing", f"Calling tool: {call['name']}"))

                if call['name'] == 'execute_query':
                    sql_query = call['args'].get('sql') or call['args'].get('query')

                try:
                    logger.info(f"Calling tool {call['name']} with args: {call['args']}")
                    tool_result = await self.mcp_client.call_tool(call['name'], call['args'])

                    if call['name'] == 'execute_query':
                        try:
                            if isinstance(tool_result, str):
                                data = json.loads(tool_result)
                        except Exception:
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
                    if turn == 0 and working_question:
                        current_history.append({"role": "user", "content": working_question})
                        working_question = None

                    last_msg = current_history[-1] if current_history else None
                    model_msg_marker = f"__gemini_model_turn_{turn}__"

                    if not last_msg or last_msg.get("internal_id") != model_msg_marker:
                        matched_parts = []
                        if response.candidates and response.candidates[0].content:
                            for p in response.candidates[0].content.parts:
                                try:
                                    if hasattr(p, "to_dict"):
                                        matched_parts.append(p.to_dict())
                                        continue
                                except Exception:
                                    pass

                                part_dict = {}
                                if p.function_call:
                                    part_dict["function_call"] = {
                                        "name": p.function_call.name,
                                        "args": dict(p.function_call.args) if p.function_call.args else {}
                                    }
                                if hasattr(p, 'text') and p.text:
                                    part_dict["text"] = p.text
                                if hasattr(p, 'thought_signature') and p.thought_signature:
                                    part_dict["thought_signature"] = p.thought_signature
                                if hasattr(p, 'thought') and p.thought:
                                    part_dict["thought"] = p.thought

                                if part_dict:
                                    matched_parts.append(part_dict)

                        if matched_parts:
                            current_history.append({
                                "role": "model",
                                "parts_raw": matched_parts,
                                "internal_id": model_msg_marker
                            })

                    tool_content = tool_result
                    if isinstance(tool_result, str):
                        try:
                            tool_content = json.loads(tool_result)
                        except Exception:
                            pass

                    if not isinstance(tool_content, dict):
                        tool_content = {"result": tool_content}

                    current_history.append({
                        "role": "function",
                        "name": call['name'],
                        "content": tool_content
                    })

                elif self.provider_name == "matcha":
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
        context_name: str = "revenue",
        two_pass_enabled: bool = False,
        value_lookup_enabled: bool = False,
        cheap_model: Optional[str] = None,
        **kwargs
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
        import time
        start_request = time.perf_counter()

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
            try:
                from app.services.schema_service import SchemaService
                from app.config import settings as app_settings
                db_path = app_settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
                temp_schema = SchemaService(db_path=db_path)
                context_info = temp_schema.get_context_info(context_name)
                if context_info:
                    context_table = context_info.get('main_view', context_name)
                    context_thai = context_info.get('display_name', context_name)
                    logger.info(f"Hybrid Mode: Using context '{context_name}' -> table '{context_table}', display '{context_thai}'")
                else:
                    logger.error(f"Hybrid Mode: Context '{context_name}' not found in schema_contexts table")
                    return QueryResult(
                        question=question, sql_query="", data=[],
                        explanation=f"ไม่พบการตั้งค่า context '{context_name}' ในระบบ กรุณาตั้งค่าผ่าน Admin UI",
                        tokens_used=0, provider=self.provider_name, error=f"Context '{context_name}' not configured"
                    )
            except Exception as e:
                logger.error(f"Failed to get context info: {e}")
                return QueryResult(
                    question=question, sql_query="", data=[],
                    explanation=f"เกิดข้อผิดพลาดในการโหลดข้อมูล context: {e}",
                    tokens_used=0, provider=self.provider_name, error=str(e)
                )

            # Native history: passed directly to generate_content() as multi-turn messages
            # Filter management rules are already in system prompt (schema_service)
            if history:
                logger.info(f"Hybrid Mode: Using native conversation history ({len(history)} messages)")

            if attempt == 0:
                # Run RAG Context + Value Lookup in parallel (both are sync → use to_thread)

                async def _rag_task():
                    try:
                        t0 = time.perf_counter()
                        ctx = await asyncio.to_thread(self._get_vanna_context_string, question)
                        t_rag = time.perf_counter() - t0
                        if ctx:
                            logger.info(f"Hybrid Mode: Injected RAG Context ({len(ctx)} chars) took {t_rag:.4f}s")
                        return ctx
                    except Exception as e:
                        logger.warning(f"Failed to get RAG context: {e}")
                        return ""

                async def _value_lookup_task():
                    try:
                        matches = await asyncio.to_thread(
                            self._lookup_values_from_question, question, context_name, context_table
                        )
                        return matches
                    except Exception as e:
                        logger.warning(f"Value Lookup failed: {e}")
                        return []

                rag_context, value_matches = await asyncio.gather(_rag_task(), _value_lookup_task())
                rag_context = rag_context or ""

                # Format value lookup results
                value_lookup_text = ""
                detected_level = None
                if value_matches:
                    hierarchy = get_column_hierarchies().get(context_name)
                    detected_level = self._detect_hierarchy_level(question, context_name)
                    if hierarchy and detected_level:
                        logger.info(f"Hierarchy: level {detected_level['level']} ({detected_level['label_en']})")
                    value_lookup_text = self._format_value_matches(
                        value_matches, hierarchy=hierarchy, detected_level=detected_level
                    )

                # Two-Pass Mode
                if two_pass_enabled:
                    logger.info("Two-Pass Mode: Starting Pass 1 (Intent Extraction)")
                    if on_status:
                        on_status(RetryStatus(attempt, max_retries, "analyzing", "Analyzing question (Pass 1)"))

                    intent_json = await self._extract_intent(
                        question=question,
                        system_prompt=system_prompt,
                        context_name=context_name,
                        context_table=context_table,
                        context_thai=context_thai,
                        history_context="",
                        rag_context=rag_context,
                        cheap_model=cheap_model
                    )

                    if intent_json:
                        logger.info(f"Two-Pass Mode: Pass 1 success. Building Pass 2 prompt.")
                        user_prompt = self._build_pass2_prompt(
                            question=question,
                            intent=intent_json,
                            context_table=context_table,
                            context_thai=context_thai,
                            value_matches=value_matches if value_lookup_text else None,
                            hierarchy=get_column_hierarchies().get(context_name),
                            detected_level=detected_level
                        )
                    else:
                        logger.warning("Two-Pass Mode: Pass 1 failed. Falling back to one-pass CoT prompt.")
                        two_pass_enabled = False

                # One-Pass Mode (default or fallback)
                if not two_pass_enabled or attempt > 0:
                    user_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

{rag_context}

{value_lookup_text}

---
**ขั้นตอนที่ 1 — วิเคราะห์คำถาม (คิดก่อนเขียน SQL):**
ก่อนสร้าง SQL ให้ตอบสั้นๆ:
- ต้องการข้อมูลอะไร? (metric คืออะไร, dimension/group by คืออะไร, filter อะไร, ช่วงเวลาใด)
- ถ้ามี "Actual Values Found" ข้างต้น → ใช้ column/value จากผลค้นหาจริง
- มี semantic mapping ใดที่ตรงกับ keyword ในคำถาม?

**ขั้นตอนที่ 2 — SQL:**
สำคัญ: ต้องใช้ตาราง {context_table} เท่านั้น
ถ้ามี "Actual Values Found" → ใช้ column/value จากนั้น ห้ามเดาเอง

```sql
<SQL ที่สร้างจากการวิเคราะห์ข้างต้น>
```

**ขั้นตอนที่ 3 — คำอธิบาย:**
<คำอธิบายผลลัพธ์ภาษาไทย>"""
            else:
                # Retry with error context
                last_error = retry_history[-1] if retry_history else {}
                user_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

SQL ก่อนหน้ามีปัญหา:
```sql
{last_error.get('sql', '')}
```
Error: {last_error.get('error', '')}

---
**วิเคราะห์ข้อผิดพลาด:**
- Error นี้เกิดจากอะไร?
- ต้องแก้ไขส่วนใดของ SQL?

**SQL ที่แก้ไขแล้ว:**
สำคัญ: ต้องใช้ตาราง {context_table} เท่านั้น

```sql
<SQL ที่แก้ไขแล้ว>
```

**คำอธิบาย:** <คำอธิบายภาษาไทย>"""

            try:
                # Step 1: AI generates SQL
                logger.info(f"Hybrid Mode: Generating SQL (attempt {attempt + 1})")

                try:
                    t0 = time.perf_counter()
                    # Pass native history — limit to last 6 messages (3 turns) to control tokens
                    native_history = history[-6:] if (attempt == 0 and history) else None
                    response_text = await self.provider.generate_content(user_prompt, system_prompt, history=native_history)
                    t_gen = time.perf_counter() - t0
                    logger.info(f"Hybrid Mode: SQL Generation took {t_gen:.4f}s")
                except Exception as gen_error:
                    logger.error(f"Hybrid Mode: generate_content raised exception: {type(gen_error).__name__}: {gen_error}")
                    retry_history.append({"sql": "", "error": f"generate_content error: {str(gen_error)}"})
                    continue

                logger.info(f"Hybrid Mode: Got response_text (len={len(response_text) if response_text else 0})")
                total_tokens += 500  # Estimate

                # Step 2: Parse SQL from response
                sql_query = self._extract_sql(response_text)
                explanation = self._extract_explanation(response_text)

                if not sql_query:
                    logger.warning("Could not extract SQL from AI response")
                    retry_history.append({"sql": "", "error": "Could not extract SQL from response"})
                    continue

                logger.info(f"Extracted SQL: {sql_query[:100]}...")

                # Phase 4: Log unmatched LIKE keywords (fire-and-forget, non-blocking)
                try:
                    import threading
                    like_patterns = re.findall(r"LIKE\s+'%(.+?)%'", sql_query, re.IGNORECASE)
                    if like_patterns:
                        def _log_unmatched():
                            try:
                                from app.services.hierarchy_service import hierarchy_service
                                for p in like_patterns:
                                    if not hierarchy_service.search_aliases(context_name, p, limit=1):
                                        hierarchy_service.log_unmatched_keyword(p, context_name, question)
                            except Exception:
                                pass
                        threading.Thread(target=_log_unmatched, daemon=True).start()
                except Exception:
                    pass

                # Step 3: Validate SQL using MCP
                if on_status:
                    on_status(RetryStatus(attempt, max_retries, "validating", "Validating SQL"))

                try:
                    validation_result = await self.mcp_client.call_tool("validate_sql", {"sql": sql_query})

                    if not validation_result:
                        retry_history.append({"sql": sql_query, "error": "MCP validation returned empty result"})
                        continue

                    validation = json.loads(validation_result) if isinstance(validation_result, str) else validation_result
                except json.JSONDecodeError as e:
                    retry_history.append({"sql": sql_query, "error": f"Validation parse error: {str(e)}"})
                    continue
                except Exception as e:
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
                    t0 = time.perf_counter()
                    exec_result = await self.mcp_client.call_tool("execute_query", {
                        "sql": sql_query,
                        "limit": 1000,
                        "validate_first": False
                    })
                    t_exec = time.perf_counter() - t0
                    logger.info(f"Hybrid Mode: SQL Execution in DB took {t_exec:.4f}s")

                    if not exec_result:
                        retry_history.append({"sql": sql_query, "error": "MCP execution returned empty result"})
                        continue

                    exec_data = json.loads(exec_result) if isinstance(exec_result, str) else exec_result

                    # Limit Warning
                    if isinstance(exec_data, list) and len(exec_data) >= 1000:
                        logger.warning("Query hit the 1000 row limit.")
                        self._pending_limit_warning = "\n\n⚠️ **คำเตือน:** ข้อมูลมีจำนวนมากและถูกจำกัดการแสดงผลที่ 1,000 รายการ อาจมีข้อมูลบางส่วนขาดหายไป กรุณาเพิ่มเงื่อนไขการค้นหา (เช่น ระบุเดือน หรือ ฝ่าย) เพื่อให้ได้ข้อมูลที่ครบถ้วนครับ"

                except json.JSONDecodeError as e:
                    retry_history.append({"sql": sql_query, "error": f"Execution parse error: {str(e)}"})
                    continue
                except Exception as e:
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
                logger.info(f"Hybrid Mode: Success! Got {len(data)} rows")

                # Load dimension families for chart axis validation
                dim_families = None
                try:
                    dim_families = temp_schema.get_dimension_families(context_table)
                except Exception as df_err:
                    logger.warning(f"Could not load dimension families: {df_err}")

                # Load schema metadata + hierarchy info for dynamic explain prompt
                _schema_metadata = None
                _hierarchy_info = None
                try:
                    _schema_metadata = temp_schema.get_schema_metadata(context_table)
                except Exception:
                    pass
                try:
                    from sqlalchemy import text as sa_text
                    with temp_schema.engine.connect() as _conn:
                        _rows = _conn.execute(sa_text(
                            "SELECT level_label_th, level_columns FROM master_hierarchy "
                            "WHERE context_name = :ctx AND is_active = 1 ORDER BY level"
                        ), {"ctx": context_name}).fetchall()
                        if _rows:
                            _hierarchy_info = [{"level_label_th": r[0], "level_columns": r[1]} for r in _rows]
                except Exception:
                    pass

                # Enhance explanation
                # Build enriched question with conversation context for better explanation
                enriched_question = question
                if history:
                    prev_questions = [m["content"] for m in history[-4:] if m.get("role") == "user"]
                    if prev_questions:
                        enriched_question = f"(บริบท: {prev_questions[-1][:100]})\n{question}"

                if not data:
                    explanation = f"ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\n{sql_query}\n```\n\nอาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา\n- ชื่อคอลัมน์หรือค่าที่ใช้ค้นหาอาจไม่ถูกต้อง"
                elif len(data) > 0:
                    try:
                        t0 = time.perf_counter()
                        # Prepare data for explanation: send summary + representative sample
                        # instead of just first 30 rows (which may be biased by ORDER BY)
                        explain_data = self._prepare_data_for_explanation(data)
                        simple_system_prompt = "You are a data visualization assistant. Analyze the data and provide a Thai explanation and chart recommendation."

                        # Use cheap model for explanation (lightweight summarization task)
                        original_model = None
                        if cheap_model and cheap_model != self.provider.model:
                            original_model = self.provider.model
                            self.provider.model = cheap_model
                            logger.info(f"Hybrid Mode: Explanation using cheap model '{cheap_model}' (default: '{original_model}')")

                        try:
                            explanation = await self.provider.explain_result(enriched_question, sql_query, explain_data, simple_system_prompt, dimension_families=dim_families, hierarchy_info=_hierarchy_info, schema_metadata=_schema_metadata)
                        except Exception as cheap_err:
                            # Cheap model failed — retry with the original (default) model
                            if original_model:
                                logger.warning(f"Cheap model '{cheap_model}' failed for explanation: {cheap_err}. Retrying with default model '{original_model}'...")
                                self.provider.model = original_model
                                original_model = None  # Already restored — prevent double-restore in finally
                                explanation = await self.provider.explain_result(enriched_question, sql_query, explain_data, simple_system_prompt, dimension_families=dim_families, hierarchy_info=_hierarchy_info, schema_metadata=_schema_metadata)
                            else:
                                raise  # No fallback model available — propagate to outer except
                        finally:
                            if original_model:
                                self.provider.model = original_model

                        t_explain = time.perf_counter() - t0
                        logger.info(f"Hybrid Mode: Explanation Generation took {t_explain:.4f}s")
                    except Exception as explain_error:
                        logger.warning(f"Could not get explanation: {explain_error}")
                        explanation = f"พบข้อมูล {len(data)} รายการ"

                # Step 5: Confidence score
                confidence_result = None
                try:
                    if "nt-validation" in self.mcp_client.servers:
                        validation_summary = await self.mcp_client.call_tool(
                            "get_validation_summary",
                            {
                                "sql": sql_query,
                                "question": question,
                                "context_name": context_name,
                                "has_similar_example": False,
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
                except Exception as conf_error:
                    logger.warning(f"Could not calculate confidence: {conf_error}")

                t_total = time.perf_counter() - start_request
                logger.info(f"Hybrid Mode: Total Request Time: {t_total:.4f}s")

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

    @staticmethod
    def _prepare_data_for_explanation(data: List[Dict]) -> List[Dict]:
        """
        Prepare data for explain_result — balance accuracy vs speed.

        NOTE: Frontend table gets FULL data separately. This is ONLY for AI explanation.

        ≤ 200 rows:  send all (fast enough, ~7s explain)
        > 200 rows:  aggregate by text columns → reduce to ≤ 200 rows
                     all groups preserved, just detail rows merged

        Previously data[:30] was biased by ORDER BY. Now we aggregate smartly.
        """
        if not data:
            return data

        if len(data) <= 200:
            return data

        # Aggregate: GROUP BY text columns, SUM numeric columns
        from collections import defaultdict

        sample = data[0]
        text_cols = [k for k, v in sample.items() if isinstance(v, str)]
        num_cols = [k for k, v in sample.items() if isinstance(v, (int, float))]

        if not text_cols or not num_cols:
            return data[:200]

        # Strategy: progressively drop the LEAST important dimension
        # Drop the column with MOST distinct values that contributes LEAST to grouping
        # i.e. the "detail" dimension — keeps the primary grouping intact
        # Example: dept(20) × quarter(4) × BG(8) = 640 → drop BG(8) → 80 rows
        cols_by_cardinality = sorted(
            text_cols,
            key=lambda c: len(set(row.get(c, '') for row in data)),
        )
        # Drop from the MIDDLE: not the smallest (time) nor largest (primary), but the detail
        # Reorder: put highest-cardinality-but-not-biggest last (protect primary grouping)
        if len(cols_by_cardinality) >= 3:
            # Keep first (smallest = time/quarter) and last (biggest = primary category)
            # Drop middle ones first
            protected = {cols_by_cardinality[0], cols_by_cardinality[-1]}
            droppable = [c for c in cols_by_cardinality if c not in protected]
            cols_by_cardinality = droppable + [cols_by_cardinality[0], cols_by_cardinality[-1]]
        # For 2 columns: drop the one with fewer distinct values (likely time → keep primary)
        # Already sorted ascending, so first = smallest

        group_cols = list(text_cols)
        for attempt in range(len(cols_by_cardinality)):
            groups = defaultdict(lambda: {c: 0.0 for c in num_cols})
            for row in data:
                key = tuple(row.get(c, '') for c in group_cols)
                for c in num_cols:
                    groups[key][c] += (row.get(c, 0) or 0)

            if len(groups) <= 200:
                break

            # Drop highest-cardinality column that's still in group_cols
            for drop_col in cols_by_cardinality:
                if drop_col in group_cols and len(group_cols) > 1:
                    group_cols.remove(drop_col)
                    break

        agg_data = []
        for key, sums in groups.items():
            row = {c: k for c, k in zip(group_cols, key)}
            row.update(sums)
            agg_data.append(row)

        agg_data.sort(key=lambda r: r.get(num_cols[0], 0), reverse=True)
        result = agg_data[:200]

        dropped = set(text_cols) - set(group_cols)
        if dropped:
            logger.info(f"explain data: {len(data)} → {len(result)} rows (dropped dimensions: {dropped})")
        return result

    def _extract_sql(self, text: str) -> Optional[str]:
        """Extract SQL from AI response"""
        sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        code_match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()

        select_match = re.search(r'(SELECT\s+.*?(?:;|$))', text, re.DOTALL | re.IGNORECASE)
        if select_match:
            sql = select_match.group(1).strip()
            if '\n\n' in sql:
                sql = sql.split('\n\n')[0]
            return sql.rstrip(';') + '' if not sql.endswith(';') else sql

        return None

    def _extract_explanation(self, text: str) -> str:
        """Extract explanation from AI response"""
        text_without_sql = re.sub(r'```sql.*?```', '', text, flags=re.DOTALL | re.IGNORECASE)
        text_without_sql = re.sub(r'```.*?```', '', text_without_sql, flags=re.DOTALL)

        explanation_match = re.search(r'\*\*คำอธิบาย:?\*\*\s*(.*)', text_without_sql, re.DOTALL)
        if explanation_match:
            return explanation_match.group(1).strip()

        cleaned = text_without_sql.strip()
        if cleaned:
            return cleaned

        return "ดำเนินการสำเร็จ"

    def _get_vanna_context_string(self, question: str) -> str:
        """Retrieve and format RAG context from Vanna"""
        try:
            if not self.vanna:
                return ""
            contexts = self.vanna.get_rag_context(question)

            parts = []

            if contexts.get('ddl'):
                parts.append("### Relevant Tables (Schema):")
                parts.extend(contexts['ddl'])

            if contexts.get('doc'):
                parts.append("\n### Relevant Rules & Dictionary:")
                parts.extend(contexts['doc'])

            if contexts.get('sql'):
                parts.append("\n### Similar Examples (Golden SQL):")
                for sql in contexts['sql']:
                    parts.append(f"- {sql}")

            if not parts:
                return ""

            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Error getting Vanna context: {e}")
            return ""

    # ============================================================
    # Smart Value Lookup
    # ============================================================

    # Thai stop words and question words that should not be searched in DB
    _THAI_STOP_WORDS = {
        "รายได้", "ค่าใช้จ่าย", "บริการ",
        "เท่าไหร่", "เท่าไร", "อะไร", "อยากรู้", "ไหน", "ยังไง", "เมื่อไร",
        "ทั้งหมด", "รวม", "แยก", "ตาม", "ราย", "เดือน", "ปี", "ไตรมาส",
        "รายเดือน", "รายไตรมาส", "รายปี",
        "เปรียบเทียบ", "เทียบ", "กับ", "และ", "ของ", "ที่", "ใน", "จาก",
        "มี", "ให้", "ดู", "หา", "แสดง", "สรุป", "วิเคราะห์",
        "มากสุด", "น้อยสุด", "สูงสุด", "ต่ำสุด", "มาก", "น้อย", "สุด",
        "อันดับ", "อันดับแรก", "แรก", "หลัง", "ล่าสุด",
        "หน่วยงาน", "ส่วนงาน",  # generic org terms — actual names are in dictionary
        "the", "of", "and", "for", "by", "in", "to", "a", "is",
        "total", "sum", "count", "group", "show", "revenue", "expense",
    }

    def _extract_keywords_from_question(self, question: str, context_name: str = None) -> List[str]:
        """
        Extract searchable keywords using dictionary-based longest-match.

        Strategy:
        1. Dictionary scan: find known terms (from keyword_value_index + master_hierarchy_values)
           using longest-match-first against the raw question text
        2. Regex fallback: split remaining text by whitespace for English/numeric tokens
        3. Filter: skip numbers, stop words, and overly long unmatched phrases
        """
        import time
        t0 = time.perf_counter()

        keywords = []
        question_lower = question.lower().strip()

        # --- Phase 1: Dictionary-based extraction (handles Thai without word segmentation) ---
        try:
            from app.services.schema_service import SchemaService
            from app.config import settings as app_settings
            db_path = app_settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            schema_svc = SchemaService(db_path=db_path)
            known_terms = schema_svc.get_known_terms(context_name)

            # Scan question for longest matches
            remaining = question_lower
            for term in known_terms:
                term_lower = term.lower()
                if len(term_lower) < 2:
                    continue
                if term_lower in remaining and term_lower not in self._THAI_STOP_WORDS:
                    keywords.append(term)
                    # Remove matched term to avoid re-matching substrings
                    remaining = remaining.replace(term_lower, " ", 1)

        except Exception as e:
            logger.warning(f"Dictionary-based extraction failed: {e}")

        # --- Phase 2: Regex fallback for remaining English/numeric tokens ---
        parts = re.split(r'[\s,;:?!()（）\[\]]+', question.strip())
        for part in parts:
            part = part.strip().strip('"\'')
            if len(part) < 2:
                continue
            # Skip pure numbers
            if re.match(r'^\d+$', part):
                continue
            if part.lower() in self._THAI_STOP_WORDS:
                continue
            # Skip long Thai phrases that didn't match dictionary (likely noise)
            if len(part) > 20 and not any(c.isascii() and c.isalpha() for c in part):
                continue
            # Only add English tokens or short Thai tokens not already found
            if any(c.isascii() and c.isalpha() for c in part):
                keywords.append(part)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)

        t_extract = time.perf_counter() - t0
        logger.info(f"Keyword extraction: {len(unique)} keywords in {t_extract:.3f}s — {[k[:30] for k in unique[:10]]}")

        return unique

    def _lookup_values_from_question(self, question: str, context_name: str, table_name: str) -> List[Dict]:
        """Look up actual database values for keywords extracted directly from question."""
        from app.services.schema_service import SchemaService
        from app.config import settings as app_settings
        import time

        t0 = time.perf_counter()
        results = []

        keywords = self._extract_keywords_from_question(question, context_name)
        if not keywords:
            return results

        try:
            db_path = app_settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            schema_svc = SchemaService(db_path=db_path)

            # Phase 2: also search master_hierarchy_values aliases
            try:
                from app.services.hierarchy_service import hierarchy_service
                has_hierarchy = True
            except Exception:
                has_hierarchy = False

            for kw in keywords[:5]:  # Cap at 5 keywords to limit DB queries
                matches = schema_svc.search_keyword_index(kw, context_name=context_name, limit=5)
                if matches:
                    results.extend(matches)
                elif has_hierarchy:
                    # Try hierarchy alias search (more precise)
                    hier_matches = hierarchy_service.search_aliases(context_name, kw, limit=3)
                    if hier_matches:
                        for hm in hier_matches:
                            results.append({
                                "keyword": kw,
                                "column_name": hm["column_name"],
                                "column_value": hm["value"],
                                "source": "hierarchy_alias",
                            })
                    else:
                        # Fallback to direct DB search
                        db_matches = schema_svc.search_db_for_keyword(kw, table_name=table_name, context_name=context_name, limit=5)
                        results.extend(db_matches)
                else:
                    db_matches = schema_svc.search_db_for_keyword(kw, table_name=table_name, context_name=context_name, limit=5)
                    results.extend(db_matches)

            t_lookup = time.perf_counter() - t0
            if results:
                logger.info(f"Value Lookup: {len(keywords)} keywords → {len(results)} matches ({t_lookup:.3f}s)")

        except Exception as e:
            logger.warning(f"Value Lookup failed: {e}")

        return results

    @staticmethod
    def _detect_hierarchy_level(question: str, context_name: str) -> Optional[Dict]:
        """Detect user's intended hierarchy FILTER level from question keywords.

        Uses longest-match to avoid 'บริการ' matching product when
        user said 'กลุ่มบริการ'.

        Drill-down pattern: when both parent and child keywords are present
        (e.g. "กลุ่ม fixed line แต่ละบริการ"), returns the PARENT level
        (for WHERE filter), not the child level (for GROUP BY).
        The AI is instructed via DRILL-DOWN PATTERN rules to use child for GROUP BY.
        """
        hierarchy = get_column_hierarchies().get(context_name)
        if not hierarchy:
            return None

        question_lower = question.lower()

        # Collect all matching levels with their longest keyword match
        matched_levels: Dict[int, tuple] = {}  # level_num → (keyword_len, level_info)
        for level_info in hierarchy:
            for kw in level_info["detection_keywords"]:
                if kw.lower() in question_lower:
                    lvl = level_info["level"]
                    if lvl not in matched_levels or len(kw) > matched_levels[lvl][0]:
                        matched_levels[lvl] = (len(kw), level_info)

        if not matched_levels:
            return None

        # Single level matched → return it
        if len(matched_levels) == 1:
            return list(matched_levels.values())[0][1]

        # Multiple levels matched (drill-down pattern)
        # Return the PARENT level (lower level number) for WHERE filter
        # The AI will use the child level for GROUP BY via DRILL-DOWN PATTERN rules
        parent_level = min(matched_levels.keys())
        return matched_levels[parent_level][1]

    @staticmethod
    def _format_value_matches(value_matches: List[Dict], hierarchy=None, detected_level=None) -> str:
        """Format value lookup results for injection into prompt.

        When hierarchy info is available, groups matches by level and marks
        the intended level so AI doesn't OR across hierarchy levels.
        """
        if not value_matches:
            return ""

        # No hierarchy → flat format (original behavior)
        if not hierarchy:
            return AIService._format_value_matches_flat(value_matches)

        # --- Hierarchy-aware format ---
        # Build column → level mapping
        col_to_level: Dict[str, Dict] = {}
        for level_info in hierarchy:
            for col in level_info["columns"]:
                col_to_level[col.lower()] = level_info

        # Group matches by hierarchy level
        by_level: Dict[int, List[Dict]] = {}
        for m in value_matches:
            level_info = col_to_level.get(m["column_name"].lower())
            lvl = level_info["level"] if level_info else 999
            by_level.setdefault(lvl, []).append(m)

        # If none of the matches belong to any hierarchy column, fall back to flat
        if not by_level or (len(by_level) == 1 and 999 in by_level):
            return AIService._format_value_matches_flat(value_matches)

        intended_level_num = detected_level["level"] if detected_level else None

        lines = ["**Actual Values Found in Database (ค่าจริงจากฐานข้อมูล):**"]
        lines.append("ค่าด้านล่างจัดกลุ่มตามลำดับชั้น (Hierarchy) — ใช้เฉพาะระดับที่ตรงกับคำถาม")
        lines.append("")

        for level_info in sorted(hierarchy, key=lambda l: l["level"]):
            matches = by_level.get(level_info["level"], [])
            if not matches:
                continue
            is_intended = (intended_level_num == level_info["level"])
            marker = " ← **ระดับที่ตรงกับคำถาม (USE THIS LEVEL)**" if is_intended else ""
            lines.append(f'### Level {level_info["level"]}: {level_info["label_th"]} ({level_info["label_en"]}){marker}')

            by_kw: Dict[str, List[Dict]] = {}
            for m in matches:
                by_kw.setdefault(m.get("keyword", "?"), []).append(m)
            for kw, kw_matches in by_kw.items():
                lines.append(f'  keyword "{kw}":')
                for m in kw_matches[:5]:
                    col, val = m["column_name"], m["column_value"]
                    if is_intended:
                        lines.append(f'    - column: `{col}`, value: `{val}`')
                        lines.append(f'      → **USE THIS**: `{col} LIKE \'%{kw}%\'`')
                    else:
                        lines.append(f'    - column: `{col}`, value: `{val}` (different level — do NOT use)')
            lines.append("")

        lines.append("⚠️ HIERARCHY RULES (สำคัญมาก!):")
        lines.append("1. ถ้ามี **USE THIS LEVEL** → ใช้ column จาก level นั้นเป็น WHERE filter")
        lines.append("2. ห้าม OR ข้าม level เด็ดขาด (ทำให้ตัวเลขผิดเพี้ยนหลายสิบเท่า)")
        lines.append("3. ถ้าไม่มี USE THIS LEVEL → ใช้ level สูงสุด (parent) ที่มี match")
        lines.append("4. ใช้ LIKE '%keyword%' สำหรับ text columns เสมอ")
        lines.append("")
        lines.append("⚠️ DRILL-DOWN PATTERN (สำคัญ!):")
        lines.append("ถ้าคำถามมีรูปแบบ 'แต่ละ X ของ Y' หรือ 'X ใน Y มีอะไรบ้าง':")
        lines.append("- Y = parent level → ใช้เป็น WHERE filter")
        lines.append("- X = child level → ใช้เป็น GROUP BY / SELECT")
        lines.append("ตัวอย่าง: 'แต่ละบริการของกลุ่ม Fixed Line' →")
        lines.append("  WHERE SERVICE_GROUP LIKE '%Fixed Line%' GROUP BY PRODUCT_NAME")
        return "\n".join(lines)

    @staticmethod
    def _format_value_matches_flat(value_matches: List[Dict]) -> str:
        """Format value matches without hierarchy awareness (original flat format)."""
        if not value_matches:
            return ""

        by_keyword: Dict[str, List[Dict]] = {}
        for m in value_matches:
            kw = m.get("keyword", "?")
            by_keyword.setdefault(kw, []).append(m)

        lines = ["**Actual Values Found in Database (ค่าจริงจากฐานข้อมูล):**"]
        lines.append("ค่าด้านล่างเป็นค่าจริงจากตารางที่กำลังใช้ — ใช้ LIKE pattern ในการค้นหา")
        lines.append("")

        for kw, matches in by_keyword.items():
            lines.append(f'- keyword "{kw}":')
            for m in matches[:5]:
                col = m["column_name"]
                val = m["column_value"]
                lines.append(f'  - column: `{col}`, actual value: `{val}`')
                lines.append(f'    → recommended: `{col} LIKE \'%{kw}%\'`')

        lines.append("")
        lines.append("⚠️ IMPORTANT:")
        lines.append("- ใช้ LIKE '%keyword%' สำหรับ text columns (ห้ามใช้ = กับค่าข้อความ)")
        lines.append("- ค่า actual value ข้างบนเป็นตัวอย่างจริงจาก DB — ถ้าต้องการ exact match ให้ใช้ค่านี้")
        lines.append("- ถ้า Actual Values ขัดกับ Semantic Mapping → ให้เชื่อ Actual Values (เพราะมาจาก DB จริง)")

        return "\n".join(lines)

    # ============================================================
    # Two-Pass SQL Generation
    # ============================================================

    def _parse_intent_json(self, text: str) -> Optional[Dict]:
        """Parse intent JSON from AI response."""
        if not text:
            return None

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    async def _extract_intent(
        self,
        question: str,
        system_prompt: str,
        context_name: str,
        context_table: str,
        context_thai: str,
        history_context: str,
        rag_context: str,
        cheap_model: Optional[str] = None
    ) -> Optional[Dict]:
        """Pass 1: Extract structured intent from user question."""
        intent_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

{rag_context}

---
**Task:** วิเคราะห์คำถามข้างต้นและส่งคืน JSON ที่มีโครงสร้างตามนี้เท่านั้น ห้ามมี text อื่นนอก JSON:

```json
{{
  "intent_type": "aggregation | comparison | trend | detail | ranking | lookup",
  "metrics": ["column_name_to_aggregate"],
  "aggregate_function": "SUM | COUNT | AVG | MIN | MAX",
  "dimensions": ["column_for_group_by"],
  "filters": [
    {{"column": "col_name", "operator": "= | LIKE | > | < | >= | <= | IN | BETWEEN", "value": "value_or_pattern"}}
  ],
  "time_range": {{"year": 2025, "month": null}},
  "ordering": {{"column": "col_name_or_alias", "direction": "ASC | DESC"}},
  "limit": null,
  "matched_mappings": [
    {{"keyword": "user_keyword", "sql_condition": "COLUMN operator 'value'"}}
  ]
}}
```

**กฎสำคัญ:**
1. ตรวจสอบ semantic mappings ใน system prompt ก่อน -- ถ้ามี keyword ที่ตรง ให้ใส่ใน matched_mappings พร้อม sql_condition ที่คัดลอกมาจาก mapping
2. ถ้า User ระบุปี พ.ศ. ให้แปลงเป็น ค.ศ. (พ.ศ. - 543) ใส่ใน time_range.year
3. ถ้าไม่แน่ใจค่า filter ให้ใช้ LIKE operator
4. ห้ามสร้าง SQL -- ระบุเฉพาะ intent เท่านั้น
5. ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น"""

        try:
            import time
            t0 = time.perf_counter()

            # Use cheap model for intent extraction (lightweight JSON task)
            original_model = None
            if cheap_model and cheap_model != self.provider.model:
                original_model = self.provider.model
                self.provider.model = cheap_model
                logger.info(f"Two-Pass: Intent using cheap model '{cheap_model}' (default: '{original_model}')")

            try:
                response_text = await self.provider.generate_content(intent_prompt, system_prompt)
            except Exception as cheap_err:
                # Cheap model failed — retry with default model
                if original_model:
                    logger.warning(f"Cheap model '{cheap_model}' failed for intent: {cheap_err}. Retrying with default model '{original_model}'...")
                    self.provider.model = original_model
                    original_model = None  # Already restored
                    response_text = await self.provider.generate_content(intent_prompt, system_prompt)
                else:
                    raise
            finally:
                if original_model:
                    self.provider.model = original_model

            t_intent = time.perf_counter() - t0

            intent_json = self._parse_intent_json(response_text)

            if intent_json:
                logger.info(f"Two-Pass: Pass 1 complete ({t_intent:.2f}s). Intent: {json.dumps(intent_json, ensure_ascii=False)[:500]}")
                return intent_json
            else:
                logger.warning(f"Two-Pass: Failed to parse intent JSON ({t_intent:.2f}s).")
                return None

        except Exception as e:
            logger.error(f"Two-Pass: Intent extraction failed: {type(e).__name__}: {e}")
            return None

    def _build_pass2_prompt(
        self,
        question: str,
        intent: Dict,
        context_table: str,
        context_thai: str,
        value_matches: List[Dict] = None,
        hierarchy: List[Dict] = None,
        detected_level: Optional[Dict] = None
    ) -> str:
        """Build Pass 2 prompt using structured intent from Pass 1."""

        # --- Filters section: ALWAYS from intent (authoritative) ---
        # Value matches must NOT replace intent filters
        intent_dimensions = {d.lower() for d in intent.get("dimensions", [])}

        filters_text = "  ไม่มี filter"
        if intent.get("filters"):
            lines = [f"  - {f['column']} {f['operator']} {f['value']}" for f in intent["filters"]]
            filters_text = "\n".join(lines)

        mappings_text = "  ไม่พบ mapping ที่ตรง"
        if intent.get("matched_mappings"):
            lines = [f"  - keyword '{m.get('keyword')}' → {m.get('sql_condition')}" for m in intent["matched_mappings"]]
            mappings_text = "\n".join(lines)

        dims = intent.get("dimensions", [])
        dimensions_text = ", ".join(dims) if dims else "ไม่มี (ไม่ต้อง GROUP BY)"

        time_text = "ไม่ระบุ"
        tr = intent.get("time_range")
        if tr:
            parts = []
            if tr.get("year"):
                parts.append(f"ปี ค.ศ. {tr['year']} (พ.ศ. {tr['year'] + 543})")
            if tr.get("month"):
                parts.append(f"เดือน {tr['month']}")
            if parts:
                time_text = ", ".join(parts)

        ordering_text = "ไม่ระบุ"
        if intent.get("ordering"):
            o = intent["ordering"]
            ordering_text = f"{o.get('column', '?')} {o.get('direction', 'DESC')}"

        # Filter value_matches: exclude matches on dimension columns (GROUP BY, not WHERE)
        # Keep only matches on columns that are in intent.filters (confirms exact values)
        intent_filter_cols = {f['column'].lower() for f in intent.get("filters", [])}
        filtered_value_matches = None
        if value_matches:
            filtered_value_matches = [
                m for m in value_matches
                if m['column_name'].lower() not in intent_dimensions
                and m['column_name'].lower() in intent_filter_cols
            ]
            if not filtered_value_matches:
                filtered_value_matches = None

        value_matches_text = ""
        if filtered_value_matches:
            value_matches_text = self._format_value_matches(
                filtered_value_matches, hierarchy=hierarchy, detected_level=detected_level
            )

        return f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

---
**Structured Intent (วิเคราะห์จากคำถามแล้ว):**
- Intent Type: {intent.get('intent_type', 'aggregation')}
- Metrics: {intent.get('aggregate_function', 'SUM')}({', '.join(intent.get('metrics', ['REVENUE_VALUE']))})
- Dimensions (GROUP BY): {dimensions_text}
- Filters:
{filters_text}
- Time Range: {time_text}
- Matched Semantic Mappings:
{mappings_text}
- Ordering: {ordering_text}
- Limit: {intent.get('limit') or 'ไม่จำกัด'}

---
{value_matches_text}
**สร้าง SQL จาก Structured Intent ข้างต้น:**
สำคัญ:
- ต้องใช้ตาราง {context_table} เท่านั้น
- **ยึดตาม Structured Intent เป็นหลัก** — Dimensions คือ GROUP BY, Filters คือ WHERE
- ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters ข้างต้น (ยกเว้น time_range)
- Dimensions (GROUP BY) columns ห้ามใช้เป็น WHERE filter
- ถ้ามี "Actual Values Found" → ใช้เป็นค่าอ้างอิงสำหรับ filter ที่ระบุไว้แล้วเท่านั้น
- ถ้ามี Matched Semantic Mappings ให้ใช้ sql_condition จาก mapping โดยตรง
- ห้าม FORMAT ตัวเลขใน SQL (ส่งค่าดิบ)
- ห้าม OR ข้ามระดับ hierarchy (เช่น service_group OR product_name)

```sql
<SQL ที่สร้างจาก Structured Intent>
```

**คำอธิบาย:**
<คำอธิบายผลลัพธ์ภาษาไทย>"""

    def train(self, question: str, sql_query: str) -> bool:
        """Train the RAG system with a verified Q&A pair"""
        try:
            if not self.vanna:
                logger.warning("Vanna service not initialized, skipping training")
                return False

            return self.vanna.train(question=question, sql=sql_query)
        except Exception as e:
            logger.error(f"Error in AIService.train: {e}")
            return False

    async def suggest_mappings(self, columns: List[Dict], samples: Dict[str, List]) -> List[Dict[str, str]]:
        """Suggest column name mappings (aliases) using AI."""
        try:
            column_info = []
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                sample_vals = samples.get(col_name, [])[:3]
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

            result = await self.provider.generate_content(prompt, system_prompt="คุณเป็น AI ที่ช่วยตั้งชื่อคอลัมน์ภาษาไทยให้เหมาะสม")

            json_match = re.search(r'```json\s*(\[.*?\])\s*```', result, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group(1))
                return suggestions

            try:
                suggestions = json.loads(result)
                if isinstance(suggestions, list):
                    return suggestions
            except Exception:
                pass

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
            return [
                {
                    'col': col['name'],
                    'alias': col['name'],
                    'reason': 'ไม่สามารถสร้างคำแนะนำได้ ใช้ชื่อเดิม'
                }
                for col in columns
            ]


# ============================================================
# Factory Functions (backward compatible)
# ============================================================

def create_claude_service(
    api_key: str,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    extended_thinking: bool = False,
    thinking_budget_tokens: int = 8000,
    **kwargs
) -> AIService:
    provider = ClaudeProvider(
        api_key=api_key,
        model=model or settings.CLAUDE_MODEL,
        extended_thinking=extended_thinking,
        thinking_budget_tokens=thinking_budget_tokens,
    )
    return AIService(provider=provider, mcp_client=mcp_client)


def create_gemini_service(
    api_key: str,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    **kwargs
) -> AIService:
    provider = GeminiProvider(
        api_key=api_key,
        model=model or settings.GEMINI_MODEL,
    )
    return AIService(provider=provider, mcp_client=mcp_client)


def create_matcha_service(
    api_key: str,
    api_url: str = None,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    **kwargs
) -> AIService:
    provider = MatchaProvider(
        api_key=api_key,
        api_url=api_url or settings.MATCHA_API_URL or "",
        model=model or settings.MATCHA_MODEL,
    )
    return AIService(provider=provider, mcp_client=mcp_client)

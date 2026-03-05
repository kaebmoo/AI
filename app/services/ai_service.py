
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
# Hierarchy: level 0 (broadest) → level N (most specific)
# AI must filter on ONLY ONE level; cross-level OR inflates results.
COLUMN_HIERARCHIES: Dict[str, List[Dict]] = {
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
        {"level": 0, "columns": ["BUSINESS"],
         "label_th": "กลุ่มธุรกิจ", "label_en": "Business",
         "detection_keywords": ["กลุ่มธุรกิจ", "ธุรกิจ", "business"]},
        {"level": 1, "columns": ["SERVICE_GROUP"],
         "label_th": "กลุ่มบริการ", "label_en": "Service Group",
         "detection_keywords": ["กลุ่มบริการ", "service group"]},
        {"level": 2, "columns": ["PRODUCT_NAME", "PRODUCT"],
         "label_th": "ผลิตภัณฑ์", "label_en": "Product",
         "detection_keywords": ["ผลิตภัณฑ์", "product", "สินค้า"]},
    ],
}


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

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None) -> str:
        return await self.provider.explain_result(question, sql, data, system_prompt, dimension_families=dimension_families)

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

            # Build conversation history context
            history_context = ""
            if history and len(history) > 0:
                history_lines = []
                for i, msg in enumerate(history[-6:]):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        history_lines.append(f"คำถามก่อนหน้า: {content}")
                    elif role == "assistant":
                        sql_match = re.search(r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
                        if sql_match:
                            sql_preview = sql_match.group(1).strip()
                            history_lines.append(f"SQL ที่ใช้:\n{sql_preview[:500]}")
                        else:
                            old_format = re.search(r'\(Context SQL:\s*(.*?)\)', content, re.DOTALL)
                            if old_format:
                                history_lines.append(f"SQL ที่ใช้:\n{old_format.group(1).strip()[:500]}")
                            else:
                                history_lines.append(f"คำตอบ: {content[:150]}...")

                if history_lines:
                    history_context = "\n\n**บริบทจากการสนทนาก่อนหน้า:**\n" + "\n".join(history_lines)
                    history_context += "\n\n**กฎจัดการ Filter (ดูจาก SQL ก่อนหน้า):**\n"
                    history_context += "- ถ้า User ระบุค่าใหม่สำหรับ Column เดิม → **REPLACE** filter นั้น\n"
                    history_context += "- ถ้า User เพิ่มเงื่อนไข Column ใหม่ → **MERGE** (AND) เข้าไป\n"
                    history_context += "- ถ้า User พูดว่า 'ทั้งหมด/ภาพรวม' → **RESET** filter ทั้งหมด"
                    logger.info(f"Hybrid Mode: Using conversation history with {len(history_lines)} context items")

            if attempt == 0:
                # Get RAG Context
                rag_context = ""
                try:
                    t0 = time.perf_counter()
                    rag_context = self._get_vanna_context_string(question)
                    t_rag = time.perf_counter() - t0
                    if rag_context:
                        logger.info(f"Hybrid Mode: Injected RAG Context ({len(rag_context)} chars) took {t_rag:.4f}s")
                except Exception as e:
                    logger.warning(f"Failed to get RAG context: {e}")

                # Value Lookup — always-on (searches actual DB values for keywords in question)
                value_lookup_text = ""
                detected_level = None
                try:
                    value_matches = self._lookup_values_from_question(question, context_name, context_table)
                    if value_matches:
                        hierarchy = COLUMN_HIERARCHIES.get(context_name)
                        detected_level = self._detect_hierarchy_level(question, context_name)
                        if hierarchy and detected_level:
                            logger.info(f"Hierarchy: level {detected_level['level']} ({detected_level['label_en']})")
                        value_lookup_text = self._format_value_matches(
                            value_matches, hierarchy=hierarchy, detected_level=detected_level
                        )
                except Exception as e:
                    logger.warning(f"Value Lookup failed: {e}")

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
                        history_context=history_context,
                        rag_context=rag_context
                    )

                    if intent_json:
                        logger.info(f"Two-Pass Mode: Pass 1 success. Building Pass 2 prompt.")
                        user_prompt = self._build_pass2_prompt(
                            question=question,
                            intent=intent_json,
                            context_table=context_table,
                            context_thai=context_thai,
                            value_matches=value_matches if value_lookup_text else None,
                            hierarchy=COLUMN_HIERARCHIES.get(context_name),
                            detected_level=detected_level
                        )
                    else:
                        logger.warning("Two-Pass Mode: Pass 1 failed. Falling back to one-pass CoT prompt.")
                        two_pass_enabled = False

                # One-Pass Mode (default or fallback)
                if not two_pass_enabled or attempt > 0:
                    user_prompt = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

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

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

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
                    response_text = await self.provider.generate_content(user_prompt, system_prompt)
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

                # Enhance explanation
                if not data:
                    explanation = f"ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\n{sql_query}\n```\n\nอาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา\n- ชื่อคอลัมน์หรือค่าที่ใช้ค้นหาอาจไม่ถูกต้อง"
                elif len(data) > 0:
                    try:
                        t0 = time.perf_counter()
                        simple_system_prompt = "You are a data visualization assistant. Analyze the data and provide a Thai explanation and chart recommendation."
                        explanation = await self.provider.explain_result(question, sql_query, data, simple_system_prompt, dimension_families=dim_families)
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

    def _extract_keywords_from_question(self, question: str) -> List[str]:
        """Extract searchable keywords from raw question text (no AI needed)."""
        strip_prefixes = [
            "ค่าใช้จ่าย", "รายได้", "บริการ", "ค่า", "ยอด",
            "ขอดู", "ขอ", "แสดง", "หา", "ดู", "สรุป",
        ]
        stop_words = {
            "รายได้", "ค่าใช้จ่าย", "บริการ",
            "เท่าไหร่", "เท่าไร", "อะไร", "อยากรู้",
            "ทั้งหมด", "รวม", "แยก", "ตาม", "ราย", "เดือน", "ปี", "ไตรมาส",
            "รายเดือน", "รายไตรมาส", "รายปี",
            "เปรียบเทียบ", "เทียบ", "กับ", "และ", "ของ", "ที่", "ใน", "จาก",
            "มี", "ให้", "ดู", "หา", "แสดง", "สรุป", "วิเคราะห์",
            "the", "of", "and", "for", "by", "in", "to", "a", "is",
            "total", "sum", "count", "group", "show", "revenue", "expense",
        }

        keywords = []

        parts = re.split(r'[\s,;:?!()（）\[\]]+', question.strip())
        for part in parts:
            part = part.strip().strip('"\'')
            if len(part) < 2 or part.lower() in stop_words:
                continue

            candidates = [part]
            current = part
            for _ in range(3):
                stripped = False
                for prefix in strip_prefixes:
                    if current.startswith(prefix) and len(current) > len(prefix) + 1:
                        current = current[len(prefix):]
                        if current not in stop_words and len(current) >= 2:
                            candidates.append(current)
                        stripped = True
                        break
                if not stripped:
                    break

            for c in candidates:
                if c not in stop_words and len(c) >= 2:
                    keywords.append(c)

        seen = set()
        unique = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)
        return unique

    def _lookup_values_from_question(self, question: str, context_name: str, table_name: str) -> List[Dict]:
        """Look up actual database values for keywords extracted directly from question."""
        from app.services.schema_service import SchemaService
        from app.config import settings as app_settings
        import time

        t0 = time.perf_counter()
        results = []

        keywords = self._extract_keywords_from_question(question)
        if not keywords:
            return results

        try:
            db_path = app_settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            schema_svc = SchemaService(db_path=db_path)

            for kw in keywords:
                matches = schema_svc.search_keyword_index(kw, context_name=context_name, limit=5)
                if matches:
                    results.extend(matches)
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
        """Detect user's intended hierarchy level from question keywords.

        Uses longest-match to avoid 'บริการ' matching product when
        user said 'กลุ่มบริการ'.
        """
        hierarchy = COLUMN_HIERARCHIES.get(context_name)
        if not hierarchy:
            return None

        question_lower = question.lower()
        candidates = []
        for level_info in hierarchy:
            for kw in level_info["detection_keywords"]:
                if kw.lower() in question_lower:
                    candidates.append((len(kw), level_info))

        if not candidates:
            return None

        # Longest match wins (e.g. "กลุ่มบริการ" > "บริการ")
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

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
        lines.append("1. ถ้ามี **USE THIS LEVEL** → ใช้ column จาก level นั้นเท่านั้น")
        lines.append("2. ห้าม OR ข้าม level เด็ดขาด (ทำให้ตัวเลขผิดเพี้ยนหลายสิบเท่า)")
        lines.append("3. ถ้าไม่มี USE THIS LEVEL → ใช้ level สูงสุด (parent) ที่มี match")
        lines.append("4. ใช้ LIKE '%keyword%' สำหรับ text columns เสมอ")
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
        rag_context: str
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
            response_text = await self.provider.generate_content(intent_prompt, system_prompt)
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

        if value_matches:
            # Determine which columns belong to the intended hierarchy level
            intended_cols = None
            if hierarchy and detected_level:
                intended_cols = {c.lower() for c in detected_level["columns"]}

            by_keyword: Dict[str, List[Dict]] = {}
            for m in value_matches:
                by_keyword.setdefault(m.get("keyword", ""), []).append(m)

            real_filter_lines = []
            for kw, matches in by_keyword.items():
                for m in matches[:5]:
                    col = m['column_name']
                    # Skip columns from other hierarchy levels
                    if intended_cols and col.lower() not in intended_cols:
                        continue
                    level_label = detected_level['label_th'] if detected_level else "DB"
                    real_filter_lines.append(f"  - {col} LIKE '%{kw}%'  (ค่าจริงจาก {level_label})")

            if real_filter_lines:
                filters_text = "\n".join(real_filter_lines)
                level_label = detected_level['label_th'] if detected_level else "DB"
                mappings_text = f"  (ใช้ค่าจริงจาก Filters — ระดับ: {level_label})"
            else:
                filters_text = "  ไม่มี filter"
                mappings_text = "  ไม่พบ mapping ที่ตรง"
        else:
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

        value_matches_text = ""
        if value_matches:
            value_matches_text = self._format_value_matches(
                value_matches, hierarchy=hierarchy, detected_level=detected_level
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
- ถ้ามี "Actual Values Found" ข้างต้น → ใช้ column/value จากผลค้นหาจริง ห้ามเดาเอง
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

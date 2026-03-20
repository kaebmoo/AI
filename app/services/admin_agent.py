"""
Admin Agent — Tool-Calling Dispatcher
=======================================
Natural language interface for admin operations.
Admin types in Thai/English → LLM selects appropriate tool → execute with confirmation flow.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.tools.admin.registry import admin_tool_registry

logger = logging.getLogger(__name__)

# System prompt for the admin agent
ADMIN_AGENT_SYSTEM_PROMPT = """คุณคือ Admin Agent ของระบบ NT AI Assistant
คุณช่วย admin จัดการ configuration ของระบบ NL-to-SQL

## กฎสำคัญ (ต้องปฏิบัติเสมอ):
1. **ใช้ tool เสมอถ้ามี tool ที่เกี่ยวข้อง** — ห้ามตอบเองถ้า tool ทำได้ ให้เรียก tool แล้วรอผลลัพธ์
2. **ค้นหาก่อนเพิ่ม** — ก่อน add ใดๆ ให้ search ก่อนเพื่อตรวจ duplicate
3. **ตอบเป็นภาษาไทย**
4. **ห้ามถามกลับถ้าสามารถ search ได้เลย** — เช่น ถ้าถามว่า "มี mapping อะไรบ้าง" ให้เรียก search_mappings เลย ไม่ต้องถามว่าต้องการ keyword อะไร
5. **ถ้าไม่มี tool** — บอกตรงๆ ว่าทำไม่ได้

## เมื่อไหร่ควรใช้ tool ไหน:
- ถามเรื่อง context, view, ตาราง → `list_contexts` (แสดง main_view ด้วย)
- ถามเรื่อง mapping, keyword → `search_mappings`
- ถามเรื่อง rule → `search_rules`
- ถามเรื่อง example, ตัวอย่าง SQL → `search_examples`
- ถามเรื่อง hierarchy, ค่าใน column → `search_hierarchy`
- ถามเรื่อง query logs, ปัญหา → `analyze_query_logs`
- ถามเรื่อง feedback → `review_feedback`
- ถามเรื่อง view structure, columns → `inspect_view`
- ต้องการ validate config → `validate_config`
- ต้องการ refresh cache → `refresh_cache`
"""


class AdminAgent:
    """Tool-calling agent for admin operations."""

    def __init__(self, db: Session):
        self.db = db

    async def chat(
        self,
        message: str,
        conversation_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a chat message from admin.

        Args:
            message: User message in Thai or English.
            conversation_id: Optional existing conversation ID.
            user_id: Admin user ID.

        Returns:
            Dict with:
                - response: str (Thai text response)
                - tool_calls: List of tool calls made
                - pending_confirmation: Optional dict if tool needs confirmation
                - conversation_id: int
        """
        # Get or create conversation
        conversation_id = await self._ensure_conversation(conversation_id, user_id, message)

        # Save user message
        await self._save_message(conversation_id, "user", message)

        # Load conversation history
        history = await self._load_history(conversation_id)

        # Get tool specs
        tool_specs = admin_tool_registry.get_all_specs()

        # Call LLM with tools — with retry if LLM doesn't select a tool
        MAX_AGENT_RETRIES = 2
        llm_result = None
        tool_calls_made = []
        pending_confirmation = None

        for attempt in range(MAX_AGENT_RETRIES + 1):
            try:
                extra_instruction = ""
                if attempt > 0:
                    # Retry: tell LLM it failed to call a tool
                    extra_instruction = (
                        "\n\n⚠️ คำเตือน: ในรอบก่อน คุณตอบเป็นข้อความแทนที่จะเรียก tool "
                        "กรุณาเลือก tool ที่เหมาะสมและตอบเป็น JSON tool_call เท่านั้น "
                        f"คำถามเดิม: \"{message}\""
                    )
                llm_result = await self._call_llm(message + extra_instruction, history, tool_specs)
            except Exception as e:
                logger.error(f"Admin Agent LLM call failed (attempt {attempt}): {e}")
                if attempt == MAX_AGENT_RETRIES:
                    error_response = f"เกิดข้อผิดพลาดในการเรียก AI: {str(e)}"
                    await self._save_message(conversation_id, "assistant", error_response)
                    return {
                        "response": error_response,
                        "tool_calls": [],
                        "pending_confirmation": None,
                        "conversation_id": conversation_id,
                    }
                continue

            # Process tool calls
            if llm_result.get("tool_calls"):
                for tool_call in llm_result["tool_calls"]:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})

                    tool = admin_tool_registry.get(tool_name)
                    if not tool:
                        logger.warning(f"Admin Agent: unknown tool '{tool_name}'")
                        continue

                    if tool.requires_confirmation:
                        pending_confirmation = {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "description": tool.description_th,
                            "message": f"ต้องการดำเนินการ '{tool.description_th}' ด้วยข้อมูลนี้หรือไม่?",
                        }
                        await self._save_message(
                            conversation_id, "assistant", "",
                            tool_name=tool_name, tool_args=json.dumps(tool_args, ensure_ascii=False),
                            tool_result=json.dumps({"status": "pending_confirmation"}, ensure_ascii=False),
                        )
                        break
                    else:
                        result = await tool.execute(tool_args, self.db)
                        tool_calls_made.append({
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "result": result,
                        })
                        await self._save_message(
                            conversation_id, "assistant", "",
                            tool_name=tool_name, tool_args=json.dumps(tool_args, ensure_ascii=False),
                            tool_result=json.dumps(result, ensure_ascii=False, default=str),
                        )
                break  # Tool was called — exit retry loop

            # LLM didn't call any tool — try keyword-based fallback before retrying LLM
            if attempt == 0:
                fallback_result = self._keyword_fallback(message)
                if fallback_result:
                    tool_name, tool_args = fallback_result
                    tool = admin_tool_registry.get(tool_name)
                    if tool:
                        logger.info(f"Admin Agent: keyword fallback → {tool_name}({tool_args})")
                        result = await tool.execute(tool_args, self.db)
                        tool_calls_made.append({
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "result": result,
                        })
                        await self._save_message(
                            conversation_id, "assistant", "",
                            tool_name=tool_name, tool_args=json.dumps(tool_args, ensure_ascii=False),
                            tool_result=json.dumps(result, ensure_ascii=False, default=str),
                        )
                        break  # Fallback succeeded
                # No fallback hit — will retry LLM with stronger instruction
                logger.info(f"Admin Agent: LLM didn't call tool (attempt {attempt}), retrying...")
                continue
            else:
                # Last retry also failed — use LLM text response as-is
                break

        # Get final text response
        if pending_confirmation:
            final_response = pending_confirmation["message"]
            args_summary = ", ".join(f"{k}='{v}'" for k, v in pending_confirmation["tool_args"].items())
            final_response += f"\n\nรายละเอียด: {args_summary}"
        elif tool_calls_made:
            # Send tool results back to LLM to summarize in Thai
            final_response = await self._summarize_tool_results(
                message, tool_calls_made, history, tool_specs
            )
        elif llm_result and llm_result.get("text"):
            final_response = llm_result["text"]
        else:
            final_response = "ไม่สามารถดำเนินการได้ กรุณาระบุคำสั่งให้ชัดเจนขึ้น"

        # Save assistant response
        await self._save_message(conversation_id, "assistant", final_response)

        return {
            "response": final_response,
            "tool_calls": tool_calls_made,
            "pending_confirmation": pending_confirmation,
            "conversation_id": conversation_id,
        }

    # ── Keyword-based fallback when LLM fails to select a tool ────────

    # Maps Thai/English keywords → (tool_name, args_builder)
    _KEYWORD_TOOL_MAP = [
        # context/view questions
        (r"context|view|ตาราง|บริบท|ชุดข้อมูล", "list_contexts", {}),
        # mapping questions
        (r"mapping|แมป|แม็ป", "search_mappings", lambda m: {"keyword": ""}),
        # rule questions
        (r"rule|กฎ|เงื่อนไข", "search_rules", lambda m: {"search_text": ""}),
        # example questions
        (r"example|ตัวอย่าง|golden", "search_examples", lambda m: {"search_text": ""}),
        # feedback
        (r"feedback|ฟีดแบ็ก|thumbs|คะแนน", "review_feedback", lambda m: {}),
        # query log / error
        (r"query.?log|error|fail|ผิดพลาด|ล้มเหลว", "analyze_query_logs", lambda m: {}),
        # hierarchy
        (r"hierarchy|ลำดับ|โครงสร้าง", "search_hierarchy", lambda m: {"keyword": ""}),
        # cache
        (r"cache|แคช|refresh|รีเฟรช", "refresh_cache", {}),
    ]

    def _keyword_fallback(self, message: str) -> Optional[tuple]:
        """Match user message to a tool using keyword patterns.

        Returns (tool_name, tool_args) or None if no match.
        """
        import re
        msg_lower = message.lower()

        for pattern, tool_name, args_or_builder in self._KEYWORD_TOOL_MAP:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                if callable(args_or_builder):
                    args = args_or_builder(message)
                else:
                    args = dict(args_or_builder)
                return (tool_name, args)

        return None

    async def confirm_action(self, conversation_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Confirm and execute a pending tool action.

        Args:
            conversation_id: Conversation with pending action.

        Returns:
            Dict with execution result.
        """
        # Find the pending tool call
        pending = await self._find_pending_action(conversation_id)
        if not pending:
            return {
                "response": "ไม่พบ action ที่รอการยืนยัน",
                "tool_calls": [],
                "pending_confirmation": None,
                "conversation_id": conversation_id,
            }

        tool_name = pending["tool_name"]
        tool_args = pending["tool_args"]

        tool = admin_tool_registry.get(tool_name)
        if not tool:
            return {
                "response": f"ไม่พบ tool '{tool_name}'",
                "tool_calls": [],
                "pending_confirmation": None,
                "conversation_id": conversation_id,
            }

        # Execute
        result = await tool.execute(tool_args, self.db)

        # Save result
        await self._save_message(
            conversation_id, "assistant", result.get("message", ""),
            tool_name=tool_name,
            tool_args=json.dumps(tool_args, ensure_ascii=False),
            tool_result=json.dumps(result, ensure_ascii=False, default=str),
        )

        return {
            "response": result.get("message", "ดำเนินการเสร็จสิ้น"),
            "tool_calls": [{"tool_name": tool_name, "tool_args": tool_args, "result": result}],
            "pending_confirmation": None,
            "conversation_id": conversation_id,
        }

    def _get_provider(self):
        """Create an LLM provider from DB config."""
        from app.providers.registry import provider_registry
        from app.services.admin_config_service import AdminConfigService

        config_service = AdminConfigService(self.db)
        provider_name = config_service.get_config("default_ai_provider", "matcha")

        provider_kwargs = {}
        try:
            api_key = config_service.get_provider_api_key(provider_name)
            if api_key:
                provider_kwargs["api_key"] = api_key
            model = config_service.get_config(f"{provider_name}_model")
            if model:
                provider_kwargs["model"] = model
            if provider_name == "matcha":
                api_url = config_service.get_config("matcha_api_url")
                if api_url:
                    provider_kwargs["api_url"] = api_url
        except Exception:
            pass

        provider = provider_registry.create_provider(provider_name, **provider_kwargs)
        if not provider:
            raise ValueError(f"Cannot create provider '{provider_name}'")
        return provider, provider_name

    async def _call_llm(self, message: str, history: List[Dict], tool_specs: List[Dict]) -> Dict[str, Any]:
        """Call LLM with NATIVE function calling (not text-based).

        Uses generate_sql() which supports OpenAI-compatible tool_choice='auto'.
        Falls back to generate_content() text-based if native fails.
        """
        provider, provider_name = self._get_provider()

        # Convert tool_specs to the format generate_sql expects:
        # [{"name": ..., "description": ..., "input_schema": ...}]
        native_tools = []
        for spec in tool_specs:
            func = spec.get("function", spec)
            native_tools.append({
                "name": func["name"],
                "description": func["description"],
                "input_schema": func.get("parameters", func.get("input_schema", {})),
            })

        # Build history as messages
        messages_for_llm = []
        for h in history[-10:]:
            if h.get("role") and h.get("content"):
                messages_for_llm.append({"role": h["role"], "content": h["content"]})

        # ── Strategy 1: Native function calling via generate_sql() ──
        try:
            raw = await provider.generate_sql(
                question=message,
                system_prompt=ADMIN_AGENT_SYSTEM_PROMPT,
                tools=native_tools,
                history=messages_for_llm,
            )

            # Parse response — extract tool_calls from OpenAI-format response
            tool_calls = []
            text_content = ""

            resp = raw.get("response", {})
            choices = resp.get("choices", [])
            if choices:
                choice_msg = choices[0].get("message", {})
                text_content = choice_msg.get("content") or ""

                # Native tool_calls from the API
                api_tool_calls = choice_msg.get("tool_calls", [])
                for tc in api_tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    if name:
                        tool_calls.append({"name": name, "arguments": args})

            if tool_calls:
                logger.info(f"Admin Agent: native tool call → {[tc['name'] for tc in tool_calls]}")
                return {"text": text_content, "tool_calls": tool_calls, "tokens_used": raw.get("tokens_used", 0)}

            # No tool_calls in response — maybe text_content has embedded JSON?
            if text_content:
                embedded = self._parse_text_tool_call(text_content)
                if embedded:
                    return {"text": "", "tool_calls": embedded, "tokens_used": raw.get("tokens_used", 0)}
                return {"text": text_content, "tool_calls": [], "tokens_used": raw.get("tokens_used", 0)}

        except Exception as e:
            logger.warning(f"Admin Agent: native tool calling failed ({e}), falling back to text mode")

        # ── Strategy 2: Fallback to text-based generate_content() ──
        tool_descriptions = []
        for spec in tool_specs:
            func = spec.get("function", spec)
            params_str = json.dumps(func.get("parameters", {}), ensure_ascii=False, indent=2)
            tool_descriptions.append(f"### {func['name']}\n{func['description']}\nParameters:\n```json\n{params_str}\n```")

        system_prompt = ADMIN_AGENT_SYSTEM_PROMPT + f"""

## Available Tools:
{chr(10).join(tool_descriptions)}

## วิธีเรียกใช้ Tool:
ถ้าคำถามเกี่ยวข้องกับ tool ใดๆ ข้างต้น ให้เรียก tool ทันทีโดยตอบเฉพาะ JSON:
```json
{{"tool_call": {{"name": "tool_name", "arguments": {{...}}}}}}
```
ตอบเป็นข้อความปกติเฉพาะเมื่อไม่มี tool ที่เกี่ยวข้องเท่านั้น
"""

        result = await provider.generate_content(
            prompt=message,
            system_prompt=system_prompt,
            history=messages_for_llm,
        )

        response_text = str(result) if result else ""
        embedded = self._parse_text_tool_call(response_text)
        if embedded:
            return {"text": "", "tool_calls": embedded, "tokens_used": 0}

        return {"text": response_text, "tool_calls": [], "tokens_used": 0}

    def _parse_text_tool_call(self, text: str) -> List[Dict]:
        """Extract tool_call JSON from text response (fallback parser)."""
        import re

        # Strip markdown code fences
        cleaned = text
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1)

        # Find {"tool_call": {...}} with balanced braces
        idx = cleaned.find('"tool_call"')
        if idx == -1:
            return []

        start = cleaned.rfind('{', 0, idx)
        if start == -1:
            return []

        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == '{':
                depth += 1
            elif cleaned[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(cleaned[start:i + 1])
                        tc = parsed.get("tool_call", {})
                        if tc.get("name"):
                            return [{"name": tc["name"], "arguments": tc.get("arguments", {})}]
                    except json.JSONDecodeError:
                        pass
                    break

        return []

    async def _ensure_conversation(self, conversation_id: Optional[int], user_id: Optional[int], message: str) -> int:
        """Get or create conversation."""
        from app.models.admin_agent import AdminAgentConversation

        if conversation_id:
            conv = self.db.query(AdminAgentConversation).filter(
                AdminAgentConversation.id == conversation_id
            ).first()
            if conv:
                conv.updated_at = datetime.utcnow()
                self.db.commit()
                return conv.id

        # Create new
        conv = AdminAgentConversation(
            user_id=user_id,
            title=message[:100],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv.id

    async def _save_message(
        self, conversation_id: int, role: str, content: str,
        tool_name: str = None, tool_args: str = None, tool_result: str = None
    ):
        """Save message to DB."""
        from app.models.admin_agent import AdminAgentMessage

        msg = AdminAgentMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            created_at=datetime.utcnow(),
        )
        self.db.add(msg)
        self.db.commit()

    async def _summarize_tool_results(
        self, original_question: str, tool_calls_made: List[Dict],
        history: List[Dict], tool_specs: List[Dict],
    ) -> str:
        """Send tool results back to LLM to get a Thai summary."""
        # Build a compact summary of what happened
        tool_results_text = []
        for tc in tool_calls_made:
            tool_name = tc["tool_name"]
            result = tc["result"]
            result_json = json.dumps(result, ensure_ascii=False, default=str)
            # Truncate very large results for the LLM
            if len(result_json) > 3000:
                result_json = result_json[:3000] + "... (truncated)"
            tool_results_text.append(f"Tool: {tool_name}\nResult:\n{result_json}")

        summarize_prompt = f"""ผู้ใช้ถามว่า: "{original_question}"

ระบบเรียก tool แล้วได้ผลลัพธ์ดังนี้:

{chr(10).join(tool_results_text)}

กรุณาสรุปผลลัพธ์เป็นภาษาไทยให้เข้าใจง่าย:
- ถ้ามีข้อมูลเยอะ ให้สรุปประเด็นสำคัญ (ไม่ต้องแสดงทุก row — frontend จะแสดงตารางเอง)
- ถ้าไม่พบข้อมูล ให้แนะนำสิ่งที่ทำได้ต่อ
- ถ้าสำเร็จ ให้บอกสิ่งที่ทำสำเร็จ
- ห้ามตอบเป็น JSON — ตอบเป็นข้อความธรรมดา"""

        try:
            provider, _ = self._get_provider()
            if provider:
                result = await provider.generate_content(
                    prompt=summarize_prompt,
                    system_prompt="คุณเป็นผู้ช่วย admin สรุปผลลัพธ์จาก tool เป็นภาษาไทย กระชับ เข้าใจง่าย",
                    history=[],
                )
                summary = str(result).strip()
                if summary and '"tool_call"' not in summary:
                    return summary
        except Exception as e:
            logger.warning(f"Summarize failed, using fallback: {e}")

        # Fallback: simple summary without LLM
        parts = []
        for tc in tool_calls_made:
            parts.append(tc["result"].get("message", ""))
            data = tc["result"].get("data")
            if data and isinstance(data, list):
                parts.append(f"(พบ {len(data)} รายการ — ดูรายละเอียดในตารางด้านล่าง)")
        return "\n".join(parts) or "ดำเนินการเสร็จสิ้น"

    async def _load_history(self, conversation_id: int) -> List[Dict]:
        """Load conversation history for LLM context."""
        from app.models.admin_agent import AdminAgentMessage

        messages = self.db.query(AdminAgentMessage).filter(
            AdminAgentMessage.conversation_id == conversation_id
        ).order_by(AdminAgentMessage.created_at).all()

        history = []
        for m in messages[-20:]:  # Last 20 messages
            entry = {"role": m.role, "content": m.content or ""}
            if m.tool_name:
                entry["content"] += f"\n[Tool: {m.tool_name}]"
            if m.tool_result:
                try:
                    result = json.loads(m.tool_result)
                    entry["content"] += f"\n[Result: {result.get('message', '')}]"
                except Exception:
                    pass
            history.append(entry)

        return history

    async def _find_pending_action(self, conversation_id: int) -> Optional[Dict]:
        """Find the last pending confirmation action."""
        from app.models.admin_agent import AdminAgentMessage

        msg = self.db.query(AdminAgentMessage).filter(
            AdminAgentMessage.conversation_id == conversation_id,
            AdminAgentMessage.tool_name != None,
        ).order_by(AdminAgentMessage.created_at.desc()).first()

        if not msg or not msg.tool_result:
            return None

        try:
            result = json.loads(msg.tool_result)
            if result.get("status") == "pending_confirmation":
                return {
                    "tool_name": msg.tool_name,
                    "tool_args": json.loads(msg.tool_args) if msg.tool_args else {},
                }
        except Exception:
            pass

        return None

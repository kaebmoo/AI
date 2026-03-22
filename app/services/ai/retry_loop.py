import json
import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from app.providers.base import QueryResult, RetryStatus

if TYPE_CHECKING:
    from app.services.ai.service import AIService


logger = logging.getLogger(__name__)

RECOVERABLE_RETRY_EXCEPTIONS = (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError)


async def query_with_retry(
    service: "AIService",
    question: str,
    max_retries: int = 3,
    history: Optional[List[Dict]] = None,
    on_status: Optional[Callable[[RetryStatus], None]] = None,
    explain: bool = True,
    context_name: str = "revenue",
) -> QueryResult:
    del max_retries, explain, context_name

    tools = await service.mcp_client.get_tools()
    max_turns = 20
    current_history = list(history or [])

    system_prompt = "You are a helpful data assistant. Use the available tools to answer the user's question. Always validate your understanding of the schema first."

    sql_query = None
    data = []
    explanation = ""
    total_tokens = 0
    working_question = question
    get_vanna_context_string = service.get_vanna_context_string

    try:
        rag_context = get_vanna_context_string(question)
        if rag_context:
            system_prompt += f"\n\n{rag_context}"
            logger.info("Injected Vanna RAG Context (%s chars)", len(rag_context))
    except RECOVERABLE_RETRY_EXCEPTIONS as exc:
        logger.error("Failed to get Vanna context: %s", exc)

    for turn in range(max_turns):
        logger.info("AIService Turn %s/%s for provider %s", turn, max_turns, service.provider_name)

        prompt_question = working_question or ""
        result = await service.provider.generate_sql(prompt_question, system_prompt, tools, current_history)
        response = result["response"]
        total_tokens += result["tokens_used"]

        tool_calls = []

        if service.provider_name == "claude":
            for content in response.content:
                if content.type == "tool_use":
                    tool_calls.append({
                        "id": content.id,
                        "name": content.name,
                        "args": content.input,
                    })

            if not tool_calls:
                text = response.content[0].text if response.content else ""
                explanation = text
                break

        elif service.provider_name == "gemini":
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if part.function_call:
                    tool_calls.append({
                        "name": part.function_call.name,
                        "args": part.function_call.args,
                    })
            if not tool_calls:
                explanation = candidate.content.parts[0].text if candidate.content.parts else ""
                break

        elif service.provider_name == "matcha":
            msg = response["choices"][0]["message"]
            if msg.get("tool_calls"):
                if turn == 0 and working_question:
                    current_history.append({"role": "user", "content": working_question})
                    working_question = None

                current_history.append(msg)

                for tool_call in msg["tool_calls"]:
                    tool_calls.append({
                        "id": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "args": json.loads(tool_call["function"]["arguments"]),
                    })
            else:
                explanation = msg.get("content", "")
                break

        for call in tool_calls:
            if on_status:
                on_status(RetryStatus(turn, max_turns, "executing", f"Calling tool: {call['name']}"))

            if call["name"] == "execute_query":
                sql_query = call["args"].get("sql") or call["args"].get("query")

            try:
                logger.info("Calling tool %s with args: %s", call["name"], call["args"])
                tool_result = await service.mcp_client.call_tool(call["name"], call["args"])

                if call["name"] == "execute_query" and isinstance(tool_result, str):
                    try:
                        data = json.loads(tool_result)
                    except json.JSONDecodeError:
                        pass
            except RECOVERABLE_RETRY_EXCEPTIONS as exc:
                tool_result = f"Error: {str(exc)}"
                logger.error("Tool execution error: %s", tool_result)

            if service.provider_name == "claude":
                current_history.append({"role": "assistant", "content": [
                    {"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]}
                ]})
                current_history.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": call["id"], "content": str(tool_result)}
                ]})

            elif service.provider_name == "gemini":
                if turn == 0 and working_question:
                    current_history.append({"role": "user", "content": working_question})
                    working_question = None

                last_msg = current_history[-1] if current_history else None
                model_msg_marker = f"__gemini_model_turn_{turn}__"

                if not last_msg or last_msg.get("internal_id") != model_msg_marker:
                    matched_parts = []
                    if response.candidates and response.candidates[0].content:
                        for part in response.candidates[0].content.parts:
                            try:
                                if hasattr(part, "to_dict"):
                                    matched_parts.append(part.to_dict())
                                    continue
                            except (AttributeError, TypeError, ValueError):
                                pass

                            part_dict = {}
                            if part.function_call:
                                part_dict["function_call"] = {
                                    "name": part.function_call.name,
                                    "args": dict(part.function_call.args) if part.function_call.args else {},
                                }
                            if hasattr(part, "text") and part.text:
                                part_dict["text"] = part.text
                            if hasattr(part, "thought_signature") and part.thought_signature:
                                part_dict["thought_signature"] = part.thought_signature
                            if hasattr(part, "thought") and part.thought:
                                part_dict["thought"] = part.thought

                            if part_dict:
                                matched_parts.append(part_dict)

                    if matched_parts:
                        current_history.append({
                            "role": "model",
                            "parts_raw": matched_parts,
                            "internal_id": model_msg_marker,
                        })

                tool_content = tool_result
                if isinstance(tool_result, str):
                    try:
                        tool_content = json.loads(tool_result)
                    except json.JSONDecodeError:
                        pass

                if not isinstance(tool_content, dict):
                    tool_content = {"result": tool_content}

                current_history.append({
                    "role": "function",
                    "name": call["name"],
                    "content": tool_content,
                })

            elif service.provider_name == "matcha":
                current_history.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": str(tool_result),
                })

    if not explanation and total_tokens > 0:
        explanation = "I apologize, but I was unable to complete the analysis within the allowed number of steps. The request required exploring too much schema information."

    pending_limit_warning = service.get_pending_limit_warning()
    if pending_limit_warning:
        explanation += pending_limit_warning

    return QueryResult(
        question=question,
        sql_query=sql_query or "",
        data=data if isinstance(data, list) else [],
        explanation=explanation,
        tokens_used=total_tokens,
        provider=service.provider_name,
    )
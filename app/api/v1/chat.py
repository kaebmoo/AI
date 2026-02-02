from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import time
import re
import json
import logging

from app.api import deps

logger = logging.getLogger(__name__)
from app.models.user import User
from app.models.chat import ChatHistory
from app.schemas.chat import ChatRequest, ChatResponse, DataWarning
from app.services.ai_service import AIService, create_gemini_service, create_claude_service, create_matcha_service
from app.services.schema_service import SchemaService
from app.config import settings

router = APIRouter()


# =============================================================================
# Auto-detect Context from Question
# =============================================================================

# Default keywords (fallback if DB doesn't have keywords configured)
DEFAULT_CONTEXT_KEYWORDS = {
    "expense": [
        "ค่าใช้จ่าย", "expense", "งบประมาณ", "budget", "ต้นทุน", "cost",
        "ค่าจ้าง", "เงินเดือน", "salary", "ค่าดำเนินการ", "operating",
        "ค่าเช่า", "rent", "ค่าน้ำ", "ค่าไฟ", "utility", "ค่าโทรศัพท์",
        "ใช้จ่าย", "จ่าย", "expenditure", "spending", "ค่าบริการ"
    ],
    "revenue": [
        "รายได้", "revenue", "ยอดขาย", "sales", "income", "กำไร", "profit",
        "ยอดรับ", "รายรับ", "earning", "ขาย", "sold"
    ]
}


def detect_context_from_question(question: str, schema_service: SchemaService = None) -> str:
    """
    Auto-detect context from user's question.

    Priority:
    1. Keywords from schema_contexts table (DB) - extensible by admin
    2. Default keywords (fallback for revenue/expense)
    3. Default to 'revenue' if no match

    Returns the most appropriate context name.
    """
    question_lower = question.lower()
    context_scores = {}

    # 1. First, try keywords from database (allows admin to add new contexts)
    if schema_service:
        try:
            contexts = schema_service.get_all_contexts()
            for ctx in contexts:
                ctx_name = ctx.get('name')
                ctx_keywords = ctx.get('keywords', [])
                priority = ctx.get('priority', 0)

                if isinstance(ctx_keywords, list) and ctx_keywords:
                    # Count keyword matches
                    score = sum(1 for kw in ctx_keywords if kw.lower() in question_lower)
                    if score > 0:
                        # Add priority bonus to score
                        context_scores[ctx_name] = score + (priority * 0.1)
        except Exception:
            pass

    # 2. If no DB matches, use default keywords
    if not context_scores:
        for ctx_name, keywords in DEFAULT_CONTEXT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in question_lower)
            if score > 0:
                context_scores[ctx_name] = score

    # 3. Return highest scoring context, or default to 'revenue'
    if context_scores:
        best_context = max(context_scores, key=context_scores.get)
        return best_context

    return "revenue"


# =============================================================================
# Data Warning Detection
# =============================================================================

# Warning definitions - can be moved to database for admin management
DATA_WARNINGS = [
    {
        "code": "OTHER_REVENUE_NOT_NET",
        "keywords": ["รายได้อื่น"],
        "exclude_keywords": ["ผลตอบแทนทางการเงิน"],
        "columns_to_check": ["BUSINESS_GROUP", "SERVICE_GROUP", "PRODUCT_NAME", "gl_group"],
        "message": "หมายเหตุ: 'รายได้อื่น' เป็นรายได้ที่ยังไม่สุทธิ",
        "severity": "warning"
    },
]


def detect_data_warnings(data: List[Dict[str, Any]], sql_query: str = None) -> List[DataWarning]:
    """
    Detect warnings based on data content.
    """
    warnings = []
    if not data:
        return warnings

    # Convert data to searchable string for each row
    for warning_def in DATA_WARNINGS:
        warning_triggered = False
        has_exclude = False

        for row in data:
            row_str = str(row.values()).lower()

            # Check if any keyword matches
            for keyword in warning_def["keywords"]:
                if keyword.lower() in row_str:
                    warning_triggered = True
                    break

            # Check if exclude keyword exists (means this is an exception)
            for exclude in warning_def.get("exclude_keywords", []):
                if exclude.lower() in row_str:
                    has_exclude = True
                    break

            if warning_triggered:
                break

        # Add warning if triggered (even if some rows have exclude, still warn)
        if warning_triggered:
            warnings.append(DataWarning(
                code=warning_def["code"],
                message=warning_def["message"],
                severity=warning_def["severity"]
            ))

    return warnings


async def detect_multiple_sources_warning(
    sql_query: str,
    mcp_client,
    context_name: str = "revenue"
) -> List[DataWarning]:
    """
    Detect when LIKE query matches multiple distinct values.
    Warns user that aggregated data comes from multiple sources.
    """
    warnings = []

    if not sql_query:
        return warnings

    # Group columns to check for multiple sources
    GROUP_COLUMNS = [
        'account_group_name', 'account_name',
        'service_group', 'business_group', 'product_name',
        'department', 'division', 'gl_group'
    ]

    # Find LIKE conditions in SQL
    # Pattern: column_name LIKE '%value%'
    like_pattern = r"(\w+)\s+LIKE\s+'%([^%]+)%'"
    matches = re.findall(like_pattern, sql_query, re.IGNORECASE)

    if not matches:
        return warnings

    # Check each LIKE condition
    for column, search_value in matches:
        column_lower = column.lower()

        # Only check group columns (not time columns like year, month)
        if column_lower not in GROUP_COLUMNS:
            continue

        # Determine table based on context
        table = "v_expense_mart" if context_name == "expense" else "revenue_search"

        # Query to find distinct values matching the LIKE
        check_sql = f"""
            SELECT DISTINCT "{column}" as matched_value
            FROM {table}
            WHERE "{column}" LIKE '%{search_value}%'
            LIMIT 10
        """

        try:
            result = await mcp_client.call_tool("execute_query", {
                "sql": check_sql,
                "limit": 10,
                "validate_first": False
            })

            result_data = json.loads(result) if isinstance(result, str) else result

            if result_data.get("success") and result_data.get("data"):
                matched_values = [row.get("matched_value") for row in result_data["data"] if row.get("matched_value")]

                # If multiple distinct values match, warn user
                if len(matched_values) > 1:
                    values_list = ", ".join([f"'{v}'" for v in matched_values[:5]])
                    if len(matched_values) > 5:
                        values_list += f" และอื่นๆ อีก {len(matched_values) - 5} รายการ"

                    warnings.append(DataWarning(
                        code="MULTIPLE_SOURCES",
                        message=f"⚠️ ข้อมูลรวมจากหลายกลุ่ม: {values_list}",
                        severity="important"
                    ))

        except Exception as e:
            # Silently fail - don't break the main flow
            logger.debug(f"Multiple sources check failed: {e}")

    return warnings

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    # By default use the system configured provider from deps
    # If user specifies a provider override, we handle it below
    default_ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Process a natural language question about revenue/sales.
    1. Verify user permission
    2. Convert Question -> SQL & Explain (AIService)
    3. Save History
    """
    start_time = time.time()
    
    # Process Query
    # 1. Manage Conversation ID
    conversation_id = request.conversation_id
    if not conversation_id:
        import uuid
        conversation_id = str(uuid.uuid4())
    
    # 2. Get History if valid conversation_id
    history = []
    if conversation_id:
        # Get last 5 interaction pairs (10 messages)
        previous_chats = db.query(ChatHistory).filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == current_user.id
        ).order_by(ChatHistory.created_at.desc()).limit(5).all()
        
        # Reverse to chronological order
        for chat_entry in reversed(previous_chats):
            if chat_entry.question:
                history.append({"role": "user", "content": chat_entry.question})
            if chat_entry.ai_response:
                # Inject SQL Context in markdown format for easy extraction
                content = chat_entry.ai_response
                if chat_entry.generated_sql:
                    content += f"\n\n```sql\n{chat_entry.generated_sql}\n```"
                history.append({"role": "assistant", "content": content})
    
    # 3. Instantiate AI Service based on provider (Override) or Default
    ai_service = default_ai_service
    
    if request.provider and request.provider != settings.AI_PROVIDER:
        # Override Provider - Need to get MCP client manually
        mcp_client = deps.get_mcp_client(current_request)
        
        if request.provider == "claude":
            if not settings.ANTHROPIC_API_KEY:
                 raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
            ai_service = create_claude_service(
                api_key=settings.ANTHROPIC_API_KEY,
                mcp_client=mcp_client,
                model=settings.CLAUDE_MODEL
            )
        elif request.provider == "gemini":
            if not settings.GOOGLE_AI_API_KEY:
                 raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
            ai_service = create_gemini_service(
                api_key=settings.GOOGLE_AI_API_KEY,
                mcp_client=mcp_client,
                model=settings.GEMINI_MODEL
            )
        elif request.provider == "matcha":
             if not settings.MATCHA_AI_API_KEY:
                  raise HTTPException(status_code=500, detail="MATCHA config missing")
             ai_service = create_matcha_service(
                 api_key=settings.MATCHA_AI_API_KEY,
                 api_url=settings.MATCHA_API_URL,
                 mcp_client=mcp_client,
                 model=settings.MATCHA_MODEL
             )
        else:
             raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # 4. Context Logic
    # Create SchemaService once and reuse for context detection + prompt building
    import logging
    logger = logging.getLogger(__name__)

    db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    schema_service = SchemaService(db_path=db_path)

    # Auto-detect context from question if not explicitly specified
    if request.context:
        context_name = request.context
        logger.info(f"Using explicit context: {context_name}")
    else:
        # Check if follow-up question should maintain previous context
        previous_context = None
        if previous_chats:
            # Get context from previous SQL (check which table was used)
            last_sql = previous_chats[0].generated_sql or ""
            if "v_expense_mart" in last_sql.lower() or "expense" in last_sql.lower():
                previous_context = "expense"
            elif "revenue_search" in last_sql.lower() or "revenue" in last_sql.lower():
                previous_context = "revenue"

        # Auto-detect from current question
        detected_context = detect_context_from_question(request.question, schema_service)

        # Decide: maintain previous or use detected
        question_lower = request.question.lower()
        has_expense_keyword = any(kw in question_lower for kw in ["ค่าใช้จ่าย", "expense", "งบประมาณ", "cost"])
        has_revenue_keyword = any(kw in question_lower for kw in ["รายได้", "revenue", "ยอดขาย", "sales"])

        if previous_context and not has_expense_keyword and not has_revenue_keyword:
            # Follow-up without explicit context -> maintain previous
            context_name = previous_context
            logger.info(f"Maintaining previous context: {context_name} for follow-up: {request.question[:50]}...")
        else:
            # New topic or explicit context keywords
            context_name = detected_context
            logger.info(f"Auto-detected context: {context_name} for question: {request.question[:50]}...")

    # 5. Call AI Service with retry mechanism (Async)

    # Determine mode: hybrid (default, cost-effective) or mcp (full tools)
    query_mode = request.mode or "hybrid"

    if query_mode == "hybrid":
        # Hybrid Mode: Static prompt + MCP validation/execution
        # Cost: 2-4 API calls vs 13+ in MCP mode
        logger.info(f"Using HYBRID mode for query")
        logger.info(f"Context: {context_name}, Database: {settings.DATABASE_URL}")

        # Get context info for debugging
        context_info = schema_service.get_context_info(context_name)
        if context_info:
            logger.info(f"Using context: {context_info.get('name')}, main_view: {context_info.get('main_view')}")
        else:
            logger.warning(f"Context '{context_name}' not found, falling back to revenue")

        system_prompt = schema_service.build_system_prompt(
            ai_provider=request.provider or "gemini",
            include_samples=True,
            language="thai",
            context_name=context_name
        )

        result = await ai_service.query_hybrid(
            question=request.question,
            system_prompt=system_prompt,
            max_retries=request.max_retries,
            history=history,  # Pass conversation history for context
            on_status=lambda status: logger.info(
                f"Hybrid status: attempt={status.attempt}/{status.max_attempts}, "
                f"status={status.status}, message={status.message}"
            ),
            context_name=context_name
        )
    else:
        # MCP Mode: Full tool access (more expensive but more flexible)
        logger.info(f"Using MCP mode for query")
        result = await ai_service.query_with_retry(
            question=request.question,
            max_retries=request.max_retries,
            history=history,
            on_status=lambda status: logger.info(
                f"Retry status: attempt={status.attempt}/{status.max_attempts}, "
                f"status={status.status}, message={status.message}"
            ),
            explain=True,
            context_name=context_name
        )

    execution_time = (time.time() - start_time) * 1000

    # Debug: Log result details
    logger.info(f"Result - SQL: {result.sql_query[:100] if result.sql_query else 'None'}...")
    logger.info(f"Result - Data: {result.data}")
    logger.info(f"Result - Explanation: {result.explanation[:200] if result.explanation else 'None'}...")
    logger.info(f"Result - Error: {result.error}")

    # Log retry info
    if result.retry_count > 0:
        logger.info(f"Query succeeded after {result.retry_count} retries for question: {request.question[:50]}...")

    # Save History
    chat_entry = ChatHistory(
        user_id=current_user.id,
        conversation_id=conversation_id,
        question=result.question,
        generated_sql=result.sql_query,
        sql_result_summary=str(result.data)[:1000] if result.data else None,
        ai_response=result.explanation if not result.error else f"Error: {result.error}",
        execution_time_ms=execution_time,
        tokens_used=result.tokens_used
    )
    db.add(chat_entry)
    db.commit()
    db.refresh(chat_entry)

    # Prepare retry history for response
    retry_history_response = None
    if result.retry_history:
        retry_history_response = [
            {
                "attempt": r.get("attempt", 0),
                "error_type": r.get("error_type", "unknown"),
                "error": r.get("error", ""),
                "sql": r.get("sql")
            }
            for r in result.retry_history
        ]

    # Detect data warnings
    warnings_response = []

    # 1. Standard data warnings (based on content)
    if result.data:
        detected_warnings = detect_data_warnings(result.data, result.sql_query)
        warnings_response.extend([
            {"code": w.code, "message": w.message, "severity": w.severity}
            for w in detected_warnings
        ])

    # 2. Multiple sources warning (when LIKE matches multiple values)
    if result.sql_query and 'LIKE' in result.sql_query.upper():
        try:
            mcp_client = deps.get_mcp_client(current_request)
            multiple_source_warnings = await detect_multiple_sources_warning(
                result.sql_query,
                mcp_client,
                context_name
            )
            warnings_response.extend([
                {"code": w.code, "message": w.message, "severity": w.severity}
                for w in multiple_source_warnings
            ])
        except Exception as e:
            logger.debug(f"Multiple sources warning check failed: {e}")

    # Convert empty list to None for cleaner response
    if not warnings_response:
        warnings_response = None

    return {
        "id": chat_entry.id,
        "conversation_id": conversation_id,
        "question": result.question,
        "answer": chat_entry.ai_response,
        "sql_query": result.sql_query,
        "data": result.data,
        "execution_time_ms": execution_time,
        "retry_count": result.retry_count,
        "retry_history": retry_history_response,
        "warnings": warnings_response
    }

@router.get("/history", response_model=List[ChatResponse])
def get_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get chat history for the current user.
    """
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    ).order_by(ChatHistory.created_at.desc()).offset(skip).limit(limit).all()
    
    results = []
    for c in chats:
        results.append({
            "id": c.id,
            "question": c.question,
            "answer": c.ai_response,
            "sql_query": c.generated_sql,
            "data": None, 
            "execution_time_ms": c.execution_time_ms or 0
        })
    return results

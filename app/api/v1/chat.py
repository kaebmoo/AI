from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import time
import re
import json
import logging
from datetime import datetime

from app.api import deps

logger = logging.getLogger(__name__)
from app.models.user import User
from app.models.chat import ChatHistory
from app.schemas.chat import ChatRequest, ChatResponse, DataWarning, TrainingRequest
from app.services.ai_service import AIService, create_gemini_service, create_claude_service, create_matcha_service
from app.services.schema_service import SchemaService
from app.services.admin_config_service import AdminConfigService
from app.config import settings


router = APIRouter()

# =============================================================================
# Context & Metadata API
# =============================================================================

@router.get("/contexts", response_model=List[Dict[str, Any]])
def get_contexts(
    schema_service: SchemaService = Depends(deps.get_schema_service),
    current_user: User = Depends(deps.get_current_user)
):
    """Get all available data contexts"""
    try:
        contexts = schema_service.get_all_contexts()
        # Ensure 'auto' is not in DB list (it's frontend logic), but allow DB to override if needed
        return contexts
    except Exception as e:
        logger.error(f"Error fetching contexts: {e}")
        # Fallback
        return [
            {'name': 'revenue', 'display_name': 'รายได้', 'description': 'ข้อมูลรายได้'},
            {'name': 'expense', 'display_name': 'ค่าใช้จ่าย', 'description': 'ข้อมูลค่าใช้จ่าย'}
        ]

@router.post("/refresh")
def refresh_metadata(
    schema_service: SchemaService = Depends(deps.get_schema_service),
    current_user: User = Depends(deps.require_admin)
):
    """Force refresh of schema metadata and contexts"""
    try:
        schema_service.refresh_cache()
        schema_service.refresh_context_cache()
        return {"message": "Metadata and Contexts refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# =============================================================================
# Auto-detect Context from Question
# =============================================================================

# No more hardcoded keywords — all loaded from schema_contexts.keywords in DB


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

    # 2. Return highest scoring context, or default to highest-priority context from DB
    if context_scores:
        best_context = max(context_scores, key=context_scores.get)
        return best_context

    # 3. Default: use the highest-priority active context from DB
    if schema_service:
        try:
            contexts = schema_service.get_all_contexts()
            if contexts:
                return contexts[0].get('name', 'revenue')  # Already sorted by priority DESC
        except Exception:
            pass

    return "revenue"  # Last resort safety net


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
    context_name: str = "revenue",
    schema_service: SchemaService = None
) -> List[DataWarning]:
    """
    Detect when LIKE query matches multiple distinct values.
    Warns user that aggregated data comes from multiple sources.
    """
    warnings = []

    if not sql_query:
        return warnings

    # Get groupable columns from DB metadata (no hardcode)
    GROUP_COLUMNS = []
    table = context_name  # fallback
    if schema_service:
        context_info = schema_service.get_context_info(context_name)
        if context_info:
            table = context_info.get('main_view', context_name)
        # Get groupable columns for this context
        cols = schema_service.get_searchable_columns(context_name, table)
        GROUP_COLUMNS = [c.lower() for c in cols]

    if not GROUP_COLUMNS:
        return warnings

    # Find LIKE conditions in SQL
    like_pattern = r"(\w+)\s+LIKE\s+'%([^%]+)%'"
    matches = re.findall(like_pattern, sql_query, re.IGNORECASE)

    if not matches:
        return warnings

    # Check each LIKE condition
    for column, search_value in matches:
        column_lower = column.lower()

        if column_lower not in GROUP_COLUMNS:
            continue

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
    
    # 3. Instantiate AI Service based on provider selection
    # If user explicitly selected a provider → always create that provider's service
    # If no selection → use system default
    _ai_cfg = AdminConfigService(db).get_ai_config()
    selected_provider = request.provider or _ai_cfg.get("default_provider", settings.AI_PROVIDER)
    mcp_client = deps.get_mcp_client(current_request)

    if selected_provider == "claude":
        if not settings.ANTHROPIC_API_KEY:
             raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        ai_service = create_claude_service(
            api_key=settings.ANTHROPIC_API_KEY,
            mcp_client=mcp_client,
            model=_ai_cfg.get("claude_model", settings.CLAUDE_MODEL),
            extended_thinking=_ai_cfg.get("claude_extended_thinking", False),
            thinking_budget_tokens=_ai_cfg.get("claude_thinking_budget_tokens", 8000),
        )
    elif selected_provider == "gemini":
        if not settings.GOOGLE_AI_API_KEY:
             raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
        ai_service = create_gemini_service(
            api_key=settings.GOOGLE_AI_API_KEY,
            mcp_client=mcp_client,
            model=_ai_cfg.get("gemini_model", settings.GEMINI_MODEL),
        )
    elif selected_provider == "matcha":
         if not settings.MATCHA_AI_API_KEY:
              raise HTTPException(status_code=500, detail="MATCHA config missing")
         api_url = _ai_cfg.get("matcha_api_url") or settings.MATCHA_API_URL
         ai_service = create_matcha_service(
             api_key=settings.MATCHA_AI_API_KEY,
             api_url=api_url,
             mcp_client=mcp_client,
             model=_ai_cfg.get("matcha_model", settings.MATCHA_MODEL),
         )
    else:
         raise HTTPException(status_code=400, detail=f"Unknown provider: {selected_provider}")

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

        # If context changed from previous conversation → clear history
        if history and previous_chats:
            prev_context = getattr(previous_chats[0], 'context_name', None)
            if prev_context and prev_context != context_name:
                logger.info(f"Context changed: '{prev_context}' → '{context_name}' — clearing conversation history")
                history = []
    else:
        # Check if follow-up question should maintain previous context
        # Use context_name from ChatHistory (no SQL string parsing)
        previous_context = getattr(previous_chats[0], 'context_name', None) if previous_chats else None

        # Auto-detect from current question (uses DB keywords)
        detected_context = detect_context_from_question(request.question, schema_service)

        # Decide: if detected context matches a strong keyword → use detected, else maintain previous
        if detected_context and detected_context != previous_context:
            context_name = detected_context
            logger.info(f"Auto-detected context: {context_name} for question: {request.question[:50]}...")
        elif previous_context:
            context_name = previous_context
            logger.info(f"Maintaining previous context: {context_name} for follow-up: {request.question[:50]}...")
        else:
            context_name = detected_context
            logger.info(f"Using detected context: {context_name} for question: {request.question[:50]}...")

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
            context_name=context_name,
            rag_enabled=True  # ENABLE RAG OPTIMIZATION: Use lite prompt, let AIService inject snippets
        )

        _feature_flags = AdminConfigService(db).get_feature_flags()

        result = await ai_service.query_hybrid(
            question=request.question,
            system_prompt=system_prompt,
            max_retries=request.max_retries,
            history=history,  # Pass conversation history for context
            on_status=lambda status: logger.info(
                f"Hybrid status: attempt={status.attempt}/{status.max_attempts}, "
                f"status={status.status}, message={status.message}"
            ),
            context_name=context_name,
            two_pass_enabled=_feature_flags.get("two_pass_enabled", False),
            value_lookup_enabled=_feature_flags.get("value_lookup_enabled", False)
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
    # Handle both string and dict explanations
    if isinstance(result.explanation, dict):
        logger.info(f"Result - Explanation (dict): visualization={result.explanation.get('visualization')}, has_chart_config={bool(result.explanation.get('chart_config'))}")
    else:
        logger.info(f"Result - Explanation: {str(result.explanation)[:200] if result.explanation else 'None'}...")
    logger.info(f"Result - Error: {result.error}")

    # Log retry info
    if result.retry_count > 0:
        logger.info(f"Query succeeded after {result.retry_count} retries for question: {request.question[:50]}...")

    # Save History
    # Extract text explanation from dict or use string directly
    if isinstance(result.explanation, dict):
        ai_response_text = result.explanation.get("explanation", str(result.explanation))
    else:
        ai_response_text = result.explanation if result.explanation else ""

    chat_entry = ChatHistory(
        user_id=current_user.id,
        conversation_id=conversation_id,
        question=result.question,
        generated_sql=result.sql_query,
        sql_result_summary=str(result.data)[:1000] if result.data else None,
        ai_response=ai_response_text if not result.error else f"Error: {result.error}",
        execution_time_ms=execution_time,
        tokens_used=result.tokens_used,
        context_name=context_name
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
                context_name,
                schema_service=schema_service
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

    # Prepare confidence response
    confidence_response = None
    if result.confidence:
        confidence_response = {
            "score": result.confidence.score,
            "level": result.confidence.level,
            "level_th": result.confidence.level_th,
            "color": result.confidence.color,
            "factors": result.confidence.factors,
            "recommendation": result.confidence.recommendation
        }

    # Prepare visualization recommendation and chart config
    visualization_response = None
    chart_config_response = None
    if isinstance(result.explanation, dict):
        if "visualization" in result.explanation:
            visualization_response = result.explanation.get("visualization")
        if "chart_config" in result.explanation:
            chart_config_response = result.explanation.get("chart_config")
        # Ensure answer is string
        chat_entry.ai_response = result.explanation.get("explanation", str(result.explanation))
        # Update DB explanation to be clean text
        db.add(chat_entry)
        db.commit()

        # DEBUG: Log AI response
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"📊 AI Response - visualization: {visualization_response}, chart_config: {chart_config_response}")
    else:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"⚠️ AI explanation is not dict: {type(result.explanation)} = {result.explanation}")

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
        "warnings": warnings_response,
        "confidence": confidence_response,
        "visualization": visualization_response,
        "chart_config": chart_config_response
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
from app.models.feedback_models import GoldenExample

@router.post("/train")
async def train_model(
    request: TrainingRequest,
    current_request: Request, # for mcp client
    current_user: User = Depends(deps.get_current_user),
    default_ai_service: AIService = Depends(deps.get_ai_service),
    db: Session = Depends(deps.get_db)
):
    """
    Train RAG with Correct SQL
    - Admins: Validates & Trains immediately (Active).
    - Users: Submits for review (Inactive).
    """
    try:
        # 1. Validate SQL integrity first (for everyone)
        # We need to run the SQL to make sure it's valid SQLite/SQL
        mcp_client = deps.get_mcp_client(current_request)
        try:
            # Dry run / Explain to check syntax
            # Or just run with limit 1
            check_res = await mcp_client.call_tool("execute_query", {"sql": request.sql, "limit": 1})
            # If string error or dict with error
            if isinstance(check_res, dict) and check_res.get('error'):
                 raise ValueError(f"Invalid SQL: {check_res['error']}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid SQL: {str(e)}")

        # 2. Check Permissions
        is_admin = getattr(current_user, 'is_superuser', False) or getattr(current_user, 'role', '') == 'admin'
        
        # 3. Save to Database (GoldenExample)
        # Check if already exists? (Maybe duplicate question pattern)
        existing = db.query(GoldenExample).filter(GoldenExample.question_pattern == request.question).first()
        
        if existing:
            # Update existing
            existing.expected_sql = request.sql
            existing.is_active = is_admin # If admin, auto-active. If user, needs review (unless updating their own?)
            existing.updated_at = datetime.utcnow() # Need datetime import or func.now
            if is_admin:
                existing.added_by = current_user.id
            db_item = existing
        else:
            # Create new
            db_item = GoldenExample(
                question_pattern=request.question,
                expected_sql=request.sql,
                category=request.context,
                is_active=is_admin, # Admin = Active, User = Pending
                added_by=current_user.id
            )
            db.add(db_item)
        
        db.commit()
        db.refresh(db_item)

        if is_admin:
            # Power User: Train Vanna immediately
            success = default_ai_service.train(request.question, request.sql)
            if success:
                return {"success": True, "message": "Admin: System trained and saved successfully"}
            else:
                # DB saved but Vanna failed?
                return {"success": True, "message": "Saved to DB, but Vector training failed (check logs)"}
        else:
            # Standard User: Queue for review
            return {"success": True, "message": "Suggestion submitted for review. Thank you!"}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

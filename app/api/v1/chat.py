from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import time

from app.api import deps
from app.models.user import User
from app.models.chat import ChatHistory
from app.schemas.chat import ChatRequest, ChatResponse, DataWarning
from app.services.ai_service import AIService

router = APIRouter()


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

    Args:
        data: Query result data
        sql_query: The SQL query used (for additional context)

    Returns:
        List of DataWarning objects
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

@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    # AI Service will be created dynamically based on request.provider
    # ai_service: AIService = Depends(deps.get_ai_service) 
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
        for chat in reversed(previous_chats):
            if chat.question:
                history.append({"role": "user", "content": chat.question})
            if chat.ai_response:
                history.append({"role": "assistant", "content": chat.ai_response})
    
    # 3. Instantiate AI Service based on provider
    from app.services.ai_service import create_gemini_service, create_claude_service, create_matcha_service
    from app.config import settings
    from app.services.prompt_manager import PromptManager
    
    prompt_manager = PromptManager(db)
    
    provider = request.provider or settings.AI_PROVIDER
    
    if provider == "claude":
        if not settings.ANTHROPIC_API_KEY:
             raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        
        # Get DB path
        if "sqlite" in settings.DATABASE_URL:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        else:
            db_path = "nt_fi_report.sqlite"
            
        ai_service = create_claude_service(
            api_key=settings.ANTHROPIC_API_KEY,
            db_path=db_path,
            model=settings.CLAUDE_MODEL,
            prompt_manager=prompt_manager
        )
    elif provider == "gemini":
        if not settings.GOOGLE_AI_API_KEY:
             raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
             
        # Get DB path (helper could be extracted)
        if "sqlite" in settings.DATABASE_URL:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        else:
            db_path = "nt_fi_report.sqlite"
            
        ai_service = create_gemini_service(
            api_key=settings.GOOGLE_AI_API_KEY,
            db_path=db_path,
            model=settings.GEMINI_MODEL,
            prompt_manager=prompt_manager
        )
    elif provider == "matcha":
        if not settings.MATCHA_AI_API_KEY or not settings.MATCHA_API_URL:
             raise HTTPException(status_code=500, detail="MATCHA configuration missing (KEY or URL)")
             
        # Get DB path
        if "sqlite" in settings.DATABASE_URL:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        else:
            db_path = "nt_fi_report.sqlite"
            
        ai_service = create_matcha_service(
            api_key=settings.MATCHA_AI_API_KEY,
            api_url=settings.MATCHA_API_URL,
            db_path=db_path,
            model=settings.MATCHA_MODEL,
            prompt_manager=prompt_manager
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # 4. Call AI Service with retry mechanism
    import logging
    logger = logging.getLogger(__name__)

    # Use query_with_retry for automatic self-correction
    result = ai_service.query_with_retry(
        question=request.question,
        max_retries=request.max_retries,
        history=history,
        on_status=lambda status: logger.info(
            f"Retry status: attempt={status.attempt}/{status.max_attempts}, "
            f"status={status.status}, message={status.message}"
        ),
        explain=True
    )

    execution_time = (time.time() - start_time) * 1000

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
    warnings_response = None
    if result.data:
        detected_warnings = detect_data_warnings(result.data, result.sql_query)
        if detected_warnings:
            warnings_response = [
                {"code": w.code, "message": w.message, "severity": w.severity}
                for w in detected_warnings
            ]

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

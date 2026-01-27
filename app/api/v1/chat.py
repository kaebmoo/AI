from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import time

from app.api import deps
from app.models.user import User
from app.models.chat import ChatHistory
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import AIService

router = APIRouter()

@router.post("/", response_model=ChatResponse)
async def chat(
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
    from app.services.ai_service import create_gemini_service, create_claude_service
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
            db_path = "nt_revenue.sqlite"
            
        ai_service = create_claude_service(
            api_key=settings.ANTHROPIC_API_KEY,
            db_path=db_path,
            model=settings.CLAUDE_MODEL,
            prompt_manager=prompt_manager
        )
    elif provider == "gemini":
        if not settings.GOOGLE_AI_API_KEY:
             raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
             
        # Get DB path
        if "sqlite" in settings.DATABASE_URL:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        else:
            db_path = "nt_revenue.sqlite"
            
        ai_service = create_gemini_service(
            api_key=settings.GOOGLE_AI_API_KEY,
            db_path=db_path,
            model=settings.GEMINI_MODEL,
            prompt_manager=prompt_manager
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # 4. Call AI Service with history
    result = ai_service.query(request.question, history=history)
    
    execution_time = (time.time() - start_time) * 1000
    
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
    
    if result.error:
         # Depending on requirement, might want to return 400 or just the error message in answer
         pass

    return {
        "id": chat_entry.id,
        "conversation_id": conversation_id,
        "question": result.question,
        "answer": chat_entry.ai_response,
        "sql_query": result.sql_query,
        "data": result.data,
        "execution_time_ms": execution_time
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

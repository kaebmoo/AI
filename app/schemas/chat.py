from pydantic import BaseModel
from typing import Optional, List, Any, Dict

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    
class ChatResponse(BaseModel):
    id: int
    conversation_id: Optional[str] = None
    question: str
    answer: str
    sql_query: Optional[str]
    data: Optional[List[Dict[str, Any]]] = None
    execution_time_ms: float

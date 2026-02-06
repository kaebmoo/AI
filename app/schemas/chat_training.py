
from pydantic import BaseModel
from typing import Optional

class TrainingRequest(BaseModel):
    question: str
    sql: str
    context: Optional[str] = "revenue"

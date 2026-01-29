from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.api import deps
from app.services.ai_service import AIService
from app.services.analyzer_service import AnalyzerService
from pydantic import BaseModel

router = APIRouter()

class AnalysisResponse(BaseModel):
    source: str
    columns: List[Dict[str, Any]]
    suggestions: Optional[Dict[str, Any]] = None

@router.post("/analyze/file", response_model=AnalysisResponse)
async def analyze_file(
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    # Assuming we get provider from settings or request
):
    """
    Upload a CSV/Excel file and get schema analysis + AI suggestions.
    """
    # Initialize services
    # For now, we use default provider from settings (handled inside AIService init if not passed)
    # Ideally should come from dependency injection or settings
    from app.config import settings
    
    try:
        ai_service = AIService(
            provider=settings.AI_PROVIDER,
            api_key=settings.AI_API_KEY,  # This might need better handling if keys are per user or rotated
            db_path=settings.DB_PATH,  # Or logic to pick correct DB
            api_url=settings.MATCHA_API_URL if settings.AI_PROVIDER == 'matcha' else None
        )
        
        analyzer = AnalyzerService(db, ai_service)
        
        # Read file content
        content = await file.read()
        
        # 1. Basic Analysis
        basic_info = analyzer.analyze_file(content, file.filename)
        
        # 2. AI Suggestions
        ai_suggestions = await analyzer.get_ai_suggestions(basic_info)
        
        # Merge results logic if needed, or just return them structured
        # The analyzer.get_ai_suggestions returns the JSON structure we want
        
        return {
            "source": basic_info['source'],
            "columns": basic_info['columns'],
            "suggestions": ai_suggestions
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/analyze/table", response_model=AnalysisResponse)
async def analyze_table(
    table_name: str = Form(...),
    db: Session = Depends(deps.get_db)
):
    """
    Analyze an existing database table.
    """
    from app.config import settings
    try:
        ai_service = AIService(
            provider=settings.AI_PROVIDER,
            api_key=settings.AI_API_KEY,
            db_path=settings.DB_PATH,
             api_url=settings.MATCHA_API_URL if settings.AI_PROVIDER == 'matcha' else None
        )
        
        analyzer = AnalyzerService(db, ai_service)
        
        # 1. Basic Analysis
        basic_info = analyzer.analyze_database_table(table_name)
        
        # 2. AI Suggestions
        ai_suggestions = await analyzer.get_ai_suggestions(basic_info)
        
        return {
            "source": basic_info['source'],
            "columns": basic_info['columns'],
            "suggestions": ai_suggestions
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

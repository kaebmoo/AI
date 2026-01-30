import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.db import base # Import to register all models
from app.services.ai_service import create_gemini_service, create_claude_service
from app.db.session import SessionLocal
from app.services.prompt_manager import PromptManager

def test_ai():
    print("Testing AI Service Integration (with PromptManager)...")
    
    # Check config
    print(f"Provider: {settings.AI_PROVIDER}")
    
    # Initialize DB for PromptManager
    try:
        db = SessionLocal()
        prompt_manager = PromptManager(db)
        print("PromptManager initialized.")
    except Exception as e:
        print(f"Warning: Could not initialize Database/PromptManager: {e}")
        print("Running without PromptManager...")
        prompt_manager = None

    service = None

    if settings.AI_PROVIDER == "gemini":
        api_key = settings.GOOGLE_AI_API_KEY
        if not api_key:
            print("ERROR: GOOGLE_AI_API_KEY not found")
            return
            
        print(f"Model: {settings.GEMINI_MODEL}")
        service = create_gemini_service(
            api_key, 
            db_path="nt_fi_report.sqlite",
            model=settings.GEMINI_MODEL,
            prompt_manager=prompt_manager
        )
        
    elif settings.AI_PROVIDER == "claude":
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
             print("ERROR: ANTHROPIC_API_KEY not found")
             return
        print(f"Model: {settings.CLAUDE_MODEL}")
        service = create_claude_service(
            api_key, 
            db_path="nt_fi_report.sqlite",
            model=settings.CLAUDE_MODEL,
            prompt_manager=prompt_manager
        )
    else:
        print(f"Unknown provider: {settings.AI_PROVIDER}")
        return

    # Check System Prompt
    print("\n--- System Prompt Preview ---")
    print(service.system_prompt[:500] + "...")
    print("-----------------------------\n")

    # Test Query
    # question = "รายได้รวมเดือนมกราคม 2025"
    question = "รายได้รวม ของบริการ fixed line โดยสรุปเป็นรายไตรมาส"
    print(f"Question: {question}")
    
    try:
        result = service.query(question)
        print(f"SQL: {result.sql_query}")
        print(f"Explanation: {result.explanation}")
        
        if result.error:
            print(f"Error: {result.error}")
        else:
            print("Success!")
            
    except Exception as e:
        print(f"Exception: {str(e)}")
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    test_ai()

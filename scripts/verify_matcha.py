
import sys
import os
import asyncio
from dotenv import load_dotenv

# Add app to path
sys.path.append(os.getcwd())
load_dotenv()

from app.services.ai_service import create_matcha_service

async def verify_matcha():
    print("Verifying Matcha AI Integration...\n")
    
    api_key = os.getenv("MATCHA_AI_API_KEY")
    api_url = os.getenv("MATCHA_API_URL")
    
    if not api_key or not api_url:
        print("❌ Missing configuration in .env")
        return

    print(f"URL: {api_url}")
    print(f"Key: {api_key[:5]}...")

    try:
        service = create_matcha_service(api_key=api_key, api_url=api_url)
        print("✅ Service initialized")
        
        question = "ขอรายได้รวมเดือนมกราคม 2568"
        print(f"\nSending Query: {question}")
        
        # Test Query
        result = service.query(question)
        
        print("\n[Result]")
        print(f"SQL: {result.sql_query}")
        print(f"Explanation: {result.explanation[:100]}...")
        print(f"Provider: {result.provider}")
        
        if result.sql_query:
            print("✅ SQL Generation Successful")
        else:
            print("❌ SQL Generation Failed (Empty)")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_matcha())

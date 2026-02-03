
import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock AIService to avoid dependency hell if env is broken, 
# BUT we want to test the PROMPT logic if possible. 
# If imports fail, we might need to rely on code analysis.
try:
    from app.services.ai_service import AIService
except ImportError:
    print("⚠️ Could not import AIService (dependency issue). Checks will be limited.")
    AIService = None

# Load env
load_dotenv()

async def test_visualization_logic():
    print("🧪 Testing AI Visualization Logic (User Scenario)...")
    
    if not AIService:
        print("❌ Skpping test due to missing dependencies.")
        return

    # Mock MCP Client (Not needed for explain_result)
    class MockMCPClient:
        pass
    
    mcp_client = MockMCPClient()
    
    # Load Credentials
    # Fallback to Claude if no keys found, assuming user has env var, or check .env
    provider = "claude"
    api_key = os.getenv("ANTHROPIC_API_KEY") 
    
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY not found. Trying Gemini...")
        provider = "gemini"
        api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        print("❌ No API Keys found in env. Cannot run live test.")
        # We can simulate the output if we just want to test the parsing logic, 
        # but here we want to test the AI's *decision* which requires the API.
        return

    print(f"🔹 Using Provider: {provider}")

    try:
        ai_service = AIService(
            provider=provider,
            api_key=api_key,
            mcp_client=mcp_client
        )
    except Exception as e:
        print(f"❌ Failed to init AIService: {e}")
        return
    
    # User Scenario: Expenses by Account Group by Month (EXACT USER QUERY)
    question = "ขอค่าใช้จ่ายรายหมวดบัญชี แบบรายเดือน"
    sql = """
    SELECT 
        year,
        printf('%02d', CAST(month AS INTEGER)) AS month,
        account_group_name,
        SUM(expense) AS total_expense
    FROM v_expense_mart
    GROUP BY year, month, account_group_name
    ORDER BY year, CAST(month AS INTEGER), account_group_name
    """
    
    import sqlite3
    db_path = "/Users/seal/Documents/GitHub/AI/nt_fi_report.sqlite"
    
    print(f"🔹 Connecting to DB: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        
        # Convert Row objects to dicts
        data = [dict(row) for row in rows]
        
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    if not data:
        print("❌ No data returned from query. Check SQL or DB content.")
        return

    system_prompt = """
    You are an AI assistant.
    Analyze the data and recommend the best visualization.
    """
    
    print(f"\n📝 Question: {question}")
    print(f"📊 Real Data Count: {len(data)}")
    print(f"📊 Sample Row: {json.dumps(data[0] if data else {}, ensure_ascii=False)}")
    
    try:
        # Call the actual Explain Result function
        result = await ai_service.explain_result(
            question=question,
            sql=sql,
            data=data,
            system_prompt=system_prompt
        )
        
        print("\n✅ AI Response (Raw):")
        print(result)

        if isinstance(result, str):
            try:
                 # Try to parse if it returned a string
                 result = json.loads(result)
            except:
                 pass

        if isinstance(result, dict):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # Validation
            viz = result.get('visualization')
            config = result.get('chart_config', {})
            
            print("\n🔍 Validation:")
            print(f"- Visualization: {viz}")
            print(f"- Chart Config: {config}")
            
            if viz in ['grouped_bar', 'stacked_bar', 'multi_line']:
                print("  -> ✅ GOOD: Recommended multi-series chart")
            else:
                 print(f"  -> ⚠️ WARNING: {viz} might be too simple for this data")
                 
            cat = config.get('category_column')
            series = config.get('series_column')
            
            # We want Month as Category (X-axis) and Section as Series (Legend)
            if cat in ['month', 'year'] and series == 'section':
                print("  -> ✅ EXCELLENT: Time on X-axis, Section as Series")
            elif cat == 'section' and series in ['month', 'year']:
                 print("  -> ⚠️ ACCEPTABLE: Section on X-axis, Time as Series (Comparison by Section)")
            else:
                print(f"  -> ❓ CHECK: ({cat} vs {series})")
                
        else:
            print("❌ Result is not JSON:")
            print(result)
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_visualization_logic())

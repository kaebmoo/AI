# /Users/seal/Documents/GitHub/AI/example_usage.py
#!/usr/bin/env python3
"""
NT AI Assistant - Example Usage
Updated version for current project structure
"""

import os
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.schema_service import SchemaService
from app.services.database_service import DatabaseService
from app.services.ai_service import AIService
from app.services.matcha_examples import MatchaExamplesService

def print_header(title: str):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"{title:^60}")
    print("="*60)

def example_schema_service():
    """Example using SchemaService with current database"""
    print_header("Example: SchemaService")
    
    # Initialize services
    db_path = project_root / "nt_fi_report.sqlite"
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("Please ensure nt_fi_report.sqlite exists in project root")
        return
    
    service = SchemaService(db_path=str(db_path))
    
    print("1. Available Tables:")
    tables = service.get_tables()
    for table in tables:
        print(f"   - {table}")
    
    print("\n2. Revenue Table Schema:")
    try:
        columns = service.get_table_columns("revenue_search")
        print(f"   Found {len(columns)} columns in revenue_search:")
        for col in columns[:10]:  # Show first 10
            print(f"   - {col['name']}: {col['type']}")
        if len(columns) > 10:
            print(f"   ... and {len(columns) - 10} more")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n3. Sample Business Rules:")
    rules = service.get_business_rules()
    for rule in rules[:3]:
        print(f"   - {rule['rule_name']}: {rule['rule_description']}")
    
    print("\n4. Semantic Mappings:")
    mappings = service.get_semantic_mappings()
    for mapping in mappings[:5]:
        print(f"   - {mapping['keyword']} → {mapping['target_condition']}")
    
    print("\n5. Sample Values:")
    try:
        samples = service.get_sample_values("revenue_search", "BUSINESS_GROUP")
        print(f"   Sample BUSINESS_GROUP values: {samples[:5]}")
    except Exception as e:
        print(f"   Error getting samples: {e}")

def example_database_service():
    """Example using DatabaseService"""
    print_header("Example: DatabaseService")
    
    db_path = project_root / "nt_fi_report.sqlite"
    if not db_path.exists():
        print("❌ Database not found")
        return
    
    db_service = DatabaseService(db_path=str(db_path))
    
    # Test connection
    if db_service.test_connection():
        print("✅ Database connection successful")
        
        # Get table info
        info = db_service.get_table_info("revenue_search")
        print(f"📊 Table: revenue_search")
        print(f"   Rows: {info.get('row_count', 'N/A')}")
        print(f"   Columns: {len(info.get('columns', []))}")
        
        # Sample query
        sample_query = "SELECT COUNT(*) as total_records FROM revenue_search"
        result = db_service.execute_query(sample_query)
        if result:
            print(f"   Total records: {result[0]['total_records']}")
    else:
        print("❌ Database connection failed")

def example_ai_service():
    """Example using AIService"""
    print_header("Example: AIService")
    
    # Check for API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GOOGLE_API_KEY")
    
    if not anthropic_key and not gemini_key:
        print("⚠️  No API keys found")
        print("Set ANTHROPIC_API_KEY or GOOGLE_API_KEY environment variables")
        return
    
    # Initialize AI service
    db_path = project_root / "nt_fi_report.sqlite"
    ai_service = AIService(
        db_path=str(db_path),
        use_claude=bool(anthropic_key),
        use_gemini=bool(gemini_key)
    )
    
    # Test with sample question
    test_questions = [
        "รายได้รวมเดือนมกราคม 2568",
        "กลุ่มธุรกิจไหนมีรายได้มากที่สุด 5 อันดับแรก"
    ]
    
    for question in test_questions:
        print(f"\n🤖 Testing: {question}")
        try:
            response = ai_service.process_question(question)
            print(f"   ✅ SQL: {response.get('sql', 'N/A')}")
            print(f"   📊 Result: {len(response.get('results', []))} records")
            print(f"   💬 Explanation: {response.get('explanation', 'N/A')[:100]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")

def example_golden_examples():
    """Example using Golden Examples"""
    print_header("Example: Golden Examples")
    
    db_path = project_root / "nt_fi_report.sqlite"
    examples_service = MatchaExamplesService(db_path=str(db_path))
    
    examples = examples_service.get_golden_examples()
    print(f"📚 Found {len(examples)} golden examples")
    
    for i, example in enumerate(examples[:3]):
        print(f"\n   Example {i+1}:")
        print(f"   Question: {example['question_pattern']}")
        print(f"   SQL Preview: {example['expected_sql'][:80]}...")

def check_requirements():
    """Check if all requirements are met"""
    print_header("System Check")
    
    # Check database
    db_path = project_root / "nt_fi_report.sqlite"
    print(f"📁 Database: {'✅' if db_path.exists() else '❌'} {db_path}")
    
    # Check environment variables
    required_env = ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
    for env in required_env:
        value = os.getenv(env)
        print(f"🔑 {env}: {'✅' if value else '❌'}")
    
    # Check Python packages
    try:
        import anthropic
        print("📦 anthropic: ✅")
    except ImportError:
        print("📦 anthropic: ❌ (pip install anthropic)")
    
    try:
        import google.generativeai as genai
        print("📦 google-generativeai: ✅")
    except ImportError:
        print("📦 google-generativeai: ❌ (pip install google-generativeai)")

def main():
    """Main function"""
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║         NT AI Assistant - Example Usage              ║")
    print("╠═══════════════════════════════════════════════════════════╣")
    print("║  This script demonstrates how to use the AI services      ║")
    print("║  with both Claude (Anthropic) and Gemini (Google) APIs    ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    # Check system requirements first
    check_requirements()
    
    try:
        example_schema_service()
    except Exception as e:
        print(f"SchemaService error: {e}")
    
    try:
        example_database_service()
    except Exception as e:
        print(f"DatabaseService error: {e}")
    
    try:
        example_ai_service()
    except Exception as e:
        print(f"AIService error: {e}")
    
    try:
        example_golden_examples()
    except Exception as e:
        print(f"GoldenExamples error: {e}")
    
    print("\n" + "="*60)
    print("Demo completed! 🎉")
    print("="*60)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
NT AI Assistant - Example Usage
=====================================

ตัวอย่างการใช้งาน AI Service ทั้ง Claude และ Gemini
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.schema_service import SchemaService
from app.services.ai_service import AIService, create_claude_service, create_gemini_service


def example_schema_service():
    """ตัวอย่างการใช้ SchemaService"""
    
    print("=" * 60)
    print("Example: SchemaService")
    print("=" * 60)
    
    # Create service
    service = SchemaService(db_path="revenue.db")
    
    # Get table info
    print("\n1. Table Info (from PRAGMA):")
    columns = service.get_table_info("revenue")
    for col in columns[:5]:
        print(f"   - {col['name']}: {col['type']}")
    print(f"   ... และอีก {len(columns) - 5} columns")
    
    # Detect date format
    print(f"\n2. Date Format: {service.get_date_format()}")
    
    # Build system prompt
    print("\n3. System Prompt (first 500 chars):")
    prompt = service.build_system_prompt(ai_provider="claude")
    print(prompt[:500] + "...")
    
    # Get sample values
    print("\n4. Sample Values:")
    samples = service.get_sample_values()
    for key, values in samples.items():
        if key != 'DATA_RANGE' and values:
            print(f"   {key}: {values[:3]}...")


def example_claude_service():
    """ตัวอย่างการใช้ Claude API"""
    
    print("\n" + "=" * 60)
    print("Example: Claude API")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY not set. Skipping Claude example.")
        print("   Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        return
    
    # Create service
    service = create_claude_service(api_key=api_key, db_path="revenue.db")
    
    # Example queries
    questions = [
        "รายได้รวมเดือนมกราคม 2568",
        "รายได้แยกตามกลุ่มธุรกิจ",
        "Top 5 สายงานที่มีรายได้สูงสุด"
    ]
    
    for q in questions:
        print(f"\n📝 Question: {q}")
        result = service.query(q)
        
        if result.error:
            print(f"   ❌ Error: {result.error}")
        else:
            print(f"   SQL: {result.sql_query}")
            print(f"   Rows: {len(result.data)}")
            print(f"   Tokens: {result.tokens_used}")
            if result.data:
                print(f"   Sample: {result.data[0]}")


def example_gemini_service():
    """ตัวอย่างการใช้ Gemini API"""
    
    print("\n" + "=" * 60)
    print("Example: Google Gemini API")
    print("=" * 60)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        print("⚠️ GOOGLE_API_KEY not set. Skipping Gemini example.")
        print("   Set it with: export GOOGLE_API_KEY=AIza...")
        return
    
    # Create service
    service = create_gemini_service(api_key=api_key, db_path="revenue.db")
    
    # Example query
    question = "รายได้รวมเดือนมกราคม 2568"
    
    print(f"\n📝 Question: {question}")
    result = service.query(question)
    
    if result.error:
        print(f"   ❌ Error: {result.error}")
    else:
        print(f"   SQL: {result.sql_query}")
        print(f"   Rows: {len(result.data)}")
        print(f"   Explanation: {result.explanation[:200]}...")


def example_compare_providers():
    """เปรียบเทียบ Claude vs Gemini"""
    
    print("\n" + "=" * 60)
    print("Example: Compare Claude vs Gemini")
    print("=" * 60)
    
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GOOGLE_API_KEY")
    
    if not claude_key or not gemini_key:
        print("⚠️ Need both ANTHROPIC_API_KEY and GOOGLE_API_KEY for comparison")
        return
    
    question = "รายได้รวมแยกตามสายงาน เดือนมกราคม 2568"
    
    # Claude
    print(f"\n📝 Question: {question}")
    print("\n--- Claude ---")
    claude_service = create_claude_service(claude_key, "revenue.db")
    claude_result = claude_service.query(question)
    print(f"SQL: {claude_result.sql_query}")
    print(f"Tokens: {claude_result.tokens_used}")
    
    # Gemini
    print("\n--- Gemini ---")
    gemini_service = create_gemini_service(gemini_key, "revenue.db")
    gemini_result = gemini_service.query(question)
    print(f"SQL: {gemini_result.sql_query}")
    print(f"Tokens: {gemini_result.tokens_used}")


def main():
    """Run all examples"""
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║         NT AI Assistant - Example Usage              ║
    ╠═══════════════════════════════════════════════════════════╣
    ║  This script demonstrates how to use the AI services      ║
    ║  with both Claude (Anthropic) and Gemini (Google) APIs    ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check if database exists
    if not Path("revenue.db").exists():
        print("⚠️ revenue.db not found. Please create the database first.")
        print("   Example: Create from CSV using KNIME or Python")
        return
    
    # Run examples
    example_schema_service()
    example_claude_service()
    example_gemini_service()
    # example_compare_providers()  # Uncomment to compare


if __name__ == "__main__":
    main()

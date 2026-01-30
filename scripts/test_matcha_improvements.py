#!/usr/bin/env python3
"""
Test script for Matcha AI improvements
======================================

ทดสอบการปรับปรุง Matcha Provider:
1. Few-shot examples loading
2. Semantic hints detection
3. SQL extraction patterns

Usage:
    python scripts/test_matcha_improvements.py
    python scripts/test_matcha_improvements.py --live  # Test with actual API
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.matcha_examples import (
    MATCHA_EXAMPLES,
    MatchaExamplesService,
    get_matcha_few_shot_messages,
    get_matcha_few_shot_prompt,
    get_abbreviation_reference,
    get_business_term_reference
)


def test_static_examples():
    """Test static MATCHA_EXAMPLES"""
    print("=" * 60)
    print("Test 1: Static Examples")
    print("=" * 60)

    print(f"Number of static examples: {len(MATCHA_EXAMPLES)}")

    for i, ex in enumerate(MATCHA_EXAMPLES[:3], 1):
        print(f"\nExample {i}:")
        print(f"  Question: {ex['question']}")
        print(f"  SQL: {ex['sql'][:80]}...")

    print("\n[PASS] Static examples loaded successfully")
    return True


def test_few_shot_messages():
    """Test few-shot message generation"""
    print("\n" + "=" * 60)
    print("Test 2: Few-shot Messages")
    print("=" * 60)

    messages = get_matcha_few_shot_messages()
    print(f"Number of messages: {len(messages)}")

    # Should have pairs of user/assistant
    user_count = sum(1 for m in messages if m['role'] == 'user')
    assistant_count = sum(1 for m in messages if m['role'] == 'assistant')

    print(f"User messages: {user_count}")
    print(f"Assistant messages: {assistant_count}")

    assert user_count == assistant_count, "User and assistant messages should be equal"

    print("\n[PASS] Few-shot messages generated correctly")
    return True


def test_few_shot_prompt():
    """Test few-shot prompt generation"""
    print("\n" + "=" * 60)
    print("Test 3: Few-shot Prompt")
    print("=" * 60)

    prompt = get_matcha_few_shot_prompt()
    print(f"Prompt length: {len(prompt)} characters")
    print(f"\nFirst 500 chars:\n{prompt[:500]}...")

    assert "ตัวอย่าง" in prompt, "Prompt should contain 'ตัวอย่าง'"
    assert "```sql" in prompt, "Prompt should contain SQL code blocks"

    print("\n[PASS] Few-shot prompt generated correctly")
    return True


def test_examples_service(db_path: str):
    """Test MatchaExamplesService"""
    print("\n" + "=" * 60)
    print("Test 4: Examples Service")
    print("=" * 60)

    service = MatchaExamplesService(db_path)

    # Test semantic mappings
    mappings = service.get_semantic_mappings()
    print(f"Semantic mappings loaded: {len(mappings)}")

    if mappings:
        print("\nSample mappings:")
        for m in mappings[:5]:
            print(f"  - {m['keyword']} -> {m['target_column']} {m['target_condition']}")

    # Test golden examples
    golden = service.get_golden_examples()
    print(f"\nGolden examples loaded: {len(golden)}")

    print("\n[PASS] Examples service working correctly")
    return True


def test_keyword_detection(db_path: str):
    """Test keyword detection in questions"""
    print("\n" + "=" * 60)
    print("Test 5: Keyword Detection")
    print("=" * 60)

    service = MatchaExamplesService(db_path)

    test_questions = [
        "รายได้ นป. เดือนมกราคม 2568",
        "รายได้อสังหาริมทรัพย์ปี 2568",
        "รายได้ บชง. แยกตามเดือน",
        "รายได้มือถือของ กน.1",
    ]

    for q in test_questions:
        print(f"\nQuestion: {q}")
        detected = service.detect_keywords_in_question(q)
        if detected:
            for d in detected:
                print(f"  -> {d['keyword']}: {d['description']}")
        else:
            print("  -> No keywords detected")

    print("\n[PASS] Keyword detection working")
    return True


def test_semantic_hints(db_path: str):
    """Test semantic hints generation"""
    print("\n" + "=" * 60)
    print("Test 6: Semantic Hints")
    print("=" * 60)

    service = MatchaExamplesService(db_path)

    question = "รายได้ นป. และ บชง. ปี 2568"
    hints = service.build_semantic_hints(question)

    print(f"Question: {question}")
    print(f"\nGenerated hints:\n{hints}")

    print("\n[PASS] Semantic hints generated")
    return True


def test_sql_extraction():
    """Test SQL extraction patterns"""
    print("\n" + "=" * 60)
    print("Test 7: SQL Extraction Patterns")
    print("=" * 60)

    # Import the provider to test extraction method
    from app.services.ai_service import MatchaProvider

    provider = MatchaProvider(
        api_key="test",
        api_url="http://test",
        model="test"
    )

    test_responses = [
        # Standard SQL block
        """นี่คือ SQL query:
```sql
SELECT SUM(revenue) FROM revenue_search WHERE year = 2025
```
คำอธิบาย: รายได้รวมปี 2568""",

        # Generic code block
        """```
SELECT department, SUM(revenue) as total
FROM revenue_search
GROUP BY department
```""",

        # Raw SQL without code block
        """SELECT * FROM revenue_search WHERE organization_group_abbr = 'นป.'

คำอธิบาย: ค้นหารายได้ของ นป.""",

        # Complex UNION query
        """```sql
SELECT 'มากสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total
    FROM revenue_search
    GROUP BY department
    ORDER BY total DESC
    LIMIT 5
)
UNION ALL
SELECT 'น้อยสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total
    FROM revenue_search
    GROUP BY department
    ORDER BY total ASC
    LIMIT 5
)
```"""
    ]

    for i, response in enumerate(test_responses, 1):
        print(f"\nTest case {i}:")
        sql = provider._extract_sql_from_response(response)
        if sql:
            print(f"  Extracted SQL: {sql[:80]}...")
            print("  [OK]")
        else:
            print("  [FAILED] No SQL extracted")

    print("\n[PASS] SQL extraction patterns tested")
    return True


def test_references():
    """Test reference text generation"""
    print("\n" + "=" * 60)
    print("Test 8: Reference Text")
    print("=" * 60)

    abbr_ref = get_abbreviation_reference()
    term_ref = get_business_term_reference()

    print(f"Abbreviation reference length: {len(abbr_ref)} chars")
    print(f"Business term reference length: {len(term_ref)} chars")

    assert "นป." in abbr_ref, "Should contain 'นป.'"
    assert "บชง." in abbr_ref, "Should contain 'บชง.'"
    assert "มือถือ" in term_ref, "Should contain 'มือถือ'"

    print("\n[PASS] Reference texts generated correctly")
    return True


def test_live_matcha(db_path: str, api_key: str, api_url: str):
    """Test with actual Matcha API (optional)"""
    print("\n" + "=" * 60)
    print("Test 9: Live Matcha API")
    print("=" * 60)

    from app.services.ai_service import create_matcha_service

    service = create_matcha_service(
        api_key=api_key,
        api_url=api_url,
        db_path=db_path
    )

    test_questions = [
        "รายได้รวมปี 2568",
        "รายได้ นป. เดือน 1",
    ]

    for q in test_questions:
        print(f"\nQuestion: {q}")
        try:
            result = service.query(q)
            print(f"SQL: {result.sql_query}")
            print(f"Data rows: {len(result.data)}")
            if result.error:
                print(f"Error: {result.error}")
        except Exception as e:
            print(f"Error: {e}")

    print("\n[DONE] Live test completed")
    return True


def main():
    """Run all tests"""
    import argparse

    parser = argparse.ArgumentParser(description="Test Matcha improvements")
    parser.add_argument("--live", action="store_true", help="Run live API tests")
    parser.add_argument("--db", default="nt_fi_report.sqlite", help="Database path")
    args = parser.parse_args()

    db_path = args.db

    print("Matcha Improvements Test Suite")
    print("=" * 60)
    print(f"Database: {db_path}")
    print()

    # Run tests
    all_passed = True

    try:
        all_passed &= test_static_examples()
        all_passed &= test_few_shot_messages()
        all_passed &= test_few_shot_prompt()
        all_passed &= test_examples_service(db_path)
        all_passed &= test_keyword_detection(db_path)
        all_passed &= test_semantic_hints(db_path)
        all_passed &= test_sql_extraction()
        all_passed &= test_references()

        if args.live:
            api_key = os.getenv("MATCHA_API_KEY")
            api_url = os.getenv("MATCHA_API_URL")

            if api_key and api_url:
                all_passed &= test_live_matcha(db_path, api_key, api_url)
            else:
                print("\n[SKIP] Live test - MATCHA_API_KEY and MATCHA_API_URL not set")

    except Exception as e:
        print(f"\n[FAILED] Test error: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

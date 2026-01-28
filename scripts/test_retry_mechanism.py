#!/usr/bin/env python3
"""
Test script for AI Service retry mechanism.

Simulates cases where AI generates invalid SQL and needs to self-correct.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import RetryStatus


def print_status(status: RetryStatus):
    """Print status update to console"""
    status_icons = {
        "generating": "🔄",
        "executing": "⚙️",
        "error": "❌",
        "retrying": "🔁",
        "success": "✅",
        "failed": "💀"
    }
    icon = status_icons.get(status.status, "❓")
    print(f"\n{icon} [{status.attempt}/{status.max_attempts}] {status.status.upper()}")
    print(f"   Message: {status.message}")
    if status.sql_query:
        sql_preview = status.sql_query[:100] + "..." if len(status.sql_query) > 100 else status.sql_query
        print(f"   SQL: {sql_preview}")
    if status.error:
        print(f"   Error: {status.error}")


def test_retry_with_matcha():
    """Test retry mechanism with Matcha provider"""
    from app.config import settings
    from app.services.ai_service import create_matcha_service

    if not settings.MATCHA_AI_API_KEY:
        print("❌ MATCHA_AI_API_KEY not configured")
        return

    print("=" * 60)
    print("Testing Retry Mechanism with Matcha Provider")
    print("=" * 60)

    # Get correct DB path from settings
    if "sqlite" in settings.DATABASE_URL:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    else:
        db_path = "nt_revenue.sqlite"
    print(f"Using database: {db_path}")

    service = create_matcha_service(
        api_key=settings.MATCHA_AI_API_KEY,
        api_url=settings.MATCHA_API_URL,
        db_path=db_path,
        model=settings.MATCHA_MODEL
    )

    # Test case: Question that might cause AI to use non-existent column
    test_questions = [
        "รายได้ nt broadband ของ อป.1 แยกเป็นรายจังหวัดเป็นเท่าไหร่",  # province doesn't exist
        "รายได้ mobile แยกตามภูมิภาค",  # region doesn't exist
        "รายได้รวม อป.1 ปี 2568",  # should work normally
    ]

    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print("=" * 60)

        result = service.query_with_retry(
            question=question,
            max_retries=3,
            on_status=print_status,
            explain=True
        )

        print("\n" + "-" * 40)
        print("FINAL RESULT:")
        print(f"  Success: {result.error is None}")
        print(f"  Retry Count: {result.retry_count}")
        print(f"  SQL: {result.sql_query[:200] if result.sql_query else 'None'}...")
        print(f"  Data Rows: {len(result.data)}")
        if result.error:
            print(f"  Error: {result.error}")

        if result.retry_history:
            print(f"\n  Retry History ({len(result.retry_history)} attempts):")
            for r in result.retry_history:
                print(f"    - Attempt {r['attempt']}: {r['error_type']} - {r['error'][:50]}...")


def test_retry_with_gemini():
    """Test retry mechanism with Gemini provider"""
    from app.config import settings
    from app.services.ai_service import create_gemini_service

    if not settings.GOOGLE_AI_API_KEY:
        print("❌ GOOGLE_AI_API_KEY not configured")
        return

    print("=" * 60)
    print("Testing Retry Mechanism with Gemini Provider")
    print("=" * 60)

    service = create_gemini_service(
        api_key=settings.GOOGLE_AI_API_KEY,
        db_path="revenue.db",
        model=settings.GEMINI_MODEL
    )

    question = "รายได้รวม อป.1 ปี 2568"

    print(f"\nQuestion: {question}\n")

    result = service.query_with_retry(
        question=question,
        max_retries=2,
        on_status=print_status,
        explain=True
    )

    print("\n" + "-" * 40)
    print("FINAL RESULT:")
    print(f"  Success: {result.error is None}")
    print(f"  Retry Count: {result.retry_count}")
    print(f"  Data Rows: {len(result.data)}")


if __name__ == "__main__":
    print("\n🧪 AI Service Retry Mechanism Test\n")

    # Test with available provider
    from app.config import settings

    if settings.MATCHA_AI_API_KEY:
        test_retry_with_matcha()
    elif settings.GOOGLE_AI_API_KEY:
        test_retry_with_gemini()
    else:
        print("❌ No AI provider configured. Set MATCHA_AI_API_KEY or GOOGLE_AI_API_KEY")

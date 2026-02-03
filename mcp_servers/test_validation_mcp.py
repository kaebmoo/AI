"""
Test script for NT Validation MCP Server
"""

import sys
import os
import json

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.nt_validation_mcp import (
    check_business_rules,
    calculate_confidence_score,
    validate_result,
    get_validation_summary
)


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  Test: {title}")
    print('='*60)


def print_result(result: dict, indent: int = 2):
    print(json.dumps(result, indent=indent, ensure_ascii=False))


def test_check_business_rules():
    """Test business rules checking"""
    print_header("check_business_rules()")

    test_cases = [
        {
            "name": "Valid query with YEAR filter",
            "sql": "SELECT YEAR, SUM(REVENUE_VALUE) FROM revenue_search WHERE YEAR = 2025 GROUP BY YEAR",
            "question": "รายได้ปี 2568"
        },
        {
            "name": "Query with unquoted Thai column",
            "sql": "SELECT กลุ่มธุรกิจ, SUM(REVENUE_VALUE) FROM revenue_search GROUP BY กลุ่มธุรกิจ",
            "question": "รายได้แยกตามกลุ่มธุรกิจ"
        },
        {
            "name": "Query with DATE column (needs conversion)",
            "sql": "SELECT DATE, REVENUE_VALUE FROM revenue_search",
            "question": "รายได้ตามวันที่"
        },
        {
            "name": "SELECT * query",
            "sql": "SELECT * FROM revenue_search",
            "question": "แสดงข้อมูลทั้งหมด"
        },
        {
            "name": "Query without YEAR filter",
            "sql": "SELECT DIVISION, SUM(REVENUE_VALUE) FROM revenue_search GROUP BY DIVISION",
            "question": "รายได้แยกตามสายงาน"
        },
        {
            "name": "Empty SQL",
            "sql": "",
            "question": "test"
        }
    ]

    passed = 0
    for tc in test_cases:
        result = json.loads(check_business_rules(tc["sql"], tc["question"]))
        status = "PASS" if result["passed"] else "WARN" if result["warnings"] else "FAIL"

        print(f"\n  [{status}] {tc['name']}")
        print(f"       SQL: {tc['sql'][:50]}...")
        print(f"       Passed: {result['passed']}, Violations: {len(result['violations'])}, Warnings: {len(result['warnings'])}")

        if result["violations"]:
            for v in result["violations"]:
                print(f"       [ERROR] {v['rule']}: {v['message']}")

        if result["warnings"]:
            for w in result["warnings"]:
                print(f"       [WARN] {w['rule']}: {w['message']}")

        passed += 1

    print(f"\n  Business rules tests: {passed}/{len(test_cases)} completed")
    return passed == len(test_cases)


def test_calculate_confidence_score():
    """Test confidence score calculation"""
    print_header("calculate_confidence_score()")

    test_cases = [
        {
            "name": "Perfect query",
            "params": {
                "sql_validation_passed": True,
                "sql_issues_count": 0,
                "sql_warnings_count": 0,
                "rules_passed": True,
                "rules_violations_count": 0,
                "has_similar_example": True,
                "example_similarity": 0.9,
                "result_row_count": 10,
                "execution_success": True
            },
            "expected_level": "high"
        },
        {
            "name": "Good query with warnings",
            "params": {
                "sql_validation_passed": True,
                "sql_issues_count": 0,
                "sql_warnings_count": 2,
                "rules_passed": True,
                "rules_violations_count": 0,
                "has_similar_example": False,
                "example_similarity": 0.0,
                "result_row_count": 5,
                "execution_success": True
            },
            "expected_level": "medium"
        },
        {
            "name": "Query with rule violations",
            "params": {
                "sql_validation_passed": True,
                "sql_issues_count": 0,
                "sql_warnings_count": 1,
                "rules_passed": False,
                "rules_violations_count": 2,
                "has_similar_example": False,
                "example_similarity": 0.0,
                "result_row_count": 100,
                "execution_success": True
            },
            "expected_level": "low"
        },
        {
            "name": "Failed execution",
            "params": {
                "sql_validation_passed": False,
                "sql_issues_count": 2,
                "sql_warnings_count": 0,
                "rules_passed": False,
                "rules_violations_count": 1,
                "has_similar_example": False,
                "example_similarity": 0.0,
                "result_row_count": 0,
                "execution_success": False
            },
            "expected_level": "very_low"
        }
    ]

    passed = 0
    for tc in test_cases:
        result = json.loads(calculate_confidence_score(**tc["params"]))

        status = "PASS" if result["level"] == tc["expected_level"] else "FAIL"
        print(f"\n  [{status}] {tc['name']}")
        print(f"       Score: {result['score']}/100")
        print(f"       Level: {result['level_th']} ({result['level']})")
        print(f"       Expected: {tc['expected_level']}")
        print(f"       Color: {result['color']}")

        if status == "PASS":
            passed += 1

    print(f"\n  Confidence score tests: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_validate_result():
    """Test result validation"""
    print_header("validate_result()")

    test_cases = [
        {
            "name": "Valid result with data",
            "result": [
                {"year": 2025, "revenue": 1000000},
                {"year": 2024, "revenue": 950000}
            ],
            "expected_columns": ["year", "revenue"]
        },
        {
            "name": "Empty result",
            "result": [],
            "expected_columns": None
        },
        {
            "name": "Result with NULL values",
            "result": [
                {"division": "Finance", "amount": 500000},
                {"division": None, "amount": 300000}
            ],
            "expected_columns": ["division", "amount"]
        },
        {
            "name": "Result with very large values",
            "result": [
                {"category": "Total", "revenue_value": 5000000000000}
            ],
            "expected_columns": ["category", "revenue_value"]
        }
    ]

    passed = 0
    for tc in test_cases:
        result = json.loads(validate_result(tc["result"], tc.get("expected_columns")))

        print(f"\n  [INFO] {tc['name']}")
        print(f"       Valid: {result['valid']}")
        print(f"       Stats: {result['stats']}")

        if result["warnings"]:
            for w in result["warnings"]:
                print(f"       [WARN] {w['message']}")

        passed += 1

    print(f"\n  Result validation tests: {passed}/{len(test_cases)} completed")
    return True


def test_get_validation_summary():
    """Test complete validation summary"""
    print_header("get_validation_summary()")

    result = json.loads(get_validation_summary(
        sql="SELECT YEAR, MONTH, SUM(REVENUE_VALUE) as total FROM revenue_search WHERE YEAR = 2025 GROUP BY YEAR, MONTH ORDER BY MONTH",
        question="รายได้รายเดือนปี 2568",
        context_name="revenue",
        has_similar_example=True,
        example_similarity=0.75,
        execution_success=True,
        result_row_count=12
    ))

    print("\n  Complete Validation Summary:")
    print(f"  SQL Valid: {result['sql_valid']}")
    print(f"  Rules Passed: {result['rules_check']['passed']}")
    print(f"\n  Confidence:")
    print(f"    Score: {result['confidence']['score']}/100")
    print(f"    Level: {result['confidence']['level_th']}")
    print(f"    Color: {result['confidence']['color']}")
    print(f"    Recommendation: {result['confidence']['recommendation']}")

    print(f"\n  Factors:")
    for factor in result['confidence']['factors']:
        print(f"    - {factor['name']}: {factor['score']}/{factor['max']} ({factor['detail']})")

    return True


def main():
    print("\n" + "="*60)
    print("  NT Validation MCP Server - Test Suite")
    print("="*60)

    results = []

    # Run all tests
    results.append(("Business Rules", test_check_business_rules()))
    results.append(("Confidence Score", test_calculate_confidence_score()))
    results.append(("Result Validation", test_validate_result()))
    results.append(("Validation Summary", test_get_validation_summary()))

    # Summary
    print("\n" + "="*60)
    print("  Test Summary")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print(f"\n  Total: {sum(1 for _, p in results if p)}/{len(results)} test groups passed")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

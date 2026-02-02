"""
Test script for NT Query MCP Server
Run: python test_query_mcp.py
"""

import os
import sys

# Set the database path
os.environ["METADATA_DB_URL"] = f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"

# Import tools from the MCP server
from nt_query_mcp import (
    validate_sql,
    execute_query,
    get_sample_values,
    explain_sql_thai,
    get_table_stats
)


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_validate_sql():
    print_section("Test: validate_sql()")

    test_cases = [
        # Valid queries
        ("SELECT * FROM revenue_search LIMIT 10", True, "Basic SELECT"),
        ("SELECT year, SUM(revenue) FROM revenue_search GROUP BY year", True, "Aggregate with GROUP BY"),
        ("WITH cte AS (SELECT * FROM revenue_search) SELECT * FROM cte", True, "CTE query"),

        # Invalid queries
        ("DROP TABLE revenue_search", False, "DROP (dangerous)"),
        ("DELETE FROM revenue_search", False, "DELETE (dangerous)"),
        ("INSERT INTO revenue_search VALUES (1)", False, "INSERT (dangerous)"),
        ("SELECT * FROM revenue_search; DROP TABLE users", False, "Multiple statements"),
        ("", False, "Empty SQL"),
    ]

    passed = 0
    for sql, expected_valid, description in test_cases:
        result = validate_sql(sql)
        is_valid = result["valid"]
        status = "PASS" if is_valid == expected_valid else "FAIL"
        if status == "PASS":
            passed += 1

        print(f"  [{status}] {description}")
        print(f"       SQL: {sql[:50]}...")
        print(f"       Valid: {is_valid}, Issues: {len(result['issues'])}, Warnings: {len(result['warnings'])}")
        if result['issues']:
            print(f"       Issues: {result['issues'][:2]}")
        print()

    print(f"  Validation tests: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_execute_query():
    print_section("Test: execute_query()")

    # Test 1: Simple query
    print("  Test 1: Simple SELECT")
    result = execute_query("SELECT year, month FROM revenue_search LIMIT 5", limit=5)
    print(f"    Success: {result['success']}")
    print(f"    Row count: {result['row_count']}")
    print(f"    Columns: {result['columns']}")
    if result['data']:
        print(f"    Sample: {result['data'][0]}")
    print()

    # Test 2: Aggregate query
    print("  Test 2: Aggregate query")
    result = execute_query(
        "SELECT year, COUNT(*) as cnt FROM revenue_search GROUP BY year",
        limit=10
    )
    print(f"    Success: {result['success']}")
    print(f"    Row count: {result['row_count']}")
    if result['data']:
        print(f"    Data: {result['data'][:3]}")
    print()

    # Test 3: Invalid query (should fail validation)
    print("  Test 3: Invalid query (DROP)")
    result = execute_query("DROP TABLE test", validate_first=True)
    print(f"    Success: {result['success']} (expected: False)")
    print(f"    Error: {result.get('error', 'N/A')}")
    print()

    # Test 4: Query with error (non-existent table)
    print("  Test 4: Non-existent table")
    result = execute_query("SELECT * FROM non_existent_table", validate_first=True)
    print(f"    Success: {result['success']} (expected: False)")
    print(f"    Error: {result.get('error', 'N/A')[:50]}...")
    print()

    return True


def test_get_sample_values():
    print_section("Test: get_sample_values()")

    # Test 1: Get year values
    print("  Test 1: Sample years")
    result = get_sample_values("year", "revenue_search", limit=10)
    print(f"    Column: {result['column']}")
    print(f"    Values: {result['values']}")
    print(f"    Total distinct: {result['total_distinct']}")
    print()

    # Test 2: Get department values
    print("  Test 2: Sample departments")
    result = get_sample_values("department", "revenue_search", limit=5)
    print(f"    Column: {result['column']}")
    print(f"    Sample count: {result['sample_count']}")
    print(f"    Total distinct: {result['total_distinct']}")
    if result['values']:
        print(f"    Values: {result['values'][:3]}...")
    print()

    return True


def test_explain_sql_thai():
    print_section("Test: explain_sql_thai()")

    test_queries = [
        "SELECT * FROM revenue_search WHERE year = 2025 LIMIT 10",
        "SELECT department, SUM(revenue) as total FROM revenue_search WHERE year = 2025 AND month = 1 GROUP BY department ORDER BY total DESC",
        "SELECT year, month, COUNT(*) as cnt FROM revenue_search GROUP BY year, month HAVING COUNT(*) > 100",
    ]

    for i, sql in enumerate(test_queries, 1):
        print(f"  Test {i}:")
        print(f"    SQL: {sql[:60]}...")
        result = explain_sql_thai(sql)
        print(f"    Summary: {result['summary']}")
        print(f"    Steps:")
        for step in result['steps']:
            print(f"      - {step}")
        print()

    return True


def test_get_table_stats():
    print_section("Test: get_table_stats()")

    # Test revenue_search
    print("  Table: revenue_search")
    result = get_table_stats("revenue_search")
    print(f"    Row count: {result['row_count']:,}")
    print(f"    Column count: {result['column_count']}")
    print(f"    Columns: {[c['name'] for c in result['columns'][:5]]}...")
    print()

    # Test v_expense_mart
    print("  Table: v_expense_mart")
    result = get_table_stats("v_expense_mart")
    print(f"    Row count: {result.get('row_count', 'N/A'):,}")
    if result.get('error'):
        print(f"    Error: {result['error']}")
    print()

    return True


def main():
    print("\n" + "="*60)
    print("  NT Query MCP Server - Test Suite")
    print("="*60)

    tests = [
        ("Validate SQL", test_validate_sql),
        ("Execute Query", test_execute_query),
        ("Sample Values", test_get_sample_values),
        ("Explain SQL Thai", test_explain_sql_thai),
        ("Table Stats", test_get_table_stats),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n  ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print_section("Test Summary")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    passed_count = sum(1 for _, p in results if p)
    print(f"\n  Total: {passed_count}/{len(results)} tests passed")


if __name__ == "__main__":
    main()

"""
Test script for NT Metadata MCP Server
Run: python test_metadata_mcp.py
"""

import os
import sys

# Set the database path
os.environ["METADATA_DB_URL"] = f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"

# Import tools from the MCP server
from nt_metadata_mcp import (
    get_available_contexts,
    route_question_to_context,
    get_context_info,
    get_schema_for_context,
    get_column_info,
    get_semantic_mappings,
    search_mapping_for_term,
    get_business_rules,
    check_rule_violation,
    get_golden_examples,
    find_similar_example,
    get_database_info,
    get_syntax_rules
)


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_contexts():
    print_section("Test: get_available_contexts()")
    contexts = get_available_contexts()
    for ctx in contexts:
        print(f"  - {ctx['name']}: {ctx['display_name']} ({ctx['main_view']})")
        print(f"    Keywords: {ctx['keywords'][:5]}...")
    return len(contexts) > 0


def test_routing():
    print_section("Test: route_question_to_context()")

    test_questions = [
        "รายได้เดือนมกราคม 2568",
        "ค่าใช้จ่ายฝ่ายบุคคล",
        "ยอดขาย Mobile",
        "งบประมาณแผนก IT"
    ]

    for q in test_questions:
        result = route_question_to_context(q)
        print(f"  Q: {q}")
        print(f"  → Context: {result['context']} (confidence: {result['confidence']})")
        print(f"    Matched: {result['matched_keywords']}")
        print()

    return True


def test_schema():
    print_section("Test: get_schema_for_context('revenue')")
    schema = get_schema_for_context("revenue")

    if "error" in schema:
        print(f"  Error: {schema['error']}")
        return False

    print(f"  Main view: {schema['main_view']}")
    print(f"  Columns: {schema['column_count']}")
    print(f"  Sample columns:")
    for col in schema['columns'][:5]:
        print(f"    - {col['name']}: {col['type']} ({col['thai_name']})")
        print(f"      Summable: {col['is_summable']}, Groupable: {col['is_groupable']}")

    return True


def test_mappings():
    print_section("Test: get_semantic_mappings()")

    mappings = get_semantic_mappings(limit=10)
    print(f"  Found {len(mappings)} mappings:")
    for m in mappings[:5]:
        print(f"    - '{m['keyword']}' → {m['target_column']}")
        if m.get('condition'):
            print(f"      Condition: {m['condition']}")

    print_section("Test: search_mapping_for_term('Mobile')")
    result = search_mapping_for_term("Mobile")
    if result.get("found"):
        print(f"  Found: {result.get('keyword', result.get('suggestions', []))}")
    else:
        print(f"  Not found: {result['message']}")

    return True


def test_rules():
    print_section("Test: get_business_rules()")

    rules = get_business_rules()
    print(f"  Found {len(rules)} rules:")
    for rule in rules[:3]:
        print(f"    - [{rule['severity']}] {rule['code']}: {rule['name']}")
        print(f"      Table: {rule['table_name']}, Applies to: {rule['applies_to']}")

    print_section("Test: check_rule_violation()")

    test_sql = "SELECT SUM(revenue) FROM revenue_search WHERE year = 2025"
    test_question = "รายได้รวมปี 2568"

    result = check_rule_violation(test_sql, test_question, "revenue_search")
    print(f"  SQL: {test_sql}")
    print(f"  Question: {test_question}")
    print(f"  Passed: {result['passed']}")
    print(f"  Violations: {len(result['violations'])}")
    for v in result['violations']:
        print(f"    - [{v['severity']}] {v['rule']}: {v['message']}")
    print(f"  Warnings: {len(result['warnings'])}")
    for w in result['warnings']:
        print(f"    - [{w['severity']}] {w['rule']}: {w['message']}")

    return True


def test_examples():
    print_section("Test: get_golden_examples()")

    examples = get_golden_examples(limit=3)
    print(f"  Found {len(examples)} examples:")
    for ex in examples:
        print(f"    Q: {ex['question'][:50]}...")
        print(f"    Category: {ex['category']}")

    return True


def test_db_info():
    print_section("Test: get_database_info()")

    info = get_database_info()
    print(f"  Engine: {info['engine']}")
    print(f"  Contexts: {info['contexts']}")
    print(f"  Views: {info['views']}")
    print(f"  Status: {info['status']}")

    print_section("Test: get_syntax_rules()")
    rules = get_syntax_rules()
    print(f"  Engine: {rules['engine']}")
    for key, value in rules.get('rules', {}).items():
        print(f"    - {key}: {value}")

    return True


def main():
    print("\n" + "="*60)
    print("  NT Metadata MCP Server - Test Suite")
    print("="*60)

    tests = [
        ("Contexts", test_contexts),
        ("Routing", test_routing),
        ("Schema", test_schema),
        ("Mappings", test_mappings),
        ("Rules", test_rules),
        ("Examples", test_examples),
        ("DB Info", test_db_info),
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

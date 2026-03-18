#!/usr/bin/env python3
"""
Context Onboarding CLI
=======================
Analyze a database view and auto-generate all config needed for the NL-to-SQL system.

Usage:
  python scripts/onboard_context.py --view-name v_pl_costtype_nt_mth_clean --dry-run
  python scripts/onboard_context.py --view-name v_asset_summary --provider gemini --apply
  python scripts/onboard_context.py --view-name v_new_view --inspect-only
  python scripts/onboard_context.py --view-name v_new_view --output config.json
"""

import argparse
import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.context_onboarding import ContextOnboardingService


DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'nt_fi_report.sqlite'
)


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_inspection(inspection):
    """Print inspection results."""
    print_header("Phase 1: Data Inspection")
    print(f"View: {inspection.view_name}")
    print(f"Rows: {inspection.row_count:,}")
    print(f"Columns: {len(inspection.columns)}")
    print(f"Detected Structure: {inspection.detected_structure}")
    print(f"Date Range: {inspection.date_range}")

    print(f"\n--- Columns ---")
    for col in inspection.columns:
        flags = []
        if col.is_numeric:
            flags.append("NUMERIC")
        if col.is_time_column:
            flags.append("TIME")
        if col.has_numeric_prefix:
            flags.append("PREFIX")
        if col.has_case_inconsistency:
            flags.append("CASE_ISSUE")
        if col.has_empty_values:
            flags.append("EMPTY")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {col.name}: {col.data_type} (distinct={col.distinct_count}, nulls={col.null_count}){flag_str}")

    if inspection.detected_value_columns:
        print(f"\nValue columns: {inspection.detected_value_columns}")
    if inspection.detected_category_columns:
        print(f"Category columns: {inspection.detected_category_columns}")
    if inspection.detected_time_columns:
        print(f"Time columns: {inspection.detected_time_columns}")

    if inspection.cross_analyses:
        print(f"\n--- Cross-Column Analysis ---")
        for ca in inspection.cross_analyses:
            status = "⚠️  SEMI-CROSSTAB" if ca.likely_semi_crosstab else "OK"
            signs = "mixed +/-" if ca.has_mixed_signs else "same sign"
            print(f"  {ca.value_column} by {ca.category_column}: {signs} → {status}")
            if ca.likely_semi_crosstab:
                for cat, stats in list(ca.categories.items())[:5]:
                    print(f"    {cat}: sum={stats.get('sum', 0):,.0f}")

    if inspection.quality_issues:
        print(f"\n--- Quality Issues ---")
        for qi in inspection.quality_issues:
            print(f"  [{qi.issue_type}] {qi.column}: {qi.description}")
            for ex in qi.examples[:3]:
                print(f"    e.g., {ex}")


def print_config(config):
    """Print config bundle summary."""
    print_header("Phase 3: Generated Config")
    print(config.summary)


async def main():
    parser = argparse.ArgumentParser(description="Context Onboarding - Auto-configure NL-to-SQL for new views")
    parser.add_argument("--view-name", required=True, help="Name of the view/table to onboard")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to SQLite database")

    # LLM provider options
    parser.add_argument("--provider", default=None, help="AI provider: claude, gemini, matcha (default: from config)")
    parser.add_argument("--model", default=None, help="Specific model name (default: from config)")
    parser.add_argument("--api-url", default=None, help="Custom API URL (for OpenAI-compatible)")
    parser.add_argument("--api-key", default=None, help="Custom API key (overrides env var)")

    # Action modes
    parser.add_argument("--inspect-only", action="store_true", help="Only run Phase 1 (no LLM)")
    parser.add_argument("--dry-run", action="store_true", help="Preview config without applying (default)")
    parser.add_argument("--apply", action="store_true", help="Apply config to database")
    parser.add_argument("--output", default=None, help="Export config as JSON file")
    parser.add_argument("--validate", action="store_true", help="Run validation after apply")

    args = parser.parse_args()

    # Validate DB path
    if not os.path.exists(args.db_path):
        print(f"Error: Database not found: {args.db_path}")
        sys.exit(1)

    service = ContextOnboardingService(args.db_path)

    # Phase 1: Inspect
    inspection = service.inspect(args.view_name)
    print_inspection(inspection)

    if args.inspect_only:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(inspection.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"\nInspection exported to: {args.output}")
        print("\n✅ Inspection complete (--inspect-only mode)")
        return

    # Phase 2: LLM Analysis
    print_header("Phase 2: LLM Analysis")
    provider_label = args.provider or "default"
    model_label = args.model or "default"
    print(f"Provider: {provider_label}, Model: {model_label}")
    print("Sending data to LLM for analysis...")

    try:
        analysis = await service.analyze(
            inspection,
            provider=args.provider,
            model=args.model,
            api_url=args.api_url,
            api_key=args.api_key,
        )
    except Exception as e:
        print(f"\n❌ LLM analysis failed: {e}")
        sys.exit(1)

    # Print structure detection
    ds = analysis.get("data_structure", {})
    print(f"\nStructure: {ds.get('type', '?')}")
    print(f"Explanation: {ds.get('explanation', '?')}")
    if ds.get("critical_rule"):
        print(f"⚠️  Critical Rule: {ds.get('critical_rule')}")

    # Phase 3: Generate Config
    service._last_view_name = args.view_name
    config = service.generate_config(analysis, view_name=args.view_name)
    print_config(config)

    # Export to JSON if requested
    if args.output:
        export = {
            "inspection": inspection.to_dict(),
            "analysis": analysis,
            "sql_statements": config.sql_statements,
            "summary": config.summary,
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(export, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Config exported to: {args.output}")

    # Phase 4: Apply
    if args.apply:
        print_header("Phase 4: Applying Config")
        result = service.apply(config, dry_run=False)
        print(f"Status: {result['status']}")
        print(f"Success: {result.get('success', 0)} statements")
        if result.get('errors'):
            print(f"Errors: {len(result['errors'])}")
            for err in result['errors']:
                print(f"  ❌ {err}")

        # Phase 5: Validate
        if args.validate:
            print_header("Phase 5: Validation")
            validation = await service.validate(args.view_name)
            print(f"Passed: {'✅' if validation.passed else '❌'}")
            for tr in validation.test_results:
                status = "✅" if tr.get("passed") else "❌"
                print(f"  {status} {tr.get('check', '?')}: {tr.get('count', 0)}")
            if validation.issues:
                for issue in validation.issues:
                    print(f"  ⚠️  {issue}")
    else:
        # Dry-run: show SQL statements
        print_header("Phase 4: Dry Run (SQL Preview)")
        print(f"Total statements: {len(config.sql_statements)}")
        for i, sql in enumerate(config.sql_statements, 1):
            print(f"\n-- [{i}] --")
            print(sql)

        print(f"\n💡 To apply: add --apply flag")
        print(f"💡 To export: add --output config.json")


if __name__ == "__main__":
    asyncio.run(main())

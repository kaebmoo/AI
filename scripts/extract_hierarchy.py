#!/usr/bin/env python3
"""
Auto-extract hierarchy from data and populate master_hierarchy tables.

Usage:
    python scripts/extract_hierarchy.py                    # extract all contexts
    python scripts/extract_hierarchy.py --context revenue  # extract specific context
    python scripts/extract_hierarchy.py --dry-run          # show what would be extracted

This script:
1. Reads hierarchy config from schema_contexts + view columns
2. Extracts DISTINCT parent-child relationships from actual data
3. Populates master_hierarchy (levels) and master_hierarchy_values (values)
4. Preserves 'manual' entries (from admin/master data files)
"""

import sqlite3
import json
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# --------------------------------------------------------------------------
# Hierarchy definitions per context
# These define WHICH columns form the hierarchy and their keywords.
# Eventually this should come from master_hierarchy table itself,
# but we need a bootstrap source.
# --------------------------------------------------------------------------
HIERARCHY_DEFS = {
    "revenue": {
        "view": "revenue_search",
        "levels": [
            {
                "level": 0,
                "columns": ["BUSINESS_GROUP"],
                "label_th": "กลุ่มธุรกิจ",
                "label_en": "Business Group",
                "keywords": ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"],
            },
            {
                "level": 1,
                "columns": ["SERVICE_GROUP"],
                "label_th": "กลุ่มบริการ",
                "label_en": "Service Group",
                "keywords": ["กลุ่มบริการ", "service group", "กลุ่ม"],
                "parent_column": "BUSINESS_GROUP",
            },
            {
                "level": 2,
                "columns": ["PRODUCT_NAME"],
                "label_th": "บริการ/ผลิตภัณฑ์",
                "label_en": "Product/Service",
                "keywords": ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ", "service"],
                "parent_column": "SERVICE_GROUP",
            },
        ],
    },
    "pl_costtype": {
        "view": "TRN_PL_COSTTYPE_NT_MTH",
        "levels": [
            {
                "level": 0,
                "columns": ["business_unit"],
                "label_th": "กลุ่มธุรกิจ",
                "label_en": "Business Unit",
                "keywords": ["กลุ่มธุรกิจ", "business unit", "ธุรกิจ"],
            },
            {
                "level": 1,
                "columns": ["service_group"],
                "label_th": "กลุ่มบริการ",
                "label_en": "Service Group",
                "keywords": ["กลุ่มบริการ", "service group", "กลุ่ม"],
                "parent_column": "business_unit",
            },
            {
                "level": 2,
                "columns": ["product_name"],
                "label_th": "ผลิตภัณฑ์/บริการ",
                "label_en": "Product/Service",
                "keywords": ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ"],
                "parent_column": "service_group",
            },
        ],
    },
    "expense": {
        "view": "v_expense_mart",
        "levels": [
            {
                "level": 0,
                "columns": ["account_group_name"],
                "label_th": "หมวดค่าใช้จ่าย",
                "label_en": "Expense Group",
                "keywords": ["หมวดค่าใช้จ่าย", "หมวด", "กลุ่มค่าใช้จ่าย", "expense group"],
            },
            {
                "level": 1,
                "columns": ["account_name"],
                "label_th": "รายการค่าใช้จ่าย",
                "label_en": "Expense Account",
                "keywords": ["รายการค่าใช้จ่าย", "ค่าใช้จ่าย", "account", "gl", "บัญชี"],
                "parent_column": "account_group_name",
            },
        ],
    },
    "expense_org": {
        "view": "v_expense_mart",
        "levels": [
            {
                "level": 0,
                "columns": ["division"],
                "label_th": "สายงาน",
                "label_en": "Division",
                "keywords": ["สายงาน", "division"],
            },
            {
                "level": 1,
                "columns": ["organization_group"],
                "label_th": "กลุ่มงาน",
                "label_en": "Group",
                "keywords": ["กลุ่มงาน", "กลุ่ม", "group"],
                "parent_column": "division",
            },
            {
                "level": 2,
                "columns": ["department"],
                "label_th": "ฝ่าย",
                "label_en": "Department",
                "keywords": ["ฝ่าย", "department"],
                "parent_column": "organization_group",
            },
        ],
    },
    "transfer price": {
        "view": "v_transfer_price",
        "levels": [
            {
                "level": 0,
                "columns": ["owner_division"],
                "label_th": "สายงาน (ผู้ให้บริการ)",
                "label_en": "Owner Division",
                "keywords": ["สายงาน", "ผู้ให้บริการ", "owner", "division"],
            },
            {
                "level": 1,
                "columns": ["product_name"],
                "label_th": "บริการ",
                "label_en": "Product",
                "keywords": ["บริการ", "product", "ผลิตภัณฑ์"],
                "parent_column": "owner_division",
            },
        ],
    },
}


def run_migration(conn: sqlite3.Connection):
    """Create tables if not exist."""
    migration_path = Path(__file__).parent.parent / "database" / "migrations" / "009_master_hierarchy.sql"
    if migration_path.exists():
        conn.executescript(migration_path.read_text())
        print(f"  Migration applied: {migration_path.name}")
    else:
        print(f"  Warning: Migration file not found at {migration_path}")


def extract_hierarchy_levels(conn: sqlite3.Connection, context_name: str, definition: dict, dry_run: bool = False):
    """Extract and save hierarchy level definitions."""
    for level_def in definition["levels"]:
        level = level_def["level"]
        columns_json = json.dumps(level_def["columns"], ensure_ascii=False)
        keywords_json = json.dumps(level_def["keywords"], ensure_ascii=False)

        if dry_run:
            print(f"    [DRY-RUN] Level {level}: {level_def['label_th']} columns={columns_json}")
            continue

        conn.execute("""
            INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, detection_keywords, source)
            VALUES (?, ?, ?, ?, ?, ?, 'auto')
            ON CONFLICT(context_name, level) DO UPDATE SET
                level_label_th = excluded.level_label_th,
                level_label_en = excluded.level_label_en,
                level_columns = CASE WHEN source = 'manual' THEN level_columns ELSE excluded.level_columns END,
                detection_keywords = CASE WHEN source = 'manual' THEN detection_keywords ELSE excluded.detection_keywords END,
                updated_at = CURRENT_TIMESTAMP
        """, (context_name, level, level_def["label_th"], level_def["label_en"], columns_json, keywords_json))


def extract_hierarchy_values(conn: sqlite3.Connection, data_engine, context_name: str, definition: dict,
                             dry_run: bool = False):
    """Extract actual parent-child values from data (read on data_engine, written on conn = config DB)."""
    from sqlalchemy import text

    view = definition["view"]
    try:  # the view must exist in the context's own source
        with data_engine.connect() as dc:
            dc.execute(text(f'SELECT 1 FROM "{view}" LIMIT 0')).fetchall()
    except Exception:
        print(f"    Warning: {view} not found, skipping value extraction")
        return

    for level_def in definition["levels"]:
        level = level_def["level"]
        col = level_def["columns"][0]  # primary column
        parent_col = level_def.get("parent_column")

        if parent_col:
            query = f'SELECT DISTINCT "{parent_col}", "{col}" FROM "{view}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\' ORDER BY "{parent_col}", "{col}"'
        else:
            query = f'SELECT DISTINCT "{col}" FROM "{view}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\' ORDER BY "{col}"'

        try:
            with data_engine.connect() as dc:
                rows = dc.execute(text(query)).fetchall()
        except Exception as e:
            print(f"    Error extracting level {level} from {view}: {e}")
            continue

        count = 0
        for row in rows:
            if parent_col:
                parent_value, value = row
            else:
                value = row[0]
                parent_value = None

            if dry_run:
                if count < 3:
                    print(f"    [DRY-RUN] L{level}: {parent_value} → {value}")
                elif count == 3:
                    print(f"    [DRY-RUN] ... and more")
                count += 1
                continue

            # Generate aliases: lowercase, no parentheses content
            aliases = set()
            aliases.add(value.lower())
            # Extract text inside parentheses as alias
            import re
            paren_match = re.search(r'\(([^)]+)\)', value)
            if paren_match:
                aliases.add(paren_match.group(1).lower())
                # Also add version without parentheses
                clean = re.sub(r'\s*\([^)]*\)\s*', ' ', value).strip()
                aliases.add(clean.lower())

            aliases_json = json.dumps(sorted(aliases), ensure_ascii=False)

            conn.execute("""
                INSERT INTO master_hierarchy_values (context_name, level, value, parent_value, aliases, source)
                VALUES (?, ?, ?, ?, ?, 'auto')
                ON CONFLICT(context_name, level, value) DO UPDATE SET
                    parent_value = CASE WHEN source = 'manual' THEN parent_value ELSE excluded.parent_value END,
                    aliases = CASE WHEN source = 'manual' THEN aliases ELSE excluded.aliases END
            """, (context_name, level, value, parent_value, aliases_json))
            count += 1

        if not dry_run:
            print(f"    Level {level} ({level_def['label_th']}): {count} values extracted")
        else:
            print(f"    [DRY-RUN] Level {level}: {count} values total")


def load_defs_from_db(conn: sqlite3.Connection, context_filter: str = None) -> dict:
    """
    Load hierarchy definitions from master_hierarchy table (DB-driven).
    Falls back to HIERARCHY_DEFS (hardcoded) if table doesn't exist or is empty.

    This is the key function that eliminates hardcoding:
    - Admin adds levels via UI → saved to master_hierarchy with source_view + parent_column
    - This function reads those → builds the same dict format as HIERARCHY_DEFS
    - extract runs against the DB config → no code changes needed for new contexts
    """
    try:
        rows = conn.execute("""
            SELECT context_name, level, level_label_th, level_label_en,
                   level_columns, detection_keywords, parent_column, source_view
            FROM master_hierarchy
            WHERE is_active = 1 AND source_view IS NOT NULL
            ORDER BY context_name, level
        """).fetchall()
    except Exception:
        # Table doesn't exist yet — use hardcoded
        rows = []

    if not rows:
        print("  (No DB config found, using hardcoded HIERARCHY_DEFS)")
        if context_filter:
            return {context_filter: HIERARCHY_DEFS[context_filter]} if context_filter in HIERARCHY_DEFS else {}
        return HIERARCHY_DEFS

    db_defs = {}
    for ctx, level, label_th, label_en, cols_json, kw_json, parent_col, view in rows:
        if context_filter and ctx != context_filter:
            continue
        if ctx not in db_defs:
            db_defs[ctx] = {"view": view, "levels": []}
        db_defs[ctx]["levels"].append({
            "level": level,
            "columns": json.loads(cols_json),
            "label_th": label_th,
            "label_en": label_en,
            "keywords": json.loads(kw_json),
            "parent_column": parent_col,
        })

    if db_defs:
        print(f"  (Loaded {len(db_defs)} context(s) from DB: {list(db_defs.keys())})")
    return db_defs


def main():
    parser = argparse.ArgumentParser(description="Extract hierarchy from data")
    parser.add_argument("--context", help="Specific context to extract (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted")
    args = parser.parse_args()

    from app.config import settings
    from app.services.data_sources import source_resolver

    # REMAIN-9.5: master_hierarchy* live in the config DB; values are read from each context's
    # own source (legacy business DB or a file source) — this used to read and write the business DB
    conn = sqlite3.connect(settings.CONFIG_DB_URL.replace("sqlite:///", ""))

    if not args.dry_run:
        run_migration(conn)

    # DB-first: read config from master_hierarchy table
    # Fallback: use hardcoded HIERARCHY_DEFS if DB empty
    contexts = load_defs_from_db(conn, args.context)

    if not contexts:
        print(f"No hierarchy config found for '{args.context}'. Add via Admin UI or HIERARCHY_DEFS.")
        conn.close()
        return

    for ctx_name, ctx_def in contexts.items():
        print(f"\n{'='*60}")
        print(f"Context: {ctx_name} (view: {ctx_def['view']})")
        print(f"{'='*60}")

        extract_hierarchy_levels(conn, ctx_name, ctx_def, dry_run=args.dry_run)
        source = source_resolver.for_context(ctx_name)
        if source.llm_data_policy != "full":  # Phase 4.5: values of such a source are never copied into the config DB
            print(f"  ข้าม values: llm_data_policy ของ source '{source.name}' = {source.llm_data_policy}")
            continue
        extract_hierarchy_values(conn, source.engine, ctx_name, ctx_def, dry_run=args.dry_run)

    if not args.dry_run:
        conn.commit()
        total_levels = conn.execute("SELECT COUNT(*) FROM master_hierarchy").fetchone()[0]
        total_values = conn.execute("SELECT COUNT(*) FROM master_hierarchy_values").fetchone()[0]
        print(f"\nDone! {total_levels} hierarchy levels, {total_values} hierarchy values")
    else:
        print(f"\nDry run complete. No changes made.")

    conn.close()


if __name__ == "__main__":
    main()

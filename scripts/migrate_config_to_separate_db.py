#!/usr/bin/env python3
"""
Migrate Config Tables to Separate DB
======================================
Copies config tables from the business DB (nt_fi_report.sqlite) to a new config.db.
Optionally drops them from the source.

Usage:
    python scripts/migrate_config_to_separate_db.py --dry-run   # Preview
    python scripts/migrate_config_to_separate_db.py --apply     # Execute
    python scripts/migrate_config_to_separate_db.py --apply --drop-source  # Execute + drop from source
"""

import argparse
import os
import sqlite3
import sys
import shutil
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Config tables to move
CONFIG_TABLES = [
    "schema_contexts",
    "schema_metadata",
    "schema_business_rules",
    "schema_semantic_mapping",
    "golden_examples",
    "master_hierarchy",
    "master_hierarchy_values",
    "data_warnings",
    "query_complexity_patterns",
    "admin_config",
    "ai_providers",
    "ai_models",
    "keyword_value_index",
    "view_column_mappings",
    "dimension_families",
]


def get_table_schema(conn: sqlite3.Connection, table_name: str) -> str:
    """Get CREATE TABLE statement for a table."""
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def copy_table_data(source: sqlite3.Connection, dest: sqlite3.Connection, table_name: str) -> int:
    """Copy all rows from source to destination. Returns row count."""
    cursor = source.execute(f"SELECT * FROM [{table_name}]")
    rows = cursor.fetchall()
    if not rows:
        return 0

    columns = [desc[0] for desc in cursor.description]
    placeholders = ",".join(["?"] * len(columns))
    col_names = ",".join(f"[{c}]" for c in columns)

    dest.executemany(
        f"INSERT INTO [{table_name}] ({col_names}) VALUES ({placeholders})",
        rows
    )
    return len(rows)


def migrate(source_path: str, dest_path: str, dry_run: bool = True, drop_source: bool = False):
    """Execute the migration."""
    print(f"Source: {source_path}")
    print(f"Destination: {dest_path}")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print(f"Drop source: {drop_source}")
    print("=" * 60)

    # Backup source before any changes
    if not dry_run:
        backup_path = f"{source_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(source_path, backup_path)
        print(f"Backup created: {backup_path}")

    source = sqlite3.connect(source_path)

    # Check which tables exist in source
    existing_tables = []
    for table in CONFIG_TABLES:
        cursor = source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if cursor.fetchone():
            existing_tables.append(table)
        else:
            print(f"  SKIP {table} (not in source)")

    print(f"\nFound {len(existing_tables)}/{len(CONFIG_TABLES)} config tables in source")

    if dry_run:
        for table in existing_tables:
            count = source.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            print(f"  {table}: {count} rows")
        source.close()
        print("\nDry run complete. Use --apply to execute.")
        return

    # Create destination DB
    dest = sqlite3.connect(dest_path)

    for table in existing_tables:
        # Get and create schema
        schema_sql = get_table_schema(source, table)
        if not schema_sql:
            print(f"  SKIP {table} (no schema)")
            continue

        try:
            dest.execute(schema_sql)
        except sqlite3.OperationalError:
            # Table already exists — drop and recreate
            dest.execute(f"DROP TABLE IF EXISTS [{table}]")
            dest.execute(schema_sql)

        # Copy data
        count = copy_table_data(source, dest, table)
        print(f"  MIGRATED {table}: {count} rows")

    dest.commit()

    # Copy indexes
    index_cursor = source.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    )
    for row in index_cursor:
        sql = row[0]
        # Only copy indexes for config tables
        for table in existing_tables:
            if table in sql:
                try:
                    dest.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Index already exists

    dest.commit()

    # Drop source tables if requested
    if drop_source:
        print("\nDropping config tables from source...")
        for table in existing_tables:
            source.execute(f"DROP TABLE IF EXISTS [{table}]")
            print(f"  DROPPED {table}")
        source.execute("VACUUM")
        source.commit()

    source.close()
    dest.close()

    print(f"\nMigration complete! Config DB: {dest_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate config tables to separate DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--apply", action="store_true", help="Execute migration")
    parser.add_argument("--drop-source", action="store_true", help="Drop tables from source after copy")
    parser.add_argument("--source", default="nt_fi_report.sqlite", help="Source DB path")
    parser.add_argument("--dest", default="config.db", help="Destination config DB path")

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        print("\nPlease specify --dry-run or --apply")
        sys.exit(1)

    if not os.path.exists(args.source):
        print(f"Source DB not found: {args.source}")
        sys.exit(1)

    migrate(
        source_path=args.source,
        dest_path=args.dest,
        dry_run=args.dry_run,
        drop_source=args.drop_source,
    )


if __name__ == "__main__":
    main()

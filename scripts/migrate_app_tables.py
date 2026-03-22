#!/usr/bin/env python3
"""
Migrate App Tables from nt_fi_report.sqlite to app.db
======================================================
Phase 2 of DB separation: moves app tables (users, chat_history, etc.)
out of the business DB into a dedicated app.db.

Also drops broken views that reference config tables already migrated to config.db.

Usage:
    python scripts/migrate_app_tables.py --dry-run           # Preview
    python scripts/migrate_app_tables.py --apply              # Copy tables + drop broken views
    python scripts/migrate_app_tables.py --apply --drop-source  # Also drop app tables from source
"""

import argparse
import os
import sys
import sqlite3
import shutil
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# App tables to move (users, sessions, chats, feedback, admin, API keys, etc.)
APP_TABLES = [
    "users",
    "user_sessions",
    "otp_requests",
    "chat_history",
    "conversations",
    "chat_session_data",
    "user_feedback",
    "admin_agent_conversations",
    "admin_agent_messages",
    "api_keys",
    "api_key_usage",
    "config_audit_log",
    "suggested_fixes",
    "trending_queries",
    "unmatched_keywords",
    "schema_context_tables",  # orphan, 0 rows — migrate for safety
]

# Broken views that reference dropped config tables
BROKEN_VIEWS = [
    "v_active_ai_providers",
    "v_active_contexts",
    "v_ai_config",
    "v_active_models",
    "v_active_providers",
    "v_business_rules_for_ai",
    "v_schema_for_ai",
    "v_semantic_mappings_for_ai",
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
    print(f"Source (business DB): {source_path}")
    print(f"Destination (app DB): {dest_path}")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print(f"Drop source tables: {drop_source}")
    print("=" * 60)

    if not os.path.exists(source_path):
        print(f"ERROR: Source DB not found: {source_path}")
        sys.exit(1)

    source = sqlite3.connect(source_path)

    # Check which app tables exist in source
    existing_tables = []
    for table in APP_TABLES:
        cursor = source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if cursor.fetchone():
            existing_tables.append(table)
        else:
            print(f"  SKIP {table} (not in source)")

    # Check which broken views exist
    existing_broken_views = []
    for view in BROKEN_VIEWS:
        cursor = source.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
            (view,)
        )
        if cursor.fetchone():
            existing_broken_views.append(view)

    print(f"\nFound {len(existing_tables)}/{len(APP_TABLES)} app tables in source")
    print(f"Found {len(existing_broken_views)}/{len(BROKEN_VIEWS)} broken views to drop")

    if dry_run:
        print("\n--- APP TABLES ---")
        for table in existing_tables:
            count = source.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            print(f"  {table}: {count} rows")

        print("\n--- BROKEN VIEWS TO DROP ---")
        for view in existing_broken_views:
            print(f"  {view}")

        source.close()
        print("\nDry run complete. Use --apply to execute.")
        return

    # Backup source before any changes
    backup_path = f"{source_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(source_path, backup_path)
    print(f"Backup created: {backup_path}")

    # Create destination DB
    dest = sqlite3.connect(dest_path)

    # Migrate app tables
    print("\n--- MIGRATING APP TABLES ---")
    for table in existing_tables:
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

        count = copy_table_data(source, dest, table)
        print(f"  MIGRATED {table}: {count} rows")

    dest.commit()

    # Copy indexes for migrated tables
    index_cursor = source.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    )
    for row in index_cursor:
        sql = row[0]
        for table in existing_tables:
            if table in sql:
                try:
                    dest.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Index already exists

    dest.commit()

    # Verify migration
    print("\n--- VERIFICATION ---")
    all_ok = True
    for table in existing_tables:
        src_count = source.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        dst_count = dest.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        status = "OK" if src_count == dst_count else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"  {table}: source={src_count}, dest={dst_count} [{status}]")

    if not all_ok:
        print("\nWARNING: Row count mismatch detected! Review before dropping source.")

    # Drop broken views
    print("\n--- DROPPING BROKEN VIEWS ---")
    for view in existing_broken_views:
        source.execute(f"DROP VIEW IF EXISTS [{view}]")
        print(f"  DROPPED VIEW {view}")
    source.commit()

    # Drop app tables from source if requested
    if drop_source and all_ok:
        print("\n--- DROPPING APP TABLES FROM SOURCE ---")
        for table in existing_tables:
            source.execute(f"DROP TABLE IF EXISTS [{table}]")
            print(f"  DROPPED {table}")
        source.execute("VACUUM")
        source.commit()
    elif drop_source and not all_ok:
        print("\nSKIPPING drop-source due to verification errors")

    source.close()
    dest.close()

    print(f"\nMigration complete!")
    print(f"  App DB: {dest_path}")
    print(f"  Backup: {backup_path}")
    if not drop_source:
        print(f"  Note: Source tables NOT dropped. Use --drop-source to remove them.")


def main():
    parser = argparse.ArgumentParser(description="Migrate app tables from business DB to app.db")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--apply", action="store_true", help="Execute migration")
    parser.add_argument("--drop-source", action="store_true", help="Drop tables from source after copy")
    parser.add_argument("--source", default="nt_fi_report.sqlite", help="Source DB path")
    parser.add_argument("--dest", default="app.db", help="Destination app DB path")

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        print("\nPlease specify --dry-run or --apply")
        sys.exit(1)

    migrate(
        source_path=args.source,
        dest_path=args.dest,
        dry_run=args.dry_run,
        drop_source=args.drop_source,
    )


if __name__ == "__main__":
    main()

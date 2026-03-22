#!/usr/bin/env python3
"""
Import master data files into master_hierarchy_values.

Supports 3 master data types:
1. Product hierarchy (MASTER_PRODUCT_NT.csv)
2. Organization hierarchy (MASTER_ORGANIZATION_NT_BU.csv)
3. GL/Account hierarchy (MASTER_REVENUE_GL_CODE_NT1_NT.csv, MASTER_EXPENSE_GL_CODE_NT1_NT.csv)

Usage:
    python scripts/import_master_data.py --source /path/to/master/source
    python scripts/import_master_data.py --source /path/to/master/source --type product
    python scripts/import_master_data.py --source /path/to/master/source --dry-run

Design:
    - 'manual' source entries override 'auto' entries
    - Running extract_hierarchy.py after this preserves manual entries
    - Re-running this script with new files updates existing entries
    - Future master data types: add a new import_xxx function + register in IMPORTERS
"""

import csv
import os
import sqlite3
import json
import re
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = os.environ.get("BUSINESS_DB_PATH", "nt_fi_report.sqlite")

# --------------------------------------------------------------------------
# Master data source file patterns (newest version = no date suffix)
# --------------------------------------------------------------------------
MASTER_FILES = {
    "product": "MASTER_PRODUCT_NT.csv",
    "product_mapping": "MASTER_PRODUCT_MAPPING_NT.csv",
    "organization": "MASTER_ORGANIZATION_NT_BU.csv",
    "org_mapping": "MASTER_ORGANIZATION_NT_MAPPING.csv",
    "revenue_gl": "MASTER_REVENUE_GL_CODE_NT1_NT.csv",
    "expense_gl": "MASTER_EXPENSE_GL_CODE_NT1_NT.csv",
    "gl_group": "MASTER_GL_GROUP_REPORT.csv",
    "product_pl": "MASTER_PRODUCT_PL_NT.csv",
}


def read_csv(filepath: Path) -> list[dict]:
    """Read CSV with BOM handling."""
    with open(filepath, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def make_aliases(value: str) -> list[str]:
    """Generate search aliases from a value."""
    aliases = {value.lower().strip()}
    # Extract text inside parentheses
    paren = re.search(r'\(([^)]+)\)', value)
    if paren:
        aliases.add(paren.group(1).lower().strip())
        clean = re.sub(r'\s*\([^)]*\)\s*', ' ', value).strip()
        aliases.add(clean.lower())
    # Short name without prefix
    for prefix in ["บริการ ", "กลุ่มบริการ ", "ฝ่าย", "ส่วน", "สายงาน"]:
        if value.startswith(prefix):
            aliases.add(value[len(prefix):].strip().lower())
    return sorted(aliases)


def upsert_value(conn, context, level, value, parent_value, aliases, source="manual"):
    """Insert or update a hierarchy value, preserving manual entries."""
    aliases_json = json.dumps(aliases, ensure_ascii=False)
    conn.execute("""
        INSERT INTO master_hierarchy_values (context_name, level, value, parent_value, aliases, source)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(context_name, level, value) DO UPDATE SET
            parent_value = excluded.parent_value,
            aliases = excluded.aliases,
            source = excluded.source
    """, (context, level, value, parent_value, aliases_json, source))


def upsert_level(conn, context, level, label_th, label_en, columns, keywords, source="manual"):
    """Insert or update a hierarchy level definition."""
    conn.execute("""
        INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, detection_keywords, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(context_name, level) DO UPDATE SET
            level_label_th = excluded.level_label_th,
            level_label_en = excluded.level_label_en,
            level_columns = excluded.level_columns,
            detection_keywords = excluded.detection_keywords,
            source = excluded.source,
            updated_at = CURRENT_TIMESTAMP
    """, (context, level, label_th, label_en,
          json.dumps(columns, ensure_ascii=False),
          json.dumps(keywords, ensure_ascii=False),
          source))


# --------------------------------------------------------------------------
# Import functions per master data type
# --------------------------------------------------------------------------

def import_product(conn, source_dir: Path, dry_run: bool = False):
    """Import product hierarchy: BUSINESS_GROUP > SERVICE_GROUP > PRODUCT_NAME"""
    filepath = source_dir / MASTER_FILES["product"]
    if not filepath.exists():
        print(f"  Skip: {filepath.name} not found")
        return

    rows = read_csv(filepath)
    print(f"  Reading {filepath.name}: {len(rows)} rows")

    # Ensure hierarchy levels exist
    if not dry_run:
        upsert_level(conn, "revenue", 0, "กลุ่มธุรกิจ", "Business Group",
                      ["BUSINESS_GROUP", "BUSINESS"],
                      ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"])
        upsert_level(conn, "revenue", 1, "กลุ่มบริการ", "Service Group",
                      ["SERVICE_GROUP"],
                      ["กลุ่มบริการ", "service group", "กลุ่ม"])
        upsert_level(conn, "revenue", 2, "บริการ/ผลิตภัณฑ์", "Product/Service",
                      ["PRODUCT_NAME", "PRODUCT"],
                      ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ", "service"])

    seen = {"bg": set(), "sg": set(), "pn": set()}

    for row in rows:
        bg = (row.get("BUSINESS_GROUP") or "").strip()
        sg = (row.get("SERVICE_GROUP") or "").strip()
        pn = (row.get("PRODUCT_NAME") or "").strip()
        short_name = (row.get("PRODUCT_SHORT_NAME") or "").strip()

        if not bg or not sg or not pn:
            continue

        # Level 0: Business Group
        if bg not in seen["bg"]:
            aliases = make_aliases(bg)
            if not dry_run:
                upsert_value(conn, "revenue", 0, bg, None, aliases)
            seen["bg"].add(bg)

        # Level 1: Service Group
        sg_key = f"{bg}|{sg}"
        if sg_key not in seen["sg"]:
            aliases = make_aliases(sg)
            if not dry_run:
                upsert_value(conn, "revenue", 1, sg, bg, aliases)
            seen["sg"].add(sg_key)

        # Level 2: Product
        pn_key = f"{sg}|{pn}"
        if pn_key not in seen["pn"]:
            aliases = make_aliases(pn)
            if short_name and short_name.lower() not in aliases:
                aliases.append(short_name.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue", 2, pn, sg, aliases)
            seen["pn"].add(pn_key)

    print(f"  Product: {len(seen['bg'])} business groups, {len(seen['sg'])} service groups, {len(seen['pn'])} products")


def import_organization(conn, source_dir: Path, dry_run: bool = False):
    """Import org hierarchy: DIVISION > GROUP > DEPARTMENT > SECTION"""
    filepath = source_dir / MASTER_FILES["organization"]
    if not filepath.exists():
        print(f"  Skip: {filepath.name} not found")
        return

    rows = read_csv(filepath)
    print(f"  Reading {filepath.name}: {len(rows)} rows")

    # Ensure hierarchy levels exist for revenue context (org dimension)
    if not dry_run:
        # These are additional hierarchy dimensions, stored with context "revenue_org"
        upsert_level(conn, "revenue_org", 0, "สายงาน", "Division",
                      ["DIVISION", "division"],
                      ["สายงาน", "division"])
        upsert_level(conn, "revenue_org", 1, "กลุ่มงาน", "Group",
                      ["GROUP", "organization_group"],
                      ["กลุ่มงาน", "กลุ่ม", "group"])
        upsert_level(conn, "revenue_org", 2, "ฝ่าย", "Department",
                      ["DEPARTMENT", "department"],
                      ["ฝ่าย", "department"])
        upsert_level(conn, "revenue_org", 3, "ส่วน", "Section",
                      ["SECTION", "section"],
                      ["ส่วน", "section"])

    seen = {"div": set(), "grp": set(), "dept": set(), "sec": set()}

    for row in rows:
        div = (row.get("DIVISION") or "").strip()
        grp = (row.get("GROUP") or "").strip()
        dept = (row.get("DEPARTMENT") or "").strip()
        sec = (row.get("SECTION") or "").strip()
        div_abbr = (row.get("DIVISION_ABBR") or "").strip()
        grp_abbr = (row.get("GROUP_ABBR") or "").strip()
        dept_abbr = (row.get("DEPARTMENT_ABBR") or "").strip()
        sec_abbr = (row.get("SECTION_ABBR") or "").strip()

        if not div:
            continue

        if div not in seen["div"]:
            aliases = make_aliases(div)
            if div_abbr:
                aliases.append(div_abbr.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue_org", 0, div, None, aliases)
            seen["div"].add(div)

        if grp and f"{div}|{grp}" not in seen["grp"]:
            aliases = make_aliases(grp)
            if grp_abbr:
                aliases.append(grp_abbr.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue_org", 1, grp, div, aliases)
            seen["grp"].add(f"{div}|{grp}")

        if dept and f"{grp}|{dept}" not in seen["dept"]:
            aliases = make_aliases(dept)
            if dept_abbr:
                aliases.append(dept_abbr.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue_org", 2, dept, grp, aliases)
            seen["dept"].add(f"{grp}|{dept}")

        if sec and f"{dept}|{sec}" not in seen["sec"]:
            aliases = make_aliases(sec)
            if sec_abbr:
                aliases.append(sec_abbr.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue_org", 3, sec, dept, aliases)
            seen["sec"].add(f"{dept}|{sec}")

    print(f"  Org: {len(seen['div'])} divisions, {len(seen['grp'])} groups, {len(seen['dept'])} departments, {len(seen['sec'])} sections")


def import_revenue_gl(conn, source_dir: Path, dry_run: bool = False):
    """Import GL hierarchy: REPORT_CODE/GL_GROUP > GL_CODE/GL_NAME"""
    filepath = source_dir / MASTER_FILES["revenue_gl"]
    if not filepath.exists():
        print(f"  Skip: {filepath.name} not found")
        return

    rows = read_csv(filepath)
    print(f"  Reading {filepath.name}: {len(rows)} rows")

    if not dry_run:
        upsert_level(conn, "revenue_gl", 0, "หมวดบัญชี", "GL Group",
                      ["GL_GROUP", "หมวดบัญชี"],
                      ["หมวดบัญชี", "gl group", "หมวด"])
        upsert_level(conn, "revenue_gl", 1, "รหัสบัญชี", "GL Code",
                      ["GL_CODE", "GL_NAME"],
                      ["รหัสบัญชี", "gl code", "gl", "บัญชี"])

    seen = {"group": set(), "gl": set()}

    for row in rows:
        gl_group = (row.get("GL_GROUP") or "").strip()
        report_code = (row.get("REPORT_CODE") or "").strip()
        gl_code = (row.get("GL_CODE") or "").strip()
        gl_name = (row.get("GL_NAME") or "").strip()

        if gl_group and gl_group not in seen["group"]:
            aliases = make_aliases(gl_group)
            if report_code:
                aliases.append(report_code.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "revenue_gl", 0, gl_group, None, aliases)
            seen["group"].add(gl_group)

        if gl_code and f"{gl_group}|{gl_code}" not in seen["gl"]:
            aliases = [gl_code.lower()]
            if gl_name:
                aliases.extend(make_aliases(gl_name))
                aliases = sorted(set(aliases))
            if not dry_run:
                upsert_value(conn, "revenue_gl", 1, f"{gl_code} {gl_name}", gl_group, aliases)
            seen["gl"].add(f"{gl_group}|{gl_code}")

    print(f"  Revenue GL: {len(seen['group'])} groups, {len(seen['gl'])} GL codes")


def import_expense_gl(conn, source_dir: Path, dry_run: bool = False):
    """Import expense GL hierarchy: CODE_GROUP/GROUP_NAME > GL_CODE/GL_NAME"""
    filepath = source_dir / MASTER_FILES["expense_gl"]
    if not filepath.exists():
        print(f"  Skip: {filepath.name} not found")
        return

    rows = read_csv(filepath)
    print(f"  Reading {filepath.name}: {len(rows)} rows")

    if not dry_run:
        upsert_level(conn, "expense", 0, "หมวดค่าใช้จ่าย", "Expense Group",
                      ["account_group_name", "account_group_code"],
                      ["หมวดค่าใช้จ่าย", "หมวด", "กลุ่มค่าใช้จ่าย", "expense group"])
        upsert_level(conn, "expense", 1, "รายการค่าใช้จ่าย", "Expense Account",
                      ["account_name", "gl_code"],
                      ["รายการค่าใช้จ่าย", "ค่าใช้จ่าย", "account", "gl", "บัญชี"])

    seen = {"group": set(), "gl": set()}

    for row in rows:
        code_group = (row.get("CODE_GROUP") or "").strip()
        group_name = (row.get("GROUP_NAME") or "").strip()
        gl_code = (row.get("GL_CODE_NT1") or row.get("GL_CODE") or "").strip()
        gl_name = (row.get("GL_NAME_NT1") or row.get("GL NAME") or "").strip()

        if group_name and group_name not in seen["group"]:
            aliases = make_aliases(group_name)
            if code_group:
                aliases.append(code_group.lower())
                aliases.sort()
            if not dry_run:
                upsert_value(conn, "expense", 0, group_name, None, aliases)
            seen["group"].add(group_name)

        if gl_code and f"{group_name}|{gl_code}" not in seen["gl"]:
            aliases = [gl_code.lower()]
            if gl_name:
                aliases.extend(make_aliases(gl_name))
                aliases = sorted(set(aliases))
            if not dry_run:
                upsert_value(conn, "expense", 1, f"{gl_code} {gl_name}", group_name, aliases)
            seen["gl"].add(f"{group_name}|{gl_code}")

    print(f"  Expense GL: {len(seen['group'])} groups, {len(seen['gl'])} GL codes")


# --------------------------------------------------------------------------
# Registry of importers — add new master data types here
# --------------------------------------------------------------------------
IMPORTERS = {
    "product": import_product,
    "organization": import_organization,
    "revenue_gl": import_revenue_gl,
    "expense_gl": import_expense_gl,
}


def main():
    parser = argparse.ArgumentParser(description="Import master data files")
    parser.add_argument("--source", required=True, help="Directory containing master data CSV files")
    parser.add_argument("--type", choices=list(IMPORTERS.keys()), help="Import specific type only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--db", default=DB_PATH, help=f"Database path (default: {DB_PATH})")
    args = parser.parse_args()

    source_dir = Path(args.source)
    if not source_dir.exists():
        print(f"Error: source directory not found: {source_dir}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)

    # Ensure tables exist
    migration = Path(__file__).parent.parent / "database" / "migrations" / "009_master_hierarchy.sql"
    if migration.exists() and not args.dry_run:
        conn.executescript(migration.read_text())

    importers = {args.type: IMPORTERS[args.type]} if args.type else IMPORTERS

    for name, func in importers.items():
        print(f"\n{'='*50}")
        print(f"Importing: {name}")
        print(f"{'='*50}")
        func(conn, source_dir, dry_run=args.dry_run)

    if not args.dry_run:
        conn.commit()
        total_levels = conn.execute("SELECT COUNT(*) FROM master_hierarchy").fetchone()[0]
        total_values = conn.execute("SELECT COUNT(*) FROM master_hierarchy_values").fetchone()[0]
        manual_count = conn.execute("SELECT COUNT(*) FROM master_hierarchy_values WHERE source = 'manual'").fetchone()[0]
        auto_count = conn.execute("SELECT COUNT(*) FROM master_hierarchy_values WHERE source = 'auto'").fetchone()[0]
        print(f"\nDone! {total_levels} levels, {total_values} values (manual: {manual_count}, auto: {auto_count})")

    conn.close()


if __name__ == "__main__":
    main()

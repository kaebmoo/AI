"""
Contract → context + knowledge generator (PLAN F10 Phase B)
============================================================
Idempotent — safe to re-run after every re-import. Registers the feed_<domain>
context and regenerates its documentation from the contract yaml.

Usage:
    python -m scripts.datafeed.gen_docs_from_contract --domain revenue \
        --contract /path/to/DataFeed/contracts/revenue.yaml
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_KEYWORDS = {
    "revenue": ["datafeed", "feed", "รายได้ feed", "dashboard"],
}


def _config_db_path() -> str:
    from app.config import settings
    return settings.CONFIG_DB_URL.replace("sqlite:///", "")


def register_context(conn, domain: str, contract: dict) -> str:
    """Upsert schema_contexts row for feed_<domain>."""
    context_name = f"feed_{domain}"
    main_view = f"feed_{domain}_{contract['control_totals']['source']}"
    rules_text = "\n".join(f"- {r['text']}" for r in contract.get("business_rules", []))
    instruction = (
        f"ข้อมูลจาก DataFeed (schema {contract['schema_version']}) — {contract.get('units', '')}\n"
        f"งวด ({contract.get('period_key', 'year_month')}) เป็น ค.ศ. รูปแบบ YYYYMM\n"
        f"กฎสำคัญ:\n{rules_text}"
    )
    import json as _json
    keywords = _json.dumps(DEFAULT_KEYWORDS.get(domain, ["datafeed"]), ensure_ascii=False)

    existing = conn.execute("SELECT id FROM schema_contexts WHERE name = ?", (context_name,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE schema_contexts SET main_view=?, description=?, instruction_th=?, keywords=?, "
            "is_active=1, updated_at=CURRENT_TIMESTAMP WHERE name=?",
            (main_view, contract.get("title", ""), instruction, keywords, context_name),
        )
    else:
        conn.execute(
            "INSERT INTO schema_contexts (name, display_name, description, main_view, is_active, priority, keywords, instruction_th) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?)",
            (context_name, f"DataFeed {domain}", contract.get("title", ""), main_view, keywords, instruction),
        )
    return context_name


def sync_schema_metadata(conn, domain: str, contract: dict) -> int:
    """Column metadata for all feed tables (delete + reinsert = idempotent)."""
    count = 0
    for dataset in contract["datasets"]:
        table = f"feed_{domain}_{dataset['name']}"
        conn.execute("DELETE FROM schema_metadata WHERE table_name = ?", (table,))
        keys = set(dataset.get("keys", []))
        for col in dataset["columns"]:
            is_summable = 1 if col["dtype"] == "double" else 0
            is_groupable = 1 if (col["dtype"] == "string" or col["name"] in keys) else 0
            desc = col.get("description") or ""
            if col.get("unit"):
                desc = f"{desc} (หน่วย: {col['unit']})".strip()
            conn.execute(
                "INSERT INTO schema_metadata (table_name, column_name, description, data_type, is_summable, is_groupable) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (table, col["name"], desc, col["dtype"], is_summable, is_groupable),
            )
            count += 1
    return count


def sync_documentation(conn, domain: str, contract: dict, context_name: str) -> int:
    """vanna_documentation entries — cleared and regenerated per run."""
    prefix = f"datafeed_{domain}_"
    conn.execute("DELETE FROM vanna_documentation WHERE doc_key LIKE ?", (f"{prefix}%",))
    docs = []

    def col_line(c: dict) -> str:
        line = f"- {c['name']} ({c['dtype']}): {c.get('description', '')}"
        if c.get("unit"):
            line += f" หน่วย: {c['unit']}"
        return line

    # Per-dataset: table, kind, grain, keys, approx rows
    for dataset in contract["datasets"]:
        table = f"feed_{domain}_{dataset['name']}"
        content = (
            f"ตาราง {table} ({dataset.get('kind', '')})\n"
            f"Grain: {dataset.get('grain', '')}\n"
            f"Keys: {', '.join(dataset.get('keys', []))}\n"
            f"จำนวนแถวโดยประมาณ: {dataset.get('row_count_built', 'n/a')}\n"
            + "\n".join(col_line(c) for c in dataset["columns"])
        )
        docs.append((f"{prefix}table_{dataset['name']}", f"ตาราง {table}", content))

        # Reserved word columns rule
        for col in dataset.get("reserved_word_columns", []):
            docs.append((
                f"{prefix}reserved_{dataset['name']}_{col}",
                f"Reserved word: {col}",
                f'คอลัมน์ {col} ในตาราง {table} เป็น reserved word ต้อง quote เป็น "{col}" เสมอ',
            ))

    # Business rules — the most important knowledge
    for rule in contract.get("business_rules", []):
        docs.append((f"{prefix}rule_{rule['id']}", f"กฎ: {rule['id']}", rule["text"]))

    # Period format rule
    docs.append((
        f"{prefix}period_format",
        "รูปแบบงวด year_month",
        f"คอลัมน์ {contract.get('period_key', 'year_month')} ในตาราง feed_{domain}_* เป็นงวด ค.ศ. รูปแบบ YYYYMM "
        f"(เช่น 202605 = พฤษภาคม 2026) — ถ้า user ถามปี พ.ศ. ให้แปลงเป็น ค.ศ. ก่อน (พ.ศ. - 543)",
    ))

    for doc_key, title, content in docs:
        conn.execute(
            "INSERT INTO vanna_documentation (doc_key, title, content, category, context_name, is_active) "
            "VALUES (?, ?, ?, 'datafeed', ?, 1)",
            (doc_key, title, content, context_name),
        )
    return len(docs)


def main():
    parser = argparse.ArgumentParser(description="Generate context + docs from DataFeed contract")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--contract", required=True, help="Path to contract yaml")
    args = parser.parse_args()

    contract = yaml.safe_load(Path(args.contract).read_text())
    conn = sqlite3.connect(_config_db_path(), timeout=60)
    try:
        context_name = register_context(conn, args.domain, contract)
        meta_count = sync_schema_metadata(conn, args.domain, contract)
        doc_count = sync_documentation(conn, args.domain, contract, context_name)
        conn.commit()
        print(f"Context '{context_name}' registered; {meta_count} metadata rows; {doc_count} docs")
    finally:
        conn.close()

    # Trigger brain sync so Vanna picks up the new documentation
    try:
        from app.api.v1.admin._shared import mark_brain_dirty
        mark_brain_dirty()
        print("Brain marked dirty — will re-sync")
    except Exception as e:
        print(f"WARN: mark_brain_dirty unavailable: {e}")


if __name__ == "__main__":
    main()

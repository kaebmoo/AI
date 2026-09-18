"""
DataFeed contract → context knowledge (Plan 7 Phase 2)
=======================================================
Moved from scripts/datafeed/gen_docs_from_contract.py so a file source keeps its
knowledge in step with its contract without anyone running a script:

- register_file_source syncs once at registration (same transaction as the registry)
- the resolver calls ensure_current() per request: one stat of the contract file;
  when the contract or the build's schema_version changed → re-sync + mark_brain_dirty

Writes (idempotent, delete + reinsert, one transaction): schema_contexts row
feed_<domain>, schema_metadata of feed_<domain>_*, vanna_documentation datafeed_<domain>_*.
Keywords and priority are set on insert only — an admin's routing edits survive re-syncs.
"""

import hashlib
import json
import logging
import os
import threading
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Router defaults, used on insert only (admin edits them afterwards). The router counts
# keyword substrings + priority*0.1, so a feed context wins over its legacy counterpart
# exactly when the question carries a feed marker: domain words match the same substrings
# as the legacy context ("ค่าใช้จ่าย" also hits "ค่า"/"จ่าย"), the marker adds 1, and
# priority 1 breaks the tie against legacy revenue's +1.0. No marker → legacy as before.
FEED_MARKERS = ["feed", "datafeed", "dashboard", "แดชบอร์ด"]
DOMAIN_KEYWORDS = {
    "revenue": ["รายได้", "revenue", "income"],
    "expense": ["ค่า", "ค่าใช้จ่าย", "จ่าย", "ค่าเสื่อม", "expense", "cost", "ต้นทุน", "spending"],
    "sales": ["ยอดขาย", "sales"],
    "ebt": ["ebt", "กำไร", "ขาดทุน", "profit", "ผลดำเนินงาน"],
}
FEED_PRIORITY = 1


def main_view_dataset(contract: dict) -> str:
    """The dataset the context is centred on: control totals' source, else the primary dataset."""
    return (contract.get("control_totals") or {}).get("source") or contract["primary_dataset"]


def register_context(conn, domain: str, contract: dict) -> str:
    """Upsert schema_contexts row for feed_<domain>."""
    context_name = f"feed_{domain}"
    main_view = f"feed_{domain}_{main_view_dataset(contract)}"
    rules_text = "\n".join(f"- {r['text']}" for r in contract.get("business_rules", []))
    instruction = (
        f"ข้อมูลจาก DataFeed (schema {contract['schema_version']}) — {contract.get('units', '')}\n"
        f"งวด ({contract.get('period_key', 'year_month')}) เป็น ค.ศ. รูปแบบ YYYYMM\n"
        f"กฎสำคัญ:\n{rules_text}"
    )
    params = {"name": context_name, "main_view": main_view, "desc": contract.get("title", ""),
              "instruction": instruction}
    updated = conn.execute(text(
        "UPDATE schema_contexts SET main_view=:main_view, description=:desc, instruction_th=:instruction, "
        "is_active=1, updated_at=CURRENT_TIMESTAMP WHERE name=:name"
    ), params).rowcount
    if not updated:
        keywords = DOMAIN_KEYWORDS.get(domain, []) + FEED_MARKERS
        conn.execute(text(
            "INSERT INTO schema_contexts (name, display_name, description, main_view, is_active, priority, "
            "keywords, instruction_th) VALUES (:name, :display, :desc, :main_view, 1, :priority, :keywords, :instruction)"
        ), {**params, "display": f"DataFeed {domain}", "priority": FEED_PRIORITY,
            "keywords": json.dumps(keywords, ensure_ascii=False)})
    if contract.get("scope_columns"):  # Phase 3: the owner declares what a caller's scope may filter on
        conn.execute(text("UPDATE schema_contexts SET scope_columns=:scope WHERE name=:name"),
                     {"scope": json.dumps(contract["scope_columns"], ensure_ascii=False), "name": context_name})
    return context_name


def sync_schema_metadata(conn, domain: str, contract: dict) -> int:
    """Column metadata for all feed tables (delete + reinsert = idempotent)."""
    count = 0
    for dataset in contract["datasets"]:
        table = f"feed_{domain}_{dataset['name']}"
        conn.execute(text("DELETE FROM schema_metadata WHERE table_name = :t"), {"t": table})
        keys = set(dataset.get("keys", []))
        for col in dataset["columns"]:
            is_summable = 1 if col["dtype"] == "double" else 0
            is_groupable = 1 if (col["dtype"] == "string" or col["name"] in keys) else 0
            desc = col.get("description") or ""
            if col.get("unit"):
                desc = f"{desc} (หน่วย: {col['unit']})".strip()
            conn.execute(text(
                "INSERT INTO schema_metadata (table_name, column_name, description, data_type, is_summable, is_groupable) "
                "VALUES (:t, :c, :d, :dt, :s, :g)"
            ), {"t": table, "c": col["name"], "d": desc, "dt": col["dtype"], "s": is_summable, "g": is_groupable})
            count += 1
    return count


def sync_documentation(conn, domain: str, contract: dict, context_name: str) -> int:
    """vanna_documentation entries — cleared and regenerated per run."""
    prefix = f"datafeed_{domain}_"
    conn.execute(text("DELETE FROM vanna_documentation WHERE doc_key LIKE :p"), {"p": f"{prefix}%"})
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
        conn.execute(text(
            "INSERT INTO vanna_documentation (doc_key, title, content, category, context_name, is_active) "
            "VALUES (:k, :t, :c, 'datafeed', :ctx, 1)"
        ), {"k": doc_key, "t": title, "c": content, "ctx": context_name})
    return len(docs)


def sync_knowledge(conn, domain: str, contract: dict) -> Tuple[str, int, int]:
    """Context + metadata + docs for one domain, on the caller's transaction."""
    context_name = register_context(conn, domain, contract)
    return (context_name, sync_schema_metadata(conn, domain, contract),
            sync_documentation(conn, domain, contract, context_name))


def knowledge_key(contract_bytes: bytes, schema_version: Any) -> str:
    """What the knowledge was generated from: contract content + the build's schema_version."""
    return f"{hashlib.sha256(contract_bytes).hexdigest()[:16]}:{schema_version}"


def load_contract(path: str) -> Tuple[dict, bytes]:
    with open(path, "rb") as f:
        raw = f.read()
    return yaml.safe_load(raw), raw


def mark_brain_dirty() -> None:
    try:
        from app.api.v1.admin._shared import mark_brain_dirty as _mark
        _mark()
    except Exception as e:  # the knowledge itself is committed; only the Sync Brain hint is lost
        logger.warning(f"mark_brain_dirty unavailable: {e}")


def sync_from_contract(config_engine, source_name: str, contract_path: str, schema_version: Any) -> bool:
    """Re-sync unless the stored key already matches. True = this call re-synced.

    Compare-and-set in the knowledge transaction: of several processes noticing the same
    change, one re-syncs and the rest find the new key (SQLite serialises the writers).
    """
    contract, raw = load_contract(contract_path)
    domain = contract["domain"]
    if source_name != f"datafeed_{domain}":  # never let one source rewrite another context
        raise ValueError(f"contract {contract_path} is domain '{domain}', not source '{source_name}'")
    key = knowledge_key(raw, schema_version)
    with config_engine.begin() as conn:
        won = conn.execute(text(
            "UPDATE data_sources SET knowledge_sha = :key, updated_at = CURRENT_TIMESTAMP "
            "WHERE name = :name AND (knowledge_sha IS NULL OR knowledge_sha != :key)"
        ), {"key": key, "name": source_name}).rowcount
        if not won:
            return False
        context_name, n_meta, n_docs = sync_knowledge(conn, domain, contract)
    logger.info(f"Knowledge of {context_name} re-synced from {contract_path} "
                f"(schema {contract.get('schema_version')}, key {key}): {n_meta} metadata, {n_docs} docs")
    mark_brain_dirty()
    return True


_seen: Dict[str, tuple] = {}  # source name → (contract stat, build schema_version) checked by this process
_seen_lock = threading.Lock()


def _stat(path: str):
    try:
        st = os.stat(path)
        return st.st_ino, st.st_size, st.st_mtime_ns
    except OSError:
        return None


def ensure_current(config_engine, source: Mapping[str, Any], manifest: Optional[dict]) -> bool:
    """Per request: a stat of the contract; re-sync only when it or the build's schema changed.

    Never raises — a failed re-sync leaves the previous knowledge in place (logged).
    """
    path = source.get("contract_file")
    if not path:
        return False
    marker = (_stat(path), (manifest or {}).get("schema_version"))
    name = source["name"]
    if _seen.get(name) == marker:
        return False
    with _seen_lock:
        previous = _seen.get(name)
        if previous == marker:
            return False
        changed = False
        try:
            changed = sync_from_contract(config_engine, name, path, marker[1])
        except Exception:
            logger.exception(f"Knowledge re-sync of source '{name}' failed — keeping previous knowledge")
        _seen[name] = marker  # also on failure: retried when the contract/build changes again
    if previous is not None:
        # Answers this process cached were made with the previous knowledge, and on the same
        # build the source-version check would still serve them — whichever process re-synced,
        # each clears its own cache. (previous None = first sight: nothing of it cached yet.)
        from app.services.query_engine import clear_query_cache
        clear_query_cache()
    return changed

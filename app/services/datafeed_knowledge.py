"""
DataFeed contract → context knowledge (Plan 7 Phase 2)
=======================================================
Moved from scripts/datafeed/gen_docs_from_contract.py so a file source keeps its
knowledge in step with its contract without anyone running a script:

- register_file_source syncs once at registration (same transaction as the registry)
- the resolver calls ensure_current() per request: one stat of the contract file;
  when the contract or the build's schema_version changed → re-sync + mark_brain_dirty

Writes (idempotent, one transaction): schema_contexts row feed_<domain>, schema_metadata of feed_<domain>_*,
vanna_documentation datafeed_<domain>_* — as `declared` (Plan 8.1, app/services/provenance.py): the contract replaces
its own earlier declaration and what a machine wrote, only where a value changed; a row a person changed keeps their
version and the contract's waits in knowledge_proposals (D-C). Keywords, priority, display name, workspace and on/off
are the admin's: set on insert only. What a new contract no longer declares goes — the contract's own rows only.
"""

import hashlib
import json
import logging
import os
import threading
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml
from sqlalchemy import text

from app.services.provenance import DECLARED, may_replace, propose

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
WAITS = "คนแก้ส่วนที่ contract ประกาศไว้ — ฉบับใหม่ของ contract รอคนตัดสิน (D-C)"


def _declare(conn, table: str, key: Dict[str, Any], values: Dict[str, Any], row: Optional[Mapping],
             insert: Dict[str, Any], stamp: bool = False) -> None:
    """Write the contract's `values` for the row at `key` (`row` = what is there, None = nothing) by the one rule."""
    if row is None:
        cols = {**key, **values, **insert, "source": DECLARED}
        conn.execute(text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"), cols)
        return
    changed = {c: v for c, v in values.items() if row[c] != v}
    if may_replace(DECLARED, row["source"], row["status"]):
        if changed or row["source"] != DECLARED:  # nothing changed = nothing written (no timestamp moves)
            sets = ", ".join([f"{c} = :{c}" for c in changed] + ["source = :source"]
                             + (["updated_at = CURRENT_TIMESTAMP"] if stamp and changed else []))
            where = " AND ".join(f"{c} = :k_{c}" for c in key)
            conn.execute(text(f"UPDATE {table} SET {sets} WHERE {where}"),
                         {**changed, "source": DECLARED, **{f"k_{c}": v for c, v in key.items()}})
    elif changed:  # a person's row that already says what the contract says: nothing waits
        propose(conn, table, key, values, DECLARED, reason=WAITS)


def main_view_dataset(contract: dict) -> str:
    """The dataset the context is centred on: control totals' source, else the primary dataset."""
    return (contract.get("control_totals") or {}).get("source") or contract["primary_dataset"]


def tables_section(domain: str, contract: dict) -> str:
    """Every table of a multi-dataset contract, by the name the model must use. The system prompt
    describes the main view only, so without this a question only another table can answer (ebt per
    cost center, full-year targets) was answered from the main view — wrongly — or not at all.
    Naming a table here is also what makes it usable (hybrid_flow.table_rule) and lets Pass 1 name
    a filter on its columns (intent_table_hint / the dropped-filter guard)."""
    if len(contract["datasets"]) < 2:
        return ""
    main = main_view_dataset(contract)
    lines = []
    for d in contract["datasets"]:
        role = " (ตารางหลัก — ใช้ตอบก่อนถ้าตอบได้)" if d["name"] == main else ""
        lines.append(f"- feed_{domain}_{d['name']}{role}: {d.get('kind', '')} | grain: {d.get('grain', '')} | "
                     f"คอลัมน์: {', '.join(c['name'] for c in d['columns'])}")
    return ("ตารางของ context นี้ (อ้างชื่อเต็มตามนี้; ตารางอื่นใช้เมื่อกฎข้างล่างสั่ง หรือเมื่อคำถามต้องใช้ "
            "คอลัมน์/grain ที่ตารางหลักไม่มี — ห้ามตอบจากตารางหลักโดยทิ้งเงื่อนไขของคำถาม):\n" + "\n".join(lines) + "\n")


def register_context(conn, domain: str, contract: dict) -> str:
    """Upsert schema_contexts row for feed_<domain>."""
    context_name = f"feed_{domain}"
    main_view = f"feed_{domain}_{main_view_dataset(contract)}"
    rules_text = "\n".join(f"- {r['text']}" for r in contract.get("business_rules", []))
    period_key = contract.get("period_key", "year_month")
    period_line = f"งวด ({period_key}) เป็น ค.ศ. รูปแบบ YYYYMM"
    if not any(c["name"] == "year" for d in contract["datasets"] for c in d["columns"]):
        # the generic prompt talks in year + month; say how that maps onto the only period column
        period_line += (f" — ไม่มีคอลัมน์ year / month: กรองเวลาด้วย {period_key} = ปี ค.ศ. × 100 + เดือน เท่านั้น "
                        f"(ปี พ.ศ. ต้องลบ 543 ก่อน: มกราคม พ.ศ. 2568 = ค.ศ. 2025 → {period_key} = 202501, "
                        f"ทั้งปี ค.ศ. 2025 → {period_key} BETWEEN 202501 AND 202512)")
    instruction = (
        f"ข้อมูลจาก DataFeed (schema {contract['schema_version']}) — {contract.get('units', '')}\n"
        f"{period_line}\n"
        f"{tables_section(domain, contract)}"
        f"กฎสำคัญ:\n{rules_text}"
    )
    # `description` is the owner's sentence about what this feed answers and what it does not
    # ("EBT ของ 2 สายงานขาย — ไม่ใช่กำไรของทั้งบริษัท"); `title` is a label ("NT EBT Data Feed").
    # The description is what the cross-context splitter and list_contexts read, so prefer it —
    # on one line, because the splitter lists one context per line.
    description = " ".join((contract.get("description") or contract.get("title") or "").split())
    values = {"main_view": main_view, "description": description, "instruction_th": instruction}
    if contract.get("scope_columns"):  # Phase 3: the owner declares what a caller's scope may filter on
        values["scope_columns"] = json.dumps(contract["scope_columns"], ensure_ascii=False)
    row = conn.execute(text("SELECT source, status, main_view, description, instruction_th, scope_columns "
                            "FROM schema_contexts WHERE name = :name"), {"name": context_name}).mappings().first()
    _declare(conn, "schema_contexts", {"name": context_name}, values, row, stamp=True, insert={
        "display_name": f"DataFeed {domain}", "is_active": 1, "priority": FEED_PRIORITY, "status": "active",
        "keywords": json.dumps(DOMAIN_KEYWORDS.get(domain, []) + FEED_MARKERS, ensure_ascii=False)})
    return context_name


def sync_schema_metadata(conn, domain: str, contract: dict) -> int:
    """Column metadata for all feed tables — declared, by the one rule (idempotent: unchanged = not written)."""
    count = 0
    # The contract declares how each measure may be aggregated (control_totals.measures): `agg: sum`
    # adds up, `agg: point_in_time` does not — revenue_ytd is the year to date AT that period, and
    # adding the periods gives several times the real figure (so does ebt's `ebt` / `expense`).
    # Summability was derived from the dtype alone, which said the opposite of the column's own
    # description, and a portal question came back with SUM(revenue_ytd) = 115,090 MB against a real
    # 26,036 MB even though the prompt already carried the rule in words (RESULT_F11 §7).
    # Contracts 2.3.2 / 1.2.2 / 1.3.2 / 1.4.2 carry `agg` on the column itself, which is where it
    # belongs — control_totals only lists the measures it reconciles, so fact_ebt.amount_ytd was
    # point-in-time in its description and nowhere a reader could see it. Column first, then the
    # reconciled measures (older contracts), then "sum".
    agg = {m["name"]: m.get("agg") for m in (contract.get("control_totals") or {}).get("measures", [])
           if m.get("name")}
    for dataset in contract["datasets"]:
        table = f"feed_{domain}_{dataset['name']}"
        existing = {r["column_name"]: r for r in conn.execute(text(
            "SELECT column_name, source, status, description, data_type, is_summable, is_groupable "
            "FROM schema_metadata WHERE table_name = :t"), {"t": table}).mappings()}
        keys = set(dataset.get("keys", []))
        for col in dataset["columns"]:
            summable_agg = (col.get("agg") or agg.get(col["name"], "sum")) == "sum"
            is_summable = 1 if (col["dtype"] == "double" and summable_agg) else 0
            is_groupable = 1 if (col["dtype"] == "string" or col["name"] in keys) else 0
            desc = col.get("description") or ""
            if col.get("unit"):
                desc = f"{desc} (หน่วย: {col['unit']})".strip()
            _declare(conn, "schema_metadata", {"table_name": table, "column_name": col["name"]},
                     {"description": desc, "data_type": col["dtype"], "is_summable": is_summable,
                      "is_groupable": is_groupable}, existing.get(col["name"]), insert={"status": "active"})
            count += 1
        declared = {c["name"] for c in dataset["columns"]}
        for name, row in existing.items():  # what the contract no longer declares: its own rows go, a person's stay
            if name not in declared and row["source"] == DECLARED:
                conn.execute(text("DELETE FROM schema_metadata WHERE table_name = :t AND column_name = :c"),
                             {"t": table, "c": name})
    return count


def sync_documentation(conn, domain: str, contract: dict, context_name: str) -> int:
    """vanna_documentation entries — declared, by the one rule; a doc the contract no longer yields goes."""
    prefix = f"datafeed_{domain}_"
    existing = {r["doc_key"]: r for r in conn.execute(text(
        "SELECT doc_key, source, status, title, content, category, context_name FROM vanna_documentation "
        "WHERE doc_key LIKE :p"), {"p": f"{prefix}%"}).mappings()}
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
        _declare(conn, "vanna_documentation", {"doc_key": doc_key},
                 {"title": title, "content": content, "category": "datafeed", "context_name": context_name},
                 existing.get(doc_key), insert={"is_active": 1, "status": "active"})
    kept = {d[0] for d in docs}
    for doc_key, row in existing.items():
        if doc_key not in kept and row["source"] == DECLARED:
            conn.execute(text("DELETE FROM vanna_documentation WHERE doc_key = :k"), {"k": doc_key})
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

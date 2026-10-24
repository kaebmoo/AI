"""Deterministic column descriptions that wait for a person in the proposal queue."""

import json

from duckdb import Error as DuckDBError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.services import data_sources
from app.services.context_onboarding import DataInspector
from app.services.database_adapter import SourceUnavailable
from app.services.datafeed_knowledge import load_contract
from app.services.provenance import INFERRED, REJECTED, propose


def _quoted(name):
    return '"' + name.replace('"', '""') + '"'


def _file_engine(conn, context):
    source = conn.execute(text(
        "SELECT ds.id, ds.name, ds.root_path, ds.manifest_file FROM data_sources ds "
        "JOIN schema_contexts sc ON sc.source_id = ds.id WHERE sc.name = :c AND ds.is_active = 1"
    ), {"c": context}).mappings().one()
    tables = [dict(r) for r in conn.execute(text(
        "SELECT table_name, file_name, columns FROM source_tables "
        "WHERE source_id = :sid AND is_active = 1 ORDER BY table_name"
    ), {"sid": source["id"]}).mappings()]
    for table in tables:
        table["columns"] = json.loads(table["columns"])
    # for_context() also syncs contract knowledge; drafting must never change the rows in use.
    return data_sources.source_resolver._adapter(
        source["name"], source["root_path"], tables, source["manifest_file"]).engine


def _dataset(conn, context, table):
    row = conn.execute(text(
        "SELECT ds.contract_file FROM schema_contexts sc "
        "JOIN data_sources ds ON ds.id = sc.source_id WHERE sc.name = :c"
    ), {"c": context}).first()
    if not row or not row[0]:
        return {}
    try:
        contract, _ = load_contract(row[0])
    except FileNotFoundError:
        return {}
    return next((d for d in contract.get("datasets", [])
                 if f"feed_{contract['domain']}_{d['name']}" == table), {})


def _value_facts(inspector, conn, table, columns, levels=(), context=None):
    facts = {c.name: {} for c in columns}
    labels = {r["level_label_th"] for r in levels if r["level_label_th"]}
    own_levels = {r["level_label_th"]: r["level"] + 1 for r in levels if r["context_name"] == context}
    for col in columns:
        values = col.all_distinct
        if values is None:
            values = [r["value"] for r in inspector._execute(conn,
                f'SELECT DISTINCT {_quoted(col.name)} AS value FROM {_quoted(table)} '
                f'WHERE {_quoted(col.name)} IS NOT NULL')]
        # The inspector omits empty strings; they still count in the prefix denominator.
        elif col.has_empty_values and "" not in values:
            values = [*values, ""]
        strings = [v for v in values if isinstance(v, str)]
        candidates = labels | {v.split()[0] for v in strings if v.split()}
        for word in sorted(candidates, key=lambda word: (-len(word), word)):
            count = sum(v.startswith(word) for v in strings)
            if count < 2:
                continue
            share = count / len(strings)
            if share >= 0.6:
                facts[col.name]["prefix"] = {"word": word, "share": share}
                if word in own_levels:
                    facts[col.name]["prefix"]["level_number"] = own_levels[word]
                break
        if ("INT" in col.data_type.upper() and values
                and all(isinstance(v, int) and not isinstance(v, bool) for v in values)):
            period = {"min": min(values), "max": max(values)}
            if all(1900 <= v // 100 <= 2999 and 1 <= v % 100 <= 12 for v in values):
                facts[col.name]["period"] = period
            elif col.is_time_column:
                for kind, low, high in (("month", 1, 12), ("year_ce", 1900, 2399), ("year_be", 2400, 2799)):
                    if low <= period["min"] <= period["max"] <= high:
                        facts[col.name]["period"] = {**period, "kind": kind}
                        break

    names = set(facts)
    for name in sorted(names):
        for suffix, role in (("_fname", "full name"), ("_sname", "short name"),
                             ("_short_name", "short name"), ("_abbr", "short name")):
            # Name siblings can pair even when the bare base column is absent.
            base = name[:-len("_fname")] if name.endswith("_fname") and role == "short name" else name
            other = base + suffix
            if other not in names or other == name:
                continue
            a, b, t = _quoted(name), _quoted(other), _quoted(table)
            row = inspector._execute(conn,
                f'SELECT COUNT(DISTINCT {a}) AS a, COUNT(DISTINCT {b}) AS b, '
                f'(SELECT COUNT(*) FROM (SELECT DISTINCT {a}, {b} FROM {t} '
                f'WHERE {a} IS NOT NULL AND {b} IS NOT NULL) AS pairs) AS pairs '
                f'FROM {t} WHERE {a} IS NOT NULL AND {b} IS NOT NULL').fetchone()
            if row["a"] > 0 and row["a"] == row["b"] == row["pairs"]:
                facts[other].setdefault("pair", []).append({"column": name, "role": role, "is_name": True})
                facts[name].setdefault("pair", []).append({"column": other, "role": role, "is_name": False})
    return facts


def _description(facts):
    parts = []
    if "level" in facts:
        f = facts["level"]
        parts.append(f"{f['label']} — ระดับ {f['number']} ของโครงสร้าง: {' > '.join(f['chain'])}")
    for f in facts.get("pair", []):
        role = "ชื่อเต็ม" if f["role"] == "full name" else "ชื่อย่อ"
        parts.append(f"{role}ของ {f['column']} (คู่ 1:1)" if f["is_name"]
                     else f"คู่{role}: {f['column']} (คู่ 1:1)")
    if "prefix" in facts:
        f = facts["prefix"]
        note = (f" — ตรงกับชื่อระดับ '{f['word']}' (ระดับ {f['level_number']}) ของโครงสร้าง"
                if "level_number" in f else "")
        parts.append(f"ค่าส่วนใหญ่ขึ้นต้นด้วย '{f['word']}' ({f['share']:.0%}){note}")
    if "period" in facts:
        f = facts["period"]
        if f.get("kind") == "month":
            parts.append("เดือน (1–12)")
        else:
            label = {"year_ce": "ปี ค.ศ.", "year_be": "ปี พ.ศ."}.get(f.get("kind"), "งวด ค.ศ. YYYYMM")
            parts.append(f"{label} ช่วง {f['min']}–{f['max']}")
    if "key" in facts:
        others = facts["key"]
        parts.append("เป็นส่วนของคีย์ของตาราง" + (f" (ร่วมกับ {', '.join(others)})" if others else ""))
    if "measure" in facts:
        f = facts["measure"]
        if f.get("agg") == "point_in_time":
            parts.append("ยอดสะสม ณ งวดนั้น ห้าม SUM ข้ามงวด")
        elif f.get("agg") == "sum":
            parts.append("SUM ข้ามงวดได้")
        if f.get("unit"):
            parts.append(f"หน่วย: {f['unit']}")
    return "; ".join(parts)


def draft_columns(config_conn, table):
    """File proposals only; the caller owns the config transaction."""
    rows = config_conn.execute(text(
        "SELECT column_name, description, status FROM schema_metadata WHERE table_name = :t ORDER BY column_name"
    ), {"t": table}).mappings().all()
    if not rows:
        raise LookupError("Table metadata not found")

    owner = data_sources.registered_tables(config_conn.engine).get(table)
    context = owner["context"] if owner else config_conn.execute(text(
        "SELECT name FROM schema_contexts WHERE main_view = :t ORDER BY is_active DESC, id LIMIT 1"
    ), {"t": table}).scalar()
    dataset = _dataset(config_conn, context, table)
    declared = {c["name"]: c for c in dataset.get("columns", [])}
    all_levels = config_conn.execute(text(
        "SELECT context_name, level, level_label_th, level_columns FROM master_hierarchy "
        "WHERE status = 'active' AND is_active = 1 ORDER BY context_name, level"
    )).mappings().all()
    levels = [r for r in all_levels if r["context_name"] == context]
    chain = [r["level_label_th"] for r in levels]
    level_facts = {c: {"number": r["level"] + 1, "label": r["level_label_th"], "chain": chain}
                   for r in levels for c in json.loads(r["level_columns"])}
    values_allowed = data_sources.policy_for_table(table, config_conn.engine) == "full"
    try:
        inspector = DataInspector(_file_engine(config_conn, context) if owner else settings.BUSINESS_DB_PATH)
        profile = inspector.inspect(table)
        value_facts = {}
        if values_allowed:
            conn = inspector._connect()
            try:
                value_facts = _value_facts(inspector, conn, table, profile.columns, all_levels, context)
            finally:
                conn.close()
    except (OSError, SQLAlchemyError, DuckDBError, ValueError) as exc:
        if owner:
            raise SourceUnavailable("File source unavailable") from exc
        raise

    result = {"table": table, "drafted": 0, "skipped": [], "drafts": []}
    for row in rows:
        name = row["column_name"]
        reason = None
        if row["status"] == REJECTED:
            reason = "แถวถูกปฏิเสธ"
        elif (row["description"] or "").strip():
            reason = "มีคำอธิบายแล้ว"
        if reason:
            result["skipped"].append({"column_name": name, "reason": reason})
            continue
        facts = value_facts.get(name, {}).copy()
        if name in level_facts:
            facts["level"] = level_facts[name]
        keys = dataset.get("keys", [])
        if name in keys:
            facts["key"] = [k for k in keys if k != name]
        col = declared.get(name, {})
        agg, dtype = col.get("agg"), col.get("dtype", "").upper()
        numeric = any(t in dtype for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL"))
        measure = {k: col[k] for k in ("agg", "dtype", "unit") if k in col}
        if agg != "point_in_time" and not (agg == "sum" and numeric):
            measure.pop("agg", None)
        if measure.get("agg") or measure.get("unit"):
            facts["measure"] = measure
        description = _description(facts)
        if not description:
            result["skipped"].append({"column_name": name, "reason": "ไม่มีข้อเท็จจริงเพียงพอ"})
            continue
        result["drafted"] += propose(config_conn, "schema_metadata", {"table_name": table, "column_name": name},
                                     {"description": description}, INFERRED,
                                     confidence=min(0.95, 0.5 + len(facts) * 0.1),
                                     reason="ร่างจากข้อเท็จจริงในโปรไฟล์ข้อมูลและ contract")
        result["drafts"].append({"column_name": name, "description": description, "facts": facts})
    return result

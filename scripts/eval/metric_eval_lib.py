"""Generate Thai metric questions and compiler-backed parquet oracles.

Usage: import generate, or run python -m scripts.eval.gen_metric_questions --help.
"""

from dataclasses import asdict, fields
import json
from pathlib import Path

import duckdb

from app.services.ai import metric_compiler
from app.services.ai.metric_compiler import CompileRequest, Metric


THAI_MONTHS = (
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
)
DESC_TEMPLATES = (
    "{label}ไหนมี{word} {period}สูงสุด {n} อันดับ",
    "ขอ {n} อันดับ{label}ที่มี{word}มากที่สุด {period}",
    "แสดง{word}สูงสุด {n} อันดับ แยกตาม{label} {period}",
)
ASC_TEMPLATES = (
    "{label}ไหนมี{word} {period}ต่ำสุด {n} อันดับ",
    "ขอ {n} อันดับ{label}ที่มี{word}น้อยที่สุด {period}",
    "แสดง{word}ต่ำสุด {n} อันดับ แยกตาม{label} {period}",
)
TEMPLATES = {
    "total": (
        "{word} {period}เท่าไหร่",
        "ขอยอดรวม{word} {period}",
        "ช่วยสรุป{word}ทั้งหมด {period}",
    ),
    "by": (
        "{word}แยกตาม{label} {period}",
        "ขอ{word}ของแต่ละ{label} {period}",
        "ช่วยสรุป{word}จำแนกตาม{label} {period}",
    ),
    "filter": (
        "{word} ของ{value} {period}เท่าไหร่",
        "ขอ{word}เฉพาะ{value} {period}",
        "ช่วยสรุป{word}สำหรับ{value} {period}",
    ),
    "top5_desc": DESC_TEMPLATES,
    "top5_asc": ASC_TEMPLATES,
    "top10_desc": DESC_TEMPLATES,
    "top10_asc": ASC_TEMPLATES,
}


def contract_metrics(contract: dict) -> list[Metric]:
    """Convert declarations exactly as the compiler's contract fixture does."""
    metrics = []
    prefix = f"feed_{contract['domain']}_"
    for declaration in contract["metrics"]:
        values = {f.name: declaration.get(f.name) for f in fields(Metric)}
        values["metric_id"] = declaration["id"]
        values["synonyms"] = tuple(values["synonyms"] or ())
        values["dimensions"] = tuple(values["dimensions"]) if values["dimensions"] is not None else None
        values["terms"] = values["terms"] or {}
        if values["dataset"] is not None:
            values["dataset"] = prefix + values["dataset"]
        if values["official_total"] is not None:
            total = values["official_total"]
            values["official_total"] = {**total, "dataset": prefix + total["dataset"]}
        metrics.append(Metric(**values))
    return metrics


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def open_dist(dist_dir: Path, domain: str):
    """Open safely quoted parquet views; the caller closes the connection."""
    if not dist_dir.is_dir():
        raise ValueError(f"Missing dist directory: {dist_dir}")
    conn = duckdb.connect(":memory:", config={"threads": 1})
    try:
        for path in sorted(dist_dir.glob("*.parquet")):
            table = _identifier(f"feed_{domain}_{path.stem}")
            conn.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({_literal(str(path))})")
    except Exception:
        conn.close()
        raise
    return conn


def _phrases(metric: Metric, shape: str, mode: str, period: int, label: str,
             value: str | None, n: int | None, count: int) -> list[str]:
    words = []
    seen = set()
    for word in (metric.name_th, *metric.synonyms):
        if word.casefold() not in seen:
            seen.add(word.casefold())
            words.append(word)
    month, year = THAI_MONTHS[period % 100 - 1], period // 100 + 543
    periods = (f"สะสมปี {year}", f"ตั้งแต่ต้นปีถึง{month} {year}", f"ยอดสะสม ณ {month} {year}")
    templates = TEMPLATES[shape]
    if shape == "filter" and not value.startswith(label):
        value = f"{label} {value}"
    phrases = []
    for i in range(count):
        time = f"เดือน{month} {year}" if mode == "month" else periods[i % len(periods)]
        phrase = templates[i % len(templates)].format(
            word=words[i % len(words)], period=time, label=label, value=value, n=n,
        )
        if phrase in phrases:
            phrase = f"ขอสอบถามข้อ {i + 1}: {phrase}"
        phrases.append(phrase)
    return phrases


def generate(contract: dict, dist_dir: Path, period: int, *, phrasings: int = 3,
             max_rows: int = 50, contract_name: str = "") -> dict:
    """Build shape × metric × mode × dimension cases using only compiler SQL."""
    if type(period) is not int or not 100001 <= period <= 999912 or not 1 <= period % 100 <= 12:
        raise ValueError("period must be YYYYMM with a month from 1 to 12")
    if type(phrasings) is not int or phrasings < 3:
        raise ValueError("phrasings must be an integer >= 3")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("max_rows must be a positive integer")
    domain = contract["domain"]
    prefix = f"feed_{domain}_"
    resolved = metric_compiler.resolve(contract_metrics(contract))
    for metric in resolved.values():
        path = dist_dir / f"{metric.dataset.removeprefix(prefix)}.parquet"
        if not path.is_file():
            raise ValueError(f"Missing metric dataset parquet: {path}")
    manifest_path = dist_dir / "manifest.json"
    result = {
        "about": "สร้างคำถามจาก metrics ของสัญญาข้อมูล; คำตอบคาดหวัง = compiler บน parquet; ตัวรัน: scripts/eval/run_metric_eval.py",
        "context": f"feed_{domain}", "scope": None,
        "request": {"include_data": True, "include_sql": True, "max_rows": max_rows, "source": "eval"},
        "oracle_build": {
            "period": period, "contract": contract_name, "schema_version": contract.get("schema_version"),
            "manifest": json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None,
        },
        "skipped": [], "questions": [],
    }
    descriptions = {
        dataset["name"]: {column["name"]: column.get("description") or column.get("desc")
                          for column in dataset.get("columns", [])}
        for dataset in contract.get("datasets", [])
    }
    conn = open_dist(dist_dir, domain)
    try:
        for metric in resolved.values():
            columns = {row[0]: row[1] for row in conn.execute(f"DESCRIBE {_identifier(metric.dataset)}").fetchall()}
            kept, excluded = [], []
            for dim in metric.dimensions or ():
                if dim not in columns:
                    reason = "missing_column"
                elif columns[dim].upper().split("(")[0] not in ("VARCHAR", "CHAR", "BPCHAR", "TEXT", "STRING"):
                    reason = "not_string"
                elif any(dim.endswith(suffix) and dim[:-len(suffix)] in metric.dimensions
                         for suffix in ("_fname", "_sname", "_short_name")):
                    reason = "name_column"
                else:
                    kept.append(dim)
                    continue
                excluded.append((dim, reason))
            labels = descriptions.get(metric.dataset.removeprefix(prefix), {})
            official_ok = bool(metric.official_total and (
                dist_dir / f"{metric.official_total['dataset'].removeprefix(prefix)}.parquet"
            ).is_file())
            values = {}
            for dim in kept:
                column = _identifier(dim)
                sql = (f"SELECT DISTINCT {column} FROM {_identifier(metric.dataset)} "
                       f"WHERE CAST({_identifier(metric.period['column'])} AS INTEGER) = {period} "
                       f"AND {column} IS NOT NULL AND TRIM({column}) <> '' ORDER BY {column}")
                items = [row[0] for row in conn.execute(sql).fetchall()]
                values[dim] = [items[i] for i in sorted({0, len(items) // 2, len(items) - 1})] if items else []
            for mode in ("month", "cumulative"):
                for dim, reason in excluded:
                    result["skipped"].append({"metric_id": metric.metric_id, "mode": mode,
                                              "dimension": dim, "shape": None, "reason": reason})

                def add(shape, dim=None, value=None, order_desc=None, limit=None):
                    class_id = f"{shape}:{metric.metric_id}:{mode}" + (f":{dim}" if dim else "")
                    req = CompileRequest(
                        metric.metric_id, period, mode, dimensions=(dim,) if dim and shape != "filter" else (),
                        filters=({"column": dim, "operator": "=", "value": value},) if shape == "filter" else (),
                        order_desc=order_desc, limit=limit, official_total_ok=official_ok,
                    )
                    try:
                        rows = conn.execute(metric_compiler.compile(req, resolved).sql).fetchall()
                        expected = [dict(zip(req.dimensions, row[:len(req.dimensions)]),
                                         value=round(float(row[-1]), 2) if row[-1] is not None else None) for row in rows]
                    except Exception as exc:
                        raise ValueError(f"{class_id}: {exc}") from exc
                    if shape == "by" and len(rows) > max_rows:
                        result["skipped"].append({"metric_id": metric.metric_id, "mode": mode, "dimension": dim,
                                                  "shape": shape, "reason": "rows>max_rows", "rows": len(rows)})
                        return
                    if order_desc is None:
                        expected.sort(key=lambda row: tuple((row[d] is not None, row[d] or "") for d in req.dimensions))
                    desc = labels.get(dim)
                    label = desc.split(" — ")[0].split(";")[0].strip() if desc else dim
                    request = asdict(req)
                    request["dimensions"] = list(req.dimensions)
                    request["filters"] = list(req.filters)
                    for phrase in _phrases(metric, shape, mode, period, label, value, limit, phrasings):
                        result["questions"].append({
                            "id": f"M{len(result['questions']) + 1:04d}", "question": phrase,
                            "time_in_question": True, "class": class_id, "shape": shape,
                            "metric_id": metric.metric_id, "mode": mode, "dimension": dim, "unit": metric.unit,
                            "ordered": order_desc is not None, "request": request, "expected_rows": expected,
                        })

                add("total")
                for dim in kept:
                    add("by", dim)
                    for value in values[dim]:
                        add("filter", dim, value)
                    for n in (5, 10):
                        for desc in (True, False):
                            add(f"top{n}_{'desc' if desc else 'asc'}", dim, order_desc=desc, limit=n)
    finally:
        conn.close()
    return result

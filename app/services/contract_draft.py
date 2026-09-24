"""Draft a data contract from the data itself (Plan 8 §9.3 step 1).

Reads a bundle of files (CSV / parquet) read-only with DuckDB and proposes what a contract declares:
datasets, columns, fact or dim, keys, measures and how they add up (sum or a year-to-date balance),
foreign keys, hierarchies, the scope columns, columns whose values must not be added together, and —
across bundles — relationships found by reconciling totals cell by cell. Every proposal carries its
evidence; what the data cannot prove becomes a question for the owner (`draft.questions`).

No LLM and no row leaves the process: every check is an aggregate query, and the draft holds column
names, counts, totals and the few values a question needs to be answerable. The output has the shape of
the contracts NT-Report writes (DataFeed/contracts/*.yaml), so the pipeline that reads those
(`datafeed_knowledge`) reads a confirmed draft the same way.
"""
from __future__ import annotations

import itertools
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

INT_TYPES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT")
FLOAT_TYPES = ("FLOAT", "REAL", "DOUBLE")
SKIP_FILES = {"control_totals", "manifest"}
PERIOD_NAME = re.compile(r"time|month|period|ym|effective|งวด", re.I)
KEY_NAME = re.compile(r"(code|key|_id|^id|_no|_seq|number|center|รหัส)$", re.I)
YTD_NAME = re.compile(r"ytd|cumul|accum|สะสม", re.I)
SCENARIO_VALUE = re.compile(r"^(actual|target|budget|plan|forecast|fcst|จริง|เป้า|งบ|ประมาณการ)", re.I)
TOTAL_VALUE = re.compile(r"^(รวม|total|subtotal|grand)", re.I)
NUMBER_PREFIX = re.compile(r"^\s*\d+(\.\d+)*\.?\s*")  # '04.Fixed…' / '4.Fixed…' / '8.2. รายได้อื่น' → the name
TOL_ABS = 1.0  # baht — the tolerance NT-Report's own control totals use
MAX_KEY_CANDIDATES = 10
MAX_LEVEL_VALUES = 12
FK_SHARE = 0.9      # an owner declares a key even when some codes are missing from the dim — the gap becomes a question
NEAR_UNIQUE = 0.99  # a dim with a few duplicate keys is still the dim the codes point at


def connect():
    """An in-memory DuckDB that reads the bundle files where they are — nothing is imported."""
    return duckdb.connect()


def q(con, sql: str) -> list:
    return con.execute(sql).fetchall()


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def norm(value: Any) -> str:
    """A label as two sources may spell it: case, spaces and a leading running number do not count."""
    return " ".join(NUMBER_PREFIX.sub("", str(value)).lower().split())


@dataclass
class Col:
    name: str
    type: str
    nulls: int
    distinct: int

    @property
    def is_float(self) -> bool:
        return self.type.startswith(FLOAT_TYPES) or self.type.startswith("DECIMAL")

    @property
    def is_int(self) -> bool:
        return self.type.startswith(INT_TYPES)

    @property
    def is_text(self) -> bool:
        return self.type == "VARCHAR"


@dataclass
class Dataset:
    name: str
    view: str
    path: Path
    rows: int = 0
    cols: Dict[str, Col] = field(default_factory=dict)
    period: Optional[str] = None
    measures: List[str] = field(default_factory=list)
    kind: str = "dim"
    keys: List[str] = field(default_factory=list)
    unique: bool = False
    key_ratio: float = 0.0
    agg: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    levels: List[Dict[str, Any]] = field(default_factory=list)
    fks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    hierarchies: List[List[str]] = field(default_factory=list)
    label_pairs: List[List[str]] = field(default_factory=list)

    def period_sql(self, alias: str = "") -> str:
        col = (alias + "." if alias else "") + ident(self.period)
        return col if self.cols[self.period].is_int else f"CAST({col} AS INTEGER)"

    def dims(self) -> List[str]:
        return [c for c in self.cols if c not in self.measures and c != self.period]


@dataclass
class Bundle:
    domain: str
    root: Path
    datasets: Dict[str, Dataset]
    primary: Optional[str] = None


# ── one bundle ─────────────────────────────────────────────


def bundle_files(root: Path) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    for p in sorted(Path(root).iterdir()):
        if p.is_file() and p.suffix in (".parquet", ".csv") and p.stem not in SKIP_FILES:
            if p.suffix == ".parquet" or p.stem not in files:  # parquet carries its types
                files[p.stem] = p
    return files


def load(con, root: Path, domain: str) -> Bundle:
    datasets = {}
    for stem, path in bundle_files(root).items():
        view = f"{domain}__{stem}"
        src = (f"read_parquet('{path}')" if path.suffix == ".parquet" else
               f"read_csv('{path}', header=true, delim=',', quote='\"', escape='\"', sample_size=-1)")
        con.execute(f"CREATE OR REPLACE VIEW {ident(view)} AS SELECT * FROM {src}")
        datasets[stem] = Dataset(stem, view, path)
    return Bundle(domain, Path(root), datasets)


def profile(con, ds: Dataset) -> None:
    described = q(con, f"DESCRIBE {ident(ds.view)}")
    names, types = [r[0] for r in described], [r[1] for r in described]
    exprs = ["count(*)"] + [f"count({ident(n)}), count(DISTINCT {ident(n)})" for n in names]
    row = q(con, f"SELECT {', '.join(exprs)} FROM {ident(ds.view)}")[0]
    ds.rows = row[0]
    for i, (n, t) in enumerate(zip(names, types)):
        ds.cols[n] = Col(n, t, ds.rows - row[1 + 2 * i], row[2 + 2 * i])


def detect_period(con, ds: Dataset) -> None:
    found = []
    for c in ds.cols.values():
        if c.distinct < 1:
            continue
        col = ident(c.name)
        if c.is_int:
            lo, hi, months = q(con, f"SELECT min({col}), max({col}), bool_and({col} % 100 BETWEEN 1 AND 12) "
                                    f"FROM {ident(ds.view)} WHERE {col} IS NOT NULL")[0]
            ok = lo is not None and 190001 <= lo and hi <= 210012 and months
        elif c.is_text:
            ok = q(con, f"SELECT bool_and(regexp_full_match({col}, '(19|20)[0-9]{{2}}(0[1-9]|1[0-2])')) "
                        f"FROM {ident(ds.view)} WHERE {col} IS NOT NULL")[0][0]
        else:
            ok = False
        if ok:
            found.append((bool(PERIOD_NAME.search(c.name)), c.distinct, c.name))
    if found:
        ds.period = max(found)[2]
    ds.measures = [c.name for c in ds.cols.values() if c.is_float]


def distinct_count(con, ds: Dataset, cols: Tuple[str, ...]) -> int:
    return q(con, f"SELECT count(*) FROM (SELECT DISTINCT {', '.join(ident(c) for c in cols)} FROM {ident(ds.view)})")[0][0]


def detect_keys(con, ds: Dataset) -> None:
    """The smallest unique column set (up to three); else the set closest to unique (posting-level data)."""
    cands = sorted((c for c in ds.cols.values() if c.name not in ds.measures and c.distinct > 1),
                   key=lambda c: -c.distinct)[:MAX_KEY_CANDIDATES]
    names = [c.name for c in cands]
    best = (0.0, ())
    for size in (1, 2, 3):
        scored = []
        for combo in itertools.combinations(names, size):
            if size == 1:  # NULL counts as one more value, as it does in SELECT DISTINCT
                c = ds.cols[combo[0]]
                ratio = (c.distinct + (c.nulls > 0)) / max(ds.rows, 1)
            else:
                ratio = distinct_count(con, ds, combo) / max(ds.rows, 1)
            hints = sum(bool(KEY_NAME.search(c)) or c == ds.period for c in combo)
            scored.append((ratio >= 1.0, hints, ratio, combo))
            if ratio > best[0] or (ratio == best[0] and len(combo) < len(best[1])):
                best = (ratio, combo)
        unique = [s for s in scored if s[0]]
        if unique:
            ds.keys, ds.unique, ds.key_ratio = list(max(unique)[3]), True, 1.0
            return
    ds.keys, ds.unique, ds.key_ratio = list(best[1]), False, best[0]


def classify(ds: Dataset) -> None:
    single_key = ds.unique and len(ds.keys) == 1 and ds.keys[0] != ds.period
    ds.kind = "fact" if ds.period and ds.measures and not single_key else "dim"


def series(con, ds: Dataset, measure: str, where: str = "") -> Dict[int, float]:
    rows = q(con, f"SELECT {ds.period_sql()} AS p, sum({ident(measure)}) FROM {ident(ds.view)} "
                  f"{'WHERE ' + where if where else ''} GROUP BY 1 ORDER BY 1")
    return {int(p): float(v or 0) for p, v in rows if p is not None}


def by_year(s: Dict[int, float]) -> Dict[int, List[Tuple[int, float]]]:
    years = defaultdict(list)
    for p in sorted(s):
        years[p // 100].append((p, s[p]))
    return years


def detect_agg(con, ds: Dataset) -> None:
    """sum (a flow per period) or point_in_time (a balance from the start of the year — never summed across periods)."""
    if ds.kind != "fact":
        return
    s = {m: series(con, ds, m) for m in ds.measures}
    flows = {}  # b: a — b is proved the monthly flow whose running total is a
    for a in ds.measures:
        verdict = None
        for b in ds.measures:
            if a == b:
                continue
            hits = total = 0
            for months in by_year(s[b]).values():
                running = 0.0
                for p, v in months:
                    running += v
                    if p in s[a] and abs(running) > TOL_ABS:
                        total += 1
                        hits += abs(s[a][p] - running) <= max(TOL_ABS, abs(running) * 1e-6)
            if total >= 3 and hits / total >= 0.8:
                verdict = {"agg": "point_in_time", "confidence": "high",
                           "evidence": f"ยอดรวมรายงวด = ยอดสะสมตั้งแต่ต้นปีของ {b} ({hits}/{total} งวด)"}
                flows[b] = a
                break
        if verdict is not None:
            ds.agg[a] = verdict
    for a in ds.measures:
        if a in ds.agg:
            continue
        verdict = None
        if a in flows:
            verdict = {"agg": "sum", "confidence": "high", "evidence": f"ยอดสะสมตั้งแต่ต้นปีของมันคือ {flows[a]}"}
        if verdict is None:
            climbs = []
            for months in by_year(s[a]).values():
                vals = [v for _, v in months]
                if len(vals) >= 4 and vals[0] > 0:
                    ups = sum(y >= x for x, y in zip(vals, vals[1:])) / (len(vals) - 1)
                    climbs.append(ups >= 0.85 and vals[-1] >= 2.5 * vals[0])
            if climbs and all(climbs):
                verdict = {"agg": "point_in_time", "confidence": "medium",
                           "evidence": "ยอดรวมรายงวดเพิ่มขึ้นตลอดปีแล้วเริ่มใหม่ต้นปี (ลักษณะยอดสะสม)"}
            elif YTD_NAME.search(a):
                verdict = {"agg": "point_in_time", "confidence": "medium", "evidence": f"ชื่อคอลัมน์ {a} บอกว่าเป็นยอดสะสม"}
            else:
                sure = any(len(m) >= 4 for m in by_year(s[a]).values())
                verdict = {"agg": "sum", "confidence": "high" if sure else "medium",
                           "evidence": "ยอดรวมรายงวดไม่สะสมข้ามเดือน" if sure else "งวดน้อยเกินกว่าจะดูว่าสะสมหรือไม่"}
        ds.agg[a] = verdict


def detect_levels(con, ds: Dataset) -> None:
    """Columns whose values must not be added together: a total row, the same amount twice, or scenarios."""
    if ds.kind != "fact":
        return
    measure = next((m for m in ds.measures if ds.agg.get(m, {}).get("agg") == "sum"), ds.measures[0])
    period_values = ds.cols[ds.period].distinct
    for c in ds.cols.values():
        if c.name in ds.measures or c.name == ds.period or c.distinct < 2:
            continue
        if distinct_count(con, ds, (ds.period, c.name)) == period_values:
            continue  # a function of the period (month number, month name) — not a level
        if c.distinct <= MAX_LEVEL_VALUES:
            totals = {v: float(t or 0) for v, t in q(con, f"SELECT {ident(c.name)}, sum({ident(measure)}) FROM "
                                                         f"{ident(ds.view)} GROUP BY 1 ORDER BY 1")}  # stable draft
            grand = sum(totals.values())
            why = []
            for v, t in totals.items():
                if t and abs(t - (grand - t)) <= max(TOL_ABS, abs(t) * 1e-4):  # two similar units are not a total
                    why.append(f"ค่า '{v}' = ผลรวมของค่าอื่น")
            for (v, t), (w, u) in itertools.combinations(totals.items(), 2):
                if t and u and abs(t - u) <= max(TOL_ABS, max(abs(t), abs(u)) * 1e-4):
                    why.append(f"ค่า '{v}' กับ '{w}' ยอดเท่ากัน (นับซ้ำ)")
            if any(v is not None and SCENARIO_VALUE.match(str(v)) for v in totals):
                why.append("ค่าเป็นสถานการณ์ (จริง / เป้า / งบ)")
            if why:
                ds.levels.append({"column": c.name, "measure": measure, "why": why,
                                  "totals_million": {str(v): round(t / 1e6, 2) for v, t in totals.items() if v is not None}})
                continue
        if c.is_text and c.distinct <= 300:
            totals_rows = [r[0] for r in q(con, f"SELECT DISTINCT {ident(c.name)} FROM {ident(ds.view)}")]
            total_values = [v for v in totals_rows if v is not None and TOTAL_VALUE.match(str(v))]
            if total_values:
                ds.levels.append({"column": c.name, "measure": measure,
                                  "why": [f"มีแถวยอดรวม: {', '.join(map(str, total_values[:5]))}"]})


def detect_hierarchies(con, ds: Dataset) -> None:
    """Functional dependencies between text columns: A → B when every A has one B (cost_center → unit → division)."""
    cols = [c.name for c in ds.cols.values() if c.is_text and c.name != ds.period and 2 <= c.distinct <= 5000]
    if len(cols) < 2:
        return
    tmp = ident(f"__h_{ds.view}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE {tmp} AS SELECT DISTINCT {', '.join(map(ident, cols))} FROM {ident(ds.view)}")
    d = {c: ds.cols[c].distinct for c in cols}
    pair = {}
    for a, b in itertools.combinations(cols, 2):
        pair[(a, b)] = pair[(b, a)] = q(con, f"SELECT count(*) FROM (SELECT DISTINCT {ident(a)}, {ident(b)} FROM {tmp})")[0][0]
    con.execute(f"DROP TABLE {tmp}")
    same = {c: c for c in cols}  # code ↔ name: one class, shown once
    for a, b in itertools.combinations(cols, 2):
        if pair[(a, b)] == d[a] == d[b]:
            ds.label_pairs.append([a, b])
            same[b] = same[a]
    reps = sorted({same[c] for c in cols}, key=lambda c: -d[c])
    parent = {}
    for a in reps:
        ups = [b for b in reps if b != a and d[b] < d[a] and pair[(a, b)] == d[a]]
        if ups:
            parent[a] = max(ups, key=lambda b: d[b])  # the nearest level up
    children = set(parent.values())
    for leaf in [c for c in reps if c in parent and c not in children]:
        chain = [leaf]
        while chain[-1] in parent:
            chain.append(parent[chain[-1]])
        ds.hierarchies.append(chain)
    ds.hierarchies.sort(key=len, reverse=True)


def values(con, ds: Dataset, col: str, limit: int = 50000) -> set:
    return {r[0] for r in q(con, f"SELECT DISTINCT {ident(col)} FROM {ident(ds.view)} WHERE {ident(col)} IS NOT NULL LIMIT {limit}")}


def detect_fks(con, bundle: Bundle) -> None:
    """Text column ⊆ a column that is unique in another dataset (alone, or with that dataset's period: a snapshot)."""
    targets = []
    for d in bundle.datasets.values():
        if d.kind != "dim":
            continue
        for c in d.cols.values():
            if (c.is_text or c.is_int) and c.distinct >= 2 and c.nulls == 0:
                if c.distinct >= d.rows * NEAR_UNIQUE:
                    targets.append((d, c.name, None))
                elif d.period and d.period != c.name and distinct_count(con, d, (c.name, d.period)) == d.rows:
                    targets.append((d, c.name, d.period))
    cache: Dict[Tuple[str, str], set] = {}

    def vals(ds, col):
        if (ds.name, col) not in cache:
            cache[(ds.name, col)] = values(con, ds, col)
        return cache[(ds.name, col)]

    for f in bundle.datasets.values():
        for c in f.cols.values():
            if not (c.is_text or c.is_int) or c.distinct < 3 or c.name == f.period:
                continue
            best = None
            for d, k, snap in targets:
                if d is f or (snap and not f.period):
                    continue
                if c.is_int != d.cols[k].is_int or (c.is_int and c.name != k and not KEY_NAME.search(c.name)):
                    continue  # a number is a key only by name — month 1..12 is inside every small id range
                src = vals(f, c.name)
                share = len(src & vals(d, k)) / len(src)
                if share >= FK_SHARE:
                    rank = (share, c.name == k, -d.rows)
                    if best is None or rank > best[0]:
                        best = (rank, d, k, snap, share)
            if best:
                _, d, k, snap, share = best
                f.fks[c.name] = {"dataset": d.name, "column": k, "snapshot": snap, "share": round(share, 4)}


def draft(con, root: Path, domain: str) -> Bundle:
    bundle = load(con, root, domain)
    for ds in bundle.datasets.values():
        profile(con, ds)
        detect_period(con, ds)
        detect_keys(con, ds)
        classify(ds)
        detect_agg(con, ds)
        detect_levels(con, ds)
        detect_hierarchies(con, ds)
    detect_fks(con, bundle)
    facts = [d for d in bundle.datasets.values() if d.kind == "fact"]
    bundle.primary = max(facts, key=lambda d: d.rows).name if facts else None
    return bundle


# ── across bundles: relationships by reconciliation ─────────


@dataclass
class Attr:
    label: str   # what the owner reads: fact_expense.cost_center→dim_org_snapshot.division
    expr: str    # SQL over the fact aliased f (+ joins)
    joins: str


def attributes(bundle: Bundle, f: Dataset) -> List[Attr]:
    out = [Attr(f"{f.name}.{c}", f"f.{ident(c)}", "") for c in f.dims() if f.cols[c].is_text]
    for i, (c, fk) in enumerate(f.fks.items()):
        d = bundle.datasets[fk["dataset"]]
        on = f"f.{ident(c)} = j{i}.{ident(fk['column'])}"
        if fk["snapshot"]:
            on += f" AND {d.period_sql(f'j{i}')} = {f.period_sql('f')}"
        join = f" LEFT JOIN {ident(d.view)} j{i} ON {on}"
        for a in d.dims():
            if a != fk["column"] and d.cols[a].is_text:
                out.append(Attr(f"{f.name}.{c}→{d.name}.{a}", f"j{i}.{ident(a)}", join))
    return out


def slices(f: Dataset) -> List[Tuple[str, str, str]]:
    """(measure, label, WHERE) — each sum measure whole, and cut by each column flagged as not addable."""
    out = []
    for m in f.measures:
        if f.agg.get(m, {}).get("agg") != "sum":
            continue
        whole = (m, m, "")
        if not f.levels:
            out.append(whole)
        for lv in f.levels:
            col = f.cols[lv["column"]]
            for v in lv.get("totals_million", {}):
                value = v.lower() if col.type == "BOOLEAN" else v if (col.is_int or col.is_float) else "'" + v.replace("'", "''") + "'"
                out.append((m, f"{m}[{lv['column']}={v}]", f"f.{ident(lv['column'])} = {value}"))
        if f.levels:
            out.append(whole)
    return out


def aggregate(con, f: Dataset, measure: str, where: str, grain: List[Attr]) -> Dict[tuple, float]:
    joins = "".join(dict.fromkeys(a.joins for a in grain if a.joins))
    keys = "".join(f", {a.expr}" for a in grain)
    sql = (f"SELECT {f.period_sql('f')}{keys}, sum(f.{ident(measure)}) FROM {ident(f.view)} f{joins} "
           f"{'WHERE ' + where if where else ''} GROUP BY ALL")
    out: Dict[tuple, float] = defaultdict(float)
    for row in q(con, sql):
        if row[0] is not None and all(v is not None for v in row[1:-1]):
            out[(int(row[0]),) + tuple(norm(v) for v in row[1:-1])] += float(row[-1] or 0)
    return out


def match_cells(a: Dict[tuple, float], b: Dict[tuple, float]) -> Tuple[int, int, list]:
    common = [k for k in a.keys() & b.keys() if abs(a[k]) > TOL_ABS or abs(b[k]) > TOL_ABS]
    misses = [(k, a[k], b[k]) for k in common if abs(a[k] - b[k]) > max(TOL_ABS, abs(a[k]) * 1e-9)]
    return len(common), len(common) - len(misses), misses


def find_bridges(con, left: Bundle, right: Bundle, max_keys: int = 10, min_cells: int = 6,
                 min_rate: float = 0.8, all_facts: bool = False) -> List[Dict[str, Any]]:
    """Measure pairs whose totals agree to the baht at a shared grain (period + up to two shared keys).
    Exact agreement over many cells is evidence of one number reported twice; the cells that differ are the
    exceptions the owner explains (ER outside EBT, a posting booked under another unit)."""
    def facts(b):
        fs = [d for d in b.datasets.values() if d.kind == "fact" and d.period and slices(d)]
        return fs if all_facts else [d for d in fs if d.name == b.primary]

    found = []
    for fa, fb in itertools.product(facts(left), facts(right)):
        attrs_a, attrs_b = attributes(left, fa), attributes(right, fb)
        va = {x.label: {norm(v) for (v,) in q(con, f"SELECT DISTINCT {x.expr} FROM {ident(fa.view)} f{x.joins}") if v is not None} for x in attrs_a}
        vb = {y.label: {norm(v) for (v,) in q(con, f"SELECT DISTINCT {y.expr} FROM {ident(fb.view)} f{y.joins}") if v is not None} for y in attrs_b}
        pairs = []
        for x, y in itertools.product(attrs_a, attrs_b):
            shared = len(va[x.label] & vb[y.label])
            small = min(len(va[x.label]), len(vb[y.label])) or 1
            if shared >= 2 and shared / small >= 0.5:
                pairs.append((shared, shared / small, x, y))
        # coarse keys first: a total reported twice usually agrees at a few units / groups, not per cost center
        pairs = sorted(pairs, key=lambda p: (-round(p[1], 2), p[0]))[:max_keys]
        grains = [[]] + [[p] for p in pairs] + [
            [p, r] for p, r in itertools.combinations(pairs, 2) if p[2].label != r[2].label and p[3].label != r[3].label]
        cache: Dict[tuple, Dict[tuple, float]] = {}

        def agg(fact, side, s, grain):
            key = (fact.name, s[1], tuple(g[side].label for g in grain))
            if key not in cache:
                cache[key] = aggregate(con, fact, s[0], s[2], [g[side] for g in grain])
            return cache[key]

        seen = set()
        for sa, sb in itertools.product(slices(fa), slices(fb)):
            best, best_rank = None, None
            for grain in grains:
                common, hits, misses = match_cells(agg(fa, 2, sa, grain), agg(fb, 3, sb, grain))
                if common < min_cells or hits / common < min_rate:
                    continue
                # the cleanest statement first: a grain that holds to the baht (≥ 99% of cells) beats a finer one
                # with more cells and more exceptions; among those, the one covering more cells
                rank = (hits / common >= 0.99, hits if hits / common >= 0.99 else hits / common)
                if best_rank is None or rank > best_rank:
                    best_rank = rank
                    best = {"left": f"{left.domain}.{fa.name}", "left_measure": sa[1],
                            "right": f"{right.domain}.{fb.name}", "right_measure": sb[1],
                            "grain": ["period"] + [f"{g[2].label} = {g[3].label}" for g in grain],
                            "cells": common, "cells_matched": hits, "rate": round(hits / common, 4),
                            "exceptions": [{"cell": list(k), "left": round(x, 2), "right": round(y, 2), "diff": round(x - y, 2)}
                                           for k, x, y in sorted(misses, key=lambda m: -abs(m[1] - m[2]))[:10]]}
            if best:
                same = (best["grain"] and tuple(best["grain"]), best["cells"], best["cells_matched"])
                if same not in seen:  # a slice that selects the same cells says nothing new
                    seen.add(same)
                    found.append(best)
    return sorted(found, key=lambda b: (-b["cells_matched"], -b["rate"]))


# ── the contract document ──────────────────────────────────

DTYPE = {"VARCHAR": "string", "BOOLEAN": "bool", "DATE": "date", "TIMESTAMP": "datetime"}


def dtype(c: Col, rows: int) -> str:
    if rows and c.nulls == rows:
        return "unknown"  # every value empty: the file's type says nothing — a question for the owner
    if c.is_int:
        return "Int64"
    if c.is_float:
        return "double"
    return DTYPE.get(c.type, c.type.lower())


def questions(bundle: Bundle) -> List[Dict[str, str]]:
    """What the data cannot settle, most consequential first: a wrong sum is a wrong answer; a missing
    description only a weaker one."""
    out = []
    for ds in bundle.datasets.values():
        for lv in ds.levels:
            out.append({"impact": "high", "about": f"{ds.name}.{lv['column']}",
                        "ask": f"คอลัมน์ {lv['column']} ของ {ds.name}: {'; '.join(lv['why'])} — ห้ามรวม {lv['measure']} ข้ามค่าของคอลัมน์นี้ใช่ไหม "
                               f"และคำถามทั่วไปควรใช้ค่าไหน?"})
        for m, v in ds.agg.items():
            if v["confidence"] != "high":
                out.append({"impact": "high", "about": f"{ds.name}.{m}",
                            "ask": f"{ds.name}.{m} ระบบอ่านว่าเป็น {'ยอดสะสม (ห้ามรวมข้ามงวด)' if v['agg'] == 'point_in_time' else 'ยอดรายงวด (รวมข้ามงวดได้)'} "
                                   f"เพราะ {v['evidence']} — ถูกไหม?"})
        if ds.kind == "fact" and not ds.unique:
            out.append({"impact": "medium", "about": ds.name,
                        "ask": f"{ds.name} ไม่มีชุดคอลัมน์ที่ไม่ซ้ำ (ใกล้สุด {', '.join(ds.keys)} = {ds.key_ratio:.1%} ของแถว) — "
                               f"แถวซ้ำคีย์ได้ตามธรรมชาติของข้อมูลใช่ไหม (เช่น ระดับรายการบันทึกบัญชี)?"})
        empty = [c.name for c in ds.cols.values() if ds.rows and c.nulls == ds.rows]
        if empty:
            out.append({"impact": "low", "about": ds.name,
                        "ask": f"{ds.name}: คอลัมน์ว่างทั้งคอลัมน์ {', '.join(empty)} — ชนิดข้อมูลคืออะไร หรือเลิกใช้แล้ว?"})
    primary = bundle.datasets.get(bundle.primary) if bundle.primary else None
    facts = [d.name for d in bundle.datasets.values() if d.kind == "fact"]
    if primary and len(facts) > 2:
        out.append({"impact": "medium", "about": "primary_dataset",
                    "ask": f"ระบบเลือก {primary.name} (ละเอียดที่สุด) เป็นตารางหลัก — คำถามทั่วไปควรตอบจากตารางไหนใน {', '.join(facts)}?"})
    if primary:
        via_dim = [c for c, fk in primary.fks.items()
                   if any(len(h) >= 2 for h in bundle.datasets[fk["dataset"]].hierarchies)]
        leaves = list(dict.fromkeys(via_dim + [h[0] for h in primary.hierarchies if len(h) >= 3]))[:3]
        if leaves:
            out.append({"impact": "medium", "about": "scope_columns.org_code",
                        "ask": f"ถ้าต้องจำกัดสิทธิ์ตามหน่วยงาน ใช้คอลัมน์ไหน: {', '.join(leaves)} หรืออื่น?"})
    blank = sum(len(ds.cols) for ds in bundle.datasets.values())
    out.append({"impact": "low", "about": "description",
                "ask": f"คำอธิบายคอลัมน์ยังว่างทั้ง {blank} คอลัมน์ — เติมเฉพาะคอลัมน์ที่ผู้ใช้จะถามถึงก่อน"})
    return out


def to_contract(bundle: Bundle, bridges: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    primary = bundle.datasets.get(bundle.primary) if bundle.primary else None
    datasets = []
    for ds in bundle.datasets.values():
        cols = []
        for c in ds.cols.values():
            col: Dict[str, Any] = {"name": c.name, "dtype": dtype(c, ds.rows), "null_ok": c.nulls > 0}
            if c.name in ds.agg:
                col["agg"] = ds.agg[c.name]["agg"]
            if c.name in ds.fks:
                col["fk"] = f"{ds.fks[c.name]['dataset']}.{ds.fks[c.name]['column']}"
            col["description"] = ""
            cols.append(col)
        datasets.append({"name": ds.name, "kind": ds.kind, "keys": ds.keys, "unique": ds.unique,
                         "row_count_built": ds.rows, "source": ds.path.name, "columns": cols})
    contract: Dict[str, Any] = {
        "schema_version": "0.1.0-draft",
        "domain": bundle.domain,
        "title": "",
        "description": "",
        "period_key": primary.period if primary else None,
        "primary_dataset": bundle.primary,
        "scope_columns": {"year_month": primary.period} if primary and primary.period else {},
        "control_totals": {
            "source": bundle.primary, "period_key": primary.period,
            "measures": [{"name": m, "agg": v["agg"]} for m, v in primary.agg.items()],
        } if primary else None,
        "business_rules": [],
        "datasets": datasets,
    }
    if bridges:
        contract["relationships"] = bridges
    contract["draft"] = {
        "evidence": {ds.name: {
            "keys": f"{'ไม่ซ้ำ' if ds.unique else 'ใกล้ไม่ซ้ำ'} {ds.key_ratio:.2%} ของ {ds.rows:,} แถว",
            "agg": {m: v for m, v in ds.agg.items()},
            "levels": ds.levels,
            "fks": ds.fks,
            "hierarchies": ds.hierarchies,
            "label_pairs": ds.label_pairs,
        } for ds in bundle.datasets.values()},
        "questions": questions(bundle),
    }
    return contract


# ── scoring a draft against a contract the owner wrote ──────


def compare(draft_doc: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    """How much of the owner's contract the data alone recovered — fields the data can decide only;
    descriptions and rule texts are the owner's by definition."""
    got = {d["name"]: d for d in draft_doc["datasets"]}
    want = {d["name"]: d for d in contract["datasets"]}
    shared = [n for n in want if n in got]
    s: Dict[str, Any] = {"datasets": f"{len(shared)}/{len(want)}"}
    s["kind"] = f"{sum(got[n]['kind'] == want[n]['kind'] for n in shared)}/{len(shared)}"
    measures = hits_m = agg_ok = agg_n = cols_n = dtype_ok = fk_n = fk_ok = 0
    key_j = []
    wrong = []
    for n in shared:
        gc = {c["name"]: c for c in got[n]["columns"]}
        for c in want[n]["columns"]:
            g = gc.get(c["name"])
            if g is None:
                continue
            cols_n += 1
            dtype_ok += _family(g["dtype"]) == _family(c.get("dtype", ""))
            if "agg" in c:
                measures += 1
                if "agg" in g:
                    hits_m += 1
                    agg_n += 1
                    agg_ok += g["agg"] == c["agg"]
                    if g["agg"] != c["agg"]:
                        wrong.append(f"{n}.{c['name']}: {g['agg']} (contract {c['agg']})")
            if c.get("fk") and re.fullmatch(r"\w+\.\w+", c["fk"]) and c["fk"].split(".")[0] != n:
                # a dim's own key annotated as fk is not a link; a composite key written as prose is not checkable
                fk_n += 1
                fk_ok += g.get("fk") == c["fk"]
        wk, gk = set(want[n].get("keys") or []), set(got[n].get("keys") or [])
        if wk:
            key_j.append(len(wk & gk) / len(wk | gk))
    s["dtype"] = f"{dtype_ok}/{cols_n}"
    s["measures_found"] = f"{hits_m}/{measures}"
    s["agg"] = f"{agg_ok}/{agg_n}"
    s["agg_wrong"] = wrong
    s["keys_jaccard"] = round(sum(key_j) / len(key_j), 2) if key_j else None
    s["fk"] = f"{fk_ok}/{fk_n}"
    s["period_key"] = draft_doc.get("period_key") == contract.get("period_key")
    s["primary_dataset"] = draft_doc.get("primary_dataset") == contract.get("primary_dataset")
    org = (contract.get("scope_columns") or {}).get("org_code")
    asked = " ".join(qn["ask"] for qn in draft_doc["draft"]["questions"] if qn["about"] == "scope_columns.org_code")
    s["org_scope_offered"] = None if not org else org in asked
    rules = " ".join(r.get("text", "") for r in contract.get("business_rules") or [])
    flagged = [f"{n}.{lv['column']}" for n, ev in draft_doc["draft"]["evidence"].items() for lv in ev["levels"]]
    s["not_addable_flagged"] = flagged
    s["flagged_in_owner_rules"] = [f for f in flagged if re.search(rf"\b{re.escape(f.split('.', 1)[1])}\b", rules)]
    return s


def _family(t: str) -> str:
    t = t.lower()
    if t.startswith(("int", "bigint")) or t == "integer":
        return "int"
    if t in ("double", "float", "float64") or t.startswith("decimal"):
        return "float"
    if t in ("string", "str", "object", "varchar"):
        return "text"
    if t in ("bool", "boolean"):
        return "bool"
    return t

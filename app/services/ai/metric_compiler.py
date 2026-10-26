"""Compile declared metrics in code (plan/RESEARCH_DECLARED_METRICS.md §3).

Only names and synonyms are exposed to intent extraction; owner-declared formulas
stay here. Loading fails open, while unsupported compilation fails closed.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
import json
import logging
import re

from sqlalchemy import text

from app.services.ai.thai_year import _MONTHS, _MONTHS_SHORT


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Metric:
    metric_id: str
    name_th: str
    synonyms: tuple[str, ...]
    extends: str | None
    dataset: str | None
    period: dict | None
    dimensions: tuple[str, ...] | None
    terms: dict
    expr: str
    official_scope: str | None
    official_total: dict | None
    reference: dict | None
    unit: str | None
    note_th: str | None
    # {scope, base, base_name_th, positive, threshold}: applied to a breakdown/ranking only — see compile()
    ranking: dict | None = None
    # [{expr, name_th}]: values shown before the metric's own column (sales: ยอดขาย and เป้า beside the %)
    extra_columns: list | None = None
    datasets: tuple | None = None

    def __post_init__(self):
        if self.datasets is not None and self.dimensions is None:
            object.__setattr__(self, "dimensions", tuple(dict.fromkeys(
                dimension for item in self.datasets for dimension in item["dimensions"])))


def load_metrics(context_name: str, config_engine=None) -> list[Metric]:
    """Read active rows afresh, decoding the JSON strings stored by sync_metrics."""
    try:
        if config_engine is None:
            from app.db.session import config_engine
        with config_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT * FROM schema_metrics WHERE context_name = :c "
                "AND status = 'active' AND is_active = 1 ORDER BY id"
            ), {"c": context_name}).mappings()
            metrics = []
            for row in rows:
                values = {f.name: row.get(f.name) for f in fields(Metric)}
                for key in ("synonyms", "period", "dimensions", "terms", "official_total", "reference", "ranking",
                            "extra_columns", "datasets"):
                    if isinstance(values[key], str):
                        values[key] = json.loads(values[key])
                values["synonyms"] = tuple(values["synonyms"] or ())
                if values["dimensions"] is not None:
                    values["dimensions"] = tuple(values["dimensions"])
                if values["datasets"] is not None:
                    values["datasets"] = tuple(values["datasets"])
                values["terms"] = values["terms"] or {}
                metrics.append(Metric(**values))
            return metrics
    except Exception:
        logger.debug("Declared metrics unavailable for %s", context_name, exc_info=True)
        return []


def resolve(metrics: list[Metric]) -> dict[str, Metric]:
    """Resolve structural inheritance only, requiring an earlier parent."""
    resolved: dict[str, Metric] = {}
    for metric in metrics:
        if metric.extends is not None:
            parent = resolved.get(metric.extends)
            if parent is None:
                continue
            inherited = {
                key: getattr(parent, key) if getattr(metric, key) is None else getattr(metric, key)
                for key in ("dataset", "datasets", "period", "dimensions", "official_scope")
            }
            metric = replace(metric, **inherited, terms=parent.terms | metric.terms)
        resolved[metric.metric_id] = metric
    return resolved


def match_metrics(question: str, metrics: list[Metric]) -> list[str]:
    """Consume longest matching spans, then order unique ids by first position."""
    remaining = question.casefold()
    candidates = [(candidate.casefold(), metric.metric_id) for metric in metrics
                  for candidate in (*metric.synonyms, metric.name_th, metric.metric_id) if candidate.strip()]
    hits: dict[str, int] = {}
    for candidate, metric_id in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        start = remaining.find(candidate)
        while start >= 0:
            hits[metric_id] = min(start, hits.get(metric_id, start))
            remaining = remaining[:start] + " " * len(candidate) + remaining[start + len(candidate):]
            start = remaining.find(candidate)
    return sorted(hits, key=hits.get)


def metric_note(matched: list[str], metrics: list[Metric]) -> str:
    names = {metric.metric_id: metric.name_th for metric in metrics}
    items = [f"{metric_id} = {names[metric_id]}" for metric_id in matched if metric_id in names]
    return "metric ที่ประกาศไว้และตรงกับคำในคำถาม: " + "; ".join(items) if items else ""


def dimension_labels(metrics: list[Metric], config_engine=None) -> dict[str, str] | None:
    """Short Thai meaning of every declared dimension, from the contract's column description in schema_metadata
    (e.g. unit → "ฝ่าย"). The schema table of the system prompt shows only the context's main view, so without this
    pass 1 never learns which column a "ฝ่าย" or "ส่วน" is. None = unavailable (the catalog then lists names only)."""
    wanted = {(m.dataset, d) for m in metrics if m.dataset for d in (m.dimensions or ())}
    wanted.update((item["name"], d) for m in metrics for item in m.datasets or () for d in item["dimensions"])
    if not wanted:
        return {}
    try:
        if config_engine is None:
            from app.db.session import config_engine
        labels: dict[str, str] = {}
        with config_engine.connect() as conn:
            for table in {t for t, _ in wanted}:
                rows = conn.execute(text(
                    "SELECT column_name, description FROM schema_metadata WHERE table_name = :t "
                    "AND COALESCE(status, 'active') = 'active'"), {"t": table}).all()
                for column, description in rows:
                    if (table, column) in wanted and isinstance(description, str) and description.strip():
                        # the meaning is the first clause: "ฝ่าย — ระดับ 3 ของ…; คำถาม…" → "ฝ่าย"
                        head = description.split(" — ")[0].split(";")[0].strip()
                        labels.setdefault(column, head[:60])
        return labels
    except Exception:
        logger.debug("Dimension labels unavailable", exc_info=True)
        return None


def metric_catalog(metrics: list[Metric], labels: dict[str, str] | None = None) -> str:
    lines = []
    for m in metrics:
        line = f"- {m.metric_id}: {m.name_th} (คำพ้อง: {', '.join(m.synonyms)})"
        if labels is not None and m.dimensions:
            dims = ", ".join(f"{d} ({labels[d]})" if labels.get(d) else d for d in m.dimensions)
            line += f"\n  มิติ/ตัวกรองที่ใช้ได้ (ชื่อคอลัมน์ → ความหมาย): {dims}"
        lines.append(line)
    return "\n".join(lines)


@dataclass(frozen=True)
class CompileRequest:
    metric_id: str
    period: int
    mode: str
    dimensions: tuple[str, ...] = ()
    filters: tuple[dict, ...] = ()
    order_desc: bool | None = None
    limit: int | None = None
    official_total_ok: bool = True
    base_period: int | None = None  # a comparison: the value at period against the value at base_period
    change: str | None = None       # a comparison across units keeps only those that went "up" / "down"
    threshold: str | None = None    # a breakdown keeps units "above" / "below" the metric's ranking.threshold


@dataclass(frozen=True)
class Clarification:
    """A question back to the asker instead of an answer (PLAN_METRICS_COMPARISON CMP-3 ค)."""
    text: str


# ponytail: short word lists — pass 1 has no field for "which way" and the owner chose to show only the units
# that moved the way the question asks (CMP-2 ข); grow them when the eval or audit shows a miss
CHANGE_WORDS = {
    "up": ("ดีกว่า", "ดีขึ้น", "เพิ่มขึ้น", "สูงขึ้น", "สูงกว่า", "มากขึ้น", "มากกว่า", "เติบโต", "โตขึ้น"),
    "down": ("แย่กว่า", "แย่ลง", "ลดลง", "ต่ำลง", "ต่ำกว่า", "น้อยลง", "น้อยกว่า", "ถดถอย"),
}
# words that name an org unit without naming a level: the owner chose to ask back (CMP-3 ค)
GENERIC_UNIT_WORDS = ("หน่วยงาน", "จังหวัด")
_MONTH_NAMES = "|".join(re.escape(m) for m in (*_MONTHS, *_MONTHS_SHORT))
# "ม.ค.-ก.ย." / "มกราคม ถึง กันยายน": a year to date at the end month, however pass 1 filled time_range
_YEAR_TO_DATE_SPAN = re.compile(rf"(?:ม\.ค\.|มกราคม)\s*(?:-|–|ถึง(?:เดือน)?)\s*({_MONTH_NAMES})")


def _year_to_date_end(question: str) -> int | None:
    found = _YEAR_TO_DATE_SPAN.search(question)
    if found is None:
        return None
    name = found[1]
    return (_MONTHS.index(name) if name in _MONTHS else _MONTHS_SHORT.index(name)) + 1


@dataclass(frozen=True)
class Compiled:
    sql: str
    metric_id: str
    name_th: str
    unit: str | None
    official: bool
    table: str
    note_th: str | None
    base_name_th: str | None = None  # the ratio's denominator column, when the result carries one
    compare: str | None = None       # what a comparison compared, for the explanation


def _validate_shape(dimensions, filters, metric: Metric) -> None:
    declared = metric.dimensions or ()
    if not isinstance(dimensions, (list, tuple)) or any(d not in declared for d in dimensions):
        raise ValueError("Undeclared dimension")
    if not isinstance(filters, (list, tuple)):
        raise ValueError("Invalid filters")
    for item in filters:
        if not isinstance(item, dict) or item.get("column") not in declared:
            raise ValueError("Undeclared filter column")
        operator, value = item.get("operator"), item.get("value")
        if operator in ("=", "LIKE") and isinstance(value, str):
            continue
        if operator == "IN" and isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            continue
        raise ValueError("Unsupported filter operator or value")


def _value_names(intent: dict, metric: Metric, extra: frozenset[str] = frozenset()) -> set[str]:
    """Every name pass 1 may use for the metric's value column: the metric itself, its official
    columns, and whatever it wrote in metric_id / metrics ("ebt", "EBT สะสม", ...)."""
    names = {metric.metric_id, metric.name_th, *metric.synonyms,
             *((metric.official_total or {}).get(key) for key in ("column", "month_column")),
             intent.get("metric_id"), *(intent.get("metrics") or [])}
    return {n.casefold().strip() for n in names if isinstance(n, str)} | set(extra)


def _orders_by_value(intent: dict, metric: Metric, extra: frozenset[str] = frozenset()) -> bool:
    """Ranking by the metric value: an explicit ranking, a LIMIT, or an ordering that names the value."""
    ordering = intent.get("ordering") or {}
    column = ordering.get("column") if isinstance(ordering, dict) else None
    return (intent.get("intent_type") == "ranking" or intent.get("limit") is not None
            or (isinstance(column, str) and column.casefold().strip() in _value_names(intent, metric, extra)))


def _reason_detail(value) -> str:
    return (" ".join(value.split())[:64] or "invalid") if isinstance(value, str) else "invalid"


def _support_reason(intent: dict, metric: Metric, extra_names: frozenset[str] = frozenset()) -> str | None:
    try:
        if intent.get("intent_type") not in ("aggregation", "ranking"):
            return "shape:intent_type:" + _reason_detail(intent.get("intent_type"))
        declared = metric.dimensions or ()
        dimensions = intent.get("dimensions", [])
        if not isinstance(dimensions, (list, tuple)):
            return "shape:dimension:invalid"
        for dimension in dimensions:
            if dimension not in declared:
                return "shape:dimension:" + _reason_detail(dimension)
        filters = intent.get("filters", [])
        if not isinstance(filters, (list, tuple)):
            return "shape:filter:invalid"
        for item in filters:
            if not isinstance(item, dict):
                return "shape:filter:invalid"
            if item.get("column") not in declared:
                return "shape:filter:" + _reason_detail(item.get("column"))
            operator, value = item.get("operator"), item.get("value")
            if operator in ("=", "LIKE") and isinstance(value, str):
                continue
            if operator == "IN" and isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                continue
            return "shape:filter:" + _reason_detail(operator)
        ordering = intent.get("ordering")
        if ordering is not None:
            if not isinstance(ordering, dict):
                return "shape:ordering:invalid"
            column = ordering.get("column")
            if column not in (*(metric.dimensions or ()), None) and not (
                    isinstance(column, str) and column.casefold().strip() in _value_names(intent, metric, extra_names)):
                return "shape:ordering:" + _reason_detail(column)
            if ordering.get("direction") not in (None, "ASC", "DESC"):
                return "shape:ordering:direction"
        return None
    except (AttributeError, TypeError, ValueError):
        return "shape:invalid"


def supports(intent: dict, metric: Metric, extra_names: frozenset[str] = frozenset()) -> bool:
    return _support_reason(intent, metric, extra_names) is None


def _threshold_side(question: str, line: dict) -> str | None:
    """"มากกว่าเป้า" → above, "ไม่ถึงเป้า" → below, from the contract's words. Below words are cut out first:
    "ไม่ถึงเป้า" contains the above word "ถึงเป้า"."""
    below = [w for w in line.get("below") or () if isinstance(w, str) and w]
    above = [w for w in line.get("above") or () if isinstance(w, str) and w]
    rest = question
    for word in sorted(below, key=len, reverse=True):
        rest = rest.replace(word, " ")
    is_below, is_above = rest != question, any(word in rest for word in above)
    return None if is_below == is_above else "below" if is_below else "above"


def _triggered_mappings(intent: dict, question: str, ignore: frozenset[str] = frozenset(),
                        names: frozenset[str] = frozenset(), defining: dict | None = None) -> list[dict]:
    """Mappings whose keyword is in the question, except `ignore` words, keywords that contain one of the
    metric's own `names` (pass 1 invents "ยอดขายเทียบเป้า" around the synonym "เทียบเป้า") and conditions that only
    restate the terms (pass 1 invents "ยอดขาย" → metric = 'actual')."""
    question = question.casefold()
    triggered = []
    for mapping in intent.get("matched_mappings") or []:
        if not isinstance(mapping, dict) or not isinstance(mapping.get("keyword"), str):
            continue
        keyword = mapping["keyword"].casefold().strip()
        if (keyword and keyword not in ignore and keyword in question
                and not any(name and name in keyword for name in names)
                and not _restates_definition(mapping.get("sql_condition"), defining or {})):
            triggered.append(mapping)
    return triggered


_TERM_LITERAL = re.compile(r"\b([a-z_][a-z0-9_]*)\s*(?:=|\bIN\b)\s*(\((?:\s*'(?:''|[^'])*'\s*,?)+\)|'(?:''|[^'])*')", re.I)


def _defining_values(metric: Metric) -> dict[str, set[str]]:
    """Columns that every term picks by literal (sales: metric = 'actual' / 'target'), with the values they pick.
    pass 1 repeats them as filters (metric = 'actual') — they are the metric's own definition, not a selection."""
    columns: dict[str, set[str]] | None = None
    for term in metric.terms.values():
        found: dict[str, set[str]] = {}
        for column, values in _TERM_LITERAL.findall((term.get("where") or "") if isinstance(term, dict) else ""):
            found.setdefault(column.casefold(), set()).update(
                v.replace("''", "'") for v in re.findall(r"'((?:''|[^'])*)'", values))
        columns = found if columns is None else {
            c: columns[c] | found[c] for c in columns.keys() & found.keys()}
    declared = {d.casefold() for d in metric.dimensions or ()}
    return {c: v for c, v in (columns or {}).items() if c not in declared}


def _restates_definition(condition, defining: dict[str, set[str]]) -> bool:
    """A condition made only of `column = 'value'` / `IN (...)` that the terms already choose."""
    if not isinstance(condition, str) or not defining:
        return False
    found = _TERM_LITERAL.findall(condition)
    for column, values in found:
        picked = {v.replace("''", "'") for v in re.findall(r"'((?:''|[^'])*)'", values)}
        if column.casefold() not in defining or not picked <= defining[column.casefold()]:
            return False
    return bool(found) and not re.sub(r"\b(?:AND|OR)\b|[()\s]", "", _TERM_LITERAL.sub(" ", condition), flags=re.I)


def _restates_scope(operator, value, scope: dict | None) -> bool:
    """A period filter that is the request scope itself: BETWEEN its first and last month, or IN all its months.
    Live audit 473 (portal, 2026-10-26): scope year_month 202501…202609 arrived as a filter beside
    time_range {2026, 9, cumulative} and sent "ยอดขายมากกว่าเป้า" to free SQL (91 units, every target 0)."""
    months = sorted({k for values in (scope or {}).values() if isinstance(values, (list, tuple))
                     for k in map(_month_key, values) if k is not None})
    if len(months) < 2 or not isinstance(value, (list, tuple)):
        return False
    keys = [_month_key(v) for v in value]
    if None in keys:
        return False
    return ((operator == "BETWEEN" and len(keys) == 2 and sorted(keys) == [months[0], months[-1]])
            or (operator == "IN" and sorted(set(keys)) == months))


def _month_key(value) -> int | None:
    """A YYYYMM bound of a period range (int or decimal string with a real month), else None."""
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    return value if type(value) is int and 100001 <= value <= 999912 and 1 <= value % 100 <= 12 else None


def plan(
    intent: dict,
    question: str,
    resolved: dict[str, Metric],
    matched: list[str],
    reference: int | None,
    tables,
    labels: dict[str, str] | None = None,
    scope: dict | None = None,
) -> CompileRequest | None:
    """Choose a declared metric and a supported single-period compile request."""
    return plan_with_reason(intent, question, resolved, matched, reference, tables, labels, scope)[0]


def plan_with_reason(
    intent: dict,
    question: str,
    resolved: dict[str, Metric],
    matched: list[str],
    reference: int | None,
    tables,
    labels: dict[str, str] | None = None,
    scope: dict | None = None,
) -> tuple[CompileRequest | None, str | None]:
    """Choose a compile request or give a short decline reason. `labels` = dimension_labels(); `scope` = the
    request's scope (the portal sends the months the asker may see)."""
    metric_id = intent.get("metric_id")
    if isinstance(metric_id, str) and metric_id not in resolved:
        column_matches = [key for key, metric in resolved.items()
                          if any(isinstance(column, str) and column.casefold() == metric_id.casefold()
                                 for column in ((metric.official_total or {}).get("column"),
                                                (metric.official_total or {}).get("month_column")))]
        if len(column_matches) == 1:
            metric_id = column_matches[0]
    if not isinstance(metric_id, str) or metric_id not in resolved:
        candidates = [item for item in matched if item in resolved]
        metric_id = candidates[0] if candidates else None
        for candidate in candidates:
            parent = resolved[candidate].extends
            visited = {candidate}
            while parent in resolved and parent not in visited:
                if parent in candidates:
                    metric_id = candidate
                    break
                visited.add(parent)
                parent = resolved[parent].extends
            if parent in candidates:
                break
    if metric_id is None:
        return None, "no_metric"
    metric = resolved[metric_id]
    ignore = set()
    ancestor = metric
    visited = set()
    while ancestor is not None and ancestor.metric_id not in visited:
        visited.add(ancestor.metric_id)
        ignore.update(value.casefold().strip() for value in
                      (ancestor.metric_id, ancestor.name_th, *ancestor.synonyms))
        ancestor = resolved.get(ancestor.extends)
    # "ฝ่ายไหน…" names a declared dimension: a mapping on that word (the global 'สายงาน', or one pass 1
    # invents for ส่วน / กลุ่ม) must not send the question to free SQL — the dimension already carries it
    level_words = {label.casefold().strip() for dim, label in (labels or {}).items()
                   if dim in (metric.dimensions or ()) and isinstance(label, str) and label.strip()}
    # the metric's own names: id / name / synonyms, and what its extra columns show ("ยอดขายบริการ (บาท)" → ยอดขายบริการ)
    names = ignore | {re.sub(r"\s*\([^)]*\)\s*$", "", extra["name_th"]).casefold().strip()
                      for extra in metric.extra_columns or ()
                      if isinstance(extra, dict) and isinstance(extra.get("name_th"), str)}
    triggered = _triggered_mappings(intent, question, frozenset(ignore | level_words), frozenset(names),
                                    _defining_values(metric))
    if triggered:
        return None, "mapping_triggered:" + _reason_detail(triggered[0]["keyword"].casefold().strip())
    filters = intent.get("filters") or []
    if not isinstance(filters, (list, tuple)):
        return None, "shape:filter:invalid"
    period_column = (metric.period or {}).get("column")
    comparison = intent.get("intent_type") == "comparison"
    line = (metric.ranking or {}).get("threshold") if isinstance(metric.ranking, dict) else None
    if intent.get("intent_type") in ("lookup", "detail") and isinstance(line, dict):
        comparison = True  # "หน่วยงานที่ยอดขายมากกว่าเป้ามีหน่วยไหนบ้าง" arrives as a lookup or a detail too
    if comparison and isinstance(line, dict):
        # "ยอดขายเทียบเป้า": a metric measured against its declared line compares with that line (the target),
        # not with the same period a year before
        ordering = intent.get("ordering")
        dimensions = intent.get("dimensions")
        intent = {**intent, "intent_type": "aggregation",
                  "ordering": {"direction": ordering.get("direction")} if isinstance(ordering, dict) else ordering,
                  # pass 1 adds the period as a dimension of a comparison; the target sits beside each unit instead
                  "dimensions": [d for d in dimensions if not (isinstance(d, str) and isinstance(period_column, str)
                                                                and d.casefold() == period_column.casefold())]
                  if isinstance(dimensions, list) else dimensions}
        comparison = False
    ordering = intent.get("ordering")
    if (isinstance(line, dict) and isinstance(ordering, dict)
            and ordering.get("column") not in (*(metric.dimensions or ()), None)):
        # a metric measured against its line ranks by its own value; pass 1 names that freely
        # ("achievement_diff", "amount - target_amt") — the actual and target travel beside it
        intent = {**intent, "ordering": {"direction": ordering.get("direction")}}
    remaining = []
    defining = _defining_values(metric)
    period_hint = None
    lows, highs = [], []
    compared = set()  # a comparison's periods as pass 1 wrote them: IN [202608, 202609], BETWEEN [202509, 202609]
    for item in filters:
        if (isinstance(item, dict) and isinstance(item.get("column"), str)
                and isinstance(period_column, str) and item["column"].casefold() == period_column.casefold()):
            operator, value = item.get("operator"), item.get("value")
            if _restates_scope(operator, value, scope):
                continue  # pass 1 copied the portal's scope (BETWEEN 202501 AND 202609), not the question's period
            if comparison:
                if operator not in ("=", "IN", "BETWEEN"):
                    return None, "period_filter:operator"
                values = [value] if operator == "=" else value
                keys = [_month_key(v) for v in values] if isinstance(values, (list, tuple)) and values else [None]
                if None in keys or (operator == "BETWEEN" and len(keys) != 2):
                    return None, "period_filter:value"
                if operator == "BETWEEN" and min(keys) // 100 == max(keys) // 100:
                    keys = [max(keys)]  # BETWEEN y01 AND yMM: the year to date at yMM, not two periods
                compared.update(keys)
            elif operator == "=":
                if isinstance(value, str) and value.isdecimal():
                    try:
                        value = int(value)
                    except ValueError:
                        return None, "period_filter:value"
                if type(value) is not int or not 100001 <= value <= 999912:
                    return None, "period_filter:value"
                period_hint = value
            elif operator in ("BETWEEN", "IN", ">=", "<="):
                bounds = value if operator in ("BETWEEN", "IN") else [value]
                keys = [_month_key(v) for v in bounds] if isinstance(bounds, (list, tuple)) else [None]
                if not keys or None in keys or (operator == "BETWEEN" and len(keys) != 2):
                    return None, "period_filter:value"
                if operator == "IN" and sorted(set(keys)) != list(range(min(keys), max(keys) + 1)):
                    return None, "period_filter:range"  # not consecutive months of one year
                if operator != "<=":
                    lows.append(min(keys))
                if operator != ">=":
                    highs.append(max(keys))
            else:
                return None, "period_filter:operator"
        elif (isinstance(item, dict) and isinstance(item.get("column"), str)
              and item["column"].casefold() in defining
              and item.get("operator") in ("=", "IN")
              and set(item["value"] if isinstance(item.get("value"), list) else [item.get("value")])
              <= defining[item["column"].casefold()]):
            continue  # metric = 'actual': the terms already choose it
        else:
            remaining.append(item)
    range_cumulative = False
    if lows or highs:
        # "สะสม / ตั้งแต่ต้นปี" arrives as time_key BETWEEN y01 AND yMM (or >= and <=, IN the months, or <= yMM
        # with time_range.cumulative): the year to date at yMM — the metric's cumulative value. A range that
        # starts in another month is a multi-month sum the declarations cannot express.
        time_range = intent.get("time_range")
        low, high = (max(lows) if lows else None), (min(highs) if highs else None)
        if (period_hint is not None or high is None or (low is not None and low > high)
                or (low is None and not (isinstance(time_range, dict) and time_range.get("cumulative") is True))
                or (low is not None and low != high and low != high // 100 * 100 + 1)):
            return None, "period_filter:range"
        period_hint, range_cumulative = high, low != high
    base_key = None
    if compared:
        # pass 1 writes a comparison's periods as a pair (IN [202509, 202609], [202608, 202609]) or as the months of
        # each year to date (IN [202601 … 202609, 202501 … 202509]; the earlier year sometimes whole to 202512)
        years = {}
        for key in sorted(compared):
            years.setdefault(key // 100, []).append(key)

        def year_end(keys):
            if len(keys) == 1:
                return keys[0]
            return keys[-1] if keys[0] % 100 == 1 and keys == list(range(keys[0], keys[-1] + 1)) else None

        if len(years) == 1 and len(compared) == 2:
            base_key, period_hint = sorted(compared)
        else:
            ends = [year_end(keys) for _, keys in sorted(years.items())]
            if len(ends) > 2 or None in ends:
                return None, "period_filter:compare"
            period_hint = ends[-1]
            if len(ends) == 2:
                # the whole earlier year listed against a year to date: its same period (CMP-1 ก)
                base_key = ends[0] if ends[0] % 100 <= period_hint % 100 else period_hint - 100
    intent = {**intent, "filters": remaining}
    if comparison and isinstance(intent.get("dimensions"), (list, tuple)) and isinstance(period_column, str):
        # "EBT ปีนี้เทียบปีก่อน" with dimensions ["time_key"]: the comparison already puts the periods side by side
        intent["dimensions"] = [d for d in intent["dimensions"]
                                if not (isinstance(d, str) and d.casefold() == period_column.casefold())]
    checked = intent
    if comparison:
        # a comparison ranks by the change, which pass 1 names freely (diff_ebt, ebt_change): keep the direction
        ordering = intent.get("ordering")
        checked = {**intent, "intent_type": "aggregation",
                   "ordering": {"direction": ordering.get("direction")} if isinstance(ordering, dict) else ordering}
    reason = _support_reason(checked, metric, frozenset(ignore))
    if reason is not None:
        return None, reason
    if metric.datasets is not None and _dataset_for(
            metric, [*(intent.get("dimensions") or ()), *(f["column"] for f in remaining)]) is None:
        return None, "shape:dimension_set"
    if type(reference) is not int:
        return None, "reference_missing"
    ref_y, ref_m = divmod(reference, 100)
    if not 1 <= ref_y <= 9999 or not 1 <= ref_m <= 12:
        return None, "reference_missing"
    tr = intent.get("time_range") or {}
    if not isinstance(tr, dict):
        return None, "time_range_invalid"
    hint_y, hint_m = divmod(period_hint, 100) if period_hint is not None else (ref_y, ref_m)
    year = tr.get("year") or hint_y
    month = tr.get("month") or hint_m
    if (type(year) is not int or not 1 <= year <= 9999
            or type(month) is not int or not 1 <= month <= 12):
        return None, "time_range_invalid"
    span_end = _year_to_date_end(question) if not comparison else None
    if span_end is not None:
        month = span_end
    if year == ref_y:
        month = min(month, ref_m)
    mode = ("month" if tr.get("month") is not None and not tr.get("cumulative") and not range_cumulative
            and span_end is None else "cumulative")
    period = year * 100 + month
    limit = intent.get("limit")
    order_desc = (intent.get("ordering") or {}).get("direction") != "ASC" \
        if not comparison and _orders_by_value(intent, metric, frozenset(ignore)) else None
    threshold = None
    if isinstance(line, dict) and not comparison and intent.get("dimensions"):
        # "หน่วยงานที่ยอดขายมากกว่าเป้า": the units on the asked side of the line, best (or worst) first
        threshold = _threshold_side(question, line)
        if threshold is not None and order_desc is None:
            order_desc = threshold == "above"
        if threshold is not None and not re.search(r"\d", question):
            # "ฝ่ายไหนยังไม่ถึงเป้า" asks for every unit on that side; live audit 471 got pass 1's invented
            # limit 10 and an answer that called those 10 "ทั้งหมด" (the report: 24)
            limit = None
    base_period = change = None
    if comparison:
        # "EBT_month กันยายนเทียบสิงหาคม": pass 1 names the month column and no time_range — month against month
        month_column = (metric.official_total or {}).get("month_column")
        named = [intent.get("metric_id"), *(intent.get("metrics") if isinstance(intent.get("metrics"), list) else [])]
        if (isinstance(month_column, str) and not tr.get("cumulative")
                and any(isinstance(n, str) and n.casefold() == month_column.casefold() for n in named)):
            mode = "month"
        base_period = base_key if base_key is not None else period - 100  # CMP-1 ก: the same period a year before
        if not base_period < period or not 100001 <= base_period:
            return None, "period_filter:compare"
        moves = [way for way, words in CHANGE_WORDS.items() if any(word in question for word in words)]
        change = moves[0] if len(moves) == 1 else None
        order_desc = change != "down" if change else (intent.get("ordering") or {}).get("direction") != "ASC"
    return CompileRequest(
        metric_id=metric_id,
        period=period,
        mode=mode,
        dimensions=tuple(intent.get("dimensions") or []),
        filters=tuple(intent.get("filters") or []),
        # "สูงสุด 10 อันดับ" arrives as ranking, as aggregation + limit, or as ordering by the metric's
        # own name — all rank by the value; an ordering by a dimension alone keeps the table order
        order_desc=order_desc,
        limit=limit if type(limit) is int and limit > 0 else None,
        official_total_ok=metric.official_total is not None and metric.official_total["dataset"] in tables,
        base_period=base_period,
        change=change,
        threshold=threshold,
    ), None


def _quote(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("Invalid SQL identifier")
    return '"' + name.replace('"', '""') + '"'


def _literal(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Invalid SQL literal")
    return "'" + value.replace("'", "''") + "'"


_TOKEN = re.compile(r"\s*([a-z_][a-z0-9_]*|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+*/(),-])")


class _Expression:
    """Recursive descent: sum -> product -> unary -> primary."""

    def __init__(self, expr: str, identifier):
        self.tokens: list[str] = []
        source = expr.strip()
        if any(comment in source for comment in ("--", "/*", "*/")):
            raise ValueError("Comments outside metric grammar")
        position = 0
        while position < len(source):
            token = _TOKEN.match(source, position)
            if token is None:
                raise ValueError("Expression outside metric grammar")
            self.tokens.append(token[1])
            position = token.end()
        self.position = 0
        self.identifier = identifier

    def peek(self) -> str:
        return self.tokens[self.position] if self.position < len(self.tokens) else ""

    def take(self, expected: str) -> None:
        if self.peek() != expected:
            raise ValueError(f"Expected {expected!r} in metric expression")
        self.position += 1

    def parse(self) -> str:
        result = self.binary(("+", "-"), self.product)
        if self.peek():
            raise ValueError("Unexpected metric expression token")
        return result

    def binary(self, operators: tuple[str, ...], operand) -> str:
        result = operand()
        while self.peek() in operators:
            operator = self.peek()
            self.position += 1
            result = f"({result} {operator} {operand()})"
        return result

    def product(self) -> str:
        return self.binary(("*", "/"), self.primary)

    def primary(self) -> str:
        token = self.peek()
        if not token:
            raise ValueError("Incomplete metric expression")
        self.position += 1
        if token in ("+", "-"):
            return f"({token}{self.primary()})"
        if token == "(":
            result = self.binary(("+", "-"), self.product)
            self.take(")")
            return f"({result})"
        if token == "nullif" and self.peek() == "(":
            self.take("(")
            first = self.binary(("+", "-"), self.product)
            self.take(",")
            second = self.binary(("+", "-"), self.product)
            self.take(")")
            return f"NULLIF({first}, {second})"
        if re.fullmatch(r"[a-z_][a-z0-9_]*", token):
            return self.identifier(token)
        if token[0].isdigit() or token[0] == ".":
            return token
        raise ValueError("Invalid metric expression operand")


def _period_label(period: int, mode: str) -> str:
    """09/2569 (พ.ศ.), with "สะสม" in front of a year to date."""
    return f"{'สะสม ' if mode == 'cumulative' else ''}{period % 100:02d}/{period // 100 + 543}"


def _dataset_for(metric: Metric, columns) -> str | None:
    if metric.datasets is None:
        return metric.dataset
    columns = set(columns)
    item = min((item for item in metric.datasets if columns <= set(item["dimensions"])),
               key=lambda item: len(item["dimensions"]), default=None)
    return item["name"] if item is not None else None


def compile(req: CompileRequest, resolved: dict[str, Metric]) -> Compiled:
    """Compile a single-period SELECT, or a two-period comparison when `base_period` is set; invalid or
    unsupported input raises ValueError."""
    try:
        metric = resolved[req.metric_id]
        _validate_shape(req.dimensions, req.filters, metric)
        if req.mode not in ("cumulative", "month"):
            raise ValueError("Unknown metric mode")
        if type(req.period) is not int or (req.limit is not None and (type(req.limit) is not int or req.limit < 0)):
            raise ValueError("Period and limit must be integers; limit must be nonnegative")
        if req.order_desc is not None and type(req.order_desc) is not bool:
            raise ValueError("Invalid ordering")
        compare = req.base_period is not None
        if compare and (type(req.base_period) is not int or not req.base_period < req.period
                        or req.change not in (None, "up", "down")):
            raise ValueError("Invalid comparison")
        if req.threshold not in (None, "above", "below"):
            raise ValueError("Invalid threshold side")
        official = not req.dimensions and not req.filters
        total = metric.official_total if official and req.official_total_ok else None
        table = total["dataset"] if total is not None else _dataset_for(
            metric, [*req.dimensions, *(f["column"] for f in req.filters)])
        if table is None:
            raise ValueError("No declared dataset holds the requested dimensions and filters")
        # no year-to-date column declared (sales holds monthly amounts): the year to date is the sum of the
        # months from 01 to the period
        summed = req.mode == "cumulative" and not metric.period["value"].get("cumulative")

        def render(expr_text: str, current: Metric, visiting: frozenset[str], when: str = "") -> str:
            value = _quote(current.period["value"]["month" if summed else req.mode])

            def identifier(name: str) -> str:
                if name in current.terms:
                    term = current.terms[name]
                    if not isinstance(term, Mapping):
                        raise ValueError("Invalid metric term")
                    where = term.get("where")
                    if where is not None and not isinstance(where, str):
                        raise ValueError("Invalid term predicate")
                    if where is None or not where.strip():
                        where = "1 = 1"
                    return f"(COALESCE(SUM(CASE WHEN ({where}){when} THEN {value} END), 0))"
                if name in resolved:
                    return f"({expression(resolved[name], visiting | {current.metric_id}, when)})"
                raise ValueError(f"Unknown metric expression identifier: {name}")

            return _Expression(expr_text, identifier).parse()

        def expression(current: Metric, visiting: frozenset[str], when: str = "") -> str:
            if current.metric_id in visiting:
                raise ValueError("Cyclic metric expression")
            if (current.dataset != metric.dataset or current.datasets != metric.datasets
                    or current.period != metric.period):
                raise ValueError("Referenced metric must use the same dataset and period mapping")
            return render(current.expr, current, visiting, when)

        expr = expression(metric, frozenset())
        ranking = metric.ranking if metric.ranking is not None else {}
        if not isinstance(ranking, dict):
            raise ValueError("Invalid ranking declaration")
        if total is not None and summed:
            raise ValueError("An official total needs a year-to-date column")
        period_key = f'CAST({_quote(metric.period["column"])} AS INTEGER)'

        def in_period(p: int) -> str:
            return f"{period_key} BETWEEN {p // 100 * 100 + 1} AND {p}" if summed else f"{period_key} = {p}"

        # a comparison reads both periods in one pass; each side of it adds its own period to every term
        period = (f"({in_period(req.base_period)} OR {in_period(req.period)})" if compare and summed
                  else f"{period_key} IN ({req.base_period}, {req.period})" if compare else in_period(req.period))
        dims = [_quote(d) for d in req.dimensions]
        if total is not None:
            measure = _quote(total["month_column" if req.mode == "month" else "column"])
            if compare:  # the official table holds one row per period
                now, then = (f"MAX(CASE WHEN {period_key} = {p} THEN {measure} END)" for p in (req.period, req.base_period))
        else:
            measure = f"({expr})"
            if compare:
                now, then = (f"({expression(metric, frozenset(), f' AND {in_period(p)}')})"
                             for p in (req.period, req.base_period))
            # No filter = the question named no unit, so a breakdown stays inside the report's
            # scope (the EBT report is of the two sales lines); a filter picks units explicitly,
            # and those outside the scope stay computable (contract: ebt_dimension_breakdown).
            if not req.filters and metric.official_scope:
                period += f" AND ({metric.official_scope})"
            # filters on one column with one operator are alternatives ("ฝ่าย A และฝ่าย B" arrives as two LIKE
            # filters on unit_fname; two = can never both hold); mixed operators (= X with LIKE 'ส่วน') narrow
            by_column: dict[tuple[str, str], list[str]] = {}
            for item in req.filters:
                column, operator, value = _quote(item["column"]), item["operator"], item["value"]
                if operator == "IN":
                    predicate = f"{column} IN ({', '.join(_literal(v) for v in value)})"
                else:
                    if operator == "LIKE" and "%" not in value:
                        value = f"%{value}%"
                    predicate = f"{column} {operator} {_literal(value)}"
                by_column.setdefault((column, operator), []).append(predicate)
            columns_operators = {}
            for column, operator in by_column:
                columns_operators.setdefault(column, set()).add(operator)
            for (column, _), predicates in by_column.items():
                alternatives = len(predicates) > 1 and len(columns_operators[column]) == 1
                period += " AND " + (f"({' OR '.join(predicates)})" if alternatives else " AND ".join(predicates))
        # a ratio's column says so in its name: "EBT Margin (%)" reads as percent in the data block too
        alias = f"{metric.name_th} (%)" if (metric.unit or "").strip().lower() in ("percent", "%") else metric.name_th
        # A breakdown or ranking of a ratio across units: the contract's `ranking.scope` keeps units the
        # report would not compare (EBT margin of a support unit with 442 baht of revenue: -47 million %),
        # and `ranking.base` puts the denominator beside the ratio so the reader sees the base. A comparison
        # always orders by its change, so there only a breakdown ranks units; a named unit stays itself.
        base_sql = base_name = None
        if total is None and (dims or (req.order_desc is not None and not compare)) and ranking:
            # Pass 1 sends LIKE for a named unit; an ordering makes non-equality filters a ranking.
            named = bool(req.filters) and all(
                any(item["column"] == d for item in req.filters)
                and (req.order_desc is None or all(
                    item["operator"] == "=" for item in req.filters if item["column"] == d))
                for d in req.dimensions)
            scope = ranking.get("scope")
            if scope is not None:
                if not isinstance(scope, str) or not scope.strip():
                    raise ValueError("Invalid ranking scope")
                if not named:
                    period += f" AND ({scope})"
            base = ranking.get("base")
            if base is not None and not compare:
                if not isinstance(base, str) or not base.strip():
                    raise ValueError("Invalid ranking base")
                base_sql = render(base, metric, frozenset())
                base_name = ranking.get("base_name_th") or "ฐาน"
                if not isinstance(base_name, str):
                    raise ValueError("Invalid ranking base name")
        columns = [*dims]
        having = []
        compare_note = None
        if compare:
            label_now, label_then = _period_label(req.period, req.mode), _period_label(req.base_period, req.mode)
            columns += [f"{then} AS {_quote(f'{alias} {label_then}')}", f"{now} AS {_quote(f'{alias} {label_now}')}",
                        f"({now}) - ({then}) AS {_quote('ผลต่าง (จุด %)' if alias != metric.name_th else 'ผลต่าง')}"]
            if dims and total is None:
                # units in both periods only; "ดีกว่าปีก่อน" keeps those that went up (CMP-2 ข)
                having = [f"COUNT(CASE WHEN {in_period(p)} THEN 1 END) > 0" for p in (req.base_period, req.period)]
                if req.change is not None:
                    having.append(f"({now}) - ({then}) {'>' if req.change == 'up' else '<'} 0")
            compare_note = (f"เทียบ {label_now} กับ {label_then}; ผลต่าง = {label_now} − {label_then}"
                            + ("" if req.change is None or not having
                               else "; แสดงเฉพาะหน่วยที่ผลต่าง > 0 (ดีขึ้น)" if req.change == "up"
                               else "; แสดงเฉพาะหน่วยที่ผลต่าง < 0 (แย่ลง)"))
        else:
            if total is None:
                for extra in metric.extra_columns or ():
                    columns.append(f"({render(extra['expr'], metric, frozenset())}) AS {_quote(extra['name_th'])}")
            if base_sql is not None:
                columns.append(f"({base_sql}) AS {_quote(base_name)}")
            columns.append(f"{measure} AS {_quote(alias)}")
            if total is None and dims and ranking:
                # sales vs target: units without a target have no % to compare (`positive`), and "มากกว่าเป้า"
                # keeps the units on the asked side of the declared line (`threshold`)
                positive = ranking.get("positive")
                if positive is not None and not named:  # a unit asked for by name (see scope above) keeps its row
                    if not isinstance(positive, str) or not positive.strip():
                        raise ValueError("Invalid ranking positive")
                    having.append(f"({render(positive, metric, frozenset())}) > 0")
                if req.threshold is not None:
                    line = ranking.get("threshold")
                    value = line.get("value") if isinstance(line, dict) else None
                    if type(value) not in (int, float):
                        raise ValueError("Invalid ranking threshold")
                    sign = ">=" if req.threshold == "above" else "<"
                    having.append(f"{measure} {sign} {value}")
                    compare_note = f"แสดงเฉพาะหน่วยที่ {alias} {'≥' if sign == '>=' else '<'} {value}"
        sql = f"SELECT {', '.join(columns)} FROM {_quote(table)} WHERE {period}"
        if dims:
            sql += " GROUP BY " + ", ".join(dims)
        if having:
            sql += " HAVING " + " AND ".join(having)
        if req.order_desc is not None:
            sql += f" ORDER BY {len(columns)} {'DESC' if req.order_desc else 'ASC'}"
        if req.limit is not None:
            sql += f" LIMIT {req.limit}"
        return Compiled(sql, metric.metric_id, metric.name_th, metric.unit, official, table, metric.note_th, base_name,
                        compare_note)
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Invalid metric declaration or compile request") from exc

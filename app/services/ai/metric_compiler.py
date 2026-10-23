"""Compile declared metrics in code (plan/RESEARCH_DECLARED_METRICS.md §3).

Only names and synonyms are exposed to intent extraction; owner-declared formulas
stay here. Loading fails open, while unsupported compilation fails closed.
"""

from dataclasses import dataclass, fields, replace
import json
import logging
import re

from sqlalchemy import text


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


def load_metrics(context_name: str, config_engine=None) -> list[Metric]:
    """Read active rows afresh, decoding the JSON strings stored by sync_metrics."""
    try:
        if config_engine is None:
            from app.db.session import config_engine
        columns = ", ".join(f.name for f in fields(Metric))
        with config_engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT {columns} FROM schema_metrics WHERE context_name = :c "
                "AND status = 'active' AND is_active = 1 ORDER BY id"
            ), {"c": context_name}).mappings()
            metrics = []
            for row in rows:
                values = dict(row)
                for key in ("synonyms", "period", "dimensions", "terms", "official_total", "reference"):
                    if isinstance(values[key], str):
                        values[key] = json.loads(values[key])
                values["synonyms"] = tuple(values["synonyms"] or ())
                if values["dimensions"] is not None:
                    values["dimensions"] = tuple(values["dimensions"])
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
                for key in ("dataset", "period", "dimensions", "official_scope")
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


def metric_catalog(metrics: list[Metric]) -> str:
    return "\n".join(f"- {m.metric_id}: {m.name_th} (คำพ้อง: {', '.join(m.synonyms)})" for m in metrics)


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


@dataclass(frozen=True)
class Compiled:
    sql: str
    metric_id: str
    name_th: str
    unit: str | None
    official: bool
    table: str
    note_th: str | None


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


def supports(intent: dict, metric: Metric) -> bool:
    try:
        if intent.get("intent_type") not in ("aggregation", "ranking"):
            return False
        _validate_shape(intent.get("dimensions", []), intent.get("filters", []), metric)
        ordering = intent.get("ordering")
        if ordering is not None:
            if not isinstance(ordering, dict) or ordering.get("column") not in (*(metric.dimensions or ()), None):
                return False
            if ordering.get("direction") not in (None, "ASC", "DESC"):
                return False
        return True
    except (AttributeError, TypeError, ValueError):
        return False


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


def compile(req: CompileRequest, resolved: dict[str, Metric]) -> Compiled:
    """Compile a single-period SELECT; invalid or unsupported input raises ValueError."""
    try:
        metric = resolved[req.metric_id]
        _validate_shape(req.dimensions, req.filters, metric)
        if req.mode not in ("cumulative", "month"):
            raise ValueError("Unknown metric mode")
        if type(req.period) is not int or (req.limit is not None and (type(req.limit) is not int or req.limit < 0)):
            raise ValueError("Period and limit must be integers; limit must be nonnegative")
        if req.order_desc is not None and type(req.order_desc) is not bool:
            raise ValueError("Invalid ordering")

        def expression(current: Metric, visiting: frozenset[str]) -> str:
            if current.metric_id in visiting:
                raise ValueError("Cyclic metric expression")
            if current.dataset != metric.dataset or current.period != metric.period:
                raise ValueError("Referenced metric must use the same dataset and period mapping")
            value = _quote(current.period["value"][req.mode])

            def identifier(name: str) -> str:
                if name in current.terms:
                    where = current.terms[name]["where"]
                    if not isinstance(where, str) or not where.strip():
                        raise ValueError("Missing term predicate")
                    return f"(COALESCE(SUM(CASE WHEN ({where}) THEN {value} END), 0))"
                if name in resolved:
                    return f"({expression(resolved[name], visiting | {current.metric_id})})"
                raise ValueError(f"Unknown metric expression identifier: {name}")

            return _Expression(current.expr, identifier).parse()

        expr = expression(metric, frozenset())
        official = not req.dimensions and not req.filters
        total = metric.official_total if official and req.official_total_ok else None
        table = total["dataset"] if total is not None else metric.dataset
        period = f'CAST({_quote(metric.period["column"])} AS INTEGER) = {req.period}'
        dims = [_quote(d) for d in req.dimensions]
        if total is not None:
            measure = _quote(total["month_column" if req.mode == "month" else "column"])
        else:
            measure = f"({expr})"
            if official and metric.official_scope:
                period += f" AND ({metric.official_scope})"
            for item in req.filters:
                column, operator, value = _quote(item["column"]), item["operator"], item["value"]
                if operator == "IN":
                    predicate = f"{column} IN ({', '.join(_literal(v) for v in value)})"
                else:
                    if operator == "LIKE" and "%" not in value:
                        value = f"%{value}%"
                    predicate = f"{column} {operator} {_literal(value)}"
                period += f" AND {predicate}"
        selection = ", ".join([*dims, f"{measure} AS {_quote(metric.name_th)}"])
        sql = f"SELECT {selection} FROM {_quote(table)} WHERE {period}"
        if dims:
            sql += " GROUP BY " + ", ".join(dims)
        if req.order_desc is not None:
            sql += f" ORDER BY {len(dims) + 1} {'DESC' if req.order_desc else 'ASC'}"
        if req.limit is not None:
            sql += f" LIMIT {req.limit}"
        return Compiled(sql, metric.metric_id, metric.name_th, metric.unit, official, table, metric.note_th)
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Invalid metric declaration or compile request") from exc

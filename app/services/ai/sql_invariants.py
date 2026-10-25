"""Judge period semantics without executing SQL or consulting context storage."""

from dataclasses import dataclass
import json
import threading

import duckdb


@dataclass(frozen=True)
class Violation:
    code: str
    name: str
    columns: tuple[str, ...]
    blocking: bool


_parser_lock = threading.Lock()
_parser_conn = None
_QUERY_NODES = ("SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE")


def _nodes(value):
    """Keep a block's expressions separate from nested query blocks."""
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item)
    elif isinstance(value, dict) and value.get("type") not in _QUERY_NODES:
        yield value
        for key, item in value.items():
            if key != "cte_map":
                yield from _nodes(item)


def _columns(value):
    return {node["column_names"][-1].lower() for node in _nodes(value)
            if node.get("type") == "COLUMN_REF" and node.get("column_names")}


def _conjuncts(expr):
    if isinstance(expr, dict):
        if expr.get("type") == "CONJUNCTION_AND":
            for child in expr.get("children", []):
                yield from _conjuncts(child)
        else:
            yield expr


def check(sql: str, point_in_time, summable, period_columns) -> list[Violation]:
    """Catch inflated YTD aggregates while preserving single-period compiler SQL."""
    pit = {name.lower() for name in point_in_time}
    periods = {name.lower() for name in period_columns}
    if not pit or not periods:
        return []
    monthly = {name.lower() for name in summable}
    global _parser_conn
    with _parser_lock:
        if _parser_conn is None:
            _parser_conn = duckdb.connect(":memory:")
        cur = _parser_conn.cursor()
    try:
        tree = json.loads(cur.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    except duckdb.Error:
        return []
    finally:
        cur.close()
    if tree.get("error") or len(tree.get("statements", [])) != 1:
        return []

    def period_ref(expr):
        while isinstance(expr, dict) and expr.get("class") == "CAST":
            expr = expr.get("child")
        return isinstance(expr, dict) and expr.get("type") == "COLUMN_REF" and bool(_columns(expr) & periods)

    def single_period(expr):
        if expr.get("type") == "COMPARE_EQUAL":
            left, right = expr.get("left") or {}, expr.get("right") or {}
            return any(period_ref(ref) and (value.get("class") == "CONSTANT"
                       or (value.get("class") == "SUBQUERY" and value.get("subquery_type") == "SCALAR"))
                       for ref, value in ((left, right), (right, left)))
        children = expr.get("children", [])
        return (expr.get("type") == "COMPARE_IN" and len(children) == 2
                and period_ref(children[0]) and children[1].get("class") == "CONSTANT")

    found = {"I1": set(), "I2": set(), "I3": set()}
    facts = {}

    def analyze(node, visible):
        if id(node) in facts:
            return facts[id(node)]
        visible = dict(visible)
        cte_map = node.get("cte_map") or {}
        for entry in cte_map.get("map", []):
            body = entry.get("value") or {}
            # DuckDB <2 uses query.node; 2.x uses query_node.
            query = (body.get("query") or {}).get("node") or body.get("query_node") or {}
            name = str(entry.get("key", "")).lower()
            if query.get("type") == "RECURSIVE_CTE_NODE":
                visible[name] = (False, False)
            visible[name] = analyze(query, visible)

        def nested(value):
            if isinstance(value, list):
                for item in value:
                    nested(item)
            elif isinstance(value, dict):
                if value.get("type") in _QUERY_NODES:
                    analyze(value, visible)
                else:
                    for key, item in value.items():
                        if key != "cte_map":
                            nested(item)

        contents = [value for key, value in node.items() if key != "cte_map"]
        nested(contents)
        if node.get("type") != "SELECT_NODE":
            branches = [facts[id(node[key])] for key in ("left", "right") if key in node]
            result = (bool(branches) and all(p for p, _ in branches), any(h for _, h in branches))
            facts[id(node)] = result
            return result

        sources = []
        conditions = [node.get("where_clause")]
        for ref in _nodes(node.get("from_table")):
            if ref.get("type") == "JOIN":
                conditions.append(ref.get("condition"))
            elif ref.get("type") == "SUBQUERY" and "class" not in ref:
                sources.append(facts[id(ref["subquery"]["node"])])
            elif (ref.get("type") == "BASE_TABLE" and not ref.get("schema_name")
                  and not ref.get("catalog_name") and ref.get("table_name", "").lower() in visible):
                sources.append(visible[ref["table_name"].lower()])
        # ponytail: a base fact table joined to a pinned CTE is taken as pinned; no column lineage.
        pinned = (any(single_period(c) for expr in conditions for c in _conjuncts(expr))
                  or bool(sources) and all(p for p, _ in sources))
        grouped = any(period_ref(expr) for expr in node.get("group_expressions", []))
        has_period = (bool(_columns([conditions, node.get("select_list")]) & periods)
                      or grouped or any(h for _, h in sources))
        own = list(_nodes(contents))
        excluded = set()
        for agg in own:
            if agg.get("class") not in ("FUNCTION", "WINDOW") or agg.get("function_name", "").lower() not in ("sum", "avg"):
                continue
            args = agg.get("children", [])
            case_pinned = any(single_period(c) for case in _nodes(args) if case.get("class") == "CASE"
                              for branch in case.get("case_checks", []) for c in _conjuncts(branch.get("when_expr")))
            partitioned = any(period_ref(expr) for expr in agg.get("partitions", []))
            if pinned or grouped or partitioned or case_pinned:
                continue
            columns = _columns(args)
            if columns & pit:
                found["I1"].update(columns & pit)
                excluded.update(id(expr) for expr in _nodes(agg))
            found["I3"].update(columns & monthly)
        if not has_period:
            found["I2"].update(expr["column_names"][-1].lower() for expr in own
                               if id(expr) not in excluded and expr.get("type") == "COLUMN_REF"
                               and expr.get("column_names") and expr["column_names"][-1].lower() in pit)
        facts[id(node)] = (pinned, has_period)
        return facts[id(node)]

    analyze(tree["statements"][0].get("node") or {}, {})
    return [Violation(code, name, tuple(sorted(found[code])), code != "I3") for code, name in (
        ("I1", "ytd_summed_across_periods"), ("I2", "ytd_without_period"), ("I3", "month_summed_as_ytd"),
    ) if found[code]]

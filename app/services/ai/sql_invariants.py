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
    tables: tuple[str, ...] = ()


_parser_lock = threading.Lock()
_parser_conn = None
_QUERY_NODES = ("SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE")
# I4: statistics that depend on how many rows there are, not on what the rows add up to
_AVERAGES = ("avg", "mean", "median", "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop")
_AGGREGATES = _AVERAGES + ("sum", "count", "count_star", "min", "max")


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


def _calls(nodes, names):
    return [node for node in nodes
            if node.get("class") in ("FUNCTION", "WINDOW") and node.get("function_name", "").lower() in names]


def check(sql: str, point_in_time, summable, period_columns, grain=None) -> list[Violation]:
    """Catch inflated YTD aggregates while preserving single-period compiler SQL; given `grain`
    ({table: its key columns}) also catch averages taken over a table's raw rows (I4)."""
    pit = {name.lower() for name in point_in_time}
    periods = {name.lower() for name in period_columns}
    monthly = {name.lower() for name in summable}
    grain = {table.lower(): {key.lower() for key in keys} for table, keys in (grain or {}).items()}
    ytd = bool(pit and periods)
    if not ytd and not (grain and monthly):
        return []
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

    def column_of(expr):
        while isinstance(expr, dict) and expr.get("class") == "CAST":
            expr = expr.get("child")
        return _columns(expr) if isinstance(expr, dict) and expr.get("type") == "COLUMN_REF" else set()

    def fixed(expr):
        """Columns a predicate pins to one value: col = <constant | scalar subquery>, col IN (<one constant>)."""
        if expr.get("type") == "COMPARE_EQUAL":
            left, right = expr.get("left") or {}, expr.get("right") or {}
            return {name for ref, value in ((left, right), (right, left))
                    if value.get("class") == "CONSTANT"
                    or (value.get("class") == "SUBQUERY" and value.get("subquery_type") == "SCALAR")
                    for name in column_of(ref)}
        children = expr.get("children", [])
        if expr.get("type") == "COMPARE_IN" and len(children) == 2 and children[1].get("class") == "CONSTANT":
            return column_of(children[0])
        return set()

    def period_ref(expr):
        return bool(column_of(expr) & periods)

    def single_period(expr):
        return bool(fixed(expr) & periods)

    found = {"I1": set(), "I2": set(), "I3": set(), "I4": set()}
    raw_tables = set()  # I4: the tables whose raw rows were averaged
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
        tables, derived = [], False  # I4 reads real tables only: no lineage through a CTE / subquery
        for ref in _nodes(node.get("from_table")):
            if ref.get("type") == "JOIN":
                conditions.append(ref.get("condition"))
            elif ref.get("type") == "SUBQUERY" and "class" not in ref:
                sources.append(facts[id(ref["subquery"]["node"])])
                derived = True
            elif (ref.get("type") == "BASE_TABLE" and not ref.get("schema_name")
                  and not ref.get("catalog_name") and ref.get("table_name", "").lower() in visible):
                sources.append(visible[ref["table_name"].lower()])
                derived = True
            elif ref.get("type") == "BASE_TABLE":
                tables.append(ref.get("table_name", "").lower())
            elif ref.get("type") in ("TABLE_FUNCTION", "EXPRESSION_LIST"):
                derived = True
        # ponytail: a base fact table joined to a pinned CTE is taken as pinned; no column lineage.
        pinned = (any(single_period(c) for expr in conditions for c in _conjuncts(expr))
                  or bool(sources) and all(p for p, _ in sources))
        grouped = any(period_ref(expr) for expr in node.get("group_expressions", []))
        has_period = (bool(_columns([conditions, node.get("select_list")]) & periods)
                      or grouped or any(h for _, h in sources))
        own = list(_nodes(contents))
        excluded = set()
        for agg in own if ytd else ():
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
        if ytd and not has_period:
            found["I2"].update(expr["column_names"][-1].lower() for expr in own
                               if id(expr) not in excluded and expr.get("type") == "COLUMN_REF"
                               and expr.get("column_names") and expr["column_names"][-1].lower() in pit)
        keyed = [table for table in tables if table in grain] if not derived else []
        if keyed and monthly:
            raw_average(node, own, conditions, keyed)
        facts[id(node)] = (pinned, has_period)
        return facts[id(node)]

    def raw_average(node, own, conditions, keyed):
        """I4: an average of a summable measure over a table's raw rows — per row (org × product × ...),
        not per month or per unit — unless every key but one is pinned (GROUP BY / PARTITION BY / = value)."""
        select = node.get("select_list", [])
        groups = node.get("group_expressions", [])
        group_all = node.get("aggregate_handling") == "FORCE_AGGREGATES"
        pins = {name for expr in conditions for c in _conjuncts(expr) for name in fixed(c)}
        group_pins = set()
        for expr in groups:
            position = (expr.get("value") or {}).get("value") if expr.get("class") == "CONSTANT" else None
            if isinstance(position, int) and 0 < position <= len(select):  # GROUP BY 1
                expr = select[position - 1]
            names = _columns(expr)
            group_pins |= names | {c for item in select if str(item.get("alias", "")).lower() in names
                                   for c in _columns(item)}
        if group_all:
            group_pins |= {c for item in select if not _calls(_nodes(item), _AGGREGATES) for c in _columns(item)}
        candidates = []  # (measure columns, pinned keys)
        for agg in _calls(own, _AVERAGES):
            args = agg.get("children", [])
            if agg.get("class") != "WINDOW":
                candidates.append((_columns(args), pins | group_pins))
            elif not (groups or group_all or _calls(_nodes(args), _AGGREGATES)):  # a window over groups is not raw
                candidates.append((_columns(args), pins | _columns(agg.get("partitions", []))))
        for div in own:  # SUM(x) / COUNT(*): an average by hand; COUNT(DISTINCT <period>) divides per period
            children = div.get("children", [])
            if div.get("class") != "FUNCTION" or div.get("function_name") != "/" or len(children) != 2:
                continue
            counts = _calls(_nodes(children[1]), ("count", "count_star"))
            if counts and not any(c.get("distinct") for c in counts):
                sums = _calls(_nodes(children[0]), ("sum",))
                candidates.append((_columns([s.get("children", []) for s in sums]), pins | group_pins))
        for columns, pinned_keys in candidates:
            rows = [table for table in keyed if len(grain[table] - pinned_keys) > 1]
            if columns & monthly and rows:
                found["I4"].update(columns & monthly)
                raw_tables.update(rows)

    analyze(tree["statements"][0].get("node") or {}, {})
    return [Violation(code, name, tuple(sorted(found[code])), code != "I3",
                      tuple(sorted(raw_tables)) if code == "I4" else ()) for code, name in (
        ("I1", "ytd_summed_across_periods"), ("I2", "ytd_without_period"), ("I3", "month_summed_as_ytd"),
        ("I4", "avg_over_fact_rows"),
    ) if found[code]]

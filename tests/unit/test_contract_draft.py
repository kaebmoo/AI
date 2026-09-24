"""The contract drafter (Plan 8 §9.3) on two small bundles built here: what the data proves, it proposes."""
import pytest

from app.services import contract_draft as cd

PERIODS = [202501, 202502, 202503, 202504, 202505, 202506]
BASE = [1000.0, 3000.0, 2000.0, 4000.0, 1500.0, 2500.0]  # a flow goes up and down; a balance only climbs
ORG = [("A1", "unit A", "div 1"), ("A2", "unit A", "div 1"), ("B1", "unit B", "div 1"), ("C1", "unit C", "div 2")]


def monthly(p, cc):
    return BASE[PERIODS.index(p)] + {"A1": 10, "A2": 20, "B1": 30, "C1": 40}[cc]


@pytest.fixture
def bundles(tmp_path):
    con = cd.connect()
    left, right = tmp_path / "ledger", tmp_path / "report"
    left.mkdir()
    right.mkdir()
    lines = []
    for cc, _, _ in ORG:
        ytd = 0.0
        for p in PERIODS:
            ytd += monthly(p, cc)
            lines.append((p, cc, "line", monthly(p, cc), ytd))
    totals = [(p, cc, "total", m, y) for p, cc, _, m, y in lines]  # a subtotal row per cost center, as in fact_ebt
    rows = ", ".join(f"({p}, '{cc}', '{t}', {m}, {y})" for p, cc, t, m, y in lines + totals)
    con.execute(f"COPY (SELECT * FROM (VALUES {rows}) v(time_key, cost_center, row_type, amount, amount_ytd)) "
                f"TO '{left}/fact_ledger.parquet'")
    org = ", ".join(f"('{c}', '{u}', '{d}')" for c, u, d in ORG)
    con.execute(f"COPY (SELECT * FROM (VALUES {org}) v(cost_center, unit, division)) TO '{left}/dim_org.parquet'")
    # the other bundle reports the same lines per division — period as text, one cell booked differently
    by_div = {}
    for p, cc, _, m, _ in lines:
        div = next(d for c, _, d in ORG if c == cc)
        by_div[(p, div)] = by_div.get((p, div), 0.0) + m
    by_div[(202503, "div 2")] += 100.0
    rows = ", ".join(f"('{p}', '{d}', {v})" for (p, d), v in by_div.items())
    con.execute(f"COPY (SELECT * FROM (VALUES {rows}) v(ym, division, value)) TO '{right}/fact_report.parquet'")
    return con, cd.draft(con, left, "ledger"), cd.draft(con, right, "report")


def test_a_year_to_date_column_is_proved_from_its_monthly_sibling(bundles):
    _, ledger, _ = bundles
    agg = ledger.datasets["fact_ledger"].agg
    assert agg["amount"]["agg"] == "sum"
    assert agg["amount_ytd"]["agg"] == "point_in_time" and agg["amount_ytd"]["confidence"] == "high"
    assert "amount" in agg["amount_ytd"]["evidence"]


def test_a_total_row_is_flagged_as_not_addable(bundles):
    _, ledger, _ = bundles
    levels = {lv["column"]: lv for lv in ledger.datasets["fact_ledger"].levels}
    assert "row_type" in levels and any("total" in w for w in levels["row_type"]["why"])
    assert "cost_center" not in levels  # its values add up to nothing twice
    assert ledger.datasets["fact_ledger"].agg["amount"]["confidence"] == "high"  # the flow of a proved balance


def test_kind_keys_fk_and_hierarchy(bundles):
    _, ledger, _ = bundles
    fact, dim = ledger.datasets["fact_ledger"], ledger.datasets["dim_org"]
    assert (fact.kind, dim.kind) == ("fact", "dim")
    assert dim.unique and dim.keys == ["cost_center"]
    assert set(fact.keys) == {"time_key", "cost_center", "row_type"} and fact.unique
    assert fact.fks["cost_center"]["dataset"] == "dim_org"
    assert ["cost_center", "unit", "division"] in dim.hierarchies
    assert fact.period == "time_key" and ledger.primary == "fact_ledger"


def test_a_relationship_is_found_by_reconciling_cells_and_its_exception_is_listed(bundles):
    con, ledger, report = bundles
    assert report.datasets["fact_report"].period == "ym"  # YYYYMM as text
    found = cd.find_bridges(con, ledger, report)
    assert found, "the per-division totals agree in all but one cell"
    best = found[0]
    # a slice by row_type, never the whole column that counts every line twice (here line = total per cost center)
    assert best["left_measure"].startswith("amount[row_type=")
    assert "fact_ledger.cost_center→dim_org.division = fact_report.division" in best["grain"]
    assert best["cells"] == 12 and best["cells_matched"] == 11
    assert best["exceptions"][0]["cell"] == [202503, "div 2"] and best["exceptions"][0]["diff"] == -100.0


def test_the_draft_reads_as_a_contract_and_scores_against_the_owners(bundles):
    _, ledger, _ = bundles
    doc = cd.to_contract(ledger)
    assert doc["period_key"] == "time_key" and doc["scope_columns"] == {"year_month": "time_key"}
    cols = {c["name"]: c for c in next(d for d in doc["datasets"] if d["name"] == "fact_ledger")["columns"]}
    assert cols["amount_ytd"]["agg"] == "point_in_time" and cols["cost_center"]["fk"] == "dim_org.cost_center"
    asks = " ".join(qn["ask"] for qn in doc["draft"]["questions"])
    assert "row_type" in asks and "cost_center" in asks  # the not-addable column, the org scope candidate
    owner = {"period_key": "time_key", "primary_dataset": "fact_ledger", "scope_columns": {"org_code": "cost_center"},
             "business_rules": [{"text": "row_type = total is a subtotal"}],
             "datasets": [{"name": "fact_ledger", "kind": "fact", "keys": ["time_key", "cost_center", "row_type"], "columns": [
                 {"name": "amount", "dtype": "double", "agg": "sum"},
                 {"name": "amount_ytd", "dtype": "double", "agg": "sum"},
                 {"name": "cost_center", "dtype": "string", "fk": "dim_org.cost_center"}]}]}
    score = cd.compare(doc, owner)
    assert score["agg"] == "1/2" and score["agg_wrong"] == ["fact_ledger.amount_ytd: point_in_time (contract sum)"]
    assert score["fk"] == "1/1" and score["keys_jaccard"] == 1.0 and score["org_scope_offered"] is True
    assert score["flagged_in_owner_rules"] == ["fact_ledger.row_type"]

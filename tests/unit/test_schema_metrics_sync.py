"""Contract metrics use the same provenance writer and withdrawal rules as other knowledge."""

from copy import deepcopy
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.schema_models import SchemaMetric
from app.services import datafeed_knowledge as dk
from tests.unit import knowledge_db


@pytest.fixture
def engine(tmp_path):
    engine = knowledge_db.make(tmp_path / "metrics.db")
    yield engine
    engine.dispose()


@pytest.fixture
def contract():
    return {
        "domain": "ebt", "schema_version": "1", "primary_dataset": "fact_ebt", "period_key": "time_key",
        "datasets": [
            {"name": "fact_ebt", "columns": [
                {"name": name, "dtype": "double" if name.startswith("amount") else "string"}
                for name in ("time_key", "division", "sub_unit", "measure_type", "group_0", "group_1",
                             "amount", "amount_ytd")]},
            {"name": "total", "columns": [{"name": name, "dtype": "double"}
                                           for name in ("ebt", "ebt_month", "nohr", "nohr_month")]},
        ],
        "metrics": [
            {"id": "ebt", "name_th": "กำไรก่อนภาษี", "synonyms": ["EBT", "กำไร"], "dataset": "fact_ebt",
             "period": {"column": "time_key", "value": {"cumulative": "amount_ytd", "month": "amount"}},
             "dimensions": ["division", "sub_unit"],
             "terms": {"rev": {"where": "measure_type = 'SUBTOTAL' AND group_1 = 'รายได้'"},
                       "exp": {"where": "measure_type <> 'COMPUTED' AND group_0 LIKE 'ค่า%'"}},
             "expr": "rev - exp", "official_scope": "division IN ('สายงาน 1', 'สายงาน 2')",
             "official_total": {"dataset": "total", "column": "ebt", "month_column": "ebt_month"},
             "reference": {"control_totals": "ebt"}, "unit": "บาท", "note_th": "สะสม ณ งวด"},
            {"id": "ebt_excluding_personnel", "name_th": "ไม่รวมบุคลากร", "extends": "ebt",
             "synonyms": ["nohr"], "terms": {"hr": {"where": "measure_type != 'COMPUTED' "
                                                      "AND group_1 IN ('แรงงาน', 'สวัสดิการ')"}},
             "expr": "ebt + hr", "unit": "บาท",
             "official_total": {"dataset": "total", "column": "nohr", "month_column": "nohr_month"}},
            {"id": "ebt_margin", "name_th": "อัตรากำไร", "extends": "ebt",
             "expr": "ebt / nullif(rev, 0) * 100", "unit": "percent"},
        ],
    }


def sync(engine, contract):
    with engine.begin() as conn:
        return dk.sync_knowledge(conn, "ebt", contract)


def stored(engine):
    with engine.connect() as conn:
        return {r["metric_id"]: dict(r) for r in conn.execute(text(
            "SELECT * FROM schema_metrics WHERE context_name = 'feed_ebt' ORDER BY id")).mappings()}


def test_sync_round_trip_and_model(engine, contract):
    original = deepcopy(contract)
    assert sync(engine, contract) == ("feed_ebt", 12, 3)
    rows = stored(engine)
    assert set(rows) == {m["id"] for m in contract["metrics"]}
    for row in rows.values():
        assert (row["source"], row["status"], row["is_active"]) == ("declared", "active", 1)
    base = rows["ebt"]
    assert base["dataset"] == "feed_ebt_fact_ebt"
    for field in ("synonyms", "period", "dimensions", "terms", "reference"):
        assert json.loads(base[field]) == contract["metrics"][0][field]
        assert base[field] == json.dumps(contract["metrics"][0][field], ensure_ascii=False, sort_keys=True)
    assert json.loads(base["official_total"]) == {
        "dataset": "feed_ebt_total", "column": "ebt", "month_column": "ebt_month"}
    # Resolve inheritance only to validate: the stored child retains exactly its own declaration.
    child = rows["ebt_excluding_personnel"]
    assert child["dataset"] is None and child["period"] is None and child["dimensions"] is None
    assert child["official_scope"] is None
    assert json.loads(child["terms"]) == contract["metrics"][1]["terms"]
    assert rows["ebt_margin"]["official_total"] is None
    assert rows["ebt_margin"]["reference"] is None and rows["ebt_margin"]["synonyms"] is None
    assert contract == original
    with Session(engine) as session:
        row = session.query(SchemaMetric).filter_by(metric_id="ebt").one()
        data = row.to_dict()
        assert data["period"] == contract["metrics"][0]["period"]
        assert data["source"] == "declared" and data["created_at"]


def test_second_sync_does_not_write_even_if_json_key_order_changes(engine, contract):
    sync(engine, contract)
    with engine.begin() as conn:
        conn.execute(text("UPDATE schema_metrics SET updated_at = '2000-01-01 00:00:00'"))
        conn.execute(text("CREATE TRIGGER metrics_no_updates BEFORE UPDATE ON schema_metrics "
                          "BEGIN SELECT RAISE(ABORT, 'unexpected update'); END"))
    before = stored(engine)
    contract["metrics"][0]["terms"] = dict(reversed(list(contract["metrics"][0]["terms"].items())))
    sync(engine, contract)
    assert stored(engine) == before


def test_unknown_term_column_skips_only_invalid_metric(engine, contract, caplog):
    contract["metrics"][1]["terms"]["hr"]["where"] = "unknown_column = 'value'"
    sync(engine, contract)
    assert set(stored(engine)) == {"ebt", "ebt_margin"}
    assert "unknown_column" in caplog.text and "Skipping metric ebt_excluding_personnel" in caplog.text


@pytest.mark.parametrize("field,value,reason", [
    ("extends", "unknown", "not an earlier metric id"),
    ("extends", "ebt_excluding_personnel", "not an earlier metric id"),
    ("dataset", "missing", "unknown dataset"),
    ("period", {"column": "absent", "value": {"month": "amount", "cumulative": "amount_ytd"}}, "period column"),
    ("period", {"column": "time_key", "value": {"month": "absent", "cumulative": "amount_ytd"}}, "period column"),
    ("period", {"column": "time_key", "value": {"month": "amount", "cumulative": "absent"}}, "period column"),
    ("dimensions", ["absent"], "unknown dimensions"),
    ("expr", "ebt_margin + hr", "unknown expr identifiers"),
    ("official_total", {"dataset": "missing", "column": "ebt", "month_column": "ebt_month"}, "official_total dataset"),
    ("official_total", {"dataset": "total", "column": "absent", "month_column": "ebt_month"}, "official_total column"),
    ("official_total", {"dataset": "total", "column": "ebt", "month_column": "absent"}, "official_total month_column"),
])
def test_invalid_references_are_logged_and_skipped(engine, contract, caplog, field, value, reason):
    contract["metrics"][1][field] = value
    sync(engine, contract)
    assert set(stored(engine)) == {"ebt", "ebt_margin"}
    assert reason in caplog.text


def test_where_literals_are_not_column_references(engine, contract):
    contract["metrics"][1]["terms"]["hr"]["where"] = (
        "amount > 0 AND amount_ytd < 100 AND group_1 = 'it''s unknown_column = 1' "
        'AND group_0 = "also_unknown IN (1)"')
    sync(engine, contract)
    assert len(stored(engine)) == 3


def test_withdrawal_preserves_manual_rejected_and_other_context_rows(engine, contract):
    sync(engine, contract)
    with engine.begin() as conn:
        conn.execute(text("UPDATE schema_metrics SET source = 'manual' WHERE metric_id = 'ebt_margin'"))
        conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, expr, source, status) "
                          "VALUES ('feed_ebt', 'rejected', 'rejected', '1', 'declared', 'rejected'), "
                          "('other', 'ebt', 'other context', '1', 'declared', 'active')"))
    contract["metrics"] = contract["metrics"][:1]
    sync(engine, contract)
    assert set(stored(engine)) == {"ebt", "ebt_margin", "rejected"}
    assert stored(engine)["ebt_margin"]["source"] == "manual"
    contract.pop("metrics")
    sync(engine, contract)
    assert set(stored(engine)) == {"ebt_margin", "rejected"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM schema_metrics WHERE context_name = 'other'")).scalar_one() == 1


@pytest.mark.parametrize("source,status", [("manual", "active"), ("declared", "rejected"), (None, "active")])
def test_protected_row_waits_as_a_proposal(engine, contract, source, status):
    sync(engine, contract)
    with engine.begin() as conn:
        conn.execute(text("UPDATE schema_metrics SET source = :s, status = :st WHERE metric_id = 'ebt'"),
                     {"s": source, "st": status})
    before = stored(engine)["ebt"]
    contract["metrics"][0]["name_th"] = "ฉบับใหม่"
    sync(engine, contract)
    sync(engine, contract)
    assert stored(engine)["ebt"] == before
    with engine.connect() as conn:
        proposal = conn.execute(text("SELECT * FROM knowledge_proposals WHERE table_name = 'schema_metrics'" )).mappings().one()
        assert proposal["source"] == "declared" and proposal["status"] == "proposed"
        assert json.loads(proposal["proposed"])["name_th"] == "ฉบับใหม่"


def test_changed_declaration_updates_and_stamps_the_row(engine, contract):
    sync(engine, contract)
    with engine.begin() as conn:
        conn.execute(text("UPDATE schema_metrics SET updated_at = '2000-01-01 00:00:00' WHERE metric_id = 'ebt'"))
    contract["metrics"][0]["note_th"] = "แก้ไขแล้ว"
    sync(engine, contract)
    assert stored(engine)["ebt"]["note_th"] == "แก้ไขแล้ว"
    assert stored(engine)["ebt"]["updated_at"] != "2000-01-01 00:00:00"


def test_missing_table_is_safe_and_warns_once(engine, contract, monkeypatch, caplog):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE schema_metrics"))
    monkeypatch.setattr(dk, "_metrics_missing_warned", False)
    assert sync(engine, contract) == ("feed_ebt", 12, 3)
    assert sync(engine, contract) == ("feed_ebt", 12, 3)
    assert caplog.text.count("schema_metrics unavailable") == 1


def test_ranking_is_declared_validated_and_stored(engine, contract):
    """ebt 1.6.0: `ranking: {scope, base, base_name_th}` on a ratio — stored as JSON; a scope that names a column the
    dataset lacks, or a base with an unknown identifier, skips that metric (the others still sync)."""
    contract = deepcopy(contract)
    contract["datasets"][0]["columns"].append({"name": "is_hq", "dtype": "integer"})
    contract["metrics"][2]["ranking"] = {"scope": "is_hq = 0", "base": "rev", "base_name_th": "รายได้"}
    sync(engine, contract)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT ranking FROM schema_metrics WHERE metric_id = 'ebt_margin'")).scalar()
    assert json.loads(row) == {"base": "rev", "base_name_th": "รายได้", "scope": "is_hq = 0"}
    # an invalid declaration is skipped with a warning: the last valid row stays (existing rule for any invalid metric)
    for bad in ({"scope": "is_support = 0"}, {"base": "revenue"}, "is_hq = 0", {"extra": 1}):
        contract["metrics"][2]["ranking"] = bad
        sync(engine, contract)
        with engine.connect() as conn:
            kept = conn.execute(text("SELECT ranking FROM schema_metrics WHERE metric_id = 'ebt_margin'")).scalar()
        assert json.loads(kept) == {"base": "rev", "base_name_th": "รายได้", "scope": "is_hq = 0"}, bad
    contract["metrics"][2].pop("ranking")  # withdrawn from the contract → cleared
    sync(engine, contract)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT ranking FROM schema_metrics WHERE metric_id = 'ebt_margin'")).scalar() is None

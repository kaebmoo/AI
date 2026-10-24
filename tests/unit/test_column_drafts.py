"""Column drafts use measured/declared facts and wait for a person's decision."""

import csv
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.v1.admin import schema
from app.config import settings
from app.services import data_sources
from app.services.column_drafts import draft_columns
from app.services.context_onboarding import DataInspector
from tests.unit import knowledge_db

TABLE = "feed_ebt_fact_ebt"
SENTINEL = "ZQX_ROW_SECRET"
COLUMNS = [
    ("time_key", "BIGINT"), ("division", "VARCHAR"), ("unit", "VARCHAR"),
    ("unit_short_name", "VARCHAR"), ("amount", "DOUBLE"), ("amount_ytd", "DOUBLE"),
    ("cost_center", "VARCHAR"), ("opaque", "VARCHAR"), ("row_rejected", "VARCHAR"),
    ("untracked", "VARCHAR"),
]


@pytest.fixture
def feed(tmp_path, monkeypatch):
    root = tmp_path / "latest"
    root.mkdir()
    data_path = root / "fact_ebt.csv"
    with data_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c for c, _ in COLUMNS])
        for period in (202601, 202602, 202609):
            for i, unit in enumerate(("ฝ่าย Alpha", "ฝ่าย Beta", "ฝ่าย Gamma", "ทีม Delta")):
                writer.writerow((period, f"{SENTINEL} {i}", unit, f"U{i}", i + 0.5, i + 10.5,
                                 f"C{i}", None, f"{SENTINEL} {i}", f"{SENTINEL} {i}"))
    contract_path = tmp_path / "contract.yaml"
    contract = {"domain": "ebt", "schema_version": "1.0.0", "primary_dataset": "fact_ebt", "datasets": [{
        "name": "fact_ebt", "keys": ["time_key", "cost_center"],
        "columns": [{"name": c, "dtype": "double" if t == "DOUBLE" else "string"}
                    | ({"agg": "sum", "unit": "บาท"} if c == "amount" else {})
                    | ({"agg": "point_in_time", "unit": "บาท"} if c == "amount_ytd" else {})
                    for c, t in COLUMNS],
    }]}
    contract_path.write_text(yaml.safe_dump(contract, allow_unicode=True))
    config_path = tmp_path / "config.sqlite"
    config = knowledge_db.make(config_path)
    with config.begin() as conn:
        conn.execute(text(
            "INSERT INTO data_sources (id, name, source_type, root_path, contract_file) "
            "VALUES (1, 'datafeed_ebt', 'duckdb_file', :root, :contract)"
        ), {"root": str(root), "contract": str(contract_path)})
        conn.execute(text(
            "INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (1, :t, :f, :c)"
        ), {"t": TABLE, "f": data_path.name, "c": json.dumps([{"name": c, "type": t} for c, t in COLUMNS])})
        conn.execute(text(
            "INSERT INTO schema_contexts (name, main_view, source_id) VALUES ('feed_ebt', :t, 1)"
        ), {"t": TABLE})
        conn.execute(text(
            "INSERT INTO schema_metadata (table_name, column_name, description, source, status) "
            "VALUES (:t, :c, :d, :source, :status)"
        ), [{"t": TABLE, "c": c, "d": "Already described" if c == "division" else (" \t\n " if c == "unit" else None),
             "source": "inferred" if c == "unit" else "declared",
             "status": "rejected" if c == "row_rejected" else "active"}
            for c, _ in COLUMNS if c != "untracked"])
        for level, (label, col) in enumerate(zip(
            ["สายงาน", "กลุ่ม", "ฝ่าย", "ส่วน", "ศูนย์ต้นทุน", "INACTIVE", "PROPOSED"],
            ["division", "group", "unit", "section", "cost_center", "unit", "unit"],
        )):
            conn.execute(text(
                "INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, "
                "level_columns, detection_keywords, is_active, status) "
                "VALUES ('feed_ebt', :level, :label, :label, :cols, '[]', :active, :status)"
            ), {"level": level, "label": label, "cols": json.dumps([col]),
                "active": int(level != 5), "status": "proposed" if level == 6 else "active"})
    resolver = data_sources.SourceResolver(config_engine=config, cache_dir=str(tmp_path / "cache"))
    monkeypatch.setattr(data_sources, "source_resolver", resolver)
    monkeypatch.setattr("app.db.session.config_engine", config)
    monkeypatch.setattr(settings, "CONFIG_DB_URL", f"sqlite:///{config_path}")
    # A broken source must fail before ever trying a legacy copy.
    monkeypatch.setattr(settings, "BUSINESS_DB_PATH", str(tmp_path / "DO_NOT_OPEN"))
    yield SimpleNamespace(config=config, path=config_path, data_path=data_path, contract_path=contract_path)
    resolver._adapters.clear()
    config.dispose()


def _snapshot(feed):
    return json.dumps(knowledge_db.rows(feed.path, "SELECT * FROM schema_metadata ORDER BY id")).encode()


def _draft(feed):
    with feed.config.begin() as conn:
        return draft_columns(conn, TABLE)


@pytest.fixture
def api(feed, monkeypatch):
    service = Mock()
    clear = Mock()
    dirty = Mock()
    monkeypatch.setattr(schema, "clear_query_cache", clear)
    monkeypatch.setattr(schema, "mark_brain_dirty", dirty)
    app = FastAPI()
    app.include_router(schema.router, prefix="/admin")

    def db():
        with sessionmaker(bind=feed.config)() as session:
            yield session

    app.dependency_overrides[deps.get_config_db] = db
    app.dependency_overrides[deps.require_admin] = lambda: SimpleNamespace(role="admin")
    app.dependency_overrides[deps.get_schema_service] = lambda: service
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, service=service, clear=clear, dirty=dirty)


def test_measured_contract_and_hierarchy_facts_only_queue_proposals(feed):
    before = _snapshot(feed)
    result = _draft(feed)
    drafts = {d["column_name"]: d for d in result["drafts"]}
    assert result["table"] == TABLE
    assert result["drafted"] == 6
    unit = drafts["unit"]
    assert "ฝ่าย" in unit["description"] and "ระดับ 3" in unit["description"]
    assert "สายงาน > กลุ่ม > ฝ่าย > ส่วน > ศูนย์ต้นทุน" in unit["description"]
    assert unit["facts"]["prefix"] == {"word": "ฝ่าย", "share": 0.75, "level_number": 3}
    assert "75%" in unit["description"]
    assert "INACTIVE" not in unit["description"] and "PROPOSED" not in unit["description"]
    assert "ชื่อย่อของ unit (คู่ 1:1)" in drafts["unit_short_name"]["description"]
    assert "ห้าม SUM ข้ามงวด" in drafts["amount_ytd"]["description"]
    assert "SUM ข้ามงวดได้" in drafts["amount"]["description"]
    assert "หน่วย: บาท" in drafts["amount"]["description"]
    assert "202601–202609" in drafts["time_key"]["description"]
    assert drafts["time_key"]["facts"]["key"] == ["cost_center"]
    assert {d["column_name"] for d in result["skipped"]} == {"division", "opaque", "row_rejected"}
    assert "untracked" not in drafts
    assert _snapshot(feed) == before
    assert _draft(feed)["drafted"] == 0
    assert _snapshot(feed) == before
    assert knowledge_db.rows(feed.path, "SELECT source, status, count(*) FROM knowledge_proposals GROUP BY source, status") == [
        ("inferred", "proposed", 6)]


@pytest.mark.parametrize("policy", ["aggregated_only", "schema_only"])
def test_restricted_policy_never_proposes_row_values(feed, policy):
    with feed.config.begin() as conn:
        conn.execute(text("UPDATE data_sources SET llm_data_policy = :p"), {"p": policy})
        # Make the sentinel eligible for a prefix draft under full policy.
        conn.execute(text("UPDATE schema_metadata SET description = NULL WHERE column_name = 'division'"))
    result = _draft(feed)
    assert SENTINEL not in json.dumps(result)
    assert "202601" not in json.dumps(result)
    for draft in result["drafts"]:
        assert not {"prefix", "pair", "period"} & draft["facts"].keys()
    assert {d["column_name"] for d in result["drafts"]} == {
        "division", "unit", "time_key", "cost_center", "amount", "amount_ytd"}
    assert SENTINEL not in str(knowledge_db.rows(feed.path, "SELECT proposed FROM knowledge_proposals"))


def test_missing_contract_still_uses_profile_and_hierarchy(feed):
    feed.contract_path.unlink()
    drafts = {d["column_name"]: d for d in _draft(feed)["drafts"]}
    assert "unit" in drafts and "period" in drafts["time_key"]["facts"]
    assert "amount" not in drafts and "amount_ytd" not in drafts
    assert all(not {"key", "measure"} & d["facts"].keys() for d in drafts.values())


def test_drafting_does_not_trigger_contract_sync(feed, monkeypatch):
    from app.services import datafeed_knowledge

    monkeypatch.setattr(datafeed_knowledge, "_seen", {})
    monkeypatch.setattr(datafeed_knowledge, "mark_brain_dirty", lambda: None)
    sync = Mock(wraps=datafeed_knowledge.ensure_current)
    monkeypatch.setattr(datafeed_knowledge, "ensure_current", sync)
    contract = yaml.safe_load(feed.contract_path.read_text())
    contract.update(schema_version="1.0.0", primary_dataset="fact_ebt")
    feed.contract_path.write_text(yaml.safe_dump(contract, allow_unicode=True))
    before = _snapshot(feed)
    _draft(feed)
    assert _snapshot(feed) == before
    assert knowledge_db.rows(feed.path, "SELECT knowledge_sha FROM data_sources") == [(None,)]
    sync.assert_not_called()


def test_api_routes_decisions_and_cache_refresh(feed, api):
    client = api.client
    before = _snapshot(feed)
    response = client.post("/admin/schema/columns/draft", params={"table": TABLE})
    assert response.status_code == 200 and response.json()["drafted"] == 6
    assert _snapshot(feed) == before
    response = client.get("/admin/schema/columns/drafts", params={"table": TABLE})
    assert response.status_code == 200
    drafts = {d["column_name"]: d for d in response.json()}
    assert len(drafts) == 6
    assert drafts["amount"]["current_description"] is None
    assert 0 <= drafts["amount"]["confidence"] <= 1
    assert drafts["amount"]["reason"] and drafts["amount"]["created_at"]
    assert client.get("/admin/schema/columns/drafts", params={"table": "other"}).json() == []
    accepted = drafts["unit"]["id"]
    url = f"/admin/schema/columns/drafts/{accepted}/accept"
    assert client.post(url, json={"description": " \t "}).status_code == 400
    edited = "คำอธิบายที่คนตรวจแล้ว"
    response = client.post(url, json={"description": edited})
    assert response.status_code == 200
    column = response.json()
    assert (column["description"], column["source"], column["status"]) == (edited, "manual", "active")
    assert column["updated_at"]
    assert knowledge_db.rows(feed.path, "SELECT status FROM knowledge_proposals WHERE id = ?", (accepted,)) == [("accepted",)]
    api.service.refresh_cache.assert_called_once()
    api.clear.assert_called_once()
    api.dirty.assert_called_once()
    assert client.get(f"/admin/schema/columns/{column['id']}").json() == column
    assert client.put(f"/admin/schema/columns/{column['id']}", json={"description": edited + " แก้"}).status_code == 200
    assert client.post(url).status_code == 404
    assert client.post(f"/admin/schema/columns/drafts/{accepted}/reject").status_code == 404

    rejected = drafts["amount_ytd"]["id"]
    before_reject = _snapshot(feed)
    url = f"/admin/schema/columns/drafts/{rejected}/reject"
    assert client.post(url).status_code == 200
    assert _snapshot(feed) == before_reject
    assert knowledge_db.rows(feed.path, "SELECT status FROM knowledge_proposals WHERE id = ?", (rejected,)) == [("rejected",)]
    assert client.post(url).status_code == 404
    assert client.post(f"/admin/schema/columns/drafts/{rejected}/accept").status_code == 404
    assert client.post("/admin/schema/columns/draft", params={"table": TABLE}).json()["drafted"] == 0
    assert knowledge_db.rows(feed.path, "SELECT count(*) FROM knowledge_proposals") == [(6,)]
    assert {d["id"] for d in client.get("/admin/schema/columns/drafts", params={"table": TABLE}).json()} == {
        d["id"] for d in drafts.values()} - {accepted, rejected}
    # Accepting without a body uses exactly the text in the queue.
    amount = drafts["amount"]
    response = client.post(f"/admin/schema/columns/drafts/{amount['id']}/accept")
    assert response.status_code == 200
    assert response.json()["description"] == amount["description"]
    assert (response.json()["source"], response.json()["status"]) == ("manual", "active")


def test_api_not_found_and_unavailable_source(feed, api, caplog):
    client = api.client
    assert client.post("/admin/schema/columns/draft", params={"table": "missing"}).status_code == 404
    for action in ("accept", "reject"):
        assert client.post(f"/admin/schema/columns/drafts/99999/{action}").status_code == 404
    assert client.get("/admin/schema/columns/99999").status_code == 404
    assert client.post("/admin/schema/columns/draft", params={"table": TABLE}).status_code == 200
    drafts = client.get("/admin/schema/columns/drafts", params={"table": TABLE}).json()
    with feed.config.begin() as conn:
        conn.execute(text("DELETE FROM schema_metadata WHERE column_name = :c"), {"c": drafts[0]["column_name"]})
    assert client.post(f"/admin/schema/columns/drafts/{drafts[0]['id']}/accept").status_code == 404
    feed.data_path.unlink()
    response = client.post("/admin/schema/columns/draft", params={"table": TABLE})
    assert response.status_code == 503
    assert response.json() == {"detail": "File source unavailable"}
    assert "could not open source" in caplog.text


def test_api_requires_admin(feed, api):
    from fastapi import HTTPException

    def refuse():
        raise HTTPException(status_code=403, detail="Admin required")

    api.app.dependency_overrides[deps.require_admin] = refuse
    for method, path in (("post", "draft"), ("get", "drafts"),
                         ("post", "drafts/1/accept"), ("post", "drafts/1/reject")):
        assert getattr(api.client, method)(f"/admin/schema/columns/{path}", params={"table": TABLE}).status_code == 403


def test_all_distinct_fallback_counts_distinct_values_not_rows(feed):
    with feed.data_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c for c, _ in COLUMNS])
        for i in range(120):
            # First word is generic; 72/120 distinct strings share it, despite many repeated minority rows.
            unit = f"{SENTINEL if i < 72 else 'other'} {i}"
            for _ in range(1 if i < 72 else 5):
                writer.writerow((202601, "D", unit, f"U{i}", 1, 2, f"C{i}", None, None, None))
    unit = next(d for d in _draft(feed)["drafts"] if d["column_name"] == "unit")
    assert unit["facts"]["prefix"] == {"word": SENTINEL, "share": 0.6}


def test_pair_period_and_prefix_require_all_values(monkeypatch):
    from app.services.column_drafts import _value_facts

    monkeypatch.setattr(data_sources, "policy_for_table", lambda *_: "full")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE facts (x TEXT, x_fname TEXT, x_sname TEXT, x_short_name TEXT, "
                             "valid INTEGER, invalid INTEGER, decimal_period REAL, sparse TEXT)")
        conn.exec_driver_sql("INSERT INTO facts VALUES "
                             "('A', 'Alpha', 'a', 'a', 190001, 202601, 202601.0, 'word A'), "
                             "('B', 'Beta', 'b', 'a', 299912, 202613, 202602.0, 'word B'), "
                             "(NULL, 'Ignored', NULL, NULL, NULL, NULL, NULL, 'other C'), "
                             "(NULL, NULL, NULL, NULL, NULL, NULL, NULL, ''), "
                             "(NULL, NULL, NULL, NULL, NULL, NULL, NULL, '   ')")
    inspector = DataInspector(engine)
    try:
        profile = inspector.inspect("facts")
        with inspector._connect() as conn:
            facts = _value_facts(inspector, conn, "facts", profile.columns)
        assert facts["x_fname"]["pair"][0]["role"] == "full name"
        assert facts["x_sname"]["pair"][0]["role"] == "short name"
        assert "pair" not in facts["x_short_name"]
        assert len(facts["x"]["pair"]) == 2
        assert facts["valid"]["period"] == {"min": 190001, "max": 299912}
        assert "period" not in facts["invalid"] and "period" not in facts["decimal_period"]
        assert "prefix" not in facts["sparse"]  # empty and whitespace strings count in the denominator
    finally:
        engine.dispose()


@pytest.fixture
def extended_feed(feed):
    extra = [("org_group", "VARCHAR"), ("division_abbr", "VARCHAR"),
             ("sub_unit_fname", "VARCHAR"), ("sub_unit_sname", "VARCHAR"),
             ("sub_unit_short_name", "VARCHAR"), ("sub_unit_abbr", "VARCHAR"),
             ("year_ce", "BIGINT"), ("year_be", "BIGINT"), ("year_th", "BIGINT"),
             ("month_no", "BIGINT"), ("number", "BIGINT")]
    with feed.data_path.open(newline="") as f:
        rows = list(csv.reader(f))[1:]
    units = ["ฝ่ายธุรกิจลูกค้าเอกชน", "ฝ่ายธุรกิจลูกค้าองค์กร", "ฝ่ายธุรกิจบริการ", "ทีมบริการ"]
    groups = ["กลุ่มธุรกิจลูกค้าเอกชน", "กลุ่มธุรกิจลูกค้าองค์กร", "กลุ่มธุรกิจลูกค้าบริการ", "กลุ่มสนับสนุน"]
    with feed.data_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c for c, _ in COLUMNS + extra])
        for i, row in enumerate(rows):
            row[2] = units[i % 4]
            writer.writerow(row + [groups[i % 4], f"D{i % 4}", f"ส่วนธุรกิจลูกค้า {i % 4}",
                                   f"S{i % 4}", f"SN{i % 4}", f"SA{i % 4}",
                                   2025 + i % 2, 2568 + i % 2, 2568 + i % 2,
                                   1 + i % 12, 1 + i % 12])
    with feed.config.begin() as conn:
        conn.execute(text("UPDATE source_tables SET columns = :c"),
                     {"c": json.dumps([{"name": c, "type": t} for c, t in COLUMNS + extra])})
        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, source, status) "
                          "VALUES (:t, :c, 'declared', 'active')"),
                     [{"t": TABLE, "c": c} for c, _ in extra])
        conn.execute(text(
            "INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, "
            "level_columns, detection_keywords, is_active, status) "
            "VALUES ('other_context', :level, :label, :label, '[]', '[]', :active, :status)"
        ), [{"level": 0, "label": "กลุ่มธุรกิจ", "active": 1, "status": "active"},
            {"level": 1, "label": "กลุ่มธุรกิจลูกค้า", "active": 0, "status": "active"},
            {"level": 2, "label": "ฝ่ายธุรกิจ", "active": 1, "status": "proposed"}])
    return feed


def test_unspaced_prefixes_use_longest_active_label_and_own_context_note(extended_feed):
    drafts = {d["column_name"]: d for d in _draft(extended_feed)["drafts"]}
    unit = drafts["unit"]
    assert unit["facts"]["prefix"]["word"] == "ฝ่าย"
    assert unit["facts"]["prefix"]["share"] == 0.75
    assert "ตรงกับชื่อระดับ 'ฝ่าย' (ระดับ 3) ของโครงสร้าง" in unit["description"]
    assert "สายงาน > กลุ่ม > ฝ่าย > ส่วน > ศูนย์ต้นทุน" in unit["description"]
    group = drafts["org_group"]
    # The shorter own-context label matches 100%; the longer foreign label matches 75%.
    assert group["facts"]["prefix"] == {"word": "กลุ่มธุรกิจ", "share": 0.75}
    assert "ตรงกับชื่อระดับ" not in group["description"]
    with extended_feed.config.begin() as conn:
        conn.execute(text("UPDATE master_hierarchy SET context_name = 'feed_ebt', level = 7 "
                          "WHERE context_name = 'other_context' AND level = 0"))
    group = next(d for d in _draft(extended_feed)["drafts"] if d["column_name"] == "org_group")
    assert "ตรงกับชื่อระดับ 'กลุ่มธุรกิจ' (ระดับ 8) ของโครงสร้าง" in group["description"]


def test_abbreviations_and_name_siblings_without_bare_column(extended_feed):
    drafts = {d["column_name"]: d for d in _draft(extended_feed)["drafts"]}
    assert "ชื่อย่อของ division (คู่ 1:1)" in drafts["division_abbr"]["description"]
    for suffix in ("sname", "short_name", "abbr"):
        short = drafts[f"sub_unit_{suffix}"]
        assert "ชื่อย่อของ sub_unit_fname (คู่ 1:1)" in short["description"]
        assert short["facts"]["pair"] == [
            {"column": "sub_unit_fname", "role": "short name", "is_name": True}]
    assert "sub_unit_sname" in drafts["sub_unit_fname"]["description"]


def test_year_and_month_facts_require_integer_time_profile(extended_feed):
    drafts = {d["column_name"]: d for d in _draft(extended_feed)["drafts"]}
    assert "ปี ค.ศ. ช่วง 2025–2026" in drafts["year_ce"]["description"]
    for name in ("year_be", "year_th"):
        assert "ปี พ.ศ. ช่วง 2568–2569" in drafts[name]["description"]
    assert "เดือน (1–12)" in drafts["month_no"]["description"]
    assert "งวด ค.ศ. YYYYMM ช่วง 202601–202609" in drafts["time_key"]["description"]
    assert "number" not in drafts


def test_extended_value_facts_are_policy_gated(extended_feed):
    with extended_feed.config.begin() as conn:
        conn.execute(text("UPDATE data_sources SET llm_data_policy = 'aggregated_only'"))
    result = _draft(extended_feed)
    assert all(not {"prefix", "pair", "period"} & d["facts"].keys() for d in result["drafts"])
    assert {d["column_name"] for d in result["drafts"]} == {
        "unit", "time_key", "cost_center", "amount", "amount_ytd"}
    assert all(value not in json.dumps(result, ensure_ascii=False)
               for value in ("ฝ่ายธุรกิจลูกค้าเอกชน", "กลุ่มธุรกิจลูกค้าเอกชน", "2025", "2568", SENTINEL))


@pytest.mark.parametrize("values, expected", [
    ([1, 12], {"min": 1, "max": 12, "kind": "month"}),
    ([1900, 2399], {"min": 1900, "max": 2399, "kind": "year_ce"}),
    ([2400, 2799], {"min": 2400, "max": 2799, "kind": "year_be"}),
    ([0, 12], None), ([1, 13], None), ([1899, 2026], None),
    ([2399, 2400], None), ([2569, 2800], None), ([], None),
])
def test_time_facts_use_all_values_and_range_boundaries(values, expected):
    from app.services.column_drafts import _value_facts
    from app.services.context_onboarding import ColumnProfile

    column = ColumnProfile(name="period", data_type="INTEGER", all_distinct=values, is_time_column=True)
    facts = _value_facts(None, None, "unused", [column])
    assert facts["period"].get("period") == expected

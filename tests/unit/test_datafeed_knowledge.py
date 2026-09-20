"""
Plan 7 Phase 2: contract → knowledge as a service, re-synced when the contract changes.

- sync is idempotent; keywords/priority are insert-only (admin edits survive re-syncs)
- the resolver re-syncs on the next request after the contract (or build schema) changes,
  once across processes (compare-and-set), never fails the request, clears the query cache
"""

import hashlib
import json
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import create_engine, text

from app.services import datafeed_knowledge as dk
from app.services.data_sources import SourceResolver
from scripts.migrate_data_sources import migrate

CONTRACT = {
    "domain": "x", "schema_version": "1.0.0", "title": "X feed", "units": "บาท",
    "period_key": "year_month", "primary_dataset": "fact_bu_monthly",
    "business_rules": [{"id": "r1", "text": "กฎหนึ่ง"}],
    "datasets": [{
        "name": "fact_bu_monthly", "kind": "fact", "grain": "bu x month", "keys": ["year_month"],
        "columns": [{"name": "year_month", "dtype": "Int64", "description": "งวด"},
                    {"name": "bu", "dtype": "string", "description": "BG"},
                    {"name": "revenue", "dtype": "double", "description": "รายได้", "unit": "บาท"}],
    }],
}
CSV = "year_month,bu,revenue\n202608,01.A,1\n"


@pytest.fixture(autouse=True)
def _isolate():
    dk._seen.clear()
    with patch.object(dk, "mark_brain_dirty") as dirty:
        yield dirty
    dk._seen.clear()


@pytest.fixture
def config_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, display_name TEXT, "
            "description TEXT, main_view TEXT, is_active BOOLEAN DEFAULT 1, priority INTEGER DEFAULT 0, "
            "keywords TEXT, instruction_th TEXT, updated_at TIMESTAMP)"))
        conn.execute(text(
            "CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY, table_name TEXT, column_name TEXT, "
            "description TEXT, data_type TEXT, is_summable BOOLEAN, is_groupable BOOLEAN)"))
        conn.execute(text(
            "CREATE TABLE vanna_documentation (id INTEGER PRIMARY KEY, doc_key TEXT UNIQUE, title TEXT, "
            "content TEXT, category TEXT, context_name TEXT, is_active INTEGER)"))
    migrate(engine)
    return engine


def _knowledge(engine):
    with engine.connect() as conn:
        return (
            [tuple(r) for r in conn.execute(text(  # updated_at left out: it moves on every sync
                "SELECT id, name, display_name, description, main_view, is_active, priority, keywords, "
                "instruction_th FROM schema_contexts"))],
            [tuple(r)[1:] for r in conn.execute(text("SELECT * FROM schema_metadata ORDER BY column_name"))],
            [tuple(r)[1:] for r in conn.execute(text("SELECT * FROM vanna_documentation ORDER BY doc_key"))],
        )


def _sync(engine, contract=CONTRACT):
    with engine.begin() as conn:
        return dk.sync_knowledge(conn, "x", contract)


class TestSyncKnowledge:
    def test_insert_sets_router_defaults_and_is_idempotent(self, config_engine):
        assert _sync(config_engine) == ("feed_x", 3, 3)  # docs: table + rule + period format
        first = _knowledge(config_engine)
        ctx = first[0][0]
        assert ctx[1:4] == ("feed_x", "DataFeed x", "X feed")
        assert ctx[4] == "feed_x_fact_bu_monthly"  # no control_totals → primary_dataset
        assert ctx[6] == dk.FEED_PRIORITY and "feed" in json.loads(ctx[7])
        _sync(config_engine)
        assert _knowledge(config_engine) == first

    def test_the_contracts_own_sentence_is_the_context_description(self, config_engine):
        """The splitter and list_contexts read schema_contexts.description to choose a context, so it
        must be the owner's sentence about what this feed answers — not the label in `title`."""
        thai = "EBT ของ 2 สายงานขาย (รายได้ฐานยอดขาย − ค่าใช้จ่าย)\n— ไม่ใช่กำไรของทั้งบริษัท"
        _sync(config_engine, {**CONTRACT, "description": thai})
        with config_engine.connect() as conn:
            stored = conn.execute(text("SELECT description FROM schema_contexts")).scalar_one()
        # one line: the splitter lists one context per line
        assert stored == "EBT ของ 2 สายงานขาย (รายได้ฐานยอดขาย − ค่าใช้จ่าย) — ไม่ใช่กำไรของทั้งบริษัท"

        _sync(config_engine, {**CONTRACT, "description": ""})  # a contract without one falls back
        with config_engine.connect() as conn:
            assert conn.execute(text("SELECT description FROM schema_contexts")).scalar_one() == "X feed"

    def test_update_keeps_admin_keywords_but_refreshes_rules(self, config_engine):
        _sync(config_engine)
        with config_engine.begin() as conn:
            conn.execute(text("UPDATE schema_contexts SET keywords='[\"mine\"]', priority=7"))
        changed = {**CONTRACT, "business_rules": [{"id": "r2", "text": "กฎใหม่"}]}
        _sync(config_engine, changed)
        with config_engine.connect() as conn:
            kw, prio, instr = conn.execute(text("SELECT keywords, priority, instruction_th FROM schema_contexts")).one()
            docs = [r[0] for r in conn.execute(text("SELECT doc_key FROM vanna_documentation"))]
        assert (kw, prio) == ('["mine"]', 7)
        assert "กฎใหม่" in instr and "กฎหนึ่ง" not in instr
        assert "datafeed_x_rule_r2" in docs and "datafeed_x_rule_r1" not in docs

    def test_instruction_says_how_to_filter_time_without_year_month_columns(self, config_engine):
        """sales/ebt/expense have only the YYYYMM period column — without this line the model
        writes `year = 2025 AND month = 1` first and burns a retry on every question."""
        _sync(config_engine)
        with config_engine.connect() as conn:
            instr = conn.execute(text("SELECT instruction_th FROM schema_contexts")).scalar_one()
        assert "ไม่มีคอลัมน์ year" in instr and "year_month = 202501" in instr
        with_year = {**CONTRACT, "datasets": [{**CONTRACT["datasets"][0], "columns": CONTRACT["datasets"][0]["columns"]
                                               + [{"name": "year", "dtype": "Int64"}, {"name": "month", "dtype": "Int64"}]}]}
        _sync(config_engine, with_year)  # revenue: year/month exist — nothing to warn about
        with config_engine.connect() as conn:
            assert "ไม่มีคอลัมน์ year" not in conn.execute(text("SELECT instruction_th FROM schema_contexts")).scalar_one()

    def test_main_view_prefers_control_totals_source(self):
        assert dk.main_view_dataset({**CONTRACT, "control_totals": {"source": "fact_other"}}) == "fact_other"
        assert dk.main_view_dataset(CONTRACT) == "fact_bu_monthly"

    def test_instruction_lists_every_table_of_the_contract(self, config_engine):
        """The prompt describes the main view only. Questions the main view can't answer (ebt per cost
        center, revenue/sales full-year targets) need the other tables: their full names make them
        usable (hybrid_flow.table_rule), their columns let Pass 1 name a filter on them."""
        two = {**CONTRACT, "control_totals": {"source": "fact_bu_monthly", "bg_key": "bu"}, "datasets": CONTRACT["datasets"] + [{
            "name": "fact_target", "kind": "fact", "grain": "bu x month (plan)", "keys": ["year_month"],
            "columns": [{"name": "year_month", "dtype": "Int64"}, {"name": "revenue_target", "dtype": "double"}]}]}
        _sync(config_engine, two)
        with config_engine.connect() as conn:
            instr = conn.execute(text("SELECT instruction_th FROM schema_contexts")).scalar_one()
        assert "feed_x_fact_bu_monthly (ตารางหลัก" in instr
        assert "feed_x_fact_target" in instr and "bu x month (plan)" in instr and "year_month, revenue_target" in instr
        assert instr.index("feed_x_fact_target") < instr.index("กฎสำคัญ")

    def test_single_table_contract_gets_no_table_list(self):
        assert dk.tables_section("x", CONTRACT) == ""


def _contract_file(tmp_path, contract=CONTRACT):
    path = tmp_path / "x.yaml"
    path.write_text(yaml.safe_dump(contract, allow_unicode=True))
    return path


class TestSyncFromContract:
    def _source(self, engine, contract_path):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO data_sources (name, source_type, contract_file) "
                              "VALUES ('datafeed_x', 'duckdb_file', :c)"), {"c": str(contract_path)})

    def test_compare_and_set_syncs_once(self, config_engine, tmp_path, _isolate):
        path = _contract_file(tmp_path)
        self._source(config_engine, path)
        assert dk.sync_from_contract(config_engine, "datafeed_x", str(path), "1.0.0") is True
        # another process noticing the same change finds the key already stored
        assert dk.sync_from_contract(config_engine, "datafeed_x", str(path), "1.0.0") is False
        assert _isolate.call_count == 1
        # a new build schema_version alone is a new key → one more sync
        assert dk.sync_from_contract(config_engine, "datafeed_x", str(path), "1.1.0") is True

    def test_contract_of_another_domain_is_refused(self, config_engine, tmp_path):
        path = _contract_file(tmp_path, {**CONTRACT, "domain": "y"})
        self._source(config_engine, path)
        with pytest.raises(ValueError):
            dk.sync_from_contract(config_engine, "datafeed_x", str(path), "1.0.0")
        assert _knowledge(config_engine)[0] == []  # nothing written


class TestResolverResync:
    """A registered file source with contract_file: knowledge follows the contract, no script."""

    @pytest.fixture
    def env(self, config_engine, tmp_path):
        root = tmp_path / "latest"
        root.mkdir()
        (root / "fact_bu_monthly.csv").write_text(CSV)
        (root / "manifest.json").write_text(json.dumps({
            "period": 202608, "schema_version": "1.0.0", "reconcile": {"ok": True},
            "files": {"fact_bu_monthly.csv": {"sha256": hashlib.sha256(CSV.encode()).hexdigest()}}}))
        path = _contract_file(tmp_path)
        contract, raw = dk.load_contract(str(path))
        cols = [{"name": c["name"], "type": {"Int64": "BIGINT", "string": "VARCHAR", "double": "DOUBLE"}[c["dtype"]]}
                for c in CONTRACT["datasets"][0]["columns"]]
        with config_engine.begin() as conn:  # what register_file_source writes
            conn.execute(text(
                "INSERT INTO data_sources (name, source_type, root_path, manifest_file, contract_file, knowledge_sha) "
                "VALUES ('datafeed_x', 'duckdb_file', :r, 'manifest.json', :c, :k)"),
                {"r": str(root), "c": str(path), "k": dk.knowledge_key(raw, "1.0.0")})
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, file_name, columns) "
                              "VALUES (2, 'feed_x_fact_bu_monthly', 'fact_bu_monthly.csv', :c)"), {"c": json.dumps(cols)})
            dk.sync_knowledge(conn, "x", contract)
            conn.execute(text("UPDATE schema_contexts SET source_id = 2"))
        return SourceResolver(config_engine=config_engine, cache_dir=str(tmp_path / "cache")), path

    def _instruction(self, engine):
        with engine.connect() as conn:
            return conn.execute(text("SELECT instruction_th FROM schema_contexts")).scalar_one()

    def test_registered_knowledge_is_not_resynced(self, env, config_engine, _isolate):
        resolver, _ = env
        before = _knowledge(config_engine)
        resolver.for_context("feed_x")
        resolver.for_context("feed_x")
        assert _knowledge(config_engine) == before and _isolate.call_count == 0

    def test_contract_edit_resyncs_on_next_request(self, env, config_engine, _isolate):
        from app.services import query_engine as qe
        resolver, path = env
        resolver.for_context("feed_x")
        qe._query_cache["k"] = {"result": None, "ts": 0}
        _contract_file(path.parent, {**CONTRACT, "business_rules": [{"id": "r9", "text": "กฎจากสัญญาใหม่"}]})
        resolver.for_context("feed_x")
        assert "กฎจากสัญญาใหม่" in self._instruction(config_engine)
        assert _isolate.call_count == 1  # Sync Brain hint for the vanna docs
        assert "k" not in qe._query_cache  # answers made with the old knowledge are dropped

    def test_broken_contract_keeps_previous_knowledge(self, env, config_engine):
        resolver, path = env
        resolver.for_context("feed_x")
        path.write_text("domain: [unclosed")
        source = resolver.for_context("feed_x")  # the request still gets its source
        assert source.adapter.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_bu_monthly") == [{"n": 1}]
        assert "กฎหนึ่ง" in self._instruction(config_engine)


class TestRouterDefaults:
    """Feed contexts win only with a feed marker; plain questions keep their legacy context."""

    LEGACY = [  # live config.db 2026-09-18, ORDER BY priority DESC, id (get_all_contexts order)
        {"name": "revenue", "priority": 10,
         "keywords": ["รายได้", "revenue", "sales", "ยอดขาย", "income", "profit", "กำไร"]},
        {"name": "expense", "priority": 9,
         "keywords": ["ค่า", "ค่าใช้จ่าย", "ค่าเสื่อม", "expense", "cost", "ต้นทุน", "งบประมาณ", "spending", "pay", "จ่าย"]},
        {"name": "transfer price", "priority": 9, "keywords": ["ราคาโอน", "transfer price", "ฝ่าย", "หน่วยงาน"]},
        {"name": "pl_costtype", "priority": 5,
         "keywords": ["ผลดำเนินงาน", "กำไร", "ขาดทุน", "EBT", "กำไรขั้นต้น", "gross profit", "product", "service"]},
    ]

    @pytest.mark.parametrize("question,expected", [
        ("รายได้รวมเดือนล่าสุด", "revenue"), ("ค่าใช้จ่ายรวมเดือนล่าสุด", "expense"),
        ("ยอดขายเดือนนี้", "revenue"), ("EBT ของส่วนงาน", "pl_costtype"),
        ("รายได้ feed เดือนล่าสุด", "feed_revenue"), ("ข้อมูล feed ล่าสุด", "feed_revenue"),
        ("ค่าใช้จ่ายรวมจาก datafeed", "feed_expense"), ("ค่าเสื่อมราคาใน dashboard", "feed_expense"),
        ("ยอดขาย feed เดือนล่าสุด", "feed_sales"), ("EBT feed เดือนล่าสุด", "feed_ebt"),
        ("กำไร feed กรกฎาคม 2569", "feed_ebt"),
    ])
    def test_routes(self, question, expected):
        from unittest.mock import MagicMock
        from app.services.query_engine import detect_context_from_question

        feeds = [{"name": f"feed_{d}", "priority": dk.FEED_PRIORITY,
                  "keywords": dk.DOMAIN_KEYWORDS[d] + dk.FEED_MARKERS} for d in ("revenue", "expense", "sales", "ebt")]
        svc = MagicMock()
        svc.get_all_contexts.return_value = self.LEGACY + feeds
        assert detect_context_from_question(question, svc) == expected


def test_point_in_time_measures_are_not_summable(tmp_path):
    """`agg: point_in_time` means the column is a running total AT that period, so adding the
    periods up multiplies it. Summability came from the dtype alone, which said the opposite of
    the column's own description — and a portal answer summed revenue_ytd (RESULT_F11 §7)."""
    from sqlalchemy import create_engine, text

    from app.services import datafeed_knowledge

    contract = {
        "control_totals": {"measures": [{"name": "revenue", "agg": "sum"},
                                        {"name": "revenue_ytd", "agg": "point_in_time"}]},
        "datasets": [{
        "name": "fact_x", "keys": ["year_month"],
        "columns": [{"name": "year_month", "dtype": "bigint"},
                    {"name": "revenue", "dtype": "double"},
                    {"name": "revenue_ytd", "dtype": "double"},
                    {"name": "other_amount", "dtype": "double"}],  # no measure entry: unchanged
    }]}
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, description TEXT,"
                          " data_type TEXT, is_summable INT, is_groupable INT)"))
        datafeed_knowledge.sync_schema_metadata(conn, "r", contract)
        got = dict(conn.execute(text("SELECT column_name, is_summable FROM schema_metadata")).all())

    assert got["revenue"] == 1
    assert got["revenue_ytd"] == 0, "a point-in-time total must not be marked summable"
    assert got["other_amount"] == 1, "a double with no declared agg keeps the old behaviour"

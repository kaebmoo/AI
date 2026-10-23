"""A value only another table of the context holds is found, and the prompt says which table (2026-10-22).

"ebt ของ น่าน" / "ค่าใช้จ่ายของน่าน" got 0 rows: the keyword index was the main view's alone, "น่าน" is only in
feed_ebt_fact_ebt / feed_expense_dim_org_snapshot, and Pass 1 — which never saw value lookups — filtered `division`.
"""

from types import SimpleNamespace

from sqlalchemy import create_engine, text

from app.services.ai import hierarchy_context, hybrid_flow
from app.services.schema import keyword_index


def _config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (name TEXT, main_view TEXT, source_id INT)"))
        conn.execute(text("CREATE TABLE source_tables (source_id INT, table_name TEXT, is_active INT)"))
        conn.execute(text("CREATE TABLE keyword_value_index (keyword TEXT, column_name TEXT, column_value TEXT, "
                          "table_name TEXT, context_name TEXT)"))
        conn.execute(text("INSERT INTO schema_contexts VALUES ('feed_x', 'feed_x_main', 2), ('legacy', 'v_legacy', NULL)"))
        conn.execute(text("INSERT INTO source_tables VALUES (2, 'feed_x_main', 1), (2, 'feed_x_detail', 1), (2, 'feed_x_old', 0)"))
        conn.execute(text("INSERT INTO keyword_value_index VALUES ('gone', 'c', 'v', 'feed_x_dropped', 'feed_x')"))
    return engine


def test_every_table_of_the_context_is_indexed_and_a_dropped_one_is_cleared(tmp_path, monkeypatch):
    service = SimpleNamespace(engine=_config(tmp_path))
    assert keyword_index.context_tables(service, "feed_x", "feed_x_main") == ["feed_x_main", "feed_x_detail"]
    assert keyword_index.context_tables(service, "legacy", "v_legacy") == ["v_legacy"]
    built = []
    monkeypatch.setattr(keyword_index, "build_keyword_index", lambda svc, ctx, table: built.append(table) or 1)
    assert keyword_index.build_context_index(service, "feed_x", "feed_x_main") == 2 and built == ["feed_x_main", "feed_x_detail"]
    with service.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM keyword_value_index WHERE table_name = 'feed_x_dropped'")).scalar() == 0


def _lookup(monkeypatch, rows):
    found = SimpleNamespace(search_keyword_index=lambda keyword, context_name, limit: [dict(r, keyword=keyword) for r in rows])
    monkeypatch.setattr("app.services.schema_service.SchemaService", lambda **kw: found)
    monkeypatch.setattr("app.services.data_sources.source_resolver", SimpleNamespace(for_context=lambda c: SimpleNamespace(engine=None)))
    monkeypatch.setattr(hierarchy_context, "extract_keywords_from_question", lambda svc, q, c: ["น่าน"])
    return hierarchy_context.lookup_values_from_question(None, "ebt ของ น่าน", "feed_x", "feed_x_main")


def test_a_value_only_another_table_holds_is_labelled_and_reaches_pass_1(monkeypatch):
    matches = _lookup(monkeypatch, [{"column_name": "sub_unit_fname", "column_value": "ส่วน น่าน", "table_name": "feed_x_detail"}])
    assert matches[0]["other_table"] == "feed_x_detail"
    assert "ของตาราง `feed_x_detail`" in hierarchy_context.format_value_matches_flat(matches)
    note = hybrid_flow.value_note(matches)
    assert "feed_x_detail.sub_unit_fname = 'ส่วน น่าน'" in note


def test_a_value_the_main_view_holds_stays_there(monkeypatch):
    matches = _lookup(monkeypatch, [{"column_name": "unit", "column_value": "น่าน 1", "table_name": "feed_x_detail"},
                                    {"column_name": "division", "column_value": "น่าน", "table_name": "feed_x_main"}])
    assert [m["table_name"] for m in matches] == ["feed_x_main"] and "other_table" not in matches[0]
    assert hybrid_flow.value_note(matches) == "\nค่าจริงที่พบในข้อมูล: \"น่าน\" → division = 'น่าน' — " \
        "คำในคำถามที่ตรงกับค่าเหล่านี้ให้ใช้คอลัมน์นั้นเป็น filter (ตารางอื่น: ใช้ตาราง/JOIN ตามกฎของ context)"
    assert hybrid_flow.value_note([]) == ""
    assert "ของตาราง" not in hierarchy_context.format_value_matches_flat(matches)


def test_pass_1_gets_one_entry_per_column_and_never_a_period():
    matches = [{"keyword": "cctv", "column_name": "product_name", "column_value": v} for v in ("CCTV A", "CCTV B", "CCTV A")]
    matches.append({"keyword": "กันยายน 2569", "column_name": "month_year_th", "column_value": "กันยายน 2569", "other_table": "t"})
    note = hybrid_flow.value_note(matches)
    assert "product_name = 'CCTV A' (+1 ค่า)" in note and "month_year_th" not in note


def test_a_null_formula_is_retried_once_and_zeros_after_it_are_no_data():
    formula = "SELECT COALESCE(SUM(a), 0) - SUM(b) AS ebt FROM t"
    history = []
    assert hybrid_flow.null_arithmetic_error([{"ebt": None}], formula, history) == hybrid_flow.NULL_SUM_HINT
    assert hybrid_flow.null_arithmetic_error([{"ebt": None}], "SELECT SUM(a) FROM t", history) is None  # nothing matched
    assert hybrid_flow.null_arithmetic_error([{"ebt": 5.0}], formula, history) is None
    history.append({"error": hybrid_flow.NULL_SUM_HINT})
    assert hybrid_flow.null_arithmetic_error([{"ebt": None}], formula, history) is None  # once
    assert hybrid_flow.zeros_after_null_retry([{"ebt": 0}], history) == [{"ebt": None}]
    assert hybrid_flow.zeros_after_null_retry([{"ebt": 24410200.83}], history) == [{"ebt": 24410200.83}]
    assert hybrid_flow.zeros_after_null_retry([{"ebt": 0}], []) == [{"ebt": 0}]  # no retry: a real 0


def test_a_filter_on_the_value_the_lookup_found_still_counts_as_asked(monkeypatch):
    tables = {"feed_x_main": ["division", "ebt"], "feed_x_detail": ["sub_unit", "amount"]}
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda table, engine=None: tables)
    intent = {"filters": [{"column": "sub_unit", "operator": "LIKE", "value": "%ส่วนขายและบริการลูกค้า น่าน%"}]}
    assert hybrid_flow.unfilterable_columns(intent, "feed_x_main", question="ebt ของ น่าน เป็นเท่าไหร่") == \
        (["sub_unit"], ["feed_x_detail"])
    unasked = {"filters": [{"column": "sub_unit", "operator": "=", "value": "ส่วนขายและบริการลูกค้า แพร่"}]}
    assert hybrid_flow.unfilterable_columns(unasked, "feed_x_main", question="ebt ของ น่าน เป็นเท่าไหร่") == ([], [])

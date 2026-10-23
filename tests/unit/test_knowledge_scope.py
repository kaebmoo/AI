"""Knowledge no context owns reaches a context only where the columns it names exist.

The feed_ebt system prompt carried department_abbr 103 times — 188 semantic mappings and 50 business rules
written for the legacy views reached every context — and "ebt ของ น่าน" was filtered at the wrong level
(2026-10-22). The scope is computed from the registry, so a data set registered tomorrow is covered too.
"""

import json

import pytest
from sqlalchemy import create_engine, text

from app.services.schema import prompt_builder
from app.services.schema.knowledge_scope import ColumnScope, named, scope_for


def test_only_identifier_shaped_tokens_count():
    assert named('ใช้ department_abbr = \'อป.1\'', 'WHERE "กลุ่มธุรกิจ" = 1') == {"department_abbr", "กลุ่มธุรกิจ"}
    # words first: SQL keywords, "division by zero", the placeholders the rules are written with
    assert named("SELECT SUM(AMOUNT) FROM table WHERE YEAR = 2025 GROUP BY division") == set()
    assert named(None, "") == set()


def test_an_item_naming_a_column_this_context_lacks_does_not_apply():
    scope = ColumnScope(own=frozenset({"division", "sub_unit_fname", "time_key"}),
                        known=frozenset({"division", "sub_unit_fname", "time_key", "department_abbr", "section"}))
    assert not scope.applies("คำย่อที่มีตัวเลข ใช้ column department_abbr")
    assert scope.applies("กรองงวดด้วย time_key")
    assert scope.applies("สร้าง SQL เพียง query เดียว")  # names no column: everywhere, as before
    assert scope.applies("ใช้ section สำหรับจังหวัด")  # a plain word is not counted (the documented ceiling)
    assert scope.applies("= 'x'", column="sub_unit_fname")
    assert not scope.applies("= 'นป.'", column="organization_group_abbr")  # a mapping to a column no one has


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A legacy context on a SQLite view and a file-source context described by source_tables."""
    business = create_engine(f"sqlite:///{tmp_path / 'biz.sqlite'}")
    with business.begin() as conn:
        conn.execute(text("CREATE TABLE legacy_t (division TEXT, department_abbr TEXT, revenue REAL)"))
        conn.execute(text("CREATE VIEW v_legacy AS SELECT * FROM legacy_t"))
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE data_sources (id INTEGER PRIMARY KEY, name TEXT, source_type TEXT)"))
        conn.execute(text("CREATE TABLE source_tables (source_id INT, table_name TEXT, columns TEXT, is_active INT DEFAULT 1)"))
        conn.execute(text("CREATE TABLE schema_contexts (name TEXT, main_view TEXT, source_id INT, is_active INT DEFAULT 1, "
                          "status TEXT DEFAULT 'active')"))
        conn.execute(text("CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, status TEXT DEFAULT 'active')"))
        conn.execute(text("INSERT INTO data_sources VALUES (2, 'datafeed_x', 'duckdb_file')"))
        for table, cols in (("feed_x_summary", ["time_key", "division", "ebt"]),
                            ("feed_x_detail", ["time_key", "sub_unit_fname", "cost_center", "amount_ytd"])):
            conn.execute(text("INSERT INTO source_tables (source_id, table_name, columns) VALUES (2, :t, :c)"),
                         {"t": table, "c": json.dumps([{"name": c} for c in cols])})
        conn.execute(text("INSERT INTO schema_contexts (name, main_view, source_id) VALUES "
                          "('legacy_ctx', 'v_legacy', NULL), ('feed_x', 'feed_x_summary', 2)"))
        conn.execute(text("INSERT INTO schema_contexts (name, main_view, is_active) VALUES ('gone', 'v_gone', 0)"))
        conn.execute(text("INSERT INTO schema_metadata VALUES ('v_legacy', 'section', 'active')"))
    monkeypatch.setattr("app.db.session.business_engine", business)

    class Service:
        def get_config_engine(self):
            return config

        def get_business_rules(self, table_name, inject_mode=None):
            return RULES

        def get_semantic_mappings(self, context_name=None):
            return MAPPINGS

    return Service()


RULES = [
    {"table_name": None, "rule_name": "คำย่อหน่วยงาน", "rule_description": "ใช้ department_abbr", "severity": "info"},
    {"table_name": "ALL", "rule_name": "งวด", "rule_description": "time_key เป็น YYYYMM", "severity": "info"},
    {"table_name": None, "rule_name": "query เดียว", "rule_description": "สร้าง SQL เพียง query เดียว", "severity": "info"},
    # bound to a table by a person: shown where it was bound, whatever it names
    {"table_name": "feed_x_summary", "rule_name": "ของ feed", "rule_description": "ZQXOWN department_abbr", "severity": "info"},
]
MAPPINGS = [
    {"keyword": "บชง.", "keyword_type": "abbreviation", "target_column": "department_abbr", "target_condition": "= 'บชง.'",
     "full_condition": "department_abbr = 'บชง.'", "context_name": None},
    {"keyword": "น่าน", "keyword_type": "term", "target_column": "sub_unit_fname", "target_condition": "LIKE '%น่าน%'",
     "full_condition": "sub_unit_fname LIKE '%น่าน%'", "context_name": None},
    {"keyword": "ZQXBOUND", "keyword_type": "term", "target_column": "nowhere_col", "target_condition": "= 1",
     "full_condition": "", "context_name": "feed_x"},
]


def test_scope_is_read_from_the_registry(registry):
    feed = scope_for(registry, "feed_x")
    # every table of the file source counts, not only the main view
    assert {"sub_unit_fname", "cost_center", "ebt"} <= feed.own and "department_abbr" not in feed.own
    legacy = scope_for(registry, "legacy_ctx")
    assert {"division", "department_abbr", "revenue", "section"} <= legacy.own  # the view + its metadata
    assert {"department_abbr", "sub_unit_fname"} <= feed.known and feed.known == legacy.known
    assert scope_for(registry, "gone") is None and scope_for(registry, "nope") is None and scope_for(registry, None) is None


def test_rules_and_mappings_reach_only_the_contexts_whose_columns_they_name(registry):
    feed_rules = prompt_builder.build_business_rules_text(registry, "feed_x_summary", context_name="feed_x")
    assert "time_key เป็น YYYYMM" in feed_rules and "query เดียว" in feed_rules and "ZQXOWN" in feed_rules
    assert "ใช้ department_abbr" not in feed_rules
    legacy_rules = prompt_builder.build_business_rules_text(registry, "v_legacy", context_name="legacy_ctx")
    assert "ใช้ department_abbr" in legacy_rules and "time_key เป็น YYYYMM" not in legacy_rules

    feed_maps = prompt_builder.build_semantic_mapping_text(registry, context_name="feed_x")
    assert "น่าน" in feed_maps and "ZQXBOUND" in feed_maps and "บชง." not in feed_maps
    legacy_maps = prompt_builder.build_semantic_mapping_text(registry, context_name="legacy_ctx")
    assert "บชง." in legacy_maps and "น่าน" not in legacy_maps


def test_without_a_context_or_a_readable_registry_nothing_is_dropped(registry, monkeypatch):
    assert "ใช้ department_abbr" in prompt_builder.build_business_rules_text(registry, "feed_x_summary")
    monkeypatch.setattr(type(registry), "get_config_engine", lambda self: create_engine("sqlite:///:memory:"))
    assert "ใช้ department_abbr" in prompt_builder.build_business_rules_text(registry, "feed_x_summary", context_name="feed_x")


def test_rules_that_all_fall_away_leave_no_section_not_the_hardcoded_fallback(registry, monkeypatch):
    monkeypatch.setattr(type(registry), "get_business_rules", lambda self, table_name, inject_mode=None: [RULES[0]])
    text_ = prompt_builder.build_business_rules_text(registry, "feed_x_summary", context_name="feed_x")
    assert text_ == ""  # the fallback speaks of a Unix-ms DATE column the feed does not have

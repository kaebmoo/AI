"""REMAIN-9.5: hierarchy automation reads data from the context's source, config from the config DB."""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.services import hierarchy_service as hs
from tests.unit import knowledge_db

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "009_master_hierarchy.sql"


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    config = tmp_path / "config.db"
    conn = sqlite3.connect(config)
    conn.executescript(MIGRATION.read_text())
    conn.execute("ALTER TABLE master_hierarchy ADD COLUMN parent_column TEXT")  # later migration, as in config.db
    conn.execute("ALTER TABLE master_hierarchy ADD COLUMN source_view TEXT")
    conn.execute("CREATE TABLE schema_contexts (name TEXT, main_view TEXT, display_name TEXT, is_active INTEGER)")
    conn.execute("INSERT INTO schema_contexts VALUES ('ctx_h', 'v_org', 'Org', 1)")
    conn.execute("INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, "
                 "detection_keywords) VALUES ('ctx_h', 0, 'สายงาน', 'Division', '[\"division\"]', '[]')")
    conn.executemany("INSERT INTO master_hierarchy_values (context_name, level, value) VALUES ('ctx_h', 0, ?)",
                     [("A",), ("B",)])
    conn.commit()
    conn.close()
    knowledge_db.add_provenance(config)  # Plan 8.1 columns
    business = create_engine(f"sqlite:///{tmp_path / 'biz.db'}")
    with business.begin() as c:
        c.execute(text("CREATE TABLE org (division TEXT, department TEXT, v REAL)"))
        c.execute(text("INSERT INTO org VALUES ('A', 'A1', 1), ('A', 'A2', 1), ('C', 'C1', 1)"))
        c.execute(text("CREATE VIEW v_org AS SELECT * FROM org"))
    monkeypatch.setattr(hs.settings, "CONFIG_DB_URL", f"sqlite:///{config}")
    monkeypatch.setattr(hs, "_data_engine", lambda context_name: business)
    monkeypatch.setattr("app.db.session.business_engine", business)
    return config


def test_detect_changes_compares_against_the_business_view(dbs):
    result = hs.HierarchyService().detect_changes("ctx_h")
    assert [v["value"] for v in result["new_values"]] == ["C"]
    assert [v["value"] for v in result["missing_values"]] == ["B"]
    assert result["unchanged_count"] == 1


def test_bootstrap_reads_view_columns_and_writes_levels_to_config(dbs, monkeypatch):
    monkeypatch.setattr(hs.HierarchyService, "auto_extract", lambda self, ctx=None: [])
    result = hs.HierarchyService().bootstrap_from_view("ctx_new", "v_org")
    assert [lvl["col"] for lvl in result["levels_created"]] == ["division", "department"]
    rows = sqlite3.connect(dbs).execute(
        "SELECT level_columns FROM master_hierarchy WHERE context_name = 'ctx_new' ORDER BY level").fetchall()
    assert rows == [('["division"]',), ('["department"]',)]


def test_available_views_come_from_the_business_db(dbs):
    names = {v["view_name"] for v in hs.HierarchyService().get_available_views()}
    assert "v_org" in names

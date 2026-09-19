"""Plan 7 Phase 4b — one Vanna brain per workspace.

Exit: retrieval for workspace A never returns a golden/doc/DDL of workspace B. The brain is a
separate Chroma directory per workspace; what is trained into it is decided by BrainFilter
(pure, tested here — chromadb does not import on the test interpreter)."""

import pytest
from sqlalchemy import create_engine, text

from app.services.workspaces import BrainFilter, brain_path, workspace_of_context
from scripts.migrate_workspaces import migrate_config


@pytest.fixture
def config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, main_view TEXT, is_active BOOLEAN DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_contexts (name, main_view) VALUES ('revenue', 'revenue_search'), "
                          "('transfer price', 'v_transfer_price'), ('feed_sales', 'feed_sales_fact_sales'), ('hr_payroll', 'v_payroll')"))
    migrate_config(engine)
    return engine


def _move(engine, workspace, *contexts):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (name) VALUES (:n) ON CONFLICT(name) DO NOTHING"), {"n": workspace})
        for c in contexts:
            conn.execute(text("UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name = :w) WHERE name = :c"),
                         {"w": workspace, "c": c})


def test_before_any_workspace_exists_the_default_brain_is_everything(config):
    keep = BrainFilter("default", config)
    assert all(keep.context(c) for c in ("revenue", "feed_sales", "hr_payroll", None, "Top-N with Breakdown"))
    assert all(keep.view(v) for v in ("revenue_search", "feed_sales_fact_sales", None))


def test_a_workspace_brain_holds_its_own_contexts_only(config):
    _move(config, "nt-report", "feed_sales")
    _move(config, "hr", "hr_payroll")
    nt = BrainFilter("nt-report", config)
    assert nt.context("feed_sales") and nt.context("FEED SALES") and nt.view("feed_sales_fact_sales")
    assert not nt.context("hr_payroll") and not nt.context("revenue") and not nt.view("v_payroll")
    assert not nt.context(None) and not nt.view(None) and not nt.context("Top-N with Breakdown")  # unattributed = default's


def test_the_default_brain_loses_what_moved_away_and_keeps_the_unattributed(config):
    _move(config, "nt-report", "feed_sales")
    default = BrainFilter("default", config)
    assert default.context("revenue") and default.context("transfer_price") and default.context(None)
    assert default.context("Top-N with Breakdown")  # legacy golden categories are free text
    assert not default.context("feed_sales") and not default.view("feed_sales_fact_sales")
    assert default.view("revenue_search")


def test_tables_of_a_file_source_follow_their_context(config):
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE source_tables (source_id INTEGER, table_name TEXT, is_active INTEGER DEFAULT 1)"))
        conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN source_id INTEGER"))
        conn.execute(text("UPDATE schema_contexts SET source_id = 9 WHERE name = 'feed_sales'"))
        conn.execute(text("INSERT INTO source_tables (source_id, table_name) VALUES (9, 'feed_sales_dim_org')"))
    _move(config, "nt-report", "feed_sales")
    assert BrainFilter("nt-report", config).view("feed_sales_dim_org")
    assert not BrainFilter("default", config).view("feed_sales_dim_org")


def test_workspace_of_context_and_brain_path(config):
    _move(config, "nt-report", "feed_sales")
    assert workspace_of_context("feed_sales", config) == "nt-report"
    assert workspace_of_context("transfer_price", config) == "default"
    assert workspace_of_context("unknown", config) == "default"
    assert workspace_of_context("feed_sales", create_engine("sqlite://")) == "default"  # not migrated
    assert brain_path("./chroma_db", "default") == "./chroma_db" and brain_path("./chroma_db", None) == "./chroma_db"
    assert brain_path("./chroma_db/", "nt-report") == "./chroma_db__nt-report"
    with pytest.raises(ValueError):
        brain_path("./chroma_db", "../etc")

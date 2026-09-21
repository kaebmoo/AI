import json

import pytest
from sqlalchemy import create_engine, text

from app.services.schema_service import SchemaService
from tests.unit import knowledge_db


def _create_remaining_service(tmp_path):
    db_path = tmp_path / "schema_remaining.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, column_name TEXT, display_name_th TEXT, display_name_en TEXT, description TEXT, data_type TEXT, format_hint TEXT, example_value TEXT, is_summable INTEGER, is_groupable INTEGER, hierarchy_level INTEGER, special_notes TEXT, conversion_sql TEXT, dimension_group TEXT, updated_at TEXT)"))
        conn.execute(text("CREATE TABLE view_column_mappings (id INTEGER PRIMARY KEY AUTOINCREMENT, view_name TEXT, view_column TEXT, source_table TEXT, source_column TEXT, mapping_type TEXT)"))
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, display_name TEXT, description TEXT, main_view TEXT, is_active INTEGER, priority INTEGER, keywords TEXT, instruction_th TEXT, instruction_en TEXT, updated_at TEXT)"))
        conn.execute(text("CREATE TABLE source_data (SECTION TEXT, SECTION_ABBR TEXT, GL_CODE TEXT, GL_NAME TEXT, YEAR INTEGER, MONTH INTEGER, amount REAL)"))

        conn.execute(text("INSERT INTO source_data (SECTION, SECTION_ABBR, GL_CODE, GL_NAME, YEAR, MONTH, amount) VALUES ('Finance', 'FIN', '1001', 'Revenue', 2025, 1, 10.5)"))
        conn.execute(text("INSERT INTO source_data (SECTION, SECTION_ABBR, GL_CODE, GL_NAME, YEAR, MONTH, amount) VALUES ('Operations', 'OPS', '1002', 'Expense', 2025, 2, 20.0)"))

        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, display_name_th, data_type, is_summable, is_groupable, dimension_group) VALUES ('source_data', 'SECTION', 'ส่วนงาน', 'TEXT', 0, 1, 'org_section')"))
        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, display_name_th, data_type, is_summable, is_groupable, dimension_group) VALUES ('source_data', 'SECTION_ABBR', 'ชื่อย่อส่วนงาน', 'TEXT', 0, 1, 'org_section')"))
        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, display_name_th, data_type, is_summable, is_groupable, dimension_group) VALUES ('source_data', 'GL_CODE', 'รหัสบัญชี', 'TEXT', 0, 1, 'gl_account')"))

        conn.execute(text("INSERT INTO schema_contexts (name, display_name, description, main_view, is_active, priority, keywords, instruction_th, instruction_en) VALUES ('transfer price', 'Transfer Price', 'context', 'source_data', 1, 10, :keywords, 'thai', 'english')"), {"keywords": json.dumps(["tp", "transfer"], ensure_ascii=False)})
    knowledge_db.add_provenance(engine)  # Plan 8.1 columns
    return SchemaService(db_engine=engine, business_engine=engine)


def test_create_custom_view_propagates_metadata_and_rejects_invalid_source(tmp_path):
    service = _create_remaining_service(tmp_path)

    created = service.create_custom_view(
        view_name="finance_view",
        source_table="source_data",
        mapping=[
            {"col": "SECTION", "alias": "ORG_SECTION"},
            {"col": "SECTION_ABBR", "alias": "ORG_SECTION_ABBR"},
        ],
    )

    mappings = service.get_view_column_mappings("finance_view")
    metadata_rows = service.get_schema_metadata("finance_view")

    assert created is True
    assert len(mappings) == 2
    assert any(row["column_name"] == "ORG_SECTION" and row["display_name_th"] == "ส่วนงาน" for row in metadata_rows)

    with pytest.raises(ValueError, match="Invalid source table|Source table not found"):
        service.create_custom_view("bad_view", "source-data;drop", [{"col": "SECTION"}])


def test_list_views_with_mappings_reports_summary(tmp_path):
    service = _create_remaining_service(tmp_path)
    service.create_custom_view(
        view_name="summary_view",
        source_table="source_data",
        mapping=[{"col": "SECTION"}, {"col": "SECTION_ABBR"}],
    )

    views = service.list_views_with_mappings()

    assert any(view["view_name"] == "summary_view" and view["mapping_count"] == 2 for view in views)


def test_context_store_normalizes_names_and_refreshes_cache(tmp_path):
    service = _create_remaining_service(tmp_path)

    context = service.get_context_info("transfer_price")
    assert context["name"] == "transfer price"
    assert context["keywords"] == ["tp", "transfer"]

    created = service.create_context({
        "name": "revenue",
        "display_name": "Revenue",
        "description": "rev",
        "main_view": "source_data",
        "is_active": 1,
        "priority": 5,
        "keywords": ["rev"],
        "instruction_th": "thai",
        "instruction_en": "english",
    })
    assert created["name"] == "revenue"

    updated = service.update_context(created["id"], {"display_name": "Revenue Updated", "keywords": ["rev", "income"]})
    assert updated["display_name"] == "Revenue Updated"
    assert updated["keywords"] == ["rev", "income"]

    service.delete_context(created["id"])
    all_contexts = service.get_all_contexts()
    assert all(context_row["name"] != "revenue" for context_row in all_contexts)


def test_dimension_families_merge_db_and_auto_detection(tmp_path):
    service = _create_remaining_service(tmp_path)

    families = service.get_dimension_families("source_data")
    families_with_source = service.get_dimension_families_with_source("source_data")

    assert families["org_section"] == ["SECTION", "SECTION_ABBR"]
    assert families["time"] == ["MONTH", "YEAR"]
    assert any(item["family_name"] == "org_section" and item["source"] == "db" for item in families_with_source)
    assert any(item["family_name"] == "time" and item["source"] == "auto" for item in families_with_source)


def test_get_sample_values_rejects_malicious_table_name(tmp_path):
    service = _create_remaining_service(tmp_path)

    samples = service.get_sample_values("source_data; DROP TABLE schema_metadata;--")

    assert samples == {}
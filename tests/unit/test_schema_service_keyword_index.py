import json

from sqlalchemy import create_engine, text

from app.services.schema import SchemaService as PackageSchemaService
from app.services.schema_service import SchemaService


def _create_schema_keyword_db(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, column_name TEXT, is_groupable INTEGER)"))
        conn.execute(text("CREATE TABLE keyword_value_index (id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT, column_name TEXT, column_value TEXT, table_name TEXT, context_name TEXT)"))
        conn.execute(text("CREATE TABLE master_hierarchy_values (id INTEGER PRIMARY KEY AUTOINCREMENT, context_name TEXT, value TEXT, aliases TEXT, is_active INTEGER)"))
        conn.execute(text('CREATE TABLE revenue_search (PRODUCT_NAME TEXT, BUSINESS_GROUP TEXT, YEAR INTEGER, MONTH TEXT)'))

        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, is_groupable) VALUES ('revenue', 'PRODUCT_NAME', 1)"))
        conn.execute(text("INSERT INTO revenue_search (PRODUCT_NAME, BUSINESS_GROUP, YEAR, MONTH) VALUES ('Trunk Radio', 'Enterprise', 2025, '1')"))
        conn.execute(text("INSERT INTO revenue_search (PRODUCT_NAME, BUSINESS_GROUP, YEAR, MONTH) VALUES ('บริการ Cloud Connect', 'Digital', 2025, '2')"))
        conn.execute(
            text(
                "INSERT INTO master_hierarchy_values (context_name, value, aliases, is_active) VALUES ('revenue', 'กลุ่มบริการ Cloud', :aliases, 1)"
            ),
            {"aliases": json.dumps(["cloud", "คลาวด์"], ensure_ascii=False)},
        )
    return engine


def test_schema_service_import_surface_uses_package_impl(tmp_path):
    db_path = tmp_path / "schema_keyword_surface.sqlite"
    engine = _create_schema_keyword_db(db_path)
    legacy_service = SchemaService(db_engine=engine, business_engine=engine)
    package_service = PackageSchemaService(db_engine=engine, business_engine=engine)

    assert type(legacy_service) is PackageSchemaService
    assert type(package_service) is PackageSchemaService


def test_build_keyword_index_and_search_keyword_index(tmp_path):
    db_path = tmp_path / "schema_keyword.sqlite"
    engine = _create_schema_keyword_db(db_path)
    service = SchemaService(db_engine=engine, business_engine=engine)

    count = service.build_keyword_index(context_name="revenue", table_name="revenue_search")
    matches = service.search_keyword_index("trunk", context_name="revenue", limit=5)

    assert count > 0
    assert any(match["column_name"] == "PRODUCT_NAME" for match in matches)
    assert any(match["column_value"] == "Trunk Radio" for match in matches)


def test_get_searchable_columns_falls_back_to_table_inspection(tmp_path):
    db_path = tmp_path / "schema_keyword_fallback.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, column_name TEXT, is_groupable INTEGER)"))
        conn.execute(text("CREATE TABLE keyword_value_index (id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT, column_name TEXT, column_value TEXT, table_name TEXT, context_name TEXT)"))
        conn.execute(text("CREATE TABLE master_hierarchy_values (id INTEGER PRIMARY KEY AUTOINCREMENT, context_name TEXT, value TEXT, aliases TEXT, is_active INTEGER)"))
        conn.execute(text('CREATE TABLE revenue_search (PRODUCT_NAME TEXT, BUSINESS_GROUP TEXT, YEAR INTEGER, MONTH TEXT)'))

    service = SchemaService(db_engine=engine, business_engine=engine)
    columns = service.get_searchable_columns("revenue", "revenue_search")

    assert "PRODUCT_NAME" in columns
    assert "BUSINESS_GROUP" in columns
    assert "YEAR" not in columns


def test_refresh_cache_clears_known_terms_cache(tmp_path):
    db_path = tmp_path / "schema_keyword_cache.sqlite"
    engine = _create_schema_keyword_db(db_path)
    service = SchemaService(db_engine=engine, business_engine=engine)

    service.build_keyword_index(context_name="revenue", table_name="revenue_search")
    terms_before = service.get_known_terms("revenue")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM keyword_value_index"))
        conn.execute(text("DELETE FROM master_hierarchy_values"))

    cached_terms = service.get_known_terms("revenue")
    service.refresh_cache()
    terms_after = service.get_known_terms("revenue")

    assert "cloud" in [term.lower() for term in terms_before]
    assert "cloud" in [term.lower() for term in cached_terms]
    assert "cloud" not in [term.lower() for term in terms_after]


def test_build_keyword_index_rejects_malicious_table_name(tmp_path):
    db_path = tmp_path / "schema_keyword_injection.sqlite"
    engine = _create_schema_keyword_db(db_path)
    service = SchemaService(db_engine=engine, business_engine=engine)

    count = service.build_keyword_index(context_name="revenue", table_name="revenue_search; DROP TABLE schema_metadata;--")

    assert count == 0

    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT COUNT(*) FROM schema_metadata")).scalar_one()

    assert remaining == 1
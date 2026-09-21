import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

from app.services.schema import SchemaService as PackageSchemaService
from app.services.schema_service import SchemaService
from tests.unit import knowledge_db


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


def _split_dbs(tmp_path):
    """Config DB (metadata + index) and business DB (the view) as separate files, like production."""
    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    business = create_engine(f"sqlite:///{tmp_path / 'business.sqlite'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, column_name TEXT, is_groupable INTEGER)"))
        conn.execute(text("CREATE TABLE keyword_value_index (id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT, column_name TEXT, column_value TEXT, table_name TEXT, context_name TEXT)"))
        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, is_groupable) VALUES ('revenue', 'PRODUCT_NAME', 1)"))
        conn.execute(text("INSERT INTO keyword_value_index (keyword, column_name, column_value, table_name, context_name) VALUES ('old', 'PRODUCT_NAME', 'Old Product', 'revenue_search', 'revenue')"))
    with business.begin() as conn:
        conn.execute(text("CREATE TABLE revenue_search (PRODUCT_NAME TEXT, YEAR INTEGER)"))
        conn.execute(text("INSERT INTO revenue_search VALUES ('Trunk Radio', 2025), ('บริการ Cloud Connect', 2025)"))
    return config, business


def _index_values(config):
    with config.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT column_value FROM keyword_value_index"))}


def test_rebuild_scans_business_db_and_replaces_index(tmp_path):
    config, business = _split_dbs(tmp_path)
    service = SchemaService(db_engine=config, business_engine=business)

    count = service.build_keyword_index(context_name="revenue", table_name="revenue_search")

    assert count > 0
    assert _index_values(config) == {"Trunk Radio", "บริการ Cloud Connect"}
    assert any(m["column_value"] == "Trunk Radio" for m in service.search_keyword_index("trunk", context_name="revenue"))


def test_rebuild_does_not_index_numeric_columns(tmp_path):
    """REMAIN-10.2: a groupable numeric column (YEAR, gl_code, quantity) must not turn '2025'/'10'
    into known terms that match numbers in a question; text codes ('007') stay searchable."""
    config, business = _split_dbs(tmp_path)
    with config.begin() as conn:
        conn.execute(text("INSERT INTO schema_metadata (table_name, column_name, is_groupable) VALUES "
                          "('revenue', 'YEAR', 1), ('revenue', 'AMOUNT', 1), ('revenue', 'CODE', 1)"))
    with business.begin() as conn:
        conn.execute(text("DROP TABLE revenue_search"))
        conn.execute(text("CREATE TABLE revenue_search (PRODUCT_NAME TEXT, YEAR INTEGER, AMOUNT REAL, CODE TEXT)"))
        conn.execute(text("INSERT INTO revenue_search VALUES ('Trunk Radio', 2025, 10.5, '007')"))
    service = SchemaService(db_engine=config, business_engine=business)

    service.build_keyword_index(context_name="revenue", table_name="revenue_search")

    assert _index_values(config) == {"Trunk Radio", "007"}


def test_numbers_inside_a_value_are_not_keywords():
    from app.services.schema.keyword_index import extract_keywords

    assert set(extract_keywords("บริการ MY 5G 700 MHZ")) == {"บริการ MY 5G 700 MHZ", "MY 5G 700 MHZ", "บริการ", "MY", "5G", "MHZ"}
    assert set(extract_keywords("1.1 กลุ่มบริการท่อร้อยสาย")) == {"1.1 กลุ่มบริการท่อร้อยสาย", "กลุ่มบริการท่อร้อยสาย"}
    assert extract_keywords("51010001") == ["51010001"]  # a code is searchable as a whole


@pytest.mark.parametrize("failure", ["select_raises", "no_values"])
def test_failed_scan_keeps_existing_index(tmp_path, failure):
    config, business = _split_dbs(tmp_path)
    if failure == "no_values":
        with business.begin() as conn:
            conn.execute(text("DELETE FROM revenue_search"))
    else:
        @event.listens_for(business, "before_cursor_execute")
        def _locked(conn, cursor, statement, *args):
            if statement.startswith("SELECT DISTINCT"):
                raise OperationalError(statement, None, Exception("database is locked"))

    service = SchemaService(db_engine=config, business_engine=business)

    assert service.build_keyword_index(context_name="revenue", table_name="revenue_search") == 0
    assert _index_values(config) == {"Old Product"}


def test_search_db_for_keyword_reads_business_db(tmp_path):
    config, business = _split_dbs(tmp_path)
    service = SchemaService(db_engine=config, business_engine=business)

    matches = service.search_db_for_keyword("TRUNK", table_name="revenue_search", context_name="revenue")

    assert [(m["column_name"], m["column_value"]) for m in matches] == [("PRODUCT_NAME", "Trunk Radio")]


def test_rebuild_endpoint_scans_each_context_on_its_own_source(tmp_path, monkeypatch):
    import app.services.data_sources as data_sources
    from app.api.v1.admin.config import rebuild_keyword_index

    config, business = _split_dbs(tmp_path)
    # The injected service is bound to a DB without the view: only the resolver's engine has it
    service = SchemaService(db_engine=config, business_engine=config)
    monkeypatch.setattr(service, "get_all_contexts", lambda: [
        {"name": "revenue", "main_view": "revenue_search"},
        {"name": "broken", "main_view": "missing_view"},
    ])
    monkeypatch.setattr(data_sources, "source_resolver", SimpleNamespace(for_context=lambda name: SimpleNamespace(engine=business)))

    result = rebuild_keyword_index(_current_user=None, schema_service=service)

    assert result["failed_contexts"] == ["broken"]
    assert result["total_entries"] > 0
    assert _index_values(config) == {"Trunk Radio", "บริการ Cloud Connect"}


class TestSearchDbSingleProbe:
    """REMAIN-10: one scan finds the columns holding a match; results stay those of the
    per-column search (the pre-REMAIN-10 loop is the oracle), on SQLite and on DuckDB."""

    KEYWORDS = ["radio", "RADIO", "cloud", "2025", "%", "_", "'", "zzz", "บริการ", "enter"]

    @staticmethod
    def _oracle(engine, table, cols, keyword, limit):
        out = []
        with engine.connect() as conn:
            for col in cols:
                try:
                    rows = conn.execute(text(
                        f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" LIKE :kw '
                        f'OR UPPER("{col}") LIKE UPPER(:kw) LIMIT :lim'), {"kw": f"%{keyword}%", "lim": limit}).fetchall()
                except Exception:
                    continue
                out += [{"keyword": keyword, "column_name": col, "column_value": str(r[0]), "table_name": table}
                        for r in rows if r[0]]
        return out

    def _config(self, tmp_path, table, cols):
        config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
        with config.begin() as conn:
            conn.execute(text("CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, is_groupable INTEGER)"))
            for c in cols:
                conn.execute(text("INSERT INTO schema_metadata VALUES (:t, :c, 1)"), {"t": table, "c": c})
        knowledge_db.add_provenance(config)  # Plan 8.1 columns
        return config

    def test_sqlite_same_results_one_scan_without_match(self, tmp_path):
        biz = create_engine(f"sqlite:///{tmp_path / 'biz.db'}")
        with biz.begin() as conn:
            conn.execute(text("CREATE TABLE revenue_search (PRODUCT_NAME TEXT, BUSINESS_GROUP TEXT, YEAR INTEGER, NOTE TEXT)"))
            conn.execute(text("INSERT INTO revenue_search VALUES ('Trunk Radio', 'Enterprise', 2025, NULL), "
                              "('บริการ Cloud Connect', 'Digital', 2025, 'radio note'), (NULL, 'ENTERPRISE', 2024, 'it''s')"))
        cols = ["PRODUCT_NAME", "BUSINESS_GROUP", "YEAR", "NOTE", "product_name"]  # case twin kept, like before
        service = SchemaService(db_engine=self._config(tmp_path, "revenue_search", cols), business_engine=biz)
        for kw in self.KEYWORDS:
            assert service.search_db_for_keyword(kw, "revenue_search", "revenue", 5) == \
                self._oracle(biz, "revenue_search", ["PRODUCT_NAME", "BUSINESS_GROUP", "YEAR", "NOTE", "PRODUCT_NAME"], kw, 5), kw

        scans = []
        event.listen(biz, "before_cursor_execute",
                     lambda conn, cur, stmt, *a: scans.append(stmt) if stmt.startswith("SELECT") else None)
        service.search_db_for_keyword("zzz", "revenue_search", "revenue", 5)
        assert len(scans) == 1  # was one scan per column

    def test_duckdb_non_text_column_skipped_as_before(self, tmp_path):
        from app.services.database_adapter import DuckDBFileAdapter

        root = tmp_path / "latest"
        root.mkdir()
        (root / "f.csv").write_text("year_month,bu,note\n202601,1.Hard Infrastructure,cloud\n202602,2.International,\n")
        cols = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"}, {"name": "note", "type": "VARCHAR"}]
        adapter = DuckDBFileAdapter("k", str(root), [{"table_name": "v", "file_name": "f.csv", "columns": cols}],
                                    str(tmp_path / "cache"))
        names = [c["name"] for c in cols]
        service = SchemaService(db_engine=self._config(tmp_path, "v", names), business_engine=adapter.engine)
        for kw in self.KEYWORDS + ["2026", "hard", "INTER"]:
            got = service.search_db_for_keyword(kw, "v", "feed_x", 10)
            want = self._oracle(adapter.engine, "v", names, kw, 10)
            key = lambda r: (r["column_name"], r["column_value"])
            assert sorted(got, key=key) == sorted(want, key=key), kw  # DuckDB DISTINCT order varies
        assert not service.search_db_for_keyword("2026", "v", "feed_x", 10)  # BIGINT can't LIKE on DuckDB — skipped

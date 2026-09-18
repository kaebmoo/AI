"""
Plan 7 Phase 1: DuckDBFileAdapter — zero-import file source, read-only, root-sandboxed.

- DuckDB can't read outside the source root / outside the registered files
- write SQL (INSERT/CREATE/COPY/ATTACH) is rejected by the F4 validator, the query
  gate and the engine — each layer tested on its own
"""

import pytest

from app.services.database_adapter import DuckDBFileAdapter, execute_select

COLUMNS = [{"name": "year_month", "type": "BIGINT"}, {"name": "bu", "type": "VARCHAR"},
           {"name": "revenue", "type": "DOUBLE"}]
TABLES = [{"table_name": "feed_x_fact_bu_monthly", "file_name": "fact_bu_monthly.csv", "columns": COLUMNS}]
WRITE_SQL = [
    "INSERT INTO feed_x_fact_bu_monthly VALUES (1, 'x', 1.0)",
    "CREATE TABLE pwn AS SELECT 1 AS x",
    "COPY (SELECT 1) TO '{root}/pwn.csv'",
    "ATTACH '{root}/pwn.duckdb' AS pwn",
]


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "latest"
    root.mkdir()
    # leading zero in bu must survive: typed VARCHAR from the registry, not sniffed
    (root / "fact_bu_monthly.csv").write_text(
        "year_month,bu,revenue\n202607,01.A,100.5\n202608,01.A,200.25\n202608,02.B,50\n"
    )
    (root / "secret.csv").write_text("k\nnot-registered\n")  # under root but not in the allowlist
    (tmp_path / "outside.csv").write_text("k\nleak\n")
    return root


@pytest.fixture
def adapter(source_root, tmp_path):
    return DuckDBFileAdapter("t", str(source_root), TABLES, str(tmp_path / "cache"))


class TestViews:
    def test_views_typed_from_registry(self, adapter):
        rows = adapter.execute_query("SELECT bu, revenue FROM feed_x_fact_bu_monthly WHERE year_month = 202607")
        assert rows == [{"bu": "01.A", "revenue": 100.5}]  # leading zero kept (VARCHAR, not sniffed)
        assert adapter.test_connection()
        assert [c["type"] for c in adapter.get_schema_info("feed_x_fact_bu_monthly")] == ["BIGINT", "VARCHAR", "DOUBLE"]

    def test_like_keeps_sqlite_case_insensitivity(self, adapter):
        # SQLite LIKE ignores case; the LLM/value verifier rely on it ('%HARD INFRA%')
        q = "SELECT COUNT(*) AS n FROM feed_x_fact_bu_monthly WHERE bu {} '%01.a%'"
        assert adapter.execute_query(q.format("LIKE"))[0]["n"] == 2
        assert adapter.execute_query(q.format("NOT LIKE"))[0]["n"] == 1
        # a LIKE inside a string literal is data, not the operator
        assert adapter.execute_query("SELECT 'x LIKE y' AS w")[0]["w"] == "x LIKE y"

    def test_columns_bound_by_header_name_not_position(self, source_root, tmp_path):
        # a publish that reorders columns must not swap values (importer selected by name too)
        (source_root / "fact_bu_monthly.csv").write_text("revenue,bu,year_month\n10.5,202608,7\n")
        reordered = DuckDBFileAdapter("r", str(source_root), TABLES, str(tmp_path / "cache"))
        assert reordered.execute_query("SELECT * FROM feed_x_fact_bu_monthly") == [
            {"year_month": 7, "bu": "202608", "revenue": 10.5}]

    def test_division_by_zero_is_null_like_sqlite(self, adapter):
        row = adapter.execute_query("SELECT 1.0 / 0 AS a, 0.0 / 0 AS b, 2.5 AS c")[0]
        assert row == {"a": None, "b": None, "c": 2.5}  # inf/nan would be invalid JSON

    def test_zero_rows_keep_column_names(self, adapter):  # xlsx export header
        assert adapter.query("SELECT bu, revenue FROM feed_x_fact_bu_monthly WHERE year_month = 1") == ([], ["bu", "revenue"])

    def test_row_cap_and_truncated_flag(self, adapter):
        result = execute_select(adapter, "SELECT * FROM feed_x_fact_bu_monthly", limit=2)
        assert result["row_count"] == 2 and result["truncated"] is True


class TestEngineLock:
    """Engine layer, reached with a raw cursor — no query gate, no F4 validator."""

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM read_csv('{outside}')",
        "SELECT * FROM read_csv('{root}/secret.csv')",
        "SELECT * FROM read_text('/etc/passwd')",
        "SELECT * FROM glob('{root}/*')",
    ])
    def test_blocks_files_outside_allowlist(self, adapter, source_root, sql):
        sql = sql.format(root=source_root, outside=source_root.parent / "outside.csv")
        with pytest.raises(Exception, match="(?i)permission|disabled"):
            adapter.cursor().execute(sql)

    @pytest.mark.parametrize("sql", WRITE_SQL)
    def test_rejects_writes(self, adapter, source_root, sql):
        with pytest.raises(Exception):
            adapter.cursor().execute(sql.format(root=source_root))
        assert not (source_root / "pwn.csv").exists() and not (source_root / "pwn.duckdb").exists()

    def test_no_shared_spill_directory(self, adapter):
        # all processes open the same view DB file; a shared <db>.tmp spill dir corrupts
        cur = adapter.cursor()
        assert cur.execute("SELECT current_setting('temp_directory')").fetchone()[0] == ""
        assert cur.execute("SELECT current_setting('allowed_directories')").fetchone()[0] == []

    def test_config_cannot_be_unlocked(self, adapter):
        with pytest.raises(Exception, match="locked"):
            adapter.cursor().execute("SET enable_external_access = true")

    def test_temp_view_cannot_poison_later_queries(self, adapter):
        adapter.cursor().execute("CREATE TEMP VIEW feed_x_fact_bu_monthly AS SELECT 0 AS year_month")
        assert adapter.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_bu_monthly")[0]["n"] == 3

    def test_registry_path_escaping_root_rejected(self, source_root, tmp_path):
        bad = [{**TABLES[0], "file_name": "../outside.csv"}]
        with pytest.raises(ValueError, match="outside source root"):
            DuckDBFileAdapter("t2", str(source_root), bad, str(tmp_path / "cache"))


class TestQueryGate:
    """execute_query = the untrusted-SQL path: one SELECT over registered views, parsed by DuckDB."""

    @pytest.mark.parametrize("sql", [
        # lock_configuration does NOT cover these: file logging aborts the process,
        # in-memory logging exposes other users' SQL via duckdb_logs
        "SELECT * FROM enable_logging(storage='file', storage_path='/x')",
        "SELECT * FROM enable_logging('QueryLog')",
        "SELECT message FROM duckdb_logs",
        "SELECT * FROM duckdb_settings()",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM query('SELECT 1')",
        "SELECT * FROM read_csv('{root}/fact_bu_monthly.csv')",  # even the registered file, directly
        "SELECT * FROM feed_x_fact_bu_monthly WHERE bu IN (SELECT k FROM read_csv('{root}/secret.csv'))",
        "SELECT 1; SELECT 2",
        *WRITE_SQL,
    ])
    def test_rejected(self, adapter, source_root, sql):
        with pytest.raises(PermissionError):
            adapter.execute_query(sql.format(root=source_root))

    def test_rejected_query_leaves_source_usable(self, adapter):
        with pytest.raises(PermissionError):
            adapter.execute_query("SELECT * FROM enable_logging(storage='file', storage_path='/x')")
        assert adapter.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_bu_monthly")[0]["n"] == 3

    @pytest.mark.parametrize("sql", [
        "WITH t AS (SELECT bu, SUM(revenue) AS r FROM feed_x_fact_bu_monthly GROUP BY bu) "
        "SELECT a.bu, a.r FROM t a JOIN (SELECT bu FROM feed_x_fact_bu_monthly) b USING (bu)",
        "SELECT bu FROM FEED_X_FACT_BU_MONTHLY UNION SELECT bu FROM main.feed_x_fact_bu_monthly",
        "SELECT MAX(year_month) AS m FROM feed_x_fact_bu_monthly",
    ])
    def test_allowed(self, adapter, sql):
        assert adapter.execute_query(sql)


class TestValidator:
    @pytest.mark.parametrize("sql", WRITE_SQL)
    def test_rejects_writes(self, adapter, source_root, sql):
        result = execute_select(adapter, sql.format(root=source_root))
        assert result["success"] is False and result["issues"]

    def test_rejects_file_functions(self, adapter, source_root):
        result = execute_select(adapter, f"SELECT * FROM read_csv('{source_root}/secret.csv')")
        assert result["success"] is False and "SQL validation failed" in result["error"]

    def test_file_access_rule_is_file_source_only(self):
        from app.services.validation_service import ValidationService
        sql = "SELECT PRODUCT_NAME FROM revenue_search WHERE glob('*CLOUD*', PRODUCT_NAME)"  # SQLite glob()
        assert ValidationService().validate_sql(sql)["valid"] is True  # legacy unchanged
        assert ValidationService().validate_sql(sql, file_source=True)["valid"] is False

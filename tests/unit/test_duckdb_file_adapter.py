"""
Plan 7 Phase 1: DuckDBFileAdapter — zero-import file source, read-only, root-sandboxed.

- DuckDB can't read outside the source root / outside the registered files
- write SQL (INSERT/CREATE/COPY/ATTACH) is rejected by the F4 validator AND the engine
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

    def test_row_cap_and_truncated_flag(self, adapter):
        result = execute_select(adapter, "SELECT * FROM feed_x_fact_bu_monthly", limit=2)
        assert result["row_count"] == 2 and result["truncated"] is True


class TestRootSandbox:
    @pytest.mark.parametrize("sql", [
        "SELECT * FROM read_csv('{outside}')",
        "SELECT * FROM read_csv('{root}/secret.csv')",
        "SELECT * FROM read_text('/etc/passwd')",
        "SELECT * FROM glob('{root}/*')",
    ])
    def test_engine_blocks_files_outside_allowlist(self, adapter, source_root, sql):
        sql = sql.format(root=source_root, outside=source_root.parent / "outside.csv")
        with pytest.raises(Exception, match="(?i)permission|disabled"):
            adapter.execute_query(sql)  # bypasses the validator on purpose

    def test_validator_also_rejects_file_functions(self, adapter, source_root):
        result = execute_select(adapter, f"SELECT * FROM read_csv('{source_root}/secret.csv')")
        assert result["success"] is False and "SQL validation failed" in result["error"]

    def test_file_access_rule_is_file_source_only(self):
        from app.services.validation_service import ValidationService
        sql = "SELECT PRODUCT_NAME FROM revenue_search WHERE glob('*CLOUD*', PRODUCT_NAME)"  # SQLite glob()
        assert ValidationService().validate_sql(sql)["valid"] is True  # legacy unchanged
        assert ValidationService().validate_sql(sql, file_source=True)["valid"] is False

    def test_registry_path_escaping_root_rejected(self, source_root, tmp_path):
        bad = [{**TABLES[0], "file_name": "../outside.csv"}]
        with pytest.raises(ValueError, match="outside source root"):
            DuckDBFileAdapter("t2", str(source_root), bad, str(tmp_path / "cache"))

    def test_config_cannot_be_unlocked(self, adapter):
        with pytest.raises(Exception, match="locked"):
            adapter.execute_query("SET enable_external_access = true")


class TestWriteRejected:
    @pytest.mark.parametrize("sql", WRITE_SQL)
    def test_validator_rejects(self, adapter, source_root, sql):
        result = execute_select(adapter, sql.format(root=source_root))
        assert result["success"] is False and result["issues"]

    @pytest.mark.parametrize("sql", WRITE_SQL)
    def test_engine_rejects_even_without_validator(self, adapter, source_root, sql):
        with pytest.raises(Exception):
            adapter.execute_query(sql.format(root=source_root))
        assert not (source_root / "pwn.csv").exists() and not (source_root / "pwn.duckdb").exists()

    def test_temp_view_cannot_poison_later_queries(self, adapter):
        adapter.execute_query("CREATE TEMP VIEW feed_x_fact_bu_monthly AS SELECT 0 AS year_month")
        assert adapter.execute_query("SELECT COUNT(*) AS n FROM feed_x_fact_bu_monthly")[0]["n"] == 3

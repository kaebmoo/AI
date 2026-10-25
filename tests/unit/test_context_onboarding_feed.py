"""Onboarding profiles registered Parquet sources instead of their stale SQLite copies."""

import json
import sqlite3
from types import SimpleNamespace

import duckdb
import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.services import data_sources
from app.services.context_onboarding import ContextOnboardingService, DataInspector
from app.services.database_adapter import DuckDBFileAdapter, SourceUnavailable
from tests.unit import knowledge_db

TABLE = 'feed_ebt_fact_ebt'
COLUMNS = [
    {'name': 'time_key', 'type': 'BIGINT'},
    {'name': 'division', 'type': 'VARCHAR'},
    {'name': 'unit', 'type': 'VARCHAR'},
    {'name': 'unit_short_name', 'type': 'VARCHAR'},
    {'name': 'amount', 'type': 'DOUBLE'},
    {'name': 'amount_ytd', 'type': 'DOUBLE'},
]
SENTINEL = 'ZQX_FEED_DIVISION'


@pytest.fixture(params=['parquet', 'csv'])
def feed_source(tmp_path, monkeypatch, request):
    root = tmp_path / 'latest'
    root.mkdir()
    data_path = root / f'fact_ebt.{request.param}'
    rows = [
        (202601 + i % 3, SENTINEL if i % 2 else 'division B',
         None if i % 5 == 0 else f'ฝ่าย {i % 3}', '' if i % 4 == 0 else f'U{i % 3}',
         None if i % 5 == 0 else (i % 4 - 1) * 10.5, (i % 4) * 100.5)
        for i in range(16)
    ]
    if request.param == 'csv':
        # The production CSV reader treats empty strings as NULL.
        rows = [tuple(None if value == '' else value for value in row) for row in rows]
    ddl = ', '.join(f'"{c["name"]}" {c["type"]}' for c in COLUMNS)
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE fact ({ddl})')
        conn.executemany('INSERT INTO fact VALUES (?, ?, ?, ?, ?, ?)', rows)
        conn.execute(f'COPY fact TO ? (FORMAT {request.param.upper()})', [str(data_path)])

    class ParquetAdapter(DuckDBFileAdapter):
        """Prepare Parquet views; the production adapter currently builds CSV views only."""

        def _build_view_db(self, views, cache_dir):
            self.db_path = str(tmp_path / f'{self.name}.duckdb')
            with duckdb.connect(self.db_path) as conn:
                for table, path, _columns in views:
                    escaped_path = path.replace("'", "''")
                    conn.execute(f'CREATE VIEW "{table}" AS SELECT * FROM read_parquet(\'{escaped_path}\')')
            return self.db_path

    if request.param == 'parquet':
        monkeypatch.setattr(data_sources, 'DuckDBFileAdapter', ParquetAdapter)

    legacy_path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(legacy_path) as conn:
        conn.execute(f'CREATE TABLE "{TABLE}" ({ddl})')
        conn.executemany(f'INSERT INTO "{TABLE}" VALUES (?, ?, ?, ?, ?, ?)', rows)
        conn.execute(f'CREATE TABLE "{TABLE}_reference" AS SELECT * FROM "{TABLE}"')
        conn.execute(f'DELETE FROM "{TABLE}"')
        conn.execute(f'INSERT INTO "{TABLE}" (division) VALUES (\'STALE_COPY\')')

    config_path = tmp_path / 'config.sqlite'
    config = knowledge_db.make(config_path)
    with config.begin() as conn:
        sid = conn.execute(text(
            "INSERT INTO data_sources (name, source_type, root_path, llm_data_policy) "
            "VALUES ('ebt_source', 'duckdb_file', :root, 'full') RETURNING id"
        ), {'root': str(root)}).scalar_one()
        conn.execute(text(
            'INSERT INTO source_tables (source_id, table_name, file_name, columns) VALUES (:sid, :t, :f, :c)'
        ), {'sid': sid, 't': TABLE, 'f': data_path.name, 'c': json.dumps(COLUMNS)})
        conn.execute(text(
            "INSERT INTO schema_contexts (name, main_view, source_id) VALUES ('feed_ebt', :t, :sid)"
        ), {'t': TABLE, 'sid': sid})
        # Missing, NULL, empty, and whitespace descriptions all count as empty.
        conn.execute(text(
            'INSERT INTO schema_metadata (table_name, column_name, description) VALUES (:t, :c, :d)'
        ), [{'t': TABLE, 'c': c, 'd': d} for c, d in [
            ('time_key', 'Period'), ('division', None), ('unit', ''),
            ('unit_short_name', ' \t\n '), ('amount', 'Monthly amount'),
            ('not_registered', 'Must not change the denominator'),
        ]])
    resolver = data_sources.SourceResolver(config_engine=config, cache_dir=str(tmp_path / 'cache'))
    monkeypatch.setattr('app.db.session.config_engine', config)
    monkeypatch.setattr(data_sources, 'source_resolver', resolver)
    monkeypatch.setattr(settings, 'CONFIG_DB_URL', f'sqlite:///{config_path}')
    service = ContextOnboardingService(str(legacy_path), config_db_path=str(config_path))
    yield SimpleNamespace(service=service, config=config, resolver=resolver, data_path=data_path,
                          legacy_path=legacy_path, row_count=len(rows))
    resolver._adapters.clear()
    config.dispose()


def test_feed_profiles_match_legacy_rows(feed_source):
    feed = feed_source.service.inspect(TABLE)
    legacy = DataInspector(str(feed_source.legacy_path)).inspect(f'{TABLE}_reference')
    assert feed.row_count == legacy.row_count == feed_source.row_count
    assert [c.name for c in feed.columns] == [c['name'] for c in COLUMNS]
    for actual, expected in zip(feed.columns, legacy.columns):
        for field in ('distinct_count', 'null_count', 'is_numeric', 'is_time_column',
                      'min_val', 'max_val', 'all_distinct', 'has_empty_values'):
            assert getattr(actual, field) == getattr(expected, field), (actual.name, field)
        assert set(actual.sample_values) == set(expected.sample_values), actual.name
    assert [c.name for c in feed.columns if c.is_numeric] == ['time_key', 'amount', 'amount_ytd']
    assert SENTINEL in json.dumps(feed.to_dict())
    # Nonregistered tables continue to use the legacy inspector.
    assert feed_source.service.inspect(f'{TABLE}_reference').row_count == feed_source.row_count


def test_feed_policy_withholds_values_but_still_profiles(feed_source):
    with feed_source.config.begin() as conn:
        conn.execute(text("UPDATE data_sources SET llm_data_policy = 'aggregated_only' WHERE name = 'ebt_source'"))
    result = feed_source.service.inspect(TABLE)
    assert result.row_count == feed_source.row_count
    assert SENTINEL in result.columns[1].all_distinct
    payload = result.to_dict()
    assert result.values_allowed is False
    assert SENTINEL not in json.dumps(payload)
    assert 'values_withheld' in payload
    for column in payload['columns']:
        assert 'sample_values' not in column
        assert 'all_distinct' not in column
        assert 'min' not in column
        assert 'max' not in column


def test_available_views_prefers_feed_and_counts_missing_descriptions(feed_source):
    result = feed_source.service.list_available_views()
    items = result['configured'] + result['unconfigured']
    feed = [item for item in items if item['name'] == TABLE]
    assert feed == [{
        'name': TABLE, 'type': 'view', 'has_config': True, 'row_count': feed_source.row_count,
        'source': 'file', 'context': 'feed_ebt', 'columns_total': 6,
        'description_empty': 4, 'description_empty_pct': 66.7,
    }]
    assert feed[0] in result['configured']
    legacy = next(item for item in result['unconfigured'] if item['name'] == f'{TABLE}_reference')
    assert legacy['source'] == 'legacy'
    assert legacy['row_count'] == feed_source.row_count
    assert legacy['has_config'] is False


def test_unavailable_feed_does_not_inspect_stale_copy(feed_source):
    feed_source.data_path.unlink()
    with pytest.raises(SourceUnavailable):
        feed_source.service.inspect(TABLE)
    result = feed_source.service.list_available_views()
    feed = next(item for item in result['configured'] if item['name'] == TABLE)
    assert feed['row_count'] is None
    assert feed['description_empty_pct'] == 66.7


def test_engine_numeric_types_and_time_columns():
    engine = create_engine('duckdb:///:memory:')
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                'CREATE TABLE numeric_types (a BIGINT, b INTEGER, c DOUBLE, d DECIMAL(18,2), '
                'e HUGEINT, f FLOAT, g UBIGINT, report_month INTEGER)'
            )
            conn.exec_driver_sql('INSERT INTO numeric_types VALUES (1, 2, 3.5, 4.25, 5, 6.5, 7, 202601)')
        result = DataInspector(engine).inspect('numeric_types')
        assert all(c.is_numeric for c in result.columns)
        assert all(c.distinct_count == 1 and c.all_distinct for c in result.columns)
        assert all(c.min_val is not None and c.max_val == c.min_val for c in result.columns)
        assert result.columns[-1].is_time_column is True
        assert result.date_range == {'report_month': {'min': 202601, 'max': 202601}}
    finally:
        engine.dispose()


def test_engine_typed_columns_do_not_abort_profiling():
    engine = create_engine('duckdb:///:memory:')
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE typed_columns (report_date DATE, enabled BOOLEAN, amount DOUBLE)')
            conn.exec_driver_sql(
                "INSERT INTO typed_columns SELECT DATE '2026-01-01', i % 2 = 0, i FROM range(24) AS t(i)"
            )
        result = DataInspector(engine).inspect('typed_columns')
        assert [c.distinct_count for c in result.columns] == [1, 2, 24]
        assert all(c.sample_values and c.all_distinct for c in result.columns)
        assert result.columns[-1].min_val == 0
        assert len(result.cross_analyses) == 1
        assert result.cross_analyses[0].category_column == 'enabled'
        assert sum(c['count'] for c in result.cross_analyses[0].categories.values()) == 24
    finally:
        engine.dispose()

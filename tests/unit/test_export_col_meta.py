"""Accepted descriptions export without resolving a source or changing config."""

import ast
import json
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.services.datafeed_knowledge import sync_schema_metadata
from scripts.export_col_meta import main, read_only_engine
from tests.unit import knowledge_db


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.fixture"
    engine = knowledge_db.make(path)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO data_sources (id, name, source_type, is_active) VALUES "
            "(1, 'datafeed_ebt', 'duckdb_file', 1), (2, 'other', 'duckdb_file', 1), "
            "(3, 'legacy', 'legacy', 1), (4, 'inactive', 'duckdb_file', 0)"))
        conn.execute(text(
            "INSERT INTO schema_contexts (name, source_id) VALUES "
            "('feed_ebt', 1), ('other', 2), ('legacy', 3), ('inactive', 4), ('empty', NULL)"))
        for source, table, active in [
            (1, 'feed_ebt_fact_a', 1), (1, 'feed_ebt_fact_b', 1),
            (1, 'feed_ebt_retired', 0), (2, 'feed_other_fact', 1),
            (3, 'legacy_table', 1), (4, 'inactive_table', 1),
        ]:
            conn.execute(text(
                "INSERT INTO source_tables (source_id, table_name, file_name, columns, is_active) "
                "VALUES (:source, :table, 'unused.parquet', '{}', :active)"
            ), {"source": source, "table": table, "active": active})
        for table, column, description, display, source, status in [
            ('feed_ebt_fact_a', 'amount', 'ยอดรายเดือน (หน่วย: บาท (THB))', None, 'manual', 'active'),
            ('feed_ebt_fact_a', 'division', 'ระดับ 1', 'สายงาน', 'manual', 'active'),
            ('feed_ebt_fact_b', 'unit', 'ฝ่าย — ระดับ 3', 'ฝ่าย', 'manual', 'active'),
            ('feed_ebt_fact_a', 'shared', 'งวด ค.ศ. YYYYMM', None, 'manual', 'active'),
            ('feed_ebt_fact_b', 'shared', 'งวด ค.ศ. YYYYMM', None, 'manual', 'active'),
            ('feed_ebt_fact_b', 'quoted', 'คำว่า \'ฝ่าย\' และ "ส่วน" \\ ตัวอย่าง\nบรรทัดถัดไป', None, 'manual', 'active'),
            ('feed_ebt_fact_a', 'blank', ' \n ', 'ชื่อว่าง', 'manual', 'active'),
            ('feed_ebt_fact_a', 'null_desc', None, None, 'manual', 'active'),
            ('feed_ebt_fact_a', 'declared', 'จาก contract', None, 'declared', 'active'),
            ('feed_ebt_fact_a', 'inferred', 'เครื่องร่าง', None, 'inferred', 'active'),
            ('feed_ebt_fact_a', 'learned', 'จากการใช้', None, 'learned', 'active'),
            ('feed_ebt_fact_a', 'proposed', 'รอรับ', None, 'manual', 'proposed'),
            ('feed_ebt_fact_a', 'rejected', 'ไม่รับ', None, 'manual', 'rejected'),
            ('feed_other_fact', 'other', 'อีก context', None, 'manual', 'active'),
            ('feed_ebt_retired', 'retired', 'เลิกใช้', None, 'manual', 'active'),
            ('unregistered', 'unregistered', 'ไม่ได้ลงทะเบียน', None, 'manual', 'active'),
        ]:
            conn.execute(text(
                "INSERT INTO schema_metadata (table_name, column_name, description, display_name_th, "
                "source, status, data_type, is_summable, is_groupable) "
                "VALUES (:table, :column, :description, :display, :source, :status, 'string', 0, 1)"
            ), dict(table=table, column=column, description=description, display=display, source=source, status=status))
    yield path, engine
    engine.dispose()


def snippet(stdout):
    header, literal = stdout.split('\n', 1)
    assert header == "# 'feed_ebt': col_meta for tools/feed/domains.py"
    return ast.literal_eval(literal)


def test_exact_snippet_and_read_only_module_cli(config):
    path, _ = config
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.export_col_meta', '--context', 'feed_ebt', '--config-db', str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ''
    assert result.stdout == (
        "# 'feed_ebt': col_meta for tools/feed/domains.py\n"
        "{\n"
        "    'amount': {'desc': 'ยอดรายเดือน'},\n"
        "    'division': {'desc': 'สายงาน — ระดับ 1'},\n"
        "    'quoted': {'desc': 'คำว่า \\'ฝ่าย\\' และ \"ส่วน\" \\\\ ตัวอย่าง\\nบรรทัดถัดไป'},\n"
        "    'shared': {'desc': 'งวด ค.ศ. YYYYMM'},\n"
        "    'unit': {'desc': 'ฝ่าย — ระดับ 3'},\n"
        "}\n"
    )
    assert snippet(result.stdout) == {
        'amount': {'desc': 'ยอดรายเดือน'},
        'division': {'desc': 'สายงาน — ระดับ 1'},
        'quoted': {'desc': 'คำว่า \'ฝ่าย\' และ "ส่วน" \\ ตัวอย่าง\nบรรทัดถัดไป'},
        'shared': {'desc': 'งวด ค.ศ. YYYYMM'},
        'unit': {'desc': 'ฝ่าย — ระดับ 3'},
    }
    assert path.read_bytes() == before


@pytest.mark.parametrize('only_conflicts', [False, True])
def test_conflict_excluded_and_reported(config, capsys, only_conflicts):
    path, engine = config
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE schema_metadata SET description = 'งวดอื่น' "
            "WHERE table_name = 'feed_ebt_fact_b' AND column_name = 'shared'"))
        if only_conflicts:
            conn.execute(text("DELETE FROM schema_metadata WHERE column_name != 'shared'"))
    assert main(['--context', 'feed_ebt', '--config-db', str(path)]) == int(only_conflicts)
    output = capsys.readouterr()
    exported = snippet(output.out)
    assert 'shared' not in exported
    assert bool(exported) is not only_conflicts
    assert "Conflict for column 'shared':" in output.err
    assert "feed_ebt_fact_a: 'งวด ค.ศ. YYYYMM'" in output.err
    assert "feed_ebt_fact_b: 'งวดอื่น'" in output.err
    if only_conflicts:
        assert 'No descriptions emitted' in output.err


@pytest.mark.parametrize('context, message', [
    ('unknown', 'Unknown context'), ('empty', 'No registered file-source tables'),
    ('legacy', 'No registered file-source tables'), ('inactive', 'No registered file-source tables'),
])
def test_invalid_context(config, capsys, context, message):
    path, _ = config
    assert main(['--context', context, '--config-db', str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert message in output.err


def test_empty_result(config, capsys):
    path, engine = config
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM schema_metadata"))
    assert main(['--context', 'feed_ebt', '--config-db', str(path)]) == 0
    output = capsys.readouterr()
    assert snippet(output.out) == {}
    assert 'No descriptions emitted' in output.err


def test_default_config_url_and_database_enforced_read_only(config, monkeypatch):
    from app.config import settings

    path, _ = config
    monkeypatch.setattr(settings, 'CONFIG_DB_URL', f'sqlite:///{path}')
    engine = read_only_engine()
    try:
        with engine.connect() as conn:
            assert conn.execute(text('SELECT COUNT(*) FROM schema_contexts')).scalar_one() == 5
            with pytest.raises(OperationalError, match='readonly'):
                conn.execute(text('DELETE FROM schema_metadata'))
    finally:
        engine.dispose()


def test_missing_database_is_not_created(tmp_path, capsys):
    path = tmp_path / 'missing.fixture'
    assert main(['--context', 'feed_ebt', '--config-db', str(path)]) == 2
    assert not path.exists()
    assert capsys.readouterr().out == ''


def test_round_trip_preserves_manual_rows_without_proposals(config, capsys):
    path, engine = config
    assert main(['--context', 'feed_ebt', '--config-db', str(path)]) == 0
    exported = snippet(capsys.readouterr().out)
    with engine.connect() as conn:
        before = [dict(row) for row in conn.execute(text(
            "SELECT * FROM schema_metadata WHERE source = 'manual' AND status = 'active' "
            "AND table_name IN ('feed_ebt_fact_a', 'feed_ebt_fact_b') ORDER BY id"
        )).mappings()]
    contract = {'domain': 'ebt', 'schema_version': '1.0.1', 'datasets': []}
    for dataset in ('fact_a', 'fact_b'):
        columns = []
        for row in before:
            if row['table_name'] != f'feed_ebt_{dataset}' or row['column_name'] not in exported:
                continue
            column = {'name': row['column_name'], 'dtype': row['data_type'],
                      'description': exported[row['column_name']]['desc']}
            if column['name'] == 'amount':
                column['unit'] = 'บาท (THB)'
            columns.append(column)
        contract['datasets'].append({'name': dataset, 'columns': columns})
    with engine.begin() as conn:
        sync_schema_metadata(conn, 'ebt', contract)
    with engine.connect() as conn:
        after = [dict(row) for row in conn.execute(text(
            "SELECT * FROM schema_metadata WHERE source = 'manual' AND status = 'active' "
            "AND table_name IN ('feed_ebt_fact_a', 'feed_ebt_fact_b') ORDER BY id"
        )).mappings()]
        proposals = conn.execute(text('SELECT row_key, source FROM knowledge_proposals')).all()
    assert after == before
    # Only the added display-name prefix differs; an already present prefix stays equal.
    assert [(json.loads(key)['column_name'], source) for key, source in proposals] == [('division', 'declared')]

"""A config DB shaped like the live one for the knowledge tables — the same keys, NOT NULLs, defaults and the
vanna_documentation trigger — migrated by scripts/migrate_knowledge_provenance.py (Plan 8.1 writer-rule tests)."""

import sqlite3

from sqlalchemy import create_engine

from scripts.migrate_knowledge_provenance import migrate

DDL = """
CREATE TABLE data_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
    root_path TEXT, description TEXT, is_active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, manifest_file TEXT, contract_file TEXT, knowledge_sha TEXT,
    llm_data_policy TEXT DEFAULT 'full', llm_provider_allowlist TEXT);
CREATE TABLE source_tables (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL, table_name TEXT NOT NULL,
    file_name TEXT NOT NULL, columns TEXT NOT NULL, sha256 TEXT, is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE (source_id, table_name));
CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, display_name TEXT,
    description TEXT, main_view TEXT, is_active BOOLEAN DEFAULT 1, priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, keywords TEXT, instruction_th TEXT, instruction_en TEXT,
    updated_at TIMESTAMP, source_id INTEGER, scope_columns TEXT, workspace_id INTEGER);
CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL, column_name TEXT NOT NULL,
    display_name_th TEXT, display_name_en TEXT, description TEXT, data_type TEXT, format_hint TEXT, example_value TEXT,
    is_summable BOOLEAN DEFAULT 0, is_groupable BOOLEAN DEFAULT 1, hierarchy_level INTEGER, sample_values TEXT,
    special_notes TEXT, conversion_sql TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, dimension_group TEXT DEFAULT NULL, UNIQUE(table_name, column_name));
CREATE TABLE schema_business_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL, rule_description TEXT NOT NULL, table_name TEXT, applies_to TEXT, example_correct TEXT,
    example_wrong TEXT, severity TEXT DEFAULT 'warning', is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    rule_category TEXT DEFAULT 'sql_generation', inject_mode TEXT DEFAULT 'schema_context', pattern TEXT,
    check_type TEXT DEFAULT 'regex_warning');
CREATE TABLE golden_examples (id INTEGER NOT NULL PRIMARY KEY, chat_id INTEGER, question_pattern TEXT NOT NULL,
    expected_sql TEXT NOT NULL, category VARCHAR, is_active BOOLEAN, added_by INTEGER, usage_count INTEGER,
    created_at DATETIME);
CREATE TABLE schema_semantic_mapping (id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT NOT NULL UNIQUE,
    keyword_type TEXT DEFAULT 'term', target_column TEXT NOT NULL, target_condition TEXT NOT NULL, full_condition TEXT,
    description TEXT, priority INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    context_name TEXT DEFAULT NULL);
CREATE TABLE master_hierarchy (id INTEGER PRIMARY KEY AUTOINCREMENT, context_name TEXT NOT NULL, level INTEGER NOT NULL,
    level_label_th TEXT NOT NULL, level_label_en TEXT NOT NULL, level_columns TEXT NOT NULL,
    detection_keywords TEXT NOT NULL, is_active BOOLEAN DEFAULT 1, source TEXT DEFAULT 'auto',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, parent_column TEXT,
    source_view TEXT, UNIQUE(context_name, level));
CREATE TABLE master_hierarchy_values (id INTEGER PRIMARY KEY AUTOINCREMENT, context_name TEXT NOT NULL,
    level INTEGER NOT NULL, value TEXT NOT NULL, parent_value TEXT, aliases TEXT, source TEXT DEFAULT 'auto',
    is_active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(context_name, level, value));
CREATE TABLE data_warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, keywords TEXT NOT NULL,
    exclude_keywords TEXT, columns_to_check TEXT NOT NULL, message TEXT NOT NULL, severity TEXT DEFAULT 'warning',
    context_name TEXT, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE vanna_documentation (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    content TEXT NOT NULL, category TEXT DEFAULT 'guide', context_name TEXT, is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TRIGGER update_vanna_doc_timestamp AFTER UPDATE ON vanna_documentation FOR EACH ROW
BEGIN UPDATE vanna_documentation SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;
"""


def make(path, seed: str = ""):
    """Create the tables, run `seed` (SQL), migrate — rows seeded here are labelled like the live rows were."""
    conn = sqlite3.connect(path)
    conn.executescript(DDL + seed)
    conn.close()
    engine = create_engine(f"sqlite:///{path}")
    migrate(engine)
    return engine


def rows(path, sql: str, params=()) -> list:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def add_provenance(target) -> None:
    """Give the knowledge tables a fixture created with its own DDL the Plan 8.1 columns — the ORM models select
    them and the readers filter on status. `target`: a path to a SQLite file or a SQLAlchemy engine."""
    from scripts.migrate_knowledge_provenance import COLUMNS, TABLES

    engine = target if hasattr(target, "begin") else create_engine(f"sqlite:///{target}")
    with engine.begin() as conn:
        for table in TABLES:
            present = {r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}
            for column, ddl in COLUMNS:
                if present and column not in present:
                    conn.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN {column} {ddl}')

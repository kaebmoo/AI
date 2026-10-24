"""Export accepted column descriptions for NT-Report's domain-wide col_meta."""

import argparse
from pathlib import Path
import re
import sys

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


def read_only_engine(config_db=None):
    if config_db is None:
        from app.config import settings

        url = make_url(settings.CONFIG_DB_URL)
        if url.get_backend_name() != "sqlite" or not url.database:
            raise ValueError("CONFIG_DB_URL must name a SQLite config DB")
        config_db = url.database
    # mode=ro also refuses a missing file, rather than creating an empty config DB.
    return create_engine(URL.create(
        "sqlite", database=Path(config_db).resolve().as_uri(),
        query={"mode": "ro", "uri": "true"},
    ))


def export_col_meta(conn, context):
    if conn.execute(text("SELECT 1 FROM schema_contexts WHERE name = :context"),
                    {"context": context}).first() is None:
        raise ValueError(f"Unknown context: {context}")
    tables = conn.execute(text(
        "SELECT st.table_name FROM source_tables st "
        "JOIN data_sources ds ON ds.id = st.source_id "
        "JOIN schema_contexts sc ON sc.source_id = ds.id "
        "WHERE sc.name = :context AND st.is_active = 1 "
        "AND ds.is_active = 1 AND ds.source_type = 'duckdb_file'"
    ), {"context": context}).scalars().all()
    if not tables:
        raise ValueError(f"No registered file-source tables for context: {context}")

    columns = {}
    for table in sorted(set(tables)):
        rows = conn.execute(text(
            "SELECT column_name, description, display_name_th FROM schema_metadata "
            "WHERE table_name = :table AND source = 'manual' AND status = 'active' "
            "ORDER BY column_name"
        ), {"table": table}).mappings()
        for row in rows:
            description = (row["description"] or "").strip()
            description = re.sub(r" \(หน่วย: .*\)$", "", description).strip()
            if not description:
                continue
            display = row["display_name_th"]
            if display and not description.startswith(display):
                description = f"{display} — {description}"
            columns.setdefault(row["column_name"], []).append((table, description))

    result, conflicts = {}, False
    for column, entries in sorted(columns.items()):
        if len({description for _, description in entries}) > 1:
            conflicts = True
            print(f"Conflict for column {column!r}:", file=sys.stderr)
            for table, description in entries:
                print(f"  {table}: {description!r}", file=sys.stderr)
        else:
            result[column] = {"desc": entries[0][1]}
    print(f"# {context!r}: col_meta for tools/feed/domains.py")
    if result:
        print("{")
        for column, metadata in result.items():
            print(f"    {column!r}: {metadata!r},")
        print("}")
    else:
        print("{}")
        print(f"No descriptions emitted for context: {context}", file=sys.stderr)
    return 1 if conflicts and not result else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--config-db", metavar="PATH", help="Config DB path (default: settings.CONFIG_DB_URL)")
    args = parser.parse_args(argv)
    engine = None
    try:
        engine = read_only_engine(args.config_db)
        with engine.connect() as conn:
            return export_col_meta(conn, args.context)
    except (ValueError, OSError, SQLAlchemyError) as exc:
        print(f"export_col_meta: {exc}", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

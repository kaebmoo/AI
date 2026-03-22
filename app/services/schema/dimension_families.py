from typing import TYPE_CHECKING, Dict, List

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.services.dimension_detector import detect_families

if TYPE_CHECKING:
    from app.services.schema.service import SchemaService


def get_dimension_families(service: "SchemaService", table_name: str) -> Dict[str, List[str]]:
    db_families: Dict[str, List[str]] = {}
    db_assigned_columns = set()
    with service.engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT dimension_group, column_name
                FROM schema_metadata
                WHERE table_name = :table_name
                  AND dimension_group IS NOT NULL
                ORDER BY dimension_group, column_name
            """), {"table_name": table_name})
            for row in result.mappings().fetchall():
                group = row["dimension_group"]
                column_name = row["column_name"]
                db_families.setdefault(group, []).append(column_name)
                db_assigned_columns.add(column_name)
        except SQLAlchemyError:
            pass

    try:
        columns = service.get_table_info(table_name)
        all_column_names = [column["name"] for column in columns]
    except (SQLAlchemyError, KeyError, TypeError, ValueError):
        all_column_names = []

    auto_families = detect_families(all_column_names) if all_column_names else {}

    merged: Dict[str, List[str]] = {}
    for group, columns in db_families.items():
        merged[group] = list(columns)

    for group, columns in auto_families.items():
        unassigned = [column for column in columns if column not in db_assigned_columns]
        if unassigned:
            merged.setdefault(group, []).extend(unassigned)

    return {group: columns for group, columns in merged.items() if len(columns) >= 2}


def get_dimension_families_with_source(service: "SchemaService", table_name: str) -> List[Dict]:
    db_map: Dict[str, str] = {}
    with service.engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT dimension_group, column_name
                FROM schema_metadata
                WHERE table_name = :table_name
                  AND dimension_group IS NOT NULL
            """), {"table_name": table_name})
            for row in result.mappings().fetchall():
                db_map[row["column_name"]] = row["dimension_group"]
        except SQLAlchemyError:
            pass

    try:
        columns = service.get_table_info(table_name)
        all_column_names = [column["name"] for column in columns]
    except (SQLAlchemyError, KeyError, TypeError, ValueError):
        all_column_names = []

    auto_families = detect_families(all_column_names) if all_column_names else {}
    families: Dict[str, List[Dict]] = {}

    for column_name, group in db_map.items():
        families.setdefault(group, []).append({"column_name": column_name, "source": "db"})

    for group, columns in auto_families.items():
        for column_name in columns:
            if column_name not in db_map:
                families.setdefault(group, []).append({"column_name": column_name, "source": "auto"})

    result = []
    for family_name, columns in sorted(families.items()):
        if len(columns) >= 2:
            source = "db" if all(column["source"] == "db" for column in columns) else "auto" if all(column["source"] == "auto" for column in columns) else "mixed"
            result.append({
                "family_name": family_name,
                "columns": sorted(columns, key=lambda column: column["column_name"]),
                "source": source,
            })
    return result
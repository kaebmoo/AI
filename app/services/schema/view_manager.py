import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.services.schema.sql_identifiers import assert_safe_identifier, quote_identifier
from app.core.time_utils import utcnow

if TYPE_CHECKING:
    from app.services.schema.service import SchemaService


logger = logging.getLogger(__name__)


def get_all_tables(service: "SchemaService") -> List[str]:
    inspector = inspect(service.business_engine)
    tables = inspector.get_table_names()
    view_names = inspector.get_view_names()
    filtered = []
    for name in tables + view_names:
        if name.startswith("sqlite_") or name.startswith("schema_"):
            continue
        filtered.append(name)
    return sorted(filtered)


def create_custom_view(service: "SchemaService", view_name: str, source_table: str, mapping: List[Dict[str, str]]) -> bool:
    assert_safe_identifier(view_name, "view name")
    assert_safe_identifier(source_table, "source table")

    available_objects = set(get_all_tables(service))
    if source_table not in available_objects:
        raise ValueError(f"Source table not found: {source_table}")

    inspector = inspect(service.business_engine)
    actual_columns = {column["name"] for column in inspector.get_columns(source_table)}

    select_parts = []
    for item in mapping:
        column_name = item["col"]
        alias = item.get("alias")

        if column_name not in actual_columns:
            raise ValueError(f"Invalid source column: {column_name}")
        if alias:
            assert_safe_identifier(alias, "alias")

        if alias and alias != column_name:
            select_parts.append(f"{quote_identifier(column_name)} AS {quote_identifier(alias)}")
        else:
            select_parts.append(quote_identifier(column_name))

    select_clause = ", ".join(select_parts)
    sql = f"CREATE VIEW {quote_identifier(view_name)} AS SELECT {select_clause} FROM {quote_identifier(source_table)}"

    with service.business_engine.begin() as conn:
        conn.execute(text(f"DROP VIEW IF EXISTS {quote_identifier(view_name)}"))
        conn.execute(text(sql))

    try:
        save_view_column_mappings(service, view_name, source_table, mapping)
        propagate_metadata_to_view(service, view_name)
    except SQLAlchemyError as exc:
        logger.warning("View created but mapping/propagation failed: %s", exc)

    return True


def list_views_with_mappings(service: "SchemaService") -> List[Dict]:
    with service.engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT
                    vcm.view_name,
                    vcm.source_table,
                    COUNT(vcm.id) as mapping_count,
                    COUNT(sm.id) as metadata_with_thai_count
                FROM view_column_mappings vcm
                LEFT JOIN schema_metadata sm
                    ON sm.table_name = vcm.view_name
                    AND sm.column_name = vcm.view_column
                    AND sm.display_name_th IS NOT NULL
                    AND sm.display_name_th != ''
                GROUP BY vcm.view_name, vcm.source_table
                ORDER BY vcm.view_name
            """))
            return [dict(row) for row in result.mappings().fetchall()]
        except SQLAlchemyError as exc:
            logger.warning("Failed to list views with mappings: %s", exc)
            return []


def save_view_column_mappings(service: "SchemaService", view_name: str, source_table: str, mappings: List[Dict[str, str]]) -> int:
    with service.engine.begin() as conn:
        conn.execute(text("DELETE FROM view_column_mappings WHERE view_name = :vn"), {"vn": view_name})

        count = 0
        for item in mappings:
            source_col = item["col"]
            view_col = item.get("alias") or source_col
            mapping_type = "alias" if view_col != source_col else "passthrough"
            conn.execute(text("""
                INSERT INTO view_column_mappings (view_name, view_column, source_table, source_column, mapping_type)
                VALUES (:vn, :vc, :st, :sc, :mt)
            """), {
                "vn": view_name,
                "vc": view_col,
                "st": source_table,
                "sc": source_col,
                "mt": mapping_type,
            })
            count += 1

    logger.info("Saved %s column mappings for view '%s'", count, view_name)
    return count


def get_view_column_mappings(service: "SchemaService", view_name: str) -> List[Dict]:
    with service.engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT * FROM view_column_mappings WHERE view_name = :vn ORDER BY id"), {"vn": view_name})
            return [dict(row) for row in result.mappings().fetchall()]
        except SQLAlchemyError as exc:
            logger.warning("Failed to get view column mappings: %s", exc)
            return []


def find_source_metadata(_service: "SchemaService", conn, source_table: str, source_column: str) -> Optional[Dict]:
    result = conn.execute(text("""
        SELECT * FROM schema_metadata
        WHERE table_name = :st AND column_name = :sc AND status = 'active'
    """), {"st": source_table, "sc": source_column})
    row = result.mappings().fetchone()
    if row:
        return dict(row)

    try:
        result = conn.execute(text("""
            SELECT DISTINCT vcm2.view_name, vcm2.view_column
            FROM view_column_mappings vcm2
            WHERE vcm2.source_table = :st AND vcm2.source_column = :sc
        """), {"st": source_table, "sc": source_column})
        for chain_row in result.mappings().fetchall():
            chain_view = chain_row["view_name"]
            chain_col = chain_row["view_column"]
            meta_result = conn.execute(text("""
                SELECT * FROM schema_metadata
                WHERE table_name = :tv AND column_name = :tc AND status = 'active'
                AND display_name_th IS NOT NULL AND display_name_th != ''
            """), {"tv": chain_view, "tc": chain_col})
            meta_row = meta_result.mappings().fetchone()
            if meta_row:
                logger.info("Chain resolved: %s.%s -> %s.%s", source_table, source_column, chain_view, chain_col)
                return dict(meta_row)
    except SQLAlchemyError:
        pass

    try:
        result = conn.execute(text("""
            SELECT * FROM schema_metadata
            WHERE column_name = :sc AND status = 'active'
            AND display_name_th IS NOT NULL AND display_name_th != ''
            AND table_name != :exclude
            ORDER BY table_name
            LIMIT 1
        """), {"sc": source_column, "exclude": source_table})
        row = result.mappings().fetchone()
        if row:
            logger.info("Fallback found: metadata for '%s' from table '%s'", source_column, row["table_name"])
            return dict(row)
    except SQLAlchemyError:
        pass

    return None


def propagate_metadata_to_view(service: "SchemaService", view_name: str) -> Dict:
    """Copy the source tables' metadata onto the view's columns. Plan 8.1: a copy is `inferred` — it fills a
    machine's row; a row a person owns keeps what it has and the copy waits in knowledge_proposals."""
    from app.services.provenance import INFERRED, may_replace, propose

    mappings = get_view_column_mappings(service, view_name)
    if not mappings:
        logger.warning("No column mappings found for view '%s'", view_name)
        return {"created": 0, "updated": 0, "skipped": 0, "missing_columns": []}

    created = 0
    updated = 0
    skipped = 0
    missing_columns = []

    with service.engine.begin() as conn:
        for item in mappings:
            source_table = item["source_table"]
            source_column = item["source_column"]
            view_column = item["view_column"]
            source_meta = find_source_metadata(service, conn, source_table, source_column)

            result = conn.execute(text("""
                SELECT id, display_name_th, source, status FROM schema_metadata
                WHERE table_name = :vn AND column_name = :vc
            """), {"vn": view_name, "vc": view_column})
            existing = result.mappings().fetchone()

            if source_meta:
                if existing and not existing["display_name_th"] and not may_replace(INFERRED, existing["source"], existing["status"]):
                    fill = {k: source_meta.get(k) for k in ("display_name_th", "display_name_en", "description", "data_type",
                                                            "hierarchy_level", "special_notes", "conversion_sql",
                                                            "dimension_group") if source_meta.get(k) is not None}
                    propose(conn, "schema_metadata", {"table_name": view_name, "column_name": view_column}, fill, INFERRED,
                            reason=f"คัดลอกจาก {source_table}.{source_column} — แถวนี้เป็นของคน")
                    skipped += 1
                elif existing:
                    if not existing["display_name_th"]:
                        conn.execute(text("""
                            UPDATE schema_metadata SET
                                display_name_th = :display_name_th,
                                display_name_en = COALESCE(display_name_en, :display_name_en),
                                description = COALESCE(description, :description),
                                data_type = COALESCE(data_type, :data_type),
                                is_summable = :is_summable,
                                is_groupable = :is_groupable,
                                hierarchy_level = COALESCE(hierarchy_level, :hierarchy_level),
                                special_notes = COALESCE(special_notes, :special_notes),
                                conversion_sql = COALESCE(conversion_sql, :conversion_sql),
                                dimension_group = COALESCE(dimension_group, :dimension_group),
                                updated_at = :updated_at
                            WHERE table_name = :vn AND column_name = :vc
                        """), {
                            "display_name_th": source_meta.get("display_name_th"),
                            "display_name_en": source_meta.get("display_name_en"),
                            "description": source_meta.get("description"),
                            "data_type": source_meta.get("data_type"),
                            "is_summable": source_meta.get("is_summable", False),
                            "is_groupable": source_meta.get("is_groupable", True),
                            "hierarchy_level": source_meta.get("hierarchy_level"),
                            "special_notes": source_meta.get("special_notes"),
                            "conversion_sql": source_meta.get("conversion_sql"),
                            "dimension_group": source_meta.get("dimension_group"),
                            "updated_at": utcnow(),
                            "vn": view_name,
                            "vc": view_column,
                        })
                        updated += 1
                    else:
                        skipped += 1
                else:
                    conn.execute(text("""
                        INSERT INTO schema_metadata (
                            table_name, column_name, display_name_th, display_name_en,
                            description, data_type, format_hint, example_value,
                            is_summable, is_groupable, hierarchy_level,
                            special_notes, conversion_sql, dimension_group, source, status
                        ) VALUES (
                            :table_name, :column_name, :display_name_th, :display_name_en,
                            :description, :data_type, :format_hint, :example_value,
                            :is_summable, :is_groupable, :hierarchy_level,
                            :special_notes, :conversion_sql, :dimension_group, 'inferred', 'active'
                        )
                    """), {
                        "table_name": view_name,
                        "column_name": view_column,
                        "display_name_th": source_meta.get("display_name_th"),
                        "display_name_en": source_meta.get("display_name_en"),
                        "description": source_meta.get("description"),
                        "data_type": source_meta.get("data_type"),
                        "format_hint": source_meta.get("format_hint"),
                        "example_value": source_meta.get("example_value"),
                        "is_summable": source_meta.get("is_summable", False),
                        "is_groupable": source_meta.get("is_groupable", True),
                        "hierarchy_level": source_meta.get("hierarchy_level"),
                        "special_notes": source_meta.get("special_notes"),
                        "conversion_sql": source_meta.get("conversion_sql"),
                        "dimension_group": source_meta.get("dimension_group"),
                    })
                    created += 1
            else:
                missing_columns.append({
                    "view_column": view_column,
                    "source_table": source_table,
                    "source_column": source_column,
                })
                if not existing:
                    conn.execute(text("""
                        INSERT INTO schema_metadata (table_name, column_name, data_type, source, status)
                        VALUES (:table_name, :column_name, :data_type, 'inferred', 'active')
                    """), {
                        "table_name": view_name,
                        "column_name": view_column,
                        "data_type": "TEXT",
                    })
                    created += 1

    logger.info(
        "Propagated metadata to '%s': %s created, %s updated, %s skipped, %s missing source",
        view_name,
        created,
        updated,
        skipped,
        len(missing_columns),
    )
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "missing_columns": missing_columns,
    }
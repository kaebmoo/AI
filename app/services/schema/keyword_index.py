import json
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.services.schema.sql_identifiers import quote_identifier

if TYPE_CHECKING:
    from app.services.schema.service import SchemaService


logger = logging.getLogger(__name__)

STRIP_PREFIXES = [
    "กลุ่มบริการ", "กลุ่ม", "บริการ", "สายงาน", "ฝ่าย", "ส่วน",
    "รายได้", "ค่าใช้จ่าย", "หมวด",
]

_known_terms_cache: dict = {}


def clear_known_terms_cache() -> None:
    _known_terms_cache.clear()


def get_searchable_columns(service: "SchemaService", context_name: str, table_name: Optional[str] = None) -> List[str]:
    """Get searchable/groupable columns from schema_metadata. Falls back to inspecting actual columns."""
    metadata_tables = [context_name]
    if table_name:
        metadata_tables.append(table_name)

    try:
        with service.engine.connect() as conn:
            for table in metadata_tables:
                rows = conn.execute(
                    text("SELECT column_name FROM schema_metadata WHERE table_name = :tbl AND is_groupable = 1"),
                    {"tbl": table},
                ).fetchall()
                if rows:
                    columns = [row[0] for row in rows]
                    logger.info("Searchable columns for '%s' from schema_metadata: %s columns", context_name, len(columns))
                    return columns
    except SQLAlchemyError as exc:
        logger.warning("Failed to get searchable columns from metadata: %s", exc)

    if table_name:
        try:
            inspector = inspect(service.business_engine)
            all_columns = inspector.get_columns(table_name)
            columns = [
                column["name"]
                for column in all_columns
                if str(column.get("type", "")).upper() in ("TEXT", "VARCHAR", "NVARCHAR")
            ]
            if columns:
                logger.info("Searchable columns for '%s' from table inspection: %s columns", context_name, len(columns))
                return columns
        except SQLAlchemyError:
            pass

    return []


def build_keyword_index(service: "SchemaService", context_name: str = "revenue", table_name: str = "revenue_search") -> int:
    """Scan searchable columns, extract keywords, and populate keyword_value_index table.

    Reads the view on service.business_engine (the context's source), writes the index on the
    config engine. Scans before deleting: a failed or empty scan keeps the existing index.
    """
    columns = get_searchable_columns(service, context_name, table_name)

    inspector = inspect(service.business_engine)
    try:
        actual_columns = set(column["name"] for column in inspector.get_columns(table_name))
    except SQLAlchemyError:
        logger.error("Cannot inspect table %s", table_name)
        return 0

    all_rows = []

    with service.business_engine.connect() as conn:
        for column_name in columns:
            matching_col = next((column for column in actual_columns if column.upper() == column_name.upper()), None)
            if not matching_col:
                continue

            try:
                result = conn.execute(
                    text(
                        f"SELECT DISTINCT {quote_identifier(matching_col)} "
                        f"FROM {quote_identifier(table_name)} "
                        f"WHERE {quote_identifier(matching_col)} IS NOT NULL"
                    )
                )
                values = [row[0] for row in result.fetchall() if row[0]]
            except SQLAlchemyError as exc:
                logger.error("Failed to scan %s, existing keyword index kept: %s", matching_col, exc)
                return 0

            for value in values:
                value_str = str(value).strip()
                if not value_str:
                    continue

                for keyword in extract_keywords(value_str):
                    if len(keyword) < 2:
                        continue
                    all_rows.append(
                        {
                            "keyword": keyword.lower(),
                            "column_name": matching_col,
                            "column_value": value_str,
                            "table_name": table_name,
                            "context_name": context_name,
                        }
                    )

    if not all_rows:
        logger.error("Keyword index scan of %s found no values, existing index kept", table_name)
        return 0

    with service.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM keyword_value_index WHERE context_name = :ctx AND table_name = :tbl"),
            {"ctx": context_name, "tbl": table_name},
        )
        conn.execute(
            text(
                """
                    INSERT INTO keyword_value_index (keyword, column_name, column_value, table_name, context_name)
                    VALUES (:keyword, :column_name, :column_value, :table_name, :context_name)
                """
            ),
            all_rows,
        )

    logger.info("Keyword index built: %s entries for context=%s, table=%s", len(all_rows), context_name, table_name)
    clear_known_terms_cache()
    return len(all_rows)


def extract_keywords(value: str) -> List[str]:
    """Extract searchable keywords from a column value."""
    import re

    keywords = {value.strip()}

    clean = value.strip()
    for prefix in STRIP_PREFIXES:
        if clean.startswith(prefix):
            remainder = clean[len(prefix):].strip()
            if remainder:
                keywords.add(remainder)

    parts = re.split(r'[\s\-&/()（）,]+', value)
    for part in parts:
        part = part.strip()
        if len(part) >= 2:
            keywords.add(part)

    return list(keywords)


def search_keyword_index(service: "SchemaService", keyword: str, context_name: str = "revenue", limit: int = 10) -> List[Dict]:
    """Search pre-built keyword index for matching values."""
    results = []
    keyword_lower = keyword.lower().strip()
    if not keyword_lower:
        return results

    try:
        with service.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT column_name, column_value, table_name
                    FROM keyword_value_index
                    WHERE keyword LIKE :kw
                      AND context_name = :ctx
                    LIMIT :lim
                    """
                ),
                {"kw": f"%{keyword_lower}%", "ctx": context_name, "lim": limit},
            ).fetchall()

            for row in rows:
                results.append(
                    {
                        "keyword": keyword,
                        "column_name": row[0],
                        "column_value": row[1],
                        "table_name": row[2],
                    }
                )

        if results:
            logger.info("Keyword index: '%s' → %s matches", keyword, len(results))
        else:
            logger.info("Keyword index: '%s' → no matches", keyword)
    except SQLAlchemyError as exc:
        logger.warning("Keyword index search failed: %s", exc)

    return results


def _like(column: str, dialect: str) -> str:
    """The match condition of search_db_for_keyword's own query. On SQLite the UPPER half
    adds nothing — upper() and LIKE's case folding are both ASCII-only — and costs ~2/3 of
    the probe, so it is left out there (same columns hit, the per-column query is unchanged)."""
    q = quote_identifier(column)
    if dialect == "sqlite":
        return f"{q} LIKE :kw"
    return f"({q} LIKE :kw OR UPPER({q}) LIKE UPPER(:kw))"


def _columns_with_match(conn, table_name: str, columns: List[str], pattern: str) -> List[str]:
    """The columns (same order, duplicates kept) holding at least one match — ONE scan of the view.

    search_db_for_keyword then runs its per-column DISTINCT only on these: a keyword
    with no match costs 1 scan instead of 1 per column (v_expense_mart: ~0.1 s each).
    A column the engine can't LIKE (DuckDB: non-text) fails the probe as it failed its
    own query before — it is dropped; if the probe still can't run, every column is
    returned and the per-column path behaves exactly as it always did.
    """
    if not columns:
        return []
    table = quote_identifier(table_name)
    dialect = conn.dialect.name

    def probe(cols):
        flags = ", ".join(f"MAX(CASE WHEN {_like(c, dialect)} THEN 1 ELSE 0 END)" for c in cols)
        return conn.execute(text(f"SELECT {flags} FROM {table}"), {"kw": pattern}).fetchone()

    def binds(col):  # bind/plan only — LIMIT 0 reads no rows
        try:
            conn.execute(text(f"SELECT 1 FROM {table} WHERE {_like(col, dialect)} LIMIT 0"), {"kw": pattern}).fetchall()
            return True
        except SQLAlchemyError:
            return False

    try:
        return [c for c, hit in zip(columns, probe(columns)) if hit]
    except SQLAlchemyError:
        pass
    usable = [c for c in columns if binds(c)]
    try:
        return [c for c, hit in zip(usable, probe(usable)) if hit] if usable else []
    except SQLAlchemyError:
        return columns


def search_db_for_keyword(
    service: "SchemaService",
    keyword: str,
    table_name: str = "revenue_search",
    context_name: str = "revenue",
    limit: int = 10,
) -> List[Dict]:
    """Fallback: search actual DB columns for keyword match."""
    results = []
    keyword_pattern = f"%{keyword}%"
    columns = get_searchable_columns(service, context_name, table_name)

    inspector = inspect(service.business_engine)
    try:
        actual_columns = set(column["name"] for column in inspector.get_columns(table_name))
    except SQLAlchemyError:
        return results

    with service.business_engine.connect() as conn:
        resolved = [next((c for c in actual_columns if c.upper() == name.upper()), None) for name in columns]
        for matching_col in _columns_with_match(conn, table_name, [c for c in resolved if c], keyword_pattern):
            try:
                rows = conn.execute(
                    text(
                        f"SELECT DISTINCT {quote_identifier(matching_col)} "
                        f"FROM {quote_identifier(table_name)} "
                        f"WHERE {quote_identifier(matching_col)} LIKE :kw "
                        f"OR UPPER({quote_identifier(matching_col)}) LIKE UPPER(:kw) "
                        f"LIMIT :lim"
                    ),
                    {"kw": keyword_pattern, "lim": limit},
                ).fetchall()

                for row in rows:
                    if row[0]:
                        results.append(
                            {
                                "keyword": keyword,
                                "column_name": matching_col,
                                "column_value": str(row[0]),
                                "table_name": table_name,
                            }
                        )
            except SQLAlchemyError:
                continue

    if results:
        logger.info("DB search: '%s' → %s matches across columns", keyword, len(results))
    else:
        logger.info("DB search: '%s' → no matches", keyword)

    return results


def get_known_terms(service: "SchemaService", context_name: Optional[str] = None) -> List[str]:
    """Get all known terms from keyword_value_index + master_hierarchy_values."""
    cache_key = context_name or "__all__"
    now = time.time()

    if cache_key in _known_terms_cache:
        cached = _known_terms_cache[cache_key]
        if now - cached["ts"] < 3600:
            return cached["terms"]

    terms_set: set = set()
    try:
        with service.engine.connect() as conn:
            context_filter = "AND context_name = :ctx" if context_name else ""
            params = {"ctx": context_name} if context_name else {}

            rows = conn.execute(
                text(
                    f'''
                    SELECT DISTINCT keyword FROM keyword_value_index
                    WHERE 1=1 {context_filter}
                    '''
                ),
                params,
            ).fetchall()
            for row in rows:
                value = (row[0] or "").strip()
                if len(value) >= 2:
                    terms_set.add(value)

            hierarchy_rows = conn.execute(
                text(
                    f'''
                    SELECT DISTINCT value FROM master_hierarchy_values
                    WHERE is_active = 1 {context_filter}
                    '''
                ),
                params,
            ).fetchall()
            for row in hierarchy_rows:
                value = (row[0] or "").strip()
                if len(value) >= 2:
                    terms_set.add(value)

            alias_rows = conn.execute(
                text(
                    f'''
                    SELECT DISTINCT aliases FROM master_hierarchy_values
                    WHERE aliases IS NOT NULL AND aliases != '' AND is_active = 1 {context_filter}
                    '''
                ),
                params,
            ).fetchall()
            for row in alias_rows:
                raw = (row[0] or "").strip()
                aliases_list = []
                if raw.startswith("["):
                    try:
                        aliases_list = json.loads(raw)
                    except (ValueError, TypeError):
                        aliases_list = raw.split(",")
                else:
                    aliases_list = raw.split(",")

                for alias in aliases_list:
                    alias = str(alias).strip()
                    if len(alias) >= 2:
                        terms_set.add(alias)
    except (SQLAlchemyError, TypeError, ValueError) as exc:
        logger.warning("get_known_terms failed: %s", exc)

    sorted_terms = sorted(terms_set, key=len, reverse=True)
    _known_terms_cache[cache_key] = {"terms": sorted_terms, "ts": now}
    return sorted_terms
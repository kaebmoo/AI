"""
NT AI Assistant - Hierarchy Service
======================================
Business logic for master hierarchy management.
Handles: CRUD, search, auto-extract, diff detection, unmatched keyword logging.
"""

import json
import re
import sqlite3
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """Get config DB path (master_hierarchy lives in config.db)."""
    config_url = settings.CONFIG_DB_URL
    if config_url:
        return config_url.replace("sqlite:///", "").replace("sqlite://", "")
    # Fallback: same as DATABASE_URL (backward compatible)
    return settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(_get_db_path())


def _data_engine(context_name: str):
    """Where a context's data lives (legacy business DB or a file source) — never the config DB.
    REMAIN-9.5: detect_changes / bootstrap / available views used to query views on config.db."""
    from app.services.data_sources import source_resolver
    return source_resolver.for_context(context_name).engine


def _data_rows(engine, sql: str) -> list:
    from sqlalchemy import text
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


class HierarchyService:
    """Service for master hierarchy CRUD, search, and automation."""

    # ------------------------------------------------------------------
    # Level CRUD
    # ------------------------------------------------------------------

    def list_contexts(self) -> List[Dict]:
        """List all hierarchy contexts with summary counts."""
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT h.context_name,
                       COUNT(DISTINCT h.level) as level_count,
                       COALESCE(v.total, 0) as value_count,
                       COALESCE(v.manual_count, 0) as manual_count,
                       COALESCE(v.auto_count, 0) as auto_count
                FROM master_hierarchy h
                LEFT JOIN (
                    SELECT context_name,
                           COUNT(*) as total,
                           SUM(CASE WHEN source='manual' THEN 1 ELSE 0 END) as manual_count,
                           SUM(CASE WHEN source='auto' THEN 1 ELSE 0 END) as auto_count
                    FROM master_hierarchy_values WHERE is_active=1
                    GROUP BY context_name
                ) v ON h.context_name = v.context_name
                WHERE h.is_active = 1
                GROUP BY h.context_name
                ORDER BY h.context_name
            """).fetchall()
            return [
                {"context_name": r[0], "level_count": r[1], "value_count": r[2],
                 "manual_count": r[3], "auto_count": r[4]}
                for r in rows
            ]
        finally:
            conn.close()

    def get_levels(self, context_name: str) -> List[Dict]:
        """Get hierarchy levels for a context with value counts."""
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT h.context_name, h.level, h.level_label_th, h.level_label_en,
                       h.level_columns, h.detection_keywords, h.source, h.is_active,
                       COALESCE(vc.cnt, 0) as value_count
                FROM master_hierarchy h
                LEFT JOIN (
                    SELECT context_name, level, COUNT(*) as cnt
                    FROM master_hierarchy_values WHERE is_active=1
                    GROUP BY context_name, level
                ) vc ON h.context_name = vc.context_name AND h.level = vc.level
                WHERE h.context_name = ? AND h.is_active = 1
                ORDER BY h.level
            """, (context_name,)).fetchall()
            return [
                {"context_name": r[0], "level": r[1], "level_label_th": r[2],
                 "level_label_en": r[3], "level_columns": json.loads(r[4]),
                 "detection_keywords": json.loads(r[5]), "source": r[6],
                 "is_active": bool(r[7]), "value_count": r[8]}
                for r in rows
            ]
        finally:
            conn.close()

    def upsert_level(self, context_name: str, level: int, data: Dict) -> Dict:
        """Create or update a hierarchy level. Saves parent_column + source_view for extract."""
        conn = _get_conn()
        try:
            cols_json = json.dumps(data.get("level_columns", []), ensure_ascii=False) if "level_columns" in data else None
            kw_json = json.dumps(data.get("detection_keywords", []), ensure_ascii=False) if "detection_keywords" in data else None

            conn.execute("""
                INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en,
                    level_columns, detection_keywords, parent_column, source_view, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual')
                ON CONFLICT(context_name, level) DO UPDATE SET
                    level_label_th = COALESCE(?, level_label_th),
                    level_label_en = COALESCE(?, level_label_en),
                    level_columns = COALESCE(?, level_columns),
                    detection_keywords = COALESCE(?, detection_keywords),
                    parent_column = COALESCE(?, parent_column),
                    source_view = COALESCE(?, source_view),
                    source = 'manual', is_active = 1, updated_at = CURRENT_TIMESTAMP
            """, (
                context_name, level,
                data.get("level_label_th", ""), data.get("level_label_en", ""),
                json.dumps(data.get("level_columns", []), ensure_ascii=False),
                json.dumps(data.get("detection_keywords", []), ensure_ascii=False),
                data.get("parent_column"), data.get("source_view"),
                data.get("level_label_th"), data.get("level_label_en"),
                cols_json, kw_json,
                data.get("parent_column"), data.get("source_view"),
            ))
            conn.commit()
            self._invalidate_cache()
            return self.get_levels(context_name)
        finally:
            conn.close()

    def delete_level(self, context_name: str, level: int):
        """Soft-delete a hierarchy level."""
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE master_hierarchy SET is_active = 0 WHERE context_name = ? AND level = ?",
                (context_name, level))
            conn.commit()
            self._invalidate_cache()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Value CRUD
    # ------------------------------------------------------------------

    def get_values(self, context_name: str, level: Optional[int] = None,
                   parent_value: Optional[str] = None, search: Optional[str] = None,
                   page: int = 1, page_size: int = 100) -> Dict:
        """Get hierarchy values with filtering, pagination, and children count."""
        conn = _get_conn()
        try:
            conditions = ["v.context_name = ?", "v.is_active = 1"]
            params: list = [context_name]

            if level is not None:
                conditions.append("v.level = ?")
                params.append(level)
            if parent_value is not None:
                conditions.append("v.parent_value = ?")
                params.append(parent_value)
            if search:
                conditions.append("(v.value LIKE ? OR v.aliases LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])

            where = " AND ".join(conditions)
            offset = (page - 1) * page_size

            # Count
            total = conn.execute(f"SELECT COUNT(*) FROM master_hierarchy_values v WHERE {where}", params).fetchone()[0]

            # Data with children count
            rows = conn.execute(f"""
                SELECT v.id, v.context_name, v.level, v.value, v.parent_value,
                       v.aliases, v.source, v.is_active,
                       COALESCE(c.cnt, 0) as children_count
                FROM master_hierarchy_values v
                LEFT JOIN (
                    SELECT parent_value, COUNT(*) as cnt
                    FROM master_hierarchy_values
                    WHERE context_name = ? AND is_active = 1
                    GROUP BY parent_value
                ) c ON v.value = c.parent_value
                WHERE {where}
                ORDER BY v.level, v.value
                LIMIT ? OFFSET ?
            """, [context_name] + params + [page_size, offset]).fetchall()

            items = [
                {"id": r[0], "context_name": r[1], "level": r[2], "value": r[3],
                 "parent_value": r[4], "aliases": json.loads(r[5]) if r[5] else [],
                 "source": r[6], "is_active": bool(r[7]), "children_count": r[8]}
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def create_value(self, context_name: str, data: Dict) -> Dict:
        """Create a hierarchy value."""
        conn = _get_conn()
        try:
            aliases_json = json.dumps(data.get("aliases", []), ensure_ascii=False)
            conn.execute("""
                INSERT INTO master_hierarchy_values (context_name, level, value, parent_value, aliases, source)
                VALUES (?, ?, ?, ?, ?, 'manual')
                ON CONFLICT(context_name, level, value) DO UPDATE SET
                    parent_value = excluded.parent_value,
                    aliases = excluded.aliases,
                    source = 'manual', is_active = 1
            """, (context_name, data["level"], data["value"], data.get("parent_value"), aliases_json))
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    def update_value(self, value_id: int, data: Dict) -> Dict:
        """Update a hierarchy value."""
        conn = _get_conn()
        try:
            updates = []
            params = []
            if "value" in data:
                updates.append("value = ?")
                params.append(data["value"])
            if "parent_value" in data:
                updates.append("parent_value = ?")
                params.append(data["parent_value"])
            if "aliases" in data:
                updates.append("aliases = ?")
                params.append(json.dumps(data["aliases"], ensure_ascii=False))
            updates.append("source = 'manual'")
            params.append(value_id)
            conn.execute(f"UPDATE master_hierarchy_values SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    def delete_value(self, value_id: int):
        """Soft-delete a hierarchy value."""
        conn = _get_conn()
        try:
            conn.execute("UPDATE master_hierarchy_values SET is_active = 0 WHERE id = ?", (value_id,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Search (used by AI pipeline)
    # ------------------------------------------------------------------

    def search_aliases(self, context_name: str, query: str, limit: int = 10) -> List[Dict]:
        """Search hierarchy values by alias match. Returns matches with parent chain."""
        conn = _get_conn()
        try:
            query_lower = query.lower().strip()
            if not query_lower:
                return []
            # Phase 4.5: hierarchy values are read from the rows — none for a source that isn't `full`
            from app.core.llm_policy import FULL
            from app.services.data_sources import policy_for_context
            if policy_for_context(context_name) != FULL:
                return []

            rows = conn.execute("""
                SELECT v.value, v.level, v.parent_value, v.aliases,
                       h.level_label_th, h.level_columns
                FROM master_hierarchy_values v
                JOIN master_hierarchy h ON v.context_name = h.context_name AND v.level = h.level
                WHERE v.context_name = ? AND v.is_active = 1 AND h.is_active = 1
                  AND v.aliases LIKE ?
                ORDER BY v.level
                LIMIT ?
            """, (context_name, f"%{query_lower}%", limit)).fetchall()

            results = []
            for r in rows:
                aliases = json.loads(r[3]) if r[3] else []
                # Find which alias matched
                matched = next((a for a in aliases if query_lower in a), query_lower)
                columns = json.loads(r[5]) if r[5] else []

                # Build parent chain
                parent_chain = self._get_parent_chain(conn, context_name, r[2])

                results.append({
                    "value": r[0], "level": r[1], "level_label_th": r[4],
                    "context_name": context_name,
                    "parent_chain": parent_chain,
                    "matched_alias": matched,
                    "column_name": columns[0] if columns else "",
                })
            return results
        finally:
            conn.close()

    def _get_parent_chain(self, conn, context_name: str, parent_value: Optional[str]) -> List[str]:
        """Walk up the hierarchy to get full parent chain."""
        chain = []
        current = parent_value
        max_depth = 5  # safety limit
        while current and max_depth > 0:
            chain.insert(0, current)
            row = conn.execute(
                "SELECT parent_value FROM master_hierarchy_values WHERE context_name = ? AND value = ? AND is_active = 1",
                (context_name, current)
            ).fetchone()
            current = row[0] if row else None
            max_depth -= 1
        return chain

    # ------------------------------------------------------------------
    # Auto-extract & Diff
    # ------------------------------------------------------------------

    def detect_changes(self, context_name: str) -> Dict:
        """Compare master_hierarchy_values vs actual data DISTINCT values."""
        conn = _get_conn()
        try:
            levels = self.get_levels(context_name)
            if not levels:
                return {"context_name": context_name, "new_values": [], "missing_values": [], "unchanged_count": 0}

            # Get the main view for this context
            view_row = conn.execute(
                "SELECT main_view FROM schema_contexts WHERE name = ? AND is_active = 1",
                (context_name,)
            ).fetchone()
            if not view_row:
                return {"context_name": context_name, "new_values": [], "missing_values": [], "unchanged_count": 0}
            view = view_row[0]

            new_values = []
            missing_values = []
            unchanged = 0
            data = _data_engine(context_name)

            for level_info in levels:
                col = level_info["level_columns"][0]
                try:
                    data_values = set(
                        r[0] for r in _data_rows(
                            data, f'SELECT DISTINCT "{col}" FROM "{view}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\''
                        )
                    )
                except Exception:
                    continue

                master_values = set(
                    r[0] for r in conn.execute(
                        "SELECT value FROM master_hierarchy_values WHERE context_name = ? AND level = ? AND is_active = 1",
                        (context_name, level_info["level"])
                    ).fetchall()
                )

                for v in data_values - master_values:
                    new_values.append({"level": level_info["level"], "value": v, "change_type": "new"})
                for v in master_values - data_values:
                    missing_values.append({"level": level_info["level"], "value": v, "change_type": "missing"})
                unchanged += len(data_values & master_values)

            return {
                "context_name": context_name,
                "new_values": new_values,
                "missing_values": missing_values,
                "unchanged_count": unchanged,
            }
        finally:
            conn.close()

    def auto_extract(self, context_name: Optional[str] = None) -> List[Dict]:
        """Run auto-extract from data. Delegates to extract_hierarchy.py logic."""
        import subprocess, sys
        cmd = [sys.executable, "scripts/extract_hierarchy.py"]
        if context_name:
            cmd += ["--context", context_name]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent.parent.parent))
        self._invalidate_cache()
        return [{"output": result.stdout, "errors": result.stderr}]

    def bootstrap_from_view(self, context_name: str, view_name: str) -> Dict:
        """
        Bootstrap: auto-detect hierarchy columns from a view and create levels + extract values.

        Solves the chicken-and-egg problem: no levels exist yet → can't extract.
        This function detects columns, creates levels, then extracts values — all in one step.

        Heuristic: looks for columns with low-to-medium cardinality that form parent-child patterns.
        """
        from sqlalchemy import inspect as sa_inspect

        conn = _get_conn()  # config DB: master_hierarchy is written here
        data = _data_engine(context_name)
        try:
            # 1. Get all columns from the view (in the context's own source)
            try:
                cols_info = sa_inspect(data).get_columns(view_name)
            except Exception as e:
                return {"error": f"View '{view_name}' not found: {e}"}

            if not cols_info:
                return {"error": f"View '{view_name}' has no columns"}

            # 2. Analyze columns: get distinct counts to find hierarchy candidates
            text_cols = []
            for col in cols_info:
                col_name = col["name"]
                col_type = str(col.get("type") or "").upper()
                # Skip numeric, date, and ID columns
                if any(k in col_name.lower() for k in ["year", "month", "date", "value", "amount", "price",
                                                         "quantity", "revenue", "expense", "cost_center",
                                                         "id", "_key", "abbr"]):
                    continue
                if any(k in col_type for k in ["INT", "REAL", "FLOAT", "DOUBLE", "NUMERIC"]):
                    # Allow integer columns only if they have very few distinct values (might be codes)
                    try:
                        cnt = _data_rows(data, f'SELECT COUNT(DISTINCT "{col_name}") FROM "{view_name}"')[0][0]
                        if cnt > 50:
                            continue
                    except Exception:
                        continue

                try:
                    cnt = _data_rows(
                        data, f'SELECT COUNT(DISTINCT "{col_name}") FROM "{view_name}" WHERE "{col_name}" IS NOT NULL AND "{col_name}" != \'\''
                    )[0][0]
                    if 1 < cnt <= 1000:  # reasonable hierarchy cardinality
                        text_cols.append({"name": col_name, "distinct": cnt})
                except Exception:
                    continue

            # 3. Sort by cardinality (lowest = broadest level)
            text_cols.sort(key=lambda c: c["distinct"])

            if not text_cols:
                return {"error": "No suitable hierarchy columns found"}

            # 4. Try to detect parent-child pairs
            levels_created = []
            level_num = 0
            used_cols = set()

            for i, col_info in enumerate(text_cols):
                col = col_info["name"]
                if col in used_cols:
                    continue

                # Find potential parent (a column with fewer distinct values where each child maps to one parent)
                parent_col = None
                if level_num > 0 and levels_created:
                    prev_col = levels_created[-1]["col"]
                    # Check if prev_col is a valid parent
                    try:
                        # Each value of current col should have <= 1 parent
                        check = _data_rows(data, f'''
                            SELECT "{col}", COUNT(DISTINCT "{prev_col}") as parent_count
                            FROM "{view_name}"
                            WHERE "{col}" IS NOT NULL AND "{col}" != ''
                            GROUP BY "{col}"
                            HAVING parent_count > 1
                            LIMIT 1
                        ''')
                        if not check:  # no multi-parent → valid hierarchy
                            parent_col = prev_col
                    except Exception:
                        pass

                # Create level
                label = col.replace("_", " ").title()
                keywords = [col.lower(), col.replace("_", " ").lower()]
                # Add Thai keywords for common columns
                thai_map = {
                    "division": ["สายงาน"], "department": ["ฝ่าย"],
                    "section": ["ส่วน"], "group": ["กลุ่ม", "กลุ่มงาน"],
                    "product_name": ["บริการ", "ผลิตภัณฑ์"], "service_group": ["กลุ่มบริการ"],
                    "business_group": ["กลุ่มธุรกิจ", "ธุรกิจ"],
                    "account_name": ["บัญชี", "ค่าใช้จ่าย"], "account_group_name": ["หมวด", "หมวดบัญชี"],
                    "gl_code": ["gl", "รหัสบัญชี"], "gl_name": ["ชื่อบัญชี"],
                    "organization_group": ["กลุ่มงาน"],
                }
                for key, thai_kws in thai_map.items():
                    if key in col.lower():
                        keywords.extend(thai_kws)

                conn.execute("""
                    INSERT INTO master_hierarchy
                        (context_name, level, level_label_th, level_label_en, level_columns,
                         detection_keywords, parent_column, source_view, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'auto')
                    ON CONFLICT(context_name, level) DO UPDATE SET
                        level_columns = excluded.level_columns,
                        detection_keywords = excluded.detection_keywords,
                        parent_column = excluded.parent_column,
                        source_view = excluded.source_view,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    context_name, level_num, label, label,
                    json.dumps([col], ensure_ascii=False),
                    json.dumps(keywords, ensure_ascii=False),
                    parent_col, view_name,
                ))

                levels_created.append({"level": level_num, "col": col, "distinct": col_info["distinct"], "parent": parent_col})
                used_cols.add(col)
                level_num += 1

                if level_num >= 4:  # max 4 levels
                    break

            conn.commit()

            # 5. Now extract values using the newly created levels
            extract_result = self.auto_extract(context_name)

            self._invalidate_cache()

            return {
                "context_name": context_name,
                "view": view_name,
                "levels_created": levels_created,
                "extract_result": extract_result,
            }
        finally:
            conn.close()

    def get_available_views(self) -> List[Dict]:
        """List views/tables that can be used for hierarchy extraction."""
        conn = _get_conn()
        try:
            # From schema_contexts
            views = []
            try:
                rows = conn.execute(
                    "SELECT name, main_view, display_name FROM schema_contexts WHERE is_active = 1"
                ).fetchall()
                for r in rows:
                    views.append({"context_name": r[0], "view_name": r[1], "display_name": r[2], "source": "schema_contexts"})
            except Exception:
                pass

            # Also list all views in the business DB (not the config DB)
            try:
                from sqlalchemy import inspect as sa_inspect
                from app.db.session import business_engine
                db_views = sorted(sa_inspect(business_engine).get_view_names())
                existing_view_names = {v["view_name"] for v in views}
                for name in db_views:
                    if name not in existing_view_names:
                        views.append({"context_name": name, "view_name": name, "display_name": name, "source": "database"})
            except Exception:
                pass

            return views
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Unmatched keyword logging (Phase 4)
    # ------------------------------------------------------------------

    def log_unmatched_keyword(self, keyword: str, context_name: str, question: str):
        """Log a keyword that was used in LIKE but has no alias match."""
        conn = _get_conn()
        try:
            # Ensure table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS unmatched_keywords (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword         TEXT NOT NULL,
                    context_name    TEXT NOT NULL,
                    occurrence_count INTEGER DEFAULT 1,
                    last_question   TEXT,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    resolved        BOOLEAN DEFAULT 0,
                    UNIQUE(keyword, context_name)
                )
            """)
            conn.execute("""
                INSERT INTO unmatched_keywords (keyword, context_name, last_question)
                VALUES (?, ?, ?)
                ON CONFLICT(keyword, context_name) DO UPDATE SET
                    occurrence_count = occurrence_count + 1,
                    last_question = excluded.last_question,
                    updated_at = CURRENT_TIMESTAMP
            """, (keyword.lower().strip(), context_name, question[:500]))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log unmatched keyword: {e}")
        finally:
            conn.close()

    def get_unmatched_keywords(self, context_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get unmatched keywords sorted by frequency."""
        conn = _get_conn()
        try:
            # Check if table exists
            try:
                conn.execute("SELECT 1 FROM unmatched_keywords LIMIT 1")
            except Exception:
                return []

            if context_name:
                rows = conn.execute(
                    "SELECT keyword, context_name, occurrence_count, last_question FROM unmatched_keywords "
                    "WHERE context_name = ? AND resolved = 0 ORDER BY occurrence_count DESC LIMIT ?",
                    (context_name, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT keyword, context_name, occurrence_count, last_question FROM unmatched_keywords "
                    "WHERE resolved = 0 ORDER BY occurrence_count DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [
                {"keyword": r[0], "context_name": r[1], "occurrence_count": r[2], "last_question": r[3]}
                for r in rows
            ]
        finally:
            conn.close()

    def resolve_unmatched_keyword(self, keyword: str, context_name: str):
        """Mark an unmatched keyword as resolved."""
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE unmatched_keywords SET resolved = 1 WHERE keyword = ? AND context_name = ?",
                (keyword, context_name))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    @staticmethod
    def _invalidate_cache():
        """Invalidate the in-memory hierarchy cache in ai_service."""
        try:
            from app.services.ai_service import _HIERARCHY_CACHE
            _HIERARCHY_CACHE.clear()
            logger.info("Hierarchy cache invalidated")
        except Exception:
            pass


# Singleton
hierarchy_service = HierarchyService()

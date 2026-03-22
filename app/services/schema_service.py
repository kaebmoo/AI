"""
NT AI Assistant - Schema Service
======================================
Service สำหรับจัดการ schema metadata และสร้าง system prompt สำหรับ AI

รองรับ:
- Claude API (Anthropic)
- Google AI / Gemini API

Enhanced Features (v2.0):
- Schema metadata from database
- Semantic mapping for abbreviations and business terms
- Business rules from database
- Database abstraction layer support (SQLAlchemy)
- **Multi-Context Support (Revenue, Expense, etc.)**
- **View Builder Support**: Create simplified SQL Views with AI-powered column mapping

Usage:
    schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
    prompt = schema_service.build_system_prompt(context_name="expense")
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import Session
import sqlite3
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class SchemaService:
    """Service สำหรับจัดการ schema metadata"""
    
    def __init__(self, db_engine: Optional[Engine] = None, db_path: str = None,
                 config_engine: Optional[Engine] = None, business_engine: Optional[Engine] = None):
        """
        Initialize SchemaService.

        If no engines provided, auto-imports from app.db.session (3-DB architecture).
        Explicit engines take priority for dependency injection and testing.

        Args:
            db_engine: Legacy param — used as config engine if config_engine not provided.
            db_path: Explicit DB path override (legacy, for scripts only).
            config_engine: Engine for config DB (schema_contexts, mappings, rules).
            business_engine: Engine for business DB (inspecting views/tables).
        """
        # Resolve engines: explicit params > auto-import from session > db_path fallback
        if config_engine or db_engine:
            self.engine = config_engine or db_engine
            self.config_engine = self.engine
        else:
            try:
                from app.db.session import config_engine as _auto_cfg
                self.engine = _auto_cfg
                self.config_engine = _auto_cfg
            except ImportError:
                # Standalone script without app context — use db_path
                _path = db_path or "nt_fi_report.sqlite"
                self.engine = create_engine(f"sqlite:///{_path}")
                self.config_engine = self.engine

        if business_engine:
            self.business_engine = business_engine
        else:
            try:
                from app.db.session import business_engine as _auto_biz
                self.business_engine = _auto_biz
            except ImportError:
                self.business_engine = self.engine

        self.db_path = db_path or "nt_fi_report.sqlite"
        self.metadata_db_path = self.db_path
        self._cache: Dict[str, Any] = {}
        self._context_cache: Dict[str, Dict] = {}

    def _get_connection(self) -> Connection:
        """Get business DB connection (for inspecting views/tables)"""
        return self.business_engine.connect()

    def _get_config_connection(self) -> Connection:
        """Get config DB connection (for schema_contexts, mappings, rules, etc.)"""
        return self.config_engine.connect()

    
    # =========================================================
    # Schema View Builder (Cross-Database)
    # =========================================================

    def get_all_tables(self) -> List[str]:
        """List all tables/views in the business database (excluding system tables)"""
        inspector = inspect(self.business_engine)
        tables = inspector.get_table_names()
        view_names = inspector.get_view_names()
        
        # Filter out system tables/views
        filtered = []
        all_objects = tables + view_names
        
        for name in all_objects:
            if name.startswith("sqlite_") or name.startswith("schema_"):
                continue
            filtered.append(name)
            
        return sorted(filtered)

    def create_custom_view(self, view_name: str, source_table: str, mapping: List[Dict[str, str]]) -> bool:
        """
        Create a SQL View from source table with column aliasing.
        After creation, saves column mappings and propagates metadata from source table.

        Args:
            view_name: Name of the view to create (e.g., 'v_sales_2024')
            source_table: Source table name
            mapping: List of dicts [{'col': 'original_col', 'alias': 'new_name'}]
        """
        # Validate inputs
        if not view_name.replace("_", "").isalnum():
             raise ValueError("Invalid view name")

        # Build SELECT clause
        select_parts = []
        for m in mapping:
            col = m['col']
            alias = m.get('alias')
            if alias and alias != col:
                select_parts.append(f'"{col}" AS "{alias}"')
            else:
                select_parts.append(f'"{col}"')

        select_clause = ", ".join(select_parts)

        # DDL Execution
        sql = f"CREATE VIEW {view_name} AS SELECT {select_clause} FROM {source_table}"

        # Views must be created in business DB (where source tables exist)
        with self.business_engine.begin() as conn:
            conn.execute(text(f"DROP VIEW IF EXISTS {view_name}"))
            conn.execute(text(sql))

        # Save column mappings and propagate metadata
        try:
            self.save_view_column_mappings(view_name, source_table, mapping)
            self.propagate_metadata_to_view(view_name)
        except Exception as e:
            logger.warning(f"View created but mapping/propagation failed: {e}")

        return True

    # =========================================================
    # View Column Mappings
    # =========================================================

    def list_views_with_mappings(self) -> List[Dict]:
        """List all views that have column mappings, with summary stats."""
        with self.engine.connect() as conn:
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
            except Exception as e:
                logger.warning(f"Failed to list views with mappings: {e}")
                return []

    def save_view_column_mappings(self, view_name: str, source_table: str, mappings: List[Dict[str, str]]) -> int:
        """
        Save column mappings for a view.
        Replaces any existing mappings for the view.

        Args:
            view_name: Name of the view
            source_table: Source table name
            mappings: List of dicts [{'col': 'SOURCE_COL', 'alias': 'view_col'}]

        Returns:
            Number of mappings saved
        """
        with self.engine.begin() as conn:
            # Delete existing mappings for this view
            conn.execute(
                text("DELETE FROM view_column_mappings WHERE view_name = :vn"),
                {"vn": view_name}
            )

            count = 0
            for m in mappings:
                source_col = m['col']
                view_col = m.get('alias') or source_col
                mapping_type = 'alias' if view_col != source_col else 'passthrough'

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

        logger.info(f"Saved {count} column mappings for view '{view_name}'")
        return count

    def get_view_column_mappings(self, view_name: str) -> List[Dict]:
        """Get all column mappings for a view."""
        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    text("SELECT * FROM view_column_mappings WHERE view_name = :vn ORDER BY id"),
                    {"vn": view_name}
                )
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception as e:
                logger.warning(f"Failed to get view column mappings: {e}")
                return []

    def _find_source_metadata(self, conn, source_table: str, source_column: str) -> Optional[Dict]:
        """
        Find metadata for a source column with chain resolution.
        If source_table has no metadata, try to find it through intermediate views.

        Chain: raw_table → intermediate_view → final_view
        If raw_table has no metadata but intermediate_view does, follow the chain.
        """
        # 1. Direct lookup
        result = conn.execute(text("""
            SELECT * FROM schema_metadata
            WHERE table_name = :st AND column_name = :sc
        """), {"st": source_table, "sc": source_column})
        row = result.mappings().fetchone()
        if row:
            return dict(row)

        # 2. Chain resolution: find views that map FROM source_table
        #    and check if THOSE views have metadata for the source_column
        try:
            result = conn.execute(text("""
                SELECT DISTINCT vcm2.view_name, vcm2.view_column
                FROM view_column_mappings vcm2
                WHERE vcm2.source_table = :st AND vcm2.source_column = :sc
            """), {"st": source_table, "sc": source_column})
            for chain_row in result.mappings().fetchall():
                chain_view = chain_row['view_name']
                chain_col = chain_row['view_column']
                meta_result = conn.execute(text("""
                    SELECT * FROM schema_metadata
                    WHERE table_name = :tv AND column_name = :tc
                    AND display_name_th IS NOT NULL AND display_name_th != ''
                """), {"tv": chain_view, "tc": chain_col})
                meta_row = meta_result.mappings().fetchone()
                if meta_row:
                    logger.info(f"Chain resolved: {source_table}.{source_column} → {chain_view}.{chain_col}")
                    return dict(meta_row)
        except Exception:
            pass

        # 3. Fallback: check if any view has metadata stored under the raw column name
        #    (handles legacy data where metadata was saved with raw column names under a view name)
        try:
            result = conn.execute(text("""
                SELECT * FROM schema_metadata
                WHERE column_name = :sc
                AND display_name_th IS NOT NULL AND display_name_th != ''
                AND table_name != :exclude
                ORDER BY table_name
                LIMIT 1
            """), {"sc": source_column, "exclude": source_table})
            row = result.mappings().fetchone()
            if row:
                logger.info(f"Fallback found: metadata for '{source_column}' from table '{row['table_name']}'")
                return dict(row)
        except Exception:
            pass

        return None

    def propagate_metadata_to_view(self, view_name: str) -> Dict:
        """
        Propagate metadata from source tables to a view using view_column_mappings.
        For each mapping: find source metadata (with chain resolution) → UPSERT schema_metadata row.

        Returns:
            Dict with 'created', 'updated', 'skipped', 'missing_columns' for diagnostics
        """
        mappings = self.get_view_column_mappings(view_name)
        if not mappings:
            logger.warning(f"No column mappings found for view '{view_name}'")
            return {"created": 0, "updated": 0, "skipped": 0, "missing_columns": []}

        created = 0
        updated = 0
        skipped = 0
        missing_columns = []

        with self.engine.begin() as conn:
            for m in mappings:
                source_table = m['source_table']
                source_column = m['source_column']
                view_column = m['view_column']

                # Find source metadata (with chain resolution)
                source_meta = self._find_source_metadata(conn, source_table, source_column)

                # Check if view metadata already exists
                result = conn.execute(text("""
                    SELECT id, display_name_th FROM schema_metadata
                    WHERE table_name = :vn AND column_name = :vc
                """), {"vn": view_name, "vc": view_column})
                existing = result.mappings().fetchone()

                if source_meta:
                    sm = source_meta
                    if existing:
                        # Update only if display_name_th is empty
                        if not existing['display_name_th']:
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
                                "display_name_th": sm.get('display_name_th'),
                                "display_name_en": sm.get('display_name_en'),
                                "description": sm.get('description'),
                                "data_type": sm.get('data_type'),
                                "is_summable": sm.get('is_summable', False),
                                "is_groupable": sm.get('is_groupable', True),
                                "hierarchy_level": sm.get('hierarchy_level'),
                                "special_notes": sm.get('special_notes'),
                                "conversion_sql": sm.get('conversion_sql'),
                                "dimension_group": sm.get('dimension_group'),
                                "updated_at": datetime.utcnow(),
                                "vn": view_name,
                                "vc": view_column,
                            })
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        # Insert new metadata row for the view
                        conn.execute(text("""
                            INSERT INTO schema_metadata (
                                table_name, column_name, display_name_th, display_name_en,
                                description, data_type, format_hint, example_value,
                                is_summable, is_groupable, hierarchy_level,
                                special_notes, conversion_sql, dimension_group
                            ) VALUES (
                                :table_name, :column_name, :display_name_th, :display_name_en,
                                :description, :data_type, :format_hint, :example_value,
                                :is_summable, :is_groupable, :hierarchy_level,
                                :special_notes, :conversion_sql, :dimension_group
                            )
                        """), {
                            "table_name": view_name,
                            "column_name": view_column,
                            "display_name_th": sm.get('display_name_th'),
                            "display_name_en": sm.get('display_name_en'),
                            "description": sm.get('description'),
                            "data_type": sm.get('data_type'),
                            "format_hint": sm.get('format_hint'),
                            "example_value": sm.get('example_value'),
                            "is_summable": sm.get('is_summable', False),
                            "is_groupable": sm.get('is_groupable', True),
                            "hierarchy_level": sm.get('hierarchy_level'),
                            "special_notes": sm.get('special_notes'),
                            "conversion_sql": sm.get('conversion_sql'),
                            "dimension_group": sm.get('dimension_group'),
                        })
                        created += 1
                else:
                    # No source metadata found anywhere
                    missing_columns.append({
                        "view_column": view_column,
                        "source_table": source_table,
                        "source_column": source_column,
                    })
                    if not existing:
                        # Create minimal row so the column appears
                        conn.execute(text("""
                            INSERT INTO schema_metadata (table_name, column_name, data_type)
                            VALUES (:table_name, :column_name, :data_type)
                        """), {
                            "table_name": view_name,
                            "column_name": view_column,
                            "data_type": "TEXT",
                        })
                        created += 1

        logger.info(
            f"Propagated metadata to '{view_name}': "
            f"{created} created, {updated} updated, {skipped} skipped, "
            f"{len(missing_columns)} missing source"
        )
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "missing_columns": missing_columns,
        }

    # =========================================================
    # Context Management
    # =========================================================

    def get_context_info(self, context_name: str) -> Optional[Dict]:
        """Get context information from schema_contexts table

        Handles name normalization: 'transfer_price' matches 'transfer price' and vice versa
        """
        if context_name in self._context_cache:
            return self._context_cache[context_name]

        with self.engine.connect() as conn:
            try:
                # Try exact match first
                result = conn.execute(
                    text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                    {"name": context_name}
                )
                row = result.mappings().fetchone()

                # If not found, try with underscore <-> space normalization
                if not row:
                    # Try underscore to space (e.g., 'transfer_price' -> 'transfer price')
                    alt_name = context_name.replace('_', ' ')
                    if alt_name != context_name:
                        result = conn.execute(
                            text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                            {"name": alt_name}
                        )
                        row = result.mappings().fetchone()

                if not row:
                    # Try space to underscore (e.g., 'transfer price' -> 'transfer_price')
                    alt_name = context_name.replace(' ', '_')
                    if alt_name != context_name:
                        result = conn.execute(
                            text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                            {"name": alt_name}
                        )
                        row = result.mappings().fetchone()
                
                if row:
                    context_info = dict(row)
                    if context_info.get('keywords') and isinstance(context_info['keywords'], str):
                        try:
                            context_info['keywords'] = json.loads(context_info['keywords'])
                        except:
                            context_info['keywords'] = []
                            
                    self._context_cache[context_name] = context_info
                    return context_info
                
                # Context not found in DB
                logger.warning(f"Context '{context_name}' not found in schema_contexts table")
                return None

            except Exception as e:
                logger.warning(f"Failed to query schema_contexts: {e}")
                return None


    def get_all_contexts(self) -> List[Dict]:
        """Get all active contexts"""
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text("SELECT * FROM schema_contexts WHERE is_active = 1 ORDER BY priority DESC"))
                contexts = []
                for row in result.mappings().fetchall():
                    ctx = dict(row)
                    if ctx.get('keywords') and isinstance(ctx['keywords'], str):
                        try:
                            ctx['keywords'] = json.loads(ctx['keywords'])
                        except:
                            ctx['keywords'] = []
                    contexts.append(ctx)
                return contexts
            except Exception as e:
                logger.warning(f"Failed to query schema_contexts: {e}")
                return []

    def create_context(self, data: Dict) -> Dict:
        """Create new context"""
        with self.engine.begin() as conn:
            # Prepare columns
            columns = ['name', 'display_name', 'description', 'main_view', 'is_active', 'priority', 'keywords', 'instruction_th', 'instruction_en']
            placeholders = ', '.join([f":{col}" for col in columns])
            sql = f"INSERT INTO schema_contexts ({', '.join(columns)}) VALUES ({placeholders})"
            
            # Serialize keywords
            params = data.copy()
            if params.get('keywords'):
                params['keywords'] = json.dumps(params['keywords'], ensure_ascii=False)
                
            cursor = conn.execute(text(sql), params)
            context_id = cursor.lastrowid
            
            # Fetch created
            result = conn.execute(text("SELECT * FROM schema_contexts WHERE id = :id"), {"id": context_id})
            row = dict(result.mappings().fetchone())
            
            # Load Keywords JSON
            if row.get('keywords'):
                try:
                    row['keywords'] = json.loads(row['keywords'])
                except:
                    row['keywords'] = []
            
            self.refresh_context_cache()
            return row

    def update_context(self, context_id: int, data: Dict) -> Optional[Dict]:
        """Update existing context"""
        with self.engine.begin() as conn:
            set_parts = []
            params = data.copy()
            params['id'] = context_id
            
            for key, value in data.items():
                if key == 'keywords':
                    params['keywords'] = json.dumps(value, ensure_ascii=False)
                set_parts.append(f"{key} = :{key}")
                
            params['updated_at'] = datetime.utcnow()
            set_parts.append("updated_at = :updated_at")

            sql = f"UPDATE schema_contexts SET {', '.join(set_parts)} WHERE id = :id"
            
            cursor = conn.execute(text(sql), params)
            
            if cursor.rowcount == 0:
                return None
                
            result = conn.execute(text("SELECT * FROM schema_contexts WHERE id = :id"), {"id": context_id})
            row = dict(result.mappings().fetchone())
            
            if row.get('keywords'):
                try:
                    row['keywords'] = json.loads(row['keywords'])
                except:
                    row['keywords'] = []
            
            self.refresh_context_cache()
            return row

    def delete_context(self, context_id: int):
        """Delete context"""
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM schema_contexts WHERE id = :id"), {"id": context_id})
            self.refresh_context_cache()

    def refresh_context_cache(self):
        """Force reload of context cache"""
        self._context_cache.clear()


    # =========================================================
    # Schema Information Methods
    # =========================================================
    
    def get_table_info(self, table_name: str) -> List[Dict]:
        """Get column information from DB Inspector"""
        inspector = inspect(self.business_engine)
        columns = inspector.get_columns(table_name)
        # Standardize return format {'name': 'x', 'type': 'y'}
        return [{'name': col['name'], 'type': str(col['type'])} for col in columns]
    
    def get_schema_metadata(self, table_name: str) -> List[Dict]:
        """Get schema metadata from metadata table"""
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text("""
                    SELECT * FROM schema_metadata 
                    WHERE table_name = :table_name
                    ORDER BY 
                        CASE column_name
                            WHEN 'YEAR' THEN 1
                            WHEN 'MONTH' THEN 2
                            WHEN 'DATE' THEN 3
                            WHEN 'REVENUE_VALUE' THEN 4
                            WHEN 'AMOUNT' THEN 5
                            WHEN 'expense' THEN 6
                            ELSE 10
                        END,
                        column_name
                """), {"table_name": table_name})
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception:
                return []
    
    def get_business_rules(self, table_name: str, inject_mode: str = None) -> List[Dict]:
        """Get business rules from schema_business_rules table

        Args:
            table_name: View/table name to filter rules for
            inject_mode: Optional filter - 'schema_context' or 'instruction'
        """
        with self.engine.connect() as conn:
            try:
                query = """
                    SELECT * FROM schema_business_rules
                    WHERE is_active = 1
                    AND (table_name = :table_name OR table_name = 'ALL' OR table_name IS NULL)
                """
                params = {"table_name": table_name}

                if inject_mode:
                    query += " AND (inject_mode = :inject_mode OR inject_mode IS NULL)"
                    params["inject_mode"] = inject_mode

                query += """
                    ORDER BY
                        CASE severity
                            WHEN 'error' THEN 1
                            WHEN 'warning' THEN 2
                            ELSE 3
                        END,
                        rule_code
                """

                result = conn.execute(text(query), params)
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception:
                return []

    def build_hierarchy_rule_text(self, context_name: str) -> str:
        """Build hierarchy rule text dynamically from master_hierarchy table.

        Returns a prompt section like:
        STEP 1.5: HIERARCHY RULE (ห้าม OR ข้ามระดับ)
        - ข้อมูลมีลำดับชั้น: กลุ่มธุรกิจ > กลุ่มบริการ > บริการ/ผลิตภัณฑ์
        ...
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT level_label_th, level_columns
                    FROM master_hierarchy
                    WHERE context_name = :ctx AND is_active = 1
                    ORDER BY level
                """), {"ctx": context_name})
                rows = result.fetchall()

            if not rows:
                return ""

            hierarchy_chain = " > ".join(r[0] for r in rows)
            # Get first column from each level for the example
            import json as _json
            example_cols = []
            for r in rows:
                try:
                    cols = _json.loads(r[1])
                    if cols:
                        example_cols.append(cols[0].lower())
                except (ValueError, IndexError):
                    pass

            text_parts = [
                "STEP 1.5: HIERARCHY RULE (ห้าม OR ข้ามระดับ)",
                f"- ข้อมูลมีลำดับชั้น: {hierarchy_chain}",
                "- ถ้า Actual Values มีข้อมูลจากหลาย level → ใช้เฉพาะ level ที่ user ถามถึง",
            ]

            if len(example_cols) >= 2:
                col_a, col_b = example_cols[0], example_cols[1]
                text_parts.append(
                    f"- ห้าม: WHERE {col_a} LIKE '%x%' OR {col_b} LIKE '%x%' (OR ข้ามระดับ)"
                )

            text_parts.append("- การ OR ข้ามระดับทำให้ตัวเลขผิดเพี้ยนอย่างมาก (สูงเกินจริงหลายสิบเท่า)")
            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"build_hierarchy_rule_text error: {e}")
            # Fallback to generic rule
            return """STEP 1.5: HIERARCHY RULE (ห้าม OR ข้ามระดับ)
- ถ้า Actual Values มีข้อมูลจากหลาย level → ใช้เฉพาะ level ที่ user ถามถึง
- ห้าม OR ข้ามระดับ — ทำให้ตัวเลขผิดเพี้ยนอย่างมาก"""

    def build_instruction_rules_text(self, main_view: str) -> str:
        """Build instruction section rules from DB (context_retention, unit_conversion, etc.)"""
        rules = self.get_business_rules(main_view, inject_mode='instruction')
        if not rules:
            return ""

        sections = {}
        for rule in rules:
            category = rule.get('rule_category', 'other')
            if category not in sections:
                sections[category] = []
            sections[category].append(rule['rule_description'])

        text = ""
        # Context retention rules get a header
        if 'context_retention' in sections:
            text += "\n## กฎการรักษาบริบท (Context Retention Rules)\n"
            text += "**หลักการสำคัญ:** แยกระหว่าง REPLACE vs MERGE\n\n"
            for desc in sections['context_retention']:
                text += f"{desc}\n\n"
            del sections['context_retention']

        # Other sections
        for category, descs in sections.items():
            for desc in descs:
                text += f"\n{desc}\n"

        return text

    def get_dimension_families(self, table_name: str) -> Dict[str, List[str]]:
        """Get dimension families — groups of related columns that must stay on the same axis.

        Uses hybrid resolution:
          1. DB overrides (admin-set) win
          2. Auto-detect fills gaps for unassigned columns
          3. Only returns groups with 2+ members

        Returns:
            Dict mapping group name to list of column names, e.g.
            {'org_section': ['SECTION', 'SECTION_ABBR'], ...}
        """
        from app.services.dimension_detector import detect_families

        # 1. Query DB overrides
        db_families: Dict[str, List[str]] = {}
        db_assigned_cols: set = set()
        with self.engine.connect() as conn:
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
                    col = row["column_name"]
                    db_families.setdefault(group, []).append(col)
                    db_assigned_cols.add(col)
            except Exception:
                pass

        # 2. Get all column names and auto-detect
        try:
            columns = self.get_table_info(table_name)
            all_col_names = [c["name"] for c in columns]
        except Exception:
            all_col_names = []

        auto_families = detect_families(all_col_names) if all_col_names else {}

        # 3. Merge: DB wins, auto-detect fills gaps
        merged: Dict[str, List[str]] = {}

        # Start with DB families
        for group, cols in db_families.items():
            merged[group] = list(cols)

        # Add auto-detected families for columns NOT already assigned in DB
        for group, cols in auto_families.items():
            unassigned = [c for c in cols if c not in db_assigned_cols]
            if unassigned:
                merged.setdefault(group, []).extend(unassigned)

        # Only return groups with 2+ members
        return {g: cols for g, cols in merged.items() if len(cols) >= 2}

    def get_dimension_families_with_source(self, table_name: str) -> List[Dict]:
        """Get dimension families with source tracking (db/auto).

        Returns list of {family_name, columns: [{column_name, source}]}.
        """
        from app.services.dimension_detector import detect_families

        # DB overrides
        db_map: Dict[str, str] = {}  # column_name → dimension_group
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text("""
                    SELECT dimension_group, column_name
                    FROM schema_metadata
                    WHERE table_name = :table_name
                      AND dimension_group IS NOT NULL
                """), {"table_name": table_name})
                for row in result.mappings().fetchall():
                    db_map[row["column_name"]] = row["dimension_group"]
            except Exception:
                pass

        # Auto-detect
        try:
            columns = self.get_table_info(table_name)
            all_col_names = [c["name"] for c in columns]
        except Exception:
            all_col_names = []

        auto_families = detect_families(all_col_names) if all_col_names else {}

        # Build merged result with source tracking
        families: Dict[str, List[Dict]] = {}

        # DB columns first
        for col, group in db_map.items():
            families.setdefault(group, []).append({"column_name": col, "source": "db"})

        # Auto-detect for unassigned columns
        for group, cols in auto_families.items():
            for col in cols:
                if col not in db_map:
                    families.setdefault(group, []).append({"column_name": col, "source": "auto"})

        # Build response list, filter 2+ members
        result = []
        for family_name, columns in sorted(families.items()):
            if len(columns) >= 2:
                source = "db" if all(c["source"] == "db" for c in columns) else \
                         "auto" if all(c["source"] == "auto" for c in columns) else "mixed"
                result.append({
                    "family_name": family_name,
                    "columns": sorted(columns, key=lambda c: c["column_name"]),
                    "source": source,
                })

        return result

    def get_semantic_mappings(
        self,
        keyword_type: Optional[str] = None,
        context_name: Optional[str] = None
    ) -> List[Dict]:
        """Get semantic mappings from schema_semantic_mapping table.

        Filtering logic:
          - context_name=None  → return global (NULL) mappings only (default for admin list)
          - context_name='all' → return all mappings regardless of context
          - context_name='revenue' → return global (NULL) + 'revenue'-scoped mappings
        """
        with self.engine.connect() as conn:
            try:
                conditions = ["is_active = 1"]
                params: dict = {}

                if keyword_type:
                    conditions.append("keyword_type = :keyword_type")
                    params["keyword_type"] = keyword_type

                if context_name and context_name != "all":
                    # Include global mappings (NULL) + mappings scoped to this context
                    conditions.append("(context_name IS NULL OR context_name = :context_name)")
                    params["context_name"] = context_name
                elif context_name is None:
                    # Default: admin list — return all (no context filter)
                    pass  # no extra condition

                where_clause = " AND ".join(conditions)
                result = conn.execute(
                    text(f"SELECT * FROM schema_semantic_mapping WHERE {where_clause} ORDER BY priority DESC, keyword"),
                    params
                )
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception:
                return []
    
    def get_sample_values(self, table_name: str) -> Dict[str, List[str]]:
        """Get sample values for important columns"""
        samples = {}
        inspector = inspect(self.business_engine)
        
        # Get actual columns first
        try:
            actual_cols = set(col['name'] for col in inspector.get_columns(table_name))
        except:
            return {}

        # Default columns to try
        columns_to_try = [
            'business_unit', 'division', 'department', 'SERVICE_GROUP',
            'BUSINESS_GROUP', 'business_group', 'PRODUCT_NAME',
            'account_group_name', 'account_name', 'gl_name'
        ]
        
        with self.engine.connect() as conn:
            for col_name in columns_to_try:
                # Find matching column (case-insensitive check might be needed for some DBs)
                # For now assume exact match or simple case variant
                matching_col = next((c for c in actual_cols if c.upper() == col_name.upper()), None)
                
                if matching_col:
                    try:
                        sql = text(f"SELECT DISTINCT {matching_col} FROM {table_name} WHERE {matching_col} IS NOT NULL LIMIT 20")
                        result = conn.execute(sql)
                        samples[col_name] = [row[0] for row in result.fetchall()]
                    except Exception:
                        pass
        
            # Get data range
            try:
                sql = text(f"""
                    SELECT 
                        MIN(year) as min_year,
                        MAX(year) as max_year,
                        MIN(CAST(month AS INTEGER)) as min_month,
                        MAX(CAST(month AS INTEGER)) as max_month
                    FROM {table_name}
                """)
                result = conn.execute(sql)
                row = result.mappings().fetchone()
                if row:
                    samples['DATA_RANGE'] = {
                        'min_year': row['min_year'],
                        'max_year': row['max_year'],
                        'min_month': row['min_month'],
                        'max_month': row['max_month']
                    }
            except Exception:
                pass
        
        return samples
    
    def get_date_format(self, table_name: str = "revenue_search") -> str:
        """Detect DATE column format (TEXT or INTEGER)"""
        return "year_month_only"
    
    # =========================================================
    # Prompt Building Methods
    # =========================================================
    
    def build_schema_text(self, table_name: str) -> str:
        """Build schema information text for AI prompt"""
        
        # Try to get from metadata table first
        metadata = self.get_schema_metadata(table_name)
        
        if metadata:
            return self._build_schema_from_metadata(metadata, table_name)
        else:
            # Fallback to PRAGMA
            return self._build_schema_from_pragma(table_name)
    
    def _build_schema_from_metadata(self, metadata: List[Dict], table_name: str) -> str:
        """Build schema text from metadata table"""
        
        text = f"## Table: {table_name}\n\n"
        text += "| Column | Type | ชื่อไทย | SUM? | GROUP BY? | หมายเหตุ |\n"
        text += "|--------|------|---------|------|-----------|----------|\n"
        
        for col in metadata:
            can_sum = "✅" if col.get('is_summable') else "❌"
            can_group = "✅" if col.get('is_groupable') else "❌"
            notes = col.get('special_notes') or ""
            if col.get('conversion_sql'):
                notes += f" แปลงด้วย: `{col['conversion_sql']}`"
            
            text += f"| {col['column_name']} | {col.get('data_type', 'TEXT')} | "
            text += f"{col.get('display_name_th', '')} | {can_sum} | {can_group} | {notes} |\n"
        
        return text
    
    def _build_schema_from_pragma(self, table_name: str) -> str:
        """Build schema text from SQLite PRAGMA (fallback)"""
        
        columns = self.get_table_info(table_name)
        
        text = f"## Table: {table_name}\n\n"
        text += "| Column | Type |\n"
        text += "|--------|------|\n"
        
        for col in columns:
            text += f"| {col['name']} | {col['type']} |\n"
        
        return text
    
    def build_business_rules_text(self, table_name: str) -> str:
        """Build business rules text for AI prompt (schema_context rules only)"""

        rules = self.get_business_rules(table_name, inject_mode='schema_context')
        
        if not rules:
            return self._get_default_business_rules()
        
        text = "## Business Rules\n\n"
        
        for rule in rules:
            severity_icon = {
                'error': '🚫',
                'warning': '⚠️',
                'info': 'ℹ️'
            }.get(rule.get('severity', 'info'), 'ℹ️')
            
            text += f"### {severity_icon} {rule['rule_name']}\n"
            text += f"{rule['rule_description']}\n\n"
            
            if rule.get('example_correct'):
                text += f"✅ **Correct:**\n```sql\n{rule['example_correct']}\n```\n\n"
            
            if rule.get('example_wrong'):
                text += f"❌ **Wrong:**\n```sql\n{rule['example_wrong']}\n```\n\n"
        
        return text
    
    def _get_default_business_rules(self) -> str:
        """Get default business rules if metadata table doesn't exist"""
        
        return """## Business Rules

### ⚠️ DATE Column Conversion
DATE เก็บเป็น Unix Timestamp (milliseconds) ต้องแปลงก่อนแสดงผล

### ⚠️ Thai Year Conversion
ปี พ.ศ. = ปี ค.ศ. + 543

### ℹ️ Common Abbreviations (คำย่อหน่วยงาน)
- **นป.** = `กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ`
- **บชง.** = `ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ`
"""
    
    def build_sample_values_text(self, table_name: str) -> str:
        """Build sample values text for AI prompt"""

        samples = self.get_sample_values(table_name)

        text = "## Available Values\n\n"

        if 'DATA_RANGE' in samples:
            dr = samples['DATA_RANGE']
            text += f"**Data Range:** {dr.get('min_year')}/{dr.get('min_month')} - {dr.get('max_year')}/{dr.get('max_month')}\n\n"

        for col, values in samples.items():
            if col == 'DATA_RANGE':
                continue
            if values:
                text += f"**{col}:**\n"
                for v in values[:10]:  # Limit to 10
                    text += f"- {v}\n"
                if len(values) > 10:
                    text += f"- ... และอื่นๆ อีก {len(values) - 10} รายการ\n"
                text += "\n"

        return text

    def build_semantic_mapping_text(self, context_name: Optional[str] = None) -> str:
        """Build semantic mapping text for AI prompt.

        Pass context_name so only relevant mappings are included:
          - global (NULL) mappings always included
          - context-scoped mappings only included when context matches
        """
        mappings = self.get_semantic_mappings(context_name=context_name)

        if not mappings:
            return self._get_default_semantic_mappings()

        text = "<semantic_mappings>\n"
        text += "## 🔥 SEMANTIC MAPPINGS - REFERENCE GUIDE 🔥\n\n"

        text += "<rules>\n"
        text += "1. ตรวจสอบ mappings ด้านล่างก่อนสร้าง SQL ทุกครั้ง\n"
        text += "2. ถ้าเจอ keyword → ใช้ mapping เป็น **reference** สำหรับหา column ที่ถูกต้อง\n"
        text += "3. ⚠️ ถ้ามี 'Actual Values Found' section → **ให้เชื่อค่าจาก Actual Values** เพราะมาจาก DB จริง\n"
        text += "4. สำหรับ text columns: ใช้ LIKE '%keyword%' เสมอ ยกเว้น mapping ระบุ LIKE pattern ไว้แล้ว\n"
        text += "</rules>\n\n"

        text += "<examples>\n"
        text += "✅ CORRECT:\n"
        text += "User: \"trunk radio\"\n"
        text += "SQL: WHERE (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')\n\n"

        text += "❌ WRONG (DO NOT DO THIS):\n"
        text += "User: \"trunk radio\"\n"
        text += "SQL: WHERE UPPER(product_name) LIKE '%TRUNK RADIO%'\n"
        text += "     OR UPPER(product_name) LIKE '%TRUNKED RADIO%'\n"
        text += "Reason: ห้ามสร้าง pattern เอง ต้องใช้ mapping ที่มีอยู่\n"
        text += "</examples>\n\n"

        # Group by keyword_type
        abbreviations = [m for m in mappings if m.get('keyword_type') == 'abbreviation']
        terms = [m for m in mappings if m.get('keyword_type') == 'term']
        synonyms = [m for m in mappings if m.get('keyword_type') == 'synonym']

        if abbreviations:
            text += "### คำย่อหน่วยงาน (Abbreviations)\n"
            text += "| คำย่อ | SQL Condition | ความหมาย |\n"
            text += "|-------|---------------|----------|\n"
            for m in abbreviations:
                # Use full_condition if available, otherwise combine target_column + target_condition
                condition = m.get('full_condition') or f"{m['target_column']} {m['target_condition']}"
                text += f"| {m['keyword']} | `{condition}` | {m.get('description', '')} |\n"
            text += "\n"

        if terms:
            text += "### คำศัพท์ธุรกิจ (Business Terms)\n"
            text += "| คำค้น | SQL Condition | ความหมาย |\n"
            text += "|-------|---------------|----------|\n"
            for m in terms:
                # Use full_condition if available, otherwise combine target_column + target_condition
                condition = m.get('full_condition') or f"{m['target_column']} {m['target_condition']}"
                text += f"| {m['keyword']} | `{condition}` | {m.get('description', '')} |\n"
            text += "\n"

        if synonyms:
            text += "### คำพ้องความหมาย (Synonyms) - MUST USE EXACTLY AS SHOWN\n"
            text += "<synonym_mappings>\n"
            for m in synonyms:
                # Use full_condition if available, otherwise combine target_column + target_condition
                if m.get('full_condition'):
                    condition = m['full_condition']
                else:
                    condition = f"{m['target_column']} {m['target_condition']}"

                text += f"<mapping keyword=\"{m['keyword']}\">\n"
                text += f"  SQL: {condition}\n"
                text += f"  Note: {m.get('description', 'N/A')}\n"
                text += f"</mapping>\n"
            text += "</synonym_mappings>\n\n"

        text += "</semantic_mappings>\n\n"
        text += "<reminder>\n"
        text += "⚠️ ก่อนสร้าง WHERE clause ทุกครั้ง:\n"
        text += "1. ถ้ามี 'Actual Values Found' → ใช้ค่าจากนั้นเป็นหลัก (มาจาก DB จริง)\n"
        text += "2. หา keyword ที่ user ใช้ใน <semantic_mappings> เพื่อหา column ที่ถูกต้อง\n"
        text += "3. สำหรับ text columns: ใช้ LIKE '%keyword%' เสมอ\n"
        text += "</reminder>\n"

        return text

    def _get_default_semantic_mappings(self) -> str:
        """Get default semantic mappings if table doesn't exist"""
        return """## Semantic Mappings
- **นป.** → `organization_group_abbr = 'นป.'`
- **บชง.** → `department_abbr = 'บชง.'`
- **Broadband** → `SERVICE_GROUP = 'กลุ่มบริการ Internet Retail'`
- **Mobile** → `BUSINESS_GROUP = 'Mobile'`
"""
    
    def get_schema_context(
        self, 
        context_name: str = "revenue", 
        include_samples: bool = True, 
        include_semantic_mappings: bool = True,
        lite_mode: bool = False
    ) -> str:
        """Get schema context (Schema + Rules + Semantic Mappings + Samples)"""
        
        # 1. Get Context Info
        context_info = self.get_context_info(context_name)
        if not context_info:
            import logging
            logging.getLogger(__name__).error(
                f"get_schema_context: Context '{context_name}' not found in schema_contexts — returning empty context"
            )
            return f"# ERROR: Context '{context_name}' not configured in database.\n"

        main_view = context_info['main_view']
        display_name = context_info.get('display_name', context_name)

        # 2. Build Components
        context = f"# Context: {display_name} ({context_name})\n"
        context += self.build_schema_text(table_name=main_view)
        context += "\n\n" + self.build_business_rules_text(table_name=main_view)

        # In Lite Mode (RAG Enabled), we skip heavy static samples
        # BUT we MUST ALWAYS keep semantic mappings (critical rules) and DATA_RANGE
        if not lite_mode:
            # Full Mode: Include everything
            if include_semantic_mappings:
                context += "\n\n" + self.build_semantic_mapping_text(context_name=context_name)

            if include_samples:
                context += "\n\n" + self.build_sample_values_text(table_name=main_view)
        else:
            # Lite Mode: ALWAYS include semantic mappings (they are rules, not data)
            # Only skip the heavy sample values list
            if include_semantic_mappings:
                context += "\n\n" + self.build_semantic_mapping_text(context_name=context_name)

            # Inject ONLY Data Range (skip detailed sample values)
            samples = self.get_sample_values(table_name=main_view)
            if 'DATA_RANGE' in samples:
                dr = samples['DATA_RANGE']
                context += f"\n\n## Available Values\n**Data Range:** {dr.get('min_year')}/{dr.get('min_month')} - {dr.get('max_year')}/{dr.get('max_month')}\n"

            context += "\n(Detailed sample values omitted for RAG optimization - relevant items will be injected)"

        date_format = self.get_date_format(main_view)
        context += "\n\n" + self._get_date_instructions(date_format)

        context += f"\n\n## Current Date\nวันที่ปัจจุบัน: {datetime.now().strftime('%Y-%m-%d')}\n"
        context += f"ปี พ.ศ. ปัจจุบัน: {datetime.now().year + 543}\n"

        return context

    def build_system_prompt(
        self,
        ai_provider: str = "claude",
        include_samples: bool = True,
        language: str = "thai",
        context_name: str = "revenue",
        rag_enabled: bool = False
    ) -> str:
        """
        Build complete system prompt for AI.
        Results are cached in-memory keyed by (provider, context, language, rag_enabled).
        Cache is invalidated on refresh_cache() or after 6 hours.
        """
        import time as _time
        cache_key = f"prompt|{ai_provider}|{context_name}|{language}|{include_samples}|{rag_enabled}"
        cached = self._cache.get(cache_key)
        if cached and (_time.time() - cached.get("_ts", 0)) < 21600:  # 6 hours
            logger.debug(f"System prompt cache HIT: {cache_key}")
            return cached["value"]

        # 1. Get Context Info
        context_info = self.get_context_info(context_name)
        if not context_info:
            import logging
            logging.getLogger(__name__).error(f"Context '{context_name}' not found in schema_contexts — cannot build prompt")
            # Return minimal prompt with error
            return f"ERROR: Context '{context_name}' not configured in database. Please add it via Admin UI."
        
        main_view = context_info['main_view']
        
        # 2. Build Instruction based on context
        if language == "thai":
            instruction = self._build_thai_prompt(ai_provider, main_view, context_name, context_info)
        else:
            instruction = self._build_english_prompt(ai_provider, main_view, context_name, context_info)
        
        # 3. Build Context (Schema, Rules, etc.)
        # Optimization: Use lite_mode if rag_enabled
        # This keeps the Table Schema (Critical) but drops the huge static lists
        context_text = self.get_schema_context(
            context_name=context_name, 
            include_samples=include_samples, 
            lite_mode=rag_enabled
        )
        
        import time as _time
        result = f"{instruction}\n\n{context_text}"
        self._cache[cache_key] = {"value": result, "_ts": _time.time()}
        logger.debug(f"System prompt cached: {cache_key} ({len(result)} chars)")
        return result
    
    def get_default_instruction(self, ai_provider: str = "claude", language: str = "thai", context_name: str = "revenue") -> str:
        """Get default system instruction without schema context"""
        context_info = self.get_context_info(context_name)
        if not context_info:
            import logging
            logging.getLogger(__name__).error(
                f"get_default_instruction: Context '{context_name}' not found in schema_contexts"
            )
            return f"ERROR: Context '{context_name}' not configured in database."
        main_view = context_info['main_view']

        if language == "thai":
            return self._build_thai_prompt(ai_provider, main_view, context_name, context_info)
        else:
            return self._build_english_prompt(ai_provider, main_view, context_name, context_info)
            
    def _get_syntax_rules(self, language: str = "thai") -> str:
        """Get database-specific syntax rules"""
        if self.engine and self.engine.name == "postgresql":
            if language == "thai":
                return """   **. PostgreSQL Syntax:**
       - ใช้ `CONCAT(a, b)` หรือ `a || b` ได้
       - การจัดรูปแบบวันที่ใช้ `to_char(date, 'YYYY-MM')`
       - การแปลงชนิดข้อมูลใช้ `::integer` หรือ `CAST(col AS INTEGER)`"""
            else:
                return """   **. PostgreSQL Syntax:**
       - Use `CONCAT(a, b)` or `a || b`
       - Date formatting: `to_char(date, 'YYYY-MM')`
       - Type casting: `::integer` or `CAST(col AS INTEGER)`"""
               
        else: # Default to sqlite
            if language == "thai":
                return """   **. SQLite Syntax:**
       - ห้ามใช้ `CONCAT(a, b)` -> ให้ใช้ `a || b` แทน
       - ห้ามใช้ `LPAD` -> ให้ใช้ `printf('%02d', CAST(col AS INTEGER))`
       - ห้ามใช้ `DATE_FORMAT` -> ให้ใช้ `strftime`"""
            else:
                return """   **. SQLite Syntax:**
       - NO `CONCAT(a, b)` -> Use `a || b` instead
       - NO `LPAD` -> Use `printf('%02d', CAST(col AS INTEGER))`
       - NO `DATE_FORMAT` -> Use `strftime`"""

    def _build_thai_prompt(self, ai_provider: str, main_view: str, context_name: str, context_info: Dict = {}) -> str:
        """Build Thai language system prompt — DB-driven sections"""

        syntax_rules = self._get_syntax_rules("thai")

        # Context specific instructions — DB-driven from schema_contexts.instruction_th
        context_instructions = context_info.get('instruction_th') or ""

        # Hierarchy rule — generated from master_hierarchy
        hierarchy_rule = self.build_hierarchy_rule_text(context_name)

        # Instruction rules from DB (context_retention, unit_conversion, response_format)
        instruction_rules = self.build_instruction_rules_text(main_view)

        return f"""<system>
คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูลของ NT (National Telecom)
บริบทปัจจุบัน: **{context_name.upper()}** (ตาราง: `{main_view}`)

<critical_instructions>
⚠️⚠️⚠️ MUST READ BEFORE GENERATING SQL ⚠️⚠️⚠️

STEP 1: CHECK FOR ACTUAL VALUES FIRST
- ถ้ามี "Actual Values Found" section ใน user message → ใช้ค่าจากนั้น (มาจาก DB จริง)
- ใช้ LIKE '%keyword%' สำหรับ text columns เสมอ

{hierarchy_rule}

STEP 2: CHECK SEMANTIC MAPPINGS
- ถ้าไม่มี Actual Values → ตรวจ <semantic_mappings> section
- ใช้ mapping เป็น reference สำหรับหา column ที่ถูกต้อง
- สำหรับ text columns: แปลง = เป็น LIKE '%keyword%' เสมอ

STEP 3: FALLBACK
- ถ้าไม่มี Actual Values และไม่มี mapping → สร้าง LIKE pattern เอง
- ห้ามใช้ = กับ text columns ยกเว้นมั่นใจ 100% ว่าค่าตรงเป๊ะ
</critical_instructions>

## หน้าที่ของคุณ
1. รับคำถามภาษาไทย/อังกฤษ เกี่ยวกับ `{context_name}`
2. ตรวจสอบ <semantic_mappings> ก่อนเสมอ
3. สร้าง SQL Query โดยใช้ mapping ที่กำหนดไว้
4. อธิบายผลลัพธ์เป็นภาษาไทย

## กฎการสร้าง SQL
1. ใช้ SQLite syntax เท่านั้น
2. ใช้ query จาก table/view: **{main_view}**
3. Column ทั้งหมดเป็นภาษาอังกฤษ (ดู Schema ด้านล่าง)
4. การค้นหาข้อความ (Text Search):
   - **กฎการค้นหา:** ห้ามใช้ `=` กับชื่อไทย (เช่น account_name, department) ยกเว้นมั่นใจ 100%
   - **ให้ใช้ `LIKE '%keyword%'` เสมอ** สำหรับคำค้นทั่วไป
   - ตัวอย่าง: User หา "ค่าล่วงเวลา" -> `WHERE account_name LIKE '%ค่าล่วงเวลา%'`
5. ใช้ `year` และ `month` สำหรับ filter เวลา
   - **กฎเหล็ก:** ใช้ `CAST(month AS INTEGER)` เสมอ
5. SELECT query เท่านั้น
   - ถ้ามี ORDER BY + LIMIT + UNION ต้องครอบด้วย Subquery
6. ห้ามใช้ table จริง ให้ใช้ view ที่กำหนดเท่านั้น
7. **ห้าม Format ตัวเลขใน SQL:** (สำคัญมาก!)
   - ห้ามใช้ `PRINTF`, `FORMAT` กับค่าเงิน/ตัวเลขคำนวณ
   - ต้องส่งค่าดิบ (Raw Number) เช่น `1234567.89` เท่านั้น
   - (Frontend จะจัดการใส่ลูกน้ำเอง)

{instruction_rules}

{context_instructions}

{syntax_rules}"""
    
    def _build_english_prompt(self, ai_provider: str, main_view: str, context_name: str, context_info: Dict = {}) -> str:
        """Build English language system prompt"""
        
        syntax_rules = self._get_syntax_rules("english")
        
        # Context specific instructions — DB-driven from schema_contexts.instruction_en
        context_instructions = context_info.get('instruction_en') or ""
        
        return f"""You are an AI Assistant for analyzing NT data.
Current Context: **{context_name.upper()}** (Table: `{main_view}`)

## Your Role
1. Answer questions about `{context_name}`
2. Generate SQL queries for `{main_view}`
3. Explain results in Thai

## SQL Rules
1. Use SQLite syntax
2. Query from: **{main_view}**
3. Use English column names (see Schema)
4. Filter time using `year` and `month`
   - Always `CAST(month AS INTEGER)`
5. Wrap UNION + ORDER BY/LIMIT in subqueries
6. Do NOT query raw tables directly

{context_instructions}

{syntax_rules}

## Response Format
1. SQL Query
2. Thai Explanation
3. Formatted numbers"""
    
    def _get_date_instructions(self, date_format: str) -> str:
        if date_format == "unix_timestamp_ms":
            return """## Date Handling
DATE column is Unix Timestamp (ms). Use YEAR/MONTH columns instead."""
        return """## Date Handling
ใช้ YEAR และ MONTH สำหรับ filter เวลา (CAST เป็น INTEGER เสมอ)"""

    def refresh_cache(self):
        """Clear cache when schema changes"""
        self._cache.clear()
        self._context_cache.clear()
    
    def get_cached_prompt(self, ai_provider: str = "claude", context_name: str = "revenue") -> str:
        """Get cached system prompt"""
        cache_key = f"prompt_{ai_provider}_{context_name}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self.build_system_prompt(ai_provider, context_name=context_name)
        return self._cache[cache_key]

# =========================================================
    # =========================================================
    # Keyword Value Index — Smart Value Lookup
    # =========================================================

    def get_searchable_columns(self, context_name: str, table_name: str = None) -> List[str]:
        """Get searchable/groupable columns from schema_metadata. Falls back to inspecting actual columns."""
        import logging
        _logger = logging.getLogger(__name__)

        # 1. Try schema_metadata (is_groupable = 1)
        # Map context_name → metadata table_name (metadata uses source table, not view)
        metadata_tables = [context_name]
        if table_name:
            metadata_tables.append(table_name)

        try:
            with self.engine.connect() as conn:
                for tbl in metadata_tables:
                    rows = conn.execute(text(
                        "SELECT column_name FROM schema_metadata WHERE table_name = :tbl AND is_groupable = 1"
                    ), {"tbl": tbl}).fetchall()
                    if rows:
                        cols = [r[0] for r in rows]
                        _logger.info(f"Searchable columns for '{context_name}' from schema_metadata: {len(cols)} columns")
                        return cols
        except Exception as e:
            _logger.warning(f"Failed to get searchable columns from metadata: {e}")

        # 2. Fallback: inspect actual table columns (all string-type columns)
        if table_name:
            try:
                inspector = inspect(self.business_engine)
                all_cols = inspector.get_columns(table_name)
                cols = [c['name'] for c in all_cols if str(c.get('type', '')).upper() in ('TEXT', 'VARCHAR', 'NVARCHAR')]
                if cols:
                    _logger.info(f"Searchable columns for '{context_name}' from table inspection: {len(cols)} columns")
                    return cols
            except Exception:
                pass

        return []

    # Thai prefixes to strip when generating keywords
    STRIP_PREFIXES = [
        "กลุ่มบริการ", "กลุ่ม", "บริการ", "สายงาน", "ฝ่าย", "ส่วน",
        "รายได้", "ค่าใช้จ่าย", "หมวด",
    ]

    def build_keyword_index(self, context_name: str = "revenue", table_name: str = "revenue_search") -> int:
        """
        Scan searchable columns, extract keywords, and populate keyword_value_index table.
        Returns number of keywords indexed.
        """
        import re
        import logging
        logger = logging.getLogger(__name__)

        columns = self.get_searchable_columns(context_name, table_name)

        inspector = inspect(self.business_engine)
        try:
            actual_cols = set(col['name'] for col in inspector.get_columns(table_name))
        except Exception:
            logger.error(f"Cannot inspect table {table_name}")
            return 0

        all_rows = []

        with self.engine.begin() as conn:
            # Clear existing index for this context
            conn.execute(text(
                "DELETE FROM keyword_value_index WHERE context_name = :ctx AND table_name = :tbl"
            ), {"ctx": context_name, "tbl": table_name})

            for col_name in columns:
                matching_col = next((c for c in actual_cols if c.upper() == col_name.upper()), None)
                if not matching_col:
                    continue

                try:
                    result = conn.execute(text(
                        f'SELECT DISTINCT "{matching_col}" FROM {table_name} WHERE "{matching_col}" IS NOT NULL'
                    ))
                    values = [row[0] for row in result.fetchall() if row[0]]
                except Exception as e:
                    logger.warning(f"Failed to scan {matching_col}: {e}")
                    continue

                for value in values:
                    value_str = str(value).strip()
                    if not value_str:
                        continue

                    # Generate keywords from the value
                    keywords = self._extract_keywords(value_str)

                    for kw in keywords:
                        if len(kw) < 2:
                            continue
                        all_rows.append({
                            "keyword": kw.lower(),
                            "column_name": matching_col,
                            "column_value": value_str,
                            "table_name": table_name,
                            "context_name": context_name,
                        })

            # Batch insert
            if all_rows:
                conn.execute(
                    text("""
                        INSERT INTO keyword_value_index (keyword, column_name, column_value, table_name, context_name)
                        VALUES (:keyword, :column_name, :column_value, :table_name, :context_name)
                    """),
                    all_rows
                )

        logger.info(f"Keyword index built: {len(all_rows)} entries for context={context_name}, table={table_name}")
        return len(all_rows)

    def _extract_keywords(self, value: str) -> List[str]:
        """Extract searchable keywords from a column value."""
        import re

        keywords = set()

        # Add full value as keyword
        keywords.add(value.strip())

        # Strip Thai prefixes and add remainder
        clean = value.strip()
        for prefix in self.STRIP_PREFIXES:
            if clean.startswith(prefix):
                remainder = clean[len(prefix):].strip()
                if remainder:
                    keywords.add(remainder)

        # Split by common delimiters and add individual words
        parts = re.split(r'[\s\-&/()（）,]+', value)
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                keywords.add(part)

        return list(keywords)

    def search_keyword_index(self, keyword: str, context_name: str = "revenue", limit: int = 10) -> List[Dict]:
        """
        Search pre-built keyword index for matching values.
        Returns list of {keyword, column_name, column_value, table_name}
        """
        import logging
        logger = logging.getLogger(__name__)

        results = []
        kw_lower = keyword.lower().strip()
        if not kw_lower:
            return results

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT DISTINCT column_name, column_value, table_name
                    FROM keyword_value_index
                    WHERE keyword LIKE :kw
                      AND context_name = :ctx
                    LIMIT :lim
                """), {"kw": f"%{kw_lower}%", "ctx": context_name, "lim": limit}).fetchall()

                for row in rows:
                    results.append({
                        "keyword": keyword,
                        "column_name": row[0],
                        "column_value": row[1],
                        "table_name": row[2],
                    })

            if results:
                logger.info(f"Keyword index: '{keyword}' → {len(results)} matches")
            else:
                logger.info(f"Keyword index: '{keyword}' → no matches")

        except Exception as e:
            logger.warning(f"Keyword index search failed: {e}")

        return results

    def search_db_for_keyword(self, keyword: str, table_name: str = "revenue_search", context_name: str = "revenue", limit: int = 10) -> List[Dict]:
        """
        Fallback: search actual DB columns for keyword match.
        Slower than index but always comprehensive.
        """
        import logging
        logger = logging.getLogger(__name__)

        results = []
        kw_pattern = f"%{keyword}%"

        columns = self.get_searchable_columns(context_name, table_name)

        inspector = inspect(self.business_engine)
        try:
            actual_cols = set(col['name'] for col in inspector.get_columns(table_name))
        except Exception:
            return results

        with self.engine.connect() as conn:
            for col_name in columns:
                matching_col = next((c for c in actual_cols if c.upper() == col_name.upper()), None)
                if not matching_col:
                    continue

                try:
                    rows = conn.execute(text(f"""
                        SELECT DISTINCT "{matching_col}"
                        FROM {table_name}
                        WHERE "{matching_col}" LIKE :kw
                           OR UPPER("{matching_col}") LIKE UPPER(:kw)
                        LIMIT :lim
                    """), {"kw": kw_pattern, "lim": limit}).fetchall()

                    for row in rows:
                        if row[0]:
                            results.append({
                                "keyword": keyword,
                                "column_name": matching_col,
                                "column_value": str(row[0]),
                                "table_name": table_name,
                            })
                except Exception:
                    continue

        if results:
            logger.info(f"DB search: '{keyword}' → {len(results)} matches across columns")
        else:
            logger.info(f"DB search: '{keyword}' → no matches")

        return results

    # ---------------------------------------------------------------
    # Known Terms Dictionary (for Thai keyword extraction)
    # ---------------------------------------------------------------
    _known_terms_cache: dict = {}
    _known_terms_ts: float = 0

    def get_known_terms(self, context_name: str = None) -> List[str]:
        """
        Get all known terms from keyword_value_index + master_hierarchy_values.
        Returns terms sorted by length DESC (for longest-match-first scanning).
        Cached for 1 hour per context.
        """
        import time
        cache_key = context_name or "__all__"
        now = time.time()

        if cache_key in self._known_terms_cache:
            cached = self._known_terms_cache[cache_key]
            if now - cached["ts"] < 3600:
                return cached["terms"]

        terms_set: set = set()
        try:
            with self.engine.connect() as conn:
                # Source 1: keyword_value_index
                ctx_filter = "AND context_name = :ctx" if context_name else ""
                params = {"ctx": context_name} if context_name else {}
                rows = conn.execute(text(f"""
                    SELECT DISTINCT keyword FROM keyword_value_index
                    WHERE 1=1 {ctx_filter}
                """), params).fetchall()
                for row in rows:
                    val = (row[0] or "").strip()
                    if len(val) >= 2:
                        terms_set.add(val)

                # Source 2: master_hierarchy_values (aliases + display values)
                ctx_filter2 = "AND context_name = :ctx" if context_name else ""
                rows2 = conn.execute(text(f"""
                    SELECT DISTINCT value FROM master_hierarchy_values
                    WHERE is_active = 1 {ctx_filter2}
                """), params).fetchall()
                for row in rows2:
                    val = (row[0] or "").strip()
                    if len(val) >= 2:
                        terms_set.add(val)

                # Source 3: aliases from master_hierarchy_values
                rows3 = conn.execute(text(f"""
                    SELECT DISTINCT aliases FROM master_hierarchy_values
                    WHERE aliases IS NOT NULL AND aliases != '' AND is_active = 1 {ctx_filter2}
                """), params).fetchall()
                for row in rows3:
                    raw = (row[0] or "").strip()
                    # aliases are stored as JSON arrays e.g. ["ปอธ.", "ธุรกิจลูกค้าฯ"]
                    aliases_list = []
                    if raw.startswith("["):
                        try:
                            import json as _json
                            aliases_list = _json.loads(raw)
                        except (ValueError, TypeError):
                            aliases_list = raw.split(",")
                    else:
                        aliases_list = raw.split(",")
                    for alias in aliases_list:
                        alias = str(alias).strip()
                        if len(alias) >= 2:
                            terms_set.add(alias)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_known_terms failed: {e}")

        # Sort by length DESC for longest-match-first
        sorted_terms = sorted(terms_set, key=len, reverse=True)
        self._known_terms_cache[cache_key] = {"terms": sorted_terms, "ts": now}
        return sorted_terms


# Factory Functions
# =========================================================

def create_claude_prompt(db_path: str = None, context_name: str = "revenue") -> str:
    """Create Claude system prompt. Uses 3-DB architecture by default."""
    service = SchemaService(db_path=db_path) if db_path else SchemaService()
    return service.build_system_prompt(ai_provider="claude", context_name=context_name)

def create_gemini_prompt(db_path: str = None, context_name: str = "revenue") -> str:
    """Create Gemini system prompt. Uses 3-DB architecture by default."""
    service = SchemaService(db_path=db_path) if db_path else SchemaService()
    return service.build_system_prompt(ai_provider="gemini", context_name=context_name)

if __name__ == "__main__":
    # Uses auto-import from app.db.session (3-DB architecture)
    service = SchemaService()
    print(service.build_system_prompt(context_name="expense")[:500])

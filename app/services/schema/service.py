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
from sqlalchemy.exc import SQLAlchemyError
import json
import logging
from typing import Dict, List, Optional, Any

import app.services.schema.context_store as context_store
import app.services.schema.dimension_families as dimension_families
import app.services.schema.keyword_index as keyword_index
import app.services.schema.prompt_builder as prompt_builder
import app.services.schema.view_manager as view_manager
from app.services.schema.sql_identifiers import quote_identifier

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

    def get_cached_value(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set_cached_value(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def clear_cached_values(self) -> None:
        self._cache.clear()

    def get_cached_context(self, context_name: str) -> Optional[Dict]:
        return self._context_cache.get(context_name)

    def set_cached_context(self, context_name: str, context_info: Dict) -> None:
        self._context_cache[context_name] = context_info

    def clear_cached_contexts(self) -> None:
        self._context_cache.clear()

    def _get_connection(self) -> Connection:
        """Get business DB connection (for inspecting views/tables)"""
        return self.business_engine.connect()

    def _get_config_connection(self) -> Connection:
        """Get config DB connection (for schema_contexts, mappings, rules, etc.)"""
        return self.config_engine.connect()

    def get_business_engine(self) -> Engine:
        return self.business_engine

    def get_config_engine(self) -> Engine:
        return self.engine

    
    # =========================================================
    # Schema View Builder (Cross-Database)
    # =========================================================

    def get_all_tables(self) -> List[str]:
        return view_manager.get_all_tables(self)

    def create_custom_view(self, view_name: str, source_table: str, mapping: List[Dict[str, str]]) -> bool:
        return view_manager.create_custom_view(self, view_name, source_table, mapping)

    # =========================================================
    # View Column Mappings
    # =========================================================

    def list_views_with_mappings(self) -> List[Dict]:
        return view_manager.list_views_with_mappings(self)

    def save_view_column_mappings(self, view_name: str, source_table: str, mappings: List[Dict[str, str]]) -> int:
        return view_manager.save_view_column_mappings(self, view_name, source_table, mappings)

    def get_view_column_mappings(self, view_name: str) -> List[Dict]:
        return view_manager.get_view_column_mappings(self, view_name)

    def _find_source_metadata(self, conn, source_table: str, source_column: str) -> Optional[Dict]:
        return view_manager.find_source_metadata(self, conn, source_table, source_column)

    def propagate_metadata_to_view(self, view_name: str) -> Dict:
        return view_manager.propagate_metadata_to_view(self, view_name)

    # =========================================================
    # Context Management
    # =========================================================

    def get_context_info(self, context_name: str) -> Optional[Dict]:
        return context_store.get_context_info(self, context_name)


    def get_all_contexts(self) -> List[Dict]:
        return context_store.get_all_contexts(self)

    def create_context(self, data: Dict) -> Dict:
        return context_store.create_context(self, data)

    def update_context(self, context_id: int, data: Dict) -> Optional[Dict]:
        return context_store.update_context(self, context_id, data)

    def delete_context(self, context_id: int):
        context_store.delete_context(self, context_id)

    def refresh_context_cache(self):
        context_store.refresh_context_cache(self)


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
            except SQLAlchemyError:
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
            except SQLAlchemyError:
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
            example_cols = []
            for r in rows:
                try:
                    cols = json.loads(r[1])
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

        except (SQLAlchemyError, TypeError, ValueError) as exc:
            logger.error("build_hierarchy_rule_text error: %s", exc)
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

        instruction_text = ""
        # Context retention rules get a header
        if 'context_retention' in sections:
            instruction_text += "\n## กฎการรักษาบริบท (Context Retention Rules)\n"
            instruction_text += "**หลักการสำคัญ:** แยกระหว่าง REPLACE vs MERGE\n\n"
            for desc in sections['context_retention']:
                instruction_text += f"{desc}\n\n"
            del sections['context_retention']

        # Other sections
        for category, descs in sections.items():
            for desc in descs:
                instruction_text += f"\n{desc}\n"

        return instruction_text

    def get_dimension_families(self, table_name: str) -> Dict[str, List[str]]:
        return dimension_families.get_dimension_families(self, table_name)

    def get_dimension_families_with_source(self, table_name: str) -> List[Dict]:
        return dimension_families.get_dimension_families_with_source(self, table_name)

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
            except SQLAlchemyError:
                return []
    
    def get_sample_values(self, table_name: str) -> Dict[str, List[str]]:
        """Get sample values for important columns"""
        # Phase 4.5: values read from the rows — none for a source whose policy isn't `full`, whoever asks
        # (system prompt, suggest-mappings, dimension-families)
        from app.core.llm_policy import FULL, restricted
        from app.services.data_sources import policy_for_table
        if restricted() or policy_for_table(table_name, self.engine) != FULL:
            return {}
        samples = {}
        inspector = inspect(self.business_engine)
        
        # Get actual columns first
        try:
            actual_cols = set(col['name'] for col in inspector.get_columns(table_name))
        except SQLAlchemyError:
            return {}

        # Default columns to try
        columns_to_try = [
            'business_unit', 'division', 'department', 'SERVICE_GROUP',
            'BUSINESS_GROUP', 'business_group', 'PRODUCT_NAME',
            'account_group_name', 'account_name', 'gl_name'
        ]
        
        with self.business_engine.connect() as conn:
            for col_name in columns_to_try:
                # Find matching column (case-insensitive check might be needed for some DBs)
                # For now assume exact match or simple case variant
                matching_col = next((c for c in actual_cols if c.upper() == col_name.upper()), None)
                
                if matching_col:
                    try:
                        sql = text(
                            f"SELECT DISTINCT {quote_identifier(matching_col)} "
                            f"FROM {quote_identifier(table_name)} "
                            f"WHERE {quote_identifier(matching_col)} IS NOT NULL LIMIT 20"
                        )
                        result = conn.execute(sql)
                        samples[col_name] = [row[0] for row in result.fetchall()]
                    except SQLAlchemyError:
                        pass
        
            # Get data range
            try:
                sql = text(
                    f"SELECT "
                    f"MIN({quote_identifier('year')}) as min_year, "
                    f"MAX({quote_identifier('year')}) as max_year, "
                    f"MIN(CAST({quote_identifier('month')} AS INTEGER)) as min_month, "
                    f"MAX(CAST({quote_identifier('month')} AS INTEGER)) as max_month "
                    f"FROM {quote_identifier(table_name)}"
                )
                result = conn.execute(sql)
                row = result.mappings().fetchone()
                if row:
                    samples['DATA_RANGE'] = {
                        'min_year': row['min_year'],
                        'max_year': row['max_year'],
                        'min_month': row['min_month'],
                        'max_month': row['max_month']
                    }
            except SQLAlchemyError:
                pass
        
        return samples
    
    # =========================================================
    # Prompt Building Methods
    # =========================================================
    
    def build_schema_text(self, table_name: str) -> str:
        return prompt_builder.build_schema_text(self, table_name)
    
    def build_business_rules_text(self, table_name: str) -> str:
        return prompt_builder.build_business_rules_text(self, table_name)
    
    def build_sample_values_text(self, table_name: str) -> str:
        return prompt_builder.build_sample_values_text(self, table_name)

    def build_semantic_mapping_text(self, context_name: Optional[str] = None) -> str:
        return prompt_builder.build_semantic_mapping_text(self, context_name)
    
    def get_schema_context(
        self, 
        context_name: str = "revenue", 
        include_samples: bool = True, 
        include_semantic_mappings: bool = True,
        lite_mode: bool = False
    ) -> str:
        return prompt_builder.get_schema_context(self, context_name, include_samples, include_semantic_mappings, lite_mode)

    def build_system_prompt(
        self,
        ai_provider: str = "claude",
        include_samples: bool = True,
        language: str = "thai",
        context_name: str = "revenue",
        rag_enabled: bool = False
    ) -> str:
        return prompt_builder.build_system_prompt(self, ai_provider, include_samples, language, context_name, rag_enabled)
    
    def get_default_instruction(self, ai_provider: str = "claude", language: str = "thai", context_name: str = "revenue") -> str:
        return prompt_builder.get_default_instruction(self, ai_provider, language, context_name)
            
    def _get_syntax_rules(self, language: str = "thai") -> str:
        return prompt_builder.get_syntax_rules(self, language)

    def _build_thai_prompt(self, ai_provider: str, main_view: str, context_name: str, context_info: Optional[Dict] = None) -> str:
        return prompt_builder.build_thai_prompt(self, ai_provider, main_view, context_name, context_info)
    
    def _build_english_prompt(self, ai_provider: str, main_view: str, context_name: str, context_info: Optional[Dict] = None) -> str:
        return prompt_builder.build_english_prompt(self, ai_provider, main_view, context_name, context_info)
    

    def refresh_cache(self):
        """Clear cache when schema changes"""
        self.clear_cached_values()
        self.clear_cached_contexts()
        keyword_index.clear_known_terms_cache()
    
    def get_cached_prompt(self, ai_provider: str = "claude", context_name: str = "revenue") -> str:
        """Get cached system prompt"""
        cache_key = f"prompt_{ai_provider}_{context_name}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self.build_system_prompt(ai_provider, context_name=context_name)
        return self._cache[cache_key]

    # =========================================================
    # Keyword Value Index — Smart Value Lookup
    # =========================================================

    def get_searchable_columns(self, context_name: str, table_name: str = None) -> List[str]:
        return keyword_index.get_searchable_columns(self, context_name, table_name)

    def build_keyword_index(self, context_name: str = "revenue", table_name: str = "revenue_search") -> int:
        return keyword_index.build_keyword_index(self, context_name, table_name)

    def search_keyword_index(self, keyword: str, context_name: str = "revenue", limit: int = 10) -> List[Dict]:
        return keyword_index.search_keyword_index(self, keyword, context_name, limit)

    def search_db_for_keyword(self, keyword: str, table_name: str = "revenue_search", context_name: str = "revenue", limit: int = 10) -> List[Dict]:
        return keyword_index.search_db_for_keyword(self, keyword, table_name, context_name, limit)

    def get_known_terms(self, context_name: str = None) -> List[str]:
        return keyword_index.get_known_terms(self, context_name)


# Factory Functions
# =========================================================

def create_claude_prompt(db_path: str = None, context_name: str = "revenue") -> str:
    """Create Claude system prompt. Uses 3-DB architecture by default."""
    schema_service = SchemaService(db_path=db_path) if db_path else SchemaService()
    return schema_service.build_system_prompt(ai_provider="claude", context_name=context_name)

def create_gemini_prompt(db_path: str = None, context_name: str = "revenue") -> str:
    """Create Gemini system prompt. Uses 3-DB architecture by default."""
    schema_service = SchemaService(db_path=db_path) if db_path else SchemaService()
    return schema_service.build_system_prompt(ai_provider="gemini", context_name=context_name)

if __name__ == "__main__":
    # Uses auto-import from app.db.session (3-DB architecture)
    sample_service = SchemaService()
    print(sample_service.build_system_prompt(context_name="expense")[:500])

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
    schema_service = SchemaService(db_path="revenue.db")
    prompt = schema_service.build_system_prompt(context_name="expense")
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import Session
import sqlite3
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

class SchemaService:
    """Service สำหรับจัดการ schema metadata"""
    
    def __init__(self, db_engine: Optional[Engine] = None, db_path: str = "nt_fi_report.sqlite"):
        """
        Initialize SchemaService
        
        Args:
            db_engine: SQLAlchemy Engine (preferred for cross-db support)
            db_path: Path to main database (fallback for legacy sqlite3 calls if engine not provided)
        """
        self.db_path = db_path
        self.engine = db_engine
        
        # Fallback engine for SQLite if None provided
        if not self.engine:
             self.engine = create_engine(f"sqlite:///{db_path}")

        self.metadata_db_path = db_path # Simplify: Assume metadata is in the same DB for now
        self._cache: Dict[str, Any] = {}
        self._context_cache: Dict[str, Dict] = {}
    
    def _get_connection(self) -> Connection:
        """Get database connection from engine"""
        return self.engine.connect()

    
    # =========================================================
    # Schema View Builder (Cross-Database)
    # =========================================================

    def get_all_tables(self) -> List[str]:
        """List all tables in the database (excluding system tables)"""
        inspector = inspect(self.engine)
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
        
        with self.engine.begin() as conn:
            # Drop if exists (optional, maybe dangerous? for now lets match implementation plan implies creation)
            conn.execute(text(f"DROP VIEW IF EXISTS {view_name}")) 
            conn.execute(text(sql))
            
        return True

    # =========================================================
    # Context Management
    # =========================================================

    def get_context_info(self, context_name: str) -> Optional[Dict]:
        """Get context information from schema_contexts table"""
        if context_name in self._context_cache:
            return self._context_cache[context_name]

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                    {"name": context_name}
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
                
                # Fallback
                if context_name == 'revenue':
                     return {'name': 'revenue', 'main_view': 'revenue_search', 'display_name': 'รายได้'}
                return None
                
            except Exception as e:
                # Fallback for bootstrapping
                if context_name == 'revenue':
                     return {'id': 1, 'name': 'revenue', 'main_view': 'revenue_search', 'display_name': 'รายได้', 'created_at': datetime.now(), 'keywords': [], 'is_active': True, 'priority': 0}
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
            except Exception:
                return [{'id': 1, 'name': 'revenue', 'main_view': 'revenue_search', 'display_name': 'รายได้', 'created_at': datetime.now(), 'keywords': [], 'is_active': True, 'priority': 0}]

    def create_context(self, data: Dict) -> Dict:
        """Create new context"""
        with self.engine.begin() as conn:
            # Prepare columns
            columns = ['name', 'display_name', 'description', 'main_view', 'is_active', 'priority', 'keywords']
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
        inspector = inspect(self.engine)
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
    
    def get_business_rules(self, table_name: str) -> List[Dict]:
        """Get business rules from schema_business_rules table"""
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text("""
                    SELECT * FROM schema_business_rules
                    WHERE is_active = 1
                    AND (table_name = :table_name OR table_name = 'ALL' OR table_name IS NULL)
                    ORDER BY
                        CASE severity
                            WHEN 'error' THEN 1
                            WHEN 'warning' THEN 2
                            ELSE 3
                        END
                """), {"table_name": table_name})
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception:
                return []

    def get_semantic_mappings(self, keyword_type: Optional[str] = None) -> List[Dict]:
        """Get semantic mappings from schema_semantic_mapping table"""
        with self.engine.connect() as conn:
            try:
                if keyword_type:
                    result = conn.execute(text("""
                        SELECT * FROM schema_semantic_mapping
                        WHERE is_active = 1 AND keyword_type = :keyword_type
                        ORDER BY priority DESC, keyword
                    """), {"keyword_type": keyword_type})
                else:
                    result = conn.execute(text("""
                        SELECT * FROM schema_semantic_mapping
                        WHERE is_active = 1
                        ORDER BY priority DESC, keyword
                    """))
                return [dict(row) for row in result.mappings().fetchall()]
            except Exception:
                return []
    
    def get_sample_values(self, table_name: str) -> Dict[str, List[str]]:
        """Get sample values for important columns"""
        samples = {}
        inspector = inspect(self.engine)
        
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
        """Build business rules text for AI prompt"""
        
        rules = self.get_business_rules(table_name)
        
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

    def build_semantic_mapping_text(self) -> str:
        """Build semantic mapping text for AI prompt"""

        mappings = self.get_semantic_mappings()

        if not mappings:
            return self._get_default_semantic_mappings()

        text = "## Semantic Mappings (การแปลงความหมาย)\n\n"

        # Group by keyword_type
        abbreviations = [m for m in mappings if m.get('keyword_type') == 'abbreviation']
        terms = [m for m in mappings if m.get('keyword_type') == 'term']
        synonyms = [m for m in mappings if m.get('keyword_type') == 'synonym']

        if abbreviations:
            text += "### คำย่อหน่วยงาน (Abbreviations)\n"
            text += "| คำย่อ | Column | Condition | ความหมาย |\n"
            text += "|-------|--------|-----------|----------|\n"
            for m in abbreviations:
                text += f"| {m['keyword']} | {m['target_column']} | {m['target_condition']} | {m.get('description', '')} |\n"
            text += "\n"

        if terms:
            text += "### คำศัพท์ธุรกิจ (Business Terms)\n"
            text += "| คำค้น | Column | Condition | ความหมาย |\n"
            text += "|-------|--------|-----------|----------|\n"
            for m in terms:
                text += f"| {m['keyword']} | {m['target_column']} | {m['target_condition']} | {m.get('description', '')} |\n"
            text += "\n"

        if synonyms:
            text += "### คำพ้องความหมาย (Synonyms)\n"
            for m in synonyms:
                text += f"- **{m['keyword']}** → `{m['target_column']} {m['target_condition']}`"
                if m.get('description'):
                    text += f" ({m['description']})"
                text += "\n"
            text += "\n"

        return text

    def _get_default_semantic_mappings(self) -> str:
        """Get default semantic mappings if table doesn't exist"""
        return """## Semantic Mappings
- **นป.** → `organization_group_abbr = 'นป.'`
- **บชง.** → `department_abbr = 'บชง.'`
"""
    
    def get_schema_context(self, context_name: str = "revenue", include_samples: bool = True, include_semantic_mappings: bool = True) -> str:
        """Get schema context (Schema + Rules + Semantic Mappings + Samples)"""
        
        # 1. Get Context Info
        context_info = self.get_context_info(context_name)
        if not context_info:
            # Fallback to revenue
            context_info = {'name': 'revenue', 'main_view': 'revenue_search', 'display_name': 'รายได้'}
            
        main_view = context_info['main_view']
        display_name = context_info.get('display_name', context_name)

        # 2. Build Components
        context = f"# Context: {display_name} ({context_name})\n"
        context += self.build_schema_text(table_name=main_view)
        context += "\n\n" + self.build_business_rules_text(table_name=main_view)

        if include_semantic_mappings:
            context += "\n\n" + self.build_semantic_mapping_text()

        if include_samples:
            context += "\n\n" + self.build_sample_values_text(table_name=main_view)

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
        context_name: str = "revenue"
    ) -> str:
        """
        Build complete system prompt for AI
        """
        
        # 1. Get Context Info
        context_info = self.get_context_info(context_name)
        if not context_info:
            context_info = {'name': 'revenue', 'main_view': 'revenue_search', 'display_name': 'รายได้'}
        
        main_view = context_info['main_view']
        
        # 2. Build Instruction based on context
        if language == "thai":
            instruction = self._build_thai_prompt(ai_provider, main_view, context_name)
        else:
            instruction = self._build_english_prompt(ai_provider, main_view, context_name)
        
        # 3. Build Context (Schema, Rules, etc.)
        context_text = self.get_schema_context(context_name, include_samples)
        
        return f"{instruction}\n\n{context_text}"
    
    def get_default_instruction(self, ai_provider: str = "claude", language: str = "thai", context_name: str = "revenue") -> str:
        """Get default system instruction without schema context"""
        context_info = self.get_context_info(context_name) or {'main_view': 'revenue_search'}
        main_view = context_info['main_view']
        
        if language == "thai":
            return self._build_thai_prompt(ai_provider, main_view, context_name)
        else:
            return self._build_english_prompt(ai_provider, main_view, context_name)
            
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

    def _build_thai_prompt(self, ai_provider: str, main_view: str, context_name: str) -> str:
        """Build Thai language system prompt"""
        
        syntax_rules = self._get_syntax_rules("thai")
        
        # Context specific instructions
        context_instructions = ""
        if context_name == "revenue":
            context_instructions = """
   - **คำเตือน (Revenue Context):**
     - อย่ารวม 'รายได้อื่น' (Other Revenue) ในการคำนวณรายได้ทั้งหมด ยกเว้น user สั่ง
     - หน่วยรายได้เป็น **บาท**
            """
        elif context_name == "expense":
            context_instructions = """
   - **คำเตือน (Expense Context):**
     - ค่าใช้จ่ายแยกตามหมวดบัญชี (Account Group)
     - `gl_code` คือรหัสบัญชี, `account_name` คือชื่อบัญชี
     - `amount` คือยอดค่าใช้จ่าย (เป็นตัวเลขติดลบ หรือบวกแล้วแต่การบันทึก ให้ระวังเรื่อง SUM)
     - ปกติถ้าเป็น Expense table ค่าอาจจะเป็น + หรือ - ให้เช็ค Data range ใน Schema
            """
        
        return f"""คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูลของ NT (National Telecom)
บริบทปัจจุบัน: **{context_name.upper()}** (ตาราง: `{main_view}`)

## หน้าที่ของคุณ
1. รับคำถามภาษาไทย/อังกฤษ เกี่ยวกับ `{context_name}`
2. สร้าง SQL Query ที่ถูกต้องเพื่อดึงข้อมูลจาก `{main_view}`
3. อธิบายผลลัพธ์เป็นภาษาไทย

## กฎการสร้าง SQL
1. ใช้ SQLite syntax เท่านั้น
2. ใช้ query จาก table/view: **{main_view}**
3. Column ทั้งหมดเป็นภาษาอังกฤษ (ดู Schema ด้านล่าง)
4. ใช้ `year` และ `month` สำหรับ filter เวลา
   - **กฎเหล็ก:** ใช้ `CAST(month AS INTEGER)` เสมอ
5. SELECT query เท่านั้น
   - ถ้ามี ORDER BY + LIMIT + UNION ต้องครอบด้วย Subquery
6. ห้ามใช้ table จริง ให้ใช้ view ที่กำหนดเท่านั้น

{context_instructions}

{syntax_rules}

## รูปแบบการตอบ
1. แสดง SQL query
2. อธิบายผลลัพธ์เป็นภาษาไทย
3. Format ตัวเลขให้อ่านง่าย (เช่น 1,234,567.89)"""
    
    def _build_english_prompt(self, ai_provider: str, main_view: str, context_name: str) -> str:
        """Build English language system prompt"""
        
        syntax_rules = self._get_syntax_rules("english")
        
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
# Factory Functions
# =========================================================

def create_claude_prompt(db_path: str, context_name: str = "revenue") -> str:
    service = SchemaService(db_path=db_path)
    return service.build_system_prompt(ai_provider="claude", context_name=context_name)

def create_gemini_prompt(db_path: str, context_name: str = "revenue") -> str:
    service = SchemaService(db_path=db_path)
    return service.build_system_prompt(ai_provider="gemini", context_name=context_name)

if __name__ == "__main__":
    service = SchemaService(db_path="nt_fi_report.sqlite")
    print(service.build_system_prompt(context_name="expense")[:500])

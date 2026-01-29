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
- Database abstraction layer support

Usage:
    schema_service = SchemaService(db_path="revenue.db")
    prompt = schema_service.build_system_prompt()
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path


class SchemaService:
    """Service สำหรับจัดการ schema metadata"""
    
    def __init__(self, db_path: str = "nt_revenue.sqlite", metadata_db_path: Optional[str] = None, db_engine: str = "sqlite"):
        """
        Initialize SchemaService
        
        Args:
            db_path: Path to main database (revenue.db)
            metadata_db_path: Path to metadata database (default: same as db_path)
            db_engine: Database engine type (e.g., "sqlite", "postgres")
        """
        self.db_path = db_path
        self.metadata_db_path = metadata_db_path or db_path
        self.db_engine = db_engine.lower()
        self._cache: Dict[str, Any] = {}
    
    def _get_connection(self, path: str) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # =========================================================
    # Schema Information Methods
    # =========================================================
    
    def get_table_info(self, table_name: str = "revenue_search") -> List[Dict]:
        """Get column information from SQLite pragma"""
        conn = self._get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return columns
    
    def get_schema_metadata(self, table_name: str = "revenue") -> List[Dict]:
        """Get schema metadata from metadata table"""
        conn = self._get_connection(self.metadata_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM schema_metadata 
                WHERE table_name = ?
                ORDER BY 
                    CASE column_name
                        WHEN 'YEAR' THEN 1
                        WHEN 'MONTH' THEN 2
                        WHEN 'DATE' THEN 3
                        WHEN 'REVENUE_VALUE' THEN 4
                        WHEN 'AMOUNT' THEN 5
                        ELSE 10
                    END,
                    column_name
            """, (table_name,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Table doesn't exist, return empty
            return []
        finally:
            conn.close()
    
    def get_business_rules(self, table_name: str = "revenue_search") -> List[Dict]:
        """Get business rules from schema_business_rules table"""
        conn = self._get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Get rules for specific table or global rules (table_name IS NULL or 'ALL')
            cursor.execute("""
                SELECT * FROM schema_business_rules
                WHERE is_active = 1
                AND (table_name = ? OR table_name = 'ALL' OR table_name IS NULL)
                ORDER BY
                    CASE severity
                        WHEN 'error' THEN 1
                        WHEN 'warning' THEN 2
                        ELSE 3
                    END
            """, (table_name,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get_semantic_mappings(self, keyword_type: Optional[str] = None) -> List[Dict]:
        """Get semantic mappings from schema_semantic_mapping table"""
        conn = self._get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            if keyword_type:
                cursor.execute("""
                    SELECT * FROM schema_semantic_mapping
                    WHERE is_active = 1 AND keyword_type = ?
                    ORDER BY priority DESC, keyword
                """, (keyword_type,))
            else:
                cursor.execute("""
                    SELECT * FROM schema_semantic_mapping
                    WHERE is_active = 1
                    ORDER BY priority DESC, keyword
                """)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get_abbreviation_mappings(self) -> List[Dict]:
        """Get abbreviation mappings only"""
        return self.get_semantic_mappings(keyword_type='abbreviation')

    def get_term_mappings(self) -> List[Dict]:
        """Get business term mappings only"""
        return self.get_semantic_mappings(keyword_type='term')
    
    def get_sample_values(self, table_name: str = "revenue_search") -> Dict[str, List[str]]:
        """Get sample values for important columns"""
        conn = self._get_connection(self.db_path)
        cursor = conn.cursor()
        
        samples = {}
        
        # Important columns to sample
        columns_to_sample = [
            ('business_unit', 'business_unit'),
            ('division', 'division'),
            ('department', 'department'),
            ('SERVICE_GROUP', 'SERVICE_GROUP'),
            ('BUSINESS_GROUP', 'BUSINESS_GROUP'),
            ('PRODUCT_NAME', 'PRODUCT_NAME'),
            ('PRODUCT_KEY', 'PRODUCT_KEY'),
        ]
        
        for col_name, col_sql in columns_to_sample:
            try:
                cursor.execute(f"""
                    SELECT DISTINCT {col_sql} 
                    FROM {table_name} 
                    WHERE {col_sql} IS NOT NULL 
                    LIMIT 20
                """)
                samples[col_name] = [row[0] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                pass
        
        # Get data range
        try:
            cursor.execute(f"""
                SELECT 
                    MIN(year) as min_year,
                    MAX(year) as max_year,
                    MIN(CAST(month AS INTEGER)) as min_month,
                    MAX(CAST(month AS INTEGER)) as max_month
                FROM {table_name}
            """)
            row = cursor.fetchone()
            if row:
                samples['DATA_RANGE'] = {
                    'min_year': row['min_year'],
                    'max_year': row['max_year'],
                    'min_month': row['min_month'],
                    'max_month': row['max_month']
                }
        except:
            pass
        
        conn.close()
        return samples
    
    def get_date_format(self, table_name: str = "revenue_search") -> str:
        """Detect DATE column format (TEXT or INTEGER)"""
        # View uses explicit year/month, but check if DATE exists
        return "year_month_only"
    
    # =========================================================
    # Prompt Building Methods
    # =========================================================
    
    def build_schema_text(self, table_name: str = "revenue_search") -> str:
        """Build schema information text for AI prompt"""
        
        # Try to get from metadata table first
        metadata = self.get_schema_metadata(table_name)
        
        if metadata:
            return self._build_schema_from_metadata(metadata)
        else:
            # Fallback to PRAGMA
            return self._build_schema_from_pragma(table_name)
    
    def _build_schema_from_metadata(self, metadata: List[Dict]) -> str:
        """Build schema text from metadata table"""
        
        text = "## Table: revenue\n\n"
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
    
    def build_business_rules_text(self, table_name: str = "revenue_search") -> str:
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

✅ **Correct:**
```sql
SELECT date(DATE / 1000, 'unixepoch') FROM revenue
```

❌ **Wrong:**
```sql
SELECT DATE FROM revenue -- จะได้ตัวเลข
```

### ⚠️ Thai Year Conversion
ปี พ.ศ. = ปี ค.ศ. + 543

✅ **Correct:**
```sql
SELECT YEAR + 543 as year_th FROM revenue
```

### ⚠️ Thai Column Names
Column ที่มีชื่อภาษาไทยต้องใช้ double quotes

✅ **Correct:**
```sql
SELECT "กลุ่มธุรกิจ", "หมวดบัญชี" FROM revenue
```

### ℹ️ Revenue Unit
REVENUE_VALUE และ AMOUNT มีหน่วยเป็น **บาท** (ไม่ใช่ล้านบาท)

### ℹ️ Organization Hierarchy
DIVISION → GROUP → DEPARTMENT → SECTION → COST_CENTER

### ℹ️ Common Abbreviations (คำย่อหน่วยงาน)
- **นป.** = `กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ` (ใช้ column `organization_group` หรือ `group`)
- **บชง.** = `ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ` (ใช้ column `department` หรือ `department_abbr`)

"""
    
    def build_sample_values_text(self, table_name: str = "revenue") -> str:
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

        text += """### วิธีใช้ Semantic Mappings
เมื่อพบคำใน query ให้ใช้ condition ที่กำหนด เช่น:
- "รายได้ นป." → `WHERE organization_group_abbr = 'นป.'`
- "รายได้อสังหาริมทรัพย์" → `WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
"""
        return text

    def _get_default_semantic_mappings(self) -> str:
        """Get default semantic mappings if table doesn't exist"""
        return """## Semantic Mappings (การแปลงความหมาย)

### คำย่อหน่วยงาน (Abbreviations)
- **นป.** → `organization_group_abbr = 'นป.'` (กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ)
- **บชง.** → `department_abbr = 'บชง.'` (ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ)
- **สญ.** → `division_abbr = 'สญ.'` (สายงานขายและบริการ)

### คำศัพท์ธุรกิจ (Business Terms)
- **อสังหาริมทรัพย์** → `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
- **ทรัพย์สิน** → `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
- **มือถือ** → `BUSINESS_GROUP = 'Mobile'`
- **โทรศัพท์บ้าน** → `BUSINESS_GROUP = 'Fixed Line'`

### วิธีใช้ Semantic Mappings
เมื่อพบคำใน query ให้ใช้ condition ที่กำหนด
"""
    
    def get_schema_context(self, include_samples: bool = True, include_semantic_mappings: bool = True) -> str:
        """Get schema context (Schema + Rules + Semantic Mappings + Samples + Date Info) without persona instructions"""
        date_format = self.get_date_format()

        context = self.build_schema_text(table_name="revenue_search")  # Default to revenue_search
        context += "\n\n" + self.build_business_rules_text(table_name="revenue_search")

        # Add semantic mappings (abbreviations and business terms)
        if include_semantic_mappings:
            context += "\n\n" + self.build_semantic_mapping_text()

        if include_samples:
            context += "\n\n" + self.build_sample_values_text()

        context += "\n\n" + self._get_date_instructions(date_format)

        # Add current date
        context += f"\n\n## Current Date\nวันที่ปัจจุบัน: {datetime.now().strftime('%Y-%m-%d')}\n"
        context += f"ปี พ.ศ. ปัจจุบัน: {datetime.now().year + 543}\n"

        return context

    def build_system_prompt(
        self, 
        ai_provider: str = "claude",
        include_samples: bool = True,
        language: str = "thai"
    ) -> str:
        """
        Build complete system prompt for AI
        
        Args:
            ai_provider: "claude" or "gemini"
            include_samples: Include sample values
            language: "thai" or "english"
        
        Returns:
            Complete system prompt string
        """
        
        # Detect date format
        date_format = self.get_date_format()
        
        # Build instruction
        if language == "thai":
            instruction = self._build_thai_prompt(ai_provider, date_format)
        else:
            instruction = self._build_english_prompt(ai_provider, date_format)
        
        # Build context
        context = self.get_schema_context(include_samples)
        
        return f"{instruction}\n\n{context}"
    
    def get_default_instruction(self, ai_provider: str = "claude", language: str = "thai") -> str:
        """Get default system instruction without schema context"""
        date_format = self.get_date_format()
        if language == "thai":
            return self._build_thai_prompt(ai_provider, date_format)
        else:
            return self._build_english_prompt(ai_provider, date_format)
            
    def _get_syntax_rules(self, language: str = "thai") -> str:
        """Get database-specific syntax rules"""
        if self.db_engine == "postgresql":
            if language == "thai":
                return """   10. **Syntax สำหรับ PostgreSQL:**
       - ใช้ `CONCAT(a, b)` หรือ `a || b` ได้
       - การจัดรูปแบบวันที่ใช้ `to_char(date, 'YYYY-MM')`
       - การแปลงชนิดข้อมูลใช้ `::integer` หรือ `CAST(col AS INTEGER)`
       - ห้ามใช้ `strftime` (ของ SQLite)"""
            else:
                return """   10. **PostgreSQL Syntax:**
       - Use `CONCAT(a, b)` or `a || b`
       - Date formatting: `to_char(date, 'YYYY-MM')`
       - Type casting: `::integer` or `CAST(col AS INTEGER)`
       - NO `strftime` (SQLite specific)"""
        
        elif self.db_engine == "mssql":
            if language == "thai":
                return """   10. **Syntax สำหรับ MSSQL (SQL Server):**
       - การต่อสตริงใช้ `+` เช่น `col1 + '-' + col2` (ห้ามใช้ `||`)
       - การจัดรูปแบบวันที่ใช้ `FORMAT(date, 'yyyy-MM')`
       - การแปลงชนิดข้อมูลใช้ `CONVERT(INT, col)` หรือ `CAST(col AS INT)`
       - ห้ามใช้ `strftime`, `printf`, `LIMIT` (ใช้ `TOP` แทน)"""
            else:
                return """   10. **MSSQL Syntax:**
       - String concatenation: Use `+` e.g. `col1 + '-' + col2` (NO `||`)
       - Date formatting: `FORMAT(date, 'yyyy-MM')`
       - Type casting: `CONVERT(INT, col)` or `CAST(col AS INT)`
       - NO `strftime`, `printf`, `LIMIT` (Use `TOP` instead)"""
               
        else: # Default to sqlite
            if language == "thai":
                return """   10. **Syntax สำหรับ SQLite:**
       - ห้ามใช้ `CONCAT(a, b)` -> ให้ใช้ `a || b` แทน
       - ห้ามใช้ `LPAD` -> ให้ใช้ `printf('%02d', CAST(col AS INTEGER))`
       - ห้ามใช้ `DATE_FORMAT` -> ให้ใช้ `strftime`"""
            else:
                return """   10. **SQLite Syntax:**
       - NO `CONCAT(a, b)` -> Use `a || b` instead
       - NO `LPAD` -> Use `printf('%02d', CAST(col AS INTEGER))`
       - NO `DATE_FORMAT` -> Use `strftime`"""

    def _build_thai_prompt(self, ai_provider: str, date_format: str) -> str:
        """Build Thai language system prompt"""
        
        syntax_rules = self._get_syntax_rules("thai")
        
        return f"""คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูลรายได้ของ NT (National Telecom)

## หน้าที่ของคุณ
1. รับคำถามเกี่ยวกับข้อมูลรายได้เป็นภาษาไทยหรืออังกฤษ
2. สร้าง SQL Query ที่ถูกต้องเพื่อดึงข้อมูลจาก View `revenue_search`
3. อธิบายผลลัพธ์เป็นภาษาไทยที่เข้าใจง่าย

## กฎการสร้าง SQL
1. ใช้ SQLite syntax เท่านั้น
2. ใช้ query จาก table/view: **revenue_search**
3. ใช้ `SUM(revenue)` สำหรับรวมรายได้
4. Column ทั้งหมดเป็นภาษาอังกฤษ (ไม่ต้องใช้ quote ภาษาไทยแล้ว)
   - `business_unit` = **โครงสร้างหน่วยงาน/BU** (เช่น กลุ่มขายและตลาด, กลุ่มธุรกิจสื่อสารไร้สาย) **ไม่ใช่**กลุ่มผลิตภัณฑ์
   - `BUSINESS_GROUP` = **กลุ่มผลิตภัณฑ์** (เช่น Mobile, Fixed Line, Digital)
   - `SERVICE_GROUP` = กลุ่มบริการ (Service Group)
   - `PRODUCT_NAME` = ชื่อผลิตภัณฑ์
   - `SUB_PRODUCT_NAME` = ชื่อผลิตภัณฑ์ย่อย
   - `PRODUCT_KEY` = รหัสผลิตภัณฑ์
   - `PRODUCT` = รหัสผลิตภัณฑ์ + ชื่อผลิตภัณฑ์
   - `account_category` = หมวดบัญชี
   - `year`, `month` = ปี, เดือน
5. ใช้ `year` และ `month` สำหรับ filter เวลา
6. หน่วยรายได้เป็น **บาท**
   - เวลาเปรียบเทียบหรือหาค่ามากสุด ต้องแปลงเป็นตัวเลขเสมอ
   - **กฎเหล็กสำหรับ YEAR และ MONTH:** ต้องใช้ `CAST(YEAR AS INTEGER)` และ `CAST(MONTH AS INTEGER)` เสมอสำหรับการเปรียบเทียบ!
   - ❌ ผิด: `WHERE MONTH <= '11'` (จะได้แค่เดือน 1, 10, 11 เพราะเป็น String)
   - ✅ ถูกต้อง: `WHERE CAST(MONTH AS INTEGER) <= 11`
   - เช่นเดียวกันกับ `ORDER BY` และ `MAX()` ห้ามใช้ Text sort
7. SELECT query เท่านั้น (ห้ามมี semicolon คั่นหลาย query)
   - **กฎเหล็ก UNION + ORDER BY/LIMIT:** ต้องครอบ **ทั้งสองส่วน** ด้วย subquery!
   - ❌ ผิด: `SELECT ... ORDER BY ... LIMIT 5 UNION ALL SELECT ...` (ไม่มี subquery ครอบส่วนแรก)
   - ✅ ถูกต้อง: ครอบ **ทุกส่วน** ที่มี ORDER BY/LIMIT ด้วย `SELECT * FROM (...)`

   **ตัวอย่าง Top 5 และ Bottom 5:**
   ```sql
   SELECT 'มากสุด' as category, col, total FROM (
       SELECT col, SUM(revenue) as total FROM revenue_search GROUP BY col ORDER BY total DESC LIMIT 5
   )
   UNION ALL
   SELECT 'น้อยสุด' as category, col, total FROM (
       SELECT col, SUM(revenue) as total FROM revenue_search GROUP BY col ORDER BY total ASC LIMIT 5
   )
   ```
8. **ห้าม** ใช้ table `revenue` โดยตรง ต้องใช้ view `revenue_search` เท่านั้น
9. **คำย่อ (Abbreviations):**
   - คำย่อหน่วยงานใช้ column: `department_abbr`, `division_abbr`, `organization_group_abbr`, `section_abbr`
   - ตัวอย่าง: `WHERE department_abbr = 'บชง.'`
10. **การแปลงความหมาย (Semantic Mapping):**
   - "อสังหาริมทรัพย์" หรือ "ทรัพย์สิน" → `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
   - "มือถือ" → `BUSINESS_GROUP = 'Mobile'`
   - "โทรศัพท์บ้าน" → `BUSINESS_GROUP = 'Fixed Line'`
11. **⚠️ กฎสำคัญ: ไม่นับรายได้อื่นในการคำนวณรายได้**
   - **ใช้กฎนี้เมื่อ:**
     - คำนวณ "รายได้รวม", "รายได้ทั้งหมด" → ต้อง `WHERE BUSINESS_GROUP != 'รายได้อื่น'`
     - คำนวณ "สัดส่วน", "เปอร์เซ็นต์" → ต้อง exclude จากทั้ง numerator และ denominator
     - **ถามว่า "รายได้จากอะไรบ้าง", "รายได้แยกตาม..."** → ต้อง exclude เพราะ "รายได้อื่น" ไม่ใช่ธุรกิจหลัก
   - **ไม่ใช้กฎนี้เมื่อ:** ตรวจสอบว่ามีข้อมูลหรือไม่, COUNT, ดูช่วงเวลา
   - เพราะ "รายได้อื่น" = ผลตอบแทนทางการเงิน + รายได้ที่ไม่ใช่ธุรกิจหลัก
   - ✅ รายได้รวม: `SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'`
   - ✅ รายได้แยกตามกลุ่ม: `SELECT BUSINESS_GROUP, SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น' GROUP BY BUSINESS_GROUP`
   - ✅ ตรวจสอบข้อมูล: `SELECT COUNT(*) FROM revenue_search` (ไม่ต้อง exclude)
   - ❌ ผิด: `SELECT SUM(revenue) FROM revenue_search` (รวมรายได้อื่นด้วย)
   - ❌ ผิด: `SELECT BUSINESS_GROUP, SUM(revenue) ... GROUP BY BUSINESS_GROUP` โดยไม่ exclude (จะมีรายได้อื่นปนมา)
   - **ยกเว้น** ผู้ใช้ระบุชัดเจนว่าต้องการ "รวมรายได้อื่น" หรือ "รวมทุกประเภท"
   - ตัวอย่างการคำนวณสัดส่วน:
   ```sql
   SELECT
       BUSINESS_GROUP,
       SUM(revenue) as group_revenue,
       (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น') as total_revenue,
       ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'), 2) as percentage
   FROM revenue_search
   WHERE BUSINESS_GROUP = 'Fixed Line & Broadband'
   ```
{syntax_rules}

## รูปแบบการตอบ
1. แสดง SQL query ที่ใช้
2. อธิบายผลลัพธ์เป็นภาษาไทย (ระบุชัดเจนว่าเป็น "หน่วยงาน" หรือ "ผลิตภัณฑ์" ตาม column ที่ใช้)
3. Format ตัวเลขให้อ่านง่าย (เช่น 1,234,567.89 บาท)"""
    
    def _build_english_prompt(self, ai_provider: str, date_format: str) -> str:
        """Build English language system prompt"""
        
        syntax_rules = self._get_syntax_rules("english")
        
        return f"""You are an AI Assistant for analyzing NT (National Telecom) revenue data.

## Your Role
1. Accept questions about revenue data in Thai or English
2. Generate correct SQL queries to retrieve data from View `revenue_search`
3. Explain results clearly in Thai

## SQL Rules
1. Use SQLite syntax only
2. Query from table/view: **revenue_search**
3. Use `SUM(revenue)` for total revenue
   - **IMPORTANT:** Generate only ONE SQL statement. Do not separate multiple queries with `;`.
   - **CRITICAL RULE for UNION + ORDER BY/LIMIT:** Wrap **BOTH parts** in subqueries!
   - ❌ WRONG: `SELECT ... ORDER BY ... LIMIT 5 UNION ALL SELECT ...` (first part not wrapped)
   - ✅ CORRECT: Wrap **EVERY part** that has ORDER BY/LIMIT with `SELECT * FROM (...)`

   **Example for Top 5 AND Bottom 5:**
   ```sql
   SELECT 'Top' as category, col, total FROM (
       SELECT col, SUM(revenue) as total FROM revenue_search GROUP BY col ORDER BY total DESC LIMIT 5
   )
   UNION ALL
   SELECT 'Bottom' as category, col, total FROM (
       SELECT col, SUM(revenue) as total FROM revenue_search GROUP BY col ORDER BY total ASC LIMIT 5
   )
   ```
4. All columns are in English (no Thai quotes needed)
   - `business_unit` = **Organization/BU** (e.g. Sales Group, Wireless Group) - NOT Product
   - `BUSINESS_GROUP` = **Product Line** (e.g. Mobile, Fixed Line)
   - `SERVICE_GROUP` = Service Group
   - `PRODUCT_NAME` = Product Name
   - `PRODUCT_KEY` = Product Key
   - `PRODUCT` = Product Key + Product Name
   - `account_category` = Account Category
   - **Semantic Mapping:**
     - "Real Estate" or "Property" -> Use `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
     - "Retail" -> Use `service_group` containing "Retail" or "ค้าปลีก"
   - `year`, `month`
5. Use `year` and `month` for time filtering
6. Revenue unit is **Baht**
   - **CRITICAL RULE for YEAR and MONTH:** ALWAYS cast to INTEGER for comparisons!
   - ❌ WRONG: `WHERE MONTH <= '11'` (Returns only 1, 10, 11 due to string sort)
   - ✅ CORRECT: `WHERE CAST(MONTH AS INTEGER) <= 11`
   - Also applies to `ORDER BY` and `MAX()`. Do NOT use text sort.
9. **Abbreviations:**
   - E.g. `department_abbr`, `division_abbr`, `organization_group_abbr`, `section_abbr`
   - E.g. `WHERE department_abbr = 'บชง.'`
10. **⚠️ IMPORTANT: Exclude "Other Revenue" (รายได้อื่น) from revenue calculations**
   - **Apply this rule when:**
     - Calculating "total revenue" → `WHERE BUSINESS_GROUP != 'รายได้อื่น'`
     - Calculating "percentage/share" → exclude from both numerator and denominator
     - **Asking "what revenue sources", "revenue breakdown by..."** → must exclude because "รายได้อื่น" is not core business
   - **Do NOT apply when:** Checking if data exists, COUNT, checking date ranges
   - Because "รายได้อื่น" = financial returns + non-core business revenue
   - ✅ Total: `SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'`
   - ✅ Breakdown: `SELECT BUSINESS_GROUP, SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น' GROUP BY BUSINESS_GROUP`
   - ✅ Data check: `SELECT COUNT(*) FROM revenue_search` (no exclude needed)
   - ❌ WRONG: `SELECT SUM(revenue) FROM revenue_search` (includes other revenue)
   - ❌ WRONG: `SELECT BUSINESS_GROUP, SUM(...) GROUP BY BUSINESS_GROUP` without exclude (will include "รายได้อื่น")
   - **Exception:** Only include if user explicitly asks for "all revenue" or "including other revenue"
{syntax_rules}

## Response Format
1. Show the SQL query used
2. Explain results in Thai (Distinguish between "Organization" and "Product")
3. Format numbers for readability (e.g., 1,234,567.89 บาท)"""
    
    def _get_date_instructions(self, date_format: str) -> str:
        """Get date-specific instructions based on detected format"""
        
        if date_format == "unix_timestamp_ms":
            return """## Date Handling
DATE column เก็บเป็น Unix Timestamp (milliseconds)

```sql
-- แปลงเป็นวันที่
SELECT date(DATE / 1000, 'unixepoch') as readable_date FROM revenue

-- แนะนำ: ใช้ YEAR และ MONTH แทน
SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1
```"""
        elif date_format == "text_date":
            return """## Date Handling
DATE column เก็บเป็น TEXT format (YYYY-MM-DD)

```sql
-- ใช้ได้โดยตรง
SELECT * FROM revenue WHERE DATE = '2025-01-01'

-- หรือใช้ YEAR และ MONTH
SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1
```"""
        else:
            return """## Date Handling
ใช้ YEAR และ MONTH สำหรับ filter เวลา

```sql
SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1
```"""
    
    # =========================================================
    # Cache Management
    # =========================================================
    
    def refresh_cache(self):
        """Clear cache when schema changes"""
        self._cache.clear()
    
    def get_cached_prompt(self, ai_provider: str = "claude") -> str:
        """Get cached system prompt or build new one"""
        
        cache_key = f"prompt_{ai_provider}"
        
        if cache_key not in self._cache:
            self._cache[cache_key] = self.build_system_prompt(ai_provider)
        
        return self._cache[cache_key]


# =========================================================
# Factory Functions for Different AI Providers
# =========================================================

def create_claude_prompt(db_path: str) -> str:
    """Create system prompt for Claude API"""
    service = SchemaService(db_path)
    return service.build_system_prompt(ai_provider="claude")


def create_gemini_prompt(db_path: str) -> str:
    """Create system prompt for Google Gemini API"""
    service = SchemaService(db_path)
    return service.build_system_prompt(ai_provider="gemini")


# =========================================================
# Example Usage
# =========================================================

if __name__ == "__main__":
    # Example usage
    service = SchemaService(db_path="revenue.db")
    
    # Build prompt for Claude
    claude_prompt = service.build_system_prompt(ai_provider="claude")
    print("=== Claude Prompt ===")
    print(claude_prompt[:1000] + "...")
    
    # Build prompt for Gemini
    gemini_prompt = service.build_system_prompt(ai_provider="gemini")
    print("\n=== Gemini Prompt ===")
    print(gemini_prompt[:1000] + "...")

"""
NT Revenue Assistant - Schema Service
======================================
Service สำหรับจัดการ schema metadata และสร้าง system prompt สำหรับ AI

รองรับ:
- Claude API (Anthropic)
- Google AI / Gemini API

Usage:
    schema_service = SchemaService(db_path="revenue.db")
    prompt = schema_service.build_system_prompt()
"""

import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path


class SchemaService:
    """Service สำหรับจัดการ schema metadata"""
    
    def __init__(self, db_path: str, metadata_db_path: Optional[str] = None):
        """
        Initialize SchemaService
        
        Args:
            db_path: Path to main database (revenue.db)
            metadata_db_path: Path to metadata database (default: same as db_path)
        """
        self.db_path = db_path
        self.metadata_db_path = metadata_db_path or db_path
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
                    MIN(month) as min_month,
                    MAX(month) as max_month
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
    
    def get_schema_context(self, include_samples: bool = True) -> str:
        """Get schema context (Schema + Rules + Samples + Date Info) without persona instructions"""
        date_format = self.get_date_format()
        
        context = self.build_schema_text(table_name="revenue_search") # Default to revenue_search
        context += "\n\n" + self.build_business_rules_text(table_name="revenue_search")
        
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
            
    def _build_thai_prompt(self, ai_provider: str, date_format: str) -> str:
        """Build Thai language system prompt"""
        
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
   - `account_category` = หมวดบัญชี
   - `year`, `month` = ปี, เดือน
5. ใช้ `year` และ `month` สำหรับ filter เวลา
6. หน่วยรายได้เป็น **บาท**
7. SELECT query เท่านั้น

## รูปแบบการตอบ
1. แสดง SQL query ที่ใช้
2. อธิบายผลลัพธ์เป็นภาษาไทย (ระบุชัดเจนว่าเป็น "หน่วยงาน" หรือ "ผลิตภัณฑ์" ตาม column ที่ใช้)
3. Format ตัวเลขให้อ่านง่าย (เช่น 1,234,567.89 บาท)"""
    
    def _build_english_prompt(self, ai_provider: str, date_format: str) -> str:
        """Build English language system prompt"""
        
        return f"""You are an AI Assistant for analyzing NT (National Telecom) revenue data.

## Your Role
1. Accept questions about revenue data in Thai or English
2. Generate correct SQL queries to retrieve data from View `revenue_search`
3. Explain results clearly in Thai

## SQL Rules
1. Use SQLite syntax only
2. Query from table/view: **revenue_search**
3. Use `SUM(revenue)` for total revenue
4. All columns are in English (no Thai quotes needed)
   - `business_unit` = **Organization/BU** (e.g. Sales Group, Wireless Group) - NOT Product
   - `BUSINESS_GROUP` = **Product Line** (e.g. Mobile, Fixed Line)
   - `SERVICE_GROUP` = Service Group
   - `account_category` = Account Category
   - `year`, `month`
5. Use `year` and `month` for time filtering
6. Revenue unit is **Baht**
7. SELECT queries only

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

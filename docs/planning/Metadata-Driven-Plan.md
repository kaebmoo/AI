จากการศึกษาโครงการนี้ ผมเจอปัญหา Matcha model ไม่เก่งจริง ๆ ครับ โดยเฉพาะเรื่องการเข้าใจ context ธุรกิจไทยและการสร้าง SQL ที่ถูกต้อง

## 🔍 วิเคราะห์ปัญหา Matcha

จาก code ที่เห็น มีจุดที่สามารถปรับปรุงได้หลายจุด:

### 1. ปรับ System Prompt สำหรับ Matcha

**ปัจจุบันใน `ai_service.py` สำหรับ Matcha** ใช้ prompt เดียวกับ OpenAI ทั่วไป ควรปรับให้เฉพาะกับ Matcha:

```python
# เพิ่มใน MatchaProvider class
def _build_enhanced_matcha_prompt(self) -> str:
    """Enhanced prompt specifically for Matcha"""
    return """คุณเป็น AI ผู้เชี่ยวชาญด้านการวิเคราะห์ข้อมูลรายได้ของ NT Telecom ประเทศไทย

## ความสามารถพิเศษ
- เข้าใจคำย่อไทย เช่น "นป.", "บชง.", "สญ."
- แปลงคำถามภาษาไทยเป็นคำสั่ง SQL ที่ถูกต้อง
- ใช้งานฐานข้อมูล SQLite ผ่าน view `revenue_search`

## หลักการสร้าง SQL
### 1. แปลงคำถามเป็นคำสั่ง SQL
- "รายได้ นป. มกราคม 2568" → `SELECT SUM(revenue) FROM revenue_search WHERE department_abbr = 'นป.' AND year = 2025 AND month = 1`
- "รายได้มือถือ" → `SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP = 'Mobile'`

### 2. ใช้ columns ที่ถูกต้อง
- business_unit: โครงสร้างหน่วยงาน (ไม่ใช่ผลิตภัณฑ์)
- BUSINESS_GROUP: กลุ่มผลิตภัณฑ์ (Mobile, Fixed Line, Digital)
- department_abbr: คำย่อฝ่าย (เช่น 'บชง.', 'ลขบ.')
- year, month: ใช้ตัวเลขโดยตรง

### 3. รูปแบบการตอบ
ต้องตอบในรูปแบบ:
```sql
[SQL QUERY ที่สมบูรณ์]
```

คำอธิบาย: [อธิบายเป็นภาษาไทยสั้นๆ]"""
```

### 2. เพิ่ม Few-Shot Examples สำหรับ Matcha

สร้างไฟล์ `app/services/matcha_examples.py`:

```python
# matcha_examples.py
MATCHA_EXAMPLES = [
    {
        "question": "รายได้รวมเดือนมกราคม 2568",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE year = 2025 AND month = 1",
        "explanation": "รายได้รวมทั้งหมดในเดือนมกราคม 2568"
    },
    {
        "question": "รายได้ นป. ปี 2568",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE department_abbr = 'นป.' AND year = 2025",
        "explanation": "รายได้ของกลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ ปี 2568"
    },
    {
        "question": "รายได้มือถือแยกตามเดือน",
        "sql": "SELECT month, SUM(revenue) as total_revenue FROM revenue_search WHERE BUSINESS_GROUP = 'Mobile' GROUP BY month ORDER BY month",
        "explanation": "รายได้จากมือถือแยกตามเดือน"
    },
    {
        "question": "อสังหาริมทรัพย์ทั้งหมด",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'",
        "explanation": "รายได้จากอสังหาริมทรัพย์ทั้งหมด"
    },
    {
        "question": "รายได้สูงสุด 5 อันดับแรก",
        "sql": "SELECT BUSINESS_GROUP, SUM(revenue) as total_revenue FROM revenue_search GROUP BY BUSINESS_GROUP ORDER BY total_revenue DESC LIMIT 5",
        "explanation": "5 กลุ่มผลิตภัณฑ์ที่มีรายได้สูงสุด"
    }
]

def get_matcha_few_shot_examples() -> str:
    """Get formatted few-shot examples for Matcha"""
    examples_text = "## ตัวอย่างคำถามและคำตอบ\n\n"
    
    for i, example in enumerate(MATCHA_EXAMPLES, 1):
        examples_text += f"### ตัวอย่างที่ {i}\n"
        examples_text += f"**คำถาม:** {example['question']}\n"
        examples_text += f"**SQL:**\n```sql\n{example['sql']}\n```\n"
        examples_text += f"**คำอธิบาย:** {example['explanation']}\n\n"
    
    return examples_text
```

### 3. ปรับ MatchaProvider ให้ใช้ Enhanced Prompt

```python
# ใน ai_service.py, แก้ MatchaProvider.generate_sql()
def generate_sql(self, question: str, system_prompt: str, history: List[Dict] = []) -> Dict[str, Any]:
    """Generate SQL using Matcha with enhanced prompt"""
    
    from app.services.matcha_examples import get_matcha_few_shot_examples
    
    # เพิ่ม few-shot examples เข้าไปใน prompt
    enhanced_prompt = system_prompt + "\n\n" + get_matcha_few_shot_examples()
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {self.api_key}'
    }

    # เพิ่ม few-shot examples ใน messages
    messages = [{"role": "system", "content": enhanced_prompt}]
    
    # เพิ่ม examples เป็น few-shot
    for example in MATCHA_EXAMPLES:
        messages.append({"role": "user", "content": example["question"]})
        messages.append({"role": "assistant", "content": f"```sql\n{example['sql']}\n```\n\nคำอธิบาย: {example['explanation']}"})
    
    # เพิ่ม history และคำถามปัจจุบัน
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    payload = {
        'model': self.model,
        'messages': messages,
        'temperature': 0.1,  # ลด temperature เพื่อให้ตอบตรง
        'max_tokens': 800,
        'top_p': 0.9
    }

    try:
        with httpx.Client(verify=False, timeout=60.0) as client:
            response = client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
        ai_message = result['choices'][0]['message']['content']
        total_tokens = result.get('usage', {}).get('total_tokens', 0)
        
        # Enhanced SQL extraction for Matcha
        sql, explanation = self._extract_sql_and_explanation(ai_message)
        
        return {
            "sql": sql,
            "explanation": explanation,
            "tokens_used": total_tokens,
            "raw_response": ai_message
        }
        
    except Exception as e:
        logger.error(f"Matcha API Error: {str(e)}")
        raise

def _extract_sql_and_explanation(self, text: str) -> tuple[str, str]:
    """Enhanced SQL extraction for Matcha responses"""
    
    # หา SQL จาก code block
    sql_pattern = r'```sql\s*(.*?)\s*```'
    sql_match = re.search(sql_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not sql_match:
        # ถ้าไม่มี code block ลองหา SELECT statement
        select_pattern = r'(SELECT\s+.*?)(?:\n\n|คำอธิบาย|$)'
        select_match = re.search(select_pattern, text, re.DOTALL | re.IGNORECASE)
        if select_match:
            sql = select_match.group(1).strip()
        else:
            sql = None
    else:
        sql = sql_match.group(1).strip()
    
    # หาคำอธิบาย
    explanation_pattern = r'คำอธิบาย[:\s]*(.*?)(?:\n\n|$)'
    explanation_match = re.search(explanation_pattern, text, re.DOTALL)
    
    if explanation_match:
        explanation = explanation_match.group(1).strip()
    else:
        # ใช้ข้อความหลัง SQL เป็นคำอธิบาย
        sql_end = sql_match.end() if sql_match else 0
        explanation = text[sql_end:].strip()
    
    return sql, explanation
```

### 4. เพิ่ม Semantic Mapping เฉพาะ Matcha

สร้างไฟล์ `app/services/matcha_semantic.py`:

```python
# matcha_semantic.py
MATCHA_SEMANTIC_MAPPING = {
    # คำย่อหน่วยงาน
    "นป.": {"column": "department_abbr", "value": "นป.", "description": "กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ"},
    "บชง.": {"column": "department_abbr", "value": "บชง.", "description": "ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ"},
    "สญ.": {"column": "division_abbr", "value": "สญ.", "description": "สายงานขายและบริการ"},
    "ลขบ.": {"column": "department_abbr", "value": "ลขบ.", "description": "ฝ่ายเลขานุการผู้บริหาร"},
    
    # คำศัพท์ธุรกิจ
    "มือถือ": {"column": "BUSINESS_GROUP", "value": "Mobile", "description": "กลุ่มผลิตภัณฑ์มือถือ"},
    "โทรศัพท์บ้าน": {"column": "BUSINESS_GROUP", "value": "Fixed Line", "description": "กลุ่มผลิตภัณฑ์โทรศัพท์บ้าน"},
    "อินเทอร์เน็ต": {"column": "BUSINESS_GROUP", "value": "Digital", "description": "กลุ่มผลิตภัณฑ์ดิจิทัล"},
    "อสังหาริมทรัพย์": {"column": "SERVICE_GROUP", "value": "กลุ่มบริการพัฒนาสินทรัพย์", "description": "รายได้จากอสังหาริมทรัพย์"},
    "ทรัพย์สิน": {"column": "SERVICE_GROUP", "value": "กลุ่มบริการพัฒนาสินทรัพย์", "description": "รายได้จากสินทรัพย์"},
    
    # คำพ้องความหมาย
    "เดือนมกราคม": {"column": "month", "value": 1, "description": "มกราคม"},
    "เดือนกุมภาพันธ์": {"column": "month", "value": 2, "description": "กุมภาพันธ์"},
    "ปี 2568": {"column": "year", "value": 2025, "description": "ปี 2568"},
    "รายได้รวม": {"sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search", "description": "รายได้ทั้งหมด"},
}

def enhance_question_for_matcha(question: str) -> str:
    """Enhance question with semantic mapping hints for Matcha"""
    
    enhanced = question
    
    # แปลงคำย่อ
    for keyword, mapping in MATCHA_SEMANTIC_MAPPING.items():
        if keyword in question:
            enhanced += f"\n\nหมายเหตุ: '{keyword}' หมายถึง {mapping['column']} = '{mapping['value']}' ({mapping['description']})"
    
    return enhanced
```

### 5. ใช้ Enhanced Question Processing

```python
# ใน AIService.query_with_retry() เพิ่มสำหรับ Matcha
if self.provider_name == "matcha":
    enhanced_question = enhance_question_for_matcha(question)
    ai_result = self.provider.generate_sql(enhanced_question, self.system_prompt, history)
else:
    ai_result = self.provider.generate_sql(question, self.system_prompt, history)
```

### 6. เพิ่ม Validation สำหรับ Matcha

```python
# เพิ่มใน SchemaService
def validate_matcha_response(self, sql: str, question: str) -> Dict[str, Any]:
    """Validate and correct Matcha SQL responses"""
    
    issues = []
    corrections = {}
    
    # ตรวจสอบ table name
    if "FROM revenue" in sql and "FROM revenue_search" not in sql:
        issues.append("ใช้ผิด table name")
        corrections["table"] = "revenue_search"
    
    # ตรวจสอบ column names
    invalid_columns = ["กลุ่มธุรกิจ", "หมวดบัญชี"]  # columns ที่ไม่ควรใช้
    for col in invalid_columns:
        if f'"{col}"' in sql:
            issues.append(f"ใช้ column ไทย: {col}")
            corrections["columns"] = "ใช้ columns ภาษาอังกฤษแทน"
    
    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "corrections": corrections
    }
```

### สรุปวิธีปรับปรุง Matcha

1. **Enhanced Prompt**: เพิ่ม few-shot examples และ context เฉพาะ
2. **Semantic Mapping**: แปลงคำถามไทยเป็นคำสั่ง SQL ที่ถูกต้อง
3. **Validation Layer**: ตรวจสอบและแก้ไข SQL ที่ Matcha สร้าง
4. **Retry Mechanism**: ใช้ query_with_retry() ที่มีอยู่แล้ว
5. **Temperature Tuning**: ลด randomness ให้ตอบตรงมากขึ้น

วิธีนี้จะช่วยให้ Matcha เข้าใจคำถามภาษาไทยได้ดีขึ้น และสร้าง SQL ที่ถูกต้องมากขึ้นครับ


เนื่องจากไม่สามารถเข้าถึงไฟล์จริงได้ ผมจะใช้ข้อมูลจาก schema ที่มีในโครงการและเสนอวิธี metadata-driven ที่ scalable สำหรับหลาย datasets

## 🎯 วิธี Metadata-Driven สำหรับหลาย Datasets

### 1. สร้าง Universal Schema Framework

**ไฟล์ใหม่: `app/services/universal_schema_service.py`**

```python
"""
Universal Schema Service สำหรับหลาย datasets
รองรับ: revenue, expenses, operations และ datasets อื่นๆ
"""

from typing import Dict, List, Optional, Any
import sqlite3
import json
from dataclasses import dataclass

@dataclass
class DatasetConfig:
    """Configuration สำหรับแต่ละ dataset"""
    name: str
    table_name: str
    primary_column: str
    value_column: str
    date_columns: List[str]
    category_columns: List[str]
    semantic_mappings: Dict[str, Dict[str, Any]]

class UniversalSchemaService:
    """Service ที่ใช้ metadata จาก database จริง ไม่ hard-code"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._dataset_configs: Dict[str, DatasetConfig] = {}
        self._load_dataset_configs()
    
    def _load_dataset_configs(self):
        """โหลด configuration จาก database metadata tables"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            cursor = conn.cursor()
            
            # 1. โหลด dataset configurations
            cursor.execute("""
                SELECT * FROM dataset_configs 
                WHERE is_active = 1
            """)
            
            for row in cursor.fetchall():
                config = DatasetConfig(
                    name=row['dataset_name'],
                    table_name=row['table_name'],
                    primary_column=row['primary_value_column'],
                    value_column=row['value_column'],
                    date_columns=json.loads(row['date_columns']),
                    category_columns=json.loads(row['category_columns']),
                    semantic_mappings={}
                )
                self._dataset_configs[row['dataset_name']] = config
            
            # 2. โหลด semantic mappings
            cursor.execute("""
                SELECT dataset_name, keyword, target_column, target_condition, description
                FROM semantic_mappings 
                WHERE is_active = 1
            """)
            
            for row in cursor.fetchall():
                ds_name = row['dataset_name']
                if ds_name in self._dataset_configs:
                    self._dataset_configs[ds_name].semantic_mappings[row['keyword']] = {
                        'column': row['target_column'],
                        'condition': row['target_condition'],
                        'description': row['description']
                    }
                    
        except sqlite3.OperationalError:
            # ถ้า tables ไม่มี สร้าง default config
            self._create_default_configs()
        finally:
            conn.close()
    
    def _create_default_configs(self):
        """สร้าง default configurations ถ้า metadata tables ยังไม่มี"""
        
        # Revenue dataset
        self._dataset_configs['revenue'] = DatasetConfig(
            name='revenue',
            table_name='revenue_search',
            primary_column='revenue',
            value_column='revenue',
            date_columns=['year', 'month'],
            category_columns=['business_unit', 'BUSINESS_GROUP', 'SERVICE_GROUP', 'department_abbr'],
            semantic_mappings={
                # คำย่อ
                'นป.': {'column': 'department_abbr', 'condition': "= 'นป.'", 'description': 'กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ'},
                'บชง.': {'column': 'department_abbr', 'condition": "= 'บชง.'", 'description': 'ฝ่ายบัญชีบริหาร'},
                
                # คำศัพท์
                'มือถือ': {'column': 'BUSINESS_GROUP', 'condition': "= 'Mobile'", 'description': 'กลุ่มผลิตภัณฑ์มือถือ'},
                'อสังหา': {'column': 'SERVICE_GROUP', 'condition': "LIKE '%พัฒนาสินทรัพย์%'", 'description': 'รายได้จากอสังหาริมทรัพย์'}
            }
        )
        
        # Expenses dataset
        self._dataset_configs['expenses'] = DatasetConfig(
            name='expenses',
            table_name='expenses',
            primary_column='expense_value',
            value_column='expense_value',
            date_columns=['year', 'month'],
            category_columns=['expense_category', 'cost_center', 'department'],
            semantic_mappings={
                'ค่าใช้จ่าย': {'column': 'expense_category', 'condition': 'IS NOT NULL', 'description': 'ค่าใช้จ่ายทั้งหมด'},
                'ค่าไฟ': {'column': 'expense_category', 'condition": "= 'Utilities'", 'description': 'ค่าใช้จ่ายด้านสาธารณูปโภค'}
            }
        )
        
        # Operations dataset
        self._dataset_configs['operations'] = DatasetConfig(
            name='operations',
            table_name='operations',
            primary_column='performance_value',
            value_column='performance_value',
            date_columns=['year', 'month', 'quarter'],
            category_columns=['operation_type', 'kpi_name', 'department'],
            semantic_mappings={
                'ผลดำเนินงาน': {'column': 'kpi_name', 'condition': 'IS NOT NULL', 'description': 'ผลการดำเนินงานทั้งหมด'},
                'kpi': {'column': 'kpi_name', 'condition': 'IS NOT NULL', 'description': 'ตัวชี้วัดผลดำเนินงาน'}
            }
        )
    
    def get_dataset_context(self, dataset_name: str, include_samples: bool = True) -> str:
        """สร้าง context สำหรับแต่ละ dataset โดยไม่ hard-code"""
        
        if dataset_name not in self._dataset_configs:
            return f"Dataset '{dataset_name}' not found"
        
        config = self._dataset_configs[dataset_name]
        
        # ดึง schema จริงจาก database
        schema_info = self._get_real_schema(config.table_name)
        
        context = f"""
## Dataset: {dataset_name.upper()}
**Table:** {config.table_name}
**Value Column:** {config.value_column} (หน่วย: บาท)
**Date Columns:** {', '.join(config.date_columns)}

### Schema
{schema_info}

### Semantic Mappings
{"| Keyword | Maps to | Description |"}
{"|---------|---------|-------------|"}
"""
        
        for keyword, mapping in config.semantic_mappings.items():
            context += f"| {keyword} | {mapping['column']} {mapping['condition']} | {mapping['description']} |\n"
        
        if include_samples:
            samples = self._get_sample_values(config.table_name, config.category_columns[:3])
            context += f"\n### Sample Values\n{samples}"
        
        return context
    
    def _get_real_schema(self, table_name: str) -> str:
        """ดึง schema จริงจาก database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            schema = "| Column | Type | Nullable | Default |\n"
            schema += "|--------|------|----------|---------|\n"
            
            for col in columns:
                schema += f"| {col['name']} | {col['type']} | {'Yes' if col['notnull'] == 0 else 'No'} | {col['dflt_value'] or ''} |\n"
            
            return schema
        except sqlite3.OperationalError as e:
            return f"Error loading schema: {str(e)}"
        finally:
            conn.close()
    
    def _get_sample_values(self, table_name: str, columns: List[str]) -> str:
        """ดึง sample values จริงจาก database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        samples = ""
        
        for col in columns:
            try:
                cursor.execute(f"""
                    SELECT DISTINCT {col} 
                    FROM {table_name} 
                    WHERE {col} IS NOT NULL 
                    LIMIT 5
                """)
                values = [row[0] for row in cursor.fetchall()]
                samples += f"\n**{col}:** {', '.join(map(str, values))}"
            except:
                pass
        
        conn.close()
        return samples
    
    def build_dynamic_system_prompt(self, dataset_name: str, ai_provider: str = "matcha") -> str:
        """สร้าง system prompt แบบ dynamic สำหรับแต่ละ dataset"""
        
        context = self.get_dataset_context(dataset_name)
        
        return f"""คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูล {dataset_name}

{context}

## กฎการสร้าง SQL
1. ใช้ table: {self._dataset_configs[dataset_name].table_name}
2. ใช้ value column: {self._dataset_configs[dataset_name].value_column}
3. ใช้ date columns: {', '.join(self._dataset_configs[dataset_name].date_columns)}
4. ใช้ semantic mappings ที่กำหนดใน context
5. สร้างเฉพาะ SELECT query
6. อธิบายผลลัพธ์เป็นภาษาไทย

ตัวอย่างการใช้งาน:
- ถาม "รายได้ นป. มกราคม 2568" → ใช้ mapping "นป." และ year=2025, month=1
- ถาม "ค่าใช้จ่ายไฟฟ้า 2568" → ใช้ dataset=expenses และ expense_category="Utilities"
"""
```

### 2. สร้าง Database Schema สำหรับ Metadata

**ไฟล์: `database/migrations/004_universal_metadata.sql`**

```sql
-- Universal Metadata Tables for Multiple Datasets

-- Dataset configurations
CREATE TABLE IF NOT EXISTS dataset_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL UNIQUE,
    table_name TEXT NOT NULL,
    primary_value_column TEXT NOT NULL,
    value_column TEXT NOT NULL,
    date_columns TEXT NOT NULL, -- JSON array
    category_columns TEXT NOT NULL, -- JSON array
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Semantic mappings for each dataset
CREATE TABLE IF NOT EXISTS semantic_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    keyword_type TEXT NOT NULL, -- abbreviation, business_term, synonym
    target_column TEXT NOT NULL,
    target_condition TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dataset_name) REFERENCES dataset_configs(dataset_name)
);

-- Business rules for each dataset
CREATE TABLE IF NOT EXISTS dataset_business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    severity TEXT DEFAULT 'info', -- info, warning, error
    example_correct TEXT,
    example_wrong TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dataset_name) REFERENCES dataset_configs(dataset_name)
);

-- ตัวอย่างข้อมูลเริ่มต้น
INSERT OR IGNORE INTO dataset_configs VALUES
(1, 'revenue', 'revenue_search', 'revenue', 'revenue', '["year", "month"]', '["business_unit", "BUSINESS_GROUP", "SERVICE_GROUP", "department_abbr"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(2, 'expenses', 'expenses', 'expense_value', 'expense_value', '["year", "month"]', '["expense_category", "cost_center", "department"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(3, 'operations', 'operations', 'performance_value', 'performance_value', '["year", "month", "quarter"]', '["operation_type", "kpi_name", "department"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- ตัวอย่าง semantic mappings
INSERT OR IGNORE INTO semantic_mappings (dataset_name, keyword, keyword_type, target_column, target_condition, description, priority) VALUES
('revenue', 'นป.', 'abbreviation', 'department_abbr', "= 'นป.'", 'กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ', 90),
('revenue', 'บชง.', 'abbreviation', 'department_abbr', "= 'บชง.'", 'ฝ่ายบัญชีบริหาร', 90),
('revenue', 'มือถือ', 'business_term', 'BUSINESS_GROUP', "= 'Mobile'", 'กลุ่มผลิตภัณฑ์มือถือ', 80),
('expenses', 'ค่าใช้จ่าย', 'business_term', 'expense_category', 'IS NOT NULL', 'ค่าใช้จ่ายทั้งหมด', 100),
('expenses', 'ค่าไฟ', 'business_term', 'expense_category', "= 'Utilities'", 'ค่าใช้จ่ายด้านสาธารณูปโภค', 85),
('operations', 'kpi', 'business_term', 'kpi_name', 'IS NOT NULL', 'ตัวชี้วัดผลดำเนินงาน', 90);
```

### 3. ปรับ AI Service ให้รองรับหลาย datasets

**ไฟล์: `app/services/enhanced_ai_service.py`**

```python
"""
Enhanced AI Service รองรับหลาย datasets
ใช้ metadata-driven approach ไม่ hard-code
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
from app.services.universal_schema_service import UniversalSchemaService

logger = logging.getLogger(__name__)

@dataclass
class DatasetQuery:
    """Query object สำหรับแต่ละ dataset"""
    dataset_name: str
    question: str
    sql_query: str
    data: List[Dict]
    explanation: str
    tokens_used: int
    provider: str

class EnhancedAIService:
    """AI Service ที่รองรับหลาย datasets ผ่าน metadata"""
    
    def __init__(self, provider: str, api_key: str, db_path: str, **kwargs):
        self.provider = provider
        self.api_key = api_key
        self.db_path = db_path
        self.universal_schema = UniversalSchemaService(db_path)
        self.kwargs = kwargs
        
    def detect_dataset(self, question: str) -> str:
        """ตรวจจับ dataset จากคำถาม โดยใช้ metadata"""
        
        # ใช้ keyword matching จาก semantic mappings
        for dataset_name, config in self.universal_schema._dataset_configs.items():
            for keyword in config.semantic_mappings:
                if keyword in question.lower():
                    return dataset_name
        
        # Default fallback
        return 'revenue'
    
    def query(self, question: str, dataset_name: Optional[str] = None) -> DatasetQuery:
        """Query โดยใช้ metadata-driven approach"""
        
        # Auto-detect dataset ถ้าไม่ระบุ
        if not dataset_name:
            dataset_name = self.detect_dataset(question)
        
        # ใช้ dynamic system prompt จาก metadata
        system_prompt = self.universal_schema.build_dynamic_system_prompt(dataset_name, self.provider)
        
        # ใช้ AI service เดิมแต่เปลี่ยน prompt
        from app.services.ai_service import AIService
        
        ai_service = AIService(
            provider=self.provider,
            api_key=self.api_key,
            db_path=self.db_path,
            **self.kwargs
        )
        
        # Override system prompt
        ai_service._system_prompt = system_prompt
        
        # Execute query
        result = ai_service.query(question)
        
        return DatasetQuery(
            dataset_name=dataset_name,
            question=question,
            sql_query=result.sql_query,
            data=result.data,
            explanation=result.explanation,
            tokens_used=result.tokens_used,
            provider=self.provider
        )
```

### 4. ตัวอย่างการใช้งาน

```python
# ตัวอย่างการใช้งานแบบ metadata-driven
service = EnhancedAIService(
    provider="matcha",
    api_key="your-key",
    db_path="nt_fi_report.sqlite",
    api_url="http://your-matcha-endpoint"
)

# สามารถถามข้าม datasets ได้เลย
result1 = service.query("รายได้ นป. มกราคม 2568")  # auto-detect revenue
result2 = service.query("ค่าใช้จ่ายไฟฟ้า 2568")    # auto-detect expenses
result3 = service.query("ผลดำเนินงาน kpi ภาคเหนือ") # auto-detect operations

# หรือระบุ dataset เอง
result4 = service.query("ค่าใช้จ่ายทั้งหมด", dataset_name="expenses")
```


## 🎯 สรุปวิธี Metadata-Driven สำหรับหลาย Datasets (ต่อให้เสร็จ)

### 5. สร้าง API Endpoints สำหรับหลาย datasets

**ไฟล์: `app/api/v1/universal.py`**

```python
"""
Universal API endpoints รองรับหลาย datasets
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel

from app.services.enhanced_ai_service import EnhancedAIService
from app.api.deps import get_current_user

router = APIRouter()

class UniversalQueryRequest(BaseModel):
    question: str
    dataset_name: Optional[str] = None
    explain: bool = True

class UniversalQueryResponse(BaseModel):
    dataset_name: str
    question: str
    sql_query: str
    data: List[dict]
    explanation: str
    tokens_used: int
    provider: str

@router.post("/query", response_model=UniversalQueryResponse)
async def universal_query(
    request: UniversalQueryRequest,
    current_user=Depends(get_current_user)
):
    """Query ข้อมูลจาก dataset ใดๆ โดยใช้ metadata-driven approach"""
    
    try:
        # ใช้ provider จาก user preference หรือ default
        from app.config import settings
        
        service = EnhancedAIService(
            provider=current_user.ai_provider or settings.DEFAULT_AI_PROVIDER,
            api_key=getattr(settings, f"{(current_user.ai_provider or settings.DEFAULT_AI_PROVIDER).upper()}_API_KEY"),
            db_path=settings.DATABASE_URL.replace("sqlite:///", "")
        )
        
        result = service.query(
            question=request.question,
            dataset_name=request.dataset_name
        )
        
        return UniversalQueryResponse(
            dataset_name=result.dataset_name,
            question=result.question,
            sql_query=result.sql_query,
            data=result.data,
            explanation=result.explanation,
            tokens_used=result.tokens_used,
            provider=result.provider
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/datasets")
async def list_datasets(current_user=Depends(get_current_user)):
    """แสดงรายการ datasets ที่พร้อมใช้งาน"""
    
    from app.services.universal_schema_service import UniversalSchemaService
    
    service = UniversalSchemaService(db_path="nt_fi_report.sqlite")
    
    datasets = []
    for name, config in service._dataset_configs.items():
        datasets.append({
            "name": name,
            "table_name": config.table_name,
            "description": f"ข้อมูล{name}",
            "value_column": config.value_column,
            "category_columns": config.category_columns
        })
    
    return {"datasets": datasets}

@router.get("/datasets/{dataset_name}/schema")
async def get_dataset_schema(
    dataset_name: str,
    current_user=Depends(get_current_user)
):
    """แสดง schema ของ dataset ที่ระบุ"""
    
    from app.services.universal_schema_service import UniversalSchemaService
    
    service = UniversalSchemaService(db_path="nt_fi_report.sqlite")
    
    if dataset_name not in service._dataset_configs:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    context = service.get_dataset_context(dataset_name)
    
    return {
        "dataset_name": dataset_name,
        "schema": context
    }
```

### 6. ปรับ Matcha Provider ให้ใช้ Metadata

**ไฟล์: `app/services/matcha_enhanced_provider.py`**

```python
"""
Enhanced Matcha Provider ที่ใช้ metadata จริง
"""

import re
from typing import Dict, List, Any
from app.services.universal_schema_service import UniversalSchemaService

class EnhancedMatchaProvider:
    """Matcha Provider ที่ใช้ metadata และ dynamic context"""
    
    def __init__(self, api_key: str, api_url: str, db_path: str):
        self.api_key = api_key
        self.api_url = api_url
        self.db_path = db_path
        self.universal_schema = UniversalSchemaService(db_path)
    
    def build_dynamic_prompt(self, question: str, dataset_name: str) -> str:
        """สร้าง prompt แบบ dynamic สำหรับ dataset และ question ที่ระบุ"""
        
        context = self.universal_schema.get_dataset_context(dataset_name)
        
        # เพิ่ม few-shot examples จาก mappings จริง
        mappings = self.universal_schema._dataset_configs[dataset_name].semantic_mappings
        
        examples_text = "### ตัวอย่างการแปลงคำถาม\n"
        for keyword, mapping in list(mappings.items())[:3]:  # ใช้ 3 ตัวอย่าง
            examples_text += f"- '{keyword}' → `{mapping['column']} {mapping['condition']}`\n"
        
        return f"""คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูล {dataset_name}

{context}

{examples_text}

## คำถามปัจจุบัน: {question}

กรุณาสร้าง SQL query ที่ตรงกับคำถามนี้ โดยใช้ semantic mappings และ schema ที่ระบุข้างต้น
ตอบในรูปแบบ:
```sql
[SQL QUERY]
```
คำอธิบาย: [คำอธิบายสั้นๆ]"""
    
    def enhance_sql_validation(self, sql: str, dataset_name: str) -> Dict[str, Any]:
        """ตรวจสอบ SQL โดยใช้ metadata จริง"""
        
        config = self.universal_schema._dataset_configs[dataset_name]
        
        issues = []
        corrections = []
        
        # ตรวจสอบ table name
        expected_table = config.table_name
        if expected_table not in sql:
            issues.append(f"ใช้ผิด table name: ควรใช้ '{expected_table}'")
        
        # ตรวจสอบ value column
        expected_value = config.value_column
        if f"SUM({expected_value})" not in sql and expected_value not in sql:
            issues.append(f"ควรใช้ column '{expected_value}' สำหรับการคำนวณ")
        
        # ตรวจสอบ date columns
        for date_col in config.date_columns:
            if date_col in question.lower() and date_col not in sql:
                issues.append(f"คำถามมี '{date_col}' แต่ SQL ไม่ได้ใช้")
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "suggestions": corrections
        }
```

### 7. ปรับ Frontend รองรับหลาย datasets

**ไฟล์: `frontend/services/universal.ts`**

```typescript
// frontend/services/universal.ts

export interface Dataset {
  name: string;
  table_name: string;
  description: string;
  value_column: string;
  category_columns: string[];
}

export interface UniversalQueryRequest {
  question: string;
  dataset_name?: string;
  explain?: boolean;
}

export interface UniversalQueryResponse {
  dataset_name: string;
  question: string;
  sql_query: string;
  data: any[];
  explanation: string;
  tokens_used: number;
  provider: string;
}

class UniversalService {
  private apiUrl = 'http://localhost:8000/api/v1/universal';
  
  async getDatasets(): Promise<Dataset[]> {
    const response = await fetch(`${this.apiUrl}/datasets`);
    return response.json();
  }
  
  async query(request: UniversalQueryRequest): Promise<UniversalQueryResponse> {
    const response = await fetch(`${this.apiUrl}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await this.getAuthToken()}`
      },
      body: JSON.stringify(request)
    });
    
    if (!response.ok) {
      throw new Error(await response.text());
    }
    
    return response.json();
  }
  
  async queryMultipleDatasets(questions: {dataset_name?: string, question: string}[]) {
    const results = await Promise.all(
      questions.map(q => this.query(q))
    );
    return results;
  }
  
  async autoDetectAndQuery(question: string) {
    return this.query({ question });
  }
}

export const universalService = new UniversalService();
```

### 8. ตัวอย่างการใช้งานทั้งระบบ

```python
# ตัวอย่างการใช้งานจริง

# 1. ผู้ใช้ถามคำถาม
question = "รายได้และค่าใช้จ่ายของ นป. ในมกราคม 2568"

# 2. ระบบตรวจจับและ query หลาย datasets
results = await universalService.queryMultipleDatasets([
    {"question": "รายได้ นป. มกราคม 2568"},
    {"question": "ค่าใช้จ่าย นป. มกราคม 2568", "dataset_name": "expenses"}
])

# 3. รวมผลลัพธ์
combined_analysis = f"""
วิเคราะห์ นป. มกราคม 2568:
- รายได้รวม: {results[0]['data'][0]['total_revenue']} บาท
- ค่าใช้จ่ายรวม: {results[1]['data'][0]['total_expense']} บาท
- กำไรสุทธิ: {results[0]['data'][0]['total_revenue'] - results[1]['data'][0]['total_expense']} บาท
"""
```

### 9. สรุปการปรับปรุง Matcha แบบ Metadata-Driven

**🎯 วิธีนี้แก้ปัญหา Matcha โดย:**

1. **❌ ไม่ hard-code** - ใช้ metadata จาก database
2. **🔧 รองรับหลาย datasets** - revenue, expenses, operations, etc.
3. **🎯 Dynamic context** - สร้าง prompt ตาม dataset จริง
4. **📊 Real-time validation** - ใช้ schema จริงจาก database
5. **🔄 Scalable** - เพิ่ม dataset ใหม่โดยไม่แก้ code

**การติดตั้ง:**
```bash
# 1. รัน migration
python scripts/init_db.py
python scripts/setup_universal_metadata.py

# 2. ทดสอบ
python scripts/test_universal_service.py "รายได้ นป. 2568"
python scripts/test_universal_service.py "ค่าใช้จ่ายไฟฟ้า 2568" --dataset expenses
```

**ผลลัพธ์:** Matcha จะเข้าใจคำถามภาษาไทยได้ดีขึ้น และสร้าง SQL ที่ถูกต้องสำหรับหลาย datasets โดยใช้ metadata จริงจาก database!
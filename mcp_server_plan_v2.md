# แผนการพัฒนา MCP Server สำหรับ NT AI Assistant (V2)
**ปรับปรุงให้สอดคล้องกับ Project ปัจจุบัน**

**Last Updated:** 2026-02-02

---

## 📋 Executive Summary

### สถานะปัจจุบัน (Already Implemented)

| Component | Status | Location |
|-----------|--------|----------|
| Multi-Context Support | ✅ Done | `schema_contexts` table, `ContextRouter` |
| Multi-Provider AI | ✅ Done | Claude, Gemini, Matcha in `ai_service.py` |
| Database Adapter | ✅ Done | SQLite, PostgreSQL, MSSQL in `database_adapter.py` |
| Schema Metadata | ✅ Done | `schema_metadata`, `schema_semantic_mapping`, `schema_business_rules` |
| Frontend Context Selector | ✅ Done | `ContextSelector.tsx` |
| Admin Context Management | ✅ Done | `frontend-admin/src/pages/Contexts.tsx` |
| **NT Metadata MCP** | ✅ Done | `mcp_servers/nt_metadata_mcp.py` |
| **NT Query MCP** | ✅ Done | `mcp_servers/nt_query_mcp.py` |

### MCP Server Progress

| MCP Server | Status | Tools | Notes |
|------------|--------|-------|-------|
| `nt_metadata_mcp.py` | ✅ **Complete** | 14 tools | Multi-DB support |
| `nt_query_mcp.py` | ✅ **Complete** | 5 tools | SQL execution, validation |
| `nt_validation_mcp.py` | ⏳ Pending | 3 tools | Confidence scoring |
| `nt_reporting_mcp.py` | ⏳ Pending | 3 tools | Report comparison |
| MCP Client Integration | ⏳ Pending | - | Backend integration |

### สิ่งที่ MCP จะเพิ่มเติม

1. **Dynamic Tool Access** - ให้ AI เรียก metadata แบบ real-time
2. **Confidence Scoring** - วัดความมั่นใจในคำตอบ
3. **Official Report Comparison** - เทียบกับรายงานมาตรฐาน
4. **Audit Trail** - บันทึกการทำงานทุกขั้นตอน

### Expected Outcomes
| Metric | ปัจจุบัน | เป้าหมาย |
|--------|----------|----------|
| SQL Accuracy | 70-80% | **90%+** |
| User Trust Score | ไม่มีการวัด | **8/10** |
| Response Time | 3-5 sec | **< 3 sec** |
| Context Detection Accuracy | 85% | **95%** |

---

## 🏗️ Architecture (Aligned with Current Project)

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INTERFACE (Existing)                     │
│  React Native App (frontend/)                                    │
│  • ContextSelector: Auto | รายได้ | ค่าใช้จ่าย                   │
│  • ModelSelector: Gemini | Claude | Matcha                      │
│  • ChatBubble with SQL explanation                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FASTAPI BACKEND (Existing: app/)                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ chat.py         │  │ ai_service.py   │  │ schema_service  │ │
│  │ /api/v1/chat    │  │ Claude/Gemini/  │  │ .py             │ │
│  │                 │  │ Matcha Provider │  │                 │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │           │
│           ▼                    ▼                    ▼           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              MCP CLIENT (NEW)                               ││
│  │  • Calls MCP servers for dynamic metadata                   ││
│  │  • Validates SQL with MCP tools                             ││
│  │  • Gets confidence score                                    ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ stdio / SSE
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MCP SERVERS (NEW)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │  nt-metadata-mcp    │  │  nt-query-mcp       │              │
│  │  ✅ COMPLETE        │  │  ✅ COMPLETE        │              │
│  ├─────────────────────┤  ├─────────────────────┤              │
│  │ 14 Tools:           │  │ Tools:              │              │
│  │ • get_available_    │  │ • validate_sql      │              │
│  │   contexts          │  │ • execute_query     │              │
│  │ • route_question_   │  │ • explain_sql       │              │
│  │   to_context        │  │ • get_sample_data   │              │
│  │ • get_context_info  │  │                     │              │
│  │ • get_schema_for_   │  │                     │              │
│  │   context           │  │                     │              │
│  │ • get_column_info   │  │                     │              │
│  │ • get_semantic_     │  │                     │              │
│  │   mappings          │  │                     │              │
│  │ • search_mapping_   │  │                     │              │
│  │   for_term          │  │                     │              │
│  │ • get_business_rules│  │                     │              │
│  │ • check_rule_       │  │                     │              │
│  │   violation         │  │                     │              │
│  │ • get_golden_       │  │                     │              │
│  │   examples          │  │                     │              │
│  │ • find_similar_     │  │                     │              │
│  │   example           │  │                     │              │
│  │ • get_database_info │  │                     │              │
│  │ • get_syntax_rules  │  │                     │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │  nt-validation-mcp  │  │  nt-reporting-mcp   │              │
│  │  ⏳ PENDING         │  │  ⏳ PENDING         │              │
│  ├─────────────────────┤  ├─────────────────────┤              │
│  │ Tools:              │  │ Tools:              │              │
│  │ • check_business    │  │ • fetch_official    │              │
│  │   _rules            │  │   _report           │              │
│  │ • calculate         │  │ • compare_results   │              │
│  │   _confidence       │  │ • get_report_list   │              │
│  │ • validate_result   │  │                     │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (Existing)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ SQLite          │  │ PostgreSQL      │  │ MSSQL           │ │
│  │ nt_fi_report    │  │ (App DB)        │  │ (NT Data)       │ │
│  │ .sqlite         │  │                 │  │                 │ │
│  │                 │  │                 │  │                 │ │
│  │ Tables:         │  │ Tables:         │  │ Tables:         │ │
│  │ • revenue_search│  │ • users         │  │ • NT_Revenue    │ │
│  │ • v_expense_mart│  │ • chat_history  │  │ • NT_Expense    │ │
│  │ • schema_*      │  │ • feedback      │  │                 │ │
│  │ • golden_examples│ │                 │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Phase 1: Core MCP Servers ✅ COMPLETE

### 1.1 NT Metadata MCP Server ✅ COMPLETE

**ไฟล์:** `mcp_servers/nt_metadata_mcp.py`
**Database:** `nt_fi_report.sqlite` (รองรับ SQLite, PostgreSQL, MSSQL)

**14 Tools Implemented:**

| Tool | Description | Status |
|------|-------------|--------|
| `get_available_contexts` | ดึงรายการ contexts ทั้งหมด | ✅ |
| `route_question_to_context` | ระบุ context จากคำถามอัตโนมัติ | ✅ |
| `get_context_info` | ข้อมูลรายละเอียด context | ✅ |
| `get_schema_for_context` | schema ของ context | ✅ |
| `get_column_info` | ข้อมูล column เฉพาะ | ✅ |
| `get_semantic_mappings` | การ mapping คำศัพท์ | ✅ |
| `search_mapping_for_term` | ค้นหาการ mapping | ✅ |
| `get_business_rules` | กฎทางธุรกิจ | ✅ |
| `check_rule_violation` | ตรวจสอบการละเมิดกฎ | ✅ |
| `get_golden_examples` | ตัวอย่าง SQL | ✅ |
| `find_similar_example` | ค้นหาตัวอย่างใกล้เคียง | ✅ |
| `get_database_info` | ข้อมูล database | ✅ |
| `get_syntax_rules` | กฎ SQL syntax | ✅ |

**Multi-Database Architecture:**

```python
# mcp_servers/nt_metadata_mcp.py

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    engine: str  # sqlite, postgresql, mssql
    connection_string: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables"""
        db_url = os.getenv(
            "METADATA_DB_URL",
            f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"
        )
        # Auto-detect engine from URL
        if db_url.startswith("sqlite"):
            engine = "sqlite"
        elif "postgresql" in db_url or "postgres" in db_url:
            engine = "postgresql"
        elif "mssql" in db_url or "sqlserver" in db_url:
            engine = "mssql"
        else:
            engine = os.getenv("DB_ENGINE", "sqlite")
        return cls(engine=engine, connection_string=db_url)

    @classmethod
    def from_url(cls, db_url: str) -> "DatabaseConfig":
        """Create config from database URL"""
        # ... similar logic


class MCPDatabaseAdapter:
    """
    Simplified database adapter for MCP server.
    Supports SQLite, PostgreSQL, and MSSQL.
    """
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = config.engine

    def execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """Execute query and return results as list of dicts"""
        if self.engine == "sqlite":
            # SQLite connection
        elif self.engine == "postgresql":
            # PostgreSQL connection via psycopg2
        elif self.engine == "mssql":
            # MSSQL connection via pyodbc
```

**วิธีใช้งาน:**

```bash
# ตั้งค่า database (SQLite - default)
export METADATA_DB_URL="sqlite:///nt_fi_report.sqlite"

# หรือ PostgreSQL
export METADATA_DB_URL="postgresql://user:pass@localhost:5432/ntdb"

# หรือ MSSQL
export METADATA_DB_URL="mssql://sa:pass@localhost:1433/ntdb"

# รัน MCP server
python -m mcp_servers.nt_metadata_mcp

# รัน test
python mcp_servers/test_metadata_mcp.py
```

**Test Results (All Passed):**
```
[PASS] Contexts - get_available_contexts()
[PASS] Routing - route_question_to_context()
[PASS] Schema - get_schema_for_context()
[PASS] Mappings - get_semantic_mappings(), search_mapping_for_term()
[PASS] Rules - get_business_rules(), check_rule_violation()
[PASS] Examples - get_golden_examples()
[PASS] DB Info - get_database_info(), get_syntax_rules()

Total: 7/7 tests passed
```

---

### 1.2 NT Query MCP Server ✅ COMPLETE

**ไฟล์:** `mcp_servers/nt_query_mcp.py`

**5 Tools Implemented:**

| Tool | Description | Status |
|------|-------------|--------|
| `validate_sql` | ตรวจสอบ SQL ว่าปลอดภัยและถูกต้อง | ✅ |
| `execute_query` | Execute validated SELECT query | ✅ |
| `get_sample_values` | ดึงตัวอย่างค่าที่ไม่ซ้ำใน column | ✅ |
| `explain_sql_thai` | อธิบาย SQL เป็นภาษาไทย | ✅ |
| `get_table_stats` | ดึงสถิติของตาราง | ✅ |

**Test Results:**
```
[PASS] Validate SQL - 8/8 test cases
[PASS] Execute Query - 4/4 scenarios
[PASS] Sample Values
[PASS] Explain SQL Thai
[PASS] Table Stats

Total: 5/5 tests passed
```

**Code:**

```python
# mcp_servers/nt_query_mcp.py
from mcp.server.fastmcp import FastMCP
from typing import Dict, List
import re

mcp = FastMCP(
    name="NT Query Server",
    instructions="Execute and validate SQL queries for NT AI Assistant"
)

# Reuse DatabaseConfig and MCPDatabaseAdapter from nt_metadata_mcp
from .nt_metadata_mcp import DatabaseConfig, MCPDatabaseAdapter, get_db

# Dangerous SQL patterns
DANGEROUS_PATTERNS = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'INSERT', 'UPDATE', 'CREATE']


@mcp.tool()
def validate_sql(sql: str) -> Dict:
    """
    ตรวจสอบ SQL ว่าปลอดภัยและถูกต้อง

    Args:
        sql: SQL query to validate

    Returns:
        {"valid": bool, "issues": [], "warnings": []}
    """
    issues = []
    warnings = []

    if not sql or not sql.strip():
        return {"valid": False, "issues": ["SQL is empty"]}

    sql_upper = sql.upper().strip()

    # Check read-only
    if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
        issues.append("Only SELECT queries (or CTEs starting with WITH) are allowed")

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if pattern in sql_upper:
            issues.append(f"Dangerous operation detected: {pattern}")

    # Warnings
    if 'SELECT *' in sql_upper:
        warnings.append("Using SELECT * may return unnecessary columns")

    if 'WHERE' not in sql_upper and 'FROM' in sql_upper:
        warnings.append("Query has no WHERE clause - may return large dataset")

    if 'LIMIT' not in sql_upper:
        warnings.append("Consider adding LIMIT to prevent large result sets")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings
    }


@mcp.tool()
def execute_query(
    sql: str,
    context_name: str = "revenue",
    limit: int = 100
) -> Dict:
    """
    Execute validated SELECT query

    Args:
        sql: SQL query (must be validated first)
        context_name: context for table resolution
        limit: max rows to return

    Returns:
        {"success": bool, "data": [...], "row_count": int}
    """
    # Validate first
    validation = validate_sql(sql)
    if not validation["valid"]:
        return {
            "success": False,
            "error": "SQL validation failed",
            "issues": validation["issues"]
        }

    try:
        db = get_db()

        # Add LIMIT if not present
        if 'LIMIT' not in sql.upper():
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        rows = db.execute_query(sql)

        return {
            "success": True,
            "data": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= limit
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def get_sample_values(
    column_name: str,
    table_name: str = "revenue_search",
    limit: int = 10
) -> Dict:
    """
    ดึงตัวอย่างค่าใน column

    Args:
        column_name: ชื่อ column
        table_name: ชื่อ table/view
        limit: จำนวนค่าที่ต้องการ

    Returns:
        {"values": [...], "total_distinct": int}
    """
    try:
        db = get_db()
        placeholder = db.get_placeholder()

        # Get sample values
        values_sql = f'''
            SELECT DISTINCT "{column_name}"
            FROM {table_name}
            WHERE "{column_name}" IS NOT NULL
            LIMIT {limit}
        '''
        values = [row[column_name] for row in db.execute_query(values_sql)]

        # Get total distinct count
        count_sql = f'''
            SELECT COUNT(DISTINCT "{column_name}") as cnt
            FROM {table_name}
            WHERE "{column_name}" IS NOT NULL
        '''
        total = db.execute_query(count_sql)[0]['cnt']

        return {
            "column": column_name,
            "values": values,
            "total_distinct": total
        }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def explain_sql_thai(sql: str) -> Dict:
    """
    อธิบาย SQL เป็นภาษาไทย

    Args:
        sql: SQL query

    Returns:
        {"steps": [...], "summary": "..."}
    """
    steps = []
    sql_upper = sql.upper()

    # SELECT
    if 'SELECT' in sql_upper:
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            columns = select_match.group(1).strip()
            if 'SUM(' in columns.upper():
                steps.append("รวมยอดเงินจากคอลัมน์ที่เลือก")
            elif 'COUNT(' in columns.upper():
                steps.append("นับจำนวนแถวข้อมูล")
            elif '*' in columns:
                steps.append("เลือกข้อมูลทุกคอลัมน์")
            else:
                steps.append(f"เลือกคอลัมน์: {columns}")

    # FROM
    from_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
    if from_match:
        table = from_match.group(1)
        steps.append(f"จากตาราง: {table}")

    # WHERE
    where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
    if where_match:
        conditions = where_match.group(1).strip()
        steps.append(f"กรองข้อมูล: {conditions}")

    # GROUP BY
    if 'GROUP BY' in sql_upper:
        group_match = re.search(r'GROUP BY\s+(.*?)(?:ORDER BY|HAVING|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if group_match:
            steps.append(f"จัดกลุ่มตาม: {group_match.group(1).strip()}")

    # ORDER BY
    if 'ORDER BY' in sql_upper:
        order_match = re.search(r'ORDER BY\s+(.*?)(?:LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if order_match:
            steps.append(f"เรียงลำดับตาม: {order_match.group(1).strip()}")

    return {
        "steps": steps,
        "summary": " → ".join(steps) if steps else "ไม่สามารถวิเคราะห์ SQL ได้"
    }


if __name__ == "__main__":
    mcp.run()
```

---

## 🛡️ Phase 2: Validation MCP Server ⏳ PENDING

### 2.1 NT Validation MCP

**ไฟล์ที่จะสร้าง:** `mcp_servers/nt_validation_mcp.py`

```python
# mcp_servers/nt_validation_mcp.py
from mcp.server.fastmcp import FastMCP
from typing import Dict, List
import re

mcp = FastMCP(
    name="NT Validation Server",
    instructions="Validate SQL queries and calculate confidence scores"
)

# Reuse from nt_metadata_mcp
from .nt_metadata_mcp import get_db


@mcp.tool()
def check_business_rules(
    sql: str,
    question: str,
    context_name: str = "revenue"
) -> Dict:
    """
    ตรวจสอบว่า SQL ปฏิบัติตาม business rules หรือไม่

    Args:
        sql: SQL query
        question: คำถามเดิม
        context_name: context

    Returns:
        {"passed": bool, "violations": [...], "warnings": [...]}
    """
    violations = []
    warnings = []
    sql_upper = sql.upper()
    question_lower = question.lower()

    # Load rules from database
    db = get_db()
    rules = db.execute_query('''
        SELECT rule_code, rule_name, applies_to, check_pattern, severity
        FROM schema_business_rules
        WHERE is_active = 1
    ''')

    for rule in rules:
        # Apply rule checks based on check_pattern
        if rule.get('check_pattern'):
            pattern = rule['check_pattern']
            if re.search(pattern, sql, re.IGNORECASE):
                item = {
                    "rule": rule['rule_code'],
                    "severity": rule['severity'],
                    "message": rule['rule_name']
                }
                if rule['severity'] == 'error':
                    violations.append(item)
                else:
                    warnings.append(item)

    return {
        "passed": len([v for v in violations if v["severity"] == "error"]) == 0,
        "violations": violations,
        "warnings": warnings
    }


@mcp.tool()
def calculate_confidence_score(
    sql_validation: Dict,
    rule_check: Dict,
    has_similar_example: bool = False,
    report_match: Dict = None
) -> Dict:
    """
    คำนวณ confidence score สำหรับคำตอบ

    Args:
        sql_validation: ผลจาก validate_sql
        rule_check: ผลจาก check_business_rules
        has_similar_example: มี golden example คล้ายกันไหม
        report_match: ผลเทียบกับรายงานมาตรฐาน

    Returns:
        {"score": 0-100, "level": "สูง/กลาง/ต่ำ", "factors": [...]}
    """
    score = 0
    factors = []

    # Factor 1: SQL Syntax (30 points)
    if sql_validation.get("valid"):
        score += 30
        factors.append("SQL ถูกต้องตามไวยากรณ์")
    else:
        factors.append("SQL มีข้อผิดพลาด")

    # Factor 2: Business Rules (30 points)
    if rule_check.get("passed"):
        score += 30
        factors.append("ปฏิบัติตามกฎธุรกิจครบถ้วน")
    else:
        violation_count = len(rule_check.get("violations", []))
        score += max(0, 30 - violation_count * 15)
        factors.append(f"มีกฎธุรกิจที่ไม่ตรง: {violation_count} ข้อ")

    # Factor 3: Similar Example (20 points)
    if has_similar_example:
        score += 20
        factors.append("มีตัวอย่างคำถามคล้ายกันในระบบ")
    else:
        score += 10
        factors.append("ไม่พบตัวอย่างคำถามคล้ายกัน")

    # Factor 4: Report Match (20 points)
    if report_match:
        if report_match.get("match"):
            score += 20
            factors.append("ตรงกับรายงานมาตรฐาน")
        elif report_match.get("comparable"):
            diff_pct = abs(report_match.get("difference_pct", 0))
            if diff_pct < 5:
                score += 15
                factors.append(f"ต่างจากรายงานมาตรฐาน {diff_pct:.1f}%")
            else:
                score += 5
                factors.append(f"ต่างจากรายงานมาตรฐานมาก: {diff_pct:.1f}%")
    else:
        score += 10
        factors.append("ไม่มีรายงานมาตรฐานเปรียบเทียบ")

    # Determine level
    if score >= 80:
        level = "สูง"
        recommendation = "สามารถใช้ข้อมูลนี้ได้เลย"
    elif score >= 60:
        level = "ปานกลาง"
        recommendation = "ควรตรวจสอบข้อมูลก่อนใช้งาน"
    else:
        level = "ต่ำ"
        recommendation = "ไม่แนะนำให้ใช้โดยตรง กรุณาปรึกษาผู้เชี่ยวชาญ"

    return {
        "score": score,
        "level": level,
        "factors": factors,
        "recommendation": recommendation
    }


if __name__ == "__main__":
    mcp.run()
```

---

## 📊 Phase 3: Reporting MCP Server ⏳ PENDING

**ไฟล์ที่จะสร้าง:** `mcp_servers/nt_reporting_mcp.py`

```python
# mcp_servers/nt_reporting_mcp.py
from mcp.server.fastmcp import FastMCP
from typing import Dict, List, Optional
import os

mcp = FastMCP(
    name="NT Reporting Server",
    instructions="Compare query results with official reports"
)

REPORTS_DIR = os.getenv("REPORTS_DIR", "/data/official_reports")


@mcp.tool()
def list_available_reports(period: str = None) -> List[Dict]:
    """
    แสดงรายการรายงานมาตรฐานที่มี

    Args:
        period: filter by period (e.g., "2024-01", "2024-Q1")

    Returns:
        List of available reports
    """
    reports = []

    if not os.path.exists(REPORTS_DIR):
        return []

    for filename in os.listdir(REPORTS_DIR):
        if filename.endswith(('.csv', '.xlsx')):
            parts = filename.rsplit('_', 1)
            if len(parts) == 2:
                report_type = parts[0]
                report_period = parts[1].replace('.csv', '').replace('.xlsx', '')

                if period and period not in report_period:
                    continue

                reports.append({
                    "filename": filename,
                    "type": report_type,
                    "period": report_period
                })

    return sorted(reports, key=lambda x: x["period"], reverse=True)


@mcp.tool()
def fetch_official_report(
    report_type: str,
    period: str
) -> Dict:
    """
    ดึงข้อมูลจากรายงานมาตรฐาน

    Args:
        report_type: revenue_monthly, expense_summary, etc.
        period: 2024-01, 2024-Q1

    Returns:
        Report data with summary
    """
    try:
        import pandas as pd
    except ImportError:
        return {"success": False, "error": "pandas not installed"}

    # Try different file formats
    for ext in ['.csv', '.xlsx']:
        filepath = os.path.join(REPORTS_DIR, f"{report_type}_{period}{ext}")

        if os.path.exists(filepath):
            try:
                if ext == '.csv':
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)

                # Find amount column
                amount_col = None
                for col in df.columns:
                    if 'amount' in col.lower() or 'revenue' in col.lower() or 'รายได้' in col:
                        amount_col = col
                        break

                summary = {}
                if amount_col:
                    summary["total"] = float(df[amount_col].sum())
                    summary["mean"] = float(df[amount_col].mean())
                    summary["count"] = int(df[amount_col].count())

                return {
                    "success": True,
                    "report_type": report_type,
                    "period": period,
                    "total_rows": len(df),
                    "columns": list(df.columns),
                    "summary": summary,
                    "data": df.head(20).to_dict('records')
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Error reading report: {str(e)}"
                }

    return {
        "success": False,
        "error": f"Report not found: {report_type}_{period}"
    }


@mcp.tool()
def compare_query_with_report(
    query_total: float,
    report_type: str,
    period: str
) -> Dict:
    """
    เปรียบเทียบผลลัพธ์จาก query กับรายงานมาตรฐาน

    Args:
        query_total: ยอดรวมจาก query
        report_type: ประเภทรายงาน
        period: ช่วงเวลา

    Returns:
        Comparison result
    """
    report = fetch_official_report(report_type, period)

    if not report.get("success"):
        return {
            "comparable": False,
            "reason": report.get("error", "Report not available")
        }

    official_total = report["summary"].get("total")

    if official_total is None:
        return {
            "comparable": False,
            "reason": "No total amount in report"
        }

    difference = query_total - official_total
    difference_pct = (difference / official_total * 100) if official_total else 0

    return {
        "comparable": True,
        "query_total": query_total,
        "official_total": official_total,
        "difference": difference,
        "difference_pct": round(difference_pct, 2),
        "match": abs(difference_pct) < 1.0,  # ต่างไม่เกิน 1%
        "status": "ตรงกัน" if abs(difference_pct) < 1.0 else f"ต่างกัน {abs(difference_pct):.1f}%"
    }


if __name__ == "__main__":
    mcp.run()
```

---

## 🔗 Phase 4: Integration with Existing Backend ⏳ PENDING

### 4.1 MCP Client Service

**ไฟล์ที่จะสร้าง:** `app/services/mcp_client.py`

```python
# app/services/mcp_client.py
"""
MCP Client - Integrates MCP servers with existing AIService
"""
from typing import Dict, List, Optional
import subprocess
import json


class MCPClient:
    """Client to call MCP server tools via stdio"""

    def __init__(self, server_configs: Dict[str, Dict]):
        """
        Args:
            server_configs: {
                "metadata": {"command": "python", "args": ["-m", "mcp_servers.nt_metadata_mcp"]},
                ...
            }
        """
        self.server_configs = server_configs
        self._processes = {}

    def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Dict
    ) -> Dict:
        """Call a tool on MCP server"""
        config = self.server_configs.get(server)
        if not config:
            raise ValueError(f"Unknown server: {server}")

        # Build MCP tool call request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments
            },
            "id": 1
        }

        # Call via subprocess (for stdio transport)
        result = subprocess.run(
            [config["command"]] + config.get("args", []),
            input=json.dumps(request),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {"error": result.stderr}

        return json.loads(result.stdout)

    # Convenience methods
    def route_context(self, question: str) -> Dict:
        """Route question to appropriate context"""
        return self.call_tool(
            "metadata",
            "route_question_to_context",
            {"question": question}
        )

    def get_schema(self, context: str) -> Dict:
        """Get schema for context"""
        return self.call_tool(
            "metadata",
            "get_schema_for_context",
            {"context_name": context}
        )

    def validate_sql(self, sql: str) -> Dict:
        """Validate SQL query"""
        return self.call_tool(
            "query",
            "validate_sql",
            {"sql": sql}
        )

    def check_rules(
        self,
        sql: str,
        question: str,
        context: str
    ) -> Dict:
        """Check business rules"""
        return self.call_tool(
            "validation",
            "check_business_rules",
            {
                "sql": sql,
                "question": question,
                "context_name": context
            }
        )

    def get_confidence(
        self,
        sql_validation: Dict,
        rule_check: Dict,
        has_example: bool,
        report_match: Dict = None
    ) -> Dict:
        """Calculate confidence score"""
        return self.call_tool(
            "validation",
            "calculate_confidence_score",
            {
                "sql_validation": sql_validation,
                "rule_check": rule_check,
                "has_similar_example": has_example,
                "report_match": report_match
            }
        )
```

---

## 📁 Project Structure (Updated)

```
nt-ai-assistant/
├── app/                          # Existing FastAPI app
│   ├── api/v1/
│   │   ├── chat.py              # Chat endpoint (existing)
│   │   └── admin.py             # Admin endpoints (existing)
│   ├── services/
│   │   ├── ai_service.py        # AI Service (existing + MCP integration)
│   │   ├── schema_service.py    # Schema Service (existing)
│   │   ├── context_router.py    # Context Router (existing)
│   │   └── mcp_client.py        # NEW: MCP Client
│   └── ...
│
├── mcp_servers/                  # MCP Servers
│   ├── __init__.py              # ✅ COMPLETE - Package init
│   ├── nt_metadata_mcp.py       # ✅ COMPLETE - Metadata tools (14 tools)
│   ├── nt_query_mcp.py          # ✅ COMPLETE - Query tools (5 tools)
│   ├── nt_validation_mcp.py     # ⏳ PENDING - Validation tools
│   ├── nt_reporting_mcp.py      # ⏳ PENDING - Reporting tools
│   ├── test_metadata_mcp.py     # ✅ COMPLETE - Test script
│   ├── test_query_mcp.py        # ✅ COMPLETE - Test script
│   ├── requirements.txt         # ✅ COMPLETE - Dependencies
│   └── claude_desktop_config.json # ✅ COMPLETE - Claude Desktop config
│
├── frontend/                     # Existing React Native app
│   ├── components/Chat/
│   │   ├── ContextSelector.tsx  # Context selector (existing)
│   │   ├── ModelSelector.tsx    # Model selector (existing)
│   │   └── ConfidenceBadge.tsx  # NEW: Confidence display
│   └── ...
│
├── frontend-admin/               # Existing Admin dashboard
│   └── ...
│
├── data/
│   └── official_reports/         # NEW: Official reports for comparison
│
├── nt_fi_report.sqlite           # Main database
└── docker-compose.yml            # NEW: MCP servers orchestration
```

---

## ⏱️ Implementation Timeline (Revised)

```
Week 1: Core MCP Servers ✅ COMPLETE
├─ Day 1-2: nt_metadata_mcp ✅ COMPLETE (14 tools, 7/7 tests passed)
├─ Day 3-4: nt_query_mcp ✅ COMPLETE (5 tools, 5/5 tests passed)
└─ Day 5: Testing with existing backend ✅ COMPLETE

Week 2: Validation & Confidence
├─ Day 1-2: nt_validation_mcp
├─ Day 3-4: Confidence scoring system
└─ Day 5: Integration testing

Week 3: Reporting & Comparison
├─ Day 1-2: nt_reporting_mcp
├─ Day 3-4: Report comparison logic
└─ Day 5: Setup official reports data

Week 4: Integration & UI
├─ Day 1-2: MCP Client in backend
├─ Day 3-4: Frontend confidence display
└─ Day 5: End-to-end testing

Week 5: Polish & Documentation
├─ Day 1-2: Performance optimization
├─ Day 3: Documentation
├─ Day 4: Bug fixes
└─ Day 5: Deployment
```

---

## ✅ Checklist

### Phase 1 - MCP Servers ✅ COMPLETE
- [x] Create `mcp_servers/` directory
- [x] Create `mcp_servers/__init__.py`
- [x] Implement `nt_metadata_mcp.py` (14 tools)
- [x] Add multi-database support (SQLite, PostgreSQL, MSSQL)
- [x] Create `test_metadata_mcp.py`
- [x] Create `requirements.txt`
- [x] Create `claude_desktop_config.json`
- [x] Test all 14 metadata tools - **7/7 PASSED**
- [x] Implement `nt_query_mcp.py` (5 tools)
- [x] Create `test_query_mcp.py`
- [x] Test all 5 query tools - **5/5 PASSED**

### Phase 2 - Validation
- [ ] Implement `nt_validation_mcp.py`
- [ ] Add business rules from existing `schema_business_rules`
- [ ] Implement confidence scoring
- [ ] Test validation tools

### Phase 3 - Reporting
- [ ] Implement `nt_reporting_mcp.py`
- [ ] Setup `/data/official_reports/` directory
- [ ] Add sample official reports
- [ ] Test reporting tools

### Phase 4 - Integration
- [ ] Create `app/services/mcp_client.py`
- [ ] Integrate MCP with existing `AIService`
- [ ] Add confidence display to frontend (`ConfidenceBadge.tsx`)
- [ ] End-to-end testing

### Phase 5 - Deployment
- [ ] Create `docker-compose.yml` for MCP servers
- [ ] Update documentation
- [ ] Production deployment

---

## 📝 Implementation Notes

### nt_metadata_mcp.py - Key Features

1. **Multi-Database Support**
   - SQLite: Built-in, default
   - PostgreSQL: via `psycopg2-binary`
   - MSSQL: via `pyodbc`

2. **Environment Variables**
   - `METADATA_DB_URL`: Database connection string
   - Default: `sqlite:///nt_fi_report.sqlite`

3. **14 Tools Available**
   ```python
   # Context Management
   get_available_contexts()      # List all contexts
   route_question_to_context()   # Auto-detect context
   get_context_info()            # Context details

   # Schema Information
   get_schema_for_context()      # Full schema
   get_column_info()             # Single column info

   # Semantic Mappings
   get_semantic_mappings()       # All mappings
   search_mapping_for_term()     # Search specific term

   # Business Rules
   get_business_rules()          # All rules
   check_rule_violation()        # Validate SQL against rules

   # Golden Examples
   get_golden_examples()         # Get examples
   find_similar_example()        # Find similar question

   # Database Info
   get_database_info()           # DB status
   get_syntax_rules()            # SQL syntax rules per engine
   ```

4. **Running the Server**
   ```bash
   # As MCP server
   python -m mcp_servers.nt_metadata_mcp

   # With custom database
   METADATA_DB_URL="postgresql://..." python -m mcp_servers.nt_metadata_mcp

   # Run tests
   python mcp_servers/test_metadata_mcp.py
   ```

---

## 📚 References

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Python SDK](https://github.com/jlowin/fastmcp)
- Existing project: `app/services/schema_service.py`, `app/services/context_router.py`

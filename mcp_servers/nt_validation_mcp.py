"""
NT Validation MCP Server
========================
MCP Server for SQL validation and confidence scoring.

Tools:
- check_business_rules: ตรวจสอบ SQL ตาม business rules
- calculate_confidence_score: คำนวณ confidence score
- validate_result: ตรวจสอบผลลัพธ์ query

Usage:
    python -m mcp_servers.nt_validation_mcp

Environment Variables:
    METADATA_DB_URL: Database connection string
"""

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nt_validation_mcp")

# =========================================================
# Database Configuration (Reused from other MCP servers)
# =========================================================

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    engine: str
    connection_string: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        db_url = os.getenv(
            "METADATA_DB_URL",
            f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"
        )

        if db_url.startswith("sqlite"):
            engine = "sqlite"
        elif "postgresql" in db_url or "postgres" in db_url:
            engine = "postgresql"
        elif "mssql" in db_url or "sqlserver" in db_url:
            engine = "mssql"
        else:
            engine = os.getenv("DB_ENGINE", "sqlite")

        return cls(engine=engine, connection_string=db_url)


class ValidationDatabaseAdapter:
    """Database adapter for validation queries"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = config.engine

    def _get_connection(self):
        if self.engine == "sqlite":
            import sqlite3
            path = self.config.connection_string.replace("sqlite:///", "").replace("sqlite://", "")
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        elif self.engine == "postgresql":
            import psycopg2
            return psycopg2.connect(self.config.connection_string)

        elif self.engine == "mssql":
            import pyodbc
            return pyodbc.connect(self.config.connection_string)

        raise ValueError(f"Unsupported engine: {self.engine}")

    def execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        conn = self._get_connection()
        try:
            if self.engine == "sqlite":
                cursor = conn.cursor()
                cursor.execute(sql, params or ())
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                return []

            elif self.engine == "postgresql":
                import psycopg2.extras
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(sql, params or ())
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                return []

            elif self.engine == "mssql":
                cursor = conn.cursor()
                cursor.execute(sql, params or ())
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                return []
        finally:
            conn.close()
        return []


# =========================================================
# Initialize Database
# =========================================================

_db_instance: Optional[ValidationDatabaseAdapter] = None

def get_db() -> ValidationDatabaseAdapter:
    global _db_instance
    if _db_instance is None:
        config = DatabaseConfig.from_env()
        _db_instance = ValidationDatabaseAdapter(config)
        logger.info(f"Connected to {config.engine} database")
    return _db_instance


# =========================================================
# Initialize MCP Server
# =========================================================

mcp = FastMCP(
    name="NT Validation Server",
    instructions="""
    NT Validation MCP Server - ตรวจสอบ SQL และคำนวณ confidence score

    Tools available:
    - check_business_rules: ตรวจสอบ SQL ตาม business rules
    - calculate_confidence_score: คำนวณ confidence score
    - validate_result: ตรวจสอบผลลัพธ์ query
    """
)


# =========================================================
# Built-in Validation Rules
# =========================================================

BUILTIN_RULES = [
    {
        "rule_code": "DATE_CONVERSION",
        "rule_name": "ต้องแปลง DATE จาก Unix Timestamp",
        "pattern": r"(?i)SELECT.*\bDATE\b(?!.*\/\s*1000)",
        "check_type": "regex_warning",
        "severity": "warning",
        "message": "คอลัมน์ DATE เป็น Unix Timestamp (ms) ควรใช้ YEAR/MONTH แทน หรือแปลงด้วย date(DATE/1000, 'unixepoch')"
    },
    {
        "rule_code": "THAI_COLUMN_QUOTES",
        "rule_name": "คอลัมน์ภาษาไทยต้องใส่ quotes",
        "pattern": r"(?i)(กลุ่มธุรกิจ|หมวดบัญชี)(?![\"'])",
        "check_type": "regex_error",
        "severity": "error",
        "message": "คอลัมน์ภาษาไทยต้องใส่ double quotes เช่น \"กลุ่มธุรกิจ\""
    },
    {
        "rule_code": "REVENUE_UNIT",
        "rule_name": "หน่วยรายได้เป็นบาท",
        "pattern": r"(?i)(REVENUE_VALUE|revenue_value).*ล้าน",
        "check_type": "context_warning",
        "severity": "info",
        "message": "REVENUE_VALUE มีหน่วยเป็นบาท (ไม่ใช่ล้านบาท)"
    },
    {
        "rule_code": "GROUP_BY_AGGREGATE",
        "rule_name": "SELECT columns ต้องอยู่ใน GROUP BY หรือ aggregate",
        "pattern": r"(?i)GROUP\s+BY",
        "check_type": "aggregate_check",
        "severity": "warning",
        "message": "ตรวจสอบว่าคอลัมน์ใน SELECT อยู่ใน GROUP BY หรือใช้ aggregate function"
    },
    {
        "rule_code": "NO_SELECT_STAR",
        "rule_name": "หลีกเลี่ยง SELECT *",
        "pattern": r"(?i)SELECT\s+\*",
        "check_type": "regex_warning",
        "severity": "info",
        "message": "ควรระบุคอลัมน์ที่ต้องการแทน SELECT *"
    },
    {
        "rule_code": "LIMIT_REQUIRED",
        "rule_name": "ควรมี LIMIT",
        "pattern": r"(?i)^(?!.*LIMIT).*SELECT",
        "check_type": "regex_warning",
        "severity": "info",
        "message": "ควรใส่ LIMIT เพื่อจำกัดจำนวนผลลัพธ์"
    },
    {
        "rule_code": "YEAR_FILTER",
        "rule_name": "ควรกรองปีข้อมูล",
        "pattern": r"(?i)^(?!.*(WHERE|AND).*YEAR).*FROM\s+(revenue|expense)",
        "check_type": "regex_warning",
        "severity": "warning",
        "message": "ควรระบุ YEAR ใน WHERE clause เพื่อจำกัดขอบเขตข้อมูล"
    }
]


# =========================================================
# Tool: check_business_rules
# =========================================================

@mcp.tool()
def check_business_rules(
    sql: str,
    question: str = "",
    context_name: str = "revenue"
) -> str:
    """
    ตรวจสอบว่า SQL ปฏิบัติตาม business rules หรือไม่

    Args:
        sql: SQL query ที่ต้องการตรวจสอบ
        question: คำถามเดิมของผู้ใช้ (optional)
        context_name: ชื่อ context (revenue, expense)

    Returns:
        JSON with passed status, violations, and warnings
    """
    violations = []
    warnings = []
    infos = []

    if not sql or not sql.strip():
        return json.dumps({
            "passed": False,
            "violations": [{"rule": "EMPTY_SQL", "message": "SQL is empty", "severity": "error"}],
            "warnings": [],
            "infos": []
        }, ensure_ascii=False)

    sql_upper = sql.upper()

    # 1. Check built-in rules
    for rule in BUILTIN_RULES:
        pattern = rule.get("pattern")
        check_type = rule.get("check_type")

        matched = False
        if check_type in ["regex_error", "regex_warning"]:
            if re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
                matched = True
        elif check_type == "context_warning":
            # Check if question mentions the context
            if question and re.search(pattern, question, re.IGNORECASE):
                matched = True
        elif check_type == "aggregate_check":
            # Special check for GROUP BY
            if re.search(pattern, sql, re.IGNORECASE):
                # This is informational - complex validation needs more logic
                pass

        if matched:
            item = {
                "rule": rule["rule_code"],
                "message": rule["message"],
                "severity": rule["severity"]
            }
            if rule["severity"] == "error":
                violations.append(item)
            elif rule["severity"] == "warning":
                warnings.append(item)
            else:
                infos.append(item)

    # 2. Load rules from database
    try:
        db = get_db()
        db_rules = db.execute_query('''
            SELECT rule_code, rule_name, rule_description, applies_to, severity
            FROM schema_business_rules
            WHERE is_active = 1
        ''')

        for rule in db_rules:
            # Check if this rule applies to current context
            applies_to = rule.get('applies_to', '')
            if applies_to and context_name not in applies_to:
                continue

            # Basic pattern matching from rule_description
            # More sophisticated matching would require custom logic per rule
            rule_code = rule.get('rule_code', '')

            # Example: Check specific known rules
            if rule_code == "DATE_UNIX" and "DATE" in sql_upper:
                if "/ 1000" not in sql and "YEAR" not in sql_upper:
                    item = {
                        "rule": rule_code,
                        "message": rule.get('rule_description', rule.get('rule_name')),
                        "severity": rule.get('severity', 'warning')
                    }
                    if rule.get('severity') == 'error':
                        violations.append(item)
                    else:
                        warnings.append(item)

    except Exception as e:
        logger.warning(f"Could not load database rules: {e}")

    # 3. Remove duplicates
    seen_rules = set()
    unique_violations = []
    unique_warnings = []
    unique_infos = []

    for v in violations:
        if v["rule"] not in seen_rules:
            seen_rules.add(v["rule"])
            unique_violations.append(v)

    for w in warnings:
        if w["rule"] not in seen_rules:
            seen_rules.add(w["rule"])
            unique_warnings.append(w)

    for i in infos:
        if i["rule"] not in seen_rules:
            seen_rules.add(i["rule"])
            unique_infos.append(i)

    passed = len(unique_violations) == 0

    return json.dumps({
        "passed": passed,
        "violations": unique_violations,
        "warnings": unique_warnings,
        "infos": unique_infos,
        "total_issues": len(unique_violations) + len(unique_warnings)
    }, ensure_ascii=False)


# =========================================================
# Tool: calculate_confidence_score
# =========================================================

@mcp.tool()
def calculate_confidence_score(
    sql_validation_passed: bool = True,
    sql_issues_count: int = 0,
    sql_warnings_count: int = 0,
    rules_passed: bool = True,
    rules_violations_count: int = 0,
    has_similar_example: bool = False,
    example_similarity: float = 0.0,
    result_row_count: int = 0,
    execution_success: bool = True
) -> str:
    """
    คำนวณ confidence score สำหรับคำตอบ

    Args:
        sql_validation_passed: SQL syntax ถูกต้อง
        sql_issues_count: จำนวน issues จาก SQL validation
        sql_warnings_count: จำนวน warnings จาก SQL validation
        rules_passed: ผ่าน business rules ทั้งหมด
        rules_violations_count: จำนวน rule violations
        has_similar_example: มี golden example คล้ายกัน
        example_similarity: ค่าความคล้าย (0-1)
        result_row_count: จำนวนแถวผลลัพธ์
        execution_success: execute สำเร็จหรือไม่

    Returns:
        JSON with score, level, factors, and recommendation
    """
    score = 0
    factors = []

    # =========================================================
    # Factor 1: SQL Syntax Validation (25 points)
    # =========================================================
    if sql_validation_passed:
        syntax_score = 25
        factors.append({
            "name": "SQL Syntax",
            "score": syntax_score,
            "max": 25,
            "detail": "SQL ถูกต้องตามไวยากรณ์"
        })
    else:
        syntax_score = max(0, 25 - (sql_issues_count * 10))
        factors.append({
            "name": "SQL Syntax",
            "score": syntax_score,
            "max": 25,
            "detail": f"พบปัญหา {sql_issues_count} รายการ"
        })
    score += syntax_score

    # =========================================================
    # Factor 2: Business Rules (25 points)
    # =========================================================
    if rules_passed:
        rules_score = 25
        factors.append({
            "name": "Business Rules",
            "score": rules_score,
            "max": 25,
            "detail": "ปฏิบัติตามกฎธุรกิจครบถ้วน"
        })
    else:
        rules_score = max(0, 25 - (rules_violations_count * 12))
        factors.append({
            "name": "Business Rules",
            "score": rules_score,
            "max": 25,
            "detail": f"มีกฎที่ไม่ตรง {rules_violations_count} ข้อ"
        })
    score += rules_score

    # =========================================================
    # Factor 3: Similar Example Match (25 points)
    # =========================================================
    if has_similar_example:
        if example_similarity >= 0.8:
            example_score = 25
            detail = "พบตัวอย่างที่ตรงกันมาก"
        elif example_similarity >= 0.5:
            example_score = 18
            detail = "พบตัวอย่างที่คล้ายกัน"
        else:
            example_score = 12
            detail = "พบตัวอย่างที่เกี่ยวข้อง"
    else:
        example_score = 8  # Base score for novel queries
        detail = "ไม่พบตัวอย่างที่คล้ายกัน (Query ใหม่)"

    factors.append({
        "name": "Example Match",
        "score": example_score,
        "max": 25,
        "detail": detail
    })
    score += example_score

    # =========================================================
    # Factor 4: Execution Success & Results (25 points)
    # =========================================================
    if execution_success:
        if result_row_count > 0:
            exec_score = 25
            detail = f"ได้ผลลัพธ์ {result_row_count} รายการ"
        else:
            exec_score = 15
            detail = "Execute สำเร็จ แต่ไม่มีข้อมูล"
    else:
        exec_score = 0
        detail = "Execute ไม่สำเร็จ"

    factors.append({
        "name": "Execution",
        "score": exec_score,
        "max": 25,
        "detail": detail
    })
    score += exec_score

    # =========================================================
    # Penalty for warnings
    # =========================================================
    warning_penalty = min(10, sql_warnings_count * 2)
    if warning_penalty > 0:
        score = max(0, score - warning_penalty)
        factors.append({
            "name": "Warning Penalty",
            "score": -warning_penalty,
            "max": 0,
            "detail": f"หักคะแนนจาก {sql_warnings_count} warnings"
        })

    # =========================================================
    # Determine Level and Recommendation
    # =========================================================
    if score >= 85:
        level = "high"
        level_th = "สูง"
        recommendation = "สามารถใช้ข้อมูลนี้ได้เลย"
        color = "green"
    elif score >= 65:
        level = "medium"
        level_th = "ปานกลาง"
        recommendation = "ควรตรวจสอบข้อมูลก่อนใช้งาน"
        color = "yellow"
    elif score >= 40:
        level = "low"
        level_th = "ต่ำ"
        recommendation = "ควรตรวจสอบ SQL และผลลัพธ์อย่างละเอียด"
        color = "orange"
    else:
        level = "very_low"
        level_th = "ต่ำมาก"
        recommendation = "ไม่แนะนำให้ใช้โดยตรง กรุณาปรึกษาผู้เชี่ยวชาญ"
        color = "red"

    return json.dumps({
        "score": score,
        "max_score": 100,
        "level": level,
        "level_th": level_th,
        "color": color,
        "factors": factors,
        "recommendation": recommendation,
        "summary": f"ความมั่นใจ {score}% ({level_th})"
    }, ensure_ascii=False)


# =========================================================
# Tool: validate_result
# =========================================================

@mcp.tool()
def validate_result(
    query_result: List[Dict[str, Any]],
    expected_columns: List[str] = None,
    context_name: str = "revenue"
) -> str:
    """
    ตรวจสอบผลลัพธ์จาก query

    Args:
        query_result: ผลลัพธ์จาก query (list of dicts)
        expected_columns: คอลัมน์ที่คาดหวัง (optional)
        context_name: ชื่อ context

    Returns:
        JSON with validation results
    """
    issues = []
    warnings = []
    stats = {}

    if not query_result:
        return json.dumps({
            "valid": True,
            "issues": [],
            "warnings": [{"message": "ไม่มีข้อมูลในผลลัพธ์"}],
            "stats": {"row_count": 0}
        }, ensure_ascii=False)

    row_count = len(query_result)
    stats["row_count"] = row_count

    # Get columns from first row
    if row_count > 0:
        actual_columns = list(query_result[0].keys())
        stats["column_count"] = len(actual_columns)
        stats["columns"] = actual_columns

        # Check expected columns
        if expected_columns:
            missing = set(expected_columns) - set(actual_columns)
            if missing:
                warnings.append({
                    "message": f"คอลัมน์ที่คาดหวังไม่พบ: {', '.join(missing)}"
                })

        # Check for null values
        null_columns = []
        for col in actual_columns:
            null_count = sum(1 for row in query_result if row.get(col) is None)
            if null_count > 0:
                null_columns.append(f"{col} ({null_count} nulls)")

        if null_columns:
            warnings.append({
                "message": f"พบค่า NULL: {', '.join(null_columns)}"
            })

        # Check for suspicious values (very large or negative revenue)
        for col in actual_columns:
            col_lower = col.lower()
            if 'revenue' in col_lower or 'amount' in col_lower or 'value' in col_lower:
                values = [row.get(col) for row in query_result if isinstance(row.get(col), (int, float))]
                if values:
                    max_val = max(values)
                    min_val = min(values)
                    stats[f"{col}_max"] = max_val
                    stats[f"{col}_min"] = min_val
                    stats[f"{col}_sum"] = sum(values)

                    # Warning for very large values (potential unit error)
                    if max_val > 1e12:  # > 1 trillion
                        warnings.append({
                            "message": f"ค่า {col} สูงมาก ({max_val:,.0f}) - ตรวจสอบหน่วยข้อมูล"
                        })

                    # Warning for negative revenue
                    if min_val < 0 and 'revenue' in col_lower:
                        warnings.append({
                            "message": f"พบค่า {col} ติดลบ ({min_val:,.2f})"
                        })

    # Check row count warnings
    if row_count > 1000:
        warnings.append({
            "message": f"ผลลัพธ์มีจำนวนมาก ({row_count:,} รายการ) - ควรกรองข้อมูลเพิ่มเติม"
        })

    return json.dumps({
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "stats": stats
    }, ensure_ascii=False)


# =========================================================
# Tool: get_validation_summary
# =========================================================

@mcp.tool()
def get_validation_summary(
    sql: str,
    question: str = "",
    context_name: str = "revenue",
    has_similar_example: bool = False,
    example_similarity: float = 0.0,
    execution_success: bool = True,
    result_row_count: int = 0
) -> str:
    """
    สรุปผลการตรวจสอบทั้งหมดในครั้งเดียว

    Args:
        sql: SQL query
        question: คำถามของผู้ใช้
        context_name: ชื่อ context
        has_similar_example: มี golden example หรือไม่
        example_similarity: ค่าความคล้าย
        execution_success: execute สำเร็จหรือไม่
        result_row_count: จำนวนแถวผลลัพธ์

    Returns:
        JSON with complete validation summary including confidence score
    """
    # 1. Check business rules
    rules_result = json.loads(check_business_rules(sql, question, context_name))

    # 2. Basic SQL validation
    sql_valid = True
    sql_issues = 0
    sql_warnings = 0

    if not sql or not sql.strip():
        sql_valid = False
        sql_issues = 1
    else:
        sql_upper = sql.upper().strip()
        # Check if it's a SELECT query
        if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
            sql_valid = False
            sql_issues += 1

        # Check for dangerous patterns
        dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'INSERT', 'UPDATE']
        for pattern in dangerous:
            if pattern in sql_upper:
                sql_valid = False
                sql_issues += 1

    sql_warnings = len(rules_result.get('warnings', []))

    # 3. Calculate confidence
    confidence_result = json.loads(calculate_confidence_score(
        sql_validation_passed=sql_valid,
        sql_issues_count=sql_issues,
        sql_warnings_count=sql_warnings,
        rules_passed=rules_result.get('passed', True),
        rules_violations_count=len(rules_result.get('violations', [])),
        has_similar_example=has_similar_example,
        example_similarity=example_similarity,
        result_row_count=result_row_count,
        execution_success=execution_success
    ))

    return json.dumps({
        "sql_valid": sql_valid,
        "rules_check": rules_result,
        "confidence": confidence_result,
        "summary": {
            "score": confidence_result['score'],
            "level": confidence_result['level'],
            "level_th": confidence_result['level_th'],
            "color": confidence_result['color'],
            "recommendation": confidence_result['recommendation']
        }
    }, ensure_ascii=False)


# =========================================================
# Main Entry Point
# =========================================================

if __name__ == "__main__":
    logger.info("Starting NT Validation MCP Server...")
    mcp.run()

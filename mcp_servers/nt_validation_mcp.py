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
# NOTE: BUILTIN_RULES have been moved to DB (migration 026).
# This MCP now delegates to ValidationService for all rule checks.
# =========================================================


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
    Delegates to ValidationService (rules are DB-driven, not hardcoded).

    Args:
        sql: SQL query ที่ต้องการตรวจสอบ
        question: คำถามเดิมของผู้ใช้ (optional)
        context_name: ชื่อ context (revenue, expense)

    Returns:
        JSON with passed status, violations, and warnings
    """
    if not sql or not sql.strip():
        return json.dumps({
            "passed": False,
            "violations": [{"rule": "EMPTY_SQL", "message": "SQL is empty", "severity": "error"}],
            "warnings": [],
            "infos": []
        }, ensure_ascii=False)

    try:
        from app.services.validation_service import ValidationService
        from app.db.session import SessionLocal
        _db = SessionLocal()
        try:
            vs = ValidationService(db=_db)
            result = vs.check_business_rules(sql, context_name=context_name)
            return json.dumps(result, ensure_ascii=False, default=str)
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"ValidationService delegation failed, using fallback: {e}")
        # Fallback: basic checks without DB
        violations = []
        warnings = []
        infos = []

        sql_upper = sql.upper()

        # Minimal hardcoded fallback rules (only if ValidationService is unavailable)
        if re.search(r"(?i)SELECT\s+\*", sql):
            infos.append({"rule": "NO_SELECT_STAR", "message": "ควรระบุคอลัมน์ที่ต้องการแทน SELECT *", "severity": "info"})
        if "DATE" in sql_upper and "/ 1000" not in sql and "YEAR" not in sql_upper:
            warnings.append({"rule": "DATE_CONVERSION", "message": "คอลัมน์ DATE เป็น Unix Timestamp (ms) ควรใช้ YEAR/MONTH แทน", "severity": "warning"})

        passed = len(violations) == 0
        return json.dumps({
            "passed": passed,
            "violations": violations,
            "warnings": warnings,
            "infos": infos,
            "total_issues": len(violations) + len(warnings)
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
    Delegates to ValidationService.calculate_confidence() (single source of truth).
    """
    try:
        from app.services.validation_service import ValidationService
        vs = ValidationService()
        result = vs.calculate_confidence(
            sql_validation_passed=sql_validation_passed,
            sql_issues_count=sql_issues_count,
            sql_warnings_count=sql_warnings_count,
            rules_passed=rules_passed,
            rules_violations_count=rules_violations_count,
            has_similar_example=has_similar_example,
            example_similarity=example_similarity,
            result_row_count=result_row_count,
            execution_success=execution_success,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"ValidationService confidence delegation failed: {e}")
        # Minimal fallback
        score = 50
        return json.dumps({
            "score": score, "max_score": 100,
            "level": "medium", "level_th": "ปานกลาง", "color": "yellow",
            "factors": [], "recommendation": "ไม่สามารถคำนวณได้ — fallback",
            "summary": f"ความมั่นใจ {score}% (ปานกลาง)"
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
    Delegates to ValidationService.validate_result() (single source of truth).
    """
    try:
        from app.services.validation_service import ValidationService
        vs = ValidationService()
        result = vs.validate_result(query_result, expected_columns, context_name)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning(f"ValidationService validate_result delegation failed: {e}")
        return json.dumps({
            "valid": True,
            "issues": [],
            "warnings": [{"message": f"Validation error: {e}"}],
            "stats": {"row_count": len(query_result) if query_result else 0}
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

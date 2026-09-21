"""
NT Metadata MCP Server
======================
MCP Server for exposing NT AI Assistant metadata as tools.

Supports multiple database engines:
- SQLite (default)
- PostgreSQL
- MSSQL

Usage:
    # Run with default SQLite
    python nt_metadata_mcp.py

    # Run with environment variables
    METADATA_DB_URL=postgresql://... python nt_metadata_mcp.py

    # Run with FastMCP
    fastmcp run nt_metadata_mcp.py
"""

import os
import sys
import json
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# Database Configuration
# =========================================================

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    engine: str  # sqlite, postgresql, mssql
    connection_string: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables.

        Every tool here reads config tables (schema_contexts, schema_metadata, mappings, rules,
        golden_examples), which live in the config DB — CONFIG_DB_URL first (REMAIN-9.8: they
        were queried on the business DB and failed); METADATA_DB_URL for single-DB setups.
        """
        db_url = os.getenv("CONFIG_DB_URL") or os.getenv(
            "METADATA_DB_URL",
            f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"
        )

        # Detect engine
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
        if db_url.startswith("sqlite"):
            engine = "sqlite"
        elif "postgresql" in db_url or "postgres" in db_url:
            engine = "postgresql"
        elif "mssql" in db_url or "sqlserver" in db_url:
            engine = "mssql"
        else:
            engine = "sqlite"
        return cls(engine=engine, connection_string=db_url)


# =========================================================
# Database Adapter (Simplified for MCP)
# =========================================================

class MCPDatabaseAdapter:
    """
    Simplified database adapter for MCP server.
    Supports SQLite, PostgreSQL, and MSSQL.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = config.engine

    def _get_sqlite_connection(self):
        """Get SQLite connection (read-only at the connection level)"""
        import sqlite3
        from pathlib import Path
        # Extract path from URL
        path = self.config.connection_string.replace("sqlite:///", "").replace("sqlite://", "")
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Config DB not found at {resolved} (from CONFIG_DB_URL / METADATA_DB_URL)")
        conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_postgresql_connection(self):
        """Get PostgreSQL connection"""
        try:
            import psycopg2
            import psycopg2.extras
            return psycopg2.connect(self.config.connection_string)
        except ImportError:
            raise ImportError("Please install psycopg2: pip install psycopg2-binary")

    def _get_mssql_connection(self):
        """Get MSSQL connection"""
        try:
            import pyodbc
            return pyodbc.connect(self.config.connection_string)
        except ImportError:
            raise ImportError("Please install pyodbc: pip install pyodbc")

    def execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """Execute query and return results as list of dicts"""

        if self.engine == "sqlite":
            conn = self._get_sqlite_connection()
            cursor = conn.cursor()

            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

        elif self.engine == "postgresql":
            import psycopg2.extras
            conn = self._get_postgresql_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

        elif self.engine == "mssql":
            conn = self._get_mssql_connection()
            cursor = conn.cursor()

            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            finally:
                conn.close()

        raise ValueError(f"Unsupported engine: {self.engine}")

    def get_placeholder(self) -> str:
        """Get parameter placeholder for the database engine"""
        if self.engine == "mssql":
            return "?"
        elif self.engine == "postgresql":
            return "%s"
        else:  # sqlite
            return "?"


# =========================================================
# Initialize MCP Server
# =========================================================

mcp = FastMCP(
    name="NT Metadata Server",
    instructions="Provides metadata, schema, mappings, and business rules for NT AI Assistant. Use these tools to get context information, column schemas, semantic mappings, and business rules for SQL generation."
)

# Global database adapter (initialized on first use)
_db_adapter: Optional[MCPDatabaseAdapter] = None


def get_db() -> MCPDatabaseAdapter:
    """Get or create database adapter"""
    global _db_adapter
    if _db_adapter is None:
        config = DatabaseConfig.from_env()
        _db_adapter = MCPDatabaseAdapter(config)
        logger.info(f"Connected to {config.engine} database")
    return _db_adapter


# =========================================================
# MCP Tools - Context Management
# =========================================================

@mcp.tool()
def get_available_contexts() -> List[Dict[str, Any]]:
    """
    ดึงรายการ contexts ที่ใช้ได้ทั้งหมด

    Returns:
        List of contexts with name, display_name, description, main_view, keywords

    Example:
        [
            {
                "name": "revenue",
                "display_name": "รายได้",
                "main_view": "revenue_search",
                "keywords": ["รายได้", "revenue", "sales"]
            }
        ]
    """
    db = get_db()

    results = db.execute_query("""
        SELECT
            name,
            display_name,
            description,
            main_view,
            keywords,
            priority,
            is_active
        FROM schema_contexts
        WHERE is_active = 1 AND status = 'active'
        ORDER BY priority DESC
    """)

    contexts = []
    for row in results:
        keywords = []
        if row.get("keywords"):
            try:
                keywords = json.loads(row["keywords"])
            except (json.JSONDecodeError, TypeError):
                keywords = []

        contexts.append({
            "name": row["name"],
            "display_name": row["display_name"],
            "description": row["description"],
            "main_view": row["main_view"],
            "keywords": keywords,
            "priority": row["priority"]
        })

    return contexts


@mcp.tool()
def route_question_to_context(question: str) -> Dict[str, Any]:
    """
    ระบุ context ที่เหมาะสมสำหรับคำถาม (Auto-detect)

    Args:
        question: คำถามจากผู้ใช้ เช่น "รายได้เดือนมกราคม" หรือ "ค่าใช้จ่ายฝ่ายบุคคล"

    Returns:
        {
            "context": "revenue",
            "display_name": "รายได้",
            "main_view": "revenue_search",
            "confidence": 0.95,
            "matched_keywords": ["รายได้"]
        }
    """
    contexts = get_available_contexts()

    question_lower = question.lower()
    best_match = None
    best_score = 0
    matched_keywords = []

    for ctx in contexts:
        score = 0
        matches = []

        for keyword in ctx.get("keywords", []):
            keyword_lower = keyword.lower()
            if keyword_lower in question_lower:
                score += 1
                matches.append(keyword)

        # Add priority bonus (normalized)
        priority_bonus = ctx.get("priority", 0) * 0.1
        total_score = score + priority_bonus

        if total_score > best_score:
            best_score = total_score
            best_match = ctx
            matched_keywords = matches

    if best_match and best_score > 0:
        # Normalize confidence (max 1.0)
        confidence = min(1.0, best_score / 3)

        return {
            "context": best_match["name"],
            "display_name": best_match["display_name"],
            "main_view": best_match["main_view"],
            "confidence": round(confidence, 2),
            "matched_keywords": matched_keywords
        }

    # Default to first context (highest priority) or "revenue"
    default_ctx = contexts[0] if contexts else {
        "name": "revenue",
        "display_name": "รายได้",
        "main_view": "revenue_search"
    }

    return {
        "context": default_ctx.get("name", "revenue"),
        "display_name": default_ctx.get("display_name", "รายได้"),
        "main_view": default_ctx.get("main_view", "revenue_search"),
        "confidence": 0.5,
        "matched_keywords": []
    }


@mcp.tool()
def get_context_info(context_name: str) -> Dict[str, Any]:
    """
    ดึงข้อมูลรายละเอียดของ context ที่ระบุ

    Args:
        context_name: ชื่อ context เช่น "revenue", "expense"

    Returns:
        Context details including main_view, keywords, description
    """
    db = get_db()
    ph = db.get_placeholder()

    results = db.execute_query(f"""
        SELECT
            name,
            display_name,
            description,
            main_view,
            keywords,
            priority
        FROM schema_contexts
        WHERE name = {ph} AND is_active = 1 AND status = 'active'
    """, (context_name,))

    if not results:
        return {"error": f"Context not found: {context_name}"}

    row = results[0]
    keywords = []
    if row.get("keywords"):
        try:
            keywords = json.loads(row["keywords"])
        except (json.JSONDecodeError, TypeError):
            keywords = []

    return {
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row["description"],
        "main_view": row["main_view"],
        "keywords": keywords,
        "priority": row["priority"]
    }


# =========================================================
# MCP Tools - Schema Information
# =========================================================

@mcp.tool()
def get_schema_for_context(context_name: str) -> Dict[str, Any]:
    """
    ดึง schema metadata สำหรับ context ที่ระบุ

    Args:
        context_name: ชื่อ context เช่น "revenue", "expense"

    Returns:
        {
            "context": "revenue",
            "main_view": "revenue_search",
            "columns": [
                {
                    "name": "REVENUE_VALUE",
                    "type": "REAL",
                    "thai_name": "มูลค่ารายได้",
                    "is_summable": true,
                    "is_groupable": false
                }
            ]
        }
    """
    db = get_db()
    ph = db.get_placeholder()

    # Get context info
    ctx_results = db.execute_query(f"""
        SELECT main_view FROM schema_contexts WHERE name = {ph} AND status = 'active'
    """, (context_name,))

    if not ctx_results:
        return {"error": f"Context not found: {context_name}"}

    main_view = ctx_results[0]["main_view"]

    # Get column metadata
    col_results = db.execute_query(f"""
        SELECT
            column_name,
            data_type,
            display_name_th,
            display_name_en,
            description,
            is_summable,
            is_groupable,
            sample_values,
            special_notes,
            format_hint,
            conversion_sql 
        FROM schema_metadata
        WHERE table_name = {ph} AND status = 'active'
        ORDER BY id
    """, (main_view,))

    columns = []
    for row in col_results:
        sample_values = []
        if row.get("sample_values"):
            try:
                sample_values = json.loads(row["sample_values"])
            except (json.JSONDecodeError, TypeError):
                sample_values = []

        columns.append({
            "name": row["column_name"],
            "type": row["data_type"],
            "thai_name": row["display_name_th"],
            "english_name": row["display_name_en"],
            "description": row["description"],
            "is_summable": bool(row["is_summable"]),
            "is_groupable": bool(row["is_groupable"]),
            "sample_values": sample_values[:10] if sample_values else [], # Increased limit
            "notes": row["special_notes"],
            "format_hint": row["format_hint"],
            "conversion_sql": row["conversion_sql"] # Added field
        })

    return {
        "context": context_name,
        "main_view": main_view,
        "column_count": len(columns),
        "columns": columns
    }


@mcp.tool()
def get_column_info(
    column_name: str,
    context_name: str = "revenue"
) -> Dict[str, Any]:
    """
    ดึงข้อมูลรายละเอียดของ column ที่ระบุ

    Args:
        column_name: ชื่อ column
        context_name: ชื่อ context (default: revenue)

    Returns:
        Column details including type, Thai name, sample values
    """
    db = get_db()
    ph = db.get_placeholder()

    # Get main_view for context
    ctx_results = db.execute_query(f"""
        SELECT main_view FROM schema_contexts WHERE name = {ph} AND status = 'active'
    """, (context_name,))

    if not ctx_results:
        return {"error": f"Context not found: {context_name}"}

    main_view = ctx_results[0]["main_view"]

    # Get column info
    results = db.execute_query(f"""
        SELECT
            column_name,
            data_type,
            display_name_th,
            display_name_en,
            description,
            is_summable,
            is_groupable,
            sample_values,
            special_notes,
            conversion_sql,
            format_hint
        FROM schema_metadata
        WHERE table_name = {ph} AND column_name = {ph} AND status = 'active'
    """, (main_view, column_name))

    if not results:
        return {"error": f"Column not found: {column_name} in {main_view}"}

    row = results[0]
    sample_values = []
    if row.get("sample_values"):
        try:
            sample_values = json.loads(row["sample_values"])
        except (json.JSONDecodeError, TypeError):
            sample_values = []

    return {
        "column_name": row["column_name"],
        "data_type": row["data_type"],
        "thai_name": row["display_name_th"],
        "english_name": row["display_name_en"],
        "description": row["description"],
        "is_summable": bool(row["is_summable"]),
        "is_groupable": bool(row["is_groupable"]),
        "sample_values": sample_values,
        "notes": row["special_notes"],
        "conversion_sql": row["conversion_sql"],
        "format_hint": row["format_hint"]
    }


# =========================================================
# MCP Tools - Semantic Mappings
# =========================================================

@mcp.tool()
def get_semantic_mappings(
    keyword: str = None,
    keyword_type: str = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    ดึง semantic mappings (คำย่อ, synonyms, business terms)

    Args:
        keyword: คำค้นหา (optional)
        keyword_type: ประเภท เช่น "abbreviation", "term", "synonym" (optional)
        limit: จำนวนผลลัพธ์สูงสุด (default: 20)

    Returns:
        List of mappings with keyword, target_column, condition, description
    """
    db = get_db()
    ph = db.get_placeholder()

    query = """
        SELECT
            keyword,
            keyword_type,
            target_column,
            target_condition,
            full_condition,
            description,
            priority
        FROM schema_semantic_mapping
        WHERE is_active = 1 AND status = 'active'
    """
    params = []

    if keyword:
        query += f" AND (keyword LIKE {ph} OR description LIKE {ph})"
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    if keyword_type:
        query += f" AND keyword_type = {ph}"
        params.append(keyword_type)

    query += f" ORDER BY priority DESC LIMIT {ph}"
    params.append(limit)

    results = db.execute_query(query, tuple(params))

    return [
        {
            "keyword": row["keyword"],
            "type": row["keyword_type"],
            "target_column": row["target_column"],
            "condition": row["target_condition"],
            "full_condition": row["full_condition"],
            "description": row["description"],
            "priority": row["priority"]
        }
        for row in results
    ]


@mcp.tool()
def search_mapping_for_term(term: str) -> Dict[str, Any]:
    """
    ค้นหา mapping ที่ตรงกับ term ที่ระบุ

    Args:
        term: คำที่ต้องการค้นหา เช่น "นป.", "มือถือ", "Mobile"

    Returns:
        Mapping result with target column and condition
    """
    db = get_db()
    ph = db.get_placeholder()

    # Exact match first
    results = db.execute_query(f"""
        SELECT
            keyword,
            keyword_type,
            target_column,
            target_condition,
            full_condition,
            description
        FROM schema_semantic_mapping
        WHERE is_active = 1 AND status = 'active' AND keyword = {ph}
        ORDER BY priority DESC
        LIMIT 1
    """, (term,))

    if results:
        row = results[0]
        return {
            "found": True,
            "exact_match": True,
            "keyword": row["keyword"],
            "type": row["keyword_type"],
            "target_column": row["target_column"],
            "condition": row["target_condition"],
            "full_condition": row["full_condition"],
            "description": row["description"]
        }

    # Try partial match
    results = db.execute_query(f"""
        SELECT
            keyword,
            keyword_type,
            target_column,
            target_condition,
            full_condition,
            description
        FROM schema_semantic_mapping
        WHERE is_active = 1 AND status = 'active' AND keyword LIKE {ph}
        ORDER BY priority DESC
        LIMIT 3
    """, (f"%{term}%",))

    if results:
        return {
            "found": True,
            "exact_match": False,
            "suggestions": [
                {
                    "keyword": row["keyword"],
                    "type": row["keyword_type"],
                    "target_column": row["target_column"],
                    "condition": row["target_condition"],
                    "description": row["description"]
                }
                for row in results
            ]
        }

    return {
        "found": False,
        "term": term,
        "message": f"No mapping found for: {term}"
    }


# =========================================================
# MCP Tools - Business Rules
# =========================================================

@mcp.tool()
def get_business_rules(
    table_name: str = None,
    severity: str = None,
    applies_to: str = None
) -> List[Dict[str, Any]]:
    """
    ดึง business rules สำหรับ SQL generation

    Args:
        table_name: filter by table name (optional)
        severity: "error", "warning", "info" (optional)
        applies_to: filter by applies_to field (optional)

    Returns:
        List of business rules with examples
    """
    db = get_db()
    ph = db.get_placeholder()

    query = """
        SELECT
            rule_code,
            rule_name,
            rule_description,
            table_name,
            applies_to,
            example_correct,
            example_wrong,
            severity
        FROM schema_business_rules
        WHERE is_active = 1 AND status = 'active'
    """
    params = []

    if severity:
        query += f" AND severity = {ph}"
        params.append(severity)

    if applies_to:
        query += f" AND applies_to LIKE {ph}"
        params.append(f"%{applies_to}%")

    if table_name:
        query += f" AND table_name = {ph}"
        params.append(table_name)

    query += " ORDER BY severity DESC, rule_code"

    results = db.execute_query(query, tuple(params) if params else None)

    return [
        {
            "code": row["rule_code"],
            "name": row["rule_name"],
            "description": row["rule_description"],
            "table_name": row["table_name"],
            "applies_to": row["applies_to"],
            "correct_example": row["example_correct"],
            "wrong_example": row["example_wrong"],
            "severity": row["severity"]
        }
        for row in results
    ]


@mcp.tool()
def check_rule_violation(
    sql: str,
    question: str,
    table_name: str = "revenue_search"
) -> Dict[str, Any]:
    """
    ตรวจสอบว่า SQL อาจละเมิด business rule ใดบ้าง

    Args:
        sql: SQL query to check
        question: Original question
        table_name: Table name for context (default: revenue_search)

    Returns:
        {
            "violations": [...],
            "warnings": [...],
            "passed": true/false
        }
    """
    import re

    violations = []
    warnings = []

    sql_upper = sql.upper()
    question_lower = question.lower()

    # Get rules for table
    rules = get_business_rules(table_name=table_name)

    # Rule: Exclude "รายได้อื่น" for revenue aggregations
    if "revenue" in table_name.lower():
        aggregate_keywords = ["รวม", "ทั้งหมด", "สัดส่วน", "เปรียบเทียบ", "sum", "total"]
        if any(kw in question_lower for kw in aggregate_keywords):
            if "SUM(" in sql_upper and "BUSINESS_GROUP" in sql_upper:
                if "รายได้อื่น" not in sql and "!=" not in sql and "<>" not in sql:
                    violations.append({
                        "rule": "EXCLUDE_OTHER_REVENUE",
                        "severity": "error",
                        "message": "ต้องตัด 'รายได้อื่น' เมื่อคำนวณรายได้รวม: WHERE BUSINESS_GROUP != 'รายได้อื่น'"
                    })

    # Rule: Use year/month instead of DATE conversion
    if "DATE / 1000" in sql or "strftime" in sql.lower():
        warnings.append({
            "rule": "USE_YEAR_MONTH",
            "severity": "warning",
            "message": "ควรใช้ column year และ month แทนการแปลง DATE"
        })

    # Rule: Quote Thai column names
    thai_columns = ["กลุ่มธุรกิจ", "หมวดบัญชี"]
    for col in thai_columns:
        if col in sql and f'"{col}"' not in sql:
            violations.append({
                "rule": "QUOTE_THAI_COLUMNS",
                "severity": "error",
                "message": f"Column ภาษาไทย '{col}' ต้องใส่ double quotes"
            })

    # Rule: GROUP BY with aggregates
    if "SUM(" in sql_upper or "COUNT(" in sql_upper or "AVG(" in sql_upper:
        if "GROUP BY" not in sql_upper:
            # Check if there are non-aggregated columns
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
            if select_match:
                select_clause = select_match.group(1)
                if not all(agg in select_clause.upper() for agg in ['SUM(', 'COUNT(', 'AVG(']):
                    warnings.append({
                        "rule": "GROUP_BY_REQUIRED",
                        "severity": "warning",
                        "message": "มี aggregate function แต่อาจขาด GROUP BY clause"
                    })

    return {
        "violations": violations,
        "warnings": warnings,
        "passed": len([v for v in violations if v.get("severity") == "error"]) == 0
    }


# =========================================================
# MCP Tools - Golden Examples
# =========================================================

@mcp.tool()
def get_golden_examples(
    category: str = None,
    similar_to: str = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    ดึงตัวอย่าง SQL ที่ถูกต้อง (Golden Examples)

    Args:
        category: ประเภท เช่น "aggregation", "comparison", "time_series"
        similar_to: คำถามที่ต้องการหาตัวอย่างคล้ายกัน
        limit: จำนวนตัวอย่างสูงสุด (default: 5)

    Returns:
        List of golden examples with question, SQL, category
    """
    db = get_db()
    ph = db.get_placeholder()

    query = """
        SELECT
            question_pattern,
            expected_sql,
            category,
            usage_count
        FROM golden_examples
        WHERE is_active = 1 AND status = 'active'
    """
    params = []

    if category:
        query += f" AND category = {ph}"
        params.append(category)

    if similar_to:
        # Simple keyword matching
        query += f" AND question_pattern LIKE {ph}"
        params.append(f"%{similar_to}%")

    query += f" ORDER BY usage_count DESC LIMIT {ph}"
    params.append(limit)

    results = db.execute_query(query, tuple(params))

    return [
        {
            "question": row["question_pattern"],
            "sql": row["expected_sql"],
            "category": row["category"],
            "usage_count": row["usage_count"]
        }
        for row in results
    ]


@mcp.tool()
def find_similar_example(question: str) -> Dict[str, Any]:
    """
    หาตัวอย่างที่คล้ายกับคำถามที่ระบุ

    Args:
        question: คำถามที่ต้องการหาตัวอย่างคล้ายกัน

    Returns:
        Most similar golden example or empty if not found
    """
    # Extract keywords from question (skip common words)
    stop_words = ["ของ", "ที่", "ใน", "และ", "หรือ", "เป็น", "ให้", "ได้", "มี", "ไม่", "the", "a", "an", "is", "are"]
    keywords = [w for w in question.lower().split() if w not in stop_words]

    # Try to find examples with matching keywords
    for keyword in keywords:
        if len(keyword) >= 2:  # Skip very short words
            examples = get_golden_examples(similar_to=keyword, limit=1)
            if examples:
                return {
                    "found": True,
                    "matched_keyword": keyword,
                    "example": examples[0]
                }

    # Fallback: get most used examples
    examples = get_golden_examples(limit=3)

    if examples:
        return {
            "found": False,
            "message": "No exact match found, returning popular examples",
            "suggestions": examples
        }

    return {
        "found": False,
        "message": "No examples found in database",
        "suggestions": []
    }


# =========================================================
# MCP Tools - Database Info
# =========================================================

@mcp.tool()
def get_database_info() -> Dict[str, Any]:
    """
    ดึงข้อมูลเกี่ยวกับ database ที่เชื่อมต่อ

    Returns:
        Database engine, tables, contexts
    """
    db = get_db()

    contexts = get_available_contexts()

    return {
        "engine": db.engine,
        "contexts": [ctx["name"] for ctx in contexts],
        "views": [ctx["main_view"] for ctx in contexts],
        "status": "connected"
    }


@mcp.tool()
def get_syntax_rules(engine: str = None) -> Dict[str, Any]:
    """
    ดึง syntax rules สำหรับ database engine ที่ใช้

    Args:
        engine: "sqlite", "postgresql", "mssql" (optional, default: current engine)

    Returns:
        SQL syntax rules for the specified engine
    """
    db = get_db()
    target_engine = engine or db.engine

    rules = {
        "sqlite": {
            "string_concat": "Use || (e.g., col1 || '-' || col2)",
            "date_format": "Use strftime('%Y-%m', date_col)",
            "limit": "Use LIMIT n",
            "no_top": "Do NOT use TOP",
            "no_concat_function": "Do NOT use CONCAT()",
            "cast": "Use CAST(col AS INTEGER)"
        },
        "postgresql": {
            "string_concat": "Use CONCAT() or ||",
            "date_format": "Use to_char(date_col, 'YYYY-MM')",
            "limit": "Use LIMIT n",
            "no_top": "Do NOT use TOP",
            "cast": "Use ::integer or CAST(col AS INTEGER)"
        },
        "mssql": {
            "string_concat": "Use + (e.g., col1 + '-' + col2)",
            "date_format": "Use FORMAT(date_col, 'yyyy-MM')",
            "limit": "Use TOP n (e.g., SELECT TOP 10 *)",
            "no_limit": "Do NOT use LIMIT",
            "cast": "Use CONVERT(INT, col) or CAST(col AS INT)"
        }
    }

    if target_engine in rules:
        return {
            "engine": target_engine,
            "rules": rules[target_engine]
        }

    return {
        "engine": target_engine,
        "error": f"No rules defined for engine: {target_engine}"
    }


# =========================================================
# Main Entry Point
# =========================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NT Metadata MCP Server")
    parser.add_argument(
        "--db-url",
        help="Database URL (default: from METADATA_DB_URL env or nt_fi_report.sqlite)"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)"
    )

    args = parser.parse_args()

    # Set database URL from args if provided
    if args.db_url:
        os.environ["METADATA_DB_URL"] = args.db_url

    # Run the server
    logger.info("Starting NT Metadata MCP Server...")
    mcp.run(transport=args.transport)

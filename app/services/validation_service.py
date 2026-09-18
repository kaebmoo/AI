"""
Validation Service
====================
Single source of truth for SQL validation, business rule checks, and confidence scoring.
Replaces hardcoded logic from MCP servers.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Security patterns — these are structural constants (not business data), OK to hardcode
DANGEROUS_PATTERNS = [
    'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'INSERT',
    'UPDATE', 'CREATE', 'GRANT', 'REVOKE', 'EXEC',
    'EXECUTE', 'xp_', 'sp_'
]

# File-source guard (Plan 7): SQL reads registered views only, never files directly
# (DuckDB table functions; they don't exist in SQLite). allowed_paths in
# DuckDBFileAdapter is the engine-level second layer.
FILE_ACCESS_PATTERN = r'\b(read_\w+|\w+_scan|glob|sniff_csv|parquet_\w+)\s*\('

INJECTION_PATTERNS = [
    r';\s*--',
    r';\s*DROP',
    r"'\s*UNION\s+SELECT",
    r'OR\s+1\s*=\s*1',
    r"OR\s+'[^']*'\s*=\s*'[^']*'",
]


class ValidationService:
    """Centralized validation for SQL queries and results."""

    def __init__(self, db=None):
        self.db = db

    def validate_sql(self, sql: str) -> Dict[str, Any]:
        """Validate SQL query for safety and correctness.

        Returns:
            {"valid": bool, "issues": [...], "warnings": [...], "sql_type": str}
        """
        issues = []
        warnings = []
        sql_type = None

        if not sql or not sql.strip():
            return {"valid": False, "issues": ["SQL is empty"], "warnings": [], "sql_type": None}

        sql_clean = sql.strip()
        sql_upper = sql_clean.upper()

        # Determine SQL type
        if sql_upper.startswith('SELECT'):
            sql_type = "SELECT"
        elif sql_upper.startswith('WITH'):
            sql_type = "WITH"
        else:
            sql_type = sql_upper.split()[0] if sql_upper.split() else "UNKNOWN"

        # Must be SELECT or WITH (CTE)
        if sql_type not in ('SELECT', 'WITH'):
            issues.append(f"Only SELECT queries (or CTEs starting with WITH) are allowed. Found: {sql_type}")

        # Dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(rf'\b{pattern}\b', sql_upper):
                issues.append(f"Dangerous operation detected: {pattern}")

        if re.search(FILE_ACCESS_PATTERN, sql, re.IGNORECASE):
            issues.append("Direct file access is not allowed — query the registered views")

        # Injection patterns
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, sql_upper):
                issues.append("Potential SQL injection pattern detected")
                break

        # Multiple statements
        semicolon_count = sql_clean.count(';')
        if semicolon_count > 1 or (semicolon_count == 1 and not sql_clean.rstrip().endswith(';')):
            issues.append("Multiple SQL statements are not allowed")

        # Warnings
        if 'SELECT *' in sql_upper:
            warnings.append("Using SELECT * may return unnecessary columns. Consider selecting specific columns.")

        if 'WHERE' not in sql_upper and 'FROM' in sql_upper:
            warnings.append("Query has no WHERE clause - may return large dataset")

        if 'LIMIT' not in sql_upper and 'TOP' not in sql_upper:
            warnings.append("Consider adding LIMIT to prevent large result sets")

        # Thai column names without quotes
        thai_pattern = r'(?<!["\'])[ก-๙]+(?!["\'])'
        if re.search(thai_pattern, sql):
            potential_thai = re.findall(thai_pattern, sql)
            if potential_thai:
                warnings.append(f"Thai column names should be quoted with double quotes: {potential_thai[:3]}")

        # Aggregate without GROUP BY
        aggregate_funcs = ['SUM(', 'COUNT(', 'AVG(', 'MAX(', 'MIN(']
        has_aggregate = any(func in sql_upper for func in aggregate_funcs)
        if has_aggregate and 'GROUP BY' not in sql_upper:
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
            if select_match:
                select_clause = select_match.group(1)
                if ',' in select_clause:
                    warnings.append("Query has aggregate function with multiple columns but no GROUP BY")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "sql_type": sql_type
        }

    def check_business_rules(self, sql: str, context_name: str = None) -> Dict[str, Any]:
        """Check SQL against business rules from DB.

        Returns:
            {"passed": bool, "violations": [...], "warnings": [...]}
        """
        violations = []
        warnings = []

        if not self.db or not sql:
            return {"passed": True, "violations": [], "warnings": []}

        try:
            rules = self._load_rules_from_db(context_name)
        except Exception as e:
            logger.warning(f"Failed to load business rules: {e}")
            return {"passed": True, "violations": [], "warnings": []}

        for rule in rules:
            pattern = rule.get("pattern")
            if not pattern:
                continue

            try:
                match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
                check_type = rule.get("check_type", "regex_warning")
                severity = rule.get("severity", "warning")

                if check_type in ("regex_warning", "context_warning") and match:
                    if severity == "error":
                        violations.append({
                            "rule_code": rule["rule_code"],
                            "message": rule.get("message", rule.get("rule_name", "")),
                            "severity": severity,
                        })
                    else:
                        warnings.append({
                            "rule_code": rule["rule_code"],
                            "message": rule.get("message", rule.get("rule_name", "")),
                            "severity": severity,
                        })
                elif check_type == "regex_error" and match:
                    violations.append({
                        "rule_code": rule["rule_code"],
                        "message": rule.get("message", rule.get("rule_name", "")),
                        "severity": "error",
                    })
            except re.error:
                logger.warning(f"Invalid regex in rule {rule.get('rule_code')}: {pattern}")

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
        }

    def _load_rules_from_db(self, context_name: str = None) -> List[Dict]:
        """Load business rules from schema_business_rules table."""
        from sqlalchemy import text

        sql = """
            SELECT rule_code, rule_name, rule_description, severity,
                   example_correct, example_wrong, pattern, check_type
            FROM schema_business_rules
            WHERE is_active = 1
        """
        params = {}

        if context_name:
            sql += " AND (table_name IS NULL OR table_name = :ctx)"
            params["ctx"] = context_name

        try:
            result = self.db.execute(text(sql), params)
            rows = result.fetchall()
            columns = result.keys()

            rules = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                # For now, rules don't have pattern column — use rule_description as hint
                # Pattern-based checking will be added when rules have regex patterns
                rules.append(row_dict)

            return rules
        except Exception:
            return []

    def validate_result(
        self,
        query_result: List[Dict],
        expected_columns: List[str] = None,
        context_name: str = "revenue",
    ) -> Dict[str, Any]:
        """Validate query results: check columns, nulls, suspicious values.

        Returns:
            {"valid": bool, "issues": [...], "warnings": [...], "stats": {...}}
        """
        issues = []
        warnings = []
        stats = {}

        if not query_result:
            return {
                "valid": True,
                "issues": [],
                "warnings": [{"message": "ไม่มีข้อมูลในผลลัพธ์"}],
                "stats": {"row_count": 0},
            }

        row_count = len(query_result)
        stats["row_count"] = row_count

        if row_count > 0:
            actual_columns = list(query_result[0].keys())
            stats["column_count"] = len(actual_columns)
            stats["columns"] = actual_columns

            # Check expected columns
            if expected_columns:
                missing = set(expected_columns) - set(actual_columns)
                if missing:
                    warnings.append({"message": f"คอลัมน์ที่คาดหวังไม่พบ: {', '.join(missing)}"})

            # Check for null values
            for col in actual_columns:
                null_count = sum(1 for row in query_result if row.get(col) is None)
                if null_count > 0:
                    warnings.append({"message": f"พบค่า NULL ใน {col} ({null_count} rows)"})

            # Check for suspicious values
            for col in actual_columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ('revenue', 'amount', 'value')):
                    values = [row.get(col) for row in query_result if isinstance(row.get(col), (int, float))]
                    if values:
                        max_val = max(values)
                        min_val = min(values)
                        stats[f"{col}_max"] = max_val
                        stats[f"{col}_min"] = min_val
                        stats[f"{col}_sum"] = sum(values)

                        if max_val > 1e12:
                            warnings.append({"message": f"ค่า {col} สูงมาก ({max_val:,.0f}) - ตรวจสอบหน่วย"})
                        if min_val < 0 and 'revenue' in col_lower:
                            warnings.append({"message": f"พบค่า {col} ติดลบ ({min_val:,.2f})"})

        if row_count > 1000:
            warnings.append({"message": f"ผลลัพธ์มีจำนวนมาก ({row_count:,} rows)"})

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "stats": stats,
        }

    def detect_warnings(self, sql: str, results: List[Dict] = None) -> List[Dict]:
        """Detect data quality warnings. Delegates to WarningDetector if available."""
        warnings = []

        try:
            from app.services.warning_detector import WarningDetector
            detector = WarningDetector(self.db)
            warnings = detector.detect(sql, results or [])
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Warning detection failed: {e}")

        return warnings

    def calculate_confidence(
        self,
        sql_validation_passed: bool = True,
        sql_issues_count: int = 0,
        sql_warnings_count: int = 0,
        rules_passed: bool = True,
        rules_violations_count: int = 0,
        has_similar_example: bool = False,
        example_similarity: float = 0.0,
        result_row_count: int = 0,
        execution_success: bool = True,
    ) -> Dict[str, Any]:
        """Calculate confidence score for a query answer.

        Returns dict with: score, max_score, level, level_th, color, factors, recommendation, summary
        """
        score = 0
        factors = []

        # Factor 1: SQL Syntax (25 pts)
        syntax_score = 25 if sql_validation_passed else max(0, 25 - (sql_issues_count * 10))
        syntax_detail = "SQL ถูกต้อง" if sql_validation_passed else f"พบปัญหา {sql_issues_count} รายการ"
        factors.append({"name": "SQL Syntax", "score": syntax_score, "max": 25, "detail": syntax_detail})
        score += syntax_score

        # Factor 2: Business Rules (25 pts)
        rules_score = 25 if rules_passed else max(0, 25 - (rules_violations_count * 12))
        rules_detail = "ผ่านกฎธุรกิจครบ" if rules_passed else f"มีกฎไม่ตรง {rules_violations_count} ข้อ"
        factors.append({"name": "Business Rules", "score": rules_score, "max": 25, "detail": rules_detail})
        score += rules_score

        # Factor 3: Example Match (25 pts)
        if has_similar_example:
            example_score = 25 if example_similarity >= 0.8 else (18 if example_similarity >= 0.5 else 12)
            example_detail = "พบตัวอย่างที่คล้ายกัน" if example_similarity >= 0.5 else "พบตัวอย่างที่เกี่ยวข้อง"
        else:
            example_score = 8
            example_detail = "ไม่พบตัวอย่างที่คล้ายกัน"
        factors.append({"name": "Example Match", "score": example_score, "max": 25, "detail": example_detail})
        score += example_score

        # Factor 4: Execution (25 pts)
        if execution_success:
            exec_score = 25 if result_row_count > 0 else 15
            exec_detail = f"ได้ผลลัพธ์ {result_row_count} รายการ" if result_row_count > 0 else "Execute สำเร็จ แต่ไม่มีข้อมูล"
        else:
            exec_score = 0
            exec_detail = "Execute ไม่สำเร็จ"
        factors.append({"name": "Execution", "score": exec_score, "max": 25, "detail": exec_detail})
        score += exec_score

        # Penalty for warnings
        warning_penalty = min(10, sql_warnings_count * 2)
        if warning_penalty > 0:
            score = max(0, score - warning_penalty)

        # Level
        if score >= 85:
            level, level_th, color = "high", "สูง", "green"
            recommendation = "สามารถใช้ข้อมูลนี้ได้เลย"
        elif score >= 65:
            level, level_th, color = "medium", "ปานกลาง", "yellow"
            recommendation = "ควรตรวจสอบข้อมูลก่อนใช้งาน"
        elif score >= 40:
            level, level_th, color = "low", "ต่ำ", "orange"
            recommendation = "ควรตรวจสอบ SQL และผลลัพธ์อย่างละเอียด"
        else:
            level, level_th, color = "very_low", "ต่ำมาก", "red"
            recommendation = "ไม่แนะนำให้ใช้โดยตรง กรุณาปรึกษาผู้เชี่ยวชาญ"

        return {
            "score": score,
            "max_score": 100,
            "level": level,
            "level_th": level_th,
            "color": color,
            "factors": factors,
            "recommendation": recommendation,
            "summary": f"ความมั่นใจ {score}% ({level_th})"
        }

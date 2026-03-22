"""
NT AI Assistant - Warning Detector
=====================================
Detect data warnings based on content and SQL patterns.

Extracted from chat.py for reuse by QueryEngine and other callers.
Warning definitions are loaded from `data_warnings` table with in-memory cache.
"""

import re
import json
import time
import logging
from typing import List, Dict, Any, Optional

from app.schemas.chat import DataWarning

logger = logging.getLogger(__name__)

# Hardcoded fallback — used only when DB is unavailable
_HARDCODED_WARNINGS = [
    {
        "code": "OTHER_REVENUE_NOT_NET",
        "keywords": ["รายได้อื่น"],
        "exclude_keywords": ["ผลตอบแทนทางการเงิน"],
        "columns_to_check": ["BUSINESS_GROUP", "SERVICE_GROUP", "PRODUCT_NAME", "gl_group"],
        "message": "หมายเหตุ: 'รายได้อื่น' เป็นรายได้ที่ยังไม่สุทธิ",
        "severity": "warning"
    },
]

# In-memory cache for warning definitions
_warnings_cache: Optional[List[Dict]] = None
_warnings_cache_ts: float = 0.0
_WARNINGS_CACHE_TTL = 3600  # 1 hour


def _load_warnings_from_db() -> Optional[List[Dict]]:
    """Load active warning definitions from data_warnings table."""
    try:
        from app.db.session import ConfigSessionLocal
        db = ConfigSessionLocal()
        try:
            from app.models.schema_models import DataWarningModel
            rows = db.query(DataWarningModel).filter(
                DataWarningModel.is_active == True
            ).all()
            warnings = []
            for row in rows:
                w = {
                    "code": row.code,
                    "keywords": json.loads(row.keywords) if isinstance(row.keywords, str) else row.keywords,
                    "exclude_keywords": json.loads(row.exclude_keywords) if row.exclude_keywords and isinstance(row.exclude_keywords, str) else (row.exclude_keywords or []),
                    "columns_to_check": json.loads(row.columns_to_check) if isinstance(row.columns_to_check, str) else row.columns_to_check,
                    "message": row.message,
                    "severity": row.severity or "warning",
                    "context_name": row.context_name,
                }
                warnings.append(w)
            return warnings
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not load warnings from DB: {e}")
        return None


def get_warning_definitions() -> List[Dict]:
    """Get warning definitions with cache. Falls back to hardcoded if DB unavailable."""
    global _warnings_cache, _warnings_cache_ts

    now = time.time()
    if _warnings_cache is not None and (now - _warnings_cache_ts) < _WARNINGS_CACHE_TTL:
        return _warnings_cache

    db_warnings = _load_warnings_from_db()
    if db_warnings is not None:
        _warnings_cache = db_warnings
        _warnings_cache_ts = now
        logger.debug(f"Loaded {len(db_warnings)} warning definitions from DB")
        return db_warnings

    # Fallback to hardcoded
    logger.debug("Using hardcoded warning definitions (DB unavailable)")
    return _HARDCODED_WARNINGS


def clear_warnings_cache():
    """Clear the warnings cache. Called by admin API after mutations."""
    global _warnings_cache, _warnings_cache_ts
    _warnings_cache = None
    _warnings_cache_ts = 0.0


class WarningDetector:
    """Detect data warnings based on content and SQL patterns."""

    def __init__(self, mcp_client=None, schema_service=None):
        self.mcp_client = mcp_client
        self.schema_service = schema_service

    async def detect(
        self,
        data: List[Dict[str, Any]],
        sql_query: str,
        context_name: str = "revenue",
    ) -> List[DataWarning]:
        """
        Run all warning detectors and return combined warnings.
        """
        warnings = []

        # 1. Standard data warnings (based on content)
        if data:
            warnings.extend(self.detect_data_warnings(data, sql_query, context_name))

        # 2. Multiple sources warning (when LIKE matches multiple values)
        if sql_query and 'LIKE' in sql_query.upper() and self.mcp_client:
            try:
                multiple_source_warnings = await self.detect_multiple_sources_warning(
                    sql_query, context_name
                )
                warnings.extend(multiple_source_warnings)
            except Exception as e:
                logger.debug(f"Multiple sources warning check failed: {e}")

        return warnings

    @staticmethod
    def detect_data_warnings(
        data: List[Dict[str, Any]],
        sql_query: str = None,
        context_name: str = None,
    ) -> List[DataWarning]:
        """Detect warnings based on data content."""
        warnings = []
        if not data:
            return warnings

        warning_defs = get_warning_definitions()

        for warning_def in warning_defs:
            # Filter by context if specified
            wctx = warning_def.get("context_name")
            if wctx and context_name and wctx != context_name:
                continue

            warning_triggered = False

            for row in data:
                row_str = str(row.values()).lower()

                for keyword in warning_def["keywords"]:
                    if keyword.lower() in row_str:
                        warning_triggered = True
                        break

                if warning_triggered:
                    break

            if warning_triggered:
                warnings.append(DataWarning(
                    code=warning_def["code"],
                    message=warning_def["message"],
                    severity=warning_def["severity"]
                ))

        return warnings

    async def detect_multiple_sources_warning(
        self,
        sql_query: str,
        context_name: str = "revenue",
    ) -> List[DataWarning]:
        """
        Detect when LIKE query matches multiple distinct values.
        Warns user that aggregated data comes from multiple sources.
        """
        warnings = []

        if not sql_query or not self.mcp_client:
            return warnings

        # Get groupable columns from DB metadata
        GROUP_COLUMNS = []
        table = context_name
        if self.schema_service:
            context_info = self.schema_service.get_context_info(context_name)
            if context_info:
                table = context_info.get('main_view', context_name)
            cols = self.schema_service.get_searchable_columns(context_name, table)
            GROUP_COLUMNS = [c.lower() for c in cols]

        if not GROUP_COLUMNS:
            return warnings

        # Find LIKE conditions in SQL
        like_pattern = r"(\w+)\s+LIKE\s+'%([^%]+)%'"
        matches = re.findall(like_pattern, sql_query, re.IGNORECASE)

        if not matches:
            return warnings

        for column, search_value in matches:
            column_lower = column.lower()

            if column_lower not in GROUP_COLUMNS:
                continue

            check_sql = f"""
                SELECT DISTINCT "{column}" as matched_value
                FROM {table}
                WHERE "{column}" LIKE '%{search_value}%'
                LIMIT 10
            """

            try:
                result = await self.mcp_client.call_tool("execute_query", {
                    "sql": check_sql,
                    "limit": 10,
                    "validate_first": False
                })

                result_data = json.loads(result) if isinstance(result, str) else result

                if result_data.get("success") and result_data.get("data"):
                    matched_values = [
                        row.get("matched_value")
                        for row in result_data["data"]
                        if row.get("matched_value")
                    ]

                    if len(matched_values) > 1:
                        values_list = ", ".join([f"'{v}'" for v in matched_values[:5]])
                        if len(matched_values) > 5:
                            values_list += f" และอื่นๆ อีก {len(matched_values) - 5} รายการ"

                        warnings.append(DataWarning(
                            code="MULTIPLE_SOURCES",
                            message=f"⚠️ ข้อมูลรวมจากหลายกลุ่ม: {values_list}",
                            severity="important"
                        ))

            except Exception as e:
                logger.debug(f"Multiple sources check failed: {e}")

        return warnings


# ============================================================
# Standalone functions for backward compatibility with chat.py
# ============================================================

def detect_data_warnings(data: List[Dict[str, Any]], sql_query: str = None) -> List[DataWarning]:
    """Backward-compatible standalone function."""
    return WarningDetector.detect_data_warnings(data, sql_query)


async def detect_multiple_sources_warning(
    sql_query: str,
    mcp_client,
    context_name: str = "revenue",
    schema_service=None,
) -> List[DataWarning]:
    """Backward-compatible standalone function."""
    detector = WarningDetector(mcp_client=mcp_client, schema_service=schema_service)
    return await detector.detect_multiple_sources_warning(sql_query, context_name)

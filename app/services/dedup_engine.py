"""
Dedup Engine
==============
Prevents duplicate or conflicting config entries before insertion.
Used by Admin Agent tools and Auto-Analyzer.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class DedupResult:
    has_duplicate: bool
    duplicate_type: Optional[str] = None  # exact, case_insensitive, conflict, similar
    existing_id: Optional[int] = None
    existing_value: Optional[str] = None
    message: str = ""


class DedupEngine:
    """Check for duplicates before inserting config entries."""

    def __init__(self, db: Session):
        self.db = db

    def check_mapping_duplicate(self, keyword: str, target_column: str = None) -> DedupResult:
        """Check if a semantic mapping already exists for this keyword."""
        from app.models.schema_models import SchemaSemanticMapping

        # Exact match
        exact = self.db.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword == keyword,
            SchemaSemanticMapping.is_active == True,
        ).first()

        if exact:
            return DedupResult(
                has_duplicate=True,
                duplicate_type="exact",
                existing_id=exact.id,
                existing_value=exact.keyword,
                message=f"Exact match: '{keyword}' → {exact.target_column} (id={exact.id})"
            )

        # Case-insensitive match
        case_match = self.db.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword.ilike(keyword),
            SchemaSemanticMapping.is_active == True,
        ).first()

        if case_match:
            return DedupResult(
                has_duplicate=True,
                duplicate_type="case_insensitive",
                existing_id=case_match.id,
                existing_value=case_match.keyword,
                message=f"Case-insensitive match: '{case_match.keyword}' (id={case_match.id})"
            )

        # Conflict: same keyword → different column
        if target_column:
            conflict = self.db.query(SchemaSemanticMapping).filter(
                SchemaSemanticMapping.keyword == keyword,
                SchemaSemanticMapping.target_column != target_column,
                SchemaSemanticMapping.is_active == True,
            ).first()

            if conflict:
                return DedupResult(
                    has_duplicate=True,
                    duplicate_type="conflict",
                    existing_id=conflict.id,
                    existing_value=conflict.target_column,
                    message=f"Conflict: '{keyword}' already maps to {conflict.target_column}, not {target_column}"
                )

        return DedupResult(has_duplicate=False)

    def check_rule_duplicate(self, rule_code: str) -> DedupResult:
        """Check if a business rule with this code exists."""
        from app.models.schema_models import SchemaBusinessRule

        existing = self.db.query(SchemaBusinessRule).filter(
            SchemaBusinessRule.rule_code == rule_code
        ).first()

        if existing:
            return DedupResult(
                has_duplicate=True,
                duplicate_type="exact",
                existing_id=existing.id,
                existing_value=existing.rule_code,
                message=f"Rule '{rule_code}' already exists (id={existing.id})"
            )

        return DedupResult(has_duplicate=False)

    def check_example_duplicate(self, question: str, sql: str) -> DedupResult:
        """Check if a golden example with similar question or identical SQL exists."""
        from app.models.feedback_models import GoldenExample

        # Exact SQL match
        sql_match = self.db.query(GoldenExample).filter(
            GoldenExample.expected_sql == sql,
            GoldenExample.is_active == True,
        ).first()

        if sql_match:
            return DedupResult(
                has_duplicate=True,
                duplicate_type="exact_sql",
                existing_id=sql_match.id,
                existing_value=sql_match.expected_sql[:100],
                message=f"Exact SQL match (id={sql_match.id})"
            )

        # Similar question (substring match)
        similar = self.db.query(GoldenExample).filter(
            GoldenExample.question_pattern.ilike(f"%{question[:50]}%"),
            GoldenExample.is_active == True,
        ).first()

        if similar:
            return DedupResult(
                has_duplicate=True,
                duplicate_type="similar_question",
                existing_id=similar.id,
                existing_value=similar.question_pattern[:100],
                message=f"Similar question found (id={similar.id}): '{similar.question_pattern[:60]}'"
            )

        return DedupResult(has_duplicate=False)

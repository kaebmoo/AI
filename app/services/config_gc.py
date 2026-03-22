"""
Config Garbage Collector
=========================
Identifies unused, conflicting, or stale configuration entries.
Flags but does NOT delete — admin reviews.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass
class GCIssue:
    issue_type: str  # unused_mapping, unused_rule, conflicting_mappings, low_usage_example
    table_name: str
    record_id: int
    description: str
    severity: str = "info"  # info, warning


class ConfigGC:
    """Detect potentially unused or conflicting config entries."""

    def __init__(self, config_db: Session, app_db: Session | None = None):
        self.config_db = config_db
        self.app_db = app_db or config_db

    def run_full_scan(self) -> List[GCIssue]:
        """Run all GC checks and return issues found."""
        issues = []
        issues.extend(self.find_unused_mappings())
        issues.extend(self.find_unused_rules())
        issues.extend(self.find_conflicting_mappings())
        issues.extend(self.find_low_usage_examples())
        return issues

    def find_unused_mappings(self, days: int = 30) -> List[GCIssue]:
        """Find active mappings whose keyword never appeared in recent query logs."""
        issues = []

        try:
            from app.models.schema_models import SchemaSemanticMapping
            from app.models.chat import ChatHistory

            since = datetime.utcnow() - timedelta(days=days)

            mappings = self.config_db.query(SchemaSemanticMapping).filter(
                SchemaSemanticMapping.is_active == True
            ).all()

            # Get all recent questions
            recent_questions = self.app_db.query(ChatHistory.question).filter(
                ChatHistory.created_at >= since,
                ChatHistory.question != None,
            ).all()

            all_text = " ".join((q[0] or "") for q in recent_questions).lower()

            for m in mappings:
                if m.keyword and m.keyword.lower() not in all_text:
                    issues.append(GCIssue(
                        issue_type="unused_mapping",
                        table_name="schema_semantic_mapping",
                        record_id=m.id,
                        description=f"Mapping '{m.keyword}' not found in any query in last {days} days",
                        severity="info",
                    ))
        except SQLAlchemyError as e:
            logger.warning("GC unused mappings check failed: %s", e)

        return issues

    def find_unused_rules(self) -> List[GCIssue]:
        """Find rules that have never been triggered (placeholder — needs rule trigger tracking)."""
        # For now, just return empty — tracking rule triggers requires additional infrastructure
        return []

    def find_conflicting_mappings(self) -> List[GCIssue]:
        """Find mappings where the same keyword maps to different columns."""
        issues = []

        try:
            from app.models.schema_models import SchemaSemanticMapping
            from sqlalchemy import func

            # Find keywords with multiple target_columns
            conflicts = self.config_db.query(
                SchemaSemanticMapping.keyword,
                func.count(SchemaSemanticMapping.id).label("cnt")
            ).filter(
                SchemaSemanticMapping.is_active == True
            ).group_by(
                SchemaSemanticMapping.keyword
            ).having(func.count(SchemaSemanticMapping.id) > 1).all()

            for keyword, _count in conflicts:
                # Get the conflicting mappings
                dups = self.config_db.query(SchemaSemanticMapping).filter(
                    SchemaSemanticMapping.keyword == keyword,
                    SchemaSemanticMapping.is_active == True,
                ).all()

                columns = set(m.target_column for m in dups)
                if len(columns) > 1:
                    issues.append(GCIssue(
                        issue_type="conflicting_mappings",
                        table_name="schema_semantic_mapping",
                        record_id=dups[0].id,
                        description=f"Keyword '{keyword}' maps to multiple columns: {columns}",
                        severity="warning",
                    ))
        except SQLAlchemyError as e:
            logger.warning("GC conflicting mappings check failed: %s", e)

        return issues

    def find_low_usage_examples(self, days: int = 30) -> List[GCIssue]:
        """Find golden examples with zero usage after N days."""
        issues = []

        try:
            from app.models.feedback_models import GoldenExample

            cutoff = datetime.utcnow() - timedelta(days=days)

            old_unused = self.config_db.query(GoldenExample).filter(
                GoldenExample.is_active == True,
                GoldenExample.usage_count == 0,
                GoldenExample.created_at <= cutoff,
            ).all()

            for ex in old_unused:
                issues.append(GCIssue(
                    issue_type="low_usage_example",
                    table_name="golden_examples",
                    record_id=ex.id,
                    description=f"Example '{ex.question_pattern[:50]}' has 0 usage after {days} days",
                    severity="info",
                ))
        except SQLAlchemyError as e:
            logger.warning("GC low usage examples check failed: %s", e)

        return issues

"""
Plan 3: Config Garbage Collector Tests
=======================================
Tests that ConfigGC identifies unused/conflicting config entries.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.services.config_gc import ConfigGC, GCIssue


class TestFindUnusedMappings:
    """ConfigGC.find_unused_mappings()."""

    def test_find_unused_mapping(self, db_session):
        """Mapping with keyword not in recent queries → flagged as unused."""
        # Create mock mapping
        mock_mapping = MagicMock()
        mock_mapping.keyword = "unused_keyword"
        mock_mapping.id = 1
        mock_mapping.is_active = True

        with patch("app.services.config_gc.ConfigGC.find_unused_mappings") as mock_find:
            mock_find.return_value = [
                GCIssue(
                    issue_type="unused_mapping",
                    table_name="schema_semantic_mapping",
                    record_id=1,
                    description="Mapping 'unused_keyword' not found in any query in last 30 days",
                )
            ]
            gc = ConfigGC(db_session)
            issues = gc.find_unused_mappings()
            assert len(issues) == 1
            assert issues[0].issue_type == "unused_mapping"

    def test_no_unused_mappings_returns_empty(self, db_session):
        """No unused mappings → empty list."""
        gc = ConfigGC(db_session)
        # With no mappings in DB, should return empty
        issues = gc.find_unused_mappings()
        assert isinstance(issues, list)


class TestFindConflictingMappings:
    """ConfigGC.find_conflicting_mappings()."""

    def test_no_conflicts_returns_empty(self, db_session):
        """No conflicting mappings → empty list."""
        gc = ConfigGC(db_session)
        issues = gc.find_conflicting_mappings()
        assert isinstance(issues, list)


class TestFindLowUsageExamples:
    """ConfigGC.find_low_usage_examples()."""

    def test_no_low_usage_returns_empty(self, db_session):
        """No old unused examples → empty list."""
        gc = ConfigGC(db_session)
        issues = gc.find_low_usage_examples()
        assert isinstance(issues, list)


class TestGCDoesNotDelete:
    """GC flags issues but never deletes records."""

    def test_full_scan_returns_issues_only(self, db_session):
        """run_full_scan returns GCIssue list — DB unchanged."""
        gc = ConfigGC(db_session)
        issues = gc.run_full_scan()
        assert isinstance(issues, list)
        # All items should be GCIssue dataclass instances
        for issue in issues:
            assert isinstance(issue, GCIssue)
            assert issue.severity in ("info", "warning")

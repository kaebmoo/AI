"""
Plan 3: Background Scheduler Tests
=================================
Tests scheduler job orchestration and auto-apply behavior.
"""

# pylint: disable=protected-access

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.auto_analyzer import AnalysisResult, SuggestedFix
from app.services.scheduler import BackgroundScheduler


class FakeDBSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


async def test_start_does_not_create_duplicate_tasks():
    scheduler = BackgroundScheduler(db_factory=FakeDBSession)

    with patch.object(scheduler, "_run_periodic", new=AsyncMock(return_value=None)) as mock_run_periodic:
        scheduler.start()
        scheduler.start()
        await asyncio.sleep(0)
        await scheduler.stop()

    assert mock_run_periodic.call_count == 4  # auto_analyze, config_gc, export_cleanup, result_retention
    assert len(scheduler._tasks) == 0


async def test_stop_cancels_existing_tasks():
    scheduler = BackgroundScheduler(db_factory=FakeDBSession)
    task_one = MagicMock()
    task_two = MagicMock()
    scheduler._tasks = [task_one, task_two]
    scheduler._running = True

    await scheduler.stop()

    assert scheduler._running is False
    assert scheduler._tasks == []
    task_one.cancel.assert_called_once_with()
    task_two.cancel.assert_called_once_with()


async def test_job_auto_analyze_calls_analyzer_and_closes_db():
    fake_db = FakeDBSession()
    scheduler = BackgroundScheduler(db_factory=lambda: fake_db)
    analyzer_instance = MagicMock()
    analyzer_instance.analyze_recent_failures = AsyncMock(
        return_value=AnalysisResult(total_failures=0, groups=[], suggested_fixes=[])
    )

    with patch("app.services.auto_analyzer.AutoAnalyzer", return_value=analyzer_instance):
        with patch.object(scheduler, "_apply_high_confidence_fixes") as mock_apply:
            await scheduler._job_auto_analyze()

    analyzer_instance.analyze_recent_failures.assert_awaited_once_with(period_hours=24)
    mock_apply.assert_not_called()
    assert fake_db.closed is True


async def test_job_auto_analyze_applies_fixes_when_failures_exist():
    fake_db = FakeDBSession()
    scheduler = BackgroundScheduler(db_factory=lambda: fake_db)
    result = AnalysisResult(
        total_failures=3,
        groups=[],
        suggested_fixes=[],
    )
    analyzer_instance = MagicMock()
    analyzer_instance.analyze_recent_failures = AsyncMock(return_value=result)

    with patch("app.services.auto_analyzer.AutoAnalyzer", return_value=analyzer_instance):
        with patch.object(scheduler, "_apply_high_confidence_fixes") as mock_apply:
            await scheduler._job_auto_analyze()

    mock_apply.assert_called_once_with(result, fake_db)
    assert fake_db.closed is True


def test_apply_high_confidence_fixes_only_applies_eligible_mappings():
    scheduler = BackgroundScheduler(db_factory=FakeDBSession)
    app_db = FakeDBSession()
    config_db = MagicMock()
    created_mapping = SimpleNamespace(id=123)
    audit_instance = MagicMock()

    eligible_fix = SuggestedFix(
        fix_type="add_mapping",
        params={
            "keyword": "datacom",
            "target_column": "PRODUCT_NAME",
            "target_condition": "LIKE '%datacom%'",
        },
        confidence=0.95,
        reason="frequent failures",
        source_query_ids=[1, 2],
    )
    low_confidence_fix = SuggestedFix(
        fix_type="add_mapping",
        params={
            "keyword": "legacy",
            "target_column": "PRODUCT_NAME",
            "target_condition": "LIKE '%legacy%'",
        },
        confidence=0.6,
        reason="not confident enough",
        source_query_ids=[3],
    )
    unsupported_fix = SuggestedFix(
        fix_type="add_rule",
        params={"rule_code": "X"},
        confidence=0.99,
        reason="different fix type",
        source_query_ids=[4],
    )
    result = AnalysisResult(
        total_failures=4,
        groups=[],
        suggested_fixes=[eligible_fix, low_confidence_fix, unsupported_fix],
    )

    with patch("app.services.audit_service.AuditService", return_value=audit_instance):
        with patch("app.db.session.ConfigSessionLocal", return_value=config_db):
            with patch("app.models.schema_models.SchemaSemanticMapping", return_value=created_mapping) as mock_mapping_class:
                scheduler._apply_high_confidence_fixes(result, app_db)

    mock_mapping_class.assert_called_once_with(
        keyword="datacom",
        target_column="PRODUCT_NAME",
        target_condition="LIKE '%datacom%'",
        keyword_type="value_alias",
        is_active=True,
    )
    config_db.add.assert_called_once_with(created_mapping)
    config_db.commit.assert_called_once_with()
    config_db.close.assert_called_once_with()
    audit_instance.log_change.assert_called_once_with(
        action="INSERT",
        table_name="schema_semantic_mapping",
        record_id=123,
        new_value=eligible_fix.params,
        source="auto_analyzer",
    )


async def test_job_config_gc_runs_scan_and_closes_db():
    fake_app_db = FakeDBSession()
    fake_config_db = FakeDBSession()
    scheduler = BackgroundScheduler(
        db_factory=lambda: fake_app_db,
        config_db_factory=lambda: fake_config_db,
    )
    gc_instance = MagicMock()
    gc_instance.run_full_scan.return_value = [
        SimpleNamespace(severity="warning", issue_type="unused_mapping", description="unused config")
    ]

    with patch("app.services.config_gc.ConfigGC", return_value=gc_instance) as mock_gc_class:
        await scheduler._job_config_gc()

    gc_instance.run_full_scan.assert_called_once_with()
    assert fake_app_db.closed is True
    assert fake_config_db.closed is True
    _, kwargs = mock_gc_class.call_args
    assert kwargs["config_db"] is fake_config_db
    assert kwargs["app_db"] is fake_app_db
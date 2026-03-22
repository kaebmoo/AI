"""
Background Scheduler
=====================
Runs periodic jobs: auto-analyzer, config GC, fix application.
Uses asyncio tasks — no external dependency needed.
Falls back gracefully if DB is not available.
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Job intervals (seconds)
AUTO_ANALYZE_INTERVAL = 6 * 3600   # 6 hours
CONFIG_GC_INTERVAL = 24 * 3600     # 24 hours


class BackgroundScheduler:
    """Simple asyncio-based scheduler for periodic jobs."""

    def __init__(self, db_factory):
        """
        Args:
            db_factory: Callable that returns a new DB session (e.g., SessionLocal).
        """
        self._db_factory = db_factory
        self._tasks = []
        self._running = False

    def start(self):
        """Start all scheduled jobs as background tasks."""
        if self._running:
            return
        self._running = True

        self._tasks.append(asyncio.create_task(
            self._run_periodic("auto_analyze", AUTO_ANALYZE_INTERVAL, self._job_auto_analyze)
        ))
        self._tasks.append(asyncio.create_task(
            self._run_periodic("config_gc", CONFIG_GC_INTERVAL, self._job_config_gc)
        ))

        logger.info("Background scheduler started with %d jobs", len(self._tasks))

    async def stop(self):
        """Cancel all running jobs."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Background scheduler stopped")

    async def _run_periodic(self, name: str, interval: float, job_fn):
        """Run a job periodically with error recovery."""
        # Initial delay — let app finish startup
        await asyncio.sleep(30)

        while self._running:
            try:
                logger.info(f"[Scheduler] Running {name}...")
                await job_fn()
                logger.info(f"[Scheduler] {name} completed")
            except Exception as e:
                logger.error(f"[Scheduler] {name} failed: {e}")

            await asyncio.sleep(interval)

    async def _job_auto_analyze(self):
        """Analyze recent query failures, suggest fixes, auto-apply high-confidence ones."""
        db = self._db_factory()
        try:
            from app.services.auto_analyzer import AutoAnalyzer
            analyzer = AutoAnalyzer(db)
            result = await analyzer.analyze_recent_failures(period_hours=24)
            if result and result.total_failures > 0:
                logger.info(
                    f"[AutoAnalyze] {result.total_failures} failures, "
                    f"{len(result.groups)} groups, "
                    f"{len(result.suggested_fixes)} suggested fixes"
                )
                # Auto-apply high-confidence fixes
                self._apply_high_confidence_fixes(result, db)
        finally:
            db.close()

    def _apply_high_confidence_fixes(self, result, db):
        """Apply suggested fixes with confidence >= 0.8 automatically."""
        from app.services.audit_service import AuditService
        audit = AuditService(db)

        for fix in result.suggested_fixes:
            if fix.confidence < 0.8:
                continue
            if not fix.auto_applicable:
                continue

            try:
                if fix.fix_type == "add_mapping":
                    from app.models.schema_models import SchemaSemanticMapping
                    from app.db.session import ConfigSessionLocal
                    config_db = ConfigSessionLocal()
                    mapping = SchemaSemanticMapping(
                        keyword=fix.params.get("keyword", ""),
                        target_column=fix.params.get("target_column", ""),
                        target_condition=fix.params.get("target_condition", ""),
                        keyword_type="value_alias",
                        is_active=True,
                    )
                    config_db.add(mapping)
                    config_db.commit()
                    audit.log_change(
                        action="INSERT", table_name="schema_semantic_mapping",
                        record_id=mapping.id,
                        new_value=fix.params,
                        source="auto_analyzer",
                    )
                    config_db.close()
                    logger.info(f"[AutoApply] Applied {fix.fix_type}: {fix.params}")
            except Exception as e:
                logger.warning(f"[AutoApply] Failed to apply {fix.fix_type}: {e}")

    async def _job_config_gc(self):
        """Scan for unused/conflicting config entries."""
        db = self._db_factory()
        try:
            from app.services.config_gc import ConfigGC
            gc = ConfigGC(db)
            issues = gc.run_full_scan()
            if issues:
                logger.info(f"[ConfigGC] Found {len(issues)} issues")
                for issue in issues[:10]:
                    logger.info(f"  [{issue.severity}] {issue.issue_type}: {issue.description}")
        finally:
            db.close()

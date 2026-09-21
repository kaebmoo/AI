"""
Background Scheduler
=====================
Runs periodic jobs: auto-analyzer, config GC, fix application.
Uses asyncio tasks — no external dependency needed.
Falls back gracefully if DB is not available.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Job intervals (seconds)
AUTO_ANALYZE_INTERVAL = 6 * 3600   # 6 hours
CONFIG_GC_INTERVAL = 24 * 3600     # 24 hours
EXPORT_CLEANUP_INTERVAL = 24 * 3600  # daily
RESULT_RETENTION_INTERVAL = 24 * 3600  # daily


class BackgroundScheduler:
    """Simple asyncio-based scheduler for periodic jobs."""

    def __init__(self, db_factory, config_db_factory=None):
        """
        Args:
            db_factory: Callable that returns a new DB session (e.g., SessionLocal).
            config_db_factory: Callable that returns a config DB session.
        """
        self._db_factory = db_factory
        self._config_db_factory = config_db_factory or db_factory
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
        self._tasks.append(asyncio.create_task(
            self._run_periodic("export_cleanup", EXPORT_CLEANUP_INTERVAL, self._job_export_cleanup)
        ))

        self._tasks.append(asyncio.create_task(
            self._run_periodic("result_retention", RESULT_RETENTION_INTERVAL, self._job_result_retention)
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
                logger.info("[Scheduler] Running %s...", name)
                await job_fn()
                logger.info("[Scheduler] %s completed", name)
            except Exception as e:
                logger.error("[Scheduler] %s failed: %s", name, e)

            await asyncio.sleep(interval)

    async def _job_auto_analyze(self):
        """Analyze recent query failures, suggest fixes, auto-apply high-confidence ones."""
        db = self._db_factory()
        config_db = self._config_db_factory()
        try:
            from app.services.auto_analyzer import AutoAnalyzer
            analyzer = AutoAnalyzer(db, config_db=config_db)
            result = await analyzer.analyze_recent_failures(period_hours=24)
            if result and result.total_failures > 0:
                logger.info(
                    "[AutoAnalyze] %s failures, %s groups, %s suggested fixes",
                    result.total_failures,
                    len(result.groups),
                    len(result.suggested_fixes),
                )
                self._propose_fixes(result, db, config_db)
        finally:
            config_db.close()
            db.close()

    def _propose_fixes(self, result, db, config_db):
        """What the learner found waits for a person — it is never put in use by itself (Plan 8.1, owner 2026-09-21).

        A mapping for a keyword nobody has is a `learned` row with status `proposed` (the prompt reads `active`
        only); a keyword a person owns keeps its mapping and the learner's waits in knowledge_proposals. It used
        to auto-apply at confidence >= 0.8 — which its heuristics never reach (0.4 / 0.5), and the keyword check
        ran on the app.db session, so nothing was ever written. Other fix types have no content to propose yet.
        """
        from app.models.schema_models import SchemaSemanticMapping
        from app.services.audit_service import AuditService
        from app.services.provenance import LEARNED, PROPOSED, may_replace, propose
        audit = AuditService(db)

        for fix in result.suggested_fixes:
            if fix.fix_type != "add_mapping" or not fix.params.get("keyword"):
                continue
            try:
                keyword = fix.params["keyword"]
                values = {"target_column": fix.params.get("target_column", ""),
                          "target_condition": fix.params.get("target_condition", ""), "keyword_type": "value_alias"}
                row = config_db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.keyword == keyword).first()
                if row is None:
                    row = SchemaSemanticMapping(keyword=keyword, is_active=True, source=LEARNED, status=PROPOSED,
                                                confidence=fix.confidence, **values)
                    config_db.add(row)
                    config_db.commit()
                    audit.log_change(action="INSERT", table_name="schema_semantic_mapping", record_id=row.id,
                                     new_value={**fix.params, "status": PROPOSED, "confidence": fix.confidence},
                                     source="auto_analyzer")
                elif may_replace(LEARNED, row.source, row.status):
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.confidence = fix.confidence
                    config_db.commit()
                elif propose(config_db.connection(), "schema_semantic_mapping", {"keyword": keyword}, values, LEARNED,
                             confidence=fix.confidence, reason=fix.reason):
                    config_db.commit()
                logger.info("[AutoAnalyze] Proposed %s: %s", fix.fix_type, fix.params)
            except Exception as e:
                config_db.rollback()
                logger.warning("[AutoAnalyze] Failed to propose %s: %s", fix.fix_type, e)

    async def _job_export_cleanup(self):
        """Delete expired report exports (records + files + orphan files)."""
        db = self._db_factory()
        try:
            from app.services.report_service import cleanup_expired
            removed = cleanup_expired(db)
            if removed:
                logger.info("[ExportCleanup] Removed %s expired exports/files", removed)
        finally:
            db.close()

    async def _job_result_retention(self):
        """Purge stored result rows past result_retention_days (question / SQL / answer stay)."""
        db = self._db_factory()
        try:
            from app.services.retention import purge_results
            done = await asyncio.to_thread(purge_results, db)
            if any(done.values()):
                logger.info("[ResultRetention] purged %s", done)
        finally:
            db.close()

    async def _job_config_gc(self):
        """Scan for unused/conflicting config entries."""
        app_db = self._db_factory()
        config_db = self._config_db_factory()
        try:
            from app.services.config_gc import ConfigGC
            gc = ConfigGC(config_db=config_db, app_db=app_db)
            issues = gc.run_full_scan()
            if issues:
                logger.info("[ConfigGC] Found %s issues", len(issues))
                for issue in issues[:10]:
                    logger.info("  [%s] %s: %s", issue.severity, issue.issue_type, issue.description)
        finally:
            config_db.close()
            app_db.close()

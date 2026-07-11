from app.celery import celery_app
from app.core.logging import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.report_worker.generate_report")
def generate_report(export_id: str):
    """Celery task: run one report export (connects to DB directly — no MCP needed)."""
    logger.info(f"Processing report export task {export_id}")
    from app.services.report_service import run_export
    run_export(export_id)
    return True

from celery import Celery
from app.config import settings

# Create Celery application
celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL if hasattr(settings, "REDIS_URL") and settings.REDIS_URL else "redis://localhost:6379/0",
    backend=settings.REDIS_URL if hasattr(settings, "REDIS_URL") and settings.REDIS_URL else "redis://localhost:6379/0"
)

celery_app.conf.task_routes = {
    "app.workers.report_worker.*": "reports-queue",
    "app.workers.email_worker.*": "email-queue",
}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Bangkok",
    enable_utc=True,
    # Ensure imports happen at startup
    include=["app.workers.email_worker"]
)

# Auto-discover tasks in packages
celery_app.autodiscover_tasks(['app.workers'])

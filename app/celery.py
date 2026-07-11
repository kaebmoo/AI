from celery import Celery
from app.config import settings

# Create Celery application
celery_app = Celery(
    "worker",
    broker=settings.get_redis_url(),
    backend=settings.get_redis_url()
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
    include=["app.workers.email_worker", "app.workers.report_worker"],
    broker_connection_retry_on_startup=True
)

# Auto-discover tasks in packages
celery_app.autodiscover_tasks(['app.workers'])

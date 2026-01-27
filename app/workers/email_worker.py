import asyncio
from app.celery import celery_app
from app.services.email_service import EmailService
from app.core.logging import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="app.workers.email_worker.send_otp_email")
def send_otp_email(to_email: str, otp_code: str, platform: str, expiry_minutes: int):
    """
    Celery task to send OTP email via EmailService.
    Uses asyncio.run() to execute the async email service method in a synchronous worker.
    """
    logger.info(f"Processing OTP email task for {to_email}")
    
    # Initialize service (this creates the Jinja2 environment)
    service = EmailService()
    
    try:
        # Run the async send method synchronously
        asyncio.run(service.send_otp_email(
            to_email=to_email, 
            otp_code=otp_code, 
            platform=platform, 
            expiry_minutes=expiry_minutes
        ))
        logger.info(f"Successfully processed OTP email task for {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to process OTP email task: {str(e)}")
        # Raise exception to allow Celery to handle retries if configured
        raise e

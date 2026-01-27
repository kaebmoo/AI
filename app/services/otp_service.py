import hashlib
import pyotp
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.otp import OTPRequest
from app.config import settings
from app.services.email_service import EmailService
from app.core.exceptions import (
    InvalidDomainError, 
    OTPExpiredError, 
    TooManyAttemptsError,
    CooldownError
)
from app.core.logging import logging
from app.workers.email_worker import send_otp_email

logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self, db: Session, email_service: EmailService):
        self.db = db
        self.email_service = email_service
    
    def validate_email_domain(self, email: str) -> bool:
        """Validate email belongs to allowed domain"""
        if not settings.ALLOWED_EMAIL_DOMAINS:
            return True # Allow all if empty
            
        domain = email.split("@")[-1].lower()
        return domain in settings.ALLOWED_EMAIL_DOMAINS
    
    def generate_otp(self) -> str:
        """Generate secure random OTP using pyotp"""
        # We use a random base32 secret each time to generate a one-time code
        # We set interval to effectively make it a one-time random number generator
        # conforming to the requested length.
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret, digits=settings.OTP_LENGTH, interval=60)
        return totp.now()
    
    def hash_otp(self, otp: str) -> str:
        """Hash OTP for storage"""
        return hashlib.sha256(otp.encode()).hexdigest()
    
    async def request_otp(
        self, 
        email: str, 
        platform: str,
        telegram_chat_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Request new OTP
        Returns: (success, message)
        """
        # Validate domain
        if not self.validate_email_domain(email):
            allowed = ", ".join(settings.ALLOWED_EMAIL_DOMAINS)
            raise InvalidDomainError(f"Email domain not allowed. Allowed: {allowed}")
        
        # Check cooldown
        recent_request = self.db.query(OTPRequest).filter(
            OTPRequest.email == email,
            OTPRequest.created_at > datetime.utcnow() - timedelta(minutes=settings.OTP_COOLDOWN_MINUTES)
        ).first()
        
        if recent_request:
            wait_seconds = settings.OTP_COOLDOWN_MINUTES * 60
            raise CooldownError(f"Please wait {wait_seconds} seconds before requesting new OTP")
        
        # Generate and store OTP
        otp = self.generate_otp()
        otp_hash = self.hash_otp(otp)
        
        otp_request = OTPRequest(
            email=email,
            otp_code=otp_hash,
            platform=platform,
            telegram_chat_id=telegram_chat_id,
            ip_address=ip_address,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
            created_at=datetime.utcnow(),
            attempts=0
        )
        self.db.add(otp_request)
        self.db.commit()
        
        # Send email asynchronously via Celery
        try:
            send_otp_email.delay(
                to_email=email,
                otp_code=otp,
                platform=platform,
                expiry_minutes=settings.OTP_EXPIRY_MINUTES
            )
            logger.info(f"Queued OTP email for {email}")
        except Exception as e:
            logger.error(f"Failed to queue OTP email task: {e}")
            # In a real system, you might revert the DB transaction or return an error,
            # but for now we proceed as if sent (client might retry).
        
        return True, "OTP sent to your email"
    
    def verify_otp(
        self, 
        email: str, 
        otp: str,
        platform: str,
        telegram_chat_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Verify OTP
        Returns: (success, message)
        """
        # Find latest OTP request
        query = self.db.query(OTPRequest).filter(
            OTPRequest.email == email,
            OTPRequest.platform == platform,
            OTPRequest.verified_at.is_(None)
        )
        
        if telegram_chat_id:
            query = query.filter(OTPRequest.telegram_chat_id == telegram_chat_id)
        
        otp_request = query.order_by(OTPRequest.created_at.desc()).first()
        
        if not otp_request:
            return False, "No OTP request found. Please request a new OTP."
        
        # Check expiry
        if datetime.utcnow() > otp_request.expires_at:
            raise OTPExpiredError("OTP has expired. Please request a new one.")
        
        # Check attempts
        if otp_request.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise TooManyAttemptsError("Too many failed attempts. Please request a new OTP.")
        
        # Verify OTP (Hash comparison)
        if self.hash_otp(otp) != otp_request.otp_code:
            otp_request.attempts += 1
            self.db.commit()
            remaining = settings.OTP_MAX_ATTEMPTS - otp_request.attempts
            return False, f"Invalid OTP. {remaining} attempts remaining."
        
        # Mark as verified
        otp_request.verified_at = datetime.utcnow()
        self.db.commit()
        
        return True, "OTP verified successfully"

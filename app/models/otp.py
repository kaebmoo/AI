from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from app.db.base import Base

class OTPRequest(Base):
    """
    OTPRequest model stores authentication attempts and verification status.
    """
    __tablename__ = "otp_requests"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    otp_code = Column(String) # Hashed
    platform = Column(String)
    telegram_chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime)
    expires_at = Column(DateTime)
    verified_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    ip_address = Column(String, nullable=True)

"""
NT AI Assistant -- Telegram Authentication
============================================
Handles user registration via email OTP and session lookup
for the Telegram bot interface.
"""

import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.session import UserSession
from app.services.otp_service import OTPService
from app.services.email_service import EmailService
from app.core.time_utils import utcnow
from app.core.exceptions import (
    InvalidDomainError,
    OTPExpiredError,
    TooManyAttemptsError,
    CooldownError,
)

logger = logging.getLogger(__name__)


class TelegramAuth:
    """Authentication service for Telegram bot users.

    Links Telegram ``chat_id`` to a ``User`` record via OTP email verification.
    The ``telegram_chat_id`` is stored on ``UserSession`` (platform='telegram').
    """

    # ── User lookup ───────────────────────────────────────────────────────

    def get_user_by_chat_id(self, chat_id: int, db: Session) -> Optional[User]:
        """Find the registered User linked to a Telegram chat_id.

        Looks up the active ``UserSession`` with ``platform='telegram'`` and
        the given *chat_id*, then returns the associated ``User``.

        Returns ``None`` if no session or user exists.
        """
        session = (
            db.query(UserSession)
            .filter(
                UserSession.telegram_chat_id == chat_id,
                UserSession.platform == "telegram",
            )
            .order_by(UserSession.created_at.desc())
            .first()
        )
        if not session:
            return None
        return (
            db.query(User)
            .filter(User.id == session.user_id, User.is_active == True)
            .first()
        )

    # ── Registration flow ─────────────────────────────────────────────────

    def start_registration(self, chat_id: int, email: str, db: Session) -> Dict:
        """Begin the registration flow: validate email, send OTP.

        Args:
            chat_id: Telegram chat id.
            email: Corporate email address.
            db: SQLAlchemy session.

        Returns:
            ``{"success": True/False, "message": "..."}``
        """
        email = email.strip().lower()

        # Check if already registered
        existing = self.get_user_by_chat_id(chat_id, db)
        if existing:
            return {
                "success": False,
                "message": f"Telegram นี้ลงทะเบียนแล้วกับ {existing.email}",
            }

        # Find user record by email
        user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user:
            return {
                "success": False,
                "message": "ไม่พบอีเมลนี้ในระบบ กรุณาติดต่อผู้ดูแลระบบ",
            }

        # Send OTP via email
        email_service = EmailService()
        otp_service = OTPService(db=db, email_service=email_service)

        try:
            success, message = otp_service.request_otp(
                email=email,
                platform="telegram",
                telegram_chat_id=chat_id,
            )
            if success:
                return {
                    "success": True,
                    "message": f"ส่ง OTP ไปที่ {email} แล้ว กรุณาพิมพ์รหัส OTP ที่ได้รับ",
                }
            return {"success": False, "message": message}

        except InvalidDomainError:
            return {
                "success": False,
                "message": "โดเมนอีเมลไม่ได้รับอนุญาต กรุณาใช้อีเมลองค์กร",
            }
        except CooldownError:
            return {
                "success": False,
                "message": "กรุณารอสักครู่ก่อนขอ OTP ใหม่",
            }
        except Exception as e:
            logger.error(f"Registration error for chat_id={chat_id}: {e}")
            return {
                "success": False,
                "message": "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง",
            }

    # ── OTP verification ──────────────────────────────────────────────────

    def verify_otp(self, chat_id: int, otp: str, db: Session) -> Dict:
        """Verify an OTP and create a Telegram session.

        On success, creates a ``UserSession`` with ``platform='telegram'`` and
        links the *chat_id* to the user.

        Args:
            chat_id: Telegram chat id.
            otp: OTP string entered by the user.
            db: SQLAlchemy session.

        Returns:
            ``{"success": True/False, "message": "...", "user": User|None}``
        """
        from app.models.otp import OTPRequest
        from datetime import datetime

        # Find the latest unverified OTP request for this chat_id
        otp_request = (
            db.query(OTPRequest)
            .filter(
                OTPRequest.telegram_chat_id == chat_id,
                OTPRequest.platform == "telegram",
                OTPRequest.verified_at.is_(None),
            )
            .order_by(OTPRequest.created_at.desc())
            .first()
        )

        if not otp_request:
            return {
                "success": False,
                "message": "ไม่พบคำขอ OTP กรุณาเริ่มลงทะเบียนใหม่ด้วย /start",
                "user": None,
            }

        email = otp_request.email
        email_service = EmailService()
        otp_service = OTPService(db=db, email_service=email_service)

        try:
            success, message = otp_service.verify_otp(
                email=email,
                otp=otp,
                platform="telegram",
                telegram_chat_id=chat_id,
            )
        except OTPExpiredError:
            return {
                "success": False,
                "message": "OTP หมดอายุแล้ว กรุณาขอ OTP ใหม่ด้วย /start",
                "user": None,
            }
        except TooManyAttemptsError:
            return {
                "success": False,
                "message": "ลองผิดหลายครั้งเกินไป กรุณาขอ OTP ใหม่ด้วย /start",
                "user": None,
            }

        if not success:
            return {"success": False, "message": message, "user": None}

        # OTP verified -- link chat_id to user via session
        user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user:
            return {
                "success": False,
                "message": "ไม่พบบัญชีผู้ใช้ กรุณาติดต่อผู้ดูแลระบบ",
                "user": None,
            }

        # Deactivate old Telegram sessions for this chat_id
        old_sessions = (
            db.query(UserSession)
            .filter(
                UserSession.telegram_chat_id == chat_id,
                UserSession.platform == "telegram",
            )
            .all()
        )
        for old in old_sessions:
            db.delete(old)

        # Create new session
        import secrets

        new_session = UserSession(
            user_id=user.id,
            session_token=secrets.token_hex(32),
            platform="telegram",
            telegram_chat_id=chat_id,
            created_at=utcnow(),
            last_activity=utcnow(),
        )
        db.add(new_session)
        db.commit()

        logger.info(f"Telegram user linked: chat_id={chat_id} -> user_id={user.id} ({user.email})")
        return {
            "success": True,
            "message": f"ลงทะเบียนสำเร็จ! สวัสดี {user.display_name or user.email}",
            "user": user,
        }

    # ── Admin check ───────────────────────────────────────────────────────

    def is_admin(self, chat_id: int, db: Session) -> bool:
        """Check whether the Telegram chat_id belongs to an admin user."""
        user = self.get_user_by_chat_id(chat_id, db)
        if not user:
            return False
        return user.role == "admin"

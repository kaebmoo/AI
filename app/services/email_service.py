import aiosmtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from typing import Optional

from app.config import settings
from app.core.logging import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        
        # Ensure template directory exists or handle path
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates/email")
        self.template_env = Environment(
            loader=FileSystemLoader(template_dir)
        )
    
    async def send_otp_email(
        self, 
        to_email: str, 
        otp_code: str, 
        platform: str,
        expiry_minutes: int
    ):
        """Send OTP verification email"""
        try:
            template = self.template_env.get_template("otp_email.html")
            
            html_content = template.render(
                otp_code=otp_code,
                platform=platform,
                expiry_minutes=expiry_minutes,
                year=datetime.now().year
            )
            
            message = MIMEMultipart("alternative")
            message["Subject"] = f"[NT Revenue Assistant] Your verification code: {otp_code}"
            message["From"] = self.from_email
            message["To"] = to_email
            
            message.attach(MIMEText(html_content, "html"))
            
            if settings.SMTP_HOST == "mock":
                 logger.info(f"MOCK EMAIL to {to_email}: OTP={otp_code}")
                 return

            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                use_tls=True if self.smtp_port == 465 else False,
                start_tls=True if self.smtp_port == 587 else False
            )
            logger.info(f"OTP email sent to {to_email}")
            
        except Exception as e:
            logger.error(f"Failed to send OTP email: {str(e)}")
            # In production, might want to raise or handle differently
            raise e

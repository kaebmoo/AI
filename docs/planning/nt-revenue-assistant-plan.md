# AI Assistant - Production Implementation Plan

## Executive Summary

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้และยอดขายขององค์กร ผ่าน Web Application และ Telegram Bot โดยใช้ Claude AI เป็นตัวประมวลผลคำถามและสร้าง SQL Query

**เป้าหมายหลัก:**
- ให้บริการสอบถามข้อมูลรายได้/ยอดขายผ่าน Web App และ Telegram Bot
- ระบบ Authentication ที่ปลอดภัยด้วย Email OTP (จำกัด Domain)
- ระบบควบคุมและ Audit Log ที่ครบถ้วน
- สามารถสร้างรายงาน, กราฟ, Dashboard และ Export ได้
- รองรับการบันทึก Query Templates สำหรับใช้งานซ้ำ

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USERS                                           │
│                    ┌──────────┐    ┌──────────────┐                         │
│                    │ Web App  │    │ Telegram Bot │                         │
│                    └────┬─────┘    └──────┬───────┘                         │
└─────────────────────────┼─────────────────┼─────────────────────────────────┘
                          │                 │
                          ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NGINX (Reverse Proxy + SSL)                          │
│                              Load Balancer                                   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │   FastAPI       │  │   Telegram      │  │   Background    │              │
│  │   Web Server    │  │   Bot Service   │  │   Workers       │              │
│  │   (Gunicorn)    │  │   (polling)     │  │   (Celery)      │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
└───────────┼────────────────────┼────────────────────┼────────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Auth Service │  │Claude Service│  │Report Service│  │ Cache Service│     │
│  │ (OTP/Email)  │  │ (AI Query)   │  │ (Export/PDF) │  │   (Redis)    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   MSSQL      │  │  PostgreSQL  │  │    Redis     │  │ File Storage │     │
│  │  (Business Data)   │  │  (App Data)  │  │   (Cache)    │  │   (MinIO)    │     │
│  │ 10.200.1.92  │  │              │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                    │
│  ┌──────────────┐  ┌──────────────┐                                         │
│  │ Claude API   │  │ SMTP Server  │                                         │
│  │ (Anthropic)  │  │ (Email OTP)  │                                         │
│  └──────────────┘  └──────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Database Schema (PostgreSQL - Application Data)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION DATABASE SCHEMA                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐     ┌──────────────────────────┐
│         users            │     │      user_sessions       │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │────▶│ id (PK)                  │
│ email                    │     │ user_id (FK)             │
│ display_name             │     │ session_token            │
│ department               │     │ platform (web/telegram)  │
│ is_active                │     │ telegram_chat_id         │
│ role (user/admin/viewer) │     │ created_at               │
│ allowed_bu_access        │     │ expires_at               │
│ created_at               │     │ last_activity            │
│ updated_at               │     │ ip_address               │
└──────────────────────────┘     │ user_agent               │
            │                    └──────────────────────────┘
            │
            ▼
┌──────────────────────────┐     ┌──────────────────────────┐
│      otp_requests        │     │      chat_history        │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ email                    │     │ user_id (FK)             │
│ otp_code (hashed)        │     │ session_id (FK)          │
│ platform                 │     │ question                 │
│ telegram_chat_id         │     │ generated_sql            │
│ created_at               │     │ sql_result_summary       │
│ expires_at               │     │ ai_response              │
│ verified_at              │     │ tokens_used              │
│ attempts                 │     │ execution_time_ms        │
│ ip_address               │     │ created_at               │
└──────────────────────────┘     │ is_bookmarked            │
                                 │ feedback_rating          │
                                 └──────────────────────────┘
            
┌──────────────────────────┐     ┌──────────────────────────┐
│    saved_templates       │     │     scheduled_reports    │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ user_id (FK)             │     │ user_id (FK)             │
│ name                     │     │ template_id (FK)         │
│ description              │     │ schedule_type            │
│ question_template        │     │ schedule_config (JSON)   │
│ category                 │     │ last_run_at              │
│ is_public                │     │ next_run_at              │
│ parameters (JSON)        │     │ is_active                │
│ created_at               │     │ delivery_method          │
│ usage_count              │     │ delivery_config (JSON)   │
└──────────────────────────┘     └──────────────────────────┘

┌──────────────────────────┐     ┌──────────────────────────┐
│     generated_reports    │     │       audit_logs         │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ user_id (FK)             │     │ user_id (FK)             │
│ chat_id (FK)             │     │ action_type              │
│ report_type              │     │ resource_type            │
│ file_path                │     │ resource_id              │
│ file_size                │     │ details (JSON)           │
│ format (xlsx/pdf/csv)    │     │ ip_address               │
│ created_at               │     │ user_agent               │
│ expires_at               │     │ created_at               │
│ download_count           │     │ platform                 │
└──────────────────────────┘     └──────────────────────────┘

┌──────────────────────────┐     ┌──────────────────────────┐
│     dashboard_configs    │     │      api_usage_logs      │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ user_id (FK)             │     │ user_id (FK)             │
│ name                     │     │ endpoint                 │
│ layout_config (JSON)     │     │ method                   │
│ widgets (JSON)           │     │ request_tokens           │
│ refresh_interval         │     │ response_tokens          │
│ is_default               │     │ cost_usd                 │
│ created_at               │     │ response_time_ms         │
│ updated_at               │     │ status_code              │
└──────────────────────────┘     │ created_at               │
                                 └──────────────────────────┘
```

---

## 2. Project Phases & Timeline

### Phase Overview

| Phase | ระยะเวลา | รายละเอียด |
|-------|----------|------------|
| Phase 1 | 2 สัปดาห์ | Infrastructure & Core Setup |
| Phase 2 | 3 สัปดาห์ | Authentication & Security |
| Phase 3 | 3 สัปดาห์ | Core Features (Chat, Query) |
| Phase 4 | 2 สัปดาห์ | Reports & Export |
| Phase 5 | 2 สัปดาห์ | Dashboard & Visualization |
| Phase 6 | 2 สัปดาห์ | Templates & Scheduling |
| Phase 7 | 2 สัปดาห์ | Testing & Security Audit |
| Phase 8 | 1 สัปดาห์ | Deployment & Go-Live |
| **Total** | **17 สัปดาห์** | (~4 เดือน) |

---

## Phase 1: Infrastructure & Core Setup (2 สัปดาห์)

### 1.1 Development Environment Setup

#### Week 1: Infrastructure Preparation

**Tasks:**
- [ ] Setup Git repository (GitLab/GitHub)
- [ ] Create Docker development environment
- [ ] Setup PostgreSQL database server
- [ ] Setup Redis server
- [ ] Setup MinIO (S3-compatible) for file storage
- [ ] Configure SMTP server access for OTP emails
- [ ] Obtain Claude API key และกำหนด budget

**Docker Compose Configuration:**
```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/nt_assistant
      - REDIS_URL=redis://redis:6379/0
      - MSSQL_HOST=10.200.1.92
    depends_on:
      - postgres
      - redis
    volumes:
      - ./app:/app

  telegram-bot:
    build: .
    command: python -m app.telegram_bot
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/nt_assistant
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  celery-worker:
    build: .
    command: celery -A app.celery worker -l info
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/nt_assistant
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  celery-beat:
    build: .
    command: celery -A app.celery beat -l info
    depends_on:
      - redis

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=nt_assistant
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=nt_assistant
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  minio:
    image: minio/minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

#### Week 2: Project Structure & Base Code

**Project Structure:**
```
nt-revenue-assistant/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Configuration management
│   ├── celery.py                  # Celery configuration
│   │
│   ├── api/                       # API endpoints
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # Authentication endpoints
│   │   │   ├── chat.py            # Chat/Query endpoints
│   │   │   ├── reports.py         # Report generation
│   │   │   ├── templates.py       # Saved templates
│   │   │   ├── dashboard.py       # Dashboard endpoints
│   │   │   ├── history.py         # Chat history
│   │   │   └── admin.py           # Admin endpoints
│   │   └── deps.py                # Dependencies
│   │
│   ├── core/                      # Core utilities
│   │   ├── __init__.py
│   │   ├── security.py            # Security utilities
│   │   ├── rate_limiter.py        # Rate limiting
│   │   ├── exceptions.py          # Custom exceptions
│   │   └── logging.py             # Logging configuration
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py        # Authentication logic
│   │   ├── otp_service.py         # OTP generation/verification
│   │   ├── email_service.py       # Email sending
│   │   ├── claude_service.py      # Claude AI integration
│   │   ├── database_service.py    # MSSQL query execution
│   │   ├── report_service.py      # Report generation
│   │   ├── cache_service.py       # Caching logic
│   │   ├── audit_service.py       # Audit logging
│   │   └── cost_service.py        # Cost tracking
│   │
│   ├── models/                    # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── session.py
│   │   ├── chat.py
│   │   ├── template.py
│   │   ├── report.py
│   │   └── audit.py
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── report.py
│   │   └── template.py
│   │
│   ├── db/                        # Database
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── migrations/
│   │
│   ├── telegram/                  # Telegram bot
│   │   ├── __init__.py
│   │   ├── bot.py
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── reports.py
│   │   │   └── templates.py
│   │   └── keyboards.py
│   │
│   └── workers/                   # Background tasks
│       ├── __init__.py
│       ├── report_worker.py
│       ├── scheduled_reports.py
│       └── cleanup_worker.py
│
├── frontend/                      # Web frontend (React/Vue)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── stores/
│   └── package.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   ├── init_db.py
│   ├── create_admin.py
│   └── backup.sh
│
├── docs/
│   ├── api.md
│   ├── deployment.md
│   └── user_guide.md
│
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

**Deliverables Phase 1:**
- [ ] Git repository พร้อม CI/CD pipeline
- [ ] Docker environment ทำงานได้
- [ ] Database schema migrations
- [ ] Basic project structure
- [ ] Configuration management

---

## Phase 2: Authentication & Security (3 สัปดาห์)

### 2.1 Email OTP Authentication System

#### Week 3-4: Core Authentication

**Allowed Domain Configuration:**
```python
# app/config.py
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Allowed email domains
    ALLOWED_EMAIL_DOMAINS: List[str] = ["example.com", "example.com"]
    
    # OTP Settings
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 3
    OTP_COOLDOWN_MINUTES: int = 1
    
    # Session Settings
    SESSION_EXPIRY_HOURS: int = 24
    SESSION_REFRESH_THRESHOLD_HOURS: int = 1
    
    # Rate Limiting
    LOGIN_RATE_LIMIT: str = "5/minute"
    API_RATE_LIMIT: str = "60/minute"
    CHAT_RATE_LIMIT: str = "20/minute"
```

**OTP Service Implementation:**
```python
# app/services/otp_service.py
import secrets
import hashlib
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

class OTPService:
    def __init__(self, db: Session, email_service: EmailService):
        self.db = db
        self.email_service = email_service
    
    def validate_email_domain(self, email: str) -> bool:
        """Validate email belongs to allowed domain"""
        domain = email.split("@")[-1].lower()
        return domain in settings.ALLOWED_EMAIL_DOMAINS
    
    def generate_otp(self) -> str:
        """Generate secure random OTP"""
        return "".join([str(secrets.randbelow(10)) for _ in range(settings.OTP_LENGTH)])
    
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
            attempts=0
        )
        self.db.add(otp_request)
        self.db.commit()
        
        # Send email
        await self.email_service.send_otp_email(
            to_email=email,
            otp_code=otp,
            platform=platform,
            expiry_minutes=settings.OTP_EXPIRY_MINUTES
        )
        
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
        
        # Verify OTP
        if self.hash_otp(otp) != otp_request.otp_code:
            otp_request.attempts += 1
            self.db.commit()
            remaining = settings.OTP_MAX_ATTEMPTS - otp_request.attempts
            return False, f"Invalid OTP. {remaining} attempts remaining."
        
        # Mark as verified
        otp_request.verified_at = datetime.utcnow()
        self.db.commit()
        
        return True, "OTP verified successfully"
```

**Email Service:**
```python
# app/services/email_service.py
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader

from app.config import settings

class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        
        self.template_env = Environment(
            loader=FileSystemLoader("app/templates/email")
        )
    
    async def send_otp_email(
        self, 
        to_email: str, 
        otp_code: str, 
        platform: str,
        expiry_minutes: int
    ):
        """Send OTP verification email"""
        template = self.template_env.get_template("otp_email.html")
        
        html_content = template.render(
            otp_code=otp_code,
            platform=platform,
            expiry_minutes=expiry_minutes,
            year=datetime.now().year
        )
        
        message = MIMEMultipart("alternative")
        message["Subject"] = f"[AI Assistant] Your verification code: {otp_code}"
        message["From"] = self.from_email
        message["To"] = to_email
        
        message.attach(MIMEText(html_content, "html"))
        
        await aiosmtplib.send(
            message,
            hostname=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            use_tls=True
        )
```

#### Week 5: Session Management & Security

**Session Service:**
```python
# app/services/auth_service.py
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.session import UserSession
from app.config import settings
from app.core.security import create_access_token

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_user(self, email: str) -> User:
        """Get existing user or create new one"""
        user = self.db.query(User).filter(User.email == email).first()
        
        if not user:
            # Extract name from email
            name_part = email.split("@")[0]
            display_name = name_part.replace(".", " ").title()
            
            user = User(
                email=email,
                display_name=display_name,
                is_active=True,
                role="user"
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        
        return user
    
    def create_session(
        self,
        user: User,
        platform: str,
        telegram_chat_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserSession:
        """Create new user session"""
        session_token = secrets.token_urlsafe(32)
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            platform=platform,
            telegram_chat_id=telegram_chat_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
            last_activity=datetime.utcnow()
        )
        self.db.add(session)
        self.db.commit()
        
        return session
    
    def validate_session(self, session_token: str) -> Optional[UserSession]:
        """Validate and refresh session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token,
            UserSession.expires_at > datetime.utcnow()
        ).first()
        
        if session:
            # Update last activity
            session.last_activity = datetime.utcnow()
            
            # Refresh token if close to expiry
            hours_until_expiry = (session.expires_at - datetime.utcnow()).total_seconds() / 3600
            if hours_until_expiry < settings.SESSION_REFRESH_THRESHOLD_HOURS:
                session.expires_at = datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
            
            self.db.commit()
        
        return session
    
    def validate_telegram_session(self, chat_id: int) -> Optional[UserSession]:
        """Validate Telegram session by chat_id"""
        return self.db.query(UserSession).filter(
            UserSession.telegram_chat_id == chat_id,
            UserSession.platform == "telegram",
            UserSession.expires_at > datetime.utcnow()
        ).first()
    
    def logout(self, session_token: str):
        """Invalidate session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()
        
        if session:
            session.expires_at = datetime.utcnow()
            self.db.commit()
```

**Rate Limiting Implementation:**
```python
# app/core/rate_limiter.py
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
import redis

from app.config import settings

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL
)

class RateLimiter:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)
    
    def check_rate_limit(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check and update rate limit
        Returns: (allowed, remaining)
        """
        current = self.redis.get(key)
        
        if current is None:
            self.redis.setex(key, window_seconds, 1)
            return True, limit - 1
        
        count = int(current)
        if count >= limit:
            ttl = self.redis.ttl(key)
            return False, 0
        
        self.redis.incr(key)
        return True, limit - count - 1
    
    def get_user_rate_limit_key(self, user_id: int, action: str) -> str:
        """Generate rate limit key for user"""
        return f"rate_limit:{action}:user:{user_id}"
    
    def get_ip_rate_limit_key(self, ip: str, action: str) -> str:
        """Generate rate limit key for IP"""
        return f"rate_limit:{action}:ip:{ip}"


# Rate limit configurations
RATE_LIMITS = {
    "login": {"limit": 5, "window": 60},           # 5 attempts per minute
    "otp_request": {"limit": 3, "window": 300},    # 3 requests per 5 minutes
    "chat": {"limit": 30, "window": 60},           # 30 queries per minute
    "report": {"limit": 10, "window": 300},        # 10 reports per 5 minutes
    "export": {"limit": 5, "window": 300},         # 5 exports per 5 minutes
}
```

**Deliverables Phase 2:**
- [ ] OTP generation and verification
- [ ] Email sending service
- [ ] Domain validation
- [ ] Session management
- [ ] Rate limiting
- [ ] Security middleware

---

## Phase 3: Core Features - Chat & Query (3 สัปดาห์)

### 3.1 Claude AI Integration with Tool Use

#### Week 6-7: Claude Service Implementation

**Claude Service with Tool Use:**
```python
# app/services/claude_service.py
import anthropic
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.config import settings
from app.services.database_service import MSSQLService
from app.services.cache_service import CacheService
from app.services.cost_service import CostService
from app.services.audit_service import AuditService

class ClaudeRevenueAssistant:
    def __init__(
        self,
        db_service: MSSQLService,
        cache_service: CacheService,
        cost_service: CostService,
        audit_service: AuditService
    ):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.db_service = db_service
        self.cache_service = cache_service
        self.cost_service = cost_service
        self.audit_service = audit_service
        
        self.schema_info = self._load_schema_info()
        self.tools = self._define_tools()
        self.system_prompt = self._build_system_prompt()
    
    def _load_schema_info(self) -> str:
        """Load and cache database schema"""
        cached = self.cache_service.get("db_schema_info")
        if cached:
            return cached
        
        schema = self.db_service.get_schema_info()
        self.cache_service.set("db_schema_info", schema, ttl=3600)  # 1 hour cache
        return schema
    
    def _define_tools(self) -> List[Dict]:
        """Define available tools for Claude"""
        return [
            {
                "name": "execute_sql",
                "description": """Execute a read-only SQL query against the revenue database.
                Use this to retrieve revenue data from EXPORT_NT_REVENUE_SUB_PRODUCT 
                or sales data from EXPORT_SPv7_PM.
                Only SELECT and WITH statements are allowed.""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SQL SELECT query to execute"
                        },
                        "purpose": {
                            "type": "string",
                            "description": "Brief description of what this query retrieves"
                        }
                    },
                    "required": ["query", "purpose"]
                }
            },
            {
                "name": "get_available_values",
                "description": """Get distinct values for a specific column. 
                Useful for understanding available filters like BU names, 
                product names, time periods, etc.""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "enum": ["EXPORT_NT_REVENUE_SUB_PRODUCT", "EXPORT_SPv7_PM"]
                        },
                        "column_name": {
                            "type": "string",
                            "description": "Column to get distinct values from"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of values to return",
                            "default": 50
                        }
                    },
                    "required": ["table_name", "column_name"]
                }
            }
        ]
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with schema information"""
        return f"""คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูลรายได้และยอดขายของ องค์กร

## Database Schema
{self.schema_info}

## หน้าที่หลัก
1. รับคำถามเกี่ยวกับรายได้/ยอดขายจากผู้ใช้
2. สร้าง SQL query ที่ถูกต้องและปลอดภัย
3. ใช้ tool execute_sql เพื่อดึงข้อมูล
4. วิเคราะห์และสรุปผลเป็นภาษาไทยที่เข้าใจง่าย

## กฎสำคัญ
- ใช้เฉพาะ SELECT statements (ห้าม INSERT, UPDATE, DELETE)
- ระวัง column names ให้ตรงกับ schema
- TIME_KEY format: YYYYMM (เช่น 202412 = ธันวาคม 2567)
- YEAR format: YYYY (2024 = 2567 - 543)
- ตอบเป็นภาษาไทย
- แสดงตัวเลขในรูปแบบที่อ่านง่าย (เช่น 1,234,567.89)
- ถ้าข้อมูลมีหลายแถว ให้สรุปเป็นตารางหรือ bullet points

## ข้อมูลเพิ่มเติม
- EXPORT_NT_REVENUE_SUB_PRODUCT: ข้อมูลรายได้แยกตาม BU, Service Group, Product
- EXPORT_SPv7_PM: ข้อมูลยอดขายแยกตามหน่วยงาน, ผลิตภัณฑ์, กลุ่มลูกค้า
- BU หลัก: Consumer, Enterprise, Wholesale, Government
- วันที่ปัจจุบัน: {datetime.now().strftime('%Y-%m-%d')}
"""

    async def chat(
        self,
        user_id: int,
        message: str,
        session_id: int,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Process user message and return response
        
        Returns:
            {
                "response": str,
                "sql_queries": List[str],
                "tokens_used": {"input": int, "output": int},
                "cost_usd": float,
                "execution_time_ms": int
            }
        """
        start_time = datetime.now()
        sql_queries = []
        
        # Build messages
        messages = conversation_history or []
        messages.append({"role": "user", "content": message})
        
        # Check cache for similar query
        cache_key = self.cache_service.generate_query_cache_key(message)
        cached_response = self.cache_service.get(cache_key)
        if cached_response:
            self.audit_service.log(
                user_id=user_id,
                action="chat_cache_hit",
                details={"message": message}
            )
            return cached_response
        
        # Initial Claude request
        response = self.client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=self.system_prompt,
            tools=self.tools,
            messages=messages
        )
        
        total_input_tokens = response.usage.input_tokens
        total_output_tokens = response.usage.output_tokens
        
        # Handle tool use loop
        while response.stop_reason == "tool_use":
            tool_results = []
            
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    
                    # Execute tool
                    if tool_name == "execute_sql":
                        try:
                            # Validate and execute query
                            query = tool_input["query"]
                            sql_queries.append(query)
                            
                            result = self.db_service.execute_query(query)
                            tool_result = json.dumps(
                                result[:100],  # Limit results
                                ensure_ascii=False, 
                                default=str
                            )
                            
                            if len(result) > 100:
                                tool_result += f"\n... และอีก {len(result) - 100} แถว"
                                
                        except Exception as e:
                            tool_result = f"SQL Error: {str(e)}"
                            
                    elif tool_name == "get_available_values":
                        try:
                            result = self.db_service.get_distinct_values(
                                tool_input["table_name"],
                                tool_input["column_name"],
                                tool_input.get("limit", 50)
                            )
                            tool_result = json.dumps(result, ensure_ascii=False)
                        except Exception as e:
                            tool_result = f"Error: {str(e)}"
                    else:
                        tool_result = f"Unknown tool: {tool_name}"
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result
                    })
            
            # Send tool results back to Claude
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            
            response = self.client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages
            )
            
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
        
        # Extract final response
        final_response = "".join(
            block.text for block in response.content 
            if hasattr(block, "text")
        )
        
        # Calculate cost
        cost_usd = self.cost_service.calculate_cost(
            total_input_tokens, 
            total_output_tokens
        )
        
        execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        result = {
            "response": final_response,
            "sql_queries": sql_queries,
            "tokens_used": {
                "input": total_input_tokens,
                "output": total_output_tokens
            },
            "cost_usd": cost_usd,
            "execution_time_ms": execution_time_ms
        }
        
        # Cache response (if not too expensive)
        if cost_usd < 0.01:  # Cache only cheap queries
            self.cache_service.set(cache_key, result, ttl=300)  # 5 min cache
        
        # Log usage
        self.cost_service.log_usage(
            user_id=user_id,
            session_id=session_id,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            cost_usd=cost_usd
        )
        
        # Audit log
        self.audit_service.log(
            user_id=user_id,
            action="chat_query",
            details={
                "message": message[:500],
                "sql_queries": sql_queries,
                "tokens": total_input_tokens + total_output_tokens,
                "cost_usd": cost_usd
            }
        )
        
        return result
```

#### Week 8: API Endpoints & Telegram Handlers

**Chat API Endpoints:**
```python
# app/api/v1/chat.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.chat import ChatRequest, ChatResponse, ChatHistoryResponse
from app.services.claude_service import ClaudeRevenueAssistant
from app.services.cache_service import CacheService
from app.core.rate_limiter import RateLimiter, RATE_LIMITS
from app.models.chat import ChatHistory

router = APIRouter()

@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: Request,
    chat_request: ChatRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    rate_limiter: RateLimiter = Depends()
):
    """Process user query and return AI response"""
    
    # Check rate limit
    key = rate_limiter.get_user_rate_limit_key(current_user.id, "chat")
    allowed, remaining = rate_limiter.check_rate_limit(
        key, 
        RATE_LIMITS["chat"]["limit"],
        RATE_LIMITS["chat"]["window"]
    )
    
    if not allowed:
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded. Please wait before sending more queries."
        )
    
    # Get conversation history if continuing
    conversation_history = []
    if chat_request.conversation_id:
        history = db.query(ChatHistory).filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.conversation_id == chat_request.conversation_id
        ).order_by(ChatHistory.created_at).limit(10).all()
        
        for h in history:
            conversation_history.append({"role": "user", "content": h.question})
            conversation_history.append({"role": "assistant", "content": h.ai_response})
    
    # Process query
    assistant = ClaudeRevenueAssistant(...)  # Inject dependencies
    result = await assistant.chat(
        user_id=current_user.id,
        message=chat_request.message,
        session_id=current_user.session_id,
        conversation_history=conversation_history
    )
    
    # Save to history
    chat_record = ChatHistory(
        user_id=current_user.id,
        session_id=current_user.session_id,
        conversation_id=chat_request.conversation_id or generate_conversation_id(),
        question=chat_request.message,
        generated_sql=json.dumps(result["sql_queries"]),
        ai_response=result["response"],
        tokens_used=result["tokens_used"]["input"] + result["tokens_used"]["output"],
        execution_time_ms=result["execution_time_ms"]
    )
    db.add(chat_record)
    db.commit()
    
    return ChatResponse(
        response=result["response"],
        conversation_id=chat_record.conversation_id,
        chat_id=chat_record.id,
        tokens_used=result["tokens_used"],
        remaining_rate_limit=remaining
    )

@router.get("/history", response_model=List[ChatHistoryResponse])
async def get_chat_history(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's chat history"""
    query = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    )
    
    if search:
        query = query.filter(
            ChatHistory.question.ilike(f"%{search}%")
        )
    
    total = query.count()
    chats = query.order_by(ChatHistory.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return {
        "items": chats,
        "total": total,
        "page": page,
        "page_size": page_size
    }

@router.post("/{chat_id}/bookmark")
async def bookmark_chat(
    chat_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bookmark a chat for easy access"""
    chat = db.query(ChatHistory).filter(
        ChatHistory.id == chat_id,
        ChatHistory.user_id == current_user.id
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.is_bookmarked = not chat.is_bookmarked
    db.commit()
    
    return {"bookmarked": chat.is_bookmarked}
```

**Telegram Bot Handlers:**
```python
# app/telegram/handlers/chat.py
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.services.auth_service import AuthService
from app.services.claude_service import ClaudeRevenueAssistant
from app.core.rate_limiter import RateLimiter

class TelegramChatHandler:
    def __init__(
        self,
        auth_service: AuthService,
        assistant: ClaudeRevenueAssistant,
        rate_limiter: RateLimiter
    ):
        self.auth_service = auth_service
        self.assistant = assistant
        self.rate_limiter = rate_limiter
    
    async def handle_message(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle incoming message"""
        chat_id = update.effective_chat.id
        user_message = update.message.text
        
        # Validate session
        session = self.auth_service.validate_telegram_session(chat_id)
        if not session:
            await update.message.reply_text(
                "กรุณายืนยันตัวตนก่อนใช้งาน\n"
                "พิมพ์ /login เพื่อเริ่มต้น"
            )
            return
        
        # Check rate limit
        key = self.rate_limiter.get_user_rate_limit_key(session.user_id, "chat")
        allowed, remaining = self.rate_limiter.check_rate_limit(key, 30, 60)
        
        if not allowed:
            await update.message.reply_text(
                "คุณส่งคำถามเร็วเกินไป กรุณารอสักครู่แล้วลองใหม่"
            )
            return
        
        # Send typing indicator
        await update.message.chat.send_action("typing")
        
        try:
            # Process query
            result = await self.assistant.chat(
                user_id=session.user_id,
                message=user_message,
                session_id=session.id
            )
            
            response = result["response"]
            
            # Split long messages
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response)
            
            # Show remaining queries
            if remaining < 10:
                await update.message.reply_text(
                    f"📊 เหลือโควต้าอีก {remaining} คำถามในนาทีนี้"
                )
                
        except Exception as e:
            await update.message.reply_text(
                f"เกิดข้อผิดพลาด: {str(e)}\n"
                "กรุณาลองใหม่อีกครั้ง หรือติดต่อผู้ดูแลระบบ"
            )
```

**Deliverables Phase 3:**
- [ ] Claude AI integration with tool use
- [ ] SQL query validation and execution
- [ ] Chat history storage
- [ ] Rate limiting per user
- [ ] Caching layer
- [ ] API endpoints for chat
- [ ] Telegram bot handlers
- [ ] Cost tracking

---

## Phase 4: Reports & Export (2 สัปดาห์)

### 4.1 Report Generation Service

#### Week 9-10: Report Service Implementation

**Report Types:**
| Type | Format | Description |
|------|--------|-------------|
| Data Export | XLSX, CSV | Raw data export with filters |
| Summary Report | PDF, XLSX | Formatted summary with charts |
| Dashboard Export | PDF | Current dashboard as PDF |
| Scheduled Report | PDF, XLSX | Auto-generated periodic reports |

**Report Service:**
```python
# app/services/report_service.py
import io
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, PatternFill
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.config import settings
from app.services.database_service import MSSQLService
from app.services.storage_service import StorageService

# Register Thai font
pdfmetrics.registerFont(TTFont('THSarabun', 'fonts/THSarabun.ttf'))

class ReportService:
    def __init__(
        self,
        db_service: MSSQLService,
        storage_service: StorageService
    ):
        self.db_service = db_service
        self.storage_service = storage_service
    
    async def generate_excel_report(
        self,
        user_id: int,
        title: str,
        query: str,
        filters: Optional[Dict] = None,
        include_charts: bool = True
    ) -> str:
        """Generate Excel report with data and optional charts"""
        
        # Execute query
        data = self.db_service.execute_query(query)
        df = pd.DataFrame(data)
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        
        # Add title
        ws.merge_cells('A1:F1')
        ws['A1'] = title
        ws['A1'].font = Font(size=16, bold=True)
        ws['A1'].alignment = Alignment(horizontal='center')
        
        # Add metadata
        ws['A2'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ws['A3'] = f"Records: {len(df)}"
        
        # Add headers
        header_row = 5
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        for col, column_name in enumerate(df.columns, 1):
            cell = ws.cell(row=header_row, column=col, value=column_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
        
        # Add data
        for row_idx, row in enumerate(df.values, header_row + 1):
            for col_idx, value in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                
                # Format numbers
                if isinstance(value, (int, float)):
                    cell.number_format = '#,##0.00'
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
        
        # Add charts if requested
        if include_charts and len(df) > 0:
            self._add_excel_charts(wb, df)
        
        # Save to buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        
        # Upload to storage
        filename = f"reports/{user_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title}.xlsx"
        file_path = await self.storage_service.upload(filename, buffer.read())
        
        return file_path
    
    def _add_excel_charts(self, wb: Workbook, df: pd.DataFrame):
        """Add charts to Excel workbook"""
        ws_charts = wb.create_sheet("Charts")
        
        # Find numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if not numeric_cols:
            return
        
        # Create bar chart for first numeric column
        if len(numeric_cols) >= 1:
            ws_data = wb.active
            
            chart = BarChart()
            chart.title = f"{numeric_cols[0]} by Category"
            chart.style = 10
            
            data = Reference(ws_data, min_col=df.columns.get_loc(numeric_cols[0]) + 1,
                           min_row=5, max_row=min(25, len(df) + 5))
            cats = Reference(ws_data, min_col=1, min_row=6, max_row=min(25, len(df) + 5))
            
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            chart.width = 15
            chart.height = 10
            
            ws_charts.add_chart(chart, "A1")
    
    async def generate_pdf_report(
        self,
        user_id: int,
        title: str,
        content: Dict[str, Any],
        template: str = "summary"
    ) -> str:
        """Generate PDF report"""
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        
        # Styles
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='ThaiTitle',
            fontName='THSarabun',
            fontSize=24,
            alignment=1,
            spaceAfter=20
        ))
        styles.add(ParagraphStyle(
            name='ThaiBody',
            fontName='THSarabun',
            fontSize=14,
            leading=20
        ))
        
        story = []
        
        # Title
        story.append(Paragraph(title, styles['ThaiTitle']))
        story.append(Spacer(1, 20))
        
        # Metadata
        story.append(Paragraph(
            f"วันที่สร้าง: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles['ThaiBody']
        ))
        story.append(Spacer(1, 20))
        
        # Content based on template
        if template == "summary":
            self._add_summary_content(story, content, styles)
        elif template == "detailed":
            self._add_detailed_content(story, content, styles)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        # Upload to storage
        filename = f"reports/{user_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title}.pdf"
        file_path = await self.storage_service.upload(filename, buffer.read())
        
        return file_path
    
    def _add_summary_content(self, story, content, styles):
        """Add summary content to PDF"""
        
        if "summary_text" in content:
            story.append(Paragraph(content["summary_text"], styles['ThaiBody']))
            story.append(Spacer(1, 20))
        
        if "table_data" in content:
            data = content["table_data"]
            
            # Create table
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'THSarabun'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('FONTSIZE', (0, 1), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
            ]))
            
            story.append(table)
    
    async def generate_csv_export(
        self,
        user_id: int,
        query: str,
        filename: str
    ) -> str:
        """Generate CSV export"""
        
        data = self.db_service.execute_query(query)
        df = pd.DataFrame(data)
        
        buffer = io.StringIO()
        df.to_csv(buffer, index=False, encoding='utf-8-sig')  # BOM for Excel Thai support
        
        file_path = f"exports/{user_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}.csv"
        await self.storage_service.upload(file_path, buffer.getvalue().encode('utf-8-sig'))
        
        return file_path
```

**Report API Endpoints:**
```python
# app/api/v1/reports.py
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.post("/generate")
async def generate_report(
    request: ReportRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate report asynchronously"""
    
    # Check rate limit
    # ...
    
    # Create report record
    report = GeneratedReport(
        user_id=current_user.id,
        report_type=request.report_type,
        status="pending"
    )
    db.add(report)
    db.commit()
    
    # Queue report generation
    background_tasks.add_task(
        generate_report_task,
        report_id=report.id,
        user_id=current_user.id,
        request=request
    )
    
    return {"report_id": report.id, "status": "pending"}

@router.get("/{report_id}/download")
async def download_report(
    report_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download generated report"""
    
    report = db.query(GeneratedReport).filter(
        GeneratedReport.id == report_id,
        GeneratedReport.user_id == current_user.id
    ).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    if report.status != "completed":
        raise HTTPException(status_code=400, detail="Report not ready")
    
    # Get file from storage
    file_content = await storage_service.download(report.file_path)
    
    # Update download count
    report.download_count += 1
    db.commit()
    
    # Determine content type
    content_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "csv": "text/csv"
    }
    
    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=content_types.get(report.format, "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename={report.filename}"
        }
    )
```

**Deliverables Phase 4:**
- [ ] Excel report generation with charts
- [ ] PDF report generation with Thai font
- [ ] CSV export
- [ ] Background task processing
- [ ] File storage (MinIO)
- [ ] Download endpoints
- [ ] Report history

---

## Phase 5: Dashboard & Visualization (2 สัปดาห์)

### 5.1 Dashboard Service

#### Week 11-12: Dashboard Implementation

**Dashboard Features:**
- Configurable widgets (charts, tables, KPIs)
- Auto-refresh capability
- Multiple dashboard layouts
- Export dashboard as PDF

**Dashboard Configuration Schema:**
```python
# app/schemas/dashboard.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from enum import Enum

class WidgetType(str, Enum):
    KPI_CARD = "kpi_card"
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    PIE_CHART = "pie_chart"
    TABLE = "table"
    TREND = "trend"

class Widget(BaseModel):
    id: str
    type: WidgetType
    title: str
    query_template: str
    parameters: Dict[str, Any] = {}
    position: Dict[str, int]  # {x, y, width, height}
    refresh_interval: Optional[int] = None  # seconds
    
class DashboardConfig(BaseModel):
    id: int
    name: str
    description: Optional[str]
    layout: str  # "grid" | "free"
    columns: int = 12
    widgets: List[Widget]
    default_filters: Dict[str, Any] = {}
    refresh_interval: int = 300  # 5 minutes default
```

**Dashboard Service:**
```python
# app/services/dashboard_service.py
from typing import Dict, List, Any
import asyncio

from app.services.database_service import MSSQLService
from app.services.cache_service import CacheService

class DashboardService:
    def __init__(
        self,
        db_service: MSSQLService,
        cache_service: CacheService
    ):
        self.db_service = db_service
        self.cache_service = cache_service
    
    async def get_dashboard_data(
        self,
        dashboard_id: int,
        filters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Fetch all widget data for a dashboard"""
        
        # Get dashboard config
        config = await self.get_dashboard_config(dashboard_id)
        
        # Fetch data for all widgets concurrently
        tasks = []
        for widget in config.widgets:
            tasks.append(self._fetch_widget_data(widget, filters))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Map results to widgets
        widget_data = {}
        for widget, result in zip(config.widgets, results):
            if isinstance(result, Exception):
                widget_data[widget.id] = {"error": str(result)}
            else:
                widget_data[widget.id] = result
        
        return {
            "dashboard": config,
            "data": widget_data,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def _fetch_widget_data(
        self,
        widget: Widget,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fetch data for a single widget"""
        
        # Check cache
        cache_key = f"widget:{widget.id}:{hash(str(filters))}"
        cached = self.cache_service.get(cache_key)
        if cached:
            return cached
        
        # Build query with filters
        query = self._build_widget_query(widget, filters)
        
        # Execute query
        raw_data = self.db_service.execute_query(query)
        
        # Transform data based on widget type
        if widget.type == WidgetType.KPI_CARD:
            data = self._transform_kpi_data(raw_data)
        elif widget.type in [WidgetType.BAR_CHART, WidgetType.LINE_CHART]:
            data = self._transform_chart_data(raw_data, widget)
        elif widget.type == WidgetType.PIE_CHART:
            data = self._transform_pie_data(raw_data)
        elif widget.type == WidgetType.TABLE:
            data = self._transform_table_data(raw_data)
        else:
            data = raw_data
        
        # Cache result
        self.cache_service.set(cache_key, data, ttl=60)  # 1 minute cache
        
        return data
    
    def _transform_chart_data(self, raw_data: List[Dict], widget: Widget) -> Dict:
        """Transform raw data to chart format"""
        
        labels = []
        datasets = []
        
        if not raw_data:
            return {"labels": [], "datasets": []}
        
        # Extract labels (first column)
        label_key = list(raw_data[0].keys())[0]
        labels = [row[label_key] for row in raw_data]
        
        # Extract data series (remaining columns)
        value_keys = list(raw_data[0].keys())[1:]
        
        for key in value_keys:
            datasets.append({
                "label": key,
                "data": [row[key] for row in raw_data]
            })
        
        return {
            "labels": labels,
            "datasets": datasets
        }
```

**Pre-built Dashboard Templates:**
```python
# app/services/dashboard_templates.py

REVENUE_OVERVIEW_DASHBOARD = {
    "name": "Revenue Overview",
    "description": "ภาพรวมรายได้แยกตาม BU และ Service Group",
    "widgets": [
        {
            "id": "total_revenue",
            "type": "kpi_card",
            "title": "รายได้รวม (YTD)",
            "query_template": """
                SELECT SUM(REVENUE_VALUE_YTD) as value
                FROM EXPORT_NT_REVENUE_SUB_PRODUCT
                WHERE TIME_KEY = (SELECT MAX(TIME_KEY) FROM EXPORT_NT_REVENUE_SUB_PRODUCT)
            """,
            "position": {"x": 0, "y": 0, "width": 3, "height": 1}
        },
        {
            "id": "revenue_by_bu",
            "type": "bar_chart",
            "title": "รายได้แยกตาม BU",
            "query_template": """
                SELECT BU, SUM(REVENUE_VALUE) as Revenue
                FROM EXPORT_NT_REVENUE_SUB_PRODUCT
                WHERE TIME_KEY = '{time_key}'
                GROUP BY BU
                ORDER BY Revenue DESC
            """,
            "position": {"x": 0, "y": 1, "width": 6, "height": 2}
        },
        {
            "id": "revenue_trend",
            "type": "line_chart",
            "title": "แนวโน้มรายได้ 12 เดือน",
            "query_template": """
                SELECT MONTH_YEAR_TH_ABB, SUM(REVENUE_VALUE) as Revenue
                FROM EXPORT_NT_REVENUE_SUB_PRODUCT
                WHERE TIME_KEY >= '{start_time_key}'
                GROUP BY TIME_KEY, MONTH_YEAR_TH_ABB
                ORDER BY TIME_KEY
            """,
            "position": {"x": 6, "y": 1, "width": 6, "height": 2}
        },
        {
            "id": "service_group_pie",
            "type": "pie_chart",
            "title": "สัดส่วนรายได้ตาม Service Group",
            "query_template": """
                SELECT SERVICE_GROUP_NT, SUM(REVENUE_VALUE) as Revenue
                FROM EXPORT_NT_REVENUE_SUB_PRODUCT
                WHERE TIME_KEY = '{time_key}'
                GROUP BY SERVICE_GROUP_NT
            """,
            "position": {"x": 0, "y": 3, "width": 4, "height": 2}
        }
    ]
}
```

**Deliverables Phase 5:**
- [ ] Dashboard configuration model
- [ ] Widget data fetching service
- [ ] Pre-built dashboard templates
- [ ] Dashboard CRUD endpoints
- [ ] Real-time data refresh (WebSocket optional)
- [ ] Dashboard export to PDF
- [ ] Frontend dashboard components

---

## Phase 6: Templates & Scheduling (2 สัปดาห์)

### 6.1 Saved Query Templates

#### Week 13-14: Template & Scheduling System

**Template Service:**
```python
# app/services/template_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import re

from app.models.template import SavedTemplate
from app.schemas.template import TemplateCreate, TemplateUpdate

class TemplateService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_template(
        self,
        user_id: int,
        template: TemplateCreate
    ) -> SavedTemplate:
        """Create new query template"""
        
        # Extract parameters from template
        parameters = self._extract_parameters(template.question_template)
        
        db_template = SavedTemplate(
            user_id=user_id,
            name=template.name,
            description=template.description,
            question_template=template.question_template,
            category=template.category,
            is_public=template.is_public,
            parameters=parameters
        )
        
        self.db.add(db_template)
        self.db.commit()
        self.db.refresh(db_template)
        
        return db_template
    
    def _extract_parameters(self, template: str) -> List[Dict]:
        """Extract parameter placeholders from template"""
        # Pattern: {param_name:type:default}
        pattern = r'\{(\w+)(?::(\w+))?(?::([^}]+))?\}'
        matches = re.findall(pattern, template)
        
        parameters = []
        for match in matches:
            param = {
                "name": match[0],
                "type": match[1] or "string",
                "default": match[2] or None
            }
            parameters.append(param)
        
        return parameters
    
    def fill_template(
        self,
        template: SavedTemplate,
        values: Dict[str, Any]
    ) -> str:
        """Fill template with provided values"""
        
        question = template.question_template
        
        for param in template.parameters:
            placeholder = f"{{{param['name']}}}"
            value = values.get(param['name'], param.get('default', ''))
            question = question.replace(placeholder, str(value))
        
        return question
    
    def get_public_templates(
        self,
        category: Optional[str] = None
    ) -> List[SavedTemplate]:
        """Get all public templates"""
        
        query = self.db.query(SavedTemplate).filter(
            SavedTemplate.is_public == True
        )
        
        if category:
            query = query.filter(SavedTemplate.category == category)
        
        return query.order_by(SavedTemplate.usage_count.desc()).all()
    
    def get_user_templates(
        self,
        user_id: int
    ) -> List[SavedTemplate]:
        """Get user's saved templates"""
        
        return self.db.query(SavedTemplate).filter(
            SavedTemplate.user_id == user_id
        ).order_by(SavedTemplate.usage_count.desc()).all()
    
    def increment_usage(self, template_id: int):
        """Increment template usage count"""
        
        template = self.db.query(SavedTemplate).filter(
            SavedTemplate.id == template_id
        ).first()
        
        if template:
            template.usage_count += 1
            self.db.commit()
```

**Scheduled Reports Service:**
```python
# app/services/scheduled_report_service.py
from datetime import datetime, timedelta
from typing import List, Optional
from croniter import croniter

from app.models.schedule import ScheduledReport
from app.services.report_service import ReportService
from app.services.email_service import EmailService

class ScheduledReportService:
    def __init__(
        self,
        db: Session,
        report_service: ReportService,
        email_service: EmailService
    ):
        self.db = db
        self.report_service = report_service
        self.email_service = email_service
    
    def create_schedule(
        self,
        user_id: int,
        template_id: int,
        schedule_config: Dict
    ) -> ScheduledReport:
        """Create new scheduled report"""
        
        # Parse schedule config
        schedule_type = schedule_config.get("type", "daily")  # daily, weekly, monthly
        
        if schedule_type == "daily":
            cron_expression = f"0 {schedule_config.get('hour', 8)} * * *"
        elif schedule_type == "weekly":
            day = schedule_config.get("day_of_week", 1)  # Monday
            cron_expression = f"0 {schedule_config.get('hour', 8)} * * {day}"
        elif schedule_type == "monthly":
            day = schedule_config.get("day_of_month", 1)
            cron_expression = f"0 {schedule_config.get('hour', 8)} {day} * *"
        else:
            cron_expression = schedule_config.get("cron", "0 8 * * *")
        
        # Calculate next run
        cron = croniter(cron_expression, datetime.utcnow())
        next_run = cron.get_next(datetime)
        
        schedule = ScheduledReport(
            user_id=user_id,
            template_id=template_id,
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            cron_expression=cron_expression,
            next_run_at=next_run,
            is_active=True,
            delivery_method=schedule_config.get("delivery", "email"),
            delivery_config=schedule_config.get("delivery_config", {})
        )
        
        self.db.add(schedule)
        self.db.commit()
        
        return schedule
    
    async def run_scheduled_reports(self):
        """Run all due scheduled reports (called by Celery beat)"""
        
        due_reports = self.db.query(ScheduledReport).filter(
            ScheduledReport.is_active == True,
            ScheduledReport.next_run_at <= datetime.utcnow()
        ).all()
        
        for schedule in due_reports:
            try:
                await self._execute_scheduled_report(schedule)
                
                # Update next run time
                cron = croniter(schedule.cron_expression, datetime.utcnow())
                schedule.next_run_at = cron.get_next(datetime)
                schedule.last_run_at = datetime.utcnow()
                
            except Exception as e:
                schedule.last_error = str(e)
            
            self.db.commit()
    
    async def _execute_scheduled_report(self, schedule: ScheduledReport):
        """Execute a single scheduled report"""
        
        # Get template
        template = self.db.query(SavedTemplate).filter(
            SavedTemplate.id == schedule.template_id
        ).first()
        
        # Fill template with current date parameters
        params = self._get_current_period_params()
        question = template_service.fill_template(template, params)
        
        # Generate report
        # ... use Claude to process query
        # ... generate report file
        
        # Deliver report
        if schedule.delivery_method == "email":
            await self._deliver_via_email(schedule, report_path)
        elif schedule.delivery_method == "telegram":
            await self._deliver_via_telegram(schedule, report_path)
    
    def _get_current_period_params(self) -> Dict:
        """Get parameters for current period"""
        
        now = datetime.now()
        last_month = now.replace(day=1) - timedelta(days=1)
        
        return {
            "current_year": str(now.year),
            "current_month": str(now.month).zfill(2),
            "last_month_year": str(last_month.year),
            "last_month": str(last_month.month).zfill(2),
            "time_key": f"{last_month.year}{str(last_month.month).zfill(2)}",
            "year_th": str(now.year + 543)
        }
```

**Celery Task for Scheduled Reports:**
```python
# app/workers/scheduled_reports.py
from celery import Celery
from app.services.scheduled_report_service import ScheduledReportService

celery_app = Celery('tasks', broker=settings.REDIS_URL)

@celery_app.task
def run_scheduled_reports():
    """Celery task to run scheduled reports"""
    service = ScheduledReportService(...)
    asyncio.run(service.run_scheduled_reports())

# Celery beat schedule
celery_app.conf.beat_schedule = {
    'run-scheduled-reports': {
        'task': 'app.workers.scheduled_reports.run_scheduled_reports',
        'schedule': crontab(minute='*/15'),  # Check every 15 minutes
    },
}
```

**Pre-defined Templates:**
```python
# app/data/default_templates.py

DEFAULT_TEMPLATES = [
    {
        "name": "รายได้รวมตาม BU ประจำเดือน",
        "description": "สรุปรายได้รวมแยกตาม Business Unit สำหรับเดือนที่ระบุ",
        "question_template": "รายได้รวมแยกตาม BU ประจำเดือน {month}/{year}",
        "category": "revenue",
        "is_public": True,
        "parameters": [
            {"name": "month", "type": "month", "default": "current"},
            {"name": "year", "type": "year", "default": "current"}
        ]
    },
    {
        "name": "ยอดขายตาม Product เปรียบเทียบเดือนก่อน",
        "description": "เปรียบเทียบยอดขายแต่ละ Product กับเดือนก่อนหน้า",
        "question_template": "ยอดขายแยกตาม Product เดือน {month}/{year} เทียบกับเดือนก่อน",
        "category": "sales",
        "is_public": True,
        "parameters": [
            {"name": "month", "type": "month", "default": "current"},
            {"name": "year", "type": "year", "default": "current"}
        ]
    },
    {
        "name": "Top 10 หน่วยงานยอดขายสูงสุด",
        "description": "10 อันดับหน่วยงานที่มียอดขายสูงสุด",
        "question_template": "10 หน่วยงานที่มียอดขายสูงสุด ประจำเดือน {month}/{year}",
        "category": "sales",
        "is_public": True
    },
    {
        "name": "รายได้ YTD แยกตาม Service Group",
        "description": "รายได้สะสมตั้งแต่ต้นปีแยกตามกลุ่มบริการ",
        "question_template": "รายได้ YTD แยกตาม Service Group ถึงเดือน {month}/{year}",
        "category": "revenue",
        "is_public": True
    }
]
```

**Deliverables Phase 6:**
- [ ] Template CRUD operations
- [ ] Parameter extraction and filling
- [ ] Public/private templates
- [ ] Template categories
- [ ] Scheduled report creation
- [ ] Celery beat scheduler
- [ ] Email/Telegram delivery
- [ ] Pre-defined templates

---

## Phase 7: Testing & Security Audit (2 สัปดาห์)

### 7.1 Testing Strategy

#### Week 15-16: Comprehensive Testing

**Test Categories:**

| Category | Tools | Coverage Target |
|----------|-------|-----------------|
| Unit Tests | pytest | 80%+ |
| Integration Tests | pytest + testcontainers | API endpoints |
| E2E Tests | Playwright | Critical user flows |
| Load Tests | Locust | 100 concurrent users |
| Security Tests | OWASP ZAP, manual | OWASP Top 10 |

**Unit Test Examples:**
```python
# tests/unit/test_otp_service.py
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from app.services.otp_service import OTPService
from app.core.exceptions import InvalidDomainError, OTPExpiredError

class TestOTPService:
    
    def test_validate_email_domain_allowed(self):
        """Test that allowed domains pass validation"""
        service = OTPService(Mock(), Mock())
        
        assert service.validate_email_domain("user@example.com") == True
        assert service.validate_email_domain("user@example.com") == True
    
    def test_validate_email_domain_not_allowed(self):
        """Test that non-allowed domains fail validation"""
        service = OTPService(Mock(), Mock())
        
        assert service.validate_email_domain("user@gmail.com") == False
        assert service.validate_email_domain("user@other.co.th") == False
    
    def test_generate_otp_length(self):
        """Test OTP has correct length"""
        service = OTPService(Mock(), Mock())
        otp = service.generate_otp()
        
        assert len(otp) == 6
        assert otp.isdigit()
    
    def test_verify_otp_expired(self):
        """Test expired OTP raises error"""
        mock_db = Mock()
        mock_otp_request = Mock()
        mock_otp_request.expires_at = datetime.utcnow() - timedelta(minutes=1)
        mock_otp_request.verified_at = None
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_otp_request
        
        service = OTPService(mock_db, Mock())
        
        with pytest.raises(OTPExpiredError):
            service.verify_otp("user@example.com", "123456", "web")
```

**Integration Test Examples:**
```python
# tests/integration/test_chat_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

class TestChatAPI:
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self, client):
        # Login and get token
        # ...
        return {"Authorization": f"Bearer {token}"}
    
    def test_chat_query_success(self, client, auth_headers):
        """Test successful chat query"""
        response = client.post(
            "/api/v1/chat/query",
            json={"message": "รายได้รวมเดือนล่าสุด"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "conversation_id" in data
    
    def test_chat_query_rate_limited(self, client, auth_headers):
        """Test rate limiting kicks in"""
        # Send 31 requests (limit is 30/minute)
        for _ in range(31):
            response = client.post(
                "/api/v1/chat/query",
                json={"message": "test"},
                headers=auth_headers
            )
        
        assert response.status_code == 429
```

**Load Test Configuration:**
```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class RevenueAssistantUser(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": "test@example.com"
        })
        # ... complete OTP flow
        self.token = "..."
    
    @task(10)
    def chat_query(self):
        self.client.post(
            "/api/v1/chat/query",
            json={"message": "รายได้รวมเดือนล่าสุด"},
            headers={"Authorization": f"Bearer {self.token}"}
        )
    
    @task(3)
    def get_history(self):
        self.client.get(
            "/api/v1/chat/history",
            headers={"Authorization": f"Bearer {self.token}"}
        )
    
    @task(1)
    def generate_report(self):
        self.client.post(
            "/api/v1/reports/generate",
            json={"report_type": "excel", "query": "..."},
            headers={"Authorization": f"Bearer {self.token}"}
        )
```

### 7.2 Security Audit Checklist

**Authentication & Authorization:**
- [ ] OTP cannot be brute-forced (rate limiting)
- [ ] Session tokens are cryptographically secure
- [ ] Session expiry works correctly
- [ ] Domain validation cannot be bypassed
- [ ] Telegram authentication is secure

**SQL Injection Prevention:**
- [ ] All queries are parameterized
- [ ] Only SELECT statements allowed
- [ ] Query validation is enforced
- [ ] No dynamic table/column names from user input

**API Security:**
- [ ] All endpoints require authentication
- [ ] Rate limiting on all endpoints
- [ ] Input validation on all parameters
- [ ] Proper error messages (no info leakage)
- [ ] CORS configured correctly

**Data Protection:**
- [ ] Sensitive data encrypted at rest
- [ ] HTTPS enforced
- [ ] API keys stored securely
- [ ] Audit logs cannot be tampered

**Deliverables Phase 7:**
- [ ] Unit tests with 80%+ coverage
- [ ] Integration tests for all APIs
- [ ] E2E tests for critical flows
- [ ] Load test results (100 concurrent users)
- [ ] Security audit report
- [ ] Bug fixes from testing
- [ ] Performance optimization

---

## Phase 8: Deployment & Go-Live (1 สัปดาห์)

### 8.1 Deployment Architecture

#### Week 17: Production Deployment

**Production Infrastructure:**
```
                                    ┌─────────────────┐
                                    │   CloudFlare    │
                                    │   (CDN + WAF)   │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │     NGINX       │
                                    │  Load Balancer  │
                                    │   (SSL Term)    │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
           ┌────────▼────────┐     ┌────────▼────────┐     ┌────────▼────────┐
           │   App Server 1  │     │   App Server 2  │     │   Bot Server    │
           │   (FastAPI)     │     │   (FastAPI)     │     │   (Telegram)    │
           └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
                    │                        │                        │
                    └────────────────────────┼────────────────────────┘
                                             │
           ┌─────────────────────────────────┼─────────────────────────────────┐
           │                                 │                                 │
  ┌────────▼────────┐             ┌─────────▼─────────┐            ┌──────────▼──────────┐
  │   PostgreSQL    │             │      Redis        │            │       MinIO         │
  │   (Primary)     │             │   (Cluster)       │            │   (File Storage)    │
  │                 │             │                   │            │                     │
  └────────┬────────┘             └───────────────────┘            └─────────────────────┘
           │
  ┌────────▼────────┐
  │   PostgreSQL    │
  │   (Replica)     │
  └─────────────────┘
```

**Docker Production Configuration:**
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  app:
    image: nt-revenue-assistant:${VERSION}
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '2'
          memory: 4G
    environment:
      - ENV=production
      - DATABASE_URL=${DATABASE_URL}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  telegram-bot:
    image: nt-revenue-assistant:${VERSION}
    command: python -m app.telegram_bot
    deploy:
      replicas: 1
    environment:
      - ENV=production

  celery-worker:
    image: nt-revenue-assistant:${VERSION}
    command: celery -A app.celery worker -l info -c 4
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 2G

  celery-beat:
    image: nt-revenue-assistant:${VERSION}
    command: celery -A app.celery beat -l info
    deploy:
      replicas: 1

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl
```

**Environment Variables (Production):**
```bash
# .env.production

# Application
ENV=production
DEBUG=false
SECRET_KEY=<generate-secure-key>
ALLOWED_HOSTS=revenue.example.com

# Database
DATABASE_URL=postgresql://user:pass@postgres-primary:5432/nt_assistant
MSSQL_HOST=10.200.1.92
MSSQL_USER=<username>
MSSQL_PASSWORD=<password>
MSSQL_DATABASE=FI

# Redis
REDIS_URL=redis://redis-cluster:6379/0

# Claude API
ANTHROPIC_API_KEY=<api-key>
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=4096

# Email
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=<username>
SMTP_PASSWORD=<password>
FROM_EMAIL=noreply@example.com

# Telegram
TELEGRAM_BOT_TOKEN=<bot-token>

# Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_BUCKET=nt-assistant

# Security
ALLOWED_EMAIL_DOMAINS=example.com,example.com
SESSION_EXPIRY_HOURS=24
OTP_EXPIRY_MINUTES=10
```

### 8.2 Monitoring & Alerting

**Monitoring Stack:**
- **Prometheus**: Metrics collection
- **Grafana**: Visualization & dashboards
- **Loki**: Log aggregation
- **AlertManager**: Alerting

**Key Metrics to Monitor:**
```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Business metrics
CHAT_QUERIES = Counter(
    'chat_queries_total',
    'Total chat queries',
    ['user_type', 'platform']
)

CLAUDE_TOKENS = Counter(
    'claude_tokens_total',
    'Claude API tokens used',
    ['type']  # input/output
)

CLAUDE_COST = Counter(
    'claude_cost_usd_total',
    'Claude API cost in USD'
)

ACTIVE_SESSIONS = Gauge(
    'active_sessions',
    'Number of active user sessions',
    ['platform']
)

REPORT_GENERATION = Histogram(
    'report_generation_seconds',
    'Report generation time',
    ['report_type']
)
```

**Alert Rules:**
```yaml
# prometheus/alerts.yml
groups:
  - name: nt-revenue-assistant
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: High error rate detected
          
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: High latency detected (p95 > 5s)
          
      - alert: ClaudeCostHigh
        expr: increase(claude_cost_usd_total[1h]) > 10
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: Claude API cost exceeded $10/hour
          
      - alert: DatabaseConnectionFailed
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: Database connection lost
```

### 8.3 Go-Live Checklist

**Pre-Launch:**
- [ ] All tests passing
- [ ] Security audit completed
- [ ] Performance benchmarks met
- [ ] Backup procedures tested
- [ ] Rollback plan documented
- [ ] Monitoring dashboards ready
- [ ] Alert rules configured
- [ ] Documentation completed
- [ ] User training materials ready

**Launch Day:**
- [ ] DNS configured
- [ ] SSL certificates installed
- [ ] Database migrations applied
- [ ] Default templates loaded
- [ ] Admin accounts created
- [ ] Smoke tests passed
- [ ] Monitoring verified

**Post-Launch:**
- [ ] Monitor error rates
- [ ] Monitor latency
- [ ] Monitor API costs
- [ ] Collect user feedback
- [ ] Address critical issues
- [ ] Plan iteration 2

**Deliverables Phase 8:**
- [ ] Production environment deployed
- [ ] CI/CD pipeline configured
- [ ] Monitoring dashboards
- [ ] Alert rules
- [ ] Backup procedures
- [ ] User documentation
- [ ] Admin documentation
- [ ] Go-live sign-off

---

## 9. Cost Estimation

### 9.1 Infrastructure Costs (Monthly)

| Item | Specification | Est. Cost (THB) |
|------|---------------|-----------------|
| App Servers (2x) | 4 vCPU, 8GB RAM | 6,000 |
| Database Server | 4 vCPU, 16GB RAM | 5,000 |
| Redis | 2 vCPU, 4GB RAM | 2,000 |
| MinIO Storage | 100GB | 500 |
| Backup Storage | 50GB | 300 |
| SSL Certificate | Wildcard | 3,000/year |
| **Total Infrastructure** | | **~14,000/month** |

### 9.2 Claude API Costs (Monthly)

| Usage Level | Queries/Day | Est. Cost (USD) | Est. Cost (THB) |
|-------------|-------------|-----------------|-----------------|
| Low | 100 | $30-50 | 1,050-1,750 |
| Medium | 500 | $150-250 | 5,250-8,750 |
| High | 1,000 | $300-500 | 10,500-17,500 |

**Cost Control Strategies:**
1. Caching frequently asked questions
2. Rate limiting per user
3. Query complexity limits
4. Daily/monthly budget caps
5. Monitoring and alerts

### 9.3 Development Costs

| Phase | Duration | Resources | Est. Cost (THB) |
|-------|----------|-----------|-----------------|
| Phase 1-2 | 5 weeks | 2 developers | 250,000 |
| Phase 3-4 | 5 weeks | 2 developers | 250,000 |
| Phase 5-6 | 4 weeks | 2 developers | 200,000 |
| Phase 7-8 | 3 weeks | 2 developers + 1 QA | 200,000 |
| **Total Development** | 17 weeks | | **~900,000** |

---

## 10. Risk Management

### 10.1 Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude API unavailable | Low | High | Implement fallback, cache common queries |
| MSSQL connection issues | Medium | High | Connection pooling, retry logic, monitoring |
| Security breach | Low | Critical | Security audit, encryption, access controls |
| Cost overrun (API) | Medium | Medium | Budget caps, usage monitoring, alerts |
| Performance issues | Medium | Medium | Load testing, caching, optimization |
| User adoption low | Medium | Medium | Training, documentation, feedback loop |

### 10.2 Contingency Plans

**Claude API Outage:**
1. Return cached responses for common queries
2. Queue requests for later processing
3. Display maintenance message
4. Notify administrators

**Database Issues:**
1. Automatic failover to replica
2. Read-only mode if write fails
3. Manual intervention procedures

**Cost Overrun:**
1. Automatic rate limiting increase
2. Temporary service degradation
3. Admin notification
4. Budget review process

---

## 11. Success Metrics

### 11.1 Key Performance Indicators (KPIs)

| Metric | Target | Measurement |
|--------|--------|-------------|
| System Uptime | 99.5% | Monitoring |
| Response Time (p95) | < 5 seconds | Prometheus |
| User Adoption | 50+ active users/month | Analytics |
| Query Success Rate | > 95% | Logs |
| User Satisfaction | > 4/5 | Feedback |
| Cost per Query | < ฿5 | Cost tracking |

### 11.2 Review Schedule

| Review | Frequency | Participants |
|--------|-----------|--------------|
| Daily Standup | Daily | Dev team |
| Sprint Review | Bi-weekly | Dev + Stakeholders |
| Cost Review | Weekly | Dev + Finance |
| Security Review | Monthly | Dev + IT Security |
| User Feedback | Monthly | Dev + Users |

---

## 12. Appendix

### A. API Documentation Template

API documentation will be auto-generated using FastAPI's OpenAPI support and hosted at `/docs`.

### B. User Guide Outline

1. Getting Started
   - Registration and Login
   - Telegram Bot Setup
2. Asking Questions
   - Basic Queries
   - Advanced Filters
   - Using Templates
3. Reports and Exports
   - Generating Reports
   - Scheduling Reports
4. Dashboard
   - Viewing Dashboards
   - Customizing Widgets
5. Troubleshooting
   - Common Issues
   - Contact Support

### C. Admin Guide Outline

1. User Management
   - Adding/Removing Users
   - Role Assignment
2. System Configuration
   - Rate Limits
   - Cost Budgets
3. Monitoring
   - Dashboard Overview
   - Alert Management
4. Maintenance
   - Backup Procedures
   - Update Procedures
5. Audit and Compliance
   - Viewing Audit Logs
   - Generating Reports

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-23 | Claude | Initial version |

---

**Prepared for:** องค์กร - Finance Department
**Project:** AI Assistant
**Distribution:** Source-available public reference

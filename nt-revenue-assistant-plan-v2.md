# NT Revenue Assistant - Production Implementation Plan v2.0

## Document Information

| รายการ | รายละเอียด |
|--------|------------|
| Version | 2.0 |
| Date | 2025-01-23 |
| Status | Draft |
| Changes | เพิ่ม Feedback Loop, Data Retention, Security Enhancements, DevOps Details |

---

## Executive Summary

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้และยอดขายของ NT ผ่าน Web Application และ Telegram Bot โดยใช้ Claude AI เป็นตัวประมวลผลคำถามและสร้าง SQL Query

**เป้าหมายหลัก:**
- ให้บริการสอบถามข้อมูลรายได้/ยอดขายผ่าน Web App และ Telegram Bot
- ระบบ Authentication ที่ปลอดภัยด้วย Email OTP (จำกัด Domain)
- ระบบควบคุมและ Audit Log ที่ครบถ้วน
- สามารถสร้างรายงาน, กราฟ, Dashboard และ Export ได้
- รองรับการบันทึก Query Templates สำหรับใช้งานซ้ำ
- **[NEW]** ระบบ Feedback Loop สำหรับปรับปรุง AI อย่างต่อเนื่อง
- **[NEW]** Data Retention Policy และ Disaster Recovery

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
│                         [NEW] WAF Rules + Rate Limit                         │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │   FastAPI       │  │   Telegram      │  │   Background    │              │
│  │   Web Server    │  │   Bot Service   │  │   Workers       │              │
│  │   (Gunicorn)    │  │   (polling)     │  │   (Celery)      │              │
│  │                 │  │                 │  │                 │              │
│  │ [NEW] req_id    │  │ [NEW] req_id    │  │ [NEW] req_id    │              │
│  │ correlation     │  │ correlation     │  │ correlation     │              │
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
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │[NEW] Feedback│  │[NEW] Prompt  │  │[NEW] Archive │                       │
│  │   Service    │  │   Manager    │  │   Service    │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   MSSQL      │  │  PostgreSQL  │  │    Redis     │  │ File Storage │     │
│  │  (NT Data)   │  │  (App Data)  │  │   (Cache)    │  │   (MinIO)    │     │
│  │ 10.200.1.92  │  │              │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                           │                                │                 │
│                    [NEW] Partitioned              [NEW] Cold Storage        │
│                    Tables + Archive               for archived data         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Database Schema (PostgreSQL - Application Data)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    APPLICATION DATABASE SCHEMA v2.0                          │
│                    [NEW] = Added in v2.0                                     │
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
│      chat_history        │     │   [NEW] user_feedback    │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │────▶│ id (PK)                  │
│ user_id (FK)             │     │ chat_id (FK)             │
│ session_id (FK)          │     │ rating (1-5 or bool)     │
│ conversation_id          │     │ feedback_text            │
│ question                 │     │ feedback_category        │
│ generated_sql            │     │ created_at               │
│ sql_result_summary       │     │ reviewed_by (FK)         │
│ ai_response              │     │ reviewed_at              │
│ tokens_used              │     │ review_notes             │
│ execution_time_ms        │     │ is_golden_example        │
│ created_at               │     └──────────────────────────┘
│ is_bookmarked            │
│ [NEW] request_id         │     ┌──────────────────────────┐
│ [NEW] prompt_version     │     │ [NEW] golden_examples    │
└──────────────────────────┘     ├──────────────────────────┤
                                 │ id (PK)                  │
                                 │ chat_id (FK)             │
┌──────────────────────────┐     │ question_pattern         │
│ [NEW] prompt_versions    │     │ expected_sql             │
├──────────────────────────┤     │ category                 │
│ id (PK)                  │     │ is_active                │
│ version                  │     │ added_by (FK)            │
│ system_prompt            │     │ created_at               │
│ few_shot_examples (JSON) │     │ usage_count              │
│ created_at               │     └──────────────────────────┘
│ created_by               │
│ is_active                │
│ performance_score        │
│ notes                    │
└──────────────────────────┘

┌──────────────────────────┐     ┌──────────────────────────┐
│       audit_logs         │     │ [NEW] data_archives      │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ user_id (FK)             │     │ source_table             │
│ action_type              │     │ archive_file_path        │
│ resource_type            │     │ record_count             │
│ resource_id              │     │ date_range_start         │
│ details (JSON)           │     │ date_range_end           │
│ ip_address               │     │ archived_at              │
│ user_agent               │     │ file_size_bytes          │
│ created_at               │     │ checksum                 │
│ platform                 │     └──────────────────────────┘
│ [NEW] request_id         │
└──────────────────────────┘

┌──────────────────────────┐     ┌──────────────────────────┐
│ [NEW] system_config      │     │ [NEW] trending_queries   │
├──────────────────────────┤     ├──────────────────────────┤
│ id (PK)                  │     │ id (PK)                  │
│ config_key               │     │ query_pattern            │
│ config_value             │     │ display_text             │
│ description              │     │ usage_count_today        │
│ updated_at               │     │ usage_count_week         │
│ updated_by               │     │ last_used_at             │
└──────────────────────────┘     │ is_featured              │
                                 └──────────────────────────┘
```

---

## 2. Project Phases & Timeline

### Phase Overview (Updated)

| Phase | ระยะเวลา | รายละเอียด | Status |
|-------|----------|------------|--------|
| Phase 1 | 2 สัปดาห์ | Infrastructure & Core Setup | |
| Phase 2 | 3 สัปดาห์ | Authentication & Security | |
| Phase 3 | 3 สัปดาห์ | Core Features (Chat, Query) | |
| **Phase 3.5** | **1 สัปดาห์** | **[NEW] Feedback Loop & Logging** | |
| **Phase 4** | **3 สัปดาห์** | **[NEW] Universal Frontend (Expo)** | |
| **Phase 4.5** | **1 สัปดาห์** | **[NEW] Telegram Bot Integration** | |
| Phase 5 | 2 สัปดาห์ | Reports & Export | |
| Phase 6 | 2 สัปดาห์ | Dashboard & Visualization | |
| Phase 7 | 2 สัปดาห์ | Templates & Scheduling | |
| Phase 7 | 2 สัปดาห์ | Testing & Security Audit | |
| **Phase 7.5** | **0.5 สัปดาห์** | **[NEW] DR Drill & Backup Test** | |
| Phase 8 | 1 สัปดาห์ | Deployment & Go-Live | |
| **Total** | **19 สัปดาห์** | (~4.5 เดือน) | |

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
- [ ] **[NEW]** Setup centralized logging structure

**[NEW] Logging Configuration:**
```python
# app/core/logging.py
import logging
import json
import re
from contextvars import ContextVar
from typing import Optional

# Context variable for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class PIIRedactingFormatter(logging.Formatter):
    """Formatter that redacts PII from log messages"""
    
    PII_PATTERNS = [
        (r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL_REDACTED]'),
        (r'\b\d{10}\b', '[PHONE_REDACTED]'),
        (r'\b\d{13}\b', '[ID_CARD_REDACTED]'),
        (r'password["\']?\s*[:=]\s*["\']?[^"\'\\s]+', 'password=[REDACTED]'),
        (r'token["\']?\s*[:=]\s*["\']?[^"\'\s]+', 'token=[REDACTED]'),
        (r'otp["\']?\s*[:=]\s*["\']?\d+', 'otp=[REDACTED]'),
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        
        for pattern, replacement in self.PII_PATTERNS:
            message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
        
        return message

class StructuredLogFormatter(PIIRedactingFormatter):
    """JSON structured logging with request_id correlation"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get request_id from context
        request_id = request_id_var.get()
        
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data["extra"] = record.extra_data
        
        formatted = json.dumps(log_data, ensure_ascii=False)
        
        # Apply PII redaction
        for pattern, replacement in self.PII_PATTERNS:
            formatted = re.sub(pattern, replacement, formatted, flags=re.IGNORECASE)
        
        return formatted

def setup_logging():
    """Configure application logging"""
    
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredLogFormatter())
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    
    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

**[NEW] Request ID Middleware:**
```python
# app/core/middleware.py
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import request_id_var

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request_id to all requests for log correlation"""
    
    async def dispatch(self, request: Request, call_next):
        # Get or generate request_id
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Set in context for logging
        request_id_var.set(request_id)
        
        # Add to request state for handlers
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
```

#### Week 2: Project Structure & Base Code

**Project Structure (Updated):**
```
nt-revenue-assistant/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── celery.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── reports.py
│   │   │   ├── templates.py
│   │   │   ├── dashboard.py
│   │   │   ├── history.py
│   │   │   ├── feedback.py          # [NEW]
│   │   │   └── admin.py
│   │   └── deps.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py
│   │   ├── rate_limiter.py
│   │   ├── exceptions.py
│   │   ├── logging.py               # [NEW] Structured logging
│   │   └── middleware.py            # [NEW] Request ID middleware
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── otp_service.py
│   │   ├── email_service.py
│   │   ├── claude_service.py
│   │   ├── database_service.py
│   │   ├── report_service.py
│   │   ├── cache_service.py
│   │   ├── audit_service.py
│   │   ├── cost_service.py
│   │   ├── feedback_service.py      # [NEW]
│   │   ├── prompt_manager.py        # [NEW]
│   │   └── archive_service.py       # [NEW]
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── session.py
│   │   ├── chat.py
│   │   ├── template.py
│   │   ├── report.py
│   │   ├── audit.py
│   │   ├── feedback.py              # [NEW]
│   │   └── prompt_version.py        # [NEW]
│   │
│   ├── schemas/
│   │   └── ...
│   │
│   ├── db/
│   │   └── ...
│   │
│   ├── telegram/
│   │   └── ...
│   │
│   └── workers/
│       ├── __init__.py
│       ├── report_worker.py
│       ├── scheduled_reports.py
│       ├── cleanup_worker.py
│       └── archive_worker.py        # [NEW]
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/                    # [NEW] Mock responses
│       └── claude_responses.json
│
├── scripts/
│   ├── init_db.py
│   ├── create_admin.py
│   ├── backup.sh
│   └── restore.sh                   # [NEW]
│
└── ...
```

---

## Phase 2: Authentication & Security (3 สัปดาห์)

*(เนื้อหาเดิมคงไว้ + เพิ่มส่วน WAF)*

### 2.3 [NEW] WAF & Rate Limiting Configuration

**NGINX Rate Limiting by Path:**
```nginx
# /etc/nginx/conf.d/rate_limit.conf

# Define rate limit zones
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=otp_limit:10m rate=3r/m;
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=chat_limit:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=report_limit:10m rate=10r/m;

server {
    listen 443 ssl;
    server_name revenue.nt.co.th;
    
    # SSL configuration
    ssl_certificate /etc/ssl/certs/revenue.nt.co.th.crt;
    ssl_certificate_key /etc/ssl/private/revenue.nt.co.th.key;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Block suspicious user agents
    if ($http_user_agent ~* (bot|crawler|spider|scraper)) {
        return 403;
    }
    
    # Rate limited endpoints
    location /api/v1/auth/login {
        limit_req zone=login_limit burst=3 nodelay;
        limit_req_status 429;
        proxy_pass http://app:8000;
    }
    
    location /api/v1/auth/otp {
        limit_req zone=otp_limit burst=2 nodelay;
        limit_req_status 429;
        proxy_pass http://app:8000;
    }
    
    location /api/v1/chat {
        limit_req zone=chat_limit burst=10;
        limit_req_status 429;
        proxy_pass http://app:8000;
    }
    
    location /api/v1/reports {
        limit_req zone=report_limit burst=5;
        limit_req_status 429;
        proxy_pass http://app:8000;
    }
    
    location /api/ {
        limit_req zone=api_limit burst=20;
        limit_req_status 429;
        proxy_pass http://app:8000;
    }
    
    location / {
        proxy_pass http://app:8000;
    }
}
```

---

## Phase 3: Core Features - Chat & Query (3 สัปดาห์)

*(เนื้อหาเดิมคงไว้ + เพิ่ม Prompt Manager)*

### 3.3 [NEW] Prompt Manager Service

**Prompt Versioning:**
```python
# app/services/prompt_manager.py
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.prompt_version import PromptVersion
from app.models.golden_example import GoldenExample
from app.config import settings

class PromptManager:
    """Manage prompt versions and few-shot examples"""
    
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}
    
    def get_active_prompt(self) -> PromptVersion:
        """Get currently active prompt version"""
        if 'active_prompt' in self._cache:
            return self._cache['active_prompt']
        
        prompt = self.db.query(PromptVersion).filter(
            PromptVersion.is_active == True
        ).order_by(PromptVersion.created_at.desc()).first()
        
        if not prompt:
            # Create default prompt if none exists
            prompt = self._create_default_prompt()
        
        self._cache['active_prompt'] = prompt
        return prompt
    
    def get_few_shot_examples(self, category: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """Get few-shot examples for prompt"""
        
        query = self.db.query(GoldenExample).filter(
            GoldenExample.is_active == True
        )
        
        if category:
            query = query.filter(GoldenExample.category == category)
        
        examples = query.order_by(
            GoldenExample.usage_count.desc()
        ).limit(limit).all()
        
        return [
            {
                "question": ex.question_pattern,
                "sql": ex.expected_sql
            }
            for ex in examples
        ]
    
    def build_system_prompt(self, schema_info: str) -> str:
        """Build complete system prompt with few-shot examples"""
        
        active_prompt = self.get_active_prompt()
        examples = self.get_few_shot_examples(limit=5)
        
        # Build few-shot section
        few_shot_section = ""
        if examples:
            few_shot_section = "\n## ตัวอย่างคำถามและ SQL ที่ถูกต้อง\n"
            for i, ex in enumerate(examples, 1):
                few_shot_section += f"""
### ตัวอย่างที่ {i}
คำถาม: {ex['question']}
SQL: 
```sql
{ex['sql']}
```
"""
        
        # Combine all parts
        full_prompt = f"""{active_prompt.system_prompt}

## Database Schema
{schema_info}
{few_shot_section}
## Prompt Version
Version: {active_prompt.version}
"""
        return full_prompt
    
    def create_new_version(
        self,
        system_prompt: str,
        created_by: int,
        notes: str = ""
    ) -> PromptVersion:
        """Create new prompt version (doesn't activate it)"""
        
        # Get next version number
        latest = self.db.query(PromptVersion).order_by(
            PromptVersion.version.desc()
        ).first()
        
        next_version = (latest.version + 1) if latest else 1
        
        new_prompt = PromptVersion(
            version=next_version,
            system_prompt=system_prompt,
            created_at=datetime.utcnow(),
            created_by=created_by,
            is_active=False,
            notes=notes
        )
        
        self.db.add(new_prompt)
        self.db.commit()
        
        return new_prompt
    
    def activate_version(self, version_id: int):
        """Activate a specific prompt version"""
        
        # Deactivate all
        self.db.query(PromptVersion).update({"is_active": False})
        
        # Activate selected
        self.db.query(PromptVersion).filter(
            PromptVersion.id == version_id
        ).update({"is_active": True})
        
        self.db.commit()
        
        # Clear cache
        self._cache.pop('active_prompt', None)
    
    def rollback_to_version(self, version: int):
        """Rollback to a previous prompt version"""
        
        prompt = self.db.query(PromptVersion).filter(
            PromptVersion.version == version
        ).first()
        
        if prompt:
            self.activate_version(prompt.id)
```

---

## Phase 4: [NEW] Universal Frontend (Expo) (3 สัปดาห์)

**Technology Stack:**
- **Framework**: Expo (React Native)
- **Styling**: NativeWind (TailwindCSS)
- **Routing**: Expo Router (File-based routing like Next.js)
- **API Client**: TanStack Query (React Query) + Axios
- **Platform**: Web, iOS, Android (Universal Codebase)

### 4.1 Project Setup
```
frontend/
├── app/                  # Expo Router pages
│   ├── (auth)/           # Authentication group
│   │   ├── login.tsx
│   │   └── verify.tsx
│   ├── (tabs)/           # Main app tabs
│   │   ├── index.tsx     # Chat
│   │   ├── history.tsx
│   │   └── settings.tsx
│   └── _layout.tsx       # Root layout
├── components/           # Reusable components (NativeWind)
├── constants/            # Config & Colors
├── hooks/                # Custom React Hooks
└── services/             # API services
```

### 4.2 Key Features
- **Chat Interface**: Streaming response, Markdown rendering, Copy SQL/Result buttons.
- **Authentication**: Login screen with OTP verification flow.
- **History**: Infinite scroll list of past conversations (cached).
- **Settings**: Language switch (TH/EN), Theme toggle.

---

## Phase 4.5: [NEW] Telegram Bot Integration (1 สัปดาห์)

**Technology Stack:**
- **Library**: `python-telegram-bot` (Async)
- **Integration**: Direct service call to `AIService`

### 4.5.1 Bot Features
- **/start**: Welcome & Language selection.
- **/login**: Link Telegram account with Email OTP.
- **Chat**: Direct question processing.
- **Voice**: (Optional) Transcribe voice to text using AI.

---

## Phase 3.5: [NEW] Feedback Loop & Enhanced Logging (1 สัปดาห์)

### 3.5.1 User Feedback System

**Feedback Models:**
```python
# app/models/feedback.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class FeedbackRating(enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"

class FeedbackCategory(enum.Enum):
    WRONG_DATA = "wrong_data"           # ข้อมูลผิด
    INCOMPLETE = "incomplete"           # ไม่ครบถ้วน
    HARD_TO_UNDERSTAND = "hard_to_understand"  # เข้าใจยาก
    SLOW = "slow"                       # ช้า
    SQL_ERROR = "sql_error"             # SQL ผิด
    PERFECT = "perfect"                 # สมบูรณ์แบบ
    OTHER = "other"                     # อื่นๆ

class UserFeedback(Base):
    __tablename__ = "user_feedback"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chat_history.id"), nullable=False)
    rating = Column(Enum(FeedbackRating), nullable=False)
    feedback_category = Column(Enum(FeedbackCategory), nullable=True)
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    
    # Review fields (for admin)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    is_golden_example = Column(Boolean, default=False)
    
    # Relationships
    chat = relationship("ChatHistory", back_populates="feedback")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
```

**Feedback Service:**
```python
# app/services/feedback_service.py
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.models.feedback import UserFeedback, FeedbackRating, FeedbackCategory
from app.models.chat import ChatHistory
from app.models.golden_example import GoldenExample

class FeedbackService:
    def __init__(self, db: Session):
        self.db = db
    
    def submit_feedback(
        self,
        chat_id: int,
        rating: FeedbackRating,
        category: Optional[FeedbackCategory] = None,
        feedback_text: Optional[str] = None
    ) -> UserFeedback:
        """Submit user feedback for a chat response"""
        
        feedback = UserFeedback(
            chat_id=chat_id,
            rating=rating,
            feedback_category=category,
            feedback_text=feedback_text,
            created_at=datetime.utcnow()
        )
        
        self.db.add(feedback)
        self.db.commit()
        
        return feedback
    
    def get_pending_reviews(
        self,
        limit: int = 50,
        include_thumbs_up: bool = False
    ) -> List[Dict[str, Any]]:
        """Get feedback items pending admin review"""
        
        query = self.db.query(UserFeedback, ChatHistory).join(
            ChatHistory, UserFeedback.chat_id == ChatHistory.id
        ).filter(
            UserFeedback.reviewed_at.is_(None)
        )
        
        if not include_thumbs_up:
            query = query.filter(UserFeedback.rating == FeedbackRating.THUMBS_DOWN)
        
        results = query.order_by(UserFeedback.created_at.desc()).limit(limit).all()
        
        return [
            {
                "feedback": feedback,
                "chat": chat,
                "question": chat.question,
                "sql": chat.generated_sql,
                "response": chat.ai_response
            }
            for feedback, chat in results
        ]
    
    def mark_as_golden_example(
        self,
        feedback_id: int,
        reviewer_id: int,
        category: str,
        review_notes: Optional[str] = None
    ):
        """Mark a chat as a golden example for few-shot learning"""
        
        feedback = self.db.query(UserFeedback).filter(
            UserFeedback.id == feedback_id
        ).first()
        
        if not feedback:
            raise ValueError("Feedback not found")
        
        # Update feedback
        feedback.reviewed_by = reviewer_id
        feedback.reviewed_at = datetime.utcnow()
        feedback.review_notes = review_notes
        feedback.is_golden_example = True
        
        # Get the chat
        chat = self.db.query(ChatHistory).filter(
            ChatHistory.id == feedback.chat_id
        ).first()
        
        # Create golden example
        import json
        sql_queries = json.loads(chat.generated_sql) if chat.generated_sql else []
        
        golden = GoldenExample(
            chat_id=chat.id,
            question_pattern=chat.question,
            expected_sql=sql_queries[0] if sql_queries else "",
            category=category,
            is_active=True,
            added_by=reviewer_id,
            created_at=datetime.utcnow()
        )
        
        self.db.add(golden)
        self.db.commit()
    
    def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics for dashboard"""
        
        since = datetime.utcnow() - timedelta(days=days)
        
        # Total counts
        total = self.db.query(func.count(UserFeedback.id)).filter(
            UserFeedback.created_at >= since
        ).scalar()
        
        thumbs_up = self.db.query(func.count(UserFeedback.id)).filter(
            UserFeedback.created_at >= since,
            UserFeedback.rating == FeedbackRating.THUMBS_UP
        ).scalar()
        
        thumbs_down = self.db.query(func.count(UserFeedback.id)).filter(
            UserFeedback.created_at >= since,
            UserFeedback.rating == FeedbackRating.THUMBS_DOWN
        ).scalar()
        
        # Category breakdown
        category_counts = self.db.query(
            UserFeedback.feedback_category,
            func.count(UserFeedback.id)
        ).filter(
            UserFeedback.created_at >= since,
            UserFeedback.feedback_category.isnot(None)
        ).group_by(UserFeedback.feedback_category).all()
        
        return {
            "total": total,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "satisfaction_rate": (thumbs_up / total * 100) if total > 0 else 0,
            "category_breakdown": {
                cat.value: count for cat, count in category_counts
            },
            "pending_reviews": self.db.query(func.count(UserFeedback.id)).filter(
                UserFeedback.reviewed_at.is_(None),
                UserFeedback.rating == FeedbackRating.THUMBS_DOWN
            ).scalar()
        }
```

**Feedback API Endpoints:**
```python
# app/api/v1/feedback.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.schemas.feedback import (
    FeedbackCreate, 
    FeedbackResponse, 
    FeedbackStatsResponse,
    FeedbackReviewRequest
)
from app.services.feedback_service import FeedbackService

router = APIRouter()

@router.post("/{chat_id}", response_model=FeedbackResponse)
async def submit_feedback(
    chat_id: int,
    feedback: FeedbackCreate,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for a chat response"""
    
    service = FeedbackService(db)
    
    result = service.submit_feedback(
        chat_id=chat_id,
        rating=feedback.rating,
        category=feedback.category,
        feedback_text=feedback.feedback_text
    )
    
    return result

@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    days: int = 30,
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get feedback statistics (admin only)"""
    
    service = FeedbackService(db)
    return service.get_feedback_stats(days)

@router.get("/pending-reviews")
async def get_pending_reviews(
    limit: int = 50,
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get feedback items pending review (admin only)"""
    
    service = FeedbackService(db)
    return service.get_pending_reviews(limit)

@router.post("/{feedback_id}/review")
async def review_feedback(
    feedback_id: int,
    review: FeedbackReviewRequest,
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Review feedback and optionally mark as golden example"""
    
    service = FeedbackService(db)
    
    if review.is_golden_example:
        service.mark_as_golden_example(
            feedback_id=feedback_id,
            reviewer_id=current_user.id,
            category=review.category,
            review_notes=review.notes
        )
    
    return {"status": "reviewed"}
```

### 3.5.2 Trending Queries

**Trending Service:**
```python
# app/services/trending_service.py
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.models.chat import ChatHistory
from app.models.trending import TrendingQuery

class TrendingService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_trending_queries(self, limit: int = 10) -> List[Dict]:
        """Get trending/popular queries"""
        
        return self.db.query(TrendingQuery).filter(
            TrendingQuery.is_featured == True
        ).order_by(
            TrendingQuery.usage_count_week.desc()
        ).limit(limit).all()
    
    def update_trending_stats(self):
        """Update trending statistics (called by Celery)"""
        
        today = datetime.utcnow().date()
        week_ago = today - timedelta(days=7)
        
        # Get popular query patterns from last week
        popular = self.db.query(
            ChatHistory.question,
            func.count(ChatHistory.id).label('count')
        ).filter(
            ChatHistory.created_at >= week_ago
        ).group_by(
            ChatHistory.question
        ).having(
            func.count(ChatHistory.id) >= 3  # At least 3 uses
        ).order_by(
            func.count(ChatHistory.id).desc()
        ).limit(20).all()
        
        # Update or create trending records
        for question, count in popular:
            existing = self.db.query(TrendingQuery).filter(
                TrendingQuery.query_pattern == question
            ).first()
            
            if existing:
                existing.usage_count_week = count
                existing.last_used_at = datetime.utcnow()
            else:
                new_trending = TrendingQuery(
                    query_pattern=question,
                    display_text=question[:100],
                    usage_count_week=count,
                    last_used_at=datetime.utcnow()
                )
                self.db.add(new_trending)
        
        self.db.commit()
```

### 3.5.3 Admin Review Dashboard

**Admin Dashboard Endpoints:**
```python
# app/api/v1/admin.py (extended)

@router.get("/review-dashboard")
async def get_review_dashboard(
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get admin review dashboard data"""
    
    feedback_service = FeedbackService(db)
    
    return {
        "feedback_stats": feedback_service.get_feedback_stats(30),
        "pending_reviews": feedback_service.get_pending_reviews(20),
        "slow_queries": get_slow_queries(db, threshold_ms=5000, limit=10),
        "empty_result_queries": get_empty_result_queries(db, limit=10),
        "prompt_versions": get_prompt_versions(db)
    }

def get_slow_queries(db: Session, threshold_ms: int, limit: int):
    """Get queries that took longer than threshold"""
    
    return db.query(ChatHistory).filter(
        ChatHistory.execution_time_ms > threshold_ms
    ).order_by(
        ChatHistory.created_at.desc()
    ).limit(limit).all()

def get_empty_result_queries(db: Session, limit: int):
    """Get queries that returned no results"""
    
    return db.query(ChatHistory).filter(
        ChatHistory.sql_result_summary.like('%0 rows%')
    ).order_by(
        ChatHistory.created_at.desc()
    ).limit(limit).all()
```

**Deliverables Phase 3.5:**
- [ ] User feedback submission (thumbs up/down)
- [ ] Feedback categories
- [ ] Admin review dashboard
- [ ] Golden example marking
- [ ] Prompt versioning
- [ ] Few-shot example loading
- [ ] Trending queries
- [ ] Request ID correlation in all logs
- [ ] PII redaction in logs

---

## Phase 4-6: (เนื้อหาเดิมคงไว้)

---

## Phase 7: Testing & Security Audit (2 สัปดาห์)

### 7.1 [NEW] Mock Claude API for Testing

**Mock Configuration:**
```python
# tests/conftest.py
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from anthropic.types import Message, ContentBlock, TextBlock, Usage

@pytest.fixture
def mock_claude_responses():
    """Load mock Claude responses from fixtures"""
    with open("tests/fixtures/claude_responses.json") as f:
        return json.load(f)

@pytest.fixture
def mock_claude_client(mock_claude_responses):
    """Mock Anthropic client for testing without API calls"""
    
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        
        # Mock messages.create
        def mock_create(**kwargs):
            # Determine response based on message content
            user_message = kwargs.get("messages", [{}])[-1].get("content", "")
            
            # Find matching mock response
            for pattern, response in mock_claude_responses.items():
                if pattern.lower() in user_message.lower():
                    return create_mock_message(response)
            
            # Default response
            return create_mock_message(mock_claude_responses.get("default", {}))
        
        mock_client.messages.create = Mock(side_effect=mock_create)
        
        yield mock_client

def create_mock_message(response_data: dict) -> Message:
    """Create mock Message object"""
    
    content = []
    
    # Add tool use if present
    if "tool_use" in response_data:
        tool_use = response_data["tool_use"]
        content.append(MagicMock(
            type="tool_use",
            id="test_tool_id",
            name=tool_use["name"],
            input=tool_use["input"]
        ))
    
    # Add text response
    if "text" in response_data:
        content.append(TextBlock(type="text", text=response_data["text"]))
    
    return Message(
        id="test_msg_id",
        type="message",
        role="assistant",
        content=content,
        model="claude-sonnet-4-20250514",
        stop_reason=response_data.get("stop_reason", "end_turn"),
        usage=Usage(
            input_tokens=response_data.get("input_tokens", 100),
            output_tokens=response_data.get("output_tokens", 200)
        )
    )
```

**Mock Responses Fixture:**
```json
// tests/fixtures/claude_responses.json
{
    "default": {
        "text": "ขออภัย ไม่สามารถตอบคำถามนี้ได้",
        "stop_reason": "end_turn",
        "input_tokens": 100,
        "output_tokens": 50
    },
    "รายได้รวม": {
        "tool_use": {
            "name": "execute_sql",
            "input": {
                "query": "SELECT SUM(REVENUE_VALUE) as total FROM EXPORT_NT_REVENUE_SUB_PRODUCT",
                "purpose": "Get total revenue"
            }
        },
        "stop_reason": "tool_use",
        "input_tokens": 500,
        "output_tokens": 100
    },
    "รายได้แยกตาม bu": {
        "tool_use": {
            "name": "execute_sql",
            "input": {
                "query": "SELECT BU, SUM(REVENUE_VALUE) as Revenue FROM EXPORT_NT_REVENUE_SUB_PRODUCT GROUP BY BU",
                "purpose": "Get revenue by BU"
            }
        },
        "stop_reason": "tool_use",
        "input_tokens": 500,
        "output_tokens": 150
    }
}
```

**Example Test with Mocked Claude:**
```python
# tests/unit/test_claude_service.py
import pytest
from app.services.claude_service import ClaudeRevenueAssistant

class TestClaudeService:
    
    @pytest.mark.asyncio
    async def test_chat_returns_response(self, mock_claude_client, mock_db_service):
        """Test that chat returns a proper response"""
        
        assistant = ClaudeRevenueAssistant(
            db_service=mock_db_service,
            cache_service=Mock(),
            cost_service=Mock(),
            audit_service=Mock()
        )
        
        result = await assistant.chat(
            user_id=1,
            message="รายได้รวมเดือนล่าสุด",
            session_id=1
        )
        
        assert "response" in result
        assert "sql_queries" in result
        assert "tokens_used" in result
        
        # Verify no real API calls were made
        # (mock would raise if called with unexpected args)
    
    @pytest.mark.asyncio
    async def test_chat_cost_tracking(self, mock_claude_client, mock_db_service):
        """Test that API costs are tracked"""
        
        cost_service = Mock()
        
        assistant = ClaudeRevenueAssistant(
            db_service=mock_db_service,
            cache_service=Mock(),
            cost_service=cost_service,
            audit_service=Mock()
        )
        
        await assistant.chat(
            user_id=1,
            message="รายได้รวม",
            session_id=1
        )
        
        # Verify cost was logged
        cost_service.log_usage.assert_called_once()
```

### 7.2 Testing Strategy (Updated)

| Category | Tools | Coverage Target | Notes |
|----------|-------|-----------------|-------|
| Unit Tests | pytest + mocks | 80%+ | **Mock Claude API** |
| Integration Tests | pytest + testcontainers | API endpoints | Use test DB |
| E2E Tests | Playwright | Critical flows | Staging environment |
| Load Tests | Locust | 100 concurrent | Mock Claude for cost |
| Security Tests | OWASP ZAP | OWASP Top 10 | Manual + automated |

---

## Phase 7.5: [NEW] Disaster Recovery Drill (0.5 สัปดาห์)

### 7.5.1 Backup Strategy

**Backup Configuration:**
```yaml
# docker/backup/backup-config.yml
backup:
  schedule:
    database:
      full: "0 2 * * *"           # Daily at 2 AM
      incremental: "0 */6 * * *"  # Every 6 hours
    files:
      minio: "0 3 * * *"          # Daily at 3 AM
  
  retention:
    database:
      daily: 7
      weekly: 4
      monthly: 12
    files:
      daily: 7
      weekly: 4
  
  storage:
    primary: /backup/primary
    offsite: s3://nt-backup-offsite/revenue-assistant
```

**Backup Script:**
```bash
#!/bin/bash
# scripts/backup.sh

set -e

BACKUP_DIR="/backup/$(date +%Y%m%d_%H%M%S)"
DB_NAME="nt_assistant"
MINIO_BUCKET="nt-assistant"

echo "Starting backup at $(date)"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# 1. Database backup
echo "Backing up PostgreSQL..."
pg_dump -h postgres -U nt_assistant -F c -f "$BACKUP_DIR/database.dump" $DB_NAME

# 2. Verify backup
echo "Verifying database backup..."
pg_restore --list "$BACKUP_DIR/database.dump" > /dev/null

# 3. MinIO backup
echo "Backing up MinIO files..."
mc mirror minio/$MINIO_BUCKET "$BACKUP_DIR/minio/"

# 4. Create checksum
echo "Creating checksums..."
sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/checksums.txt"

# 5. Compress
echo "Compressing backup..."
tar -czf "$BACKUP_DIR.tar.gz" -C "$(dirname $BACKUP_DIR)" "$(basename $BACKUP_DIR)"

# 6. Upload to offsite (optional)
if [ -n "$OFFSITE_BUCKET" ]; then
    echo "Uploading to offsite storage..."
    aws s3 cp "$BACKUP_DIR.tar.gz" "$OFFSITE_BUCKET/"
fi

# 7. Cleanup old backups
echo "Cleaning up old backups..."
find /backup -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed at $(date)"
echo "Backup location: $BACKUP_DIR.tar.gz"
```

**Restore Script:**
```bash
#!/bin/bash
# scripts/restore.sh

set -e

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

echo "WARNING: This will restore from backup and overwrite current data!"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

RESTORE_DIR="/tmp/restore_$(date +%s)"
mkdir -p "$RESTORE_DIR"

echo "Extracting backup..."
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

BACKUP_NAME=$(ls "$RESTORE_DIR")
BACKUP_PATH="$RESTORE_DIR/$BACKUP_NAME"

# Verify checksums
echo "Verifying checksums..."
cd "$BACKUP_PATH"
sha256sum -c checksums.txt

# Stop application
echo "Stopping application..."
docker-compose stop app telegram-bot celery-worker

# Restore database
echo "Restoring database..."
docker-compose exec -T postgres psql -U nt_assistant -c "DROP DATABASE IF EXISTS nt_assistant_old;"
docker-compose exec -T postgres psql -U nt_assistant -c "ALTER DATABASE nt_assistant RENAME TO nt_assistant_old;"
docker-compose exec -T postgres psql -U nt_assistant -c "CREATE DATABASE nt_assistant;"
docker-compose exec -T postgres pg_restore -U nt_assistant -d nt_assistant < "$BACKUP_PATH/database.dump"

# Restore MinIO
echo "Restoring MinIO files..."
mc mirror "$BACKUP_PATH/minio/" minio/nt-assistant/

# Start application
echo "Starting application..."
docker-compose start app telegram-bot celery-worker

# Health check
echo "Running health check..."
sleep 10
curl -f http://localhost:8000/health || echo "WARNING: Health check failed"

echo "Restore completed at $(date)"
echo "Old database preserved as 'nt_assistant_old'"
```

### 7.5.2 DR Drill Checklist

**Pre-Migration Backup Test:**
- [ ] Take full backup before migration
- [ ] Verify backup file integrity (checksum)
- [ ] Test restore to separate environment
- [ ] Verify data completeness after restore
- [ ] Document restore time

**DR Drill Steps:**
1. [ ] Schedule maintenance window
2. [ ] Notify stakeholders
3. [ ] Take fresh backup
4. [ ] Simulate failure (stop services)
5. [ ] Execute restore procedure
6. [ ] Verify application functionality
7. [ ] Verify data integrity
8. [ ] Document results and issues
9. [ ] Update runbook if needed

**Recovery Time Objectives:**
| Scenario | RTO | RPO |
|----------|-----|-----|
| Database corruption | 1 hour | 6 hours |
| Server failure | 2 hours | 6 hours |
| Complete site failure | 4 hours | 24 hours |

---

## Phase 8: Deployment & Go-Live (1 สัปดาห์)

### 8.1 [NEW] CI/CD Pipeline Details

**GitLab CI/CD Pipeline:**
```yaml
# .gitlab-ci.yml
stages:
  - lint
  - test
  - security
  - build
  - deploy-staging
  - integration-test
  - deploy-production

variables:
  DOCKER_IMAGE: registry.nt.co.th/revenue-assistant
  POSTGRES_DB: test_db
  POSTGRES_USER: test_user
  POSTGRES_PASSWORD: test_pass

# ==================== LINT ====================
lint:
  stage: lint
  image: python:3.11
  script:
    - pip install ruff black isort
    - ruff check app/
    - black --check app/
    - isort --check-only app/
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"

# ==================== TEST ====================
unit-test:
  stage: test
  image: python:3.11
  services:
    - postgres:15
    - redis:7-alpine
  variables:
    DATABASE_URL: postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB
    REDIS_URL: redis://redis:6379/0
  before_script:
    - pip install -r requirements.txt
    - pip install pytest pytest-cov pytest-asyncio
  script:
    - pytest tests/unit/ -v --cov=app --cov-report=xml --cov-report=html
  coverage: '/TOTAL.*\s+(\d+%)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
    paths:
      - htmlcov/
    expire_in: 1 week
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"

# ==================== SECURITY ====================
security-scan:
  stage: security
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - apk add --no-cache curl
    - curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
  script:
    # Build image first
    - docker build -t $DOCKER_IMAGE:$CI_COMMIT_SHA .
    # Scan for vulnerabilities
    - trivy image --exit-code 1 --severity HIGH,CRITICAL $DOCKER_IMAGE:$CI_COMMIT_SHA
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  allow_failure: true  # Don't block on first run, review results

dependency-check:
  stage: security
  image: python:3.11
  script:
    - pip install safety
    - safety check -r requirements.txt --full-report
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  allow_failure: true

# ==================== BUILD ====================
build:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $DOCKER_IMAGE:$CI_COMMIT_SHA -t $DOCKER_IMAGE:latest .
    - docker push $DOCKER_IMAGE:$CI_COMMIT_SHA
    - docker push $DOCKER_IMAGE:latest
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

# ==================== STAGING ====================
deploy-staging:
  stage: deploy-staging
  image: alpine:latest
  before_script:
    - apk add --no-cache openssh-client
    - eval $(ssh-agent -s)
    - echo "$STAGING_SSH_KEY" | ssh-add -
  script:
    - ssh -o StrictHostKeyChecking=no $STAGING_USER@$STAGING_HOST "
        cd /opt/revenue-assistant &&
        docker-compose pull &&
        docker-compose up -d &&
        sleep 10 &&
        curl -f http://localhost:8000/health
      "
  environment:
    name: staging
    url: https://staging-revenue.nt.co.th
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

integration-test:
  stage: integration-test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pip install pytest httpx
    - pytest tests/integration/ -v --staging-url=$STAGING_URL
  variables:
    STAGING_URL: https://staging-revenue.nt.co.th
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  needs:
    - deploy-staging

# ==================== PRODUCTION ====================
deploy-production:
  stage: deploy-production
  image: alpine:latest
  before_script:
    - apk add --no-cache openssh-client
    - eval $(ssh-agent -s)
    - echo "$PROD_SSH_KEY" | ssh-add -
  script:
    # Backup before deploy
    - ssh -o StrictHostKeyChecking=no $PROD_USER@$PROD_HOST "
        cd /opt/revenue-assistant &&
        ./scripts/backup.sh
      "
    # Deploy
    - ssh -o StrictHostKeyChecking=no $PROD_USER@$PROD_HOST "
        cd /opt/revenue-assistant &&
        docker-compose pull &&
        docker-compose up -d --no-deps app telegram-bot celery-worker &&
        sleep 15 &&
        curl -f http://localhost:8000/health
      "
  environment:
    name: production
    url: https://revenue.nt.co.th
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual  # Require manual approval
  needs:
    - integration-test
```

---

## 9. [NEW] Data Retention & Archival Policy

### 9.1 Retention Policy

| Data Type | Hot Storage | Cold Storage | Delete |
|-----------|-------------|--------------|--------|
| chat_history | 6 เดือน | 2 ปี | 5 ปี |
| audit_logs | 1 ปี | 7 ปี | 10 ปี |
| user_feedback | 1 ปี | 3 ปี | 5 ปี |
| generated_reports | 3 เดือน | 1 ปี | 2 ปี |
| api_usage_logs | 3 เดือน | 1 ปี | 2 ปี |
| user_sessions | 30 วัน | - | 90 วัน |

### 9.2 Archive Service

```python
# app/services/archive_service.py
import json
import gzip
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.chat import ChatHistory
from app.models.audit import AuditLog
from app.models.archive import DataArchive
from app.services.storage_service import StorageService
from app.config import settings

class ArchiveService:
    def __init__(self, db: Session, storage: StorageService):
        self.db = db
        self.storage = storage
    
    def archive_old_data(self, table: str, days_old: int) -> Dict:
        """Archive data older than specified days"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        if table == "chat_history":
            return self._archive_chat_history(cutoff_date)
        elif table == "audit_logs":
            return self._archive_audit_logs(cutoff_date)
        else:
            raise ValueError(f"Unknown table: {table}")
    
    def _archive_chat_history(self, cutoff_date: datetime) -> Dict:
        """Archive chat history to cold storage"""
        
        # Get records to archive
        records = self.db.query(ChatHistory).filter(
            ChatHistory.created_at < cutoff_date,
            ChatHistory.is_bookmarked == False  # Don't archive bookmarked
        ).limit(10000).all()
        
        if not records:
            return {"archived": 0}
        
        # Convert to JSON
        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "question": r.question,
                "generated_sql": r.generated_sql,
                "ai_response": r.ai_response,
                "tokens_used": r.tokens_used,
                "created_at": r.created_at.isoformat()
            }
            for r in records
        ]
        
        # Compress and upload
        json_data = json.dumps(data, ensure_ascii=False)
        compressed = gzip.compress(json_data.encode('utf-8'))
        
        # Generate archive filename
        date_range = f"{records[-1].created_at.date()}_to_{records[0].created_at.date()}"
        filename = f"archives/chat_history/{date_range}.json.gz"
        
        # Upload to cold storage
        file_path = self.storage.upload(filename, compressed)
        
        # Record archive metadata
        archive_record = DataArchive(
            source_table="chat_history",
            archive_file_path=file_path,
            record_count=len(records),
            date_range_start=records[-1].created_at,
            date_range_end=records[0].created_at,
            archived_at=datetime.utcnow(),
            file_size_bytes=len(compressed)
        )
        self.db.add(archive_record)
        
        # Delete archived records
        record_ids = [r.id for r in records]
        self.db.query(ChatHistory).filter(
            ChatHistory.id.in_(record_ids)
        ).delete(synchronize_session=False)
        
        self.db.commit()
        
        return {
            "archived": len(records),
            "file_path": file_path,
            "file_size_mb": len(compressed) / 1024 / 1024
        }
    
    def restore_from_archive(self, archive_id: int) -> Dict:
        """Restore data from archive (for audit/legal purposes)"""
        
        archive = self.db.query(DataArchive).filter(
            DataArchive.id == archive_id
        ).first()
        
        if not archive:
            raise ValueError("Archive not found")
        
        # Download and decompress
        compressed = self.storage.download(archive.archive_file_path)
        json_data = gzip.decompress(compressed).decode('utf-8')
        records = json.loads(json_data)
        
        return {
            "source_table": archive.source_table,
            "record_count": len(records),
            "date_range": f"{archive.date_range_start} to {archive.date_range_end}",
            "records": records  # Return for viewing, not restore to DB
        }
```

**Archive Worker (Celery):**
```python
# app/workers/archive_worker.py
from celery import Celery
from app.services.archive_service import ArchiveService
from app.config import settings

celery_app = Celery('tasks', broker=settings.REDIS_URL)

@celery_app.task
def run_daily_archive():
    """Run daily archival job"""
    
    archive_service = ArchiveService(...)
    
    results = {}
    
    # Archive chat_history older than 6 months
    results["chat_history"] = archive_service.archive_old_data(
        table="chat_history",
        days_old=180
    )
    
    # Archive audit_logs older than 1 year
    results["audit_logs"] = archive_service.archive_old_data(
        table="audit_logs",
        days_old=365
    )
    
    return results

# Schedule
celery_app.conf.beat_schedule['daily-archive'] = {
    'task': 'app.workers.archive_worker.run_daily_archive',
    'schedule': crontab(hour=4, minute=0),  # 4 AM daily
}
```

---

## 10. [NEW] Features for Future Consideration

### Features ที่ไม่จำเป็นในตอนนี้ แต่ควรพิจารณาเมื่อ:

| Feature | ควรทำเมื่อ | เหตุผล |
|---------|-----------|--------|
| **OpenTelemetry/Jaeger (Distributed Tracing)** | มี services > 10 ตัว หรือ debug ยากขึ้น | ระบบปัจจุบันมี 4-5 services ใช้ request_id correlation เพียงพอ |
| **Terraform/Ansible (IaC)** | ย้ายไป cloud หรือต้อง provision servers บ่อย | ถ้าใช้ on-premise servers ที่มีอยู่ manual setup ก็พอ |
| **HashiCorp Vault (Secrets Manager)** | มี secrets > 20 ตัว หรือต้อง rotate บ่อย | Docker secrets + .env file ยังจัดการได้ |
| **Read Replica for PostgreSQL** | Users > 500 หรือ reports ทำให้ chat ช้า | ดู load จริงก่อน ค่อยเพิ่ม |
| **A/B Testing for Prompts** | มี users > 100 และต้องการ optimize prompt | ระยะแรกใช้ manual review + golden examples |
| **Real-time Dashboard (WebSocket)** | Users ต้องการ live data refresh < 1 นาที | Polling ทุก 1-5 นาทีน่าจะเพียงพอ |
| **Multi-language Support** | มี users ที่ไม่ใช้ภาษาไทย | ปัจจุบัน users เป็นคนไทยทั้งหมด |
| **Mobile App (Native)** | Users ต้องการ offline หรือ push notifications | Web app + Telegram ครอบคลุมแล้ว |

---

## 11. Cost Estimation (Updated)

### 11.1 Infrastructure Costs (Monthly)

| Item | Specification | Est. Cost (THB) |
|------|---------------|-----------------|
| App Servers (2x) | 4 vCPU, 8GB RAM | 6,000 |
| Database Server | 4 vCPU, 16GB RAM | 5,000 |
| Redis | 2 vCPU, 4GB RAM | 2,000 |
| MinIO Storage | 100GB + Archive 200GB | 1,000 |
| Backup Storage | 100GB | 500 |
| SSL Certificate | Wildcard | 250/month |
| **Total Infrastructure** | | **~15,000/month** |

### 11.2 Development Costs (Updated)

| Phase | Duration | Resources | Est. Cost (THB) |
|-------|----------|-----------|-----------------|
| Phase 1-2 | 5 weeks | 2 developers | 250,000 |
| Phase 3-3.5 | 4 weeks | 2 developers | 200,000 |
| Phase 4-6 | 6 weeks | 2 developers | 300,000 |
| Phase 7-8 | 4 weeks | 2 devs + 1 QA | 250,000 |
| **Total Development** | **19 weeks** | | **~1,000,000** |

---

## 12. Summary of Changes in v2.0

| Section | Change Type | Description |
|---------|-------------|-------------|
| Architecture | Enhanced | เพิ่ม Feedback Service, Prompt Manager, Archive Service |
| Database Schema | Enhanced | เพิ่ม user_feedback, golden_examples, prompt_versions, data_archives, trending_queries |
| Phase 3.5 | **NEW** | Feedback Loop & Enhanced Logging |
| Phase 7.5 | **NEW** | DR Drill & Backup Test |
| Logging | **NEW** | Request ID correlation, PII redaction |
| Testing | Enhanced | Mock Claude API for cost-effective testing |
| CI/CD | **NEW** | Detailed pipeline with security scanning |
| Data Retention | **NEW** | Archive policy & automated archival |
| WAF | **NEW** | NGINX rate limiting by path |
| Future Features | **NEW** | Documented what to add and when |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-23 | Claude | Initial version |
| 2.0 | 2025-01-23 | Claude | Added feedback loop, DR, logging, CI/CD details |

---

**Prepared for:** NT (National Telecom) - Finance Department  
**Project:** NT Revenue Assistant  
**Classification:** Internal Use Only

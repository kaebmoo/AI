# NT AI Assistant

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้และยอดขายของหน่วยงาน ผ่าน Web Application (React Native) และ API Backend (FastAPI) โดยใช้ GenAI (Claude/Gemini) เป็นตัวประมวลผลคำถามและสร้าง SQL Query อัตโนมัติ

## Project Status

**Phase:** 4.0 (Universal Frontend - In Progress)
**Current Version:** 0.3.5-beta

## Features Implemented

- **Project Structure:** FastAPI standard layout
- **Frontend:** React Native (Expo) supporting Web, Android, iOS
- **Database:** SQLAlchemy setup (SQLite/PostgreSQL/MSSQL support)
- **Authentication:**
  - Email OTP (Limited to configured domains e.g. `ntplc.co.th`)
  - Session Management (Token-based)
- **Services:**
  - **AI Service (Core):**
    - Support for **Claude 3.5 Sonnet**, **Gemini 2.0 Flash**, and **Matcha (OpenAI Compatible)**
    - **Self-Correcting Logic:** Implements an Agentic Loop (Generate → Validate → Execute → Self-Correct) to handle SQL errors and zero-result queries automatically.
    - **Dynamic SQL Generation:** Auto-detects DB engine (SQLite/Postgres/MSSQL) and adjusts syntax rules.
    - **Multi-Context Architecture (New):**
      - Supports multiple data contexts (Revenue, Expense, etc.) with dynamic schema loading.
      - **Context Router:** Automatically routes user questions to the correct context (e.g., "ค่าใช้จ่าย" -> Expense, "ยอดขาย" -> Revenue).
      - **Data Marts:** Uses simplified views (e.g., `v_expense_mart`) to provide English-friendly schemas for AI.
    - **Metadata-Driven Architecture:**
      - **Dynamic Context:** Builds system prompts from database metadata (`schema_metadata`) rather than hardcoded text.
      - **Semantic Mapping:** Maps user terms (e.g., "นป.", "อสังหา") to SQL conditions via `schema_semantic_mapping`.
      - **Business Rules:** Admin-configurable constraints via `schema_business_rules`.
  - **Admin Management:**
    - Full CRUD API for managing schema metadata, mappings, and rules without code deployment.
    - **Web Admin Interface:**
      - Built with React + Ant Design (TypeScript).
      - Visual management for Users, Schemas, Rules, and Golden Examples.
      - **Context Management:** Create and edit data contexts (Revenue, Expense) and manage routing keywords.
      - Schema Analyzer tool for importing and verifying metadata from Excel/CSV (Backend ready).
  - **Task Queue:** Celery + Redis for async tasks (Email, Long-running queries)
- **Feedback System:**
  - Collect user feedback (Thumbs Up/Down)
  - Admin Dashboard for reviewing AI performance

## Requirements

- Python 3.10+
- Node.js 18+ (for Frontend)
- Redis (for Celery Task Queue)
- Database: SQLite (Default/Dev) or PostgreSQL/MSSQL (Production)

---

## 🚀 Quick Start Guide

### 1. Backend Setup

```bash
# 1. Clone & Enter Directory
git clone <repository_url>
cd nt-revenue-assistant

# 2. Create Virtual Environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install Python Dependencies
pip install -r requirements.txt

# 4. Configuration
# Copy .env.example to .env (if available) or create one:
echo "DATABASE_URL=sqlite:///./nt_fi_report.sqlite" > .env
echo "AI_PROVIDER=gemini" >> .env  # or 'claude'
echo "GOOGLE_AI_API_KEY=your_gemini_key" >> .env
# echo "ANTHROPIC_API_KEY=your_claude_key" >> .env

# 5. Initialize Database & Rules
python scripts/init_db.py         # Create tables
python scripts/setup_rules_db.py  # Inject business rules & abbreviations
```

### 2. Frontend Setup

```bash
# Open a new terminal
cd frontend

# Install Dependencies
npm install

# Run Web Interface
npm run web
# Or run on device:
# npm run android
# npm run ios
```

### 3. Admin Web UI Setup

```bash
cd frontend-admin

# Install Dependencies
npm install

# Run Admin Interface
npm run dev
```

### 4. Start Services

You need to run these 4 processes in parallel (separate terminals):

**Terminal 1: Backend API**
```bash
# Make sure venv is activated
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2: Celery Worker (Async Tasks)**
```bash
# Make sure venv is activated and Redis is running
celery -A app.celery worker -Q email-queue,celery --loglevel=info
```

**Terminal 3: User Frontend (Expo)**
```bash
cd frontend
npm run web
```

**Terminal 4: Admin Web UI**
```bash
cd frontend-admin
npm run dev
```

---

## API Documentation

Once the backend is running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Development Layout

- `app/api`: API route handlers
- `app/services`: Business logic (AI, Auth, Schema, Email)
- `app/config.py`: Application configuration settings
- `frontend/`: React Native / Expo application
- `scripts/`: Utility scripts for maintenance and testing
    - `verify_dynamic_rules.py`: Test SQL syntax generation for different DBs
    - `verify_sql_syntax.py`: Test actual DB query execution
    - `setup_rules_db.py`: Manage business rules

## Testing

- **Verify AI SQL Generation:**
  ```bash
  python scripts/verify_sql_syntax.py
  ```
- **Test Filtering Rules:**
  ```bash
  python scripts/test_filtering_rules.py
  ```

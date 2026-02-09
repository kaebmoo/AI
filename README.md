# NT AI Assistant

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้ ยอดขาย ค่าใช้จ่าย และข้อมูลทางการเงิน ของหน่วยงาน ผ่าน Web Application (React Native) และ API Backend (FastAPI) โดยใช้ GenAI (Claude/Gemini/Matcha) เป็นตัวประมวลผลคำถามและสร้าง SQL Query อัตโนมัติ

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
    - **Dynamic Provider Management (New):**
      - **Admin-Controlled Model Selection:** Enable/disable AI providers through Admin UI
      - **Multi-Model Support:** Switch between different models per provider (e.g., claude-sonnet, gpt-4o, gemini-flash)
      - **Fallback Configuration:** 3-tier config system (Database → .env → Hardcoded defaults)
      - **User Model Selector:** Frontend dynamically loads only enabled providers from backend
    - **Self-Correcting Logic:** Implements an Agentic Loop (Generate → Validate → Execute → Self-Correct) to handle SQL errors and zero-result queries automatically.
    - **Dynamic SQL Generation:** Auto-detects DB engine (SQLite/Postgres/MSSQL) and adjusts syntax rules.
    - **Multi-Context Architecture:**
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
      - **Settings Panel (New):**
        - **AI Provider Configuration:** Enable/disable providers (Claude, Gemini, Matcha), select default provider
        - **Model Management:** Choose models for each provider, configure API URLs
        - **Feature Flags:** Toggle RAG, auto-context detection, debug mode, query logging
        - **Cache Management:** Clear configuration cache without server restart
      - Schema Analyzer tool for importing and verifying metadata from Excel/CSV (Backend ready).
  - **User App (Frontend):**
    - Built with **React Native (Expo)** for Web, iOS, and Android.
    - **Smart Visualization:** Auto-selects best chart type (Line/Bar/Grouped) based on data shape.
    - **Interactive Reports:** Drill-down tooltips, responsive data tables, and rich markdown support.
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
echo "AI_PROVIDER=matcha" >> .env  # Default: matcha (or 'claude', 'gemini')
echo "GOOGLE_AI_API_KEY=your_gemini_key" >> .env
echo "ANTHROPIC_API_KEY=your_claude_key" >> .env
echo "MATCHA_AI_API_KEY=your_matcha_key" >> .env
echo "MATCHA_API_URL=https://aigateway.ntictsolution.com/v1/chat/completions" >> .env

# 5. Initialize Database & Metadata
python scripts/init_db.py         # Create tables
python scripts/setup_rules_db.py  # Inject business rules & abbreviations

# 6. Run Database Migrations (includes admin_config table)
sqlite3 nt_fi_report.sqlite < database/migrations/004_admin_config.sql
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

## Documentation

### API Documentation

Once the backend is running, visit:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Project Documentation

- **[Admin Configuration System](docs/ADMIN_CONFIGURATION.md)** - Complete guide for AI provider management
- **[Data Dictionary](docs/DATA_DICTIONARY.md)** - Database schema reference
- **[CLAUDE.md](CLAUDE.md)** - Instructions for AI coding assistants

## Development Layout

- `app/api`: API route handlers
- `app/services`: Business logic (AI, Auth, Schema, Email, Admin Config)
- `app/config.py`: Application configuration settings
- `frontend/`: React Native / Expo application
- `frontend-admin/`: Admin Web UI (React + Ant Design)
- `database/migrations/`: Database migration scripts
- `docs/`: Documentation
  - `ADMIN_CONFIGURATION.md`: Admin config system guide
  - `DATA_DICTIONARY.md`: Schema documentation
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

---

## Admin Configuration System

### Overview

The system supports **dynamic AI provider management** through a 3-tier configuration mechanism:

```
Priority 1: Database (admin_config table)  ← Admin can change via Web UI
          ↓ (if not found)
Priority 2: .env file                      ← Developer/deployment config
          ↓ (if not found)
Priority 3: Hardcoded defaults             ← Fallback safety net
```

### Configuration Tables

**`admin_config` table:**
- Stores AI provider settings (default provider, enabled status, models)
- Feature flags (RAG, auto-context detection, debug mode)
- API keys and URLs (masked in UI)
- Hot-reloadable without server restart

**`schema_contexts` table:**
- Multiple data contexts (Revenue, Expense, Transfer Price, etc.)
- Context routing keywords for auto-detection
- Custom AI instructions per context

### Admin Settings UI

Access at: `http://localhost:5173/settings` (Admin login required)

**Features:**
1. **AI Provider Management**
   - Enable/disable providers (Claude, Gemini, Matcha)
   - Select default provider
   - Choose models per provider
   - Configure Matcha API gateway URL

2. **Model Selection**
   - Claude: claude-sonnet-4-5, claude-opus-4, claude-haiku-3-5
   - Gemini: gemini-3-flash, gemini-2.0-flash-exp, gemini-1.5-pro
   - Matcha: gpt-4.1, gpt-4o, gpt-4-turbo, gpt-3.5-turbo

3. **Feature Flags**
   - RAG Enabled: Toggle Retrieval-Augmented Generation
   - Auto Context Detection: Automatically route questions to correct context
   - Debug Mode: Show detailed debug info in responses
   - Log Queries: Save all generated SQL to database
   - Collect Feedback: Enable user feedback collection

4. **Cache Management**
   - Clear configuration cache
   - Refresh metadata without restart

### User Experience

**Dynamic Model Selector:**
- Frontend `ModelSelector` component fetches active providers from API
- Users only see providers that admin has enabled
- If a provider is disabled in admin, it disappears from user interface
- Default provider is auto-selected on page load

**API Endpoints:**
```
GET  /api/v1/admin/config/ai/providers          # Public: Get active providers
GET  /api/v1/admin/config/ai                    # Admin: Get full config
PUT  /api/v1/admin/config/ai                    # Admin: Update config
GET  /api/v1/admin/config/features              # Admin: Get feature flags
POST /api/v1/admin/config/features/{name}/toggle # Admin: Toggle feature
```

### Configuration Files

**Backend:**
- `app/services/admin_config_service.py` - Config service with fallback logic
- `app/api/v1/admin.py` - Admin API endpoints
- `database/migrations/004_admin_config.sql` - Migration script

**Frontend:**
- `frontend/components/Chat/ModelSelector.tsx` - Dynamic model selector
- `frontend/services/adminService.ts` - Admin API client
- `frontend-admin/src/pages/Settings.tsx` - Settings UI (Ant Design)

### Example: Changing Default Provider

**Via Admin UI:**
1. Login to admin panel: `http://localhost:5173/`
2. Go to Settings
3. Select "Matcha" as default provider
4. Click "Save Configuration"
5. Users will now see Matcha selected by default in chat interface

**Via .env (fallback):**
```env
AI_PROVIDER=matcha  # Default if not set in database
```

**Via Database:**
```sql
UPDATE admin_config
SET config_value = 'matcha'
WHERE config_key = 'default_ai_provider';
```

---

# NT AI Assistant

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้ ยอดขาย ค่าใช้จ่าย และข้อมูลทางการเงิน ของหน่วยงาน ผ่าน Web Application (React Native) และ API Backend (FastAPI) โดยใช้ GenAI (Claude/Gemini/Matcha) เป็นตัวประมวลผลคำถามและสร้าง SQL Query อัตโนมัติ

## Project Status

**Phase:** 5.0 (Plans 0-5 Complete)
**Current Version:** 0.5.0
**Tests:** 359 passing (0 failures)

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

## Plans 0-5 Implementation (2026-03-19) — All Complete

### Plan 0: Fix Legacy Tests
- Fixed 15 pre-existing test failures, baseline 279 tests passing

### Plan 1: Admin Agent (Tool-Calling Dispatcher)
- **Natural language admin interface** — type Thai/English commands to manage system config
- 14 admin tools: mappings, rules, examples, hierarchy, onboarding, analysis
- Native function calling (OpenAI tool_choice='auto') with keyword fallback
- Confirmation flow for destructive operations
- Tool result summarization via LLM in Thai
- Frontend: `http://localhost:5173/admin-agent`
- See: [Admin Agent Manual](docs/manuals/manual_admin_agent.md)

### Plan 1B: Validation Consolidation + Admin MCP
- Centralized `ValidationService` (validate_sql, check_business_rules, calculate_confidence)
- 7 built-in validation rules seeded to DB
- Admin MCP server (`mcp_servers/nt_admin_mcp.py`) — 13 MCP tools wrapping admin tools

### Plan 2: Feedback + Query Log Enhancement
- Enhanced query logs with feedback join and filters
- Query analytics endpoint (period, error_rate, context distribution)
- Feedback detail view

### Plan 3: Self-Learning Loop
- **DedupEngine:** duplicate detection (exact, case-insensitive, conflict)
- **AutoAnalyzer:** analyzes failed queries, suggests fixes
- **ConfigGC:** finds unused mappings, conflicting entries, low-usage examples
- **AuditService:** records config changes with source tracking

### Plan 4: Telegram Interface
- Full Telegram bot with email OTP registration
- Free-text queries with table + chart (PNG) responses
- Admin commands routed to Admin Agent
- Message splitting (4096 char limit), Thai font charts
- See: [Telegram Bot Manual](docs/manuals/manual_telegram_bot.md)

### Plan 4B: OpenMiniCrew Readiness (API Keys + /query/ Endpoint)
- **API Key management:** create, validate, revoke, rate limiting
- **Stateless query endpoint:** `POST /api/v1/query/` — question in, answer out
- **X-API-Key authentication** with scoped access (query/admin/full)
- Frontend: `http://localhost:5173/api-keys`
- See: [API Keys Manual](docs/manuals/manual_api_keys.md)

### Plan 5: DB Separation
- `BusinessDBAdapter` for SQLite/PostgreSQL/MSSQL
- Migration script to separate config tables from business data

## Architecture Overview

```
app/
├── providers/           # AI providers (auto-discovered by registry)
│   ├── base.py          # AIProvider ABC, QueryResult
│   ├── claude_provider.py
│   ├── gemini_provider.py
│   ├── matcha_provider.py
│   ├── chart_postprocessor.py
│   └── registry.py      # provider_registry singleton
├── services/
│   ├── ai_service.py         # AIService orchestrator
│   ├── query_engine.py       # Main entry + result cache + dedup
│   ├── schema_service.py     # Schema metadata + system prompt cache
│   ├── admin_agent.py        # Admin Agent dispatcher
│   ├── validation_service.py # SQL validation
│   ├── dedup_engine.py       # Duplicate detection
│   ├── auto_analyzer.py      # Failed query analysis
│   ├── config_gc.py          # Config garbage collection
│   ├── audit_service.py      # Change audit trail
│   ├── api_key_service.py    # API key management
│   ├── business_db.py        # Multi-DB adapter
│   └── ...
├── api/v1/
│   ├── chat.py          # Main chat + SSE streaming
│   ├── admin.py         # Admin CRUD endpoints
│   ├── admin_agent.py   # Admin Agent chat API
│   └── query.py         # Stateless query API (API key auth)
├── tools/admin/         # Admin tools (14 tools)
├── telegram/            # Telegram bot
│   ├── bot.py           # Bot initialization
│   ├── dispatcher.py    # Command routing
│   ├── handlers.py      # Command handlers
│   ├── formatters.py    # Message formatting
│   ├── auth.py          # Email OTP auth
│   └── chart_renderer.py # matplotlib charts
└── config.py
mcp_servers/
├── nt_metadata_mcp.py   # Schema metadata MCP
├── nt_query_mcp.py      # Query execution MCP
├── nt_validation_mcp.py # SQL validation MCP
└── nt_admin_mcp.py      # Admin tools MCP
```

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

### Manuals

- **[Admin Agent Manual](docs/manuals/manual_admin_agent.md)** - Chat-based admin interface
- **[API Keys Manual](docs/manuals/manual_api_keys.md)** - API key management + /query/ endpoint
- **[Telegram Bot Manual](docs/manuals/manual_telegram_bot.md)** - Telegram bot setup and usage
- **[Context Onboarding Manual](docs/manuals/manual_context_onboarding.md)** - Auto-configure new data contexts
- **[Web Admin Manual](docs/manuals/manual_web_admin_comprehensive.md)** - Full admin UI guide

### Changelogs

- **[Plans 0-5 Implementation](docs/changelogs/PLANS_0_5_IMPLEMENTATION.md)** - 2026-03-19, all plans complete
- **[Context Onboarding System](docs/changelogs/CONTEXT_ONBOARDING_SYSTEM.md)** - Auto-analysis pipeline
- **[DB-Driven Hardcode Removal](docs/changelogs/DB_DRIVEN_HARDCODE_REMOVAL.md)** - 6-phase cleanup
- **[Master Data Hierarchy](docs/changelogs/MASTER_DATA_HIERARCHY.md)** - DB-driven hierarchy system

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

**Run all tests:**
```bash
pytest tests/ -v
```

**Current:** 359 tests passing (0 failures)

- **Unit tests:** `tests/unit/` — 25+ test files covering all services
- **Integration tests:** `tests/integration/` — API endpoint tests

**Verify AI SQL Generation:**
```bash
python scripts/verify_sql_syntax.py
```

**Test Filtering Rules:**
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

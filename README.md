# NT Revenue Assistant

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้และยอดขายของหน่วยงาน ผ่าน Web Application และ Telegram Bot โดยใช้ Claude AI เป็นตัวประมวลผลคำถามและสร้าง SQL Query

## Project Status

**Phase:** 3.5 (Core Features & Feedback Loop)
**Current Version:** 0.3.0-beta

## Features Implemented

- **Project Structure:** FastAPI standard layout
- **Database:** SQLAlchemy setup (SQLite/PostgreSQL support)
- **Authentication:**
  - Email OTP (Limited to configured domains e.g. `example.com`)`)
  - Session Management (Token-based)
  - Login & Verify API Endpoints
- **Services:**
  - OTP Service (using `pyotp`)
  - Email Service (using `aiosmtplib` + `jinja2`)
  - **AI Service (Core):**
    - Support for **Claude** and **Gemini** models
    - **Multi-turn Chat:** Context-aware conversations
    - **Tool Use:** Auto-generates and executes SQL
    - **Robustness:** Automatic retry mechanism for API failures
  - **Schema & Rules:**
    - `revenue_search` View for clean English schema
    - **Flexible Business Rules:** Admin-configurable SQL constraints via `schema_business_rules` table
  - **Feedback System:**
    - Collect user feedback (Thumbs Up/Down, Categories)
    - **Admin Dashboard:** Stats, Pending Reviews, Trending Queries
    - **Golden Examples:** Auto-learning from reviewed feedback

## Requirements

- Python 3.9+
- PostgreSQL (Production) / SQLite (Dev)
- Redis

## Setup & Installation

1. **Clone the repository**

   ```bash
   git clone <repository_url>
   cd nt-revenue-assistant
   ```
2. **Create Virtual Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```
4. **Configuration**
   Create a `.env` file (or rely on defaults in `app/config.py` for dev):

   ```env
   DATABASE_URL=sqlite:///./nt_revenue.db
   SMTP_HOST=mock  # Use 'mock' to log emails to console instead of sending
   ```
5. **Initialize Database**

   ```bash
   python scripts/init_db.py
   ```
6. **Run Application**

   ```bash
   uvicorn app.main:app --reload
   ```

## API Documentation

Once running, visit:

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## Development Layout

- `app/api`: API route handlers
- `app/core`: Core config, logging, exceptions
- `app/services`: Business logic (Auth, OTP, Email)
- `app/models`: Database models
- `app/schemas`: Pydantic models
- `scripts/`: Utility scripts

## Testing

- Run auth flow test: `python scripts/test_auth_flow.py`
- Run multi-turn chat test: `python scripts/test_multiturn_chat.py`
- Run filtering rules test: `python scripts/test_filtering_rules.py`

---

*Last Updated: 2026-01-27*

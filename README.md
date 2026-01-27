# NT Revenue Assistant

โครงการพัฒนาระบบ AI Assistant สำหรับสอบถามข้อมูลรายได้และยอดขายของหน่วยงาน ผ่าน Web Application และ Telegram Bot โดยใช้ Claude AI เป็นตัวประมวลผลคำถามและสร้าง SQL Query

## Project Status

**Phase:** 2 (Authentication & Security)
**Current Version:** 0.1.0-alpha

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

---

*Last Updated: 2026-01-26*

# Plan 4B: AI Assistant Readiness สำหรับ OpenMiniCrew Integration

**Priority:** ทำคู่กับ Plan 4 (Telegram) หรือก่อนก็ได้  
**ประมาณเวลา:** 2-3 วัน  
**Prerequisite:** ไม่มี (standalone)  
**อ้างอิงโดย:** Plan 4 (Telegram), Plan 6 (SaaS — API key auth ใช้ร่วมกัน)

---

## 1. สถานการณ์ปัจจุบัน

### AI Assistant ฝั่ง API

- **Auth:** Session token เท่านั้น (X-Session-Token header หรือ Bearer token)
  - ได้จาก OTP email verification หรือ password login
  - ไม่มี API key auth → external service เรียกไม่ได้โดยตรง
- **Chat endpoint:** `POST /api/v1/chat/` — รับ `ChatRequest`, คืน `ChatResponse` ที่มี chart_config, visualization, display_hint ฯลฯ (ซับซ้อนเกินสำหรับ Telegram bot)
- **SSE endpoint:** `POST /api/v1/chat/stream` — streaming response
- **Contexts:** `GET /api/v1/chat/contexts` — list available contexts

### OpenMiniCrew ฝั่ง Tool

- Tool ต้อง implement `BaseTool` → `async execute(user_id, args, **kwargs) -> str`
- Tool เรียก external API ผ่าน `requests` หรือ `httpx`
- ต้อง return string (ไม่ใช่ JSON complex object)
- User ใช้ผ่าน Telegram → ได้แค่ text + รูป (ไม่มี HTML/chart rendering)

### Gap ที่ต้องปิด

| Gap | รายละเอียด | แก้ที่ไหน |
|-----|-----------|----------|
| **Auth** | OpenMiniCrew ไม่สามารถ login OTP ได้ | AI Assistant: เพิ่ม API key auth |
| **Response format** | ChatResponse ซับซ้อน (chart_config, visualization) | AI Assistant: เพิ่ม simplified endpoint |
| **User mapping** | OpenMiniCrew user_id (Telegram chat_id) ≠ AI Assistant user_id (DB int) | AI Assistant: map telegram_chat_id → user |
| **Context** | OpenMiniCrew ไม่รู้ว่า AI Assistant มี contexts อะไร | AI Assistant: public context list endpoint |
| **Rate limit** | ไม่มี per-API-key rate limit | AI Assistant: เพิ่ม |
| **Error format** | AI Assistant error → HTTPException detail string | ต้อง consistent |

## 2. สิ่งที่ AI Assistant ต้องเตรียม

### 2.1 API Key Authentication (สำคัญสุด)

**เพิ่ม auth method ใหม่** ที่ใช้ API key แทน session token สำหรับ external services:

```python
# app/models/api_key.py (NEW)

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True)
    key_hash = Column(String, unique=True, nullable=False)  # SHA-256 hash
    key_prefix = Column(String(8), nullable=False)  # แสดง "ntai_<prefix>..." สำหรับ identify
    name = Column(String, nullable=False)  # "OpenMiniCrew Bot", "Telegram Gateway"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # owner
    
    # Permissions
    scopes = Column(String, default="query")  # query, admin, full
    
    # Limits
    rate_limit_per_minute = Column(Integer, default=30)
    rate_limit_per_day = Column(Integer, default=1000)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # None = never expires
    
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Auth flow:**

```
OpenMiniCrew → POST /api/v1/chat/
               Header: X-API-Key: <API_KEY>
                       │
                       ▼
AI Assistant deps.py:
  1. ดึง X-API-Key header
  2. Hash key → lookup ใน api_keys table
  3. ตรวจ: is_active, expires_at, rate limit
  4. Return user ที่เป็น owner ของ key
  5. Request proceeds as that user
```

**แก้ไขใน `app/api/deps.py`:**

```python
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(header_scheme),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),  # NEW
    db: Session = Depends(get_db)
) -> User:
    # 1. Try API key first (for external services)
    if api_key:
        return _authenticate_api_key(api_key, db)
    
    # 2. Try session token (for web UI)
    final_token = token or bearer_token
    ...existing logic...
```

### 2.2 Simplified Query Endpoint

**ปัญหา:** `POST /api/v1/chat/` คืน response ที่มี chart_config, visualization, display_hint, hierarchy_columns, confidence, retry_history ฯลฯ — OpenMiniCrew ต้องการแค่ text answer + data table

**เพิ่ม endpoint ใหม่:** `POST /api/v1/query`

```python
# app/api/v1/query.py (NEW)

@router.post("/", response_model=SimpleQueryResponse)
async def simple_query(
    request: SimpleQueryRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """
    Simplified query endpoint for external services.
    Returns plain text answer + optional data table.
    No chart_config, no visualization, no streaming.
    """
    ...
```

**Request:**
```python
class SimpleQueryRequest(BaseModel):
    question: str
    context: Optional[str] = None  # auto-detect if not specified
    provider: Optional[str] = None
    format: str = "text"  # text, json, markdown
    include_sql: bool = False
    include_data: bool = False  # True = include raw data rows
    max_rows: int = 20  # limit data rows returned
```

**Response:**
```python
class SimpleQueryResponse(BaseModel):
    answer: str  # plain text explanation (Thai)
    context: str  # which context was used
    sql: Optional[str] = None  # only if include_sql=True
    data: Optional[List[Dict]] = None  # only if include_data=True
    row_count: Optional[int] = None
    execution_time_ms: float = 0
    error: Optional[str] = None
```

**ทำไมต้อง endpoint ใหม่:**
- `/chat/` ผูกกับ conversation_id, session management, chart rendering — ไม่จำเป็นสำหรับ bot
- `/query` ไม่สร้าง conversation, ไม่เก็บ chart session, response เรียบง่าย
- ลด overhead: ไม่ต้อง intent classification สำหรับ chart-only requests
- ง่ายต่อ external integration ทุกรูปแบบ (ไม่เฉพาะ OpenMiniCrew)

### 2.3 Public Context List (ไม่ต้อง auth)

**ปัจจุบัน:** `GET /api/v1/chat/contexts` ต้อง login

**เพิ่ม:** public endpoint ที่ list contexts ได้โดยไม่ต้อง auth (หรือใช้ API key scope "query")

```python
@router.get("/contexts")
def list_contexts():
    """Public: list available data contexts"""
    return [
        {"name": "revenue", "display_name": "รายได้", "description": "..."},
        {"name": "expense", "display_name": "ค่าใช้จ่าย", "description": "..."},
        ...
    ]
```

### 2.4 User Mapping: Telegram chat_id → AI Assistant user

**ปัญหา:** OpenMiniCrew ส่ง `user_id` เป็น Telegram chat_id (string) แต่ AI Assistant ใช้ user_id เป็น DB integer

**วิธี 1 (แนะนำ): API key เป็น proxy auth**
- Admin สร้าง API key สำหรับ OpenMiniCrew bot
- API key link กับ AI Assistant user (เจ้าของ bot)
- ทุก query ผ่าน API key → เป็น user คนเดียว
- เหมาะกับ single-user / small team

**วิธี 2: Per-user API key (multi-user)**
- ผู้ใช้แต่ละคน register ผ่าน `/start` ใน Telegram (Plan 4)
- ระบบ map telegram_chat_id → AI Assistant user
- OpenMiniCrew ส่ง `telegram_chat_id` ใน request header
- AI Assistant lookup user จาก telegram_chat_id

```python
class SimpleQueryRequest(BaseModel):
    question: str
    context: Optional[str] = None
    telegram_chat_id: Optional[str] = None  # สำหรับ multi-user mapping
```

**วิธี 3: Service account + impersonation**
- API key มี scope "service" → ส่ง `on_behalf_of` user_id ได้
- เหมาะกับ SaaS (Plan 6)

### 2.5 API Key Management (Admin)

**Endpoints ใหม่:**

```
POST   /api/v1/admin/api-keys          สร้าง API key
GET    /api/v1/admin/api-keys          list API keys ของ user
DELETE /api/v1/admin/api-keys/{key_id}  revoke API key
GET    /api/v1/admin/api-keys/{key_id}/usage  ดูสถิติการใช้งาน
```

**Frontend (Admin UI):**
- หน้า Settings หรือหน้าใหม่ "API Keys"
- สร้าง key → แสดง key ครั้งเดียว (ไม่แสดงอีก)
- Revoke, view usage stats

### 2.6 Rate Limiting per API Key

```python
# app/core/rate_limiter.py

class APIKeyRateLimiter:
    """Per API-key rate limiting using in-memory counter or Redis"""
    
    async def check(self, key_id: int, limits: dict) -> bool:
        """
        limits = {"per_minute": 30, "per_day": 1000}
        Returns True if allowed, False if exceeded
        """
```

### 2.7 Usage Tracking

ทุก query ผ่าน API key ต้อง log:

```sql
CREATE TABLE api_key_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL REFERENCES api_keys(id),
    endpoint TEXT NOT NULL,  -- /query, /chat, /admin/...
    question TEXT,
    context_name TEXT,
    tokens_used INTEGER DEFAULT 0,
    execution_time_ms FLOAT DEFAULT 0,
    status TEXT,  -- success, error
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 3. OpenMiniCrew Tool Design (ฝั่ง OpenMiniCrew)

หลังจาก AI Assistant เตรียมพร้อมแล้ว OpenMiniCrew สร้าง tool ได้ง่ายมาก:

```python
# openminicrew/tools/nt_query.py

"""AI Assistant Query Tool — ถามข้อมูลการเงินจาก AI Assistant"""

import httpx
from tools.base import BaseTool
from core.config import NT_AI_API_URL, NT_AI_API_KEY
from core import db
from core.logger import get_logger

log = get_logger(__name__)


class NTQueryTool(BaseTool):
    name = "nt_query"
    description = "ถามข้อมูลการเงิน เช่น รายได้ ค่าใช้จ่าย กำไรขาดทุน ผลดำเนินงาน"
    commands = ["/nt", "/ntquery", "/finance"]
    direct_output = True
    preferred_tier = "cheap"  # tool ไม่เรียก LLM เอง — AI Assistant จัดการให้

    async def execute(self, user_id: str, args: str = "", 
                      context: str = "", **kwargs) -> str:
        if not args:
            return (
                "กรุณาระบุคำถาม เช่น:\n"
                "/nt รายได้รวมปี 68\n"
                "/nt ค่าใช้จ่ายกลุ่ม mobile เดือนนี้\n"
                "/nt ผลดำเนินงานกลุ่ม datacom"
            )

        if not NT_AI_API_URL or not NT_AI_API_KEY:
            return "AI Assistant API ยังไม่ได้ตั้งค่า กรุณาเพิ่ม NT_AI_API_URL และ NT_AI_API_KEY ใน .env"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{NT_AI_API_URL}/api/v1/query/",
                    headers={"X-API-Key": NT_AI_API_KEY},
                    json={
                        "question": args,
                        "context": context or None,
                        "format": "markdown",
                        "include_sql": False,
                        "include_data": True,
                        "max_rows": 10,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("error"):
                return f"AI Assistant Error: {data['error']}"

            # Format response for Telegram
            answer = data.get("answer", "ไม่มีคำตอบ")
            result = f"📊 {answer}"

            # Append data table if available
            rows = data.get("data")
            if rows and len(rows) > 0:
                result += "\n\n📋 ข้อมูล:\n"
                result += _format_table(rows)

            result += f"\n⏱ {data.get('execution_time_ms', 0):.0f}ms"

            db.log_tool_usage(user_id, self.name, args[:100], status="success")
            return result

        except httpx.TimeoutException:
            return "AI Assistant ใช้เวลานานเกินไป กรุณาลองใหม่"
        except Exception as e:
            log.error(f"Query failed: {e}")
            db.log_tool_usage(user_id, self.name, args[:100], 
                            status="failed", error_message=str(e))
            return f"เกิดข้อผิดพลาด: {e}"

    def get_tool_spec(self) -> dict:
        return {
            "name": self.name,
            "description": (
                "ถามข้อมูลการเงิน เช่น รายได้ ค่าใช้จ่าย กำไรขาดทุน ผลดำเนินงาน "
                "ค้นหาตามกลุ่มธุรกิจ กลุ่มบริการ ช่วงเวลา เปรียบเทียบ"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": "คำถามภาษาไทย เช่น 'รายได้รวมปี 68', 'ค่าใช้จ่าย mobile Q1'",
                    },
                    "context": {
                        "type": "string",
                        "enum": ["revenue", "expense", "pl_costtype"],
                        "description": "บริบทข้อมูล: revenue=รายได้, expense=ค่าใช้จ่าย, pl_costtype=งบกำไรขาดทุน",
                    },
                },
                "required": ["args"],
            },
        }


def _format_table(rows: list, max_rows: int = 10) -> str:
    """Format data rows as monospace table for Telegram"""
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = ["  ".join(h[:12].ljust(12) for h in headers)]
    lines.append("-" * len(lines[0]))
    for row in rows[:max_rows]:
        line = "  ".join(str(row.get(h, ""))[:12].ljust(12) for h in headers)
        lines.append(line)
    if len(rows) > max_rows:
        lines.append(f"... (แสดง {max_rows}/{len(rows)} แถว)")
    return "```\n" + "\n".join(lines) + "\n```"
```

**Config เพิ่มใน OpenMiniCrew `.env`:**
```bash
NT_AI_API_URL=http://localhost:8000
NT_AI_API_KEY=<API_KEY>
```

## 4. Dependency Map (ฝั่ง AI Assistant)

```
2.1 API Key Auth  ←── ต้องทำก่อนทุกอย่าง
      │
      ├──→ 2.2 Simplified Query Endpoint (/query)
      │         │
      │         └──→ OpenMiniCrew สร้าง NTQueryTool ได้
      │
      ├──→ 2.3 Public Context List
      │
      ├──→ 2.5 API Key Management (Admin UI)
      │
      ├──→ 2.6 Rate Limiting
      │
      └──→ 2.7 Usage Tracking
```

## 5. ไฟล์ทั้งหมดที่ต้องสร้าง/แก้ (ฝั่ง AI Assistant)

### ไฟล์ใหม่

| ไฟล์ | หน้าที่ |
|------|---------|
| `app/models/api_key.py` | APIKey model |
| `app/api/v1/query.py` | Simplified query endpoint |
| `app/schemas/query.py` | SimpleQueryRequest, SimpleQueryResponse |
| `app/services/api_key_service.py` | API key create, validate, revoke |
| `database/migrations/025_api_keys.sql` | API key + usage tables |
| `frontend-admin/src/pages/APIKeys.tsx` | API key management UI |
| `frontend-admin/src/services/apiKeyService.ts` | API key service |

### ไฟล์แก้

| ไฟล์ | การแก้ |
|------|--------|
| `app/api/deps.py` | เพิ่ม X-API-Key auth path |
| `app/main.py` | เพิ่ม query router |
| `app/config.py` | เพิ่ม API_KEY_ENABLED config |
| `app/models/user.py` | เพิ่ม telegram_chat_id (ถ้ายังไม่มีจาก Plan 4) |
| `frontend-admin/src/App.tsx` | เพิ่ม route /api-keys |
| `frontend-admin/src/components/Layout/AdminLayout.tsx` | เพิ่ม menu item |

### ไฟล์ที่ต้องสร้างฝั่ง OpenMiniCrew (หลัง AI Assistant พร้อม)

| ไฟล์ | หน้าที่ |
|------|---------|
| `openminicrew/tools/nt_query.py` | NTQueryTool |
| `openminicrew/tools/nt_admin.py` | NTAdminTool (ถ้าต้องการ admin commands ผ่าน Telegram) |

---

## Claude Code Instructions

```
## ฝั่ง AI Assistant

### ไฟล์ที่ต้องอ่านก่อน
- app/api/deps.py (current auth flow — session token)
- app/api/v1/chat.py (current chat endpoint — response format)
- app/api/v1/auth.py (OTP/password login)
- app/schemas/chat.py (ChatRequest, ChatResponse)
- app/services/query_engine.py (QueryEngine.query() — core logic)
- app/core/rate_limiter.py (existing rate limiter)
- app/config.py (settings)

### ลำดับ Implementation

Phase 1: API Key Auth
  1. สร้าง app/models/api_key.py
  2. สร้าง DB migration: api_keys + api_key_usage tables
  3. สร้าง app/services/api_key_service.py (create, validate, revoke, track usage)
  4. แก้ app/api/deps.py: เพิ่ม X-API-Key auth path ใน get_current_user()
  5. ทดสอบ: สร้าง key ด้วย script → เรียก /chat/ ด้วย API key → ได้ response

Phase 2: Simplified Query Endpoint
  6. สร้าง app/schemas/query.py (SimpleQueryRequest, SimpleQueryResponse)
  7. สร้าง app/api/v1/query.py (POST /query/)
  8. แก้ app/main.py: เพิ่ม query router
  9. ทดสอบ: curl -X POST /api/v1/query/ -H "X-API-Key: ..." -d '{"question":"รายได้รวม"}'

Phase 3: Admin Endpoints + UI
  10. เพิ่ม CRUD endpoints สำหรับ API keys ใน admin.py
  11. สร้าง frontend-admin/src/pages/APIKeys.tsx
  12. แก้ App.tsx + AdminLayout.tsx

Phase 4: Rate Limiting + Usage Tracking
  13. เพิ่ม per-API-key rate limit ใน deps.py
  14. เพิ่ม usage logging ทุก request ที่ใช้ API key

## กฎ
- API key ต้อง hash (SHA-256) ก่อน store — แสดง key ครั้งเดียวตอนสร้าง
- key format: "ntai_" + 32 random chars (ให้ identify ได้ว่าเป็น key ของ AI Assistant)
- /query/ endpoint ต้องไม่สร้าง conversation, ไม่เก็บ chart session
- /query/ ยังคงเก็บ ChatHistory (เพื่อ audit trail) แต่ conversation_id = None
- rate limit default: 30/min, 1000/day (configurable per key)
- API key auth ต้อง backward compatible — session token ยังใช้ได้เหมือนเดิม
- ห้ามเปลี่ยน /chat/ endpoint ที่มีอยู่ (frontend ยังใช้อยู่)

## ฝั่ง OpenMiniCrew (ทำหลัง AI Assistant Phase 2 เสร็จ)

### ไฟล์ที่ต้องอ่านก่อน
- tools/base.py (BaseTool pattern)
- core/config.py (config pattern)
- tools/exchange_rate.py (ตัวอย่าง API tool ที่ใกล้เคียงที่สุด)

### ลำดับ
1. เพิ่ม NT_AI_API_URL, NT_AI_API_KEY ใน core/config.py + .env.example
2. สร้าง tools/nt_query.py (NTQueryTool)
3. ทดสอบ: /nt รายได้รวมปี 68 → ได้คำตอบจาก AI Assistant
4. (Optional) สร้าง tools/nt_admin.py สำหรับ admin commands

### กฎ OpenMiniCrew
- ไม่แก้ไฟล์ existing — สร้างเฉพาะไฟล์ใหม่
- ใช้ httpx (async) ไม่ใช่ requests (sync) เพราะ execute() เป็น async
- timeout 60 วินาที (AI Assistant อาจช้าถ้า LLM ทำงานหนัก)
- format table เป็น monospace สำหรับ Telegram
```

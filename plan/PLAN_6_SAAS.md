# Plan 6: Multi-tenant / SaaS Architecture

**Priority:** 6 (ระยะยาว)  
**ประมาณเวลา:** Design 3 วัน, Implement 2-4 สัปดาห์  
**Prerequisite:** Plan 5 (DB Separation)  
**อ้างอิง:** Plan 1 (Admin Agent), Plan 4 (Telegram), Plan 5 (DB Separation)

---

## 1. Service Models

### 1.1 Model A: API as a Service (ง่ายสุด)

Tenant เรียก API มาถามคำถาม → เราคืน SQL + result

```
Tenant App/Dashboard
        │ HTTP POST /api/v1/tenant/{tenant_id}/chat
        ▼
AI Assistant API
        │
        ├── Tenant config (config.db per tenant)
        ├── Tenant business DB (connection string)
        └── Response: { sql, data, explanation, chart }
```

**Tenant onboarding:**
1. Admin สร้าง tenant → ได้ API key
2. Tenant ให้ DB connection string (PostgreSQL/MSSQL/SQLite)
3. Admin run Context Onboarding สำหรับ tenant
4. Tenant เรียก API ด้วย API key

### 1.2 Model B: Upload & Query (self-service)

Tenant upload CSV/Excel → ระบบสร้าง SQLite ให้ → onboard อัตโนมัติ

```
Tenant Web UI
        │ Upload CSV/Excel
        ▼
AI Assistant Upload Service
        │
        ├── แปลง CSV → SQLite table
        ├── Auto Context Onboarding (Plan existing)
        └── Tenant ถามข้อมูลได้ทันที
```

**Tenant onboarding:**
1. Tenant สมัคร → ได้ workspace
2. Upload ไฟล์ (CSV, Excel, หรือ SQLite)
3. ระบบ inspect + onboard อัตโนมัติ
4. Tenant ถามคำถามได้เลย

### 1.3 Model C: Connect & Query (enterprise)

Tenant ให้ connection string → เราเชื่อม DB ตรง (read-only)

```
Tenant DB (PostgreSQL/MSSQL)
        │ Read-only connection
        ▼
AI Assistant Business DB Adapter (Plan 5)
        │
        ├── Schema inspection
        ├── Context Onboarding
        └── Query execution
```

### 1.4 Model D: MCP Server (developer-focused)

Expose AI Assistant เป็น MCP Server ให้ Claude Desktop / Claude Code เรียกใช้

```
Claude Desktop / Claude Code
        │ MCP Protocol
        ▼
AI Assistant MCP Server (มีอยู่แล้วบางส่วนใน mcp_servers/)
        │
        ├── query tool: ถามข้อมูลภาษาไทย
        ├── metadata tool: ดู schema/contexts
        └── validation tool: ตรวจ SQL
```

**มีอยู่แล้ว:** `mcp_servers/nt_query_mcp.py`, `nt_metadata_mcp.py`, `nt_validation_mcp.py`
ต้องเพิ่ม: tenant isolation, API key auth

### 1.5 Model E: Skill Package

Export เป็น `.claude/skills/` สำหรับ Claude Code

**มีอยู่แล้ว:** `.claude/skills/onboard-context.md`
ต้องเพิ่ม: skill templates per domain (finance, HR, inventory, etc.)

## 2. Multi-tenant Architecture

### แนะนำ: DB per Tenant (Isolated)

```
┌─────────────────────────────────────────┐
│              Shared Layer                │
│                                          │
│  app.db (shared)                        │
│  ├── tenants table                      │
│  ├── users table (+ tenant_id FK)      │
│  ├── tenant_api_keys                   │
│  └── billing / usage tracking           │
│                                          │
│  FastAPI Application (shared)           │
│  ├── Auth middleware (API key → tenant)  │
│  ├── QueryEngine (shared code)         │
│  ├── Provider Registry (shared)        │
│  └── Admin Agent (shared)              │
└───────────────┬─────────────────────────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│Tenant A │ │Tenant B │ │Tenant C │
│         │ │         │ │         │
│config_a │ │config_b │ │config_c │
│.db      │ │.db      │ │.db      │
│         │ │         │ │         │
│biz_a.   │ │pg://    │ │upload/  │
│sqlite   │ │host/db  │ │data.csv │
└─────────┘ └─────────┘ └─────────┘
```

### Tenant Table

```sql
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,  -- URL-safe identifier
    plan TEXT DEFAULT 'free',  -- free, pro, enterprise
    
    -- Business DB connection
    db_type TEXT DEFAULT 'sqlite',  -- sqlite, postgresql, mssql
    db_connection TEXT,  -- connection string or file path
    
    -- Config DB
    config_db_path TEXT,  -- path to tenant's config.db
    
    -- Limits
    max_queries_per_day INTEGER DEFAULT 100,
    max_contexts INTEGER DEFAULT 5,
    max_api_keys INTEGER DEFAULT 3,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME,
    created_by INTEGER REFERENCES users(id)
);

CREATE TABLE tenant_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    api_key TEXT UNIQUE NOT NULL,
    name TEXT,  -- "Production", "Development"
    permissions TEXT DEFAULT 'query',  -- query, admin, full
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at DATETIME,
    created_at DATETIME
);
```

### Tenant Middleware

```python
# app/core/tenant_middleware.py

class TenantMiddleware:
    """Extract tenant from API key or session"""
    
    async def __call__(self, request, call_next):
        api_key = request.headers.get("X-API-Key")
        if api_key:
            tenant = lookup_tenant_by_api_key(api_key)
            if not tenant:
                return JSONResponse(status_code=401, content={"error": "Invalid API key"})
            request.state.tenant = tenant
            request.state.config_db = get_config_db_session(tenant)
            request.state.business_db = get_business_db_adapter(tenant)
        
        response = await call_next(request)
        return response
```

### Tenant-aware QueryEngine

```python
# ปัจจุบัน QueryEngine ใช้ global config
# ต้องเปลี่ยนให้รับ tenant context:

class QueryEngine:
    def __init__(self, config_db, business_db, tenant_id: str):
        self.config_db = config_db  # tenant's config DB session
        self.business_db = business_db  # tenant's business DB adapter
        self.tenant_id = tenant_id
    
    # schema_service, semantic_mapping, business_rules ทั้งหมด
    # ดึงจาก tenant's config_db
```

## 3. Tenant Onboarding Workflow

```
1. Admin สร้าง tenant → tenants table
2. Setup business DB:
   a. SQLite: สร้าง directory /data/tenants/{tenant_id}/business.db
   b. Upload: รับ CSV → สร้าง SQLite
   c. Connect: บันทึก connection string
3. สร้าง config DB: /data/tenants/{tenant_id}/config.db (empty schema)
4. Context Onboarding: inspect views → LLM analyze → apply config
5. สร้าง API key
6. Tenant พร้อมใช้งาน
```

## 4. SKILL.md Integration

SKILL.md เป็น format เฉพาะ Claude Code แต่แนวคิดใช้ได้กับทุก LLM:

### สิ่งที่ทำได้

**4.1 Admin Instruction Templates (แทน SKILL.md สำหรับ LLM ทั่วไป)**

```python
# Tenant-specific instruction template (stored in config DB)
# inject เข้า system prompt ของ LLM ตอน generate SQL

class InstructionTemplate:
    """เหมือน SKILL.md แต่เป็น DB-driven instruction สำหรับ LLM"""
    name: str
    domain: str  # finance, hr, inventory, sales
    instruction_th: str  # Thai instruction for LLM
    instruction_en: str
    example_queries: List[Dict]
    critical_rules: List[str]
```

ตอนนี้ `schema_contexts.instruction_th` ทำหน้าที่นี้อยู่แล้ว → ขยายให้ tenant-specific

**4.2 Claude Code Skills สำหรับ tenant management**

```markdown
# .claude/skills/manage-tenant.md

เมื่อ admin ต้องการจัดการ tenant:
1. สร้าง tenant ใหม่: INSERT INTO tenants ...
2. Setup business DB: สร้าง directory + copy data
3. Run onboarding: python scripts/onboard_context.py --db-path /data/tenants/{id}/business.db
4. สร้าง API key: INSERT INTO tenant_api_keys ...
```

**4.3 Domain-specific Skill Packages (SaaS product)**

Export ชุด config (contexts + rules + mappings + examples) สำหรับ domain:

```
skills/
├── finance/
│   ├── SKILL.md
│   ├── contexts.json (P&L, Revenue, Expense, Balance Sheet)
│   ├── rules.json (unit conversion, year conversion, semi-crosstab)
│   └── mappings.json (Thai financial terms)
├── hr/
│   ├── SKILL.md
│   ├── contexts.json (Employee, Payroll, Leave)
│   └── ...
└── inventory/
    ├── SKILL.md
    └── ...
```

Tenant เลือก domain → import skill package → ปรับแต่งเพิ่ม

## 5. ข้อจำกัดที่ต้อง address

| ข้อจำกัด | วิธีแก้ |
|---------|--------|
| SQLite ไม่รองรับ concurrent writes | PostgreSQL for shared DB, SQLite OK for per-tenant (1 tenant = 1 user at a time) |
| LLM token cost per tenant | Usage tracking + quota per plan |
| Business DB security (tenant ส่ง connection string) | Read-only connection, allowlist tables, SQL validation |
| Data isolation | DB per tenant + middleware check |
| Tenant config ปนกัน | Config DB per tenant (isolated) |

---

## Claude Code Instructions

```
## Plan 6 เป็นแผนระยะยาว — ไม่ต้อง implement ทั้งหมดตอนนี้
## สิ่งที่ Claude Code ทำได้ตอนนี้:

Phase 0: Preparation (ทำได้เลย หลัง Plan 5)
  1. สร้าง tenants model + migration
  2. สร้าง tenant_api_keys model + migration
  3. สร้าง tenant middleware (basic)
  4. สร้าง tenant management admin endpoints

Phase 1: Model B — Upload & Query (ง่ายสุดสำหรับ MVP)
  5. สร้าง upload endpoint: POST /tenant/{id}/upload (CSV/Excel → SQLite)
  6. Auto-run Context Onboarding หลัง upload
  7. Tenant query endpoint: POST /tenant/{id}/chat
  8. Usage tracking

Phase 2: Model A — API as a Service
  9. API key authentication
  10. Rate limiting per tenant
  11. External DB connection support (PostgreSQL, MSSQL)

Phase 3: Model D — MCP Server
  12. Update existing mcp_servers/ ให้รองรับ tenant
  13. API key auth สำหรับ MCP

## ไฟล์ที่ต้องอ่านก่อน
- app/config.py (DB URLs)
- app/core/middleware.py (existing middleware)
- app/services/context_onboarding.py (onboarding per DB)
- app/services/database_adapter.py (DB adapter pattern)
- mcp_servers/nt_query_mcp.py (existing MCP server)
- app/services/query_engine.py (main query flow — ต้อง inject tenant context)

## กฎ
- Tenant isolation เป็น non-negotiable — ห้าม cross-tenant data access
- Default เป็น read-only สำหรับ business DB ของ tenant
- Usage tracking ทุก query (token count, execution time)
- API key ต้อง hash ก่อน store (เหมือน password)
- Free tier จำกัด: 100 queries/day, 5 contexts, 1 API key
```

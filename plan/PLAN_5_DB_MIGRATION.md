# Plan 5: DB Separation + PostgreSQL Migration Path

**Priority:** 5 (infrastructure — ทำขนานกับ Plan 3-4 ได้)  
**ประมาณเวลา:** 2-3 วัน  
**Prerequisite:** ไม่มี (standalone)  
**อ้างอิงโดย:** Plan 6 (SaaS ต้องใช้ DB separation)

---

## 1. ปัญหาปัจจุบัน

### 1.1 Table/View ปะปนกัน

`nt_fi_report.sqlite` มีทั้ง:
- **Business data:** `v_pl_costtype_nt_mth_clean`, `v_expense_mart`, revenue tables/views
- **System config:** `schema_contexts`, `schema_metadata`, `schema_business_rules`, `golden_examples`, `schema_semantic_mapping`, `master_hierarchy`, `master_hierarchy_values`, `data_warnings`, `query_complexity_patterns`, `admin_config`, `ai_providers`, `ai_models`, `keyword_value_index`, `view_column_mappings`

`app/db/app.db` มี:
- **App data:** `users`, `user_sessions`, `otp_codes`, `chat_history`, `user_feedback`, `conversations`, `training_data`

ปัญหา:
- Context Onboarding ต้อง filter internal tables ออก (ใช้ prefix matching ที่ fragile)
- Admin endpoints ใช้ทั้ง SQLAlchemy (app.db) และ raw sqlite3 (nt_fi_report.sqlite) → dual connection
- ถ้า tenant ใหม่ upload data มา config tables จะปนกับ data tables

### 1.2 SQLite Limitations

- ไม่มี concurrent writes (WAL ช่วยได้บ้างแต่จำกัด)
- ไม่มี schema separation
- ไม่มี role-based access control
- File-based → ย้าย server ต้อง copy file

## 2. แผนการแยก DB (Phase A — ทำได้เลย)

### เป้าหมาย: แยก 3 DB ชัดเจน

```
app.db (SQLAlchemy ORM)
├── users, user_sessions, otp_codes
├── chat_history, conversations, user_feedback
├── admin_agent_conversations, admin_agent_messages (Plan 1)
└── config_audit_log (Plan 3)

config.db (SQLAlchemy ORM — ย้ายจาก nt_fi_report.sqlite)
├── schema_contexts, schema_metadata
├── schema_business_rules, schema_semantic_mapping
├── golden_examples, master_hierarchy, master_hierarchy_values
├── data_warnings, query_complexity_patterns
├── admin_config, ai_providers, ai_models
├── keyword_value_index, view_column_mappings
└── unmatched_hierarchy_keywords

nt_fi_report.sqlite (raw SQL — business data only)
├── business views: v_pl_costtype_nt_mth_clean, v_expense_mart, etc.
├── business tables: raw data tables
└── ไม่มี config tables อีกต่อไป
```

### ไฟล์ที่ต้องแก้

| ไฟล์ | การแก้ |
|------|--------|
| `app/config.py` | เพิ่ม `CONFIG_DB_URL`, แยก `DATABASE_URL` (app), `BUSINESS_DB_PATH` (business) |
| `app/db/session.py` | เพิ่ม session factory สำหรับ config.db |
| `app/models/schema_models.py` | เปลี่ยน Base → ConfigBase (bind ไป config.db) |
| `app/services/schema_service.py` | ใช้ config DB session |
| `app/services/context_onboarding.py` | business DB ยังใช้ raw sqlite3 ตามเดิม, config operations ใช้ ORM |
| `app/api/v1/admin.py` | inject config DB session |
| `scripts/migrate_config_to_separate_db.py` | **ใหม่** — script ย้าย config tables |

### Migration Script

```python
# scripts/migrate_config_to_separate_db.py

"""
ย้าย config tables จาก nt_fi_report.sqlite → config.db
1. สร้าง config.db ด้วย schema เดียวกัน
2. Copy data ทุก row
3. Drop config tables จาก nt_fi_report.sqlite
4. Verify
"""

CONFIG_TABLES = [
    "schema_contexts", "schema_metadata", "schema_business_rules",
    "schema_semantic_mapping", "golden_examples", "master_hierarchy",
    "master_hierarchy_values", "data_warnings", "query_complexity_patterns",
    "admin_config", "ai_providers", "ai_models",
    "keyword_value_index", "view_column_mappings",
    "unmatched_hierarchy_keywords",
]
```

## 3. แผน PostgreSQL Migration (Phase B — ทำทีหลัง)

### เมื่อไหร่ควรย้าย

- เมื่อต้องการ multi-tenant (Plan 6)
- เมื่อ concurrent users > 10 (SQLite WAL ไม่พอ)
- เมื่อ deploy เป็น container cluster (SQLite file ไม่ share ได้)

### สิ่งที่ต้องเปลี่ยน

| Component | SQLite ปัจจุบัน | PostgreSQL |
|-----------|----------------|------------|
| App DB | SQLAlchemy ORM → เปลี่ยน `DATABASE_URL` จบ | `postgresql://...` |
| Config DB | SQLAlchemy ORM → เปลี่ยน `CONFIG_DB_URL` จบ | `postgresql://...` schema "config" |
| Business DB | raw `sqlite3.connect()` | ต้องสร้าง DB adapter |

### DB Adapter Pattern

**ไฟล์:** `app/services/business_db.py`

```python
class BusinessDBAdapter:
    """Unified interface for business DB regardless of backend"""
    
    def __init__(self, db_url: str):
        self.engine_type = self._detect_engine(db_url)
        # SQLite: sqlite3.connect()
        # PostgreSQL: psycopg2 หรือ asyncpg
        # MSSQL: pymssql
    
    def execute(self, sql: str, params: tuple = None) -> List[Dict]:
        """Execute read-only query"""
    
    def get_schema(self, table_name: str) -> List[ColumnInfo]:
        """Get table/view schema (PRAGMA for SQLite, information_schema for PG)"""
    
    def get_tables(self) -> List[str]:
        """List all tables/views"""
```

สิ่งที่ต้องระวังใน SQL syntax:

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| String concat | `\|\|` | `\|\|` (เหมือนกัน) |
| LIKE case | case-insensitive default | case-sensitive (ใช้ ILIKE) |
| Quoting | `"column"` | `"column"` (เหมือนกัน) |
| PRAGMA | `PRAGMA table_info()` | `information_schema.columns` |
| Boolean | 0/1 | true/false |
| Date functions | date(), strftime() | TO_DATE(), DATE_TRUNC() |

`database_adapter.py` ที่มีอยู่แล้วอาจ handle บางส่วนแล้ว — ต้องตรวจ

## 4. Context Onboarding Impact

หลังแยก DB แล้ว `context_onboarding.py` ต้องแก้:

- `DataInspector` → ยังชี้ไป business DB (nt_fi_report.sqlite) เหมือนเดิม
- `ConfigGenerator` → generate SQL สำหรับ config DB (ไม่ใช่ business DB)
- `ConfigApplicator` → apply ไป config DB
- `ConfigValidator` → ตรวจ config DB
- `list_available_views()` → ดึง views จาก business DB, ดึง contexts จาก config DB

ปัจจุบันทุก class ใน `context_onboarding.py` ใช้ `self.db_path` เดียว → ต้องแยกเป็น `business_db_path` + `config_db_path` (หรือ config DB session)

---

## Claude Code Instructions

```
## Phase A: DB Separation (ทำได้เลย)

### ไฟล์ที่ต้องอ่านก่อน
- app/config.py (DATABASE_URL, BUSINESS_DB_PATH)
- app/db/session.py (current session factory)
- app/models/schema_models.py (config models — target for migration)
- app/services/context_onboarding.py (uses single db_path)
- app/services/database_adapter.py (existing adapter)
- app/services/schema_service.py (uses config tables)
- app/api/v1/admin.py (dual DB pattern)

### ลำดับ
1. เพิ่ม CONFIG_DB_URL ใน config.py (default: sqlite:///./config.db)
2. สร้าง config DB session factory ใน db/session.py
3. สร้าง scripts/migrate_config_to_separate_db.py
4. แก้ schema_models.py ให้ bind ไป config DB
5. แก้ schema_service.py ให้ใช้ config DB session
6. แก้ admin.py endpoints ที่ query config tables
7. แก้ context_onboarding.py: แยก business_db_path + config_db_path
8. ทดสอบ: onboard view + query ทำงานปกติหลังแยก DB
9. ทดสอบ: admin CRUD operations ทำงานปกติ

## Phase B: PostgreSQL (ทำทีหลัง)
10. สร้าง app/services/business_db.py (DB adapter)
11. แก้ DataInspector ใช้ adapter แทน raw sqlite3
12. แก้ DatabaseService ใช้ adapter
13. ทดสอบกับ PostgreSQL (docker-compose.yml มี PG อยู่แล้ว)

## กฎ
- Phase A ห้ามเปลี่ยน ORM models — แค่ย้าย tables
- Migration script ต้อง: copy data → verify → แล้วค่อย drop จาก source
- ถ้า migration fail ต้อง rollback ได้ (keep backup ของ nt_fi_report.sqlite)
- หลังแยกแล้ว list_available_views() ไม่ต้อง filter config tables อีกต่อไป (clean!)
```

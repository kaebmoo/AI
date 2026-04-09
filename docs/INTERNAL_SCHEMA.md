# Internal Schema Reference

**Version:** 1.0
**Last Updated:** 2026-03-22

> Developer reference สำหรับ app.db และ config.db tables ที่ไม่เกี่ยวกับ SQL generation
> ไฟล์นี้ **ไม่ถูก** Vanna RAG consume — เป็น internal reference เท่านั้น
>
> สำหรับ tables ที่เกี่ยวกับ SQL generation ดูที่:
> - [DATABASE_TABLES_GUIDE.md](DATABASE_TABLES_GUIDE.md) — config tables สำหรับ AI context
> - [DATA_DICTIONARY.md](DATA_DICTIONARY.md) — business data views

---

## สารบัญ

### app.db (ORM Base: `Base`)

1. [users](#1-users)
2. [user_sessions](#2-user_sessions)
3. [chat_history](#3-chat_history)
4. [conversations](#4-conversations)
5. [chat_session_data](#5-chat_session_data)
6. [otp_requests](#6-otp_requests)
7. [user_feedback](#7-user_feedback)
8. [trending_queries](#8-trending_queries)
9. [api_keys](#9-api_keys)
10. [api_key_usage](#10-api_key_usage)
11. [admin_agent_conversations](#11-admin_agent_conversations)
12. [admin_agent_messages](#12-admin_agent_messages)

### config.db (ORM Base: `ConfigBase`) — non-SQL-gen tables

13. [admin_config](#13-admin_config)
14. [ai_providers](#14-ai_providers)
15. [ai_models](#15-ai_models)
16. [config_audit_log](#16-config_audit_log)
17. [suggested_fixes](#17-suggested_fixes)
18. [data_warnings](#18-data_warnings)
19. [query_complexity_patterns](#19-query_complexity_patterns)

---

## 3-DB Architecture

```
┌─────────────┐   ┌──────────────┐   ┌───────────────────┐
│   app.db    │   │  config.db   │   │ nt_fi_report.sqlite│
│  (Base)     │   │ (ConfigBase) │   │   (raw SQL/MCP)    │
├─────────────┤   ├──────────────┤   ├───────────────────┤
│ users       │   │ admin_config │   │ revenue            │
│ sessions    │   │ ai_providers │   │ expense            │
│ chat_history│   │ ai_models    │   │ transfer_price     │
│ conversations│  │ audit_log    │   │ TRN_PL_COSTTYPE..  │
│ feedback    │   │ suggested_fix│   │ + views            │
│ api_keys    │   │ schema_*     │   └───────────────────┘
│ admin_agent │   │ master_*     │
│ otp         │   │ golden_*     │
│ trending    │   │ warnings     │
└─────────────┘   └──────────────┘
```

**Key files:**
- `app/db/base_class.py` — `Base` (app) + `ConfigBase` (config)
- `app/db/session.py` — `engine`, `config_engine`, `business_engine`
- `app/api/deps.py` — `get_db()` (app), `get_config_db()` (config)

---

# app.db Tables

---

## 1. users

**Model:** `app/models/user.py` — class `User(Base)`
**หน้าที่:** ข้อมูลผู้ใช้งานระบบ (authentication + authorization)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| email | String | UNIQUE, indexed, NOT NULL | — | Email (ใช้เป็น login) |
| display_name | String | | NULL | ชื่อแสดง |
| department | String | nullable | NULL | แผนก |
| is_active | Boolean | | True | สถานะ active |
| role | String | | 'user' | user / admin / viewer |
| allowed_bu_access | String | nullable | NULL | BU ที่เข้าถึงได้ (comma-separated) |
| hashed_password | String | nullable | NULL | Password hash (สำหรับ local auth) |
| force_password_change | Boolean | | False | บังคับเปลี่ยน password |
| created_at | DateTime | | utcnow | |
| updated_at | DateTime | | utcnow | auto-update |

**Relationships:** sessions, chats, conversations

---

## 2. user_sessions

**Model:** `app/models/session.py` — class `UserSession(Base)`
**หน้าที่:** Session tokens สำหรับ web และ telegram

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| user_id | Integer | FK → users.id | — | เจ้าของ session |
| session_token | String | UNIQUE, indexed | — | Token สำหรับ auth |
| platform | String | | — | web / telegram |
| telegram_chat_id | BigInteger | nullable | NULL | Telegram chat ID (ถ้า platform=telegram) |
| created_at | DateTime | | utcnow | |
| expires_at | DateTime | | — | วันหมดอายุ |
| last_activity | DateTime | | utcnow | ใช้ล่าสุดเมื่อไหร่ |
| ip_address | String | nullable | NULL | |
| user_agent | String | nullable | NULL | |

---

## 3. chat_history

**Model:** `app/models/chat.py` — class `ChatHistory(Base)`
**หน้าที่:** ประวัติคำถาม-คำตอบทั้งหมด (main query log)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| user_id | Integer | FK → users.id | — | ผู้ถาม |
| session_id | Integer | FK → user_sessions.id, nullable | NULL | Session ที่ถาม |
| conversation_id | String | FK → conversations.id, indexed, nullable | NULL | Conversation ที่อยู่ |
| question | Text | | — | คำถามภาษาไทย |
| generated_sql | Text | nullable | NULL | SQL ที่ AI สร้าง |
| sql_result_summary | Text | nullable | NULL | สรุปผลลัพธ์ |
| ai_response | Text | | — | คำตอบ AI |
| tokens_used | Integer | | 0 | จำนวน tokens |
| execution_time_ms | Float | | 0.0 | เวลาประมวลผล (ms) |
| created_at | DateTime | | utcnow | |
| context_name | String | nullable | NULL | revenue / expense / etc. |
| is_bookmarked | Boolean | | False | ผู้ใช้ bookmark ไว้ |
| feedback_rating | Integer | nullable | NULL | Rating 1-5 |

**Relationships:** user, conversation, feedback (via UserFeedback backref)

---

## 4. conversations

**Model:** `app/models/conversation.py` — class `Conversation(Base)`
**หน้าที่:** จัดกลุ่ม chat messages เป็น conversations (เหมือน chat threads)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | String(36) | PK | uuid4() | UUID string |
| user_id | Integer | FK → users.id, indexed, NOT NULL | — | เจ้าของ |
| title | String(255) | nullable | NULL | ชื่อ conversation |
| created_at | DateTime | | utcnow | |
| updated_at | DateTime | | utcnow | auto-update |
| is_archived | Boolean | | False | เก็บถาวร |
| message_count | Integer | | 0 | จำนวน messages |

**Relationships:** user, messages (ChatHistory ordered by created_at)

---

## 5. chat_session_data

**Model:** `app/models/chat_session.py` — class `ChatSessionData(Base)`
**หน้าที่:** เก็บ last query result per conversation สำหรับ follow-up queries และ chart rendering

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| conversation_id | String | PK, indexed | — | FK (logical) → conversations.id |
| last_data | Text | NOT NULL | — | JSON: list of row dicts |
| last_columns | Text | NOT NULL | — | JSON: list of column names |
| last_chart_config | Text | nullable | NULL | JSON: chart config dict |
| row_count | Integer | | 0 | จำนวน rows |
| updated_at | DateTime | | utcnow | auto-update |

---

## 6. otp_requests

**Model:** `app/models/otp.py` — class `OTPRequest(Base)`
**หน้าที่:** OTP สำหรับ passwordless login (web + telegram)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| email | String | indexed | — | Email ที่ขอ OTP |
| otp_code | String | | — | Hashed OTP |
| platform | String | | — | web / telegram |
| telegram_chat_id | BigInteger | nullable | NULL | |
| created_at | DateTime | | — | |
| expires_at | DateTime | | — | หมดอายุเมื่อไหร่ |
| verified_at | DateTime | nullable | NULL | ยืนยันเมื่อไหร่ |
| attempts | Integer | | 0 | จำนวนครั้งที่ลองผิด |
| ip_address | String | nullable | NULL | |

---

## 7. user_feedback

**Model:** `app/models/feedback_models.py` — class `UserFeedback(Base)`
**หน้าที่:** Feedback จากผู้ใช้ต่อ query results (thumbs up/down + category)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| chat_id | Integer | FK → chat_history.id, NOT NULL | — | Query ที่ให้ feedback |
| rating | Enum | NOT NULL | — | thumbs_up / thumbs_down |
| feedback_category | Enum | nullable | NULL | wrong_data, incomplete, sql_error, perfect, etc. |
| feedback_text | Text | nullable | NULL | ข้อความเพิ่มเติม |
| created_at | DateTime | | utcnow | |
| reviewed_by | Integer | FK → users.id, nullable | NULL | Admin ที่ review |
| reviewed_at | DateTime | nullable | NULL | |
| review_notes | Text | nullable | NULL | หมายเหตุ review |
| is_golden_example | Boolean | | False | ถูกเลื่อนขั้นเป็น golden example |

**Enum FeedbackRating:** thumbs_up, thumbs_down
**Enum FeedbackCategory:** wrong_data, incomplete, hard_to_understand, slow, sql_error, perfect, other

---

## 8. trending_queries

**Model:** `app/models/feedback_models.py` — class `TrendingQuery(Base)`
**หน้าที่:** นับคำถามยอดนิยม (สำหรับแสดง trending / analytics)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| question | String | indexed, NOT NULL | — | คำถาม |
| count | Integer | | 1 | จำนวนครั้งที่ถูกถาม |
| date | DateTime | | utcnow | วัน/ช่วงเวลา |
| updated_at | DateTime | | utcnow | auto-update |

---

## 9. api_keys

**Model:** `app/models/api_key.py` — class `APIKey(Base)`
**Migration:** `database/migrations/027_api_keys.sql`
**หน้าที่:** API key authentication สำหรับ external integrations (OpenMiniCrew, etc.)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| key_hash | String(64) | UNIQUE, indexed, NOT NULL | — | SHA-256 hash ของ raw key |
| key_prefix | String(12) | indexed, NOT NULL | — | 8 ตัวแรกสำหรับแสดง (เช่น "ntai_<prefix>") |
| name | String(200) | | '' | ชื่อ key |
| user_id | Integer | NOT NULL | — | เจ้าของ |
| scopes | String(100) | | 'query' | query / admin / full |
| rate_limit_per_minute | Integer | | 30 | Rate limit/นาที |
| rate_limit_per_day | Integer | | 1000 | Rate limit/วัน |
| is_active | Boolean | | True | สามารถ revoke ได้ |
| expires_at | DateTime | nullable | NULL | NULL = ไม่หมดอายุ |
| last_used_at | DateTime | nullable | NULL | ใช้ล่าสุดเมื่อไหร่ |
| created_at | DateTime | | utcnow | |
| updated_at | DateTime | | utcnow | auto-update |

---

## 10. api_key_usage

**Model:** `app/models/api_key.py` — class `APIKeyUsage(Base)`
**หน้าที่:** นับ usage per day per key (สำหรับ rate limiting)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| api_key_id | Integer | NOT NULL | — | FK (logical) → api_keys.id |
| date | String(10) | NOT NULL | — | YYYY-MM-DD |
| request_count | Integer | | 0 | Requests วันนี้ |
| token_count | Integer | | 0 | Tokens ใช้ไปวันนี้ |
| created_at | DateTime | | utcnow | |

**Unique:** (api_key_id, date)

---

## 11. admin_agent_conversations

**Model:** `app/models/admin_agent.py` — class `AdminAgentConversation(Base)`
**Migration:** `database/migrations/025_admin_agent.sql`
**หน้าที่:** Admin Agent chat sessions (AI ช่วย admin จัดการ config)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| user_id | Integer | nullable | NULL | เจ้าของ (ไม่มี FK — cross-DB) |
| title | String(200) | | '' | ชื่อ conversation |
| created_at | DateTime | | utcnow | |
| updated_at | DateTime | | utcnow | auto-update |

---

## 12. admin_agent_messages

**Model:** `app/models/admin_agent.py` — class `AdminAgentMessage(Base)`
**หน้าที่:** Messages ใน Admin Agent conversation (รวม tool calls)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| conversation_id | Integer | FK → admin_agent_conversations.id, CASCADE, NOT NULL | — | |
| role | String(20) | NOT NULL | — | user / assistant / system |
| content | Text | | '' | เนื้อหา message |
| tool_name | String(100) | nullable | NULL | ชื่อ tool ที่เรียก |
| tool_args | Text | nullable | NULL | JSON: arguments ที่ส่งให้ tool |
| tool_result | Text | nullable | NULL | JSON: ผลลัพธ์จาก tool |
| created_at | DateTime | | utcnow | |

**Index:** ix_admin_agent_messages_conversation (conversation_id)

---

# config.db Tables (non-SQL-gen)

> Tables ด้านล่างอยู่ใน config.db แต่ **ไม่เกี่ยวกับ SQL generation** โดยตรง
> สำหรับ tables ที่ drive SQL generation ดู [DATABASE_TABLES_GUIDE.md](DATABASE_TABLES_GUIDE.md)

---

## 13. admin_config

**Migration:** `database/migrations/004_admin_config.sql`
**หน้าที่:** Runtime configuration — AI providers, models, feature flags, DB settings
**ใช้โดย:** `AdminConfigService` (3-tier fallback: DB → .env → hardcoded)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK | auto | |
| config_key | Text | UNIQUE, NOT NULL | — | Key (เช่น 'default_ai_provider') |
| config_value | Text | | NULL | Value |
| config_type | Text | NOT NULL | — | ai_provider / model / api_key / feature_flag / database |
| category | Text | | NULL | ai / database / security / features |
| display_name | Text | | NULL | ชื่อแสดงใน UI |
| description | Text | | NULL | Help text |
| is_active | Integer | | 1 | |
| is_sensitive | Integer | | 0 | Mask ใน UI (สำหรับ API keys) |
| validation_regex | Text | | NULL | Regex สำหรับ validate |
| default_value | Text | | NULL | Fallback ถ้าถูกลบ |
| created_at | Text | | CURRENT_TIMESTAMP | |
| updated_at | Text | | CURRENT_TIMESTAMP | trigger auto-update |
| updated_by | Text | | NULL | Email ผู้แก้ |
| metadata | Text | | NULL | JSON extra data |

**Key config_keys:**

| config_key | ความหมาย |
|---|---|
| default_ai_provider | Provider default (claude/gemini/matcha) |
| claude_enabled / gemini_enabled / matcha_enabled | เปิด/ปิด provider |
| claude_model / gemini_model / matcha_model | Model ที่ใช้ |
| anthropic_api_key / google_ai_api_key / matcha_api_key | API keys (is_sensitive=1) |
| matcha_api_url | Gateway endpoint |
| rag_enabled | เปิด RAG |
| auto_context_detection | Auto-detect context จาก keywords |
| debug_mode | แสดง debug info |
| query_timeout_seconds | SQL timeout |
| max_result_rows | Max rows return |

---

## 14. ai_providers

**Migration:** `database/migrations/005_dynamic_providers.sql`
**หน้าที่:** รายชื่อ AI providers ที่ระบบรองรับ (auto-discovered by provider system)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Text | PK | — | Provider ID (claude/gemini/matcha/openai) |
| name | Text | NOT NULL | — | ชื่อ (Claude, Gemini) |
| display_name | Text | | NULL | ชื่อเต็ม (Claude (Anthropic)) |
| icon | Text | | 'bulb' | Ionicons icon name |
| is_active | Boolean | | 1 | Admin เปิด/ปิดได้ |
| is_default | Boolean | | 0 | Provider default |
| api_key_env_var | Text | | NULL | ENV var สำหรับ API key |
| api_url_env_var | Text | | NULL | ENV var สำหรับ custom URL |
| default_api_url | Text | | NULL | Default URL |
| description | Text | | NULL | คำอธิบาย |
| priority | Integer | | 0 | ลำดับแสดง (สูง = แสดงก่อน) |
| config_schema | Text | | NULL | JSON schema สำหรับ provider-specific config |
| created_at | DateTime | | CURRENT_TIMESTAMP | |
| updated_at | DateTime | | CURRENT_TIMESTAMP | trigger auto-update |

---

## 15. ai_models

**Migration:** `database/migrations/005_dynamic_providers.sql` + `022_ai_models_tier.sql`
**หน้าที่:** Models ที่แต่ละ provider มี พร้อม capabilities และ cost

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK | auto | |
| provider_id | Text | FK → ai_providers.id, CASCADE, NOT NULL | — | Provider ที่เป็นเจ้าของ |
| model_id | Text | NOT NULL | — | Model ID (gpt-4o, claude-sonnet-4-6) |
| display_name | Text | | NULL | ชื่อแสดง |
| is_active | Boolean | | 1 | เปิด/ปิดได้ |
| is_default | Boolean | | 0 | Default model ของ provider |
| context_window | Integer | | NULL | Max tokens |
| supports_vision | Boolean | | 0 | รับ images ได้ไหม |
| cost_per_1m_tokens | Real | | NULL | ราคา (optional) |
| description | Text | | NULL | คำอธิบาย |
| priority | Integer | | 0 | ลำดับแสดง |
| tier | Text | | 'default' | default / cheap (สำหรับ query complexity routing) |
| created_at | DateTime | | CURRENT_TIMESTAMP | |
| updated_at | DateTime | | CURRENT_TIMESTAMP | trigger auto-update |

**Unique:** (provider_id, model_id)

---

## 16. config_audit_log

**Migration:** `database/migrations/028_audit_log.sql`
**หน้าที่:** Audit trail ของทุกการเปลี่ยนแปลง config.db (manual, auto_analyzer, admin_agent)
**ใช้โดย:** `AuditService.log_change()`

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK | auto | |
| action | Text | NOT NULL | — | create / update / delete / toggle / auto_apply |
| table_name | Text | NOT NULL | — | ตารางที่ถูกแก้ |
| record_id | Integer | | NULL | Row ID ที่ถูกแก้ |
| old_value | Text | | NULL | JSON: ค่าเก่า |
| new_value | Text | | NULL | JSON: ค่าใหม่ |
| source | Text | NOT NULL | 'manual' | manual / admin_agent / auto_analyzer / onboarding / api |
| confidence | Real | | NULL | Confidence score (สำหรับ auto_analyzer) |
| source_query_ids | Text | | NULL | JSON array: chat_ids ที่ trigger |
| created_by | Integer | | NULL | User ID |
| created_at | Timestamp | | CURRENT_TIMESTAMP | |

**Indexes:** table_name, source, created_at

---

## 17. suggested_fixes

**Migration:** `database/migrations/028_audit_log.sql`
**หน้าที่:** คำแนะนำจาก auto_analyzer (add_mapping, add_rule, etc.) สำหรับ admin review
**ใช้โดย:** `AutoAnalyzer`, Admin Agent

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK | auto | |
| fix_type | Text | NOT NULL | — | add_mapping / add_rule / add_example / update_instruction |
| params | Text | NOT NULL | — | JSON: tool parameters ที่จะส่งถ้า approve |
| confidence | Real | NOT NULL | 0.0 | Confidence 0.0-1.0 |
| reason | Text | | NULL | เหตุผลที่แนะนำ |
| source_query_ids | Text | | NULL | JSON array: chat_ids ที่ trigger |
| status | Text | NOT NULL | 'pending' | pending / approved / rejected / auto_applied |
| reviewed_by | Integer | | NULL | User ID ที่ review |
| reviewed_at | Timestamp | | NULL | |
| applied_audit_id | Integer | | NULL | FK → config_audit_log.id (หลัง apply) |
| created_at | Timestamp | | CURRENT_TIMESTAMP | |

**Index:** status

---

## 18. data_warnings

**Model:** `app/models/schema_models.py` — class `DataWarningModel(ConfigBase)`
**หน้าที่:** คำเตือนเกี่ยวกับ data quality (แทน hardcoded DATA_WARNINGS)

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| code | String(50) | UNIQUE, NOT NULL | — | Warning code |
| keywords | Text | NOT NULL | — | JSON array: keywords ที่ trigger warning |
| exclude_keywords | Text | nullable | NULL | JSON array: keywords ที่ยกเว้น |
| columns_to_check | Text | NOT NULL | — | JSON array: columns ที่ต้องเช็ค |
| message | Text | NOT NULL | — | ข้อความเตือน |
| severity | String(20) | | 'warning' | warning / error / info |
| context_name | String(100) | nullable | NULL | NULL = ทุก context |
| is_active | Boolean | | True | |
| created_at | DateTime | | utcnow | |
| updated_at | DateTime | | utcnow | auto-update |

---

## 19. query_complexity_patterns

**Model:** `app/models/schema_models.py` — class `QueryComplexityPattern(ConfigBase)`
**หน้าที่:** Regex patterns สำหรับจำแนก query complexity (simple/complex) เพื่อเลือก model tier

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | Integer | PK, indexed | auto | |
| tier | String(20) | NOT NULL | — | simple / complex |
| pattern | Text | NOT NULL | — | Regex pattern |
| description | Text | nullable | NULL | คำอธิบาย pattern |
| is_active | Boolean | | True | |
| created_at | DateTime | | utcnow | |

**Unique:** (tier, pattern)

---

## Entity Relationship Summary

```
app.db:
  users ─┬─< user_sessions
         ├─< chat_history ──< user_feedback
         ├─< conversations ──< chat_history
         │                    └── chat_session_data
         └─< admin_agent_conversations ──< admin_agent_messages
  otp_requests (standalone)
  trending_queries (standalone)
  api_keys ──< api_key_usage

config.db:
  ai_providers ──< ai_models
  admin_config (standalone key-value)
  config_audit_log ←── suggested_fixes
  data_warnings (standalone)
  query_complexity_patterns (standalone)
  + SQL-gen tables (see DATABASE_TABLES_GUIDE.md)
```

---

## API Endpoints Reference

### app.db endpoints (ใช้ `get_db()`)

| Endpoint | Table(s) | Description |
|---|---|---|
| POST /api/v1/auth/* | users, user_sessions, otp_requests | Authentication |
| GET/POST /api/v1/chat/* | chat_history, conversations, chat_session_data | Chat queries |
| POST /api/v1/query | chat_history | Simplified query API |
| GET/POST /api/v1/feedback/* | user_feedback | User feedback |
| GET /api/v1/admin/query-logs | chat_history | Query log viewer |
| GET /api/v1/admin/stats | chat_history, user_feedback | Dashboard stats |
| GET/POST /api/v1/admin/api-keys | api_keys, api_key_usage | API key management |
| GET/POST /api/v1/admin-agent/* | admin_agent_conversations, admin_agent_messages | Admin Agent |

### config.db endpoints (ใช้ `get_config_db()`)

| Endpoint | Table(s) | Description |
|---|---|---|
| GET/PUT /api/v1/admin/config/ai | admin_config | AI provider config |
| GET /api/v1/admin/config/ai/providers | admin_config, ai_providers, ai_models | Active providers list |
| GET /api/v1/admin/audit-log | config_audit_log | Audit trail |
| GET /api/v1/admin/suggested-fixes | suggested_fixes | Auto-analyzer suggestions |

---

## Version History

| Date | Version | Changes |
|---|---|---|
| 2026-03-22 | 1.0 | Initial — all app.db + config.db non-SQL-gen tables |

# AI Assistant — Master Test Plan (All Plans)

**Date:** 2026-03-19  
**Project Root:** `/Users/seal/Documents/GitHub/AI/`  
**สถานะปัจจุบัน:** 194 passed, 15 failed (pre-existing)

---

## Test Infrastructure ที่มีอยู่

```
tests/
├── conftest.py                        # fixtures: db_session, test_user, admin_user, client, authenticated_client
├── unit/
│   ├── test_ai_service.py             # ← 11 tests (10 fail: validate_sql ถูกลบ, 1 fail: mock ผิด)
│   ├── test_auth_service.py
│   ├── test_context_onboarding.py     # 26 tests (all pass)
│   ├── test_dimension_detector.py
│   ├── test_feedback_service.py       # ← 2 tests fail: PromptVersion ถูกลบ
│   ├── test_normalize_question.py
│   ├── test_otp_service.py
│   └── test_phase_completion.py       # ← 2 tests fail: PromptManager/PromptVersion ถูกลบ
├── integration/
│   ├── test_api.py
│   └── test_onboarding_api.py         # 10 tests (all pass)
└── pytest.ini                         # asyncio_mode=auto, -v --tb=short
```

**Convention:** `pytest.mark.asyncio` ไม่ต้องใส่ (asyncio_mode=auto), ใช้ fixtures จาก conftest.py, mock LLM ทุกครั้ง (ไม่เสีย token ใน test)

---

## Plan 0: Fix Legacy Tests

### เป้าหมาย: 209/209 passed → 0 failed

**ไฟล์ test:** แก้ไขที่มีอยู่ (ไม่สร้างใหม่)

| Test File | Tests ที่ fail | สาเหตุ | วิธีแก้ |
|-----------|---------------|--------|---------|
| `unit/test_ai_service.py` | 10 (TestAIServiceValidation) | `validate_sql()` ถูกลบจาก AIService | grep หาว่า validate_sql อยู่ที่ไหน → ย้าย tests หรือลบ |
| `unit/test_ai_service.py` | 1 (test_generate_sql_with_tool_use) | mock `Anthropic` sync แต่ code ใช้ `AsyncAnthropic` | แก้ mock ให้ตรง async client |
| `unit/test_feedback_service.py` | 2 (TestPromptVersion) | `PromptVersion` model ถูกลบ | ลบ class TestPromptVersion ทั้ง class |
| `unit/test_phase_completion.py` | 2 (test_prompt_manager_exists, test_feedback_models_exist) | `PromptManager` service + `PromptVersion` import ถูกลบ | ลบ/แก้ 2 tests |

### Claude Code Instructions

```
1. grep -rn "validate_sql" app/ --include="*.py" | grep -v __pycache__
   → ถ้าพบใน query_engine.py → สร้าง tests/unit/test_query_engine.py ย้าย tests ไป
   → ถ้าไม่พบ → ลบ class TestAIServiceValidation

2. แก้ test_generate_sql_with_tool_use:
   - patch('anthropic.AsyncAnthropic') แทน patch('anthropic.Anthropic')
   - mock client.messages.create เป็น AsyncMock
   
3. ลบ class TestPromptVersion จาก test_feedback_service.py

4. แก้ test_phase_completion.py:
   - test_prompt_manager_exists → ลบ
   - test_feedback_models_exist → ลบ import PromptVersion, ตรวจเฉพาะ models ที่มี

5. รัน: python -m pytest tests/ -v --tb=short
6. เป้าหมาย: 0 failed
```

---

## Plan 1: Admin Agent

### Test Files ที่ต้องสร้าง

```
tests/unit/test_admin_tools.py         # แต่ละ admin tool
tests/unit/test_admin_agent.py         # dispatcher logic
tests/integration/test_admin_agent_api.py  # API endpoint
```

### Unit Tests: Admin Tools (`test_admin_tools.py`)

| Test | Tool | ทดสอบอะไร |
|------|------|----------|
| `test_search_mappings_found` | SearchMappingsTool | ค้นหา keyword ที่มี → พบ |
| `test_search_mappings_not_found` | SearchMappingsTool | ค้นหา keyword ที่ไม่มี → empty |
| `test_add_mapping_success` | AddMappingTool | เพิ่ม mapping ใหม่ → success |
| `test_add_mapping_duplicate` | AddMappingTool | เพิ่ม keyword ที่มีอยู่แล้ว → error |
| `test_search_rules_by_severity` | SearchRulesTool | filter by severity → ได้ rules ที่ตรง |
| `test_add_rule_success` | AddRuleTool | เพิ่ม rule → success + cache refreshed |
| `test_add_rule_duplicate_code` | AddRuleTool | rule_code ซ้ำ → error |
| `test_search_examples` | SearchExamplesTool | ค้นหา golden examples |
| `test_add_example` | AddExampleTool | เพิ่ม example → success |
| `test_refresh_cache` | RefreshCacheTool | เรียก refresh → success |
| `test_list_contexts` | ListContextsTool | list → ได้ contexts จาก DB |

**Fixtures ที่ต้องเพิ่มใน conftest.py:**
```python
@pytest.fixture
def business_db_with_config(tmp_path):
    """Temp SQLite business DB with config tables + sample data"""
    # สร้าง schema_contexts, schema_metadata, schema_business_rules,
    # golden_examples, schema_semantic_mapping + sample rows
```

### Unit Tests: Admin Agent Dispatcher (`test_admin_agent.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_agent_selects_search_mapping_tool` | ถาม "มี mapping สำหรับ datacom ไหม" → LLM เลือก search_mappings |
| `test_agent_selects_add_mapping_tool` | ถาม "เพิ่ม mapping datacom ไป service_group" → LLM เลือก add_mapping |
| `test_agent_asks_confirmation_before_add` | add tool ที่ requires_confirmation → agent ถาม confirm |
| `test_agent_executes_after_confirmation` | ตอบ "ใช่" → agent execute tool |
| `test_agent_direct_answer` | ถาม "MCP คืออะไร" → agent ตอบตรง ไม่เรียก tool |
| `test_agent_no_suitable_tool` | ถาม "ช่วยสั่งอาหาร" → agent บอกทำไม่ได้ |
| `test_agent_search_before_add` | LLM ถูก instruct ให้ search ก่อน add → verify tool call order |
| `test_agent_saves_conversation` | หลัง chat → conversation + messages ถูกบันทึก |

**Mock strategy:** mock LLM response ให้ return tool_call ที่ต้องการ ไม่เรียก LLM จริง

### Integration Tests: API (`test_admin_agent_api.py`)

| Test | Endpoint | ทดสอบอะไร |
|------|----------|----------|
| `test_agent_chat_no_auth` | POST /admin/agent/chat | ไม่มี auth → 401 |
| `test_agent_chat_user_role` | POST /admin/agent/chat | user ธรรมดา → 403 |
| `test_agent_chat_admin_success` | POST /admin/agent/chat | admin + message → 200 + response |
| `test_agent_chat_with_conversation_id` | POST /admin/agent/chat | ส่ง conversation_id → ใช้ history |
| `test_agent_confirm_action` | POST /admin/agent/confirm | confirm pending action → execute |

### Frontend Manual Tests

```
[ ] เปิดหน้า Admin Agent
[ ] พิมพ์ "มี mapping สำหรับ datacom ไหม" → ได้คำตอบ
[ ] พิมพ์ "เพิ่ม mapping datacom ไป service_group" → agent ถาม confirm
[ ] กด confirm → mapping ถูกเพิ่ม
[ ] ไปหน้า Mappings → เห็น datacom mapping ใหม่
[ ] พิมพ์ "ดู query ที่ fail สัปดาห์นี้" → ได้รายงาน
[ ] พิมพ์ "onboard view v_new_table" → agent เรียก onboarding
```

---

## Plan 1B: MCP Consolidation

### Test Files

```
tests/unit/test_validation_service.py      # Phase A
tests/unit/test_admin_mcp.py               # Phase B
```

### Phase A: ValidationService (`test_validation_service.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_validate_sql_safe_select` | SELECT query → valid |
| `test_validate_sql_blocks_drop` | DROP TABLE → invalid + "Dangerous operation" |
| `test_validate_sql_blocks_insert` | INSERT → invalid |
| `test_validate_sql_blocks_injection` | `'; DROP TABLE` → invalid |
| `test_validate_sql_empty` | empty string → invalid |
| `test_validate_sql_multiple_statements` | 2 statements (;) → invalid |
| `test_check_rules_from_db` | business rules จาก DB ถูก check → violations/warnings |
| `test_check_rules_no_hardcoded` | ลบ BUILTIN_RULES แล้ว → rules มาจาก DB เท่านั้น |
| `test_detect_warnings_delegates` | ValidationService.detect_warnings() → WarningDetector.detect() ถูกเรียก |
| `test_seed_migration_inserts_rules` | รัน migration → 7 rules อยู่ใน schema_business_rules |

### Phase A: MCP Thin Wrapper

| Test | ทดสอบอะไร |
|------|----------|
| `test_mcp_validate_sql_delegates` | MCP validate_sql() → เรียก ValidationService.validate_sql() |
| `test_mcp_check_rules_delegates` | MCP check_business_rules() → เรียก ValidationService.check_business_rules() |
| `test_mcp_no_builtin_rules` | BUILTIN_RULES ไม่มีใน nt_validation_mcp.py อีกต่อไป |

### Phase B: Admin MCP (`test_admin_mcp.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_admin_mcp_search_mappings` | เรียก MCP tool → delegate ไป admin tool → ได้ผลลัพธ์ |
| `test_admin_mcp_add_mapping` | เรียก MCP tool → delegate ไป admin tool → mapping ถูกเพิ่ม |
| `test_admin_mcp_tools_registered` | MCP server มี tools ครบตามที่กำหนด |
| `test_admin_mcp_auto_discovered` | mcp_client.py detect nt_admin_mcp.py ได้ |

---

## Plan 2: Feedback + Query Log Enhancement

### Test Files

```
tests/unit/test_feedback_enhanced.py
tests/integration/test_feedback_api.py      # เพิ่ม tests ใน file ที่มี หรือสร้างใหม่
```

### Unit Tests (`test_feedback_enhanced.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_query_log_includes_sql` | query-logs endpoint คืน generated_sql (ไม่ truncate) |
| `test_query_log_includes_feedback` | query-logs endpoint join feedback rating |
| `test_query_log_filter_thumbs_down` | filter feedback_rating → เฉพาะ thumbs down |
| `test_query_log_filter_context` | filter context → เฉพาะ context ที่ระบุ |
| `test_feedback_detail_includes_sql` | GET feedback-details/{id} → มี generated_sql |
| `test_query_analytics_period` | GET query-analytics?period=7d → aggregated stats |
| `test_query_analytics_error_rate` | error_rate คำนวณถูก (errors / total) |
| `test_query_analytics_top_failed_keywords` | top_failed_keywords sort ถูกต้อง |

### Integration Tests (`test_feedback_api.py`)

| Test | Endpoint | ทดสอบอะไร |
|------|----------|----------|
| `test_query_logs_with_feedback_join` | GET /admin/query-logs?feedback_only=true | คืนเฉพาะ queries ที่มี feedback |
| `test_feedback_detail_endpoint` | GET /admin/feedback-details/{id} | คืน full ChatHistory + feedback |
| `test_query_analytics_endpoint` | GET /admin/query-analytics | คืน aggregated stats |
| `test_query_analytics_requires_admin` | GET /admin/query-analytics (no auth) | 401 |

### Frontend Manual Tests

```
[ ] หน้า Feedback → คอลัมน์ "Generated SQL" แสดงข้อมูล (ไม่ใช่ว่าง)
[ ] หน้า Feedback → Filter "Thumbs Down Only" ทำงาน
[ ] หน้า Feedback → คลิกแถว → modal แสดง full details + SQL
[ ] หน้า Query Logs → Summary cards แสดง total, error rate, thumbs down rate
[ ] หน้า Query Logs → Filter by context ทำงาน
[ ] หน้า Query Logs → Filter by date range ทำงาน
```

---

## Plan 3: Self-Learning Loop

### Test Files

```
tests/unit/test_dedup_engine.py
tests/unit/test_auto_analyzer.py
tests/unit/test_config_gc.py
tests/unit/test_audit_service.py
tests/integration/test_auto_fix_api.py
```

### Dedup Engine (`test_dedup_engine.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_exact_duplicate_mapping` | keyword ตรงกัน → has_duplicate=True, type="exact" |
| `test_case_insensitive_duplicate` | "Datacom" vs "datacom" → has_duplicate=True, type="case" |
| `test_no_duplicate` | keyword ใหม่ → has_duplicate=False |
| `test_conflict_detection` | keyword เดียวกัน map ไป column ต่างกัน → type="conflict" |
| `test_rule_duplicate_by_code` | rule_code ซ้ำ → has_duplicate=True |
| `test_example_duplicate_similar_question` | question คล้ายกัน → warn |
| `test_example_duplicate_exact_sql` | SQL ตรงกัน → has_duplicate=True |

### Auto-Analyzer (`test_auto_analyzer.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_analyze_single_query` | วิเคราะห์ query เดียว → diagnosis + suggested fixes |
| `test_group_similar_failures` | 5 queries คล้ายกัน → grouped เป็น 1 group |
| `test_suggested_fix_add_mapping` | diagnosis = "wrong column" → fix_type="add_mapping" |
| `test_suggested_fix_add_rule` | diagnosis = "missing rule" → fix_type="add_rule" |
| `test_confidence_high_auto_apply` | confidence ≥ 0.8 → auto_applicable=True |
| `test_confidence_low_queue_review` | confidence < 0.8 → auto_applicable=False |
| `test_no_failures_returns_empty` | ไม่มี failed queries → empty list |

**Mock strategy:** mock LLM response สำหรับ diagnosis, mock ChatHistory สำหรับ failed queries

### Garbage Collector (`test_config_gc.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_find_unused_mappings` | mapping ที่ keyword ไม่เคยปรากฏใน query logs → flagged |
| `test_find_unused_rules` | rule ที่ไม่เคย trigger → flagged |
| `test_find_conflicting_mappings` | 2 mappings keyword เดียวกัน condition ต่างกัน → flagged |
| `test_find_low_usage_examples` | example ที่ usage_count=0 หลัง 30 วัน → flagged |
| `test_gc_does_not_delete` | GC flag เท่านั้น ไม่ delete → verify DB unchanged |

### Audit Service (`test_audit_service.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_log_manual_add` | admin เพิ่ม mapping → audit log source="manual" |
| `test_log_auto_add` | auto-analyzer apply → audit log source="auto_analyzer" |
| `test_log_agent_add` | admin agent เพิ่ม → audit log source="admin_agent" |
| `test_log_contains_old_new_values` | update → audit log มี old_value + new_value |

### Integration Tests (`test_auto_fix_api.py`)

| Test | Endpoint | ทดสอบอะไร |
|------|----------|----------|
| `test_get_pending_fixes` | GET /admin/auto-analyzer/pending | list pending fixes |
| `test_approve_fix` | POST /admin/auto-analyzer/{id}/approve | approve → apply + audit log |
| `test_reject_fix` | POST /admin/auto-analyzer/{id}/reject | reject → mark reviewed |
| `test_approve_requires_admin` | POST (no auth) | 401 |

---

## Plan 4: Telegram Interface

### Test Files

```
tests/unit/test_telegram_dispatcher.py
tests/unit/test_telegram_auth.py
tests/unit/test_telegram_formatters.py
tests/unit/test_chart_renderer.py
tests/integration/test_telegram_webhook.py
```

### Telegram Dispatcher (`test_telegram_dispatcher.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_dispatch_help_command` | /help → แสดง commands (zero token) |
| `test_dispatch_context_command` | /context revenue → เปลี่ยน context |
| `test_dispatch_free_text_query` | "รายได้รวมปี 68" → QueryEngine.query() ถูกเรียก |
| `test_dispatch_admin_command` | admin ส่ง "เพิ่ม mapping" → AdminAgent.chat() ถูกเรียก |
| `test_dispatch_admin_blocked_for_user` | user ธรรมดาส่ง admin command → rejected |
| `test_dispatch_unregistered_user` | chat_id ไม่มีใน DB → "กรุณาลงทะเบียน" |

### Telegram Auth (`test_telegram_auth.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_start_command_asks_email` | /start → bot ถาม email |
| `test_email_lookup_found` | ส่ง email ที่มี → ส่ง OTP |
| `test_email_lookup_not_found` | ส่ง email ที่ไม่มี → "ไม่พบ email" |
| `test_otp_verify_success` | OTP ถูก → update telegram_chat_id + "ลงทะเบียนสำเร็จ" |
| `test_otp_verify_wrong` | OTP ผิด → "OTP ไม่ถูกต้อง" |
| `test_already_registered` | /start ซ้ำ → "คุณลงทะเบียนแล้ว" |

### Formatters (`test_telegram_formatters.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_format_table_data` | data rows → monospace table string |
| `test_split_long_message` | message > 4096 chars → split เป็นหลาย messages |
| `test_format_error_message` | error → user-friendly Thai message |
| `test_format_markdown_escape` | Telegram markdown special chars ถูก escape |

### Chart Renderer (`test_chart_renderer.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_render_bar_chart` | bar data → PNG bytes (ไม่ empty, ไม่ crash) |
| `test_render_line_chart` | line data → PNG bytes |
| `test_render_pie_chart` | pie data → PNG bytes |
| `test_render_empty_data` | empty data → graceful error (ไม่ crash) |

### Integration Tests (`test_telegram_webhook.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_webhook_wrong_secret` | POST webhook with wrong secret → 403 |
| `test_webhook_valid_message` | POST valid update → 200 + message processed |
| `test_health_endpoint` | GET /health → status ok |

### Manual Tests (ต้องรัน bot จริง)

```
[ ] /start → ลงทะเบียนด้วย email + OTP
[ ] "รายได้รวมปี 68" → ได้คำตอบ + ตาราง
[ ] "ค่าใช้จ่ายกลุ่ม mobile" → ได้คำตอบ context=expense
[ ] "แสดงเป็น bar chart" → ได้รูป PNG
[ ] /context → แสดง contexts ที่มี
[ ] /help → แสดง commands
[ ] Admin: "เพิ่ม mapping xxx" → admin agent ทำงาน
[ ] User ทั่วไป: "เพิ่ม mapping xxx" → ถูก reject
```

---

## Plan 4B: OpenMiniCrew Readiness

### Test Files

```
tests/unit/test_api_key_service.py
tests/unit/test_simple_query.py
tests/integration/test_api_key_auth.py
tests/integration/test_query_endpoint.py
```

### API Key Service (`test_api_key_service.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_create_api_key` | สร้าง key → return raw key (ntai_ prefix) + hash stored |
| `test_validate_api_key_success` | key ที่ valid → return user |
| `test_validate_api_key_expired` | key ที่หมดอายุ → rejected |
| `test_validate_api_key_revoked` | key ที่ถูก revoke → rejected |
| `test_validate_api_key_wrong` | key ที่ไม่มี → rejected |
| `test_revoke_api_key` | revoke → is_active=False |
| `test_track_usage` | เรียก API → usage log ถูกบันทึก |
| `test_rate_limit_per_minute` | เรียกเกิน 30/min → blocked |
| `test_rate_limit_per_day` | เรียกเกิน 1000/day → blocked |

### Simple Query Endpoint (`test_simple_query.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_simple_query_text_format` | format="text" → plain text answer |
| `test_simple_query_with_data` | include_data=true → data rows included |
| `test_simple_query_without_data` | include_data=false → data=null |
| `test_simple_query_with_sql` | include_sql=true → SQL included |
| `test_simple_query_max_rows` | max_rows=5 → data truncated to 5 |
| `test_simple_query_auto_context` | ไม่ระบุ context → auto-detect |
| `test_simple_query_no_conversation` | ไม่สร้าง conversation record |
| `test_simple_query_saves_chat_history` | ChatHistory ถูกบันทึก (audit trail) |

### Integration Tests: API Key Auth (`test_api_key_auth.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_chat_with_api_key` | X-API-Key header → เข้าถึง /chat/ ได้ |
| `test_query_with_api_key` | X-API-Key header → เข้าถึง /query/ ได้ |
| `test_session_token_still_works` | X-Session-Token → ยังใช้ได้เหมือนเดิม |
| `test_both_headers_api_key_wins` | ส่งทั้ง X-API-Key + X-Session-Token → API key ถูกใช้ |
| `test_no_auth_rejected` | ไม่มี header ใด → 401 |
| `test_admin_endpoints_need_admin_key` | API key scope=query → admin endpoints rejected |

### Integration Tests: Query Endpoint (`test_query_endpoint.py`)

| Test | Endpoint | ทดสอบอะไร |
|------|----------|----------|
| `test_query_basic` | POST /query/ + API key | ได้ answer, context, execution_time |
| `test_query_with_context` | POST /query/ context="expense" | ใช้ expense context |
| `test_query_error_handling` | POST /query/ invalid question | error field มีค่า ไม่ crash |
| `test_query_contexts_public` | GET /query/contexts | list contexts (ไม่ต้อง auth?) |

### Frontend Manual Tests

```
[ ] หน้า API Keys → สร้าง key → key แสดงครั้งเดียว
[ ] คัดลอก key → ใช้ curl เรียก /query/ → ได้ผลลัพธ์
[ ] หน้า API Keys → Revoke key → เรียก API อีกครั้ง → 401
[ ] หน้า API Keys → Usage stats แสดงจำนวนครั้งที่เรียก
```

---

## Plan 5: DB Separation

### Test Files

```
tests/unit/test_db_separation.py
tests/integration/test_migration_script.py
```

### Unit Tests (`test_db_separation.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_config_db_session_factory` | CONFIG_DB_URL → สร้าง session ได้ |
| `test_business_db_adapter_sqlite` | adapter สำหรับ SQLite ทำงาน |
| `test_business_db_adapter_query` | execute_query → return rows |
| `test_business_db_adapter_schema` | get_schema → return columns |
| `test_schema_service_uses_config_db` | SchemaService ดึง contexts จาก config.db |
| `test_onboarding_uses_both_dbs` | inspect → business DB, apply → config DB |
| `test_list_views_no_config_tables` | list_available_views() ไม่ต้อง filter config tables อีก (เพราะ config อยู่คนละ DB) |

### Migration Script (`test_migration_script.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_migration_copies_all_data` | schema_contexts rows ใน source = destination |
| `test_migration_all_tables_moved` | 15 config tables ถูกสร้างใน config.db |
| `test_migration_source_tables_dropped` | config tables ถูกลบจาก business DB |
| `test_migration_rollback` | ถ้า fail → source DB ไม่ถูกแก้ |
| `test_app_works_after_migration` | QueryEngine ทำงานปกติหลัง migrate |

### Manual Tests

```
[ ] รัน migration script → ไม่ error
[ ] Business DB มีแค่ business tables/views
[ ] Config DB มี 15 config tables
[ ] App DB ไม่เปลี่ยน (users, sessions, etc.)
[ ] ถามคำถามบน web → ผลลัพธ์ถูกต้อง
[ ] Admin CRUD → ทำงานปกติ
[ ] Context Onboarding → ทำงานปกติ
```

---

## Plan 6: SaaS Architecture

### Test Files

```
tests/unit/test_tenant_service.py
tests/unit/test_tenant_middleware.py
tests/integration/test_tenant_api.py
tests/integration/test_tenant_isolation.py
```

### Tenant Service (`test_tenant_service.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_create_tenant` | สร้าง tenant → id, slug, config_db_path |
| `test_create_tenant_duplicate_slug` | slug ซ้ำ → error |
| `test_get_tenant_by_slug` | lookup by slug → ได้ tenant |
| `test_tenant_db_isolation` | 2 tenants → config_db_path ต่างกัน |
| `test_upload_csv_creates_sqlite` | upload CSV → SQLite file ถูกสร้าง |
| `test_upload_auto_onboards` | upload → Context Onboarding ถูกเรียก |

### Tenant Middleware (`test_tenant_middleware.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_middleware_extracts_tenant` | X-API-Key → request.state.tenant set |
| `test_middleware_invalid_key` | bad API key → 401 |
| `test_middleware_inactive_tenant` | inactive tenant → 403 |
| `test_middleware_sets_db_sessions` | request.state.config_db + business_db set |

### Tenant Isolation (`test_tenant_isolation.py`)

| Test | ทดสอบอะไร |
|------|----------|
| `test_tenant_a_cannot_see_tenant_b_data` | query tenant A → ไม่เห็น data ของ tenant B |
| `test_tenant_a_cannot_see_tenant_b_config` | contexts ของ A ≠ contexts ของ B |
| `test_tenant_query_uses_own_db` | tenant A query → ใช้ business_db ของ A |
| `test_usage_tracking_per_tenant` | tenant A query → usage log เป็นของ A |
| `test_rate_limit_per_tenant` | tenant A เกิน quota → blocked, tenant B ยังใช้ได้ |

---

## End-to-End Test Scenarios (Manual)

ทดสอบ flow ข้าม Plans — ต้องรัน backend + frontend + Telegram bot

### Scenario 1: Admin fixes "datacom" problem via Agent

```
Prerequisite: Plan 1 + Plan 2

1. User ถามบน web: "ผลดำเนินงาน กลุ่ม datacom" → ได้ SQL ผิด (ค้น business_unit แทน service_group)
2. User กด thumbs down
3. Admin เปิด Admin Agent → "ดู feedback ที่เป็น thumbs down ล่าสุด"
4. Agent แสดง: question + wrong SQL + ปัญหา
5. Admin: "datacom อยู่ใน service_group ไม่ใช่ business_unit"
6. Agent: search_mappings("datacom") → ไม่พบ → แนะนำ add
7. Admin: confirm
8. Agent: add_mapping + refresh_cache
9. User ถามอีกครั้ง: "ผลดำเนินงาน กลุ่ม datacom" → SQL ถูกต้อง (ค้น service_group)
```

### Scenario 2: Auto-Learning fixes recurring failure

```
Prerequisite: Plan 1 + Plan 2 + Plan 3

1. 5 users ถาม "รายได้ datacom" ในช่วง 24 ชม. → ทุกคำถอง fail/thumbs_down
2. Auto-analyzer (scheduled) ดึง failures → group เป็น 1 pattern
3. LLM วิเคราะห์: "datacom ถูก map ไป business_unit แต่ควรเป็น service_group"
4. confidence = 0.9 → auto-apply mapping
5. audit_log: source="auto_analyzer", confidence=0.9
6. Admin ได้ Telegram notification: "Auto-fixed: datacom → service_group"
7. User ถามอีกครั้ง → ได้ผลถูกต้อง
```

### Scenario 3: Telegram user queries data

```
Prerequisite: Plan 4 + Plan 4B

1. User /start บน Telegram → ใส่ email → OTP → ลงทะเบียนสำเร็จ
2. User: "รายได้รวมปี 68" → bot ส่งคำตอบ + ตาราง monospace
3. User: "แสดงเป็น bar chart" → bot ส่งรูป PNG
4. User: "export เป็น csv" → bot ส่งไฟล์
```

### Scenario 4: OpenMiniCrew queries AI Assistant

```
Prerequisite: Plan 4B

1. Admin สร้าง API key บน web admin
2. ตั้ง NT_AI_API_KEY ใน OpenMiniCrew .env
3. User พิมพ์ใน Telegram: "/nt รายได้ mobile ปี 68"
4. OpenMiniCrew NTQueryTool → POST /api/v1/query/ → ได้ answer
5. Telegram แสดงผลลัพธ์
```

### Scenario 5: New tenant onboarding (SaaS)

```
Prerequisite: Plan 5 + Plan 6

1. Admin สร้าง tenant "company_x" บน admin UI
2. Tenant upload CSV "sales_data.csv"
3. ระบบสร้าง SQLite + auto Context Onboarding
4. Tenant ได้ API key
5. Tenant เรียก POST /api/v1/query/ ด้วย API key: "ยอดขายรวมเดือนนี้"
6. ได้ผลลัพธ์จาก data ของ tenant
7. Tenant อื่นเรียก API เดียวกัน → ไม่เห็น data ของ company_x
```

---

## Regression Test Protocol

ทุกครั้งที่ implement Plan ใหม่เสร็จ:

```bash
# 1. Run full test suite
python -m pytest tests/ -v --tb=short

# 2. เป้าหมาย: 0 failed (หลัง Plan 0 แก้ 15 legacy tests แล้ว)

# 3. ถ้ามี failure ใหม่ → แก้ก่อน merge

# 4. Check test count เพิ่มขึ้น
# Plan 0: baseline ~209 tests → 0 failed
# Plan 1: +30 tests (admin tools + agent + API)
# Plan 1B: +15 tests (validation + MCP)
# Plan 2: +12 tests (feedback + analytics)
# Plan 3: +25 tests (dedup + analyzer + GC + audit)
# Plan 4: +20 tests (telegram + auth + formatters + chart)
# Plan 4B: +20 tests (API key + query endpoint)
# Plan 5: +12 tests (DB separation + migration)
# Plan 6: +15 tests (tenant + middleware + isolation)
# รวม: ~360 tests
```

---

## Claude Code Instructions สำหรับเขียน Tests ทุก Plan

```
## กฎทั่วไป

1. ไม่เรียก LLM จริง — mock ทุกครั้ง (ใช้ unittest.mock.patch + AsyncMock)
2. ไม่แก้ production DB — ใช้ tmp_path fixture สำหรับ temp SQLite
3. ใช้ fixtures จาก conftest.py (db_session, test_user, admin_user, client, authenticated_client)
4. asyncio_mode=auto ใน pytest.ini → ไม่ต้องใส่ @pytest.mark.asyncio
5. ตั้งชื่อ test file ตาม pattern: test_{feature}.py
6. ตั้งชื่อ test class ตาม pattern: Test{Feature}
7. ตั้งชื่อ test function ตาม pattern: test_{what_it_tests}
8. ทุก test ต้อง assert อย่างน้อย 1 อย่าง
9. ห้าม skip test แทนการแก้จริง

## Pattern สำหรับ mock LLM

async def mock_llm_tool_call(tool_name, tool_args):
    """Mock LLM ที่เลือก tool"""
    return MockResponse(
        content="",
        tool_calls=[MockToolCall(name=tool_name, args=tool_args)]
    )

async def mock_llm_direct_answer(text):
    """Mock LLM ที่ตอบตรง"""
    return MockResponse(content=text, tool_calls=[])

## Pattern สำหรับ business DB fixture

@pytest.fixture
def business_db(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    conn = sqlite3.connect(db_path)
    # สร้าง tables + insert sample data
    conn.close()
    yield db_path

## Pattern สำหรับ admin auth ใน integration test

@pytest.fixture
def admin_client(client, db_session):
    user = User(email="admin@example.com", role="admin", is_active=True)
    db_session.add(user)
    db_session.commit()
    session = UserSession(user_id=user.id, session_token="admin_token", ...)
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "admin_token"
    return client

## ลำดับ Implementation

1. Plan 0 tests → แก้ failures ก่อน (baseline clean)
2. Plan 1B Phase A tests → validation_service (standalone)
3. Plan 1 tests → admin tools + agent
4. Plan 1B Phase B tests → admin MCP
5. Plan 2 tests → feedback + analytics
6. Plan 4B tests → API key + query endpoint
7. Plan 3 tests → dedup + analyzer + GC + audit
8. Plan 4 tests → telegram
9. Plan 5 tests → DB separation
10. Plan 6 tests → tenant + isolation

## รัน tests

# ทั้งหมด
python -m pytest tests/ -v --tb=short

# เฉพาะ Plan
python -m pytest tests/unit/test_admin_tools.py -v
python -m pytest tests/unit/test_validation_service.py -v
python -m pytest tests/integration/test_admin_agent_api.py -v

# เฉพาะ test เดียว
python -m pytest tests/unit/test_admin_tools.py::TestSearchMappings::test_search_found -v
```

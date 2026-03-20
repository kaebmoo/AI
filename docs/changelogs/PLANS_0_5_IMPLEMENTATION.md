# Plans 0-5 Implementation Changelog

**Date:** 2026-03-19
**Status:** All Complete (359 tests passing)

---

## Plan 0: Fix Legacy Tests

- Fixed 15 pre-existing test failures
- Removed TestAIServiceValidation (validate_sql moved to ValidationService)
- Fixed async mock for AsyncAnthropic
- Removed obsolete PromptVersion/PromptManager tests
- Baseline: 279 tests passing

## Plan 1: Admin Agent — Tool-Calling Dispatcher

### New Files

- `app/tools/admin/{__init__, base, registry, mapping_tools, rule_tools, example_tools, onboarding_tools, analysis_tools, system_tools}.py`
- `app/services/admin_agent.py` — core dispatcher with:
  - Native function calling via generate_sql() (OpenAI tool_choice='auto')
  - Text-based fallback with JSON parsing
  - Keyword-based fallback when LLM fails to select tool
  - LLM retry with stronger instructions (max 2 retries)
  - Tool result summarization via LLM (2nd call)
- `app/api/v1/admin_agent.py` — POST /admin/agent/chat, POST confirm, GET conversations
- `app/schemas/admin_agent_schemas.py`
- `app/models/admin_agent.py`
- `database/migrations/025_admin_agent.sql`
- `frontend-admin/src/pages/AdminAgent.tsx` — chat UI with:
  - Tool call visualization with mini data tables
  - SQL truncation for readability (hover for full text)
  - Sticky headers, zebra striping, row numbers
  - Confirmation flow for destructive operations
- `frontend-admin/src/services/adminAgentService.ts`

### Admin Tools (14 tools)

| Tool | Category | Confirmation |
|------|----------|-------------|
| search_mappings | mapping | No |
| add_mapping | mapping | Yes |
| search_rules | rule | No |
| add_rule | rule | Yes |
| search_examples | example | No |
| add_example | example | Yes |
| list_contexts | system | No |
| refresh_cache | system | No |
| search_hierarchy | system | No |
| inspect_view | onboarding | No |
| validate_config | onboarding | No |
| analyze_query_logs | analysis | No |
| review_feedback | analysis | No |

## Plan 1B-A: Validation Consolidation

- Created `app/services/validation_service.py` (validate_sql, check_business_rules, calculate_confidence)
- Created `database/migrations/026_seed_builtin_rules.sql` (7 rules seeded to DB)
- Removed BUILTIN_RULES from `nt_validation_mcp.py` — delegates to ValidationService
- MCP check_business_rules now uses SessionLocal() for DB access

## Plan 1B-B: Admin MCP Server

- Created `mcp_servers/nt_admin_mcp.py` (13 MCP tools wrapping admin tools)

## Plan 2: Feedback + Query Log Enhancement

- Enhanced `GET /admin/query-logs` with feedback join and filters
- Created `GET /admin/feedback-details/{id}`
- Created `GET /admin/query-analytics` (period, error_rate, context distribution)
- Frontend `Feedback.tsx` and `QueryLogs.tsx` enhanced

## Plan 3: Self-Learning Loop

- Created `app/services/dedup_engine.py` — duplicate detection (exact, case-insensitive, conflict)
- Created `app/services/auto_analyzer.py` — analyzes failed queries, suggests fixes
- Created `app/services/config_gc.py` — finds unused mappings, conflicting entries, low-usage examples
- Created `app/services/audit_service.py` — records config changes with source tracking
- Created `database/migrations/028_audit_log.sql`
- Integrated DedupEngine into AddMappingTool + AddRuleTool

## Plan 4: Telegram Interface

- Created `app/telegram/{__init__, bot, dispatcher, handlers, formatters, auth, chart_renderer}.py`
- dispatcher: routes /start, /help, /context, free-text queries, admin commands
- auth: email OTP registration, chat_id linking, admin detection
- chart_renderer: matplotlib PNG generation (bar, line, pie) with Thai font support
- formatters: table formatting, message splitting (4096 char limit), markdown escaping
- Created `database/migrations/029_telegram_support.sql`

## Plan 4B: OpenMiniCrew Readiness

- Created `app/models/api_key.py` — API key model with hash, prefix, scopes, rate limits
- Created `app/services/api_key_service.py` — create, validate, revoke, track_usage, rate_limit
- Created `app/api/v1/query.py` — simplified stateless query endpoint:
  - `POST /query/` — question to answer (no conversation)
  - `GET /query/contexts` — public, lists available contexts
  - Proper QueryEngine integration (mcp_client, db_session)
  - Correct column names (name, display_name from schema_contexts)
- Added X-API-Key support in `app/api/deps.py` (priority: API key > session > bearer)
- API key admin endpoints: POST/GET/DELETE /admin/api-keys, GET /admin/api-keys/{id}/usage
- Created `database/migrations/027_api_keys.sql`
- Created `frontend-admin/src/pages/ApiKeys.tsx` + `apiKeyService.ts`

## Plan 5: DB Separation

- Created `app/services/business_db.py` — BusinessDBAdapter for SQLite/PostgreSQL/MSSQL
- Created `scripts/migrate_config_to_separate_db.py` — copies 15 config tables to config.db
- Supports --dry-run, --apply, --drop-source modes

## Test Coverage

- Before: 279 tests (15 failures)
- After: 359 tests (0 failures)
- New test files: 14

### New Test Files

| File | Tests |
|------|-------|
| `tests/unit/test_admin_agent.py` | Admin agent dispatcher |
| `tests/unit/test_admin_tools.py` | Tool registry + execution |
| `tests/unit/test_admin_mcp.py` | Admin MCP server |
| `tests/unit/test_validation_service.py` | SQL validation service |
| `tests/unit/test_dedup_engine.py` | Duplicate detection |
| `tests/unit/test_auto_analyzer.py` | Failed query analyzer |
| `tests/unit/test_config_gc.py` | Config garbage collector |
| `tests/unit/test_audit_service.py` | Audit trail |
| `tests/unit/test_api_key_service.py` | API key management |
| `tests/unit/test_telegram_auth.py` | Telegram OTP auth |
| `tests/unit/test_telegram_dispatcher.py` | Telegram routing |
| `tests/unit/test_telegram_formatters.py` | Message formatting |
| `tests/unit/test_chart_renderer.py` | Chart PNG generation |
| `tests/unit/test_db_separation.py` | DB migration script |
| `tests/integration/test_admin_agent_api.py` | Agent API endpoints |
| `tests/integration/test_api_key_auth.py` | API key auth flow |
| `tests/integration/test_query_endpoint.py` | /query/ endpoint |
| `tests/integration/test_telegram_webhook.py` | Telegram webhook |
| `tests/integration/test_feedback_api.py` | Feedback API |
| `tests/integration/test_auto_fix_api.py` | Auto-fix suggestions |
| `tests/integration/test_migration_script.py` | DB migration |

## Bug Fixes (Post-Verification)

- Fixed `query.py`: wrong QueryEngine constructor + parameter names
- Fixed `query.py`: wrong column names in /contexts endpoint
- Fixed MCP: ValidationService called without DB connection
- Fixed AdminAgent: text-based tool calling replaced with native function calling
- Fixed frontend: mixed value+type imports causing Vite SES errors

## Database Migrations Added

| Migration | Purpose |
|-----------|---------|
| `025_admin_agent.sql` | Agent conversations + messages tables |
| `026_seed_builtin_rules.sql` | 7 built-in validation rules |
| `027_api_keys.sql` | API keys table with hash, scopes, rate limits |
| `028_audit_log.sql` | Config change audit trail |
| `029_telegram_support.sql` | Telegram users, OTP, chat linking |

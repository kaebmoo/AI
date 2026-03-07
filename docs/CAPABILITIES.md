# NT AI Assistant — Capabilities Overview

**Last Updated:** 2026-03-06

เอกสารนี้สรุปความสามารถทั้งหมดของระบบ เพื่อให้เห็นภาพรวมว่า "ตอนนี้มีอะไรแล้วบ้าง" และ "อะไรยังไม่มี"

---

## 1. AI Query (Core Feature)

| Capability | Status | Notes |
|------------|--------|-------|
| Thai natural language → SQL | Done | Chain-of-Thought prompt |
| Multi-context support (revenue, expense, transfer price) | Done | DB-driven via `schema_contexts` |
| Auto context detection from keywords | Done | `detect_context_from_question()` |
| Context switch with history reset | Done | `_resolve_context_with_history()` |
| SQL validation via MCP | Done | `nt-validation` server |
| SQL execution via MCP | Done | `nt-query` server |
| Auto-retry on SQL error (max 3) | Done | Hybrid mode retry loop |
| Value lookup (search actual DB values) | Done | Feature flag: `value_lookup_enabled` |
| RAG context injection (Vanna) | Done | Feature flag: `rag_enabled` |
| Two-pass SQL generation (intent → SQL) | Done | Feature flag: `two_pass_enabled` |
| Extended Thinking (Claude Sonnet/Opus) | Done | Admin config |

---

## 2. AI Providers

| Provider | Status | Models |
|----------|--------|--------|
| Claude (Anthropic) | Done | claude-sonnet-4, claude-opus-4, claude-haiku-3.5 |
| Gemini (Google AI) | Done | gemini-3-flash, gemini-2.0-flash-exp |
| Matcha (NT Gateway) | Done | gpt-4.1, gpt-4o, gpt-4-turbo |
| Provider auto-discovery | Done | `registry.py` auto-discovers on import |
| Provider fallback | Done | If primary fails → try next configured |
| Tier-based model selection | Done | cheap/default/premium per provider |
| Admin enable/disable providers | Done | Web UI at `/settings` |

---

## 3. Cost Optimization

| Capability | Status | Impact | Notes |
|------------|--------|--------|-------|
| Claude Prompt Caching | Done | cached tokens 90% cheaper | `cache_control: ephemeral` |
| Query Result Cache | Done | 0 tokens for repeated questions | 5 min TTL, in-memory |
| System Prompt Cache | Done | Skip schema rebuild | 6 hour TTL |
| Request Dedup | Done | Block spam/double-click | 5 sec window |
| Tier Classification | Done | Cheap model for simple queries | Rule-based, 0 token cost |
| Gemini Implicit Caching | Automatic | Google handles internally | No code needed |

---

## 4. Conversation & Context

| Capability | Status | Notes |
|------------|--------|-------|
| Native multi-turn history | Done | LLM sees real conversation turns |
| Configurable history window | Done | `MAX_HISTORY_MESSAGES=10` |
| Context retention (REPLACE/MERGE/RESET) | Done | Rules in system prompt |
| Conversation persistence (DB) | Done | `ChatHistory` table |
| Concise assistant summaries | Done | SQL + 300 chars |
| Context switch clears history | Done | Prevents stale filters |

### Not Yet Implemented
| Capability | Priority | Notes |
|------------|----------|-------|
| History summarization/compression | Low | Sliding window + truncation is sufficient for now |
| Redis-backed conversation cache | Low | In-memory works for single-process |
| Chat history cleanup (auto-delete old) | Low | openminicrew has 30-day cleanup |

---

## 5. Data Visualization

| Capability | Status | Notes |
|------------|--------|-------|
| Auto chart type recommendation | Done | AI analyzes data and suggests |
| Bar, Line, Pie, Grouped Bar, Stacked Bar | Done | Frontend renders |
| Hierarchical table display | Done | display_hint: hierarchical |
| Crosstab table display | Done | display_hint: crosstab |
| Single value display | Done | For scalar results |
| Dimension family validation | Done | `enforce_dimension_family_rule()` |
| Time-series axis enforcement | Done | `enforce_time_series_rule()` |
| CSV export | Done | Frontend feature |

---

## 6. Schema & Metadata

| Capability | Status | Notes |
|------------|--------|-------|
| Dynamic schema from DB | Done | `schema_metadata` table |
| Semantic mapping (Thai terms → columns) | Done | `semantic_mappings` table |
| Business rules from DB | Done | `business_rules` table |
| Column descriptions (Thai) | Done | `column_descriptions` table |
| View builder (simplified SQL views) | Done | `view_column_mappings` table |
| Keyword value index | Done | Searches actual DB values |
| Multi-context schema | Done | Each context has own schema/rules |
| Dimension families | Done | `dimension_families` table |
| **Master hierarchy (DB-driven)** | Done | `master_hierarchy` + `master_hierarchy_values` |
| **Auto-extract hierarchy from data** | Done | `scripts/extract_hierarchy.py` |
| **Import master data from CSV** | Done | `scripts/import_master_data.py` |
| **Drill-down hierarchy detection** | Done | parent→WHERE, child→GROUP BY |
| **Hierarchy alias search** | Done | AI searches aliases before DB fallback |
| **Unmatched keyword learning** | Done | Logs LIKE patterns without alias match for admin review |

---

## 7. Admin System

| Capability | Status | Notes |
|------------|--------|-------|
| Admin Web UI | Done | React + Ant Design at `/settings` |
| Provider management (enable/disable/model) | Done | `admin_config` table |
| Feature flags management | Done | toggle via Admin UI |
| Golden examples management | Done | Training data review |
| Schema context management | Done | Add/edit contexts |
| Semantic mapping management | Done | Add/edit mappings |
| Metadata refresh | Done | `/api/v1/chat/refresh` |
| **Hierarchy management UI** | Done | `/hierarchy` — tree view, CRUD, diff, unmatched keywords |
| **Hierarchy API (CRUD)** | Done | 14 endpoints for levels, values, search, extract, diff |
| **Unmatched keywords review** | Done | Admin reviews AI's unresolved LIKE patterns |

---

## 8. Security & Access

| Capability | Status | Notes |
|------------|--------|-------|
| JWT authentication | Done | Token-based |
| OTP email login | Done | Configurable allowed domains |
| Role-based access (user/admin) | Done | Admin-only endpoints |
| SELECT-only SQL enforcement | Done | MCP validation |
| CORS configuration | Done | Configurable origins |

---

## 9. Infrastructure

| Capability | Status | Notes |
|------------|--------|-------|
| MCP Server architecture | Done | 3 servers: metadata, query, validation |
| SQLite support | Done | Development & small deployments |
| PostgreSQL support | Done | Production |
| MSSQL support | Partial | Via SQLAlchemy, not fully tested |
| Redis cache service | Available | `cache_service.py` exists but not integrated into query pipeline |
| Confidence scoring | Done | Via `nt-validation` MCP server |
| Warning detection | Done | Data quality warnings |

### Performance Notes

| Component | Current Load | Threshold | Action if Exceeded |
|-----------|-------------|-----------|-------------------|
| Hierarchy values | 3,475 | 50,000 | Migrate to FTS5 or alias lookup table |
| Alias search (LIKE) | 0.07-0.37ms | 5ms | Add index on aliases column |
| Hierarchy levels cache | 19 rows / 1hr TTL | 100+ contexts | Unlikely to be an issue |
| PostgreSQL migration | — | — | Add `pg_trgm` GIN index for LIKE search |

See `memory/architecture.md` § Performance and `docs/planning/MASTER_DATA_PLAN.md` § Performance for details.

---

## 10. Integrations

| Integration | Status | Notes |
|-------------|--------|-------|
| Web API (FastAPI) | Done | Primary interface |
| React Native frontend (Expo) | Done | Mobile-ready |
| Admin frontend (React + Ant Design) | Done | Desktop admin |
| OpenMiniCrew Telegram bot | Not Done | Phase 4 of refactoring plan |

---

## Architecture Diagram

```
Frontend (React Native / Admin UI)
    |
    v
FastAPI (/api/v1/chat)
    |
    v
QueryEngine (orchestrator)
    |
    +-- Provider Registry --> Claude / Gemini / Matcha
    |
    +-- SchemaService --> schema_contexts, semantic_mappings, ...
    |
    +-- AIService --> generate_content(prompt, system, history)
    |       |
    |       +-- [Cache L1] Query Result Cache (5 min)
    |       +-- [Cache L2] System Prompt Cache (6 hr)
    |       +-- [Cache L3] Claude Prompt Cache (API-level, 5 min)
    |
    +-- MCP Servers
    |       +-- nt-query (execute SQL)
    |       +-- nt-validation (validate SQL)
    |       +-- nt-metadata (schema info)
    |
    +-- WarningDetector
    +-- QueryClassifier (tier selection)
    +-- VannaService (RAG, optional)
```

---

## Changelog References

| Date | Document | Summary |
|------|----------|---------|
| 2026-03-04 | `docs/changelogs/REFACTORING_PHASE_1_2_3_5.md` | Provider extraction, QueryEngine, Tool system, Cost control |
| 2026-03-06 | `docs/changelogs/CACHING_AND_CONTEXT_IMPROVEMENTS.md` | LLM caching, native history, dedup, hierarchy detection fix |
| 2026-03-07 | `docs/changelogs/MASTER_DATA_HIERARCHY.md` | DB-driven hierarchy, master data import, auto-extract |
| — | `docs/planning/MASTER_DATA_PLAN.md` | Phase 2-4 plan: API, Admin UI, automation |
| — | `docs/ADMIN_MASTER_DATA_GUIDE.md` | Admin manual: Master Data UI usage |
| — | `docs/changelogs/CHART_TABLE_ENHANCEMENTS.md` | Chart/table display improvements |
| — | `docs/changelogs/TOOLTIP_IMPROVEMENTS.md` | UI tooltip improvements |
| — | `docs/changelogs/BUGFIX_CSV_EXPAND.md` | CSV export + expand bugfix |

# DB Separation — 3-Database Architecture

**Date:** 2026-03-21
**Status:** Complete and Live

## Overview

แยกจาก 1 DB (nt_fi_report.sqlite มีทุกอย่างปนกัน) เป็น 3 DB:

```
app.db              ← App tables (users, sessions, chats, feedback, api_keys)
config.db           ← Config tables (contexts, rules, mappings, hierarchy, admin_config)
nt_fi_report.sqlite ← Business data only (revenue, expense, transfer_price + views)
```

## ENV Configuration

```env
DATABASE_URL=sqlite:///./app.db
CONFIG_DB_URL=sqlite:///./config.db
BUSINESS_DB_PATH=./nt_fi_report.sqlite
```

## ORM Separation

- `Base` (app/db/base_class.py) → app tables only
- `ConfigBase` (app/db/base_class.py) → config tables only
- `init_db.py` → `Base.metadata.create_all(engine)` + `ConfigBase.metadata.create_all(config_engine)`

## Engine Routing

| Engine | Source | Used By |
|--------|--------|---------|
| `engine` | `DATABASE_URL` | App tables (users, sessions, chats) |
| `config_engine` | `CONFIG_DB_URL` | Config tables (contexts, rules, mappings) |
| `business_engine` | `BUSINESS_DB_PATH` | View/table inspection (SchemaService) |

## Dependency Injection

| Dependency | Returns | Used For |
|------------|---------|----------|
| `deps.get_db()` | App session | auth, chat, feedback, api_keys, query-logs |
| `deps.get_config_db()` | Config session | admin CRUD (contexts, rules, mappings, hierarchy) |
| `deps.get_schema_service()` | SchemaService(config_engine, business_engine) | Schema operations |

## AdminConfigService

`AdminConfigService()` (no params) → auto-creates `ConfigSessionLocal()` internally.
All 18+ callers in admin.py pass no DB param.

## MCP Servers

MCP servers receive `METADATA_DB_URL` env var = `BUSINESS_DB_PATH` (NOT `DATABASE_URL`).
Set in `app/services/mcp_client.py`.

## Migration Scripts

```bash
# Phase 1: Config tables → config.db
python scripts/migrate_config_to_separate_db.py --apply

# Phase 2: App tables → app.db
python scripts/migrate_app_tables.py --apply --drop-source

# Bootstrap from scratch
python scripts/init_db.py
```

## Files Changed

| File | Change |
|------|--------|
| `app/db/base_class.py` | Added `ConfigBase` |
| `app/db/session.py` | Added `config_engine`, `business_engine`, `ConfigSessionLocal`, `get_config_db()` |
| `app/config.py` | Added `CONFIG_DB_URL`, `BUSINESS_DB_PATH`, changed `DATABASE_URL` default |
| `app/api/deps.py` | Added `get_config_db()`, updated `get_schema_service()` |
| `app/api/v1/admin.py` | 57 endpoints → `get_config_db`, 7 endpoints → `get_db` (app tables) |
| `app/api/v1/query.py` | `/contexts` → `get_config_db` |
| `app/api/v1/chat.py` | SchemaService → `config_engine` + `business_engine` |
| `app/services/schema_service.py` | Added `business_engine` param, all `inspect()` → `business_engine` |
| `app/services/admin_config_service.py` | Auto `ConfigSessionLocal()` if no db param |
| `app/services/hierarchy_service.py` | `_get_db_path()` → `CONFIG_DB_URL` |
| `app/services/context_router.py` | `__init__` → `CONFIG_DB_URL` |
| `app/services/context_onboarding.py` | SQL gen matches config.db schema, applicator/validator → config DB |
| `app/providers/base.py` | `ConfigSessionLocal` for ai_models |
| `app/services/warning_detector.py` | `ConfigSessionLocal` for data_warnings |
| `app/services/query_classifier.py` | `ConfigSessionLocal` for query_complexity_patterns |
| `app/services/mcp_client.py` | Sends `BUSINESS_DB_PATH` as `METADATA_DB_URL` |
| `app/models/schema_models.py` | All models → `ConfigBase` |
| `app/models/feedback_models.py` | `GoldenExample` → `ConfigBase`, cross-DB FK removed |
| `scripts/init_db.py` | Both `Base` + `ConfigBase` create_all |
| `tests/conftest.py` | Both `Base` + `ConfigBase` in test engine |

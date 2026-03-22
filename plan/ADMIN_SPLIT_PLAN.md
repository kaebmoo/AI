# admin.py Split — Execution-Ready Plan

> File: `app/api/v1/admin.py` (2,639 lines, 95 endpoints)
> Goal: แยกเป็น package โดยไม่เปลี่ยน API path หรือ import contract
> Snapshot: 2026-03-22

---

## Current State Summary

### File Facts

```
app/api/v1/admin.py
  Lines:     ~2,639
  Endpoints: 95
  Inline helpers:
    - _ensure_metadata_rows()  (line ~948, used by dimension family endpoints)
    - _get_business_db_path()  (line ~2310, used by onboarding endpoints only)
  Inline Pydantic models:
    - APIKeyCreateRequest      (line ~2533)
    - APIKeyResponse           (line ~2540)
    - APIKeyCreateResponse     (line ~2553)
```

### Top-Level Imports (shared by all sections)

```python
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from app.api import deps
from app.services.ai_service import AIService
from app.models.user import User
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule
from app.models.feedback_models import GoldenExample
from app.schemas.admin_schemas import (...)  # large multi-line import
from app.services.schema_service import SchemaService
from app.services.admin_config_service import AdminConfigService
from app.services.query_engine import clear_query_cache
from app.config import settings
```

### Section-Level (Inline) Imports

Some sections have additional imports at the section level:

| Section | Inline Imports |
|---------|---------------|
| Dashboard Stats (~1092) | `from app.schemas.admin_schemas import DashboardStatsResponse` |
| Hierarchy (~1610) | `from app.schemas.hierarchy_schemas import (...)` |
| Hierarchy (~1610) | `from app.services.hierarchy_service import hierarchy_service` |
| Data Warnings (~1878) | `from app.models.schema_models import DataWarningModel` |
| Data Warnings (~1882) | `from app.services.warning_detector import clear_warnings_cache` |
| Query Patterns (~1988) | `from app.models.schema_models import QueryComplexityPattern` |
| Query Patterns (~1992) | `from app.services.query_classifier import clear_patterns_cache` |
| Query Logs (~2112) | `from app.models.chat import ChatHistory` |
| Query Logs (~2114) | `from app.models.feedback_models import UserFeedback, FeedbackRating` |
| Onboarding (~2340) | `from app.services.context_onboarding import ContextOnboardingService` |
| API Keys (~2530) | `from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField` |

### Services That Already Exist

These are NOT new logic — the admin endpoints delegate to them:

| Service File | What It Does |
|---|---|
| `app/services/hierarchy_service.py` | Hierarchy CRUD, search, extract, diff, unmatched |
| `app/services/admin_config_service.py` | Runtime config, feature flags, providers/models |
| `app/services/context_onboarding.py` | Inspect/analyze/generate/apply/validate pipeline |
| `app/services/api_key_service.py` | API key create/validate/revoke/track |
| `app/services/warning_detector.py` | Data warning detection + cache |
| `app/services/query_classifier.py` | Query pattern classification + cache |

### Who Imports admin.py?

| File | Import |
|---|---|
| `app/main.py` | `from app.api.v1.admin import router as admin_router` |
| Tests | Use `TestClient` against the app — no direct admin.py imports |

### Prefix Wiring in main.py

```python
app.include_router(admin_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(admin_agent_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin-agent"])
```

`admin_agent.py` shares the same `/api/v1/admin` prefix. It stays separate (not part of this refactor) but must not conflict.

---

## Target Structure

```
app/api/v1/admin/          # package replaces single file
    __init__.py             # router aggregator
    _shared.py              # shared helper functions
    schema.py               # schema columns + views + dimension families
    mappings.py             # semantic mappings CRUD
    rules.py                # business rules CRUD + toggle
    golden_examples.py      # golden examples CRUD + categories
    contexts.py             # context CRUD
    onboarding.py           # onboarding flow (inspect/apply/validate)
    config.py               # AI config + features + cache/keyword ops
    providers.py            # provider/model CRUD
    hierarchy.py            # hierarchy levels/values/extract/bootstrap/CSV/diff/unmatched
    warnings.py             # data warnings CRUD
    query_patterns.py       # query patterns CRUD
    analytics.py            # dashboard stats + refresh cache + sync brain + query logs + feedback
    api_keys.py             # API key CRUD + usage
```

Total: 14 files (12 route modules + 1 init + 1 shared)

### Endpoint Distribution

| Module | Endpoints | Lines (est.) | Key Dependencies |
|--------|-----------|------------|------------------|
| schema.py | 14 | ~360 | SchemaService, AIService, SchemaMetadata, `_ensure_metadata_rows` |
| mappings.py | 5 | ~160 | SchemaSemanticMapping, clear_query_cache |
| rules.py | 6 | ~170 | SchemaBusinessRule, clear_query_cache |
| golden_examples.py | 6 | ~170 | GoldenExample, AIService, clear_query_cache |
| contexts.py | 4 | ~80 | SchemaService, clear_query_cache |
| onboarding.py | 5 | ~240 | ContextOnboardingService, `_get_business_db_path` |
| config.py | 6 | ~230 | AdminConfigService, clear_query_cache |
| providers.py | 8 | ~230 | AdminConfigService |
| hierarchy.py | 15 | ~280 | hierarchy_service, hierarchy_schemas, clear_query_cache |
| warnings.py | 5 | ~120 | DataWarningModel, clear_warnings_cache |
| query_patterns.py | 5 | ~120 | QueryComplexityPattern, clear_patterns_cache |
| analytics.py | 6 | ~280 | ChatHistory, UserFeedback, DashboardStatsResponse, VannaService |
| api_keys.py | 4 | ~120 | APIKeyService |
| _shared.py | 0 | ~50 | Helpers: `_ensure_metadata_rows`, `_get_business_db_path` |

---

## Pre-Step: Move Inline Pydantic Models

Before splitting routes, move the 3 inline Pydantic classes out of admin.py.

### Action

Move `APIKeyCreateRequest`, `APIKeyResponse`, `APIKeyCreateResponse` to `app/schemas/admin_schemas.py`.

### Why First

These models are defined near the bottom of admin.py (line ~2530). If we split routes first, we'd have to decide which route file owns them. Moving them to the canonical schemas file first eliminates the problem.

### Changes

1. **Add** to `app/schemas/admin_schemas.py`:

```python
# ============================================================
# API Key Schemas
# ============================================================

class APIKeyCreateRequest(BaseModel):
    name: str
    scopes: str = "chat"
    rate_limit_per_minute: int = 30
    rate_limit_per_day: int = 1000

class APIKeyResponse(BaseModel):
    id: int
    key_prefix: str
    name: str
    user_id: int
    scopes: str
    rate_limit_per_minute: int
    rate_limit_per_day: int
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

class APIKeyCreateResponse(APIKeyResponse):
    raw_key: str = Field(..., description="Full API key — shown ONCE")
```

2. **Update** `admin.py` API Keys section: remove inline classes, add import:

```python
from app.schemas.admin_schemas import APIKeyCreateRequest, APIKeyResponse, APIKeyCreateResponse
```

3. **Remove** the `from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField` import

### Verify

- Run existing API key tests
- Confirm `/api/v1/admin/api-keys` endpoints work via manual test or TestClient

---

## Phase A: Core CRUD Modules

Split the simplest, most self-contained CRUD sections.

### Files to Create

#### `app/api/v1/admin/__init__.py`

```python
"""
NT AI Assistant - Admin API Package
====================================
Split from monolithic admin.py into domain-specific modules.
All endpoint paths remain unchanged.
"""
from fastapi import APIRouter

router = APIRouter()

# Phase A
from .schema import router as schema_router
from .mappings import router as mappings_router
from .rules import router as rules_router
from .golden_examples import router as golden_examples_router

router.include_router(schema_router)
router.include_router(mappings_router)
router.include_router(rules_router)
router.include_router(golden_examples_router)

# Remaining endpoints still in legacy admin.py will be added in later phases
```

#### `app/api/v1/admin/_shared.py`

```python
"""
Shared helpers for admin API modules.
"""
from sqlalchemy.orm import Session
from app.services.schema_service import SchemaService


def ensure_metadata_rows(db: Session, table_name: str, column_names: list, service: SchemaService):
    """Ensure schema_metadata rows exist for all columns in a table.
    Creates minimal rows for any missing columns.
    """
    # Copy exact logic from admin.py _ensure_metadata_rows (line ~948)
    ...


def get_business_db_path() -> str:
    """Resolve business DB path from settings.
    Used by onboarding endpoints.
    """
    # Copy exact logic from admin.py _get_business_db_path (line ~2310)
    ...
```

#### Each Route Module Pattern

Every route module follows this pattern:

```python
"""Module docstring"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
# ... module-specific imports

router = APIRouter()

# ... endpoints (copy verbatim from admin.py, no logic changes)
```

### What Moves in Phase A

| Source Lines (approx) | Target Module | Endpoints |
|---|---|---|
| 43-174 | schema.py | schema columns CRUD (5 endpoints) |
| 175-328 | mappings.py | semantic mappings CRUD (5 endpoints) |
| 329-492 | rules.py | business rules CRUD + toggle (6 endpoints) |
| 493-651 | golden_examples.py | golden examples CRUD + categories (6 endpoints) |

### Phase A — admin.py Handling

During Phase A, `admin.py` still exists and keeps all remaining endpoints. We remove the 4 sections that moved and update the router:

```python
# admin.py becomes:
# (all imports remain, minus what's no longer needed)
# (sections: schema columns, mappings, rules, golden examples REMOVED)
# (remaining sections: contexts, views, dimension families, refresh cache,
#  dashboard stats, sync brain, AI config, providers, models, hierarchy,
#  warnings, query patterns, query logs, onboarding, api_keys)

router = APIRouter()
# ... remaining endpoints
```

### Phase A — main.py Change

**IMPORTANT:** `main.py` import stays exactly the same: `from app.api.v1.admin import router as admin_router`. This works because `admin/` is now a package and `__init__.py` exports `router`.

However, since `admin.py` (the old file) and `admin/` (the new package) cannot coexist at the same path, the conversion must happen atomically:

1. Create `admin/` directory with `__init__.py` and route files
2. Move remaining content from `admin.py` into `admin/_legacy.py` (temporary)
3. Import and include `_legacy.router` in `admin/__init__.py`
4. Delete `admin.py`
5. Verify

### Phase A Checklist

```
[ ] Create app/api/v1/admin/ directory
[ ] Create app/api/v1/admin/__init__.py
[ ] Create app/api/v1/admin/_shared.py with ensure_metadata_rows, get_business_db_path
[ ] Create app/api/v1/admin/schema.py (lines 43-174 + view/dim family endpoints)
[ ] Create app/api/v1/admin/mappings.py (lines 175-328)
[ ] Create app/api/v1/admin/rules.py (lines 329-492)
[ ] Create app/api/v1/admin/golden_examples.py (lines 493-651)
[ ] Move remaining admin.py content to app/api/v1/admin/_legacy.py
[ ] Delete app/api/v1/admin.py (old file)
[ ] Wire everything in __init__.py
[ ] Verify: python -c "from app.api.v1.admin import router"
[ ] Verify: all endpoint paths unchanged (grep /schema/columns, /mappings, /rules, /golden-examples)
[ ] Run tests: pytest tests/integration/test_api.py -v
```

---

## Phase B: Contexts + Onboarding

### Files to Create

- `app/api/v1/admin/contexts.py` — context CRUD (4 endpoints, lines ~652-723)
- `app/api/v1/admin/onboarding.py` — onboarding flow (5 endpoints, lines ~2307-2529)

### Dependencies

- `contexts.py`: SchemaService, SchemaContextCreate/Update/Response/ListResponse, clear_query_cache
- `onboarding.py`: ContextOnboardingService, `_shared.get_business_db_path`, OnboardingRequest/Response, InspectRequest, ValidateRequest, ApplySqlRequest, etc.

### Phase B Checklist

```
[ ] Create contexts.py — move 4 context CRUD endpoints
[ ] Create onboarding.py — move 5 onboarding endpoints + _get_business_db_path calls
[ ] Update __init__.py to include both
[ ] Remove these sections from _legacy.py
[ ] Verify: /contexts, /contexts/onboard/* paths
[ ] Run tests: pytest tests/integration/test_onboarding_api.py -v
```

---

## Phase C: Config + Providers + API Keys

### Files to Create

- `app/api/v1/admin/config.py` — AI config, feature flags, cache clear, rebuild keyword index (6 endpoints, lines ~1157-1381)
- `app/api/v1/admin/providers.py` — provider + model CRUD (8 endpoints, lines ~1382-1604)
- `app/api/v1/admin/api_keys.py` — API key CRUD + usage (4 endpoints, lines ~2530-2639)

### Dependencies

- `config.py`: AdminConfigService
- `providers.py`: AdminConfigService
- `api_keys.py`: APIKeyService, APIKeyCreateRequest/Response/CreateResponse (now in admin_schemas.py)

### Phase C Checklist

```
[ ] Create config.py — move AI config + features + cache/keyword endpoints
[ ] Create providers.py — move provider + model CRUD
[ ] Create api_keys.py — move API key CRUD + usage
[ ] Update __init__.py
[ ] Remove from _legacy.py
[ ] Verify: /config/*, /providers/*, /api-keys/* paths
[ ] Run tests: pytest tests/integration/test_api_key_auth.py -v
```

---

## Phase D: Hierarchy + Warnings + Patterns + Analytics

### Files to Create

- `app/api/v1/admin/hierarchy.py` — all hierarchy endpoints (15 endpoints, lines ~1605-1874)
- `app/api/v1/admin/warnings.py` — data warnings CRUD (5 endpoints, lines ~1875-1984)
- `app/api/v1/admin/query_patterns.py` — query patterns CRUD (5 endpoints, lines ~1985-2093)
- `app/api/v1/admin/analytics.py` — dashboard stats, refresh cache, sync brain, clear query cache, query logs, feedback details, query analytics (6 endpoints, lines ~1061-1156 + 2094-2306)

### Dependencies

- `hierarchy.py`: hierarchy_service, hierarchy_schemas, clear_query_cache
- `warnings.py`: DataWarningModel, DataWarningCreate/Update/Response/ListResponse, clear_warnings_cache
- `query_patterns.py`: QueryComplexityPattern, QueryPatternCreate/Update/Response/ListResponse, clear_patterns_cache
- `analytics.py`: DashboardStatsResponse, ChatHistory, UserFeedback, FeedbackRating, VannaService, SchemaService

### Note on analytics.py

`analytics.py` combines several "operational" endpoints that don't fit other CRUD domains:
- `/stats` (dashboard stats)
- `/refresh-cache`
- `/sync-brain`
- `/clear-query-cache`
- `/query-logs`
- `/feedback-details/{id}`
- `/query-analytics`

These share the pattern of read-only or operational admin actions.

### Phase D Checklist

```
[ ] Create hierarchy.py
[ ] Create warnings.py
[ ] Create query_patterns.py
[ ] Create analytics.py
[ ] Update __init__.py — include all 4
[ ] Delete _legacy.py (should now be empty)
[ ] Final __init__.py should include all 12 sub-routers
[ ] Verify: all 95 endpoints respond at correct paths
[ ] Run full test suite: pytest tests/ -v
[ ] Verify admin UI still works end-to-end
```

---

## Phase E: Cleanup

```
[ ] Remove _legacy.py if still exists
[ ] Verify no dead imports in __init__.py
[ ] Verify admin_agent.py still works at same prefix (not affected)
[ ] Update ARCHITECTURE.md or project docs if they reference admin.py
[ ] Commit clean
```

---

## Final __init__.py

After all phases complete:

```python
"""
NT AI Assistant - Admin API Package
====================================
Split from monolithic admin.py into domain-specific modules.
All endpoint paths remain unchanged.
"""
from fastapi import APIRouter

router = APIRouter()

from .schema import router as schema_router
from .mappings import router as mappings_router
from .rules import router as rules_router
from .golden_examples import router as golden_examples_router
from .contexts import router as contexts_router
from .onboarding import router as onboarding_router
from .config import router as config_router
from .providers import router as providers_router
from .hierarchy import router as hierarchy_router
from .warnings import router as warnings_router
from .query_patterns import router as query_patterns_router
from .analytics import router as analytics_router
from .api_keys import router as api_keys_router

router.include_router(schema_router)
router.include_router(mappings_router)
router.include_router(rules_router)
router.include_router(golden_examples_router)
router.include_router(contexts_router)
router.include_router(onboarding_router)
router.include_router(config_router)
router.include_router(providers_router)
router.include_router(hierarchy_router)
router.include_router(warnings_router)
router.include_router(query_patterns_router)
router.include_router(analytics_router)
router.include_router(api_keys_router)
```

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Path collision from double prefix | No prefix on sub-routers. main.py adds `/api/v1/admin`. Verified in code. |
| `admin.py` file and `admin/` package can't coexist | Atomic conversion: create package, move legacy, delete old file in single commit |
| `admin_agent.py` conflict | Stays separate. Shares prefix but different tags. Not touched. |
| `clear_query_cache()` used in 25+ places | Each module imports it independently. No shared state issue. |
| `_ensure_metadata_rows` used by 2 endpoints in schema.py | Moved to `_shared.py`, imported by schema.py only |
| `_get_business_db_path` used by 5 onboarding endpoints | Moved to `_shared.py`, imported by onboarding.py only |
| Inline Pydantic models in admin.py | Moved to admin_schemas.py in pre-step |
| Tests break | Tests use TestClient, not direct imports. Path-based. Low risk. |
| Frontend calls break | Paths unchanged. No risk. |
| Import from `app.api.v1.admin` breaks | Package `__init__.py` exports `router`. Import works identically. |

---

## Effort Estimate

| Phase | Working Time | Notes |
|-------|-------------|-------|
| Pre-step | 30 min | Move Pydantic models, verify |
| Phase A | 2-3 hours | Biggest phase: create package, atomic conversion, 4 modules + shared |
| Phase B | 1 hour | 2 modules, straightforward delegation |
| Phase C | 1-1.5 hours | 3 modules, AdminConfigService patterns |
| Phase D | 1.5-2 hours | 4 modules, analytics is the most complex |
| Phase E | 30 min | Cleanup and verification |
| **Total** | **~1-1.5 working days** | Includes testing between phases |

---

## What This Plan Does NOT Cover

- Splitting `schema_service.py` (next priority, separate plan)
- Splitting `ai_service.py` (third priority, separate plan)
- Splitting frontend files (DataChart.tsx, DataTable.tsx)
- Any business logic changes
- Any API contract changes

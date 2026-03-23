# Admin Configuration System

Updated: 2026-03-23

## Overview

NT AI Assistant มีระบบจัดการ configuration แบบ dynamic ที่ให้ admin สามารถเปลี่ยนการตั้งค่า AI providers, models, features, และ Vanna knowledge ผ่าน Web UI โดยไม่ต้อง restart server หรือแก้ code

รอบล่าสุดของ admin refresh เพิ่ม runtime contract ที่ชัดขึ้นสำหรับ provider/model, dashboard view-model จาก backend จริง, และ brain sync freshness tracking สำหรับงาน Vanna/database

---

## Architecture

### 3-Tier Configuration Fallback

```
┌─────────────────────────────────────────────┐
│  Priority 1: Database (admin_config)        │  ← Admin Web UI
│  ✓ Hot-reloadable                           │
│  ✓ No server restart needed                 │
│  ✓ Centralized management                   │
└─────────────────┬───────────────────────────┘
                  │ (if config not found)
                  ↓
┌─────────────────────────────────────────────┐
│  Priority 2: .env File                      │  ← Developer/Deploy Config
│  ✓ Environment-specific                     │
│  ✓ Secret management                        │
└─────────────────┬───────────────────────────┘
                  │ (if .env not set)
                  ↓
┌─────────────────────────────────────────────┐
│  Priority 3: Hardcoded Defaults             │  ← Safety Net
│  ✓ Always available                         │
│  ✓ Matcha as default                        │
└─────────────────────────────────────────────┘
```

---

## Database Schema

### Table: `admin_config`

```sql
CREATE TABLE admin_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE,
    config_value TEXT,
    config_type TEXT,  -- 'ai_provider', 'model', 'api_key', 'feature_flag'
    category TEXT,     -- 'ai', 'database', 'features'
    display_name TEXT,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    is_sensitive INTEGER DEFAULT 0,  -- Mask in UI if 1
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);
```

**Key Configurations:**

| config_key | config_value | config_type | Description |
|------------|--------------|-------------|-------------|
| `default_ai_provider` | `matcha` | `ai_provider` | Default provider to use |
| `claude_enabled` | `true` | `ai_provider` | Enable Claude |
| `gemini_enabled` | `true` | `ai_provider` | Enable Gemini |
| `matcha_enabled` | `true` | `ai_provider` | Enable Matcha |
| `claude_model` | `claude-sonnet-4-5-20250929` | `model` | Claude model |
| `gemini_model` | `gemini-3-flash-preview` | `model` | Gemini model |
| `matcha_model` | `gpt-4.1` | `model` | Matcha model |
| `matcha_api_url` | `https://aigateway...` | `api_key` | Matcha gateway |
| `rag_enabled` | `false` | `feature_flag` | Enable RAG |
| `auto_context_detection` | `true` | `feature_flag` | Auto detect context |
| `debug_mode` | `false` | `feature_flag` | Debug mode |
| `log_queries` | `true` | `feature_flag` | Log SQL queries |

### Table: `schema_contexts`

```sql
CREATE TABLE schema_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    main_view TEXT NOT NULL,
    keywords TEXT,
    priority INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);
```

**Example Data:**

| id | name | display_name | main_view | keywords |
|----|------|--------------|-----------|----------|
| 1 | revenue | รายได้ (Revenue) | revenue_search | รายได้,revenue,ขาย,sales |
| 2 | expense | ค่าใช้จ่าย (Expense) | v_expense_mart | ค่าใช้จ่าย,expense,cost |
| 3 | transfer_price | ราคาโอน | v_transfer_price | ราคาโอน,transfer price |

Notes:
- `schema_contexts` เป็นตัวกำหนด `main_view` ของแต่ละ context และถูกใช้ทั้งใน query routing, admin onboarding, dashboard coverage, และ Vanna context summaries
- เมื่อ mutation เกิดกับ contexts, mappings, rules, schema metadata, hierarchy, golden examples, หรือ Vanna docs ระบบจะ mark `last_brain_relevant_change_at` เพื่อให้ admin เห็นว่า knowledge เปลี่ยนแล้ว

---

## Backend Implementation

### AdminConfigService

**File:** `app/services/admin_config_service.py`

**Key Methods:**

```python
class AdminConfigService:
    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get config with 3-tier fallback:
        1. Database (admin_config table)
        2. Environment variable (.env)
        3. Provided default
        """

    def set_config(self, key: str, value: str, updated_by: str) -> bool:
        """Update config in database"""

    def get_ai_config(self) -> Dict[str, Any]:
        """Get complete AI configuration"""

    def get_effective_ai_state(self) -> Dict[str, Any]:
      """Get effective runtime provider/model state for admin surfaces"""

    def get_active_providers(self) -> List[Dict[str, Any]]:
        """Get list of enabled providers"""

    def validate_provider(self, provider: str) -> bool:
        """Check if provider is valid and enabled"""
```

**Example Usage:**

```python
from app.services.admin_config_service import AdminConfigService

config_service = AdminConfigService(db)

# Get default provider (with fallback)
default_provider = config_service.get_config('default_ai_provider')
# Returns: 'matcha' (from DB, or .env, or hardcoded)

# Get active providers (only enabled ones)
providers = config_service.get_active_providers()
# Returns: [
#   {"id": "matcha", "name": "Matcha", "model": "gpt-4.1", "is_default": True},
#   {"id": "gemini", "name": "Gemini", "model": "gemini-3-flash", "is_default": False}
# ]

# Get effective runtime state used by Dashboard and QA
effective = config_service.get_effective_ai_state()
# Includes provider/model alignment, fallback usage, counts, and last_brain_sync_at
```

### Runtime Alignment Rules

- `admin_config.default_ai_provider` และ `{provider}_model` ยังเป็น runtime keys ที่ backend ใช้ตัดสิน effective provider/model
- Settings save และ provider/model CRUD จะ sync default flags กลับไปที่ `ai_providers.is_default` และ `ai_models.is_default` เพื่อลด drift ระหว่างหน้า admin
- Dashboard ใช้ `/api/v1/admin/config/ai/effective` และ `/api/v1/admin/dashboard-overview` เพื่อแสดง runtime state ที่ backend ใช้อยู่จริง

---

## API Endpoints

### Public Endpoints (No Auth Required)

**GET /api/v1/admin/config/ai/providers**

Returns active AI providers (enabled by admin)

```json
[
  {
    "id": "matcha",
    "name": "Matcha",
    "display_name": "Matcha (NT Gateway)",
    "model": "gpt-4.1",
    "icon": "leaf",
    "is_default": true
  },
  {
    "id": "gemini",
    "name": "Gemini",
    "display_name": "Gemini (Google)",
    "model": "gemini-3-flash-preview",
    "icon": "sparkles",
    "is_default": false
  }
]
```

**Purpose:** Frontend ModelSelector component calls this to display available providers

---

### Admin Endpoints (Requires Admin Auth)

**GET /api/v1/admin/config/ai**

Returns complete AI configuration

```json
{
  "ai": {
    "default_provider": "matcha",
    "claude_enabled": true,
    "gemini_enabled": true,
    "matcha_enabled": true,
    "claude_model": "claude-sonnet-4-5-20250929",
    "gemini_model": "gemini-3-flash-preview",
    "matcha_model": "gpt-4.1",
    "matcha_api_url": "https://aigateway.ntictsolution.com/v1/chat/completions"
  },
  "features": {
    "rag_enabled": false,
    "auto_context_detection": true,
    "debug_mode": false,
    "log_queries": true,
    "collect_feedback": true
  }
}
```

**PUT /api/v1/admin/config/ai**

Update AI configuration

```json
{
  "default_provider": "claude",
  "claude_enabled": true,
  "claude_model": "claude-opus-4-20250514"
}
```

**GET /api/v1/admin/config/ai/models/{provider}**

Get available models for a provider

```json
[
  "claude-sonnet-4-5-20250929",
  "claude-opus-4-20250514",
  "claude-haiku-3-5-20241022"
]
```

**POST /api/v1/admin/config/features/{feature_name}/toggle?enabled=true**

Toggle a feature flag

**POST /api/v1/admin/config/cache/clear**

Clear configuration cache

**GET /api/v1/admin/config/ai/effective**

Returns the effective runtime configuration that admin pages should trust.

```json
{
  "default_provider": {
    "id": "matcha",
    "display_name": "Matcha (NT Gateway)",
    "is_active": true
  },
  "default_model": {
    "id": "gpt-4.1",
    "display_name": "gpt-4.1",
    "is_active": true,
    "tier": "default"
  },
  "provider_source": "database",
  "fallback_in_use": false,
  "provider_alignment": true,
  "model_alignment": true,
  "active_provider_count": 3,
  "active_model_count": 8,
  "last_brain_sync_at": "2026-03-23T09:15:00"
}
```

**GET /api/v1/admin/dashboard-overview**

Returns the blended dashboard view-model used by the refreshed admin home:

- effective runtime AI state
- 7-day usage and error rates
- feedback queue and trending queries
- data admin coverage metrics
- operational alerts for drift, fallback, warnings, and review backlog

---

## Frontend Implementation

### User Interface: Dynamic Model Selector

**File:** `frontend/components/Chat/ModelSelector.tsx`

**Before (Hardcoded):**
```typescript
// ❌ Old way
const models = ['claude', 'gemini', 'matcha'];
```

**After (Dynamic):**
```typescript
// ✅ New way
useEffect(() => {
  fetch('/api/v1/admin/config/ai/providers')
    .then(res => res.json())
    .then(providers => setAvailableProviders(providers));
}, []);

// Only show providers that admin enabled
{availableProviders.map(provider =>
  <ModelButton key={provider.id} {...provider} />
)}
```

**Benefits:**
- Users only see enabled providers
- If admin disables Claude → Claude button disappears
- If admin changes default → automatically selected

---

### Admin Interface: Settings Page

**File:** `frontend-admin/src/pages/Settings.tsx`

**Built with:** React + Ant Design (TypeScript)

**Sections:**

1. **AI Provider Configuration**
   - Default Provider selector
   - Enable/disable switches for each provider
   - Model dropdown for each provider
   - Matcha API URL input

2. **Feature Flags**
   - Toggle switches for each feature
   - Description for each flag

3. **Cache Management**
   - Clear cache button

4. **Runtime Consistency**
  - Dashboard, Providers, Models, and Settings now converge on the same runtime state
  - Query invalidation refreshes Dashboard after provider/model changes

5. **Brain Operations**
  - Dashboard can trigger schema cache refresh, query cache clear, and Vanna brain sync
  - brain freshness is tracked via `last_brain_sync_at` and `last_brain_relevant_change_at`

**Screenshot:**

```
┌─────────────────────────────────────────────┐
│ Settings                                     │
├─────────────────────────────────────────────┤
│                                              │
│ AI Provider Configuration                    │
│ ┌─────────────────────────────────────────┐ │
│ │ Default Provider: [Matcha ▼]            │ │
│ │                                         │ │
│ │ ┌─ Claude (Anthropic) ────────  [✓]───┐│ │
│ │ │ Model: [claude-sonnet-4-5 ▼]        ││ │
│ │ └─────────────────────────────────────┘│ │
│ │                                         │ │
│ │ ┌─ Matcha (NT Gateway) ──────  [✓]───┐│ │
│ │ │ Model: [gpt-4.1 ▼]                  ││ │
│ │ │ API URL: [https://aigateway...]     ││ │
│ │ └─────────────────────────────────────┘│ │
│ │                                         │ │
│ │ [Save Configuration] [Reset]            │ │
│ └─────────────────────────────────────────┘ │
│                                              │
│ Feature Flags                                │
│ ┌─────────────────────────────────────────┐ │
│ │ RAG Enabled                     [✓]     │ │
│ │ Auto Context Detection          [✓]     │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

---

## Configuration Workflow

### Scenario: Change Default Provider from Gemini to Matcha

**Via Admin UI (Recommended):**

1. Login to admin panel: `http://localhost:5173/` or `http://localhost:5175/`
2. Navigate to Settings
3. Select "Matcha" in Default Provider dropdown
4. Click "Save Configuration"
5. ✅ Change takes effect immediately (no restart needed)

**Via Database (Direct):**

```sql
UPDATE admin_config
SET config_value = 'matcha',
    updated_by = 'admin@ntplc.co.th',
    updated_at = CURRENT_TIMESTAMP
WHERE config_key = 'default_ai_provider';
```

**Via .env (Fallback):**

```env
AI_PROVIDER=matcha
```

Only used if database value doesn't exist

---

### Scenario: Disable Claude for All Users

**Via Admin UI:**

1. Go to Settings
2. Toggle off "Claude (Anthropic)" switch
3. Click "Save Configuration"
4. ✅ Claude button disappears from all user interfaces

**Result:**
- Frontend ModelSelector no longer shows Claude
- `/api/v1/admin/config/ai/providers` excludes Claude
- Users cannot select Claude even if they try
- Dashboard alert state updates after save because the dashboard query is invalidated

---

### Scenario: Add New Model to Matcha

**Via Admin UI:**

1. Go to Settings
2. Find "Matcha (NT Gateway)" section
3. Select new model from dropdown (e.g., "gpt-4o")
4. Click "Save Configuration"
5. ✅ All users now use gpt-4o when selecting Matcha

### Scenario: Verify Runtime Drift Before Release

1. Open Dashboard
2. Check the runtime alignment tag in System Health
3. If a warning appears, open Providers or Models from the alert CTA
4. Save the intended defaults once through admin UI
5. Refresh Dashboard to confirm the warning disappears

---

## Testing

### Test API Endpoints

```bash
# Get active providers (public)
curl http://localhost:8000/api/v1/admin/config/ai/providers

# Get full config (admin only)
curl -H "X-Session-Token: YOUR_TOKEN" \
  http://localhost:8000/api/v1/admin/config/ai

# Update config (admin only)
curl -X PUT \
  -H "X-Session-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"default_provider": "matcha"}' \
  http://localhost:8000/api/v1/admin/config/ai
```

### Test Fallback Mechanism

```python
# Test 3-tier fallback
from app.services.admin_config_service import AdminConfigService

# 1. Test database value
assert config_service.get_config('default_ai_provider') == 'matcha'

# 2. Remove from database, should fallback to .env
db.execute("DELETE FROM admin_config WHERE config_key = 'default_ai_provider'")
assert config_service.get_config('default_ai_provider') == settings.AI_PROVIDER

# 3. Remove from .env, should fallback to default
settings.AI_PROVIDER = None
assert config_service.get_config('default_ai_provider', 'matcha') == 'matcha'
```

---

## Migration

**File:** `database/migrations/004_admin_config.sql`

**Run Migration:**

```bash
# SQLite
sqlite3 nt_fi_report.sqlite < database/migrations/004_admin_config.sql

# PostgreSQL
psql -d nt_fi_report < database/migrations/004_admin_config.sql
```

**What it creates:**
- `admin_config` table with default values
- `schema_contexts` table with default contexts
- Indexes for fast lookups
- Triggers for timestamp management
- Views for admin UI

Additional runtime/admin pieces added after the original migration:
- effective AI runtime endpoint in `app/api/v1/admin/config.py`
- dashboard overview endpoint in `app/api/v1/admin/analytics.py`
- brain dirty markers in admin mutation routes via `app/api/v1/admin/_shared.py`

---

## Best Practices

### 1. Use Admin UI for Runtime Changes

✅ **DO:** Use Settings UI to change providers/models
- No code changes
- No server restart
- Audit trail (updated_by field)

❌ **DON'T:** Hardcode configuration in code
- Requires deployment
- No flexibility

### 1.1 Trust Effective Runtime State for Cross-Page Display

✅ **DO:** Use `/api/v1/admin/config/ai/effective` or `/api/v1/admin/dashboard-overview` when a page needs the current provider/model runtime state

❌ **DON'T:** Reconstruct effective state independently on each page from mixed sources

### 2. Use .env for Secrets

✅ **DO:** Store API keys in .env
```env
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_API_KEY=AIza...
MATCHA_AI_API_KEY=sk-...
```

❌ **DON'T:** Store API keys in database (even if marked sensitive)
- Database backups may expose keys
- Use .env + secrets manager in production

### 3. Test Provider Before Enabling

✅ **DO:** Verify API key works before enabling provider
1. Test with curl/postman
2. Check provider status in Settings
3. Enable in admin UI

### 4. Clear Cache After Direct DB Changes

If you modify `admin_config` table directly (SQL):

```bash
# Call cache clear endpoint
curl -X POST \
  -H "X-Session-Token: YOUR_TOKEN" \
  http://localhost:8000/api/v1/admin/config/cache/clear
```

Or restart backend server

---

## Troubleshooting

### Issue: Users still see disabled provider

**Solution:** Clear configuration cache

```bash
curl -X POST http://localhost:8000/api/v1/admin/config/cache/clear
```

### Issue: Changes in .env not reflected

**Reason:** Database value takes priority

**Solution:** Either:

1. Remove or update the corresponding `admin_config` row
2. Clear config cache
3. Re-check `/api/v1/admin/config/ai/effective` to confirm the runtime source

### Issue: Login works on one Vite port but fails on another in development

**Reason:** `CORS_ORIGINS` does not include the active admin port

**Solution:**

1. Include both `http://localhost:5173` and `http://localhost:5175` in `CORS_ORIGINS`
2. In development, backend also allows localhost/127.0.0.1 by regex via `settings.get_cors_origin_regex()`
3. Keep explicit origins correct anyway before staging/production

### Issue: Brain sync freshness is unclear after changing mappings/rules/schema

**Solution:**

1. Check `GET /api/v1/admin/brain-sync-status` or the Dashboard sync timestamp
2. If `needs_sync=true`, trigger Sync Brain from Dashboard or Vanna Knowledge
3. Re-test Vanna-backed retrieval after sync
1. Remove from database, or
2. Update via Admin UI (which updates database)

### Issue: API returns empty providers list

**Check:**
1. All providers disabled? Enable at least one
2. Database connection issue? Check logs
3. Migration not run? Run 004_admin_config.sql

---

## Security Considerations

### API Key Protection

- `is_sensitive` flag masks values in UI
- API keys should be in .env, not database
- Admin UI shows masked input: `***********`

### Admin Authentication

- All write endpoints require admin role
- Public endpoint (`/providers`) is read-only
- Session-based authentication required

### Audit Trail

- `updated_by` field tracks who made changes
- `updated_at` timestamp for change history
- Useful for compliance and debugging

---

## Future Enhancements

### Planned Features

1. **Model Cost Tracking**
   - Log token usage per model
   - Cost analytics dashboard

2. **A/B Testing**
   - Test multiple providers side-by-side
   - Compare accuracy/performance

3. **Custom Prompt Templates**
   - Admin-configurable system prompts
   - Per-context prompt variations

4. **Provider Health Monitoring**
   - Auto-disable failing providers
   - Fallback to backup provider

5. **Multi-Database Support**
   - Connect to multiple databases
   - Switch data sources via UI

---

## References

**Files:**
- Backend: `app/services/admin_config_service.py`
- API: `app/api/v1/admin.py`
- Frontend: `frontend/components/Chat/ModelSelector.tsx`
- Admin UI: `frontend-admin/src/pages/Settings.tsx`
- Migration: `database/migrations/004_admin_config.sql`

**Documentation:**
- [README.md](../README.md)
- [CLAUDE.md](../CLAUDE.md)
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md)

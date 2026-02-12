# AI Provider and Model Management

## Overview

NT AI Assistant now supports dynamic AI provider and model management through a comprehensive admin interface. This allows administrators to add, configure, and manage multiple AI providers and their models without code changes.

## Features

- **Multiple AI Provider Support**: Configure multiple AI providers (Claude, Gemini, Matcha, etc.)
- **Dynamic Model Management**: Add and configure models for each provider
- **3-Tier Configuration Fallback**: Database → Environment Variables → Hardcoded Defaults
- **Hot-Reload Configuration**: Changes take effect immediately without server restart
- **Admin UI**: Full CRUD interface for managing providers and models
- **Priority System**: Control display order and selection preferences
- **Default Provider Selection**: Set which provider/model to use by default

## Architecture

### Configuration Layers (Priority Order)

1. **Database (Highest Priority)**
   - Tables: `ai_providers`, `ai_models`
   - Managed through Admin UI
   - Enables runtime configuration

2. **Environment Variables (Fallback)**
   - `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, etc.
   - `MATCHA_AI_API_URL`, etc.
   - Used when database config is not available

3. **Hardcoded Defaults (Safety Net)**
   - Built-in defaults ensure system always works
   - Activates only if both database and .env are unavailable

### API Key Management

**Current Implementation** (As of 2025-02-09):

API keys are **NOT stored in the database**. The system uses a 3-tier fallback for API key retrieval:

```
┌─────────────────────────────────────────────┐
│ API Key Resolution Order                    │
├─────────────────────────────────────────────┤
│ 1. Database (admin_config table)            │
│    Status: ❌ Empty (config_value = NULL)   │
│    Purpose: Reserved for future use         │
│                                             │
│ 2. Environment Variables (.env)             │
│    Status: ✅ ACTIVE (Currently Used)       │
│    Examples:                                │
│    - ANTHROPIC_API_KEY                      │
│    - GOOGLE_AI_API_KEY                      │
│    - MATCHA_AI_API_KEY                      │
│                                             │
│ 3. Hardcoded Default                        │
│    Status: ❌ None                          │
└─────────────────────────────────────────────┘
```

**Important**: The `api_key_env_var` column in `ai_providers` table stores the **name** of the environment variable (e.g., `"ANTHROPIC_API_KEY"`), **NOT** the actual API key value.

**Code Reference**: `app/services/admin_config_service.py:491-521`
```python
def get_provider_api_key(self, provider: str) -> Optional[str]:
    # Try database first (currently empty)
    api_key = self.get_config(f"{provider}_api_key", use_cache=False)

    # Fallback to environment variable
    if not api_key:
        api_key = settings.ANTHROPIC_API_KEY  # From .env

    return api_key
```

**Future Enhancement**:
See [API Key Management Plan](./API_KEY_MANAGEMENT_PLAN.md) for planned implementation of:
- Encrypted API key storage in database
- Admin UI for key management
- Key validation and testing
- Audit logging
- No server restart required for key changes

### Database Schema

#### `ai_providers` Table

```sql
CREATE TABLE ai_providers (
    id TEXT PRIMARY KEY,                    -- e.g., 'claude', 'gemini', 'matcha'
    name TEXT NOT NULL,                     -- e.g., 'Claude'
    display_name TEXT,                      -- e.g., 'Claude (Anthropic)'
    icon TEXT DEFAULT 'bulb',               -- Ionicons icon name
    is_active BOOLEAN DEFAULT 1,            -- Enable/disable provider
    is_default BOOLEAN DEFAULT 0,           -- Default provider flag
    api_key_env_var TEXT,                   -- e.g., 'ANTHROPIC_API_KEY'
    api_url_env_var TEXT,                   -- e.g., 'ANTHROPIC_API_URL'
    default_api_url TEXT,                   -- Default API endpoint
    description TEXT,
    priority INTEGER DEFAULT 0,             -- Display order (higher first)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `ai_models` Table

```sql
CREATE TABLE ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,              -- FK to ai_providers.id
    model_id TEXT NOT NULL,                 -- e.g., 'claude-3-opus-20240229'
    display_name TEXT,                      -- e.g., 'Claude 3 Opus'
    is_active BOOLEAN DEFAULT 1,
    is_default BOOLEAN DEFAULT 0,           -- Default model for provider
    context_window INTEGER,                 -- e.g., 200000
    supports_vision BOOLEAN DEFAULT 0,
    cost_per_1m_tokens REAL,               -- Cost in USD per 1M tokens
    description TEXT,
    priority INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE,
    UNIQUE(provider_id, model_id)
);
```

## Admin UI Guide

### Accessing Provider Management

1. Log in to Admin Panel: `http://localhost:3001/login`
2. Navigate to **AI Configuration → AI Providers**

### Managing Providers

#### Create New Provider

1. Click **Add Provider** button
2. Fill in the form:
   - **Provider ID**: Unique identifier (lowercase, no spaces)
   - **Name**: Short name (e.g., "Claude")
   - **Display Name**: User-friendly name (e.g., "Claude (Anthropic)")
   - **Icon**: Ionicons name (e.g., "bulb", "sparkles", "leaf")
   - **API Key Environment Variable**: Name of .env variable
   - **Priority**: Higher values appear first
   - **Active**: Toggle to enable/disable
   - **Set as Default**: Toggle to make this the default provider
3. Click **OK** to save

#### Edit Provider

1. Click **Edit** button on the provider row
2. Modify fields as needed
3. Click **OK** to save

#### Delete Provider

1. Click **Delete** button on the provider row
2. Confirm deletion
3. **Warning**: All associated models will also be deleted (CASCADE)

### Managing Models

#### Access Models Management

1. Navigate to **AI Configuration → AI Models**
2. Select a provider from the tabs

#### Create New Model

1. Select the provider tab
2. Click **Add Model** button
3. Fill in the form:
   - **Model ID**: Unique model identifier
   - **Display Name**: User-friendly name
   - **Context Window**: Maximum tokens
   - **Cost per 1M Tokens**: Pricing information
   - **Priority**: Display order
   - **Active**: Enable/disable
   - **Set as Default**: Default model for this provider
   - **Supports Vision**: Image input capability
4. Click **OK** to save

#### Edit/Delete Models

Same process as providers

## API Endpoints

### Provider Management

```
GET    /api/v1/admin/providers              # List all providers
POST   /api/v1/admin/providers              # Create provider
PUT    /api/v1/admin/providers/{id}         # Update provider
DELETE /api/v1/admin/providers/{id}         # Delete provider (CASCADE)
```

### Model Management

```
GET    /api/v1/admin/providers/{id}/models  # List models for provider
POST   /api/v1/admin/providers/{id}/models  # Create model
PUT    /api/v1/admin/models/{id}            # Update model
DELETE /api/v1/admin/models/{id}            # Delete model
```

## Configuration Examples

### Example 1: Add New Provider (OpenAI)

```sql
INSERT INTO ai_providers (id, name, display_name, icon, is_active, api_key_env_var, priority)
VALUES ('openai', 'OpenAI', 'OpenAI (GPT)', 'flash', 1, 'OPENAI_API_KEY', 40);

INSERT INTO ai_models (provider_id, model_id, display_name, is_active, is_default, context_window)
VALUES
    ('openai', 'gpt-4-turbo', 'GPT-4 Turbo', 1, 1, 128000),
    ('openai', 'gpt-4', 'GPT-4', 1, 0, 8192),
    ('openai', 'gpt-3.5-turbo', 'GPT-3.5 Turbo', 1, 0, 16385);
```

### Example 2: Disable a Provider

```sql
UPDATE ai_providers SET is_active = 0 WHERE id = 'claude';
```

### Example 3: Change Default Provider

```sql
-- Remove current default
UPDATE ai_providers SET is_default = 0 WHERE is_default = 1;

-- Set new default
UPDATE ai_providers SET is_default = 1 WHERE id = 'gemini';
```

## Integration with admin_config

The system integrates with the existing `admin_config` table:

- `admin_config.default_ai_provider` → Overrides `ai_providers.is_default`
- `admin_config.{provider}_enabled` → Overrides `ai_providers.is_active`

This ensures backward compatibility with existing configurations.

## Frontend Integration

### ModelSelector Component

The ModelSelector component automatically fetches enabled providers and displays them:

```typescript
// frontend/components/Chat/ModelSelector.tsx
const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: () => api.get('/admin/config/ai/providers')
});
```

Features:
- Auto-selects default provider on first load
- Shows only enabled providers
- Displays correct icons and names from database

## Migration Guide

### Migrating from Hardcoded Configuration

1. **Run Database Migration**:
   ```bash
   sqlite3 revenue.sqlite < database/migrations/005_dynamic_providers.sql
   ```

2. **Verify Default Data**:
   ```sql
   SELECT * FROM ai_providers;
   SELECT * FROM ai_models;
   ```

3. **Configure via Admin UI**:
   - Log in to admin panel
   - Navigate to AI Providers
   - Adjust settings as needed

4. **Test**:
   - Check user-facing app
   - Verify correct providers/models appear
   - Test provider switching

## Troubleshooting

### Issue: No providers visible in user app

**Solution**:
1. Check `ai_providers.is_active = 1`
2. Check `admin_config.{provider}_enabled = 'true'`
3. Clear config cache: `POST /api/v1/admin/config/cache/clear`

### Issue: Wrong default provider

**Solution**:
1. Check `admin_config.default_ai_provider` value
2. Update via Admin UI or SQL:
   ```sql
   UPDATE admin_config SET config_value = 'gemini' WHERE config_key = 'default_ai_provider';
   ```

### Issue: Changes not taking effect

**Solution**:
1. Refresh browser cache
2. Clear config cache via API
3. Restart backend if needed

## Best Practices

1. **Testing New Providers**:
   - Add with `is_active = 0` first
   - Test thoroughly before enabling
   - Monitor logs for errors

2. **Priority System**:
   - Use gaps (10, 20, 30...) for flexibility
   - Higher priority = appears first in UI

3. **Default Selection**:
   - Only one provider should have `is_default = 1`
   - System enforces this via triggers

4. **Model Management**:
   - Keep model_id consistent with provider's API
   - Update context_window and costs regularly
   - Document special capabilities in description

5. **Security**:
   - **API keys are NOT stored in database** (currently)
   - Use environment variables only (`.env` file)
   - Rotate keys regularly
   - See [API Key Management Plan](./API_KEY_MANAGEMENT_PLAN.md) for future encrypted database storage

## Future Enhancements

### Planned Features

- [ ] **API Key Management UI** - See [API_KEY_MANAGEMENT_PLAN.md](./API_KEY_MANAGEMENT_PLAN.md)
  - Encrypted API key storage in database
  - Admin UI for key management
  - Key validation and testing
  - Audit logging
  - No server restart required
- [ ] Model performance metrics tracking
- [ ] Automatic model discovery from providers
- [ ] Cost tracking and budgeting
- [ ] A/B testing different models
- [ ] Model fallback chains
- [ ] Rate limiting per model

## Support

For issues or questions:
- Check logs: Backend console and browser console
- Review database: `SELECT * FROM ai_providers; SELECT * FROM ai_models;`
- Contact development team with error details

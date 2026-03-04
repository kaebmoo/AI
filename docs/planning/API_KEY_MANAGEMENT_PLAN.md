# API Key Management - Implementation Plan

## Overview

Plan for implementing secure API Key management through Admin UI, allowing administrators to configure API keys for AI providers without modifying `.env` files or requiring server restarts.

---

## Current State (As-Is)

### How API Keys Work Now

```
┌─────────────────────────────────────────────┐
│ 3-Tier Fallback System                      │
├─────────────────────────────────────────────┤
│ 1. Database (admin_config)                  │
│    Status: ❌ config_value = NULL (Empty)   │
│    Priority: Highest                        │
│                                             │
│ 2. Environment Variables (.env)             │
│    Status: ✅ Active (Currently Used)       │
│    - ANTHROPIC_API_KEY                      │
│    - GOOGLE_AI_API_KEY                      │
│    - MATCHA_AI_API_KEY                      │
│    Priority: Fallback                       │
│                                             │
│ 3. Hardcoded Default                        │
│    Status: ❌ None                          │
│    Priority: Last Resort                    │
└─────────────────────────────────────────────┘
```

### Current Code Flow

**Backend**: `app/services/admin_config_service.py:491-521`
```python
def get_provider_api_key(self, provider: str) -> Optional[str]:
    key_map = {
        "claude": ("anthropic_api_key", settings.ANTHROPIC_API_KEY),
        "gemini": ("google_ai_api_key", settings.GOOGLE_AI_API_KEY),
        "matcha": ("matcha_api_key", settings.MATCHA_AI_API_KEY)
    }

    db_key, env_fallback = key_map[provider]

    # Try Database first
    api_key = self.get_config(db_key, use_cache=False)  # No cache for security

    # Fallback to Environment
    if not api_key:
        api_key = env_fallback

    return api_key
```

### Database State
```sql
-- Current state in admin_config table
SELECT config_key, config_value FROM admin_config WHERE config_key LIKE '%api_key%';

config_key            | config_value
----------------------|-------------
anthropic_api_key     | (empty/NULL)
google_ai_api_key     | (empty/NULL)
matcha_api_key        | (empty/NULL)
```

**Why empty?**
- Placeholder rows created by migration
- Prepared for future Admin UI implementation
- Currently falls back to `.env` (secure, standard practice)

---

## Problem Statement

### User Pain Points

1. **Non-technical admins can't change API keys**
   - Requires file system access to `.env`
   - Requires server restart after change
   - No validation or error feedback

2. **No visibility into current configuration**
   - Can't see which API key is active
   - Can't test if key is valid
   - No audit trail of changes

3. **Security concerns**
   - `.env` file readable by anyone with server access
   - API keys stored in plain text
   - No encryption at rest

4. **Operational overhead**
   - Must SSH to server to change keys
   - Restart required (downtime)
   - Multiple environments = multiple `.env` files to manage

---

## Proposed Solution

### Goals

1. **Admin UI for API Key Management**
   - CRUD operations through web interface
   - Secure input/storage/display
   - Real-time validation

2. **Enhanced Security**
   - Encrypt API keys in database (AES-256)
   - Mask display (show only first/last chars)
   - Audit logging (who changed what, when)
   - Role-based access control

3. **Operational Excellence**
   - No server restart required (hot-reload)
   - Test API key before saving
   - Environment fallback for safety
   - Migration path from `.env` to database

---

## Architecture Design

### 1. Database Schema Enhancement

**Option A: Use Existing `admin_config` Table**
```sql
-- Already exists, just needs values
UPDATE admin_config
SET
    config_value = encrypt_aes('sk-ant-api03-...', encryption_key),
    is_sensitive = 1,
    updated_by = 'admin@ntplc.co.th',
    metadata = '{"encrypted": true, "algorithm": "AES-256-GCM"}'
WHERE config_key = 'anthropic_api_key';
```

**Option B: Create Dedicated `api_keys` Table** (More Secure)
```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,              -- FK to ai_providers.id
    key_name TEXT NOT NULL,                 -- e.g., 'api_key', 'api_url'
    encrypted_value TEXT NOT NULL,          -- AES-256 encrypted
    encryption_version TEXT DEFAULT 'v1',   -- For key rotation
    is_active BOOLEAN DEFAULT 1,
    last_validated_at DATETIME,             -- Last time key was tested
    validation_status TEXT,                 -- 'valid', 'invalid', 'untested'
    validation_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    last_rotated_at DATETIME,
    expires_at DATETIME,                    -- Optional expiry
    FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE,
    UNIQUE(provider_id, key_name)
);

-- Audit trail
CREATE TABLE api_key_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    key_name TEXT NOT NULL,
    action TEXT NOT NULL,                   -- 'created', 'updated', 'validated', 'deleted', 'viewed'
    old_value_hash TEXT,                    -- SHA-256 hash for comparison
    new_value_hash TEXT,
    performed_by TEXT NOT NULL,
    performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN,
    error_message TEXT,
    metadata TEXT
);
```

**Recommendation**: Option B (dedicated table) for better security and auditability

### 2. Encryption Strategy

**Library**: Python `cryptography` (Fernet or AES-GCM)

```python
# app/services/encryption_service.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64

class EncryptionService:
    """Handles encryption/decryption of sensitive data"""

    def __init__(self):
        # Load encryption key from environment (NOT database)
        self.encryption_key = os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY not found in environment")

        # Initialize Fernet cipher
        self.cipher = Fernet(self.encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string"""
        if not plaintext:
            return None
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt encrypted string"""
        if not encrypted_text:
            return None
        decoded = base64.b64decode(encrypted_text.encode())
        decrypted = self.cipher.decrypt(decoded)
        return decrypted.decode()

    def hash_value(self, value: str) -> str:
        """Create SHA-256 hash for audit comparison"""
        import hashlib
        return hashlib.sha256(value.encode()).hexdigest()

# Generate encryption key (one-time setup)
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Environment Variable**:
```bash
# .env (NEVER commit this)
ENCRYPTION_KEY="your-generated-fernet-key-here"
```

### 3. Backend API Endpoints

**New Endpoints**: `app/api/v1/admin.py`

```python
# API Key Management
@router.get("/api-keys", response_model=List[dict])
def list_api_keys(current_user: User = Depends(require_admin)):
    """List all API keys (masked) for all providers"""
    # Returns: [{provider_id, key_name, masked_value, is_active, last_validated_at, validation_status}]

@router.post("/api-keys/{provider_id}", response_model=dict)
def create_or_update_api_key(
    provider_id: str,
    data: APIKeyRequest,
    current_user: User = Depends(require_admin)
):
    """Create or update API key for provider"""
    # 1. Validate provider exists
    # 2. Encrypt API key
    # 3. Store in database
    # 4. Log to audit trail
    # 5. Clear config cache
    # 6. Return success (masked key)

@router.post("/api-keys/{provider_id}/validate", response_model=dict)
def validate_api_key(
    provider_id: str,
    api_key: Optional[str] = None,  # If None, validate stored key
    current_user: User = Depends(require_admin)
):
    """Test if API key is valid by making test API call"""
    # 1. Get or decrypt API key
    # 2. Make test API call to provider
    # 3. Update validation_status in database
    # 4. Return result

@router.delete("/api-keys/{provider_id}", status_code=204)
def delete_api_key(
    provider_id: str,
    current_user: User = Depends(require_admin)
):
    """Delete API key (will fallback to .env)"""

@router.get("/api-keys/audit-log", response_model=List[dict])
def get_audit_log(
    provider_id: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(require_admin)
):
    """Get audit trail of API key changes"""
```

**Request/Response Models**:
```python
from pydantic import BaseModel, validator

class APIKeyRequest(BaseModel):
    api_key: str
    api_url: Optional[str] = None
    validate_before_save: bool = True  # Test key before storing

    @validator('api_key')
    def validate_key_format(cls, v):
        if not v or len(v) < 10:
            raise ValueError('API key too short')
        return v

class APIKeyResponse(BaseModel):
    provider_id: str
    key_name: str
    masked_value: str  # e.g., "sk-ant-***************-abc"
    is_active: bool
    last_validated_at: Optional[datetime]
    validation_status: Optional[str]
    source: str  # 'database' or 'environment'
```

### 4. Backend Service Layer

**Update**: `app/services/admin_config_service.py`

```python
from app.services.encryption_service import EncryptionService

class AdminConfigService:
    def __init__(self, db: Session):
        self.db = db
        self.encryption = EncryptionService()

    def set_provider_api_key(
        self,
        provider: str,
        api_key: str,
        user_email: str,
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Store encrypted API key in database

        Args:
            provider: Provider ID (claude, gemini, matcha)
            api_key: Plain text API key
            user_email: Who is making the change
            validate: Test key before saving

        Returns:
            {success: bool, message: str, masked_key: str}
        """
        # 1. Validate provider exists
        provider_obj = self.get_provider(provider)
        if not provider_obj:
            raise ValueError(f"Provider {provider} not found")

        # 2. Test API key if requested
        if validate:
            validation = self._validate_api_key(provider, api_key)
            if not validation['valid']:
                raise ValueError(f"API key validation failed: {validation['error']}")

        # 3. Encrypt API key
        encrypted = self.encryption.encrypt(api_key)
        key_hash = self.encryption.hash_value(api_key)

        # 4. Get old value for audit
        old_key = self.get_provider_api_key(provider)
        old_hash = self.encryption.hash_value(old_key) if old_key else None

        # 5. Store in database
        key_name = f"{provider}_api_key"
        self.db.execute(
            text("""
                INSERT INTO api_keys (provider_id, key_name, encrypted_value, updated_by)
                VALUES (:provider, :key_name, :encrypted, :user)
                ON CONFLICT(provider_id, key_name)
                DO UPDATE SET
                    encrypted_value = :encrypted,
                    updated_by = :user,
                    updated_at = CURRENT_TIMESTAMP,
                    last_validated_at = CURRENT_TIMESTAMP,
                    validation_status = 'valid'
            """),
            {
                "provider": provider,
                "key_name": key_name,
                "encrypted": encrypted,
                "user": user_email
            }
        )

        # 6. Audit log
        self.db.execute(
            text("""
                INSERT INTO api_key_audit_log
                (provider_id, key_name, action, old_value_hash, new_value_hash, performed_by, success)
                VALUES (:provider, :key_name, 'updated', :old_hash, :new_hash, :user, 1)
            """),
            {
                "provider": provider,
                "key_name": key_name,
                "old_hash": old_hash,
                "new_hash": key_hash,
                "user": user_email
            }
        )

        self.db.commit()

        # 7. Clear cache
        self.cache.delete(f"config:{key_name}")

        return {
            "success": True,
            "message": "API key updated successfully",
            "masked_key": self._mask_key(api_key)
        }

    def get_provider_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key with enhanced security
        Now tries: Encrypted DB → .env → None
        """
        key_name = f"{provider}_api_key"

        # 1. Try encrypted database value
        result = self.db.execute(
            text("""
                SELECT encrypted_value
                FROM api_keys
                WHERE provider_id = :provider
                  AND key_name = :key_name
                  AND is_active = 1
            """),
            {"provider": provider, "key_name": key_name}
        ).fetchone()

        if result and result[0]:
            try:
                decrypted = self.encryption.decrypt(result[0])
                # Log access (optional)
                self._log_key_access(provider, key_name)
                return decrypted
            except Exception as e:
                logger.error(f"Failed to decrypt API key for {provider}: {e}")
                # Fall through to .env

        # 2. Fallback to environment (existing code)
        key_map = {
            "claude": settings.ANTHROPIC_API_KEY,
            "gemini": settings.GOOGLE_AI_API_KEY,
            "matcha": settings.MATCHA_AI_API_KEY
        }
        return key_map.get(provider)

    def _validate_api_key(self, provider: str, api_key: str) -> Dict[str, Any]:
        """Test if API key works by making a minimal API call"""
        try:
            if provider == "claude":
                # Test Anthropic API
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                # Minimal test call
                response = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "test"}]
                )
                return {"valid": True, "message": "Claude API key is valid"}

            elif provider == "gemini":
                # Test Google AI API
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content("test",
                    generation_config={"max_output_tokens": 10})
                return {"valid": True, "message": "Gemini API key is valid"}

            elif provider == "matcha":
                # Test Matcha API (OpenAI compatible)
                import httpx
                response = httpx.post(
                    settings.MATCHA_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 10
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    return {"valid": True, "message": "Matcha API key is valid"}
                else:
                    return {"valid": False, "error": f"HTTP {response.status_code}"}

            return {"valid": False, "error": "Unknown provider"}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _mask_key(self, api_key: str) -> str:
        """Mask API key for display: sk-ant-***************-abc"""
        if not api_key or len(api_key) < 10:
            return "***"
        return f"{api_key[:7]}***************{api_key[-3:]}"

    def _log_key_access(self, provider: str, key_name: str):
        """Log when API key is accessed (optional, for security audit)"""
        self.db.execute(
            text("""
                INSERT INTO api_key_audit_log
                (provider_id, key_name, action, performed_by, success)
                VALUES (:provider, :key_name, 'accessed', 'system', 1)
            """),
            {"provider": provider, "key_name": key_name}
        )
        self.db.commit()
```

### 5. Frontend Admin UI

**New Page**: `frontend-admin/src/pages/APIKeys.tsx`

**Features**:
1. List all providers with API key status
2. Add/Edit API key with masked input
3. Test API key before saving
4. View audit log
5. Delete API key (revert to .env)

**Wireframe**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🔐 API Key Management                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Provider   | API Key              | Status  | Last Tested  │
│────────────|──────────────────────|─────────|──────────────│
│ 🔮 Claude  | sk-ant-***...-abc   | ✅ Valid | 2 hrs ago   │
│            | Source: Database     |         | [Test] [Edit]│
│────────────|──────────────────────|─────────|──────────────│
│ ✨ Gemini  | AIza***...-xyz      | ✅ Valid | 1 day ago   │
│            | Source: Database     |         | [Test] [Edit]│
│────────────|──────────────────────|─────────|──────────────│
│ 🍵 Matcha  | sk-oHs***...-Gdw    | ⚠️ .env  | Never       │
│            | Source: Environment  |         | [Migrate]    │
└─────────────────────────────────────────────────────────────┘

[+ Add API Key]  [View Audit Log]
```

**Edit Modal**:
```typescript
const APIKeyModal = ({ provider, onSave, onClose }) => {
  return (
    <Modal title={`Edit API Key: ${provider.name}`} ...>
      <Form>
        <Form.Item label="API Key" name="api_key">
          <Input.Password
            placeholder="sk-ant-api03-..."
            visibilityToggle
          />
        </Form.Item>

        {provider.id === 'matcha' && (
          <Form.Item label="API URL" name="api_url">
            <Input placeholder="https://..." />
          </Form.Item>
        )}

        <Form.Item label="Test Before Saving" name="validate">
          <Switch defaultChecked />
        </Form.Item>

        <Alert
          message="Security Note"
          description="API key will be encrypted before storage"
          type="info"
        />
      </Form>

      <Space>
        <Button onClick={handleTest}>
          🧪 Test API Key
        </Button>
        <Button type="primary" onClick={handleSave}>
          💾 Save
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </Space>
    </Modal>
  );
};
```

**Audit Log View**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📋 API Key Audit Log                                        │
├─────────────────────────────────────────────────────────────┤
│ Timestamp           | Provider | Action   | User           │
│─────────────────────|──────────|──────────|────────────────│
│ 2025-02-09 15:30:21 | Claude   | Updated  | admin@nt.co.th │
│ 2025-02-09 14:15:03 | Gemini   | Validated| admin@nt.co.th │
│ 2025-02-08 10:22:45 | Claude   | Created  | admin@nt.co.th │
│ 2025-02-07 16:01:12 | Matcha   | Viewed   | admin@nt.co.th │
└─────────────────────────────────────────────────────────────┘

Filters: [Provider ▼] [Action ▼] [User ▼] [Date Range]
```

### 6. Navigation Integration

**Update**: `frontend-admin/src/components/Layout/AdminLayout.tsx`

```typescript
{
    type: 'group',
    label: 'AI Configuration',
    children: [
        {
            key: '/providers',
            icon: <CloudOutlined />,
            label: 'AI Providers',
        },
        {
            key: '/models',
            icon: <ThunderboltOutlined />,
            label: 'AI Models',
        },
        {
            key: '/api-keys',      // NEW
            icon: <KeyOutlined />, // NEW
            label: 'API Keys',     // NEW
        },
    ]
},
```

---

## Security Considerations

### 1. Encryption at Rest
- ✅ Use AES-256 encryption (industry standard)
- ✅ Store encryption key in `.env` (not in database)
- ✅ Use Fernet (symmetric encryption) for simplicity
- ⚠️ Consider key rotation mechanism

### 2. Encryption in Transit
- ✅ HTTPS only (enforce SSL/TLS)
- ✅ Never log API keys (even encrypted)
- ✅ Use CORS to restrict API access

### 3. Access Control
- ✅ Admin role required for all API key operations
- ✅ Audit log tracks who accessed/modified keys
- ✅ Consider 2FA for API key changes

### 4. Key Masking
- ✅ Display only first 7 and last 3 characters
- ✅ Never return full key in API responses
- ✅ Use Input.Password component in UI

### 5. Environment Fallback Safety
- ✅ Keep `.env` as backup (defense in depth)
- ✅ Database failure → automatic fallback to `.env`
- ✅ Document migration path clearly

### 6. Vulnerability Prevention
- ✅ SQL injection: Use parameterized queries
- ✅ XSS: Sanitize all inputs
- ✅ CSRF: Use CSRF tokens
- ✅ Rate limiting on API key validation endpoint

---

## Migration Strategy

### Phase 1: Setup Encryption (Week 1)

**Tasks**:
1. Install `cryptography` library
   ```bash
   pip install cryptography
   ```

2. Generate encryption key
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Add to `.env`
   ```bash
   ENCRYPTION_KEY="your-generated-key-here"
   ```

4. Create `app/services/encryption_service.py`

5. Write unit tests
   ```python
   def test_encrypt_decrypt():
       service = EncryptionService()
       plaintext = "sk-ant-api03-test"
       encrypted = service.encrypt(plaintext)
       decrypted = service.decrypt(encrypted)
       assert decrypted == plaintext
   ```

### Phase 2: Database Schema (Week 1)

**Tasks**:
1. Create migration script
   ```bash
   database/migrations/006_api_key_management.sql
   ```

2. Run migration
   ```bash
   sqlite3 nt_fi_report.sqlite < database/migrations/006_api_key_management.sql
   ```

3. Verify tables created
   ```sql
   SELECT name FROM sqlite_master WHERE type='table'
   AND name LIKE '%api_key%';
   ```

### Phase 3: Backend Implementation (Week 2)

**Tasks**:
1. Update `AdminConfigService.get_provider_api_key()` to try encrypted DB first
2. Add `set_provider_api_key()` method
3. Add validation methods for each provider
4. Implement audit logging
5. Add API endpoints in `app/api/v1/admin.py`
6. Write integration tests

### Phase 4: Frontend UI (Week 2)

**Tasks**:
1. Create `APIKeys.tsx` page
2. Create `APIKeyModal.tsx` component
3. Create `AuditLogTable.tsx` component
4. Add service methods in `providerService.ts`
5. Add navigation menu item
6. Add route in `App.tsx`

### Phase 5: Testing & Documentation (Week 3)

**Tasks**:
1. Manual testing all CRUD operations
2. Test encryption/decryption
3. Test API key validation for each provider
4. Test fallback to `.env`
5. Security testing (penetration testing)
6. Update documentation
7. Create user guide

### Phase 6: Optional - Migration Tool (Week 3)

**Create script to migrate from `.env` to database**:
```python
# scripts/migrate_api_keys_to_db.py
from app.services.admin_config_service import AdminConfigService
from app.config import settings

def migrate_api_keys():
    """Migrate API keys from .env to encrypted database"""
    service = AdminConfigService(db_session)

    migrations = [
        ("claude", settings.ANTHROPIC_API_KEY),
        ("gemini", settings.GOOGLE_AI_API_KEY),
        ("matcha", settings.MATCHA_AI_API_KEY),
    ]

    for provider, api_key in migrations:
        if api_key:
            print(f"Migrating {provider}...")
            result = service.set_provider_api_key(
                provider=provider,
                api_key=api_key,
                user_email="system@migration",
                validate=True  # Test before storing
            )
            print(f"  ✅ {result['message']}")
        else:
            print(f"  ⏭️  Skipping {provider} (no key in .env)")

    print("\n✅ Migration complete!")
    print("⚠️  Remember to:")
    print("  1. Verify keys work in database")
    print("  2. Keep .env as backup")
    print("  3. Update deployment documentation")

if __name__ == "__main__":
    migrate_api_keys()
```

---

## Implementation Checklist

### Backend Tasks

- [ ] **Encryption Service**
  - [ ] Install cryptography library
  - [ ] Create `EncryptionService` class
  - [ ] Generate and document encryption key
  - [ ] Write unit tests for encrypt/decrypt
  - [ ] Add key rotation support (future)

- [ ] **Database Schema**
  - [ ] Create `api_keys` table
  - [ ] Create `api_key_audit_log` table
  - [ ] Add indexes for performance
  - [ ] Create migration script
  - [ ] Run migration on all environments

- [ ] **Service Layer**
  - [ ] Update `get_provider_api_key()` to use encrypted DB
  - [ ] Add `set_provider_api_key()` method
  - [ ] Add `delete_provider_api_key()` method
  - [ ] Add `validate_api_key()` for each provider
  - [ ] Add audit logging helpers
  - [ ] Handle edge cases (decryption failure, etc.)

- [ ] **API Endpoints**
  - [ ] `GET /admin/api-keys` - List all keys (masked)
  - [ ] `POST /admin/api-keys/{provider}` - Create/update key
  - [ ] `POST /admin/api-keys/{provider}/validate` - Test key
  - [ ] `DELETE /admin/api-keys/{provider}` - Delete key
  - [ ] `GET /admin/api-keys/audit-log` - View audit trail
  - [ ] Add request/response models
  - [ ] Add authentication/authorization
  - [ ] Add rate limiting

- [ ] **Testing**
  - [ ] Unit tests for EncryptionService
  - [ ] Unit tests for AdminConfigService
  - [ ] Integration tests for API endpoints
  - [ ] Test fallback to .env
  - [ ] Test validation for each provider
  - [ ] Security testing (try to access without auth)

### Frontend Tasks

- [ ] **Service Layer**
  - [ ] Add API key methods to `providerService.ts`
  - [ ] Add TypeScript interfaces
  - [ ] Handle errors and loading states

- [ ] **UI Components**
  - [ ] Create `APIKeys.tsx` page
  - [ ] Create `APIKeyModal.tsx` for add/edit
  - [ ] Create `AuditLogTable.tsx` for history
  - [ ] Add masked input component
  - [ ] Add test button with status indicator
  - [ ] Add confirmation dialogs

- [ ] **Navigation**
  - [ ] Add route in `App.tsx`
  - [ ] Add menu item in `AdminLayout.tsx`
  - [ ] Add breadcrumbs

- [ ] **UX Polish**
  - [ ] Loading indicators
  - [ ] Success/error messages
  - [ ] Validation feedback
  - [ ] Help text and tooltips
  - [ ] Responsive design

### Documentation Tasks

- [ ] **Technical Documentation**
  - [ ] Update PROVIDER_MODEL_MANAGEMENT.md
  - [ ] Document encryption approach
  - [ ] Document API endpoints
  - [ ] Document database schema

- [ ] **User Documentation**
  - [ ] Create user guide for API key management
  - [ ] Add screenshots/GIFs
  - [ ] Document migration from .env
  - [ ] Add troubleshooting section

- [ ] **Deployment Documentation**
  - [ ] Document ENCRYPTION_KEY setup
  - [ ] Document migration steps
  - [ ] Update environment variables guide
  - [ ] Add rollback procedure

### Deployment Tasks

- [ ] **Environment Setup**
  - [ ] Generate encryption key for each environment
  - [ ] Add to `.env` files (dev, staging, prod)
  - [ ] Verify .gitignore excludes .env

- [ ] **Database Migration**
  - [ ] Backup database before migration
  - [ ] Run migration script
  - [ ] Verify tables created
  - [ ] Run migration tool to populate from .env

- [ ] **Testing in Production**
  - [ ] Test API key retrieval
  - [ ] Test API key update
  - [ ] Test validation for each provider
  - [ ] Verify audit logging
  - [ ] Test fallback to .env

- [ ] **Monitoring**
  - [ ] Add metrics for API key usage
  - [ ] Alert on decryption failures
  - [ ] Monitor audit log for suspicious activity

---

## Estimated Timeline

### Effort Estimation

| Task | Estimated Time | Priority |
|------|---------------|----------|
| Encryption Service | 0.5 day | High |
| Database Schema | 0.5 day | High |
| Backend Service Methods | 1.5 days | High |
| Backend API Endpoints | 1 day | High |
| Backend Testing | 1 day | High |
| Frontend Service Layer | 0.5 day | Medium |
| Frontend UI Components | 2 days | Medium |
| Frontend Testing | 0.5 day | Medium |
| Documentation | 1 day | Medium |
| Migration Tool | 0.5 day | Low |
| Security Review | 1 day | High |
| **Total** | **10 days** | |

### Phased Rollout

**Week 1: Backend Foundation**
- Days 1-2: Encryption + Database Schema
- Days 3-4: Service Layer + API Endpoints
- Day 5: Backend Testing

**Week 2: Frontend + Integration**
- Days 1-2: Frontend UI Development
- Day 3: Frontend Testing
- Days 4-5: Integration Testing + Bug Fixes

**Week 3: Polish + Deploy**
- Day 1: Security Review
- Day 2: Documentation
- Day 3: Staging Deployment + UAT
- Day 4: Production Deployment
- Day 5: Monitoring + Hotfixes

---

## Success Criteria

### Functional Requirements
- ✅ Admin can add/edit/delete API keys via UI
- ✅ System validates API keys before saving
- ✅ Keys are encrypted in database
- ✅ Keys are masked in UI (except during edit)
- ✅ Audit log tracks all changes
- ✅ Fallback to `.env` works if DB unavailable

### Non-Functional Requirements
- ✅ No server restart required for key changes
- ✅ Response time < 500ms for key retrieval
- ✅ Encryption/decryption < 100ms
- ✅ 100% test coverage for security-critical code
- ✅ Zero API keys leaked in logs or error messages

### User Acceptance
- ✅ Admin can complete key change in < 2 minutes
- ✅ Clear error messages if validation fails
- ✅ Audit log provides sufficient detail for compliance

---

## Risks and Mitigations

### Risk 1: Encryption Key Compromise
**Impact**: All API keys exposed
**Probability**: Low
**Mitigation**:
- Store ENCRYPTION_KEY in `.env` (not in code/DB)
- Use environment variable injection in production
- Consider external secret management (Vault)
- Implement key rotation mechanism

### Risk 2: Decryption Failure
**Impact**: System can't access API keys
**Probability**: Low
**Mitigation**:
- Automatic fallback to `.env`
- Alert on decryption failures
- Keep `.env` in sync as backup

### Risk 3: Migration Data Loss
**Impact**: API keys lost during migration
**Probability**: Low
**Mitigation**:
- Backup database before migration
- Test migration on staging first
- Keep `.env` as backup during transition

### Risk 4: Performance Degradation
**Impact**: Slower API key retrieval
**Probability**: Low
**Mitigation**:
- Benchmark encryption/decryption performance
- Consider caching decrypted keys in memory (with TTL)
- Use connection pooling for database

### Risk 5: Audit Log Growth
**Impact**: Database bloat from audit logs
**Probability**: Medium
**Mitigation**:
- Add retention policy (e.g., keep 90 days)
- Implement log archival/purge script
- Monitor database size

---

## Future Enhancements

### Phase 2 Features (After Initial Launch)

1. **Key Rotation**
   - Automatic rotation on schedule
   - Notification before expiry
   - Version management

2. **Multi-Region Support**
   - Different API keys per region
   - Geographic redundancy

3. **Cost Tracking**
   - Track API usage per key
   - Budget alerts
   - Cost attribution

4. **Advanced Validation**
   - Periodic background validation
   - Health check dashboard
   - Auto-disable invalid keys

5. **External Secret Management**
   - Integration with HashiCorp Vault
   - AWS Secrets Manager
   - Azure Key Vault

6. **Compliance Features**
   - PCI-DSS compliance
   - SOC 2 audit trail
   - GDPR data handling

---

## References

### Libraries & Tools
- **Python cryptography**: https://cryptography.io/
- **Fernet encryption**: https://cryptography.io/en/latest/fernet/
- **AES-GCM**: https://cryptography.io/en/latest/hazmat/primitives/aead/

### Best Practices
- **OWASP Secrets Management**: https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password
- **12-Factor App Config**: https://12factor.net/config
- **NIST Encryption Standards**: https://www.nist.gov/publications/advanced-encryption-standard-aes

### Similar Implementations
- **Django encrypted fields**: https://django-encrypted-model-fields.readthedocs.io/
- **SQLAlchemy encryption**: https://sqlalchemy-utils.readthedocs.io/en/latest/data_types.html#module-sqlalchemy_utils.types.encrypted

---

## Appendix

### A. Database Migration Script

**File**: `database/migrations/006_api_key_management.sql`

```sql
-- ============================================================
-- NT AI Assistant - API Key Management
-- Purpose: Secure storage and management of AI provider API keys
-- Version: 1.0
-- Date: 2025-02-09
-- ============================================================

-- ============================================================
-- Table: api_keys
-- Stores encrypted API keys for AI providers
-- ============================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    key_name TEXT NOT NULL,                 -- 'api_key', 'api_url', etc.
    encrypted_value TEXT NOT NULL,          -- AES-256 encrypted
    encryption_version TEXT DEFAULT 'v1',   -- For key rotation
    is_active BOOLEAN DEFAULT 1,
    last_validated_at DATETIME,
    validation_status TEXT,                 -- 'valid', 'invalid', 'untested'
    validation_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    last_rotated_at DATETIME,
    expires_at DATETIME,
    FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE,
    UNIQUE(provider_id, key_name)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active, provider_id);

-- ============================================================
-- Table: api_key_audit_log
-- Audit trail for API key operations
-- ============================================================
CREATE TABLE IF NOT EXISTS api_key_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    key_name TEXT NOT NULL,
    action TEXT NOT NULL,                   -- 'created', 'updated', 'validated', 'deleted', 'viewed'
    old_value_hash TEXT,                    -- SHA-256 hash for comparison
    new_value_hash TEXT,
    performed_by TEXT NOT NULL,
    performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN DEFAULT 1,
    error_message TEXT,
    metadata TEXT                           -- JSON for additional context
);

CREATE INDEX IF NOT EXISTS idx_audit_log_provider ON api_key_audit_log(provider_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_performed_at ON api_key_audit_log(performed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_performed_by ON api_key_audit_log(performed_by);

-- ============================================================
-- Remove placeholder rows from admin_config
-- (Optional: Only if you want to force DB-only approach)
-- ============================================================
-- DELETE FROM admin_config WHERE config_key IN (
--     'anthropic_api_key',
--     'google_ai_api_key',
--     'matcha_api_key'
-- );

-- ============================================================
-- Initial data (optional - for testing)
-- ============================================================
-- Note: Don't insert real API keys here!
-- Use the migration tool script instead
```

### B. Environment Variables Template

**File**: `.env.example` (Update)

```bash
# Existing variables...

# ============================================================
# Security - Encryption
# ============================================================
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY="your-fernet-key-here"

# ============================================================
# AI Provider API Keys
# ============================================================
# Note: These are now fallbacks. Primary keys stored encrypted in database.
# To migrate to database, use: python scripts/migrate_api_keys_to_db.py

ANTHROPIC_API_KEY="sk-ant-api03-..."  # Fallback if DB empty
GOOGLE_AI_API_KEY="AIza..."           # Fallback if DB empty
MATCHA_AI_API_KEY="sk-..."            # Fallback if DB empty
MATCHA_API_URL="https://aigateway.ntictsolution.com/v1/chat/completions"
```

---

**Document Version**: 1.0
**Last Updated**: 2025-02-09
**Status**: Planning Phase
**Next Review**: Before Implementation Start

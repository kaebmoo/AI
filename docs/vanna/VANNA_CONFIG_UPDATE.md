# Vanna Configuration Update - Summary

**Date**: 2026-02-06
**Changes**: Made Vanna settings configurable via .env

---

## 📝 Changes Made

### 1. Added Config to `.env`

```bash
# Vanna AI (RAG) Settings
VANNA_CHROMA_PATH="./chroma_db"
VANNA_DISTANCE_THRESHOLD=1.8
```

**Parameters:**
- `VANNA_CHROMA_PATH`: Path to ChromaDB storage directory
- `VANNA_DISTANCE_THRESHOLD`: Distance threshold for similarity filtering (lower = stricter)

---

### 2. Updated `app/config.py`

Added Vanna settings to Settings class:

```python
# Vanna AI (RAG) Settings
VANNA_CHROMA_PATH: str = "./chroma_db"
VANNA_DISTANCE_THRESHOLD: float = 1.8
```

---

### 3. Updated Service Initialization

#### `app/services/ai_service.py`

**Before:**
```python
self.vanna = VannaService()
```

**After:**
```python
# Import settings
from app.config import settings

# Initialize with config
self.vanna = VannaService(config={
    "path": settings.VANNA_CHROMA_PATH,
    "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
})
```

#### `app/api/v1/admin.py`

**Before:**
```python
vanna = VannaService()
```

**After:**
```python
from app.config import settings

vanna = VannaService(config={
    "path": settings.VANNA_CHROMA_PATH,
    "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
})
```

#### `scripts/sync_vanna_brain.py`

**Before:**
```python
vanna = VannaService()
```

**After:**
```python
from app.config import settings

vanna = VannaService(config={
    "path": settings.VANNA_CHROMA_PATH,
    "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
})
```

---

## 🎯 How to Use

### Tuning Distance Threshold

Edit `.env` to adjust the threshold:

```bash
# Stricter filtering (fewer, more relevant results)
VANNA_DISTANCE_THRESHOLD=1.5

# Default (balanced)
VANNA_DISTANCE_THRESHOLD=1.8

# Looser filtering (more results, potentially less relevant)
VANNA_DISTANCE_THRESHOLD=2.2
```

**Guidelines:**
- **< 1.5**: Very strict - only highly similar contexts
- **1.5 - 2.0**: Balanced - good for most use cases (default: 1.8)
- **> 2.0**: Loose - more results but may include less relevant content

### Changing ChromaDB Path

```bash
# Store in different directory
VANNA_CHROMA_PATH="./data/vector_db"

# Use absolute path
VANNA_CHROMA_PATH="/var/lib/ai_assistant/chroma_db"
```

---

## 🔄 How Settings Flow

```
.env
  ↓
app/config.py (Settings class)
  ↓
settings object
  ↓
VannaService initialization
  ↓
self.distance_threshold (used in get_rag_context)
```

---

## 🧪 Testing

### 1. Verify Config Loading

```python
from app.config import settings

print(f"Vanna Path: {settings.VANNA_CHROMA_PATH}")
print(f"Distance Threshold: {settings.VANNA_DISTANCE_THRESHOLD}")
```

Expected output:
```
Vanna Path: ./chroma_db
Distance Threshold: 1.8
```

### 2. Test VannaService Initialization

```python
from app.services.vanna_service import VannaService
from app.config import settings

vanna = VannaService(config={
    "path": settings.VANNA_CHROMA_PATH,
    "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
})

print(f"Threshold: {vanna.distance_threshold}")
# Output: Threshold: 1.8
```

### 3. Test Different Thresholds

```python
from app.services.vanna_service import VannaService

# Test with custom threshold
vanna = VannaService(config={
    "path": "./chroma_db",
    "distance_threshold": 1.5  # Stricter
})

contexts = vanna.get_rag_context("รายได้รวม")
print(f"Results with threshold 1.5: {len(contexts['doc'])} docs")

# Test with default from .env
from app.config import settings
vanna = VannaService(config={
    "path": settings.VANNA_CHROMA_PATH,
    "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
})

contexts = vanna.get_rag_context("รายได้รวม")
print(f"Results with threshold {settings.VANNA_DISTANCE_THRESHOLD}: {len(contexts['doc'])} docs")
```

---

## 📊 Expected Behavior

### Before Changes
- ❌ Hardcoded path: `./chroma_db`
- ❌ Hardcoded threshold: `1.8`
- ❌ Required code changes to adjust settings

### After Changes
- ✅ Configurable path via `.env`
- ✅ Configurable threshold via `.env`
- ✅ No code changes needed for tuning
- ✅ Environment-specific settings (dev, staging, prod)

---

## 🔍 Files Modified

| File | Changes |
|------|---------|
| `.env` | Added `VANNA_CHROMA_PATH` and `VANNA_DISTANCE_THRESHOLD` |
| `app/config.py` | Added Vanna settings to Settings class |
| `app/services/ai_service.py` | Import settings, pass config to VannaService |
| `app/api/v1/admin.py` | Import settings, pass config to VannaService |
| `scripts/sync_vanna_brain.py` | Import settings, pass config to VannaService |

---

## 🚀 Production Deployment

### 1. Update Production .env

```bash
# Production settings
VANNA_CHROMA_PATH="/var/lib/ai_assistant/chroma_db"
VANNA_DISTANCE_THRESHOLD=1.8

# Or use environment-specific threshold
# VANNA_DISTANCE_THRESHOLD=1.5  # Stricter for production
```

### 2. Restart Services

```bash
# Restart backend to load new config
uvicorn app.main:app --reload

# Or with systemd
sudo systemctl restart ai-assistant
```

### 3. Verify Settings

```bash
# Check logs for Vanna initialization
tail -f logs/app.log | grep "Vanna"

# Test RAG retrieval
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "รายได้รวม"}'
```

---

## 💡 Tuning Recommendations

### When to Adjust Threshold

**Lower threshold (< 1.8) if:**
- Getting too many irrelevant contexts
- Responses include unrelated information
- Query precision is more important than recall

**Higher threshold (> 1.8) if:**
- Getting too few contexts (empty results)
- Missing relevant information
- Query recall is more important than precision

### Monitoring

Add to your monitoring dashboard:
```python
# Log threshold effectiveness
logger.info(f"RAG Query: threshold={threshold}, results={len(contexts)}")

# Track result counts
metrics = {
    "ddl_count": len(contexts['ddl']),
    "doc_count": len(contexts['doc']),
    "sql_count": len(contexts['sql']),
    "threshold": vanna.distance_threshold
}
```

---

## ✅ Verification Checklist

- [x] `.env` updated with Vanna settings
- [x] `app/config.py` includes Vanna settings
- [x] `ai_service.py` uses settings
- [x] `admin.py` uses settings
- [x] `sync_vanna_brain.py` uses settings
- [x] Settings flow correctly from .env to VannaService
- [x] Threshold is configurable without code changes

---

## 📞 Support

**Issue**: Settings not loading
```bash
# Check if .env is being read
python -c "from app.config import settings; print(settings.VANNA_DISTANCE_THRESHOLD)"
```

**Issue**: Threshold not changing results
```bash
# Verify threshold is being used
python -c "from app.services.vanna_service import VannaService; from app.config import settings; v = VannaService(config={'path': settings.VANNA_CHROMA_PATH, 'distance_threshold': settings.VANNA_DISTANCE_THRESHOLD}); print(v.distance_threshold)"
```

**Issue**: ChromaDB path not found
```bash
# Check if directory exists
ls -la ./chroma_db

# Create if needed
mkdir -p ./chroma_db

# Re-sync brain
curl -X POST http://localhost:8000/api/v1/admin/sync-brain
```

---

**Configuration Complete** ✅

All Vanna settings are now configurable via `.env` without code changes!

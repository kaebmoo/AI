# Adding a New AI Provider

> คู่มือสำหรับเพิ่ม AI Provider ใหม่เข้าระบบ NT AI Assistant
> ระบบรองรับ provider ไม่จำกัดจำนวน โดยไม่ต้องแก้ไข core code

---

## สถาปัตยกรรม

```
app/providers/
├── base.py                # AIProvider ABC — interface ที่ต้อง implement
├── registry.py            # Auto-discover ไฟล์ provider ทั้งหมด
├── retry_config.py        # @ai_retry decorator
├── chart_postprocessor.py # Shared explain/chart logic
├── claude_provider.py     # Built-in: Anthropic Claude
├── gemini_provider.py     # Built-in: Google Gemini
├── matcha_provider.py     # Built-in: OpenAI-compatible (NT Gateway)
└── deepseek_provider.py   # ← ไฟล์ใหม่ที่คุณสร้าง
```

**Auto-discovery:** เมื่อ server start, `registry.discover()` จะ scan ทุกไฟล์ `.py` ใน `app/providers/` และลงทะเบียน class ที่ inherit จาก `AIProvider` โดยอัตโนมัติ — ไม่ต้องแก้ registry

---

## 3 ขั้นตอนเพิ่ม Provider ใหม่

### ขั้นตอนที่ 1: สร้างไฟล์ Provider

สร้างไฟล์ `app/providers/{name}_provider.py`

#### AIProvider Interface (ต้อง implement ทั้ง 3 methods)

```python
class AIProvider(ABC):
    name: str = ""                    # ต้องตั้งค่า — ใช้เป็น provider ID

    def is_configured(self) -> bool:  # เช็คว่ามี credentials ครบไหม
    def get_model(self, tier) -> str: # return model name ตาม tier

    # === 3 Abstract Methods ===
    async def generate_sql(self, question, system_prompt, tools, history) -> dict
    async def explain_result(self, question, sql, data, system_prompt, ...) -> dict
    async def generate_content(self, prompt, system_prompt, history) -> str
```

#### Template: OpenAI-Compatible Provider (แนะนำ — ง่ายที่สุด)

ใช้ `matcha_provider.py` เป็นฐาน — เหมาะกับ provider ที่มี API แบบ OpenAI (DeepSeek, Together, Groq, vLLM, etc.)

```python
"""
NT AI Assistant - DeepSeek Provider
=====================================
DeepSeek API implementation (OpenAI-compatible).
"""

import json
import logging
from typing import Dict, List, Optional, Any, Union

import httpx

from app.providers.base import AIProvider, lookup_model_by_tier
from app.providers.retry_config import ai_retry
from app.providers.chart_postprocessor import (
    parse_explanation_response,
    enforce_time_series_rule,
    enforce_dimension_family_rule,
    build_explain_prompt,
    auto_detect_chart_config,
)

logger = logging.getLogger(__name__)


class DeepSeekProvider(AIProvider):
    """DeepSeek API provider (OpenAI-compatible)"""

    name = "deepseek"  # ← ต้องตรงกับ ai_providers.id ใน DB

    def __init__(self, api_key: str, api_url: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.api_url = api_url  # e.g. "https://api.deepseek.com/v1/chat/completions"
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_url)

    def get_model(self, tier: str = "default") -> str:
        # ลอง DB ก่อน (admin อาจตั้ง model ผ่าน ai_models table)
        db_model = lookup_model_by_tier("deepseek", tier)
        if db_model:
            return db_model
        # Fallback
        if tier == "cheap":
            return "deepseek-chat"
        return self.model

    # =====================================================
    # Method 1: generate_sql — สร้าง SQL จากคำถาม + tools
    # =====================================================
    @ai_retry
    async def generate_sql(
        self,
        question: Optional[str],
        system_prompt: str,
        tools: List[Dict],
        history: List[Dict] = [],
    ) -> Dict[str, Any]:

        # แปลง tools เป็น OpenAI format
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            })

        # สร้าง messages
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            new_msg = {
                k: v for k, v in msg.items()
                if k in ["role", "content", "tool_calls", "tool_call_id", "name"]
            }
            messages.append(new_msg)

        if question:
            messages.append({"role": "user", "content": question})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
        if openai_tools:
            payload["tools"] = openai_tools

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()

        return {
            "response": result,
            "tokens_used": result.get("usage", {}).get("total_tokens", 0),
        }

    # =====================================================
    # Method 2: explain_result — อธิบายผลลัพธ์ + chart config
    # =====================================================
    async def explain_result(
        self,
        question: str,
        sql: str,
        data: List[Dict],
        system_prompt: str,
        dimension_families: Optional[Dict[str, List[str]]] = None,
        hierarchy_info: Optional[list] = None,
        schema_metadata: Optional[list] = None,
    ) -> Dict[str, Any]:
        # ใช้ shared prompt builder
        prompt = build_explain_prompt(
            question=question, sql=sql, data=data,
            dimension_families=dimension_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )
        response_text = await self.generate_content(prompt, system_prompt)

        # ใช้ shared post-processor
        time_columns = (
            [m["column_name"] for m in schema_metadata
             if m.get("dimension_group") == "time_period"]
            if schema_metadata else None
        )
        parsed_result = parse_explanation_response(response_text)
        parsed_result = enforce_time_series_rule(parsed_result, time_columns=time_columns)
        parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)

        # Fallback: auto-detect chart config
        if "chart_config" not in parsed_result and data and len(data) > 0:
            parsed_result = auto_detect_chart_config(
                data, parsed_result, schema_metadata=schema_metadata
            )

        return parsed_result

    # =====================================================
    # Method 3: generate_content — สร้าง text content ทั่วไป
    # =====================================================
    async def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()

            return result["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"DeepSeekProvider: API call failed: {type(e).__name__}: {e}")
            raise
```

#### Template: SDK-Based Provider (Claude / Gemini style)

ถ้า provider มี official Python SDK ให้ใช้ pattern แบบ Claude:

```python
class MyProvider(AIProvider):
    name = "myprovider"

    def __init__(self, api_key: str, model: str = "my-model-v1"):
        self.api_key = api_key
        self.model = model
        self._client = None  # lazy init

    @property
    def client(self):
        """Lazy-init SDK client"""
        if self._client is None:
            import my_sdk
            self._client = my_sdk.AsyncClient(api_key=self.api_key)
        return self._client
```

---

### ขั้นตอนที่ 2: เพิ่มข้อมูลใน Database

เพิ่ม row ใน 2 tables: `ai_providers` และ `ai_models`

#### 2a. INSERT ai_providers

```sql
INSERT INTO ai_providers (id, name, description, api_key_env_var, api_url_env_var, default_api_url, is_active, config_schema)
VALUES (
    'deepseek',                          -- id: ต้องตรงกับ class.name
    'DeepSeek',                          -- name: แสดงใน UI
    'DeepSeek AI API',                   -- description
    'DEEPSEEK_API_KEY',                  -- api_key_env_var: ชื่อ env var สำหรับ API key
    'DEEPSEEK_API_URL',                  -- api_url_env_var: ชื่อ env var สำหรับ API URL (NULL ถ้าไม่ต้องการ)
    'https://api.deepseek.com/v1/chat/completions',  -- default_api_url
    1,                                   -- is_active
    NULL                                 -- config_schema: JSON สำหรับ extra config (ถ้ามี)
);
```

**`config_schema` (optional):** ถ้า provider มี config พิเศษ ให้ใส่เป็น JSON:

```sql
-- ตัวอย่าง: provider ที่มี options เพิ่มเติม
UPDATE ai_providers SET config_schema = '{
    "temperature": {"type": "number", "default": 0.1, "label": "Temperature"},
    "max_tokens": {"type": "integer", "default": 4096, "label": "Max Tokens"}
}' WHERE id = 'deepseek';
```

#### 2b. INSERT ai_models

```sql
-- Default model
INSERT INTO ai_models (id, provider_id, model_id, name, tier, is_default, is_active, priority)
VALUES ('deepseek-chat', 'deepseek', 'deepseek-chat', 'DeepSeek Chat', 'default', 1, 1, 100);

-- Cheap model (สำหรับ tasks ที่ไม่ต้องการ quality สูง)
INSERT INTO ai_models (id, provider_id, model_id, name, tier, is_default, is_active, priority)
VALUES ('deepseek-chat-cheap', 'deepseek', 'deepseek-chat', 'DeepSeek Chat (Cheap)', 'cheap', 0, 1, 50);

-- Reasoning model (optional)
INSERT INTO ai_models (id, provider_id, model_id, name, tier, is_default, is_active, priority)
VALUES ('deepseek-reasoner', 'deepseek', 'deepseek-reasoner', 'DeepSeek Reasoner', 'default', 0, 1, 90);
```

#### 2c. Enable ใน admin_config

```sql
INSERT INTO admin_config (config_key, config_value, config_type, category)
VALUES ('deepseek_enabled', 'true', 'ai_provider', 'ai');

INSERT INTO admin_config (config_key, config_value, config_type, category)
VALUES ('deepseek_model', 'deepseek-chat', 'model', 'ai');
```

---

### ขั้นตอนที่ 3: ตั้ง Environment Variable

เพิ่มใน `.env`:

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
```

---

## เสร็จ! ไม่ต้องแก้ไฟล์อื่น

ระบบจะ auto-discover provider ใหม่เมื่อ restart server:

1. `registry.discover()` — scan ไฟล์ → พบ `DeepSeekProvider` → ลงทะเบียน
2. `_build_provider_kwargs("deepseek", ai_config)` — อ่าน `api_key_env_var` จาก DB → resolve จาก `.env`
3. `registry.create_provider("deepseek", **kwargs)` — introspect `__init__` → สร้าง instance
4. `provider.is_configured()` → เช็คว่ามี api_key + api_url → พร้อมใช้

---

## 3-Tier Fallback — ไม่มีทาง Crash

ทุกจุดใช้ 3-tier resolution:

```
Tier 1: Database (ai_providers table)
  → อ่าน api_key_env_var, api_url_env_var
  → resolve เป็นค่าจริงจาก os.environ

Tier 2: .env / Settings object
  → ถ้า DB ไม่มีข้อมูล (เช่น migration ยังไม่รัน)
  → ใช้ค่าจาก config.py / pydantic Settings
  → รองรับเฉพาะ 3 built-in providers (claude, gemini, matcha)

Tier 3: Hardcoded defaults
  → ถ้า .env ไม่มีค่า → return ""
  → is_configured() = False → skip provider → ลอง provider อื่น
  → ไม่มี provider ใดพร้อม → return error message (ไม่ crash)
```

**สำหรับ provider ใหม่:** ต้อง INSERT row ใน `ai_providers` table (Tier 1) เพราะไม่มี Tier 2 fallback สำหรับ provider ที่ไม่ใช่ 3 ตัว built-in

---

## Checklist

| # | รายการ | ตรวจสอบ |
|---|--------|---------|
| 1 | สร้างไฟล์ `app/providers/{name}_provider.py` | |
| 2 | Class inherit จาก `AIProvider` | |
| 3 | ตั้ง `name = "xxx"` ตรงกับ DB id | |
| 4 | Implement `__init__` รับ `api_key`, `model` (+ `api_url` ถ้าจำเป็น) | |
| 5 | Implement `is_configured()` | |
| 6 | Implement `generate_sql()` — return `{"response": ..., "tokens_used": N}` | |
| 7 | Implement `explain_result()` — ใช้ `build_explain_prompt()` + `parse_explanation_response()` | |
| 8 | Implement `generate_content()` — return string | |
| 9 | INSERT `ai_providers` row พร้อม `api_key_env_var` | |
| 10 | INSERT `ai_models` row(s) พร้อม tier | |
| 11 | INSERT `admin_config` rows (`{name}_enabled`, `{name}_model`) | |
| 12 | เพิ่ม API key ใน `.env` | |
| 13 | Restart server → ตรวจ log "Discovered provider: xxx" | |
| 14 | ทดสอบ query ผ่าน UI | |

---

## FAQ

### Q: ต้องเพิ่ม env var ใน `config.py` (Pydantic Settings) ไหม?

**ไม่จำเป็น** — ระบบใช้ `os.environ.get()` โดยตรงจาก `api_key_env_var` ที่เก็บใน DB
Pydantic Settings ใน `config.py` เป็น fallback สำหรับ 3 provider เดิมเท่านั้น

### Q: ถ้า provider ไม่ต้องการ `api_url` (เหมือน Claude / Gemini)?

`__init__` ไม่ต้องรับ `api_url` — ระบบ introspect `__init__` signature แล้ว pass เฉพาะ params ที่ match:

```python
class MyProvider(AIProvider):
    name = "myprovider"

    def __init__(self, api_key: str, model: str = "default-model"):
        # ไม่มี api_url — ระบบจะไม่ส่ง api_url มาให้
        ...
```

และใน DB ตั้ง `api_url_env_var = NULL`

### Q: ถ้า provider มี config พิเศษ (เช่น extended_thinking)?

เพิ่มใน `__init__` signature — ระบบจะ resolve จาก `admin_config` table:

```python
def __init__(self, api_key: str, model: str = "default", use_cache: bool = True):
    ...
```

แล้ว INSERT ใน admin_config:
```sql
INSERT INTO admin_config (config_key, config_value)
VALUES ('myprovider_use_cache', 'true');
```

ระบบจะ match `myprovider_use_cache` → ตัด prefix → `use_cache` → pass เข้า `__init__`

### Q: `generate_sql` return format ต้องเป็นยังไง?

**OpenAI-compatible format:**
```python
return {
    "response": {
        "choices": [{
            "message": {
                "content": "...",
                "tool_calls": [...]  # ถ้าใช้ tools
            }
        }],
        "usage": {"total_tokens": 123}
    },
    "tokens_used": 123
}
```

**Claude format:**
```python
return {
    "response": anthropic_response_object,  # Claude SDK response
    "tokens_used": input_tokens + output_tokens
}
```

**Gemini format:**
```python
return {
    "response": gemini_response_object,  # Gemini SDK response
    "tokens_used": prompt_tokens + candidate_tokens
}
```

> **หมายเหตุ:** `ai_service.py` มี handler สำหรับ 3 format นี้ ถ้าเพิ่ม provider แบบ OpenAI-compatible ให้ return format เหมือน matcha (จะทำงานได้ทันที)

### Q: ต้องเพิ่ม handler ใน `ai_service.py` ไหม?

**ถ้า OpenAI-compatible: ไม่ต้อง** — ระบบมี handler สำหรับ OpenAI format อยู่แล้ว (ใช้ร่วมกับ matcha)

**ถ้า format ต่างออกไป:** ต้องเพิ่ม handling ใน `ai_service.py` → method `_handle_tool_call_response()` เพื่อ parse response ของ provider ใหม่

### Q: dependency ใหม่ต้องทำยังไง?

```bash
# เพิ่ม dependency
pip install deepseek-sdk  # (ถ้ามี official SDK)

# หรือใช้ httpx (มีอยู่แล้ว) สำหรับ OpenAI-compatible API
# ไม่ต้อง install อะไรเพิ่ม
```

> **แนะนำ:** ถ้า provider รองรับ OpenAI-compatible API ให้ใช้ `httpx` (มีอยู่แล้ว) แทน official SDK — ลด dependency

---

## ตัวอย่างจริง: Provider ที่มีอยู่ในระบบ

| Provider | `__init__` params | SDK/HTTP | ไฟล์ |
|----------|-------------------|----------|------|
| Claude | `api_key, model, extended_thinking, thinking_budget_tokens` | `anthropic` SDK | `claude_provider.py` |
| Gemini | `api_key, model` | `google-genai` SDK | `gemini_provider.py` |
| Matcha | `api_key, api_url, model` | `httpx` (OpenAI-compat) | `matcha_provider.py` |

---

## Flow Diagram

```
                    Server Start
                         │
                  registry.discover()
                         │
              ┌──────────┼──────────┐
              │          │          │
         claude.py   gemini.py   deepseek.py  ← auto-discovered
              │          │          │
              └──────────┼──────────┘
                         │
                  User sends query
                         │
              query_engine.query()
                         │
          _build_provider_kwargs("deepseek")
                         │
              ┌──── 3-Tier Resolve ────┐
              │                        │
         Tier 1: DB                    │
         ai_providers.api_key_env_var  │
         = "DEEPSEEK_API_KEY"          │
              │                        │
         os.environ["DEEPSEEK_API_KEY"]│
         = "sk-xxx"                    │
              │                        │
              └────────────────────────┘
                         │
          registry.create_provider("deepseek",
              api_key="sk-xxx",
              api_url="https://...",
              model="deepseek-chat")
                         │
              inspect __init__ signature
              → pass matching kwargs only
                         │
              provider.is_configured() ✓
                         │
              provider.generate_sql(...)
```

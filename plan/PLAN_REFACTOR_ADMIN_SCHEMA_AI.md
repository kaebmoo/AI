# Refactor Plan - admin.py, schema_service.py, ai_service.py

> Scope: [app/api/v1/admin.py](app/api/v1/admin.py), [app/services/schema_service.py](app/services/schema_service.py), [app/services/ai_service.py](app/services/ai_service.py)
> Snapshot date: 2026-03-22
> Goal: ลดขนาด monolith, แยก bounded responsibilities, ลด regression risk โดยคง API behavior เดิมไว้

---

## Current Baseline

จาก repository ปัจจุบัน

- [app/api/v1/admin.py](app/api/v1/admin.py): 2639 lines
- [app/services/schema_service.py](app/services/schema_service.py): 1769 lines
- [app/services/ai_service.py](app/services/ai_service.py): 1732 lines

ข้อเท็จจริงสำคัญ

- `admin.py` เป็น endpoint monolith และแตกก่อนสุดได้ ROI สูงสุด
- `schema_service.py` ไม่ใช่ไฟล์ concern เดียวล้วน แต่รวม view management, metadata propagation, context loading, prompt building, dimension family logic, cache logic
- `ai_service.py` ไม่ใช่แค่ factory + hierarchy helpers แต่มี orchestration flow ขนาดใหญ่, Vanna integration, retry flow, explanation flow, value verification/value lookup และ provider compatibility layer

---

## Refactor Objectives

1. ลดขนาดไฟล์ใหญ่ที่เป็น bottleneck ใน review และ maintenance
2. แยก responsibility โดยไม่เปลี่ยน public API contract หรือ business behavior โดยไม่จำเป็น
3. เปิดทางให้เขียน tests ราย module ได้ง่ายขึ้น
4. ทำแบบ incremental refactor ไม่ทำ big-bang rewrite

---

## Execute Readiness Adjustments

แผนฉบับนี้ถูกปรับให้พร้อม execute มากขึ้นจากข้อเท็จจริงใน repo ปัจจุบัน

1. route modules ใหม่ต้อง delegate ไปยัง service ที่มีอยู่แล้วก่อน ไม่ใช่ย้าย business logic เข้า route file
2. API key Pydantic models ให้ย้ายไป [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py) โดยตรง ไม่สร้าง `shared.py` เพียงเพื่อรองรับ models 3 ตัวนี้
3. การแตก `schema_service.py` และ `ai_service.py` ต้องคง import path เดิมด้วย compatibility shim ชั่วคราว เพราะทั้ง codebase import path เดิมกระจายอยู่หลายจุด
4. hierarchy cache ของ `ai_service.py` ต้อง merge เข้ากับ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) ไม่สร้างไฟล์ cache ซ้ำ
5. [app/api/v1/admin_agent.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin_agent.py) mount อยู่ใต้ prefix `/api/v1/admin` เหมือนกัน แต่ไม่รวมอยู่ในงาน split รอบแรก และต้องระวัง path conflict ตลอดการ refactor
6. effort estimate จะใช้ working days ต่อ phase เพื่อให้ scope ได้ชัดตอน execute จริง
7. cache logic ของ `SchemaService` จะยังอยู่ใน facade/service file ไม่แตกเป็น `cache.py`

---

## Priority Order

1. [app/api/v1/admin.py](app/api/v1/admin.py)
2. [app/services/schema_service.py](app/services/schema_service.py)
3. [app/services/ai_service.py](app/services/ai_service.py)

เหตุผล

- `admin.py` เป็น mechanical split ที่ชัดที่สุดและกระทบ productivity สูงสุด
- `schema_service.py` มี risk เชิง security/design สูงและมีหลาย subdomains ชัดเจน
- `ai_service.py` ควรแตกหลังจาก schema seams ชัดขึ้น เพราะมันพึ่ง schema/prompt/context หลายจุด

---

## 1. Plan for admin.py

## Problem Summary

[app/api/v1/admin.py](app/api/v1/admin.py) รวม endpoints หลาย domain ในไฟล์เดียว ทำให้

- merge conflict สูง
- review ยาก
- import graph หนาแน่น
- helper และ schema ปนหลาย concern

## Refactor Strategy

เป้าหมายคือแปลงจาก single module เป็น package โดย **คง path เดิมทั้งหมด**

### Existing services that must be reused

route files ใหม่ต้องพึ่ง service เดิมให้ชัด

- [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
  - CRUD, search, extract, diff, unmatched keyword logging
- [app/services/admin_config_service.py](/Users/seal/Documents/GitHub/AI/app/services/admin_config_service.py)
  - runtime config, feature flags, providers/models
- [app/services/context_onboarding.py](/Users/seal/Documents/GitHub/AI/app/services/context_onboarding.py)
  - inspect, analyze, generate, apply, validate pipeline
- [app/services/api_key_service.py](/Users/seal/Documents/GitHub/AI/app/services/api_key_service.py)
  - create, validate, revoke, usage tracking

กติกาคือ: ถ้า endpoint เดิมมี inline business logic ที่จริงควรอยู่ใน service ให้ย้าย logic นั้นออกระหว่าง split แต่อย่า duplicate logic ใส่ route module ใหม่

### Target structure

```text
app/api/v1/admin/
  __init__.py
  _utils.py
  schema.py
  mappings.py
  rules.py
  golden_examples.py
  contexts.py
  onboarding.py
  providers.py
  hierarchy.py
  warnings.py
  query_patterns.py
  analytics.py
  api_keys.py
```

### Responsibility split

- `schema.py`
  - schema column CRUD
  - table/view endpoints
  - mapping suggestion
  - view summary
  - propagate metadata
  - dimension family endpoints
- `mappings.py`
  - semantic mappings CRUD
- `rules.py`
  - business rules CRUD + toggle
- `golden_examples.py`
  - golden examples CRUD + categories
- `contexts.py`
  - context CRUD only
- `onboarding.py`
  - onboardable views
  - inspect/apply/validate/onboard flow
  - delegate ไป `ContextOnboardingService`
  - `_get_business_db_path` ย้ายไป `_utils.py`
- `providers.py`
  - AI config
  - feature flags
  - providers/models CRUD
  - config cache clear / rebuild keyword index
  - delegate ไป `AdminConfigService`
- `hierarchy.py`
  - levels, values, extract, bootstrap, import CSV, diff, unmatched, search
  - delegate ไป `HierarchyService`
- `warnings.py`
  - data warnings CRUD
- `query_patterns.py`
  - query patterns CRUD
- `analytics.py`
  - dashboard stats
  - refresh cache / sync brain / clear query cache
  - query logs / feedback details / query analytics
- `api_keys.py`
  - API key CRUD + usage
  - delegate ไป `APIKeyService`

### Shared code to extract first

ก่อนย้าย endpoints ควรดึงของกลางออกก่อน

- imports ของ `deps`, `User`, `Session`
- common service factories
- common error/404 helpers ถ้ามี pattern ซ้ำ
- small utility helpers เช่น metadata row ensure, business DB path resolver

### Pre-step ก่อนเริ่ม Phase A

ต้องทำ step นี้ก่อน commit แรกของ admin split

- ย้าย `APIKeyCreateRequest`, `APIKeyResponse`, `APIKeyCreateResponse` จาก [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) ไป [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py)
- ปรับ import ใน route เดิมให้ใช้ schema file กลาง
- ยืนยันว่า route ใหม่จะไม่สร้าง Pydantic models inline เพิ่มอีก

### Router wiring

ใน [app/api/v1/admin/__init__.py](app/api/v1/admin/__init__.py)

```python
from fastapi import APIRouter

router = APIRouter()

from .schema import router as schema_router
from .mappings import router as mappings_router
from .rules import router as rules_router
from .golden_examples import router as golden_examples_router
from .contexts import router as contexts_router
from .onboarding import router as onboarding_router
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
router.include_router(providers_router)
router.include_router(hierarchy_router)
router.include_router(warnings_router)
router.include_router(query_patterns_router)
router.include_router(analytics_router)
router.include_router(api_keys_router)
```

สำคัญ: ไม่ใส่ `prefix="/admin"` ที่ subpackage level เพราะ [app/main.py](app/main.py) ใส่ prefix อยู่แล้ว

ต้องระวังเพิ่มอีกข้อ: [app/api/v1/admin_agent.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin_agent.py) ก็ถูก mount ด้วย prefix เดียวกันใน [app/main.py](/Users/seal/Documents/GitHub/AI/app/main.py) ดังนั้น split ของ admin router ต้องไม่ไปแตะ path `/agent/...` และไม่รวม admin-agent เข้า package นี้ในรอบแรก

## Execution phases

### Phase A

- สร้าง package `app/api/v1/admin/`
- ย้าย `schema.py` + `mappings.py` + `rules.py` + `golden_examples.py`
- เป็นกลุ่ม CRUD เรียบง่ายประมาณ 4 domains, ~20 endpoints
- ตรวจ inline helper ว่ามีอันไหนควรอยู่ใน service/helper มากกว่า route
- estimate: 1.5-2.0 working days

### Phase B

- ย้าย contexts + onboarding
- ย้าย `_get_business_db_path` ไป `_utils.py`
- `onboarding.py` ต้อง delegate ไป `ContextOnboardingService` เป็นหลัก
- estimate: 1.0-1.5 working days

### Phase C

- ย้าย providers/models/config/features
- ย้าย api_keys
- `providers.py` ต้อง delegate ไป `AdminConfigService`
- `api_keys.py` ต้องใช้ models จาก [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py) และ delegate ไป `APIKeyService`
- estimate: 1.0-1.5 working days

### Phase D

- ย้าย hierarchy, warnings, query_patterns, analytics
- `hierarchy.py` ต้อง delegate ไป `HierarchyService`
- estimate: 1.5-2.0 working days

### Phase E

- ลบ [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) เดิม
- verify imports
- verify tests
- verify frontend calls
- estimate: 0.5-1.0 working days

### Execution rule

- แต่ละ phase ควรเป็น commit แยก
- run tests ก่อนขยับไป phase ถัดไป
- ถ้า phase ไหนเริ่มต้องแตะ behavior มากกว่า router split ให้หยุดและย้าย logic เข้า service/helper ก่อนค่อยไปต่อ

## Validation

- verify import ใน [app/main.py](app/main.py) ยังทำงานเหมือนเดิม
- run targeted tests สำหรับ admin endpoints
- grep เส้นทาง endpoint เดิมเพื่อ confirm ว่า path ไม่เปลี่ยน
- smoke check admin UI services ที่เรียก `/api/v1/admin/...`

### Admin.py Definition of Ready

ถือว่าเริ่ม execute ได้เมื่อ

1. API key models ถูกย้ายไป [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py) แล้ว
2. phase plan A-E ถูกใช้ตามลำดับ ไม่ข้ามลำดับ
3. ตกลงชัดว่ารอบนี้ไม่รวม [app/api/v1/admin_agent.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin_agent.py)
4. route modules ใหม่จะ delegate ไป service เดิมก่อนเสมอ

---

## 2. Plan for schema_service.py

## Problem Summary

[app/services/schema_service.py](app/services/schema_service.py) รวม responsibility หลักอย่างน้อย 5 กลุ่ม

- view management
- metadata propagation / lookup
- context management
- dimension family logic
- prompt building / schema text / semantic mapping text / business rules text
- cache management

นั่นหมายความว่าไฟล์นี้ควรถูกแตก ไม่ใช่เลื่อนออกไป

## Refactor Strategy

ไม่ควรแตกเป็นหลาย class ใหญ่ที่ state ซ้ำกันทันที แต่ควรแยกเป็น helper modules หรือ collaborator classes ที่รับ `SchemaService` state ผ่าน constructor/arguments อย่างชัดเจน

### Import compatibility rule

เพราะ import เดิมกระจายอยู่ทั่วระบบ ต้องคง path เดิมชั่วคราว

- เก็บ [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) ไว้เป็น shim ในช่วง migrate
- shim จะ re-export `SchemaService` และ helper public functions จาก package ใหม่
- ค่อยทำ import migration ทีหลังเมื่อ behavior คงที่แล้ว

ตัวอย่าง shim

```python
from app.services.schema.service import SchemaService  # noqa: F401
from app.services.schema.service import create_claude_prompt, create_gemini_prompt  # noqa: F401
```

### Target structure

```text
app/services/schema/
  __init__.py
  service.py
  view_manager.py
  metadata_propagation.py
  context_store.py
  dimension_families.py
  prompt_builder.py
```

### Responsibility split

- `service.py`
  - เก็บ `SchemaService` facade class
  - เก็บ constructor, engine resolution, public surface หลัก
- `view_manager.py`
  - `get_all_tables`
  - `create_custom_view`
  - `list_views_with_mappings`
  - `save_view_column_mappings`
  - `get_view_column_mappings`
- `metadata_propagation.py`
  - `_find_source_metadata`
  - `propagate_metadata_to_view`
- `context_store.py`
  - `get_context_info`
  - `get_all_contexts`
  - context CRUD-ish internals if still used from service
- `dimension_families.py`
  - `get_dimension_families`
  - `get_dimension_families_with_source`
  - analyze / batch update / auto populate support if present later in file
- `prompt_builder.py`
  - `build_schema_text`
  - `build_business_rules_text`
  - `build_sample_values_text`
  - `build_semantic_mapping_text`
  - `build_system_prompt`
  - few-shot/query-pattern/warnings prompt sections if present deeper in file

หมายเหตุ: cache logic (`self._cache`, `self._context_cache`, `refresh_cache()`) คงไว้ใน `service.py` เพราะเล็กและผูกกับ facade โดยตรง การแยก `cache.py` ไม่คุ้มกับ cognitive overhead

### Recommended pattern

คง external API เป็น `SchemaService` เหมือนเดิมก่อน แล้วให้ facade delegate ไปยัง collaborator

ตัวอย่าง

```python
class SchemaService:
    def __init__(...):
        ...
        self.view_manager = ViewManager(self)
        self.prompt_builder = PromptBuilder(self)

    def build_system_prompt(self, ...):
        return self.prompt_builder.build_system_prompt(...)
```

ข้อดี

- ไม่ต้องเปลี่ยน dependency injection ฝั่ง API/services ทั่วระบบทันที
- ย้าย logic ออกได้ทีละก้อน

## Execution phases

### Phase A

- สร้าง package `app/services/schema/`
- ย้าย prompt-building functions ก่อน เพราะเป็น concern ชัดและทดสอบง่าย
- สร้าง shim ที่ [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) ตั้งแต่ phase นี้
- estimate: 1.0-1.5 working days

### Phase B

- ย้าย view management + metadata propagation
- ใน phase นี้ควรแก้ SQL interpolation ใน `create_custom_view` ไปพร้อมกัน
- estimate: 1.0-1.5 working days

### Phase C

- ย้าย context loading + dimension family logic
- เหลือ facade class บางลง
- estimate: 1.0-1.5 working days

## Validation

- compare output ของ `build_system_prompt()` ก่อนและหลัง refactor
- compare output ของ `get_context_info()` และ `get_dimension_families()` ก่อนและหลัง
- smoke test view creation / metadata propagation ผ่าน admin endpoints

---

## 3. Plan for ai_service.py

## Problem Summary

[app/services/ai_service.py](app/services/ai_service.py) มีอย่างน้อย 4 responsibility ใหญ่

- provider compatibility / legacy constructor layer
- hierarchy cache + DB-backed hierarchy loading
- query orchestration (`query_with_retry`, `query_hybrid`)
- explanation / extraction / retry helper logic
- Vanna context injection และ value verification/value lookup paths

## Refactor Strategy

ไม่ควรพยายามแยก `query_hybrid()` ออกเป็น micro-functions ครั้งเดียว เพราะ risk สูง แต่ควรดึง seam ที่ชัดก่อน แล้วค่อย split orchestrator helpers รอบถัดไป

### Import compatibility rule

เช่นเดียวกับ schema service, path เดิมต้องยังใช้ได้ก่อน

- เก็บ [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) ไว้เป็น shim ชั่วคราว
- shim จะ re-export `AIService`, `create_claude_service`, `create_gemini_service`, `create_matcha_service`

ตัวอย่าง shim

```python
from app.services.ai.service import AIService  # noqa: F401
from app.services.ai.factory import create_claude_service, create_gemini_service, create_matcha_service  # noqa: F401
```

### Target structure

```text
app/services/ai/
  __init__.py
  service.py
  factory.py
  prompt_context.py
  result_parser.py
  hybrid_executor.py
```

### Responsibility split

- `service.py`
  - เก็บ `AIService` facade/class หลัก
- `factory.py`
  - `create_claude_service`
  - `create_gemini_service`
  - `create_matcha_service`
- `prompt_context.py`
  - `_get_vanna_context_string`
  - helper สำหรับ injecting RAG/value lookup context ลง prompt
- `result_parser.py`
  - SQL extraction
  - explanation extraction
  - data preparation for explanation
  - formatting helpers ที่ไม่ต้องพึ่ง heavy class state มาก
- `hybrid_executor.py`
  - helper methods ที่แตกออกจาก `query_hybrid()` ได้แบบ low-risk
  - เช่น generate SQL step, validate step, execute step, explain step

### What not to do in first pass

- อย่า rewrite `query_hybrid()` ใหม่ทั้งก้อน
- อย่าเปลี่ยน public constructor behavior พร้อมกันหลายจุด
- อย่าเปลี่ยน provider contract ระหว่างแตกไฟล์

### Recommended incremental cuts

#### Cut 1

- ย้าย factories ออกก่อน
- merge `_load_hierarchies_from_db()` และ `get_column_hierarchies()` เข้า [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
- ปรับ invalidation ให้ `HierarchyService` เป็นเจ้าของ cache concern นี้แทน
- ความเสี่ยงต่ำและไม่กระทบ orchestration หลัก
- estimate: 1.0-1.5 working days

#### Cut 2

- ย้าย parse/format helpers ที่เป็น pure-ish logic ออก
- estimate: 1.0-1.5 working days

#### Cut 3

- แตก `query_hybrid()` ภายใน class เป็น private helper methods ก่อน แม้ยังอยู่ไฟล์เดิม
- เมื่อ seam ชัดค่อยย้าย helper methods ไป `hybrid_executor.py`
- estimate: 1.5-2.0 working days

ตัวอย่าง helper seam ที่ควรมี

- `_build_initial_user_prompt(...)`
- `_build_retry_user_prompt(...)`
- `_generate_sql_attempt(...)`
- `_validate_sql_attempt(...)`
- `_execute_sql_attempt(...)`
- `_build_explanation(...)`

## Validation

- regression test สำหรับ query flows ที่มีอยู่แล้ว
- compare `QueryResult` shape ก่อนและหลัง
- smoke test provider creation paths ทั้ง legacy และ new-style provider instance

---

## Cross-File Constraints

มีข้อจำกัดร่วมที่ต้องรักษาระหว่าง refactor

1. Public imports เดิมต้องยังใช้ได้ชั่วคราว
2. API endpoint paths ต้องไม่เปลี่ยน
3. Dependency injection ของ FastAPI ต้องไม่พัง
4. tests ที่มีอยู่ควรรันได้โดยไม่ต้องแก้ใหญ่ในรอบแรก
5. แยกแบบ facade-first ไม่ใช่ rewrite architecture ทั้งระบบในครั้งเดียว
6. admin split ต้องไม่ชน path ของ [app/api/v1/admin_agent.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin_agent.py)
7. route files ใหม่ต้อง delegate ไป service เดิมก่อน ยกเว้น utility เล็กมากที่ชัดว่าไม่ใช่ business logic

---

## Suggested Delivery Plan

## Milestone 1

- pre-step: ย้าย API key schemas ไป [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py)
- แตก [app/api/v1/admin.py](app/api/v1/admin.py) Phase A
- ไม่แตะ `schema_service.py` / `ai_service.py` มากเกินจำเป็น
- duration: 1.5-2.0 working days

## Milestone 2

- แตก admin Phase B-C
- ปิด route delegation ของ onboarding/providers/api keys ให้ชัด
- duration: 2.0-3.0 working days

## Milestone 3

- แตก admin Phase D-E
- ปิดงาน admin split พร้อม verify frontend calls
- duration: 2.0-3.0 working days

## Milestone 4

- เริ่ม schema_service refactor พร้อม shim path เดิม
- duration: 3.0-4.5 working days

## Milestone 5

- เริ่ม ai_service refactor แบบ incremental cuts
- merge hierarchy cache concern เข้ากับ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
- duration: 3.5-5.0 working days

---

## Effort / Risk Estimate

| Scope | Priority | Risk | Effort |
| --- | --- | --- | --- |
| [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) Phase A | Highest | Medium | 1.5-2.0 working days |
| [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) Phase B | Highest | Medium | 1.0-1.5 working days |
| [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) Phase C | Highest | Medium | 1.0-1.5 working days |
| [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) Phase D | Highest | Medium-High | 1.5-2.0 working days |
| [app/api/v1/admin.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin.py) Phase E | Highest | Low-Medium | 0.5-1.0 working days |
| [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) | High | Medium-High | 3.0-4.5 working days |
| [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) | High | High | 3.5-5.0 working days |

หมายเหตุ

- `admin.py` รอบแรกควร lock เป็น router split + delegate-first ไม่ใช่ service rewrite ใหญ่
- `schema_service.py` ต้องใช้ shim path เดิม ไม่อย่างนั้นจะบานเป็น global import migration
- `ai_service.py` ต้องทำแบบ incremental seams และ merge hierarchy cache เข้ากับ service เดิมที่มีอยู่แล้ว

---

## Definition of Done

จะถือว่าแผนนี้เสร็จเมื่อ

1. `admin.py` ถูกแยกเป็น package ตาม phase A-E โดย path `/api/v1/admin/...` เดิมไม่เปลี่ยน และไม่ชนกับ [app/api/v1/admin_agent.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin_agent.py)
2. route files ใหม่ของ admin delegate ไปยัง [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py), [app/services/admin_config_service.py](/Users/seal/Documents/GitHub/AI/app/services/admin_config_service.py), [app/services/context_onboarding.py](/Users/seal/Documents/GitHub/AI/app/services/context_onboarding.py), [app/services/api_key_service.py](/Users/seal/Documents/GitHub/AI/app/services/api_key_service.py) ตาม domain จริง
3. [app/schemas/admin_schemas.py](/Users/seal/Documents/GitHub/AI/app/schemas/admin_schemas.py) เป็นที่อยู่ของ API key schemas แทน inline models
4. [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) เหลือ facade/shim ที่คง import path เดิม และ prompt/view logic ถูกแยก module แล้วโดย cache logic ยังอยู่ใน service
5. [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) เหลือ facade/shim ที่คง import path เดิม, factories ถูกแยก, และ hierarchy cache concern ถูก merge เข้ากับ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
6. tests สำคัญยังผ่าน และ public API behavior ไม่เปลี่ยน
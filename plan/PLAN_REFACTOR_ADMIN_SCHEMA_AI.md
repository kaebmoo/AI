# Refactor Plan - admin.py, schema_service.py, ai_service.py

> Scope: former admin monolith now at [app/api/v1/admin/__init__.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/__init__.py), [app/services/schema_service.py](app/services/schema_service.py), [app/services/ai_service.py](app/services/ai_service.py)
> Snapshot date: 2026-03-22
> Goal: ลดขนาด monolith, แยก bounded responsibilities, ลด regression risk โดยคง API behavior เดิมไว้

## Final Status

Status ของแผนนี้ ณ snapshot ปัจจุบันคือ completed

- admin router split เสร็จและ validate แล้ว
- schema service package split + compatibility shim เสร็จและ validate แล้ว
- ai service package split + compatibility shim + retry/hybrid seam extraction เสร็จและ validate แล้ว
- targeted regression `./venv/bin/pytest tests/unit/test_ai_service.py tests/unit/test_phase_completion.py` ผ่าน 65 tests
- broader unit suite `./venv/bin/pytest tests/unit` ผ่าน 336 tests และ skipped 3

หมายเหตุสำคัญ:

- เนื้อหาหลายส่วนด้านล่างยังคงเก็บ reasoning, baseline, estimates, และ delivery plan เดิมไว้เป็นบันทึกการ execute
- งานที่ยังพูดถึงหลังจากนี้ให้ถือเป็น follow-up cleanup แยก ไม่ใช่ blocker ของ refactor รอบนี้
- follow-up ของ [app/services/analyzer_service.py](/Users/seal/Documents/GitHub/AI/app/services/analyzer_service.py) ถูกปิดแล้วโดยเปลี่ยนให้เรียก `ai_service.provider.generate_content(...)` ตาม public surface ที่ใช้อยู่จริง และเพิ่ม regression tests แล้ว

### Status Matrix For Remaining Questions

| Item | Status | Notes |
| --- | --- | --- |
| Cut 5 cleanup / lint noise ใน modules ใหม่ | Closed for this refactor pass | Cut 5 ถูก implement และ validate แล้ว; lint/static-analysis noise ที่ยังเหลือบางจุดนับเป็น debt ต่อเนื่อง ไม่ใช่งานค้างของ cut |
| [app/services/analyzer_service.py](/Users/seal/Documents/GitHub/AI/app/services/analyzer_service.py) follow-up | Closed | เดิมอยู่นอก scope รอบแรก แต่ follow-up ถูกปิดแล้วพร้อม regression tests |
| `_detect_hierarchy_level()` route ผ่าน shim | Acceptable debt | behavior ถูกต้องและตั้งใจ preserve monkeypatch seam เดิม; ยังเป็น minor inconsistency ที่ค่อยเก็บตอน cleanup ได้ |
| hierarchy cache owner transfer ไป [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) | Future optional | pass แรกใช้ bridge + in-place mutation ตามแผน; owner transfer ไม่ใช่ requirement บังคับ |

---

## Current Baseline

จาก repository ก่อนเริ่ม refactor รอบนี้

- former `app/api/v1/admin.py`: 2639 lines before package split
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

1. admin router package conversion from the former monolith path to [app/api/v1/admin/__init__.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/__init__.py)
2. [app/services/schema_service.py](app/services/schema_service.py)
3. [app/services/ai_service.py](app/services/ai_service.py)

เหตุผล

- `admin.py` เป็น mechanical split ที่ชัดที่สุดและกระทบ productivity สูงสุด
- `schema_service.py` มี risk เชิง security/design สูงและมีหลาย subdomains ชัดเจน
- `ai_service.py` ควรแตกหลังจาก schema seams ชัดขึ้น เพราะมันพึ่ง schema/prompt/context หลายจุด

---

## 1. Plan for admin.py

Execution status: implemented and validated on 2026-03-22

Verified outcomes:

- package import works from [app/main.py](/Users/seal/Documents/GitHub/AI/app/main.py)
- route count remains 95
- onboarding and API key focused tests pass after split
- compatibility shim was required for `_get_business_db_path` and function-local onboarding service imports to preserve existing test seams

Remaining admin follow-up is now cleanup, not structural split:

- reduce static-analysis noise in the new route modules where worthwhile
- keep `admin_agent.py` path isolation intact while later refactors proceed

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

Execution status: implemented and validated on 2026-03-22

Goal ของรอบนี้ไม่ใช่ rewrite service แต่คือทำให้ [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) กลายเป็น facade ที่บางลง โดย public import path และ dependency injection ยังใช้ได้เหมือนเดิม

## Problem Summary

[app/services/schema_service.py](app/services/schema_service.py) รวม responsibility หลักอย่างน้อย 5 กลุ่ม

- view management
- metadata propagation / lookup
- context management
- dimension family logic
- prompt building / schema text / semantic mapping text / business rules text
- cache management

จากโค้ดจริงยังมีอีก 1 concern ที่แผนเดิมควรนับรวมด้วย

- keyword index / known-term lookup (`get_searchable_columns`, `build_keyword_index`, `search_keyword_index`, `search_db_for_keyword`, `get_known_terms`)

นั่นหมายความว่าไฟล์นี้ควรถูกแตก ไม่ใช่เลื่อนออกไป

### Observed method clusters from current file

จาก [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) ปัจจุบัน method grouping ที่เห็นชัดคือ

- engine + cache facade
  - `__init__`, `_get_connection`, `_get_config_connection`, `refresh_cache`, `refresh_context_cache`, `get_cached_prompt`
- view management
  - `get_all_tables`, `create_custom_view`, `list_views_with_mappings`, `save_view_column_mappings`, `get_view_column_mappings`, `get_table_info`
- metadata propagation
  - `_find_source_metadata`, `propagate_metadata_to_view`, `get_date_format`
- context store
  - `get_context_info`, `get_all_contexts`, `create_context`, `update_context`, `delete_context`
- dimension and instruction helpers
  - `build_hierarchy_rule_text`, `build_instruction_rules_text`, `get_dimension_families`, `get_dimension_families_with_source`
- prompt context builder
  - `get_sample_values`, `build_schema_text`, `build_business_rules_text`, `build_sample_values_text`, `build_semantic_mapping_text`, `get_schema_context`, `build_system_prompt`, `get_default_instruction`, `_build_thai_prompt`, `_build_english_prompt`, `_get_date_instructions`
- keyword lookup
  - `get_searchable_columns`, `build_keyword_index`, `_extract_keywords`, `search_keyword_index`, `search_db_for_keyword`, `get_known_terms`
- module-level public factory functions
  - `create_claude_prompt`, `create_gemini_prompt`

### Constraints from current usage

`SchemaService` ถูกใช้กว้างมากในระบบปัจจุบัน ทั้งผ่าน DI และ instantiate ตรง เช่น

- [app/api/deps.py](/Users/seal/Documents/GitHub/AI/app/api/deps.py)
- [app/api/v1/chat.py](/Users/seal/Documents/GitHub/AI/app/api/v1/chat.py)
- [app/api/v1/schema_analyzer.py](/Users/seal/Documents/GitHub/AI/app/api/v1/schema_analyzer.py)
- [app/services/query_engine.py](/Users/seal/Documents/GitHub/AI/app/services/query_engine.py)
- [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py)
- [app/services/vanna_service.py](/Users/seal/Documents/GitHub/AI/app/services/vanna_service.py)
- admin route modules ที่เพิ่ง split เสร็จ

สรุป: ห้ามทำ import migration พร้อมกับ refactor รอบแรก

ข้อสังเกตเพิ่มจาก current callers ของ keyword-index methods

- `search_keyword_index()` และ `get_known_terms()` ถูกเรียกจาก [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py)
- `build_keyword_index()` ถูกเรียกผ่าน admin config endpoint ที่ [app/api/v1/admin/config.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/config.py)
- `get_searchable_columns()` ถูกใช้โดย [app/services/warning_detector.py](/Users/seal/Documents/GitHub/AI/app/services/warning_detector.py)

ดังนั้น keyword-index concern เป็น low-risk cut ที่ดี และมี external callers ชัด แต่ coupling ภายใน `SchemaService` ต่ำ

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
  keyword_index.py
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
- `keyword_index.py`
  - `get_searchable_columns`
  - `build_keyword_index`
  - `_extract_keywords`
  - `search_keyword_index`
  - `search_db_for_keyword`
  - `get_known_terms`

หมายเหตุ: cache logic (`self._cache`, `self._context_cache`, `refresh_cache()`) คงไว้ใน `service.py` เพราะเล็กและผูกกับ facade โดยตรง การแยก `cache.py` ไม่คุ้มกับ cognitive overhead

### Important boundary: data access vs formatting

`prompt_builder.py` ควรรับผิดชอบเฉพาะการ format/compose prompt text ไม่ควรย้าย data-access methods ไปอยู่ใน module นี้

methods ที่ควรยังอยู่บน facade/service layer และถูกเรียกผ่าน `self` หรือ collaborator reference ได้แก่

- `get_schema_metadata()`
- `get_business_rules()`
- `get_semantic_mappings()`
- `get_sample_values()`
- `get_table_info()`

pattern ที่ควรใช้

```python
class PromptBuilder:
    def __init__(self, service: "SchemaService"):
        self._service = service

    def build_semantic_mapping_text(self, context_name=None):
        mappings = self._service.get_semantic_mappings(context_name=context_name)
        ...
```

เหตุผล

- data query methods ยังถูกใช้จากหลายที่ ไม่ใช่ prompt builder อย่างเดียว
- ลด risk จากการกระจาย DB access across many modules too early

### Important boundary: keyword index cache state

ปัจจุบัน `_known_terms_cache` เป็น class-level mutable state ใน `SchemaService`

```python
_known_terms_cache: dict = {}
_known_terms_ts: float = 0
```

ตอนย้ายไป `keyword_index.py` ต้องเลือกหนึ่งทางให้ชัด

- เก็บเป็น module-level cache ใน `keyword_index.py` เพื่อรักษา behavior ใกล้เดิมที่สุด
- หรือย้ายเป็น instance-owned cache ถ้ายอมรับ behavior change เล็กน้อยได้

สำหรับรอบแรกแนะนำทางแรก เพราะ regression risk ต่ำกว่า

ข้อกำหนดตามมาคือ `SchemaService.refresh_cache()` ต้อง clear keyword-index cache ด้วย ไม่ใช่แค่ `_cache` และ `_context_cache`

### Compatibility shape that should be implemented

รอบแรกให้ปลายทาง import เดิมยังทำงานแบบนี้

- [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) กลายเป็น compatibility shim
- [app/services/schema/__init__.py](/Users/seal/Documents/GitHub/AI/app/services/schema/__init__.py) export `SchemaService`, `create_claude_prompt`, `create_gemini_prompt`
- [app/api/deps.py](/Users/seal/Documents/GitHub/AI/app/api/deps.py) ยังไม่ต้องแก้ import path ใน phase แรก

ตัวอย่าง target

```python
# app/services/schema_service.py
from app.services.schema.service import SchemaService  # noqa: F401
from app.services.schema.service import create_claude_prompt, create_gemini_prompt  # noqa: F401
```

### Test gap to close before moving code

ตอนนี้ยังไม่เห็น test file เฉพาะของ `schema_service.py` ใน repo ดังนั้นก่อนเริ่มย้าย code ต้องทำ characterization tests ก่อน

ขั้นต่ำที่ต้องล็อก behavior

- `build_system_prompt()` สำหรับอย่างน้อย 2 contexts
- `get_context_info()` และ `get_all_contexts()`
- `get_dimension_families_with_source()`
- `create_custom_view()` + `propagate_metadata_to_view()` บน temp DB หรือ fixture DB
- `build_keyword_index()` / `search_keyword_index()` basic flow

ควรเพิ่ม snapshot-style comparison สำหรับ prompt outputs ที่มีโอกาสยาวและเปราะบางกับ formatting ด้วย เพื่อให้จับ regression เชิงข้อความได้เร็ว

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

### Phase 0

- เพิ่ม characterization tests สำหรับ public surface ที่เสี่ยง regression
- บันทึก baseline outputs ของ:
  - `build_system_prompt(context_name="revenue")`
  - `build_system_prompt(context_name="expense")` ถ้ามี fixture รองรับ
  - `get_context_info()`
  - `get_dimension_families_with_source()`
  - `build_keyword_index()` + `search_keyword_index()`
- ระบุ methods ที่ external callers ใช้อยู่จริงจาก grep ปัจจุบันเป็น “must preserve” list
- estimate: 0.5-1.0 working days

Status update:
- Completed initial characterization slice for keyword/index behavior in [tests/unit/test_schema_service_keyword_index.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_keyword_index.py)
- Covered compatibility import surface, `build_keyword_index()`, `search_keyword_index()`, `get_searchable_columns()`, and `refresh_cache()` clearing known-terms cache
- Prompt/context characterization is still pending for later phases

### Phase A

- สร้าง package `app/services/schema/`
- สร้าง `service.py` เป็น facade ใหม่ แต่ยัง copy public constructor behavior เดิมทั้งหมด
- ย้าย keyword-index / known-terms logic ไป `keyword_index.py` ก่อน
- wiring facade methods ให้ delegate ไป keyword module โดย public API เดิมไม่เปลี่ยน
- สร้าง shim ที่ [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) ตั้งแต่ phase นี้
- verify ว่า callers ของ `search_keyword_index()`, `get_known_terms()`, `get_searchable_columns()` ยังทำงาน
- estimate: 0.5-1.0 working days

Status update:
- Completed first extraction slice:
  - [app/services/schema/service.py](/Users/seal/Documents/GitHub/AI/app/services/schema/service.py) is now the package facade copy
  - [app/services/schema/keyword_index.py](/Users/seal/Documents/GitHub/AI/app/services/schema/keyword_index.py) owns keyword-index and known-terms logic
  - [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) is now a compatibility shim
- `refresh_cache()` in the facade now clears keyword known-terms cache explicitly
- Regression checks passed for:
  - [tests/unit/test_schema_service_keyword_index.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_keyword_index.py)
  - [tests/unit/test_phase_completion.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_phase_completion.py)

### Phase B

- ย้าย prompt-building functions ไป `prompt_builder.py`
- ย้าย instruction/hierarchy text helpers ที่ผูกกับ prompt ไป phase นี้ด้วย
- data-access methods ที่ prompt builder ใช้ยังคงอยู่บน facade/service layer แล้วให้ builder เรียกผ่าน service reference
- verify output comparison ของ `build_system_prompt()` ก่อนและหลังอย่างน้อย 2 contexts
- estimate: 1.0-1.5 working days

Status update:
- Completed prompt-builder extraction slice:
  - [app/services/schema/prompt_builder.py](/Users/seal/Documents/GitHub/AI/app/services/schema/prompt_builder.py) now owns prompt composition helpers
  - [app/services/schema/service.py](/Users/seal/Documents/GitHub/AI/app/services/schema/service.py) delegates `build_schema_text()`, `build_business_rules_text()`, `build_sample_values_text()`, `build_semantic_mapping_text()`, `get_schema_context()`, `build_system_prompt()`, and `get_default_instruction()`
- Added prompt characterization tests in [tests/unit/test_schema_service_prompt_builder.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_prompt_builder.py)
- Regression checks passed for prompt slice together with earlier compatibility tests

### Phase C

- ย้าย view management + metadata propagation
- ใน phase นี้ต้องเก็บ SQL interpolation risk ใน `create_custom_view` ไปพร้อมกัน โดยไม่เปลี่ยน behavior ภายนอก
- เพิ่ม validation ให้ `source_table` ด้วย ไม่ใช่ validate แค่ `view_name`
- ย้าย `get_table_info()` และ `get_date_format()` ไป module เดียวกับ view/metadata ถ้าช่วยลด coupling
- smoke test ผ่าน admin schema endpoints ที่แตะ view creation / propagation
- estimate: 1.0-1.5 working days

Status update:
- Completed view/metadata extraction slice:
  - [app/services/schema/view_manager.py](/Users/seal/Documents/GitHub/AI/app/services/schema/view_manager.py) now owns view creation, mapping persistence, and metadata propagation helpers
  - [app/services/schema/service.py](/Users/seal/Documents/GitHub/AI/app/services/schema/service.py) delegates view-management methods to the module
- `create_custom_view()` now validates `view_name`, `source_table`, source columns, and aliases before SQL interpolation
- Added regression coverage for view creation, metadata propagation, and view summary behavior in [tests/unit/test_schema_service_remaining_modules.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_remaining_modules.py)

### Phase D

- ย้าย context loading + dimension family logic
- ล้าง import ภายใน package ใหม่ให้เหลือ dependency ทิศทางเดียว
- รัน caller smoke tests สำหรับ chat/admin/query paths ที่ instantiate `SchemaService`
- ยืนยันว่า shim file [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) export surface ครบ
- verify ว่า `refresh_cache()` clear ทั้ง prompt/context caches และ keyword-index cache ตามที่ออกแบบไว้
- estimate: 0.5-1.0 working days

Status update:
- Completed context/dimension extraction slice:
  - [app/services/schema/context_store.py](/Users/seal/Documents/GitHub/AI/app/services/schema/context_store.py) now owns context CRUD and cache refresh helpers
  - [app/services/schema/dimension_families.py](/Users/seal/Documents/GitHub/AI/app/services/schema/dimension_families.py) now owns dimension family merge logic
  - [app/services/schema/service.py](/Users/seal/Documents/GitHub/AI/app/services/schema/service.py) delegates the remaining context and dimension-family methods
- Added regression coverage for context normalization/CRUD and dimension-family merge behavior in [tests/unit/test_schema_service_remaining_modules.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_remaining_modules.py)

## Validation

- compare output ของ `build_system_prompt()` ก่อนและหลัง refactor
- compare output ของ `get_context_info()` และ `get_dimension_families()` ก่อนและหลัง
- smoke test view creation / metadata propagation ผ่าน admin endpoints
- verify keyword-index flows ก่อนและหลัง:
  - `build_keyword_index()`
  - `search_keyword_index()`
  - `get_known_terms()`
- verify DI path ใน [app/api/deps.py](/Users/seal/Documents/GitHub/AI/app/api/deps.py) ยังคืน `SchemaService` ที่ใช้งานได้

### SchemaService Definition of Ready

ถือว่าเริ่ม execute ได้เมื่อ

1. ตกลงว่า phase แรกจะใช้ compatibility shim ที่ [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py)
2. มี characterization tests สำหรับ prompt/context/view/keyword-index อย่างน้อยระดับ smoke
3. ยืนยันแล้วว่ารอบแรกจะไม่ย้าย import callers ทั่วระบบ
4. ยืนยันว่า cache logic จะคงอยู่ใน facade `service.py` ไม่แตกออกเป็น `cache.py`

### SchemaService Definition of Done

ถือว่า phase นี้เสร็จเมื่อ

1. public import เดิม `from app.services.schema_service import SchemaService` ยังใช้ได้
2. [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py) เหลือเป็น shim/facade บาง
3. prompt/view/context/dimension/keyword-index logic ถูกแยกออกตาม modules เป้าหมาย
4. admin/chat/query callers สำคัญยังทำงานได้โดยไม่แก้ import ใหญ่
5. characterization tests และ smoke tests ผ่านหลัง refactor

Completion status:

- Done for the planned extraction scope
- Implemented package modules:
  - [app/services/schema/service.py](/Users/seal/Documents/GitHub/AI/app/services/schema/service.py)
  - [app/services/schema/keyword_index.py](/Users/seal/Documents/GitHub/AI/app/services/schema/keyword_index.py)
  - [app/services/schema/prompt_builder.py](/Users/seal/Documents/GitHub/AI/app/services/schema/prompt_builder.py)
  - [app/services/schema/view_manager.py](/Users/seal/Documents/GitHub/AI/app/services/schema/view_manager.py)
  - [app/services/schema/context_store.py](/Users/seal/Documents/GitHub/AI/app/services/schema/context_store.py)
  - [app/services/schema/dimension_families.py](/Users/seal/Documents/GitHub/AI/app/services/schema/dimension_families.py)
- Legacy import path remains available via compatibility shim at [app/services/schema_service.py](/Users/seal/Documents/GitHub/AI/app/services/schema_service.py)
- Verified by regression suite:
  - [tests/unit/test_schema_service_prompt_builder.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_prompt_builder.py)
  - [tests/unit/test_schema_service_keyword_index.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_keyword_index.py)
  - [tests/unit/test_schema_service_remaining_modules.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_schema_service_remaining_modules.py)
  - [tests/unit/test_phase_completion.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_phase_completion.py)

---

## 3. Plan for ai_service.py

## Problem Summary

[app/services/ai_service.py](app/services/ai_service.py) ใน repo ปัจจุบันไม่ได้เป็นแค่ provider wrapper แต่เป็น service monolith ที่รวมอย่างน้อย 6 clusters ชัดเจน

### Method Clusters Observed In Repo

1. provider bootstrap / compatibility layer
- `AIService.__init__()`
- `_init_legacy_provider()`
- re-export ของ provider classes และ retry decorators
- factory functions `create_claude_service()`, `create_gemini_service()`, `create_matcha_service()`

2. hierarchy metadata + cache concern
- `_load_hierarchies_from_db()`
- `get_column_hierarchies()`
- module globals `_HIERARCHY_CACHE`, `_HIERARCHY_CACHE_TS`, `_HIERARCHY_CACHE_TTL`
- fallback `_HARDCODED_HIERARCHIES`

3. MCP tool-loop orchestration
- `query_with_retry()`
- provider-specific message parsing for Claude / Gemini / Matcha
- tool execution + history mutation per provider format

4. hybrid query pipeline
- `query_hybrid()`
- SQL generation, MCP validation, execution, value verification, explanation, confidence scoring
- inline async subtasks for RAG context and value lookup
- retry-history and correction loop

5. prompt / intent / lookup / formatting helpers
- `_get_vanna_context_string()`
- `_extract_keywords_from_question()`
- `_lookup_values_from_question()`
- `_detect_hierarchy_level()`
- `_format_value_matches()` / `_format_value_matches_flat()`
- `_parse_intent_json()`
- `_extract_intent()`
- `_build_pass2_prompt()`
- `_extract_sql()` / `_extract_explanation()`
- `_prepare_data_for_explanation()`

6. training / admin-assist helpers
- `train()`
- `suggest_mappings()`
- `_log_value_corrections()`

### Caller Surface Observed In Repo

Authoritative callers ที่ต้องถือเป็น preserve surface รอบแรก

- [app/api/deps.py](/Users/seal/Documents/GitHub/AI/app/api/deps.py)
  - instantiate `AIService(provider=provider_instance, mcp_client=mcp_client)` ผ่าน DI
- [app/services/query_engine.py](/Users/seal/Documents/GitHub/AI/app/services/query_engine.py)
  - เรียก `query_hybrid()` และ `query_with_retry()` เป็น flow หลักของ production query path
- [app/api/v1/admin/schema.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/schema.py)
  - เรียก `suggest_mappings()`
  - และมี direct access ที่ `ai_service.provider.generate_content(...)` ซึ่งหมายความว่า field `provider` ต้องคงอยู่
- [app/api/v1/chat.py](/Users/seal/Documents/GitHub/AI/app/api/v1/chat.py)
  - เรียก `train()` จาก training endpoint
- [app/api/v1/feedback.py](/Users/seal/Documents/GitHub/AI/app/api/v1/feedback.py)
  - เรียก `train()` ใน auto-train path ของ admin thumbs up
- [app/api/v1/admin/golden_examples.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/golden_examples.py)
  - เรียก `train()` หลัง approve/save golden example
- [app/api/v1/schema_analyzer.py](/Users/seal/Documents/GitHub/AI/app/api/v1/schema_analyzer.py)
  - ใช้ `ai_service.provider.generate_content(...)` ตรง
- [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
  - invalidate `_HIERARCHY_CACHE` ของ ai_service โดยตรงอยู่ในปัจจุบัน

Secondary / suspect callers ที่ไม่ควรใช้เป็น preservation anchor โดยไม่ตรวจเพิ่ม

- [app/services/analyzer_service.py](/Users/seal/Documents/GitHub/AI/app/services/analyzer_service.py)
  - import `AIService` แต่เรียก `self.ai_service.generate_content(...)` ซึ่งไม่ใช่ public method ที่มีอยู่จริงใน class ปัจจุบัน
  - ให้ถือเป็น follow-up cleanup แยก ไม่ควรขยาย scope refactor แรกเพื่อรองรับ path นี้

## Refactor Strategy

เป้าหมายของรอบ execute นี้ไม่ใช่ rewrite orchestration ใหม่ แต่คือทำให้ [app/services/ai_service.py](app/services/ai_service.py) กลายเป็น facade ที่บางลงแบบเดียวกับ schema service โดย preserve caller surface ข้างต้นทั้งหมดก่อน

หลักการ execute ที่เหมาะกับ repo ปัจจุบัน

- แยก pure / low-coupling helpers ออกก่อน
- คง `AIService.provider`, `AIService.mcp_client`, `AIService.vanna`, constructor behavior และ factory API เดิมไว้ก่อน
- แยก `query_with_retry()` และ `query_hybrid()` แบบ delegate-first ไม่ rewrite flow ใหม่ใน phase เดียว
- hierarchy cache ต้องย้ายแบบมี bridge เพราะ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) แตะ `_HIERARCHY_CACHE` ตรงอยู่แล้ว

### Import compatibility rule

เช่นเดียวกับ schema service, path เดิมต้องยังใช้ได้ก่อน

- เก็บ [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) ไว้เป็น shim ชั่วคราว
- shim ต้อง re-export module surface ที่ถูกใช้อยู่จริงให้ครบ ไม่ใช่แค่ class + factories

must-preserve re-exports จากไฟล์เดิมที่แผนนี้ต้องนับรวม:

- `AIService`
- `create_claude_service`, `create_gemini_service`, `create_matcha_service`
- `AIProvider`, `ConfidenceResult`, `QueryResult`, `RetryStatus`
- `ClaudeProvider`, `GeminiProvider`, `MatchaProvider`
- `ai_retry`, `create_retry_decorator`
- `get_column_hierarchies`
- `COLUMN_HIERARCHIES`
- bridge สำหรับ `_HIERARCHY_CACHE` ระหว่างช่วง migrate ตราบใดที่ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) ยัง import symbol นี้อยู่ตรงๆ

ตัวอย่าง shim

```python
from app.services.ai.service import AIService  # noqa: F401
from app.services.ai.factory import create_claude_service, create_gemini_service, create_matcha_service  # noqa: F401
from app.providers.base import AIProvider, ConfidenceResult, QueryResult, RetryStatus  # noqa: F401
from app.providers.claude_provider import ClaudeProvider  # noqa: F401
from app.providers.gemini_provider import GeminiProvider  # noqa: F401
from app.providers.matcha_provider import MatchaProvider  # noqa: F401
from app.providers.retry_config import ai_retry, create_retry_decorator  # noqa: F401
```

### Target structure

```text
app/services/ai/
  __init__.py
  service.py
  factory.py
  hierarchy_context.py
  response_utils.py
  retry_loop.py
  hybrid_flow.py
```

### Responsibility split

- `service.py`
  - เก็บ `AIService` facade/class หลัก
  - constructor compatibility
  - property/state ที่ callers แตะโดยตรง (`provider`, `provider_name`, `mcp_client`, `vanna`)
  - `explain_result()` ยังคงอยู่บน facade เป็น thin wrapper ไป `self.provider.explain_result(...)`
- `factory.py`
  - `create_claude_service`
  - `create_gemini_service`
  - `create_matcha_service`
- `hierarchy_context.py`
  - `_load_hierarchies_from_db`
  - `get_column_hierarchies`
  - hierarchy cache globals/bridge
  - `_get_vanna_context_string`
  - `_THAI_STOP_WORDS`
  - `_extract_keywords_from_question`
  - `_lookup_values_from_question`
  - `_detect_hierarchy_level`
  - `_format_value_matches` / `_format_value_matches_flat`
- `response_utils.py`
  - `_extract_sql`
  - `_extract_explanation`
  - `_prepare_data_for_explanation`
  - `_parse_intent_json`
- `retry_loop.py`
  - helper(s) สำหรับ `query_with_retry()` tool-loop โดยยังคง provider-specific branching behavior เดิม
- `hybrid_flow.py`
  - private helper(s) สำหรับ `query_hybrid()`
  - `_extract_intent`
  - `_build_pass2_prompt`
  - prompt assembly / retry prompt assembly / validation-execution-explanation substeps

### What not to do in first pass

- อย่า rewrite `query_hybrid()` หรือ `query_with_retry()` ใหม่ทั้งก้อน
- อย่าเปลี่ยน public constructor behavior พร้อมกันหลายจุด
- อย่าเปลี่ยน provider contract ระหว่างแตกไฟล์
- อย่าเปลี่ยน direct access pattern `ai_service.provider.generate_content(...)` ใน admin/schema_analyzer รอบแรก
- อย่าแก้ `AnalyzerService` ให้เป็น scope แฝงของ refactor นี้

### Recommended incremental cuts

#### Cut 1

Execution status: implemented and validated on 2026-03-22

- สร้าง package `app/services/ai/`
- copy facade class ไป [app/services/ai/service.py](/Users/seal/Documents/GitHub/AI/app/services/ai/service.py)
- ย้าย factory functions ไป [app/services/ai/factory.py](/Users/seal/Documents/GitHub/AI/app/services/ai/factory.py)
- ย้าย response helpers pure-ish ไป [app/services/ai/response_utils.py](/Users/seal/Documents/GitHub/AI/app/services/ai/response_utils.py)
- ทำ shim ที่ [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) ตั้งแต่ phase นี้
- verify constructor ทั้งแบบ `provider instance` และ `provider name string`
- estimate: 1.0-1.5 working days

#### Cut 2

Execution status: implemented and validated on 2026-03-22

- ย้าย hierarchy/prompt-context/value-lookup helpers ไป [app/services/ai/hierarchy_context.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hierarchy_context.py)
- ย้าย `_THAI_STOP_WORDS` ไปพร้อมกับ `_extract_keywords_from_question()` ใน phase เดียวกัน
- สร้าง bridge สำหรับ `_HIERARCHY_CACHE` และ `get_column_hierarchies()` ให้ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) invalidation ได้ต่อระหว่างช่วง migrate
- ระหว่างที่ยังใช้ bridge ห้ามใช้ cache reassignment แบบสร้าง dict object ใหม่
- ขั้นต่ำต้องเปลี่ยน `_load_hierarchies_from_db()` เป็น in-place mutation:

```python
_HIERARCHY_CACHE.clear()
_HIERARCHY_CACHE.update(result)
```

- ทางเลือกที่ดีกว่าในระยะถัดไปคือย้าย cache ownership ไป [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) โดยตรง แต่ไม่ควรบังคับทำใน cut เดียวถ้ายังเพิ่ม risk มากเกินไป
- หลัง bridge พร้อม ค่อยย้าย invalidation จาก `import _HIERARCHY_CACHE` ไปเป็น helper call/owner ใหม่
- estimate: 1.0-1.5 working days

#### Cut 3

Execution status: implemented and validated on 2026-03-22

- แตก `query_with_retry()` ก่อน เพราะ surface แคบกว่า `query_hybrid()`
- แยก provider-response parsing + tool execution history handling เป็น helper ใน [app/services/ai/retry_loop.py](/Users/seal/Documents/GitHub/AI/app/services/ai/retry_loop.py)
- verify Claude/Gemini/Matcha branching behavior ไม่เปลี่ยน
- current repo status: `query_with_retry()` lives in [app/services/ai/retry_loop.py](/Users/seal/Documents/GitHub/AI/app/services/ai/retry_loop.py), [app/services/ai/service.py](/Users/seal/Documents/GitHub/AI/app/services/ai/service.py) delegates to it, and [app/services/ai/hybrid_flow.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hybrid_flow.py) no longer owns this loop
- characterization coverage added for Claude no-tool path and Matcha tool-execution path in [tests/unit/test_ai_service.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_ai_service.py)
- estimate: 1.0-1.5 working days

#### Cut 4

Execution status: implemented and validated on 2026-03-22

- แตก `query_hybrid()` แบบ internal seam first
- private seam ขั้นต่ำที่ควรมีใน phase นี้:
  - `_resolve_context_info(...)`
  - `_build_initial_user_prompt(...)`
  - `_build_retry_user_prompt(...)`
  - `_generate_sql_attempt(...)`
  - `_validate_sql_attempt(...)`
  - `_verify_values(...)`
  - `_execute_sql_attempt(...)`
  - `_build_explanation(...)`
  - `_build_confidence_result(...)`
- เมื่อ seam ชัดแล้วค่อยย้าย helper เหล่านี้ไป [app/services/ai/hybrid_flow.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hybrid_flow.py)
- current repo progress: helper seams สำหรับ `build_history_context(...)`, `build_initial_user_prompt(...)`, และ `build_retry_user_prompt(...)` ถูกดึงออกใน [app/services/ai/hybrid_flow.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hybrid_flow.py) แล้ว และมี characterization tests รองรับใน [tests/unit/test_ai_service.py](/Users/seal/Documents/GitHub/AI/tests/unit/test_ai_service.py)
- current repo progress เพิ่มเติม: `resolve_context_info(...)`, `validate_sql_attempt(...)`, `execute_sql_attempt(...)`, `load_execution_metadata(...)`, `build_explanation(...)`, `build_confidence_result(...)`, `generate_sql_attempt(...)`, และ `verify_values_if_needed(...)` ถูกดึงออกแล้วใน [app/services/ai/hybrid_flow.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hybrid_flow.py)
- current repo progress เพิ่มเติมอีก: ก้อน pre-SQL preparation สำหรับ first attempt ถูกย้ายเข้า `build_first_attempt_prompt(...)` แล้ว ทำให้ `query_hybrid()` เหลือ orchestration ของแต่ละ attempt เป็นหลัก
- current repo status final for this cut: per-attempt execution orchestration ถูกย้ายเข้า `run_hybrid_attempt(...)` และ unmatched-like logging ถูกแยกเป็น `log_unmatched_like_patterns(...)` ทำให้ `query_hybrid()` เหลือ attempt loop + terminal result handling เป็นหลัก
- estimate: 1.5-2.5 working days

#### Cut 5

Execution status: implemented and validated on 2026-03-22

- เก็บ cleanup/lint debt ใน facade/shim และโมดูลใหม่
- ยืนยันว่า direct callers ที่ใช้ `ai_service.provider` ยังไม่ต้องแก้
- ระบุ follow-up แยกสำหรับ [app/services/analyzer_service.py](/Users/seal/Documents/GitHub/AI/app/services/analyzer_service.py) ถ้ายังต้องใช้งานจริง
- current repo status: [app/services/ai/service.py](/Users/seal/Documents/GitHub/AI/app/services/ai/service.py), [app/services/ai/hybrid_flow.py](/Users/seal/Documents/GitHub/AI/app/services/ai/hybrid_flow.py), และ [app/services/ai/retry_loop.py](/Users/seal/Documents/GitHub/AI/app/services/ai/retry_loop.py) ผ่าน diagnostics ล่าสุดโดยไม่มี errors
- validation status: targeted regression `./venv/bin/pytest tests/unit/test_ai_service.py tests/unit/test_phase_completion.py` ผ่าน 65 tests และ broader unit suite `./venv/bin/pytest tests/unit` ผ่าน 336 tests with 3 skipped
- estimate: 0.5-1.0 working days

ตัวอย่าง helper seam ที่ควรมี

- `_build_initial_user_prompt(...)`
- `_build_retry_user_prompt(...)`
- `_generate_sql_attempt(...)`
- `_validate_sql_attempt(...)`
- `_execute_sql_attempt(...)`
- `_build_explanation(...)`

## Validation

- characterization tests ที่ควรมีเพิ่มก่อน execute จริง
  - `_extract_sql()` / `_extract_explanation()` / `_parse_intent_json()`
  - `_prepare_data_for_explanation()` สำหรับ large dataset aggregation behavior
  - `get_column_hierarchies()` DB-first with fallback behavior
  - cache invalidation behavior ของ hierarchy cache โดยเฉพาะกรณี reload หลัง in-place mutation
  - `_detect_hierarchy_level()` และ `_format_value_matches()` สำหรับ hierarchy-safe prompt injection
  - `suggest_mappings()` success + fallback parse path
  - `train()` fail-open behavior เมื่อ Vanna unavailable
- mocked integration tests ที่ควรล็อก caller surface สำคัญ
  - [app/services/query_engine.py](/Users/seal/Documents/GitHub/AI/app/services/query_engine.py) with mocked provider + mocked MCP for `query_hybrid()`
  - [app/services/query_engine.py](/Users/seal/Documents/GitHub/AI/app/services/query_engine.py) with mocked provider + mocked MCP for `query_with_retry()`
  - [app/api/deps.py](/Users/seal/Documents/GitHub/AI/app/api/deps.py) returns usable `AIService`
  - hierarchy cache invalidation from [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py)
  - direct field access `ai_service.provider` ยังใช้ได้สำหรับ [app/api/v1/admin/schema.py](/Users/seal/Documents/GitHub/AI/app/api/v1/admin/schema.py) และ [app/api/v1/schema_analyzer.py](/Users/seal/Documents/GitHub/AI/app/api/v1/schema_analyzer.py)

### AIService Definition of Ready

ถือว่าเริ่ม execute ได้เมื่อ

1. ตกลงว่าจะใช้ compatibility shim ที่ [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) ตั้งแต่ phase แรก
2. มี must-preserve caller list ชัดเจนสำหรับ deps/query_engine/admin/chat/feedback/schema_analyzer/hierarchy_service
3. มี characterization tests ขั้นต่ำสำหรับ parser/hierarchy/value-format helpers
4. ตกลงว่า [app/services/analyzer_service.py](/Users/seal/Documents/GitHub/AI/app/services/analyzer_service.py) ไม่ใช่ preservation anchor ของรอบแรก
5. ตกลงชัดเจนว่า Cut 2 จะใช้ in-place mutation หรือ owner-transfer สำหรับ hierarchy cache ก่อนย้ายไฟล์จริง

### AIService Definition of Done

ถือว่า phase นี้เสร็จเมื่อ

1. public import เดิม `from app.services.ai_service import AIService` และ factory functions ยังใช้ได้
2. [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) เหลือเป็น shim/facade บาง
3. shim ยัง re-export provider symbols, retry decorators, `get_column_hierarchies`, `COLUMN_HIERARCHIES`, และ bridge ที่จำเป็นระหว่าง migrate ได้ครบ
4. factories, hierarchy-context helpers, response helpers, retry loop, และ hybrid helper seams ถูกแยกตาม modules เป้าหมาย
5. [app/services/query_engine.py](/Users/seal/Documents/GitHub/AI/app/services/query_engine.py) ยังเรียก `query_hybrid()` / `query_with_retry()` ได้โดยไม่ต้องแก้ import ใหญ่
6. direct access `ai_service.provider` และ facade method `explain_result()` ยังทำงานสำหรับ callers เดิม
7. hierarchy cache invalidation concern ถูกย้าย/bridge อย่างปลอดภัยจาก [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) โดยไม่เกิด stale reference จาก dict reassignment
8. regression tests สำคัญผ่านหลัง refactor

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
- duration: 5.0-8.0 working days

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
| [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) | High | High | 5.0-8.0 working days |

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
5. [app/services/ai_service.py](/Users/seal/Documents/GitHub/AI/app/services/ai_service.py) เหลือ facade/shim ที่คง import path เดิม, factories ถูกแยก, และ hierarchy cache concern ถูก bridge อย่างปลอดภัยกับ [app/services/hierarchy_service.py](/Users/seal/Documents/GitHub/AI/app/services/hierarchy_service.py) โดยไม่เกิด stale reference
6. tests สำคัญยังผ่าน และ public API behavior ไม่เปลี่ยน
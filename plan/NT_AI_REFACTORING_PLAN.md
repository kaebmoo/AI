# NT AI Assistant — Refactoring Plan
## Applying OpenMiniCrew Architectural Patterns

**Version:** 1.0
**Date:** 2026-03-04
**Author:** Pornthep (AVP Finance, NT) + Claude
**Status:** Phase 1, 2, 3, 5 completed (2026-03-04) — Phase 4 pending

---

## 1. ที่มาและเหตุผล

### 1.1 สถานะปัจจุบันของ NT AI Assistant

NT AI Assistant เป็นระบบถาม-ตอบข้อมูลการเงินผ่าน Web Application ใช้ AI (Claude/Gemini/Matcha) แปลงคำถามภาษาไทยเป็น SQL แล้ว execute กับฐานข้อมูล โครงสร้างหลัก:

- **Backend:** FastAPI (Python) ที่ `app/`
- **Frontend:** React Native (Expo) ที่ `frontend/`
- **Admin UI:** React + Ant Design ที่ `frontend-admin/`
- **MCP Servers:** metadata, query, validation ที่ `mcp_servers/`
- **Database:** SQLite (dev) / PostgreSQL / MSSQL (production)

ระบบทำงานได้แต่มีปัญหาเชิงโครงสร้างที่กระทบการดูแลรักษาและขยายระบบ

### 1.2 ปัญหาที่พบ

**P1: ai_service.py เป็น God File (~1,200 บรรทัด)**
ไฟล์เดียวรวม 3 provider classes (ClaudeProvider, GeminiProvider, MatchaProvider), AIService orchestrator, retry logic, RAG integration, SQL extraction, explanation parsing, chart config post-processing, two-pass generation, value lookup ทุกอย่างอยู่ในไฟล์เดียว ถ้าจะแก้ Gemini ต้องเปิดไฟล์ที่มี Claude และ Matcha code ด้วย

**P2: chat.py endpoint ทำทุกอย่างใน function เดียว (~350 บรรทัด)**
POST `/api/v1/chat/` endpoint หนึ่งเดียวรับผิดชอบ: detect context, resolve provider, create AI service, build history, execute query, detect warnings, calculate confidence, save history, format response -- ทุกอย่างอยู่ใน function เดียว

**P3: Provider selection เป็น if/elif chain**
ทั้งใน `chat.py` (เลือก service factory) และ `AIService.__init__()` (เลือก provider class) ใช้ if/elif chain ที่ต้องแก้ทุกครั้งที่เพิ่ม provider ใหม่

**P4: Duplicate chart post-processing logic**
Code สำหรับ parse JSON response และ enforce Time-Series Rule ถูก copy-paste ใน `ClaudeProvider.explain_result()`, `GeminiProvider.explain_result()`, และ `MatchaProvider.explain_result()` ทั้งสามที่

**P5: ไม่มี internal tool system**
ถ้าอยากเพิ่ม feature ที่ไม่ใช่ database query (เช่น export report, send email alert, trending analysis) ต้องสร้าง MCP server ใหม่ซึ่งเป็น external process ที่หนักเกินไป

**P6: ไม่มี cost control**
ทุก query ใช้ model เดียวกันหมด ไม่ว่าจะเป็นคำถามง่ายหรือซับซ้อน

**P7: ไม่มี Telegram interface**
มี `app/telegram/` directory ว่างเปล่า แต่ยังไม่ได้ implement ในขณะที่ OpenMiniCrew มี Telegram interface ที่ production-ready แล้ว

### 1.3 OpenMiniCrew คืออะไร

OpenMiniCrew เป็น personal AI assistant framework (github.com/kaebmoo/openminicrew) ที่สั่งงานผ่าน Telegram รองรับ Claude + Gemini มีหลักการออกแบบที่ดี:

- **Provider Registry:** auto-discover LLM providers จาก directory, auto-fallback
- **Tool Registry:** auto-discover tools, เพิ่ม tool = สร้างไฟล์เดียว
- **Dispatcher:** แยก routing logic ออกจาก business logic อย่างชัดเจน
- **Tier-based cost control:** tool แต่ละตัวกำหนด preferred_tier (cheap/mid) ได้
- **Separation of concerns:** dispatcher ไม่รู้เรื่อง tool internals, tool ไม่รู้เรื่อง LLM routing

### 1.4 เป้าหมาย

1. Refactor NT AI ให้โครงสร้าง clean ขึ้น โดยนำ patterns จาก OpenMiniCrew มาใช้
2. ลด coupling ระหว่าง components ให้แต่ละส่วนแก้ไขแยกกันได้
3. เตรียมโครงสร้างให้ OpenMiniCrew เรียกใช้ NT AI engine ผ่าน API (Telegram gateway)
4. ทำเป็น phase ทำ phase ไหนก็ได้ ระบบเดิมยังทำงานได้ตลอด

---

## 2. สถาปัตยกรรมเป้าหมาย

```
┌──────────────────────────────────────────────────────────────┐
│                      INTERFACE LAYER                          │
│                                                                │
│  Web App (React)    Telegram (OpenMiniCrew)    External API    │
│  ┌───────────┐     ┌──────────────────┐       ┌──────────┐   │
│  │ frontend  │     │ tools/nt_query.py│       │ REST API │   │
│  │ frontend- │     │ เรียก NT AI API  │       │ /api/v1/ │   │
│  │ admin     │     └────────┬─────────┘       └────┬─────┘   │
│  └─────┬─────┘              │                      │          │
└────────┼────────────────────┼──────────────────────┼──────────┘
         │                    │                      │
         ▼                    ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│                     FASTAPI ENDPOINTS                         │
│                                                                │
│  chat.py (slim)    admin.py    feedback.py    auth.py         │
│  ~50 lines         (ไม่เปลี่ยน) (ไม่เปลี่ยน)  (ไม่เปลี่ยน)    │
│  เรียก QueryEngine                                            │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                     QUERY ENGINE (ใหม่)                       │
│                     app/services/query_engine.py               │
│                                                                │
│  Orchestrator หลัก — รับคำถาม ส่งคืน QueryResult              │
│  ใครจะเรียกก็ได้ (Web, Telegram, API, test)                   │
│                                                                │
│  Flow: resolve_provider → detect_context → build_prompt       │
│        → execute (hybrid/MCP) → detect_warnings               │
│        → calculate_confidence → return QueryResult             │
└────────┬─────────────┬──────────────┬────────────────────────┘
         │             │              │
         ▼             ▼              ▼
┌─────────────┐ ┌────────────┐ ┌────────────────┐
│  Provider   │ │  Services  │ │ Internal Tools │
│  Registry   │ │  (existing)│ │ (ใหม่)         │
│  (ใหม่)     │ │            │ │                │
│ ┌─────────┐ │ │ context_   │ │ app/tools/     │
│ │ Claude  │ │ │ router.py  │ │ base.py        │
│ │ Gemini  │ │ │ schema_    │ │ registry.py    │
│ │ Matcha  │ │ │ service.py │ │ report_export  │
│ │(auto-   │ │ │ admin_     │ │ trending       │
│ │discover)│ │ │ config.py  │ │ (auto-discover)│
│ └─────────┘ │ │ warning_   │ │                │
│ auto-       │ │ detector.py│ │                │
│ fallback    │ │ (ใหม่)     │ │                │
└─────────────┘ └────────────┘ └────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                       DATA LAYER                              │
│                                                                │
│  MCP Servers (nt_metadata, nt_query, nt_validation)           │
│  Database Adapter (SQLite / PostgreSQL / MSSQL)               │
│  Vanna RAG (ChromaDB)                                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. รายละเอียดการ Refactor — 5 Phases

### Phase 1: แยก Provider ออกจาก ai_service.py

**เป้าหมาย:** แยก 3 provider classes + shared utilities ออกเป็นไฟล์แยก + เพิ่ม auto-discover registry

**ไฟล์ที่จะสร้างใหม่:**

```
app/providers/             # directory ใหม่
  __init__.py
  base.py                  # AIProvider abstract class + dataclasses
  claude_provider.py       # ClaudeProvider class
  gemini_provider.py       # GeminiProvider class
  matcha_provider.py       # MatchaProvider class
  registry.py              # ProviderRegistry (auto-discover + fallback)
  chart_postprocessor.py   # shared chart config post-processing logic
  retry_config.py          # shared retry decorator
```

**ไฟล์ที่จะแก้ไข:**

```
app/services/ai_service.py  # ลบ provider classes ออก, import จาก app/providers/ แทน
app/api/v1/chat.py           # ลบ if/elif provider selection, ใช้ registry แทน
```

**รายละเอียดแต่ละไฟล์:**

#### app/providers/base.py

ย้ายจาก ai_service.py:
- `class AIProvider(ABC)` — abstract class (มีอยู่แล้วใน ai_service.py บรรทัด ~100)
- `@dataclass ConfidenceResult` (บรรทัด ~78)
- `@dataclass QueryResult` (บรรทัด ~87)
- `@dataclass RetryStatus` (บรรทัด ~99)

เพิ่มใหม่:
- `is_configured() -> bool` — abstract method ตรวจว่ามี API key หรือยัง (pattern จาก OpenMiniCrew `core/providers/base.py`)
- `get_model(tier: str) -> str` — abstract method return model name ตาม tier

```python
# Signature ของ base class ใหม่
class AIProvider(ABC):
    name: str = ""

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def get_model(self, tier: str = "default") -> str: ...

    @abstractmethod
    async def generate_sql(self, question, system_prompt, tools, history=[]) -> Dict: ...

    @abstractmethod
    async def explain_result(self, question, sql, data, system_prompt) -> Union[str, Dict]: ...

    @abstractmethod
    async def generate_content(self, prompt, system_prompt=None) -> str: ...
```

#### app/providers/chart_postprocessor.py

ย้าย duplicate logic จาก `ClaudeProvider.explain_result()`, `GeminiProvider.explain_result()`, `MatchaProvider.explain_result()`:
- JSON parsing (try pure JSON → markdown code block → regex extract)
- Time-Series Rule enforcement (swap category/series if needed)
- Auto-detection fallback logic (จาก MatchaProvider)

```python
# Signature
def parse_explanation_response(text: str) -> Dict:
    """Parse JSON from AI response, handle markdown code blocks"""
    ...

def enforce_time_series_rule(parsed_result: Dict) -> Dict:
    """Swap category/series if time column is misplaced"""
    ...

def auto_detect_chart_config(data: List[Dict]) -> Dict:
    """Fallback: infer chart config from data shape"""
    ...
```

#### app/providers/retry_config.py

ย้าย `create_retry_decorator()` function จาก ai_service.py (บรรทัด ~40-74)

#### app/providers/claude_provider.py

ย้าย `class ClaudeProvider(AIProvider)` จาก ai_service.py (บรรทัด ~107-250)
เปลี่ยน:
- `explain_result()` ใช้ `chart_postprocessor` แทน inline logic
- เพิ่ม `name = "claude"`
- เพิ่ม `is_configured()` — ตรวจ API key
- เพิ่ม `get_model(tier)` — return model ตาม tier

#### app/providers/gemini_provider.py

ย้าย `class GeminiProvider(AIProvider)` จาก ai_service.py (บรรทัด ~251-500)
เปลี่ยนเหมือน Claude

#### app/providers/matcha_provider.py

ย้าย `class MatchaProvider(AIProvider)` จาก ai_service.py (บรรทัด ~501-750)
เปลี่ยนเหมือน Claude

#### app/providers/registry.py

สร้างใหม่ ตาม pattern จาก OpenMiniCrew `core/providers/registry.py`:

```python
class ProviderRegistry:
    """Auto-discover providers จาก app/providers/ directory"""

    def __init__(self):
        self.providers: dict[str, AIProvider] = {}

    def discover(self):
        """Scan app/providers/ directory หา class ที่ inherit AIProvider"""
        # ใช้ importlib + inspect เหมือน OpenMiniCrew
        ...

    def get(self, name: str) -> AIProvider | None: ...

    def get_available(self) -> list[str]:
        """Return list of configured provider names"""
        ...

    def get_fallback(self, preferred: str) -> AIProvider | None:
        """ถ้า preferred ไม่พร้อม → return ตัวแรกที่พร้อม"""
        ...

    def create_service(self, provider_name: str, mcp_client, **kwargs) -> "AIService":
        """Factory method แทน if/elif chain ใน chat.py"""
        ...

# Singleton
provider_registry = ProviderRegistry()
```

#### แก้ไข app/services/ai_service.py

ลบออก:
- `class AIProvider(ABC)` (ย้ายไป base.py)
- `class ClaudeProvider` (ย้ายไป claude_provider.py)
- `class GeminiProvider` (ย้ายไป gemini_provider.py)
- `class MatchaProvider` (ย้ายไป matcha_provider.py)
- `create_retry_decorator()` (ย้ายไป retry_config.py)
- `@dataclass ConfidenceResult, QueryResult, RetryStatus` (ย้ายไป base.py)
- `create_claude_service()`, `create_gemini_service()`, `create_matcha_service()` factory functions

เหลือ:
- `class AIService` — orchestrator ที่รับ provider instance แทนที่จะสร้างเอง
- `query_with_retry()`, `query_hybrid()` methods
- Helper methods: `_extract_sql()`, `_extract_explanation()`, `_get_vanna_context_string()`, `_lookup_values_from_question()`, `_extract_intent()`, etc.

เปลี่ยน `__init__`:
```python
# เดิม (if/elif chain)
class AIService:
    def __init__(self, provider: str, api_key, mcp_client, model=None, **kwargs):
        if provider == "claude":
            self.provider = ClaudeProvider(...)
        elif provider == "gemini":
            ...

# ใหม่ (รับ provider instance ตรงๆ)
class AIService:
    def __init__(self, provider: AIProvider, mcp_client: MCPClientService):
        self.provider = provider
        self.provider_name = provider.name
        self.mcp_client = mcp_client
        self.vanna = VannaService(...)
```

#### แก้ไข app/api/v1/chat.py

ลบ if/elif chain ที่เลือก provider (บรรทัด ~180-215) แทนด้วย:

```python
# เดิม (~35 บรรทัด)
if selected_provider == "claude":
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(...)
    ai_service = create_claude_service(...)
elif selected_provider == "gemini":
    ...
elif selected_provider == "matcha":
    ...
else:
    raise HTTPException(...)

# ใหม่ (~5 บรรทัด)
from app.providers.registry import provider_registry
provider = provider_registry.get_fallback(selected_provider)
if not provider:
    raise HTTPException(status_code=400, detail=f"Provider '{selected_provider}' not available")
ai_service = AIService(provider=provider, mcp_client=mcp_client)
```

**Backward compatibility:**
- API endpoints ไม่เปลี่ยน
- Frontend ไม่ต้องแก้
- Admin config ยังทำงานเหมือนเดิม
- MCP servers ไม่เปลี่ยน

**วิธีทดสอบ:**
```bash
# 1. Unit test registry discover
python -c "from app.providers.registry import provider_registry; provider_registry.discover(); print(provider_registry.get_available())"

# 2. Integration test — run existing test suite
pytest tests/ -v

# 3. Manual test — ถามคำถามผ่าน Web UI
# ตรวจว่าผลลัพธ์เหมือนเดิม ทั้ง SQL, explanation, chart config
```

---

### Phase 2: สร้าง QueryEngine — แยก logic ออกจาก chat endpoint

**เป้าหมาย:** สร้าง orchestrator class ที่เรียกจากไหนก็ได้ (Web, Telegram, test, script)

**ไฟล์ที่จะสร้างใหม่:**

```
app/services/query_engine.py     # orchestrator หลัก
app/services/warning_detector.py # แยก warning logic ออกมา
```

**ไฟล์ที่จะแก้ไข:**

```
app/api/v1/chat.py  # ลด function เหลือ ~50 บรรทัด
```

#### app/services/query_engine.py

รวบรวม logic จาก `chat.py` POST endpoint เป็น class:

```python
class QueryEngine:
    """
    Core orchestrator — เรียกจาก Web, Telegram, หรือ API ก็ได้

    Usage:
        engine = QueryEngine(mcp_client=mcp, db_session=db)
        result = await engine.query("รายได้เดือนนี้เท่าไหร่")
    """

    def __init__(
        self,
        mcp_client: MCPClientService,
        db_session: Session,
        admin_config: AdminConfigService | None = None,
    ):
        self.mcp_client = mcp_client
        self.db = db_session
        self.admin_config = admin_config or AdminConfigService(db_session)
        self._schema_service = None

    @property
    def schema_service(self) -> SchemaService:
        if not self._schema_service:
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            self._schema_service = SchemaService(db_path=db_path)
        return self._schema_service

    async def query(
        self,
        question: str,
        provider: str | None = None,
        context: str | None = None,
        mode: str = "hybrid",
        history: list[dict] | None = None,
        max_retries: int = 3,
        conversation_id: str | None = None,
    ) -> "QueryEngineResult":
        """
        Main entry point

        Returns QueryEngineResult ที่รวม QueryResult + warnings + confidence
        """
        # 1. Resolve provider
        ai_config = self.admin_config.get_ai_config()
        selected = provider or ai_config.get("default_provider", settings.AI_PROVIDER)
        provider_instance = provider_registry.get_fallback(selected)
        if not provider_instance:
            raise ValueError(f"No available provider for '{selected}'")
        ai_service = AIService(provider=provider_instance, mcp_client=self.mcp_client)

        # 2. Detect context
        context_name = self._resolve_context(question, context, history)

        # 3. Build system prompt
        system_prompt = self.schema_service.build_system_prompt(
            ai_provider=selected, include_samples=True,
            language="thai", context_name=context_name, rag_enabled=True,
        )

        # 4. Execute query
        feature_flags = self.admin_config.get_feature_flags()
        if mode == "hybrid":
            result = await ai_service.query_hybrid(
                question=question, system_prompt=system_prompt,
                max_retries=max_retries, history=history,
                context_name=context_name,
                two_pass_enabled=feature_flags.get("two_pass_enabled", False),
                value_lookup_enabled=feature_flags.get("value_lookup_enabled", False),
            )
        else:
            result = await ai_service.query_with_retry(
                question=question, max_retries=max_retries,
                history=history, explain=True, context_name=context_name,
            )

        # 5. Detect warnings
        warnings = await WarningDetector(self.mcp_client, self.schema_service).detect(
            result.data, result.sql_query, context_name
        )

        # 6. Return combined result
        return QueryEngineResult(
            query_result=result,
            context_name=context_name,
            warnings=warnings,
        )

    def _resolve_context(self, question, explicit_context, history):
        """Logic ที่ปัจจุบันอยู่ใน chat.py (บรรทัด ~220-260)"""
        ...
```

#### app/services/warning_detector.py

ย้ายจาก `chat.py`:
- `DATA_WARNINGS` list (บรรทัด ~130)
- `detect_data_warnings()` function (บรรทัด ~140)
- `detect_multiple_sources_warning()` function (บรรทัด ~165)

```python
class WarningDetector:
    def __init__(self, mcp_client, schema_service):
        self.mcp_client = mcp_client
        self.schema_service = schema_service

    async def detect(self, data, sql_query, context_name) -> list[DataWarning]:
        warnings = []
        warnings.extend(self._detect_content_warnings(data, sql_query))
        if sql_query and 'LIKE' in sql_query.upper():
            warnings.extend(await self._detect_multiple_sources(sql_query, context_name))
        return warnings
```

#### แก้ไข app/api/v1/chat.py

POST endpoint เหลือแค่:

```python
@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, current_request: Request,
               current_user: User = Depends(deps.get_current_user),
               db: Session = Depends(deps.get_db)):
    start_time = time.time()
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Get history
    history = _get_conversation_history(db, conversation_id, current_user.id)

    # Execute query
    mcp_client = deps.get_mcp_client(current_request)
    engine = QueryEngine(mcp_client=mcp_client, db_session=db)
    result = await engine.query(
        question=request.question,
        provider=request.provider,
        context=request.context,
        mode=request.mode or "hybrid",
        history=history,
        max_retries=request.max_retries,
    )

    # Save history
    chat_entry = _save_history(db, current_user.id, conversation_id, result)

    # Format response
    return _format_response(chat_entry, conversation_id, result, start_time)
```

**Backward compatibility:**
- API response format ไม่เปลี่ยน
- Frontend ไม่ต้องแก้
- QueryEngine เรียกจาก test ได้โดยไม่ต้อง HTTP

**วิธีทดสอบ:**
```python
# Unit test QueryEngine โดยตรง (ไม่ผ่าน HTTP)
async def test_query_engine():
    engine = QueryEngine(mcp_client=mock_mcp, db_session=mock_db)
    result = await engine.query("รายได้เดือนมกราคม 2568")
    assert result.query_result.data is not None
    assert result.context_name == "revenue"
```

---

### Phase 3: เพิ่ม Internal Tool System

**เป้าหมาย:** สร้าง tool system แบบ auto-discover ตาม pattern OpenMiniCrew สำหรับ features ที่ไม่ใช่ database query

**ไฟล์ที่จะสร้างใหม่:**

```
app/tools/
  __init__.py
  base.py              # BaseTool abstract class
  registry.py          # auto-discover tools
  report_export.py     # ตัวอย่าง: export query result เป็น Excel
```

#### app/tools/base.py

ตาม pattern จาก OpenMiniCrew `tools/base.py`:

```python
from abc import ABC, abstractmethod

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    description_th: str = ""  # สำหรับแสดงใน UI
    preferred_tier: str = "cheap"  # cheap = Haiku/Flash, mid = Sonnet/Pro

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """ทำงานหลัก — return dict ที่มี result"""
        ...

    def get_tool_spec(self) -> dict:
        """Return generic tool spec สำหรับ LLM function calling"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
```

#### app/tools/registry.py

```python
class ToolRegistry:
    """Auto-discover tools จาก app/tools/ directory"""

    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def discover(self):
        """Scan app/tools/ directory หา class ที่ inherit BaseTool"""
        # importlib + inspect pattern เหมือน OpenMiniCrew
        ...

    def get(self, name: str) -> BaseTool | None: ...
    def get_all_specs(self) -> list[dict]: ...

tool_registry = ToolRegistry()
```

#### app/tools/report_export.py (ตัวอย่าง)

```python
class ReportExportTool(BaseTool):
    name = "report_export"
    description = "Export query result to Excel/PDF"
    description_th = "ส่งออกผลลัพธ์เป็น Excel หรือ PDF"

    async def execute(self, data: list[dict], format: str = "xlsx", **kwargs) -> dict:
        # สร้าง Excel file จาก data
        ...
        return {"file_path": path, "format": format}
```

**Phase 3 เป็น additive** — ไม่ต้องแก้ code เดิม เพิ่มไฟล์ใหม่อย่างเดียว

---

### Phase 4: เชื่อม OpenMiniCrew กับ NT AI

**เป้าหมาย:** ให้ user ถามข้อมูลการเงินผ่าน Telegram ได้

**แนวทาง:** สร้าง tool ใหม่ใน OpenMiniCrew ที่เรียก NT AI API ผ่าน HTTP

**ไฟล์ที่จะสร้างใหม่ (ใน OpenMiniCrew project):**

```
openminicrew/tools/nt_query.py
```

#### tools/nt_query.py

```python
import httpx
from tools.base import BaseTool

class NTQueryTool(BaseTool):
    name = "nt_query"
    description = (
        "สอบถามข้อมูลรายได้ ค่าใช้จ่าย P&L หรือข้อมูลทางการเงินของ NT "
        "เช่น 'รายได้เดือนนี้เท่าไหร่' 'ค่าใช้จ่ายแยกตามฝ่าย' 'เปรียบเทียบรายได้ปีนี้กับปีก่อน'"
    )
    commands = ["/ntquery", "/revenue", "/expense", "/finance"]
    direct_output = True
    preferred_tier = "cheap"  # dispatcher ใช้ cheap, NT AI จัดการ LLM เอง

    async def execute(self, user_id: str, args: str = "", **kwargs) -> str:
        from core.config import _require
        base_url = _require("NT_AI_BASE_URL")  # e.g. http://localhost:8000
        api_token = _require("NT_AI_API_TOKEN")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/api/v1/chat/",
                json={"question": args, "mode": "hybrid"},
                headers={"Authorization": f"Bearer {api_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return self._format_for_telegram(data)

    def _format_for_telegram(self, data: dict) -> str:
        """Format NT AI response สำหรับ Telegram (markdown)"""
        parts = []

        # คำตอบ
        answer = data.get("answer", "")
        if answer:
            parts.append(answer)

        # SQL (ถ้ามี — แสดงแบบ collapsed)
        sql = data.get("sql_query", "")
        if sql:
            parts.append(f"\n```sql\n{sql}\n```")

        # Data summary
        result_data = data.get("data")
        if result_data and len(result_data) > 0:
            parts.append(f"\n(พบข้อมูล {len(result_data)} รายการ)")

        # Warnings
        warnings = data.get("warnings")
        if warnings:
            for w in warnings:
                parts.append(f"\n{w.get('message', '')}")

        return "\n".join(parts) if parts else "ไม่พบข้อมูล"

    def get_tool_spec(self) -> dict:
        return {
            "name": "nt_query",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": "คำถามเกี่ยวกับข้อมูลการเงินของ NT เช่น 'รายได้เดือนมกราคม 2568'"
                    }
                },
                "required": ["args"],
            },
        }
```

**ต้องเพิ่มใน .env ของ OpenMiniCrew:**
```bash
NT_AI_BASE_URL=http://localhost:8000
NT_AI_API_TOKEN=<session token จาก NT AI auth system>
```

**Authentication:**
NT AI ใช้ Email OTP + session token ดังนั้นต้อง:
1. สร้าง service account user ใน NT AI สำหรับ bot
2. หรือเพิ่ม API key authentication endpoint ใน NT AI (recommended)

**ทางเลือกอนาคต (4B):**
ถ้า latency เป็นปัญหา สามารถ import QueryEngine ตรงแทน HTTP:
```python
# แทนที่ HTTP call ด้วย direct import
from nt_ai.services.query_engine import QueryEngine
```
แต่ต้อง share codebase ซึ่งซับซ้อนขึ้น เริ่มจาก 4A ก่อน

---

### Phase 5: Tier-based Cost Control

**เป้าหมาย:** ใช้ model ถูก/แพง ตามความซับซ้อนของ query

**ไฟล์ที่จะสร้างใหม่:**

```
app/services/query_classifier.py
```

#### app/services/query_classifier.py

```python
class QueryComplexityClassifier:
    """จำแนกความซับซ้อนของ query เพื่อเลือก model tier"""

    # Rule-based classification (ไม่เสีย LLM token)
    COMPLEX_PATTERNS = [
        r"เปรียบเทียบ", r"เทียบ", r"แนวโน้ม", r"trend",
        r"ยอดสูงสุด.*ต่ำสุด", r"สัดส่วน", r"ร้อยละ",
        r"year.over.year", r"month.over.month",
    ]
    SIMPLE_PATTERNS = [
        r"^รายได้\s*เดือน", r"^ค่าใช้จ่าย\s*เดือน",
        r"^ยอดรวม", r"^ทั้งหมด",
    ]

    def classify(self, question: str) -> str:
        """
        Returns: "cheap" | "mid"
        """
        q = question.lower()

        # Complex patterns -> mid tier
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, q):
                return "mid"

        # Simple patterns -> cheap tier
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, q):
                return "cheap"

        # Default
        return "cheap"
```

**Integration กับ QueryEngine:**

```python
# ใน query_engine.py
classifier = QueryComplexityClassifier()
tier = classifier.classify(question)
model = provider_instance.get_model(tier)
```

**Integration กับ admin config:**
Admin สามารถ override ใน Settings UI:
- `force_tier`: บังคับใช้ tier เดียว (ถ้าต้องการ control cost)
- `tier_classification_enabled`: เปิด/ปิดระบบ auto classification

---

## 4. ลำดับการทำงานและ Dependencies

```
Phase 1 ──→ Phase 2 ──→ Phase 3 (independent)
   │            │
   │            └──→ Phase 4 (ต้องทำหลัง Phase 2)
   │
   └──→ Phase 5 (ทำเมื่อไหร่ก็ได้หลัง Phase 1)
```

| Phase | Prerequisites | ไฟล์ที่สร้างใหม่ | ไฟล์ที่แก้ไข | ประมาณเวลา |
|-------|---------------|-----------------|-------------|-----------|
| 1 | ไม่มี | 8 ไฟล์ใน app/providers/ | ai_service.py, chat.py | 1-2 วัน |
| 2 | Phase 1 | 2 ไฟล์ (query_engine, warning_detector) | chat.py | 2-3 วัน |
| 3 | ไม่มี (additive) | 3+ ไฟล์ใน app/tools/ | ไม่แก้ code เดิม | 1-2 วัน |
| 4 | Phase 2 | 1 ไฟล์ใน openminicrew/tools/ | .env | 1 วัน |
| 5 | Phase 1 | 1 ไฟล์ (query_classifier) | query_engine.py | 1 วัน |

---

## 5. กฎสำคัญสำหรับ AI Agent ที่ทำงานต่อ

### 5.1 กฎเกี่ยวกับ Codebase

1. **อย่าแก้ MCP servers** — `mcp_servers/` ไม่อยู่ในขอบเขตของ refactoring นี้
2. **อย่าแก้ Frontend** — `frontend/` และ `frontend-admin/` ไม่ต้องเปลี่ยน API contract เดิมต้องยังใช้ได้
3. **อย่าแก้ Database schema** — ไม่ต้อง migration ใหม่
4. **อย่าลบ function ก่อนย้าย** — ย้ายไปไฟล์ใหม่ก่อน แล้วเปลี่ยน import ให้ชี้ไปที่ใหม่ แล้วค่อยลบจากเดิม
5. **ทดสอบทุกครั้งหลังแก้** — `pytest tests/ -v` + manual test ผ่าน Web UI

### 5.2 กฎเกี่ยวกับ OpenMiniCrew Codebase

1. **ใช้ `_require()` ไม่ใช่ `_required()`** ใน `core/config.py`
2. **ใช้ `db.get_conn()` ไม่ใช่ `db.get_connection()`**
3. **Tool ใหม่ต้องมี `direct_output = True`** เพราะ dispatcher step 2 (summary fallback) ไม่ถูกใช้ในทางปฏิบัติ
4. **Project root:** `/Users/seal/Documents/GitHub/openminicrew/`
5. **Tool registry auto-discovers** — สร้างไฟล์ใน `tools/` แค่นั้น ไม่ต้อง register ที่ไหน

### 5.3 กฎเกี่ยวกับ NT AI Data

1. **REVENUE_VALUE หน่วยเป็นบาท** ไม่ใช่ล้านบาท
2. **DATE column เก็บเป็น Unix Timestamp (Milliseconds)** ต้องใช้ YEAR, MONTH แทน
3. **Thai column names ต้อง double quotes** เช่น `"กลุ่มธุรกิจ"`
4. **ชื่อหน่วยงานมี inconsistent casing** — normalization rules อยู่ใน schema_business_rules
5. **P&L data มี subtotal rows** ที่ทำให้เกิด double-counting ถ้าไม่ filter

### 5.4 File Paths Reference

```
NT AI Assistant:
  Root:        /Users/seal/Documents/GitHub/AI/
  Backend:     /Users/seal/Documents/GitHub/AI/app/
  AI Service:  /Users/seal/Documents/GitHub/AI/app/services/ai_service.py
  Chat API:    /Users/seal/Documents/GitHub/AI/app/api/v1/chat.py
  MCP Client:  /Users/seal/Documents/GitHub/AI/app/services/mcp_client.py
  Config:      /Users/seal/Documents/GitHub/AI/app/config.py
  MCP Servers: /Users/seal/Documents/GitHub/AI/mcp_servers/

OpenMiniCrew:
  Root:        /Users/seal/Documents/GitHub/openminicrew/
  Dispatcher:  /Users/seal/Documents/GitHub/openminicrew/dispatcher.py
  Tools:       /Users/seal/Documents/GitHub/openminicrew/tools/
  Providers:   /Users/seal/Documents/GitHub/openminicrew/core/providers/
  LLM Router:  /Users/seal/Documents/GitHub/openminicrew/core/llm.py
```

---

## 6. Checklist สำหรับแต่ละ Phase

### Phase 1 Checklist ✅ (completed 2026-03-04)

- [x] สร้าง `app/providers/__init__.py`
- [x] สร้าง `app/providers/base.py` — ย้าย AIProvider, dataclasses
- [x] สร้าง `app/providers/retry_config.py` — ย้าย create_retry_decorator
- [x] สร้าง `app/providers/chart_postprocessor.py` — รวม duplicate logic
- [x] สร้าง `app/providers/claude_provider.py` — ย้าย ClaudeProvider
- [x] สร้าง `app/providers/gemini_provider.py` — ย้าย GeminiProvider
- [x] สร้าง `app/providers/matcha_provider.py` — ย้าย MatchaProvider
- [x] สร้าง `app/providers/registry.py` — auto-discover + fallback
- [x] แก้ `app/services/ai_service.py` — ลบ provider classes, re-export for backward compat
- [x] Backward compatible imports verified (all 15 importing files pass)
- [x] Run `pytest tests/` — 82 passed, 0 regressions

### Phase 2 Checklist ✅ (completed 2026-03-04)

- [x] สร้าง `app/services/warning_detector.py` — ย้าย warning logic จาก chat.py
- [x] สร้าง `app/services/query_engine.py` — orchestrator
- [x] แก้ `app/api/v1/chat.py` — ใช้ QueryEngine, ลบ duplicate code ทั้งหมด
  - ลบ `DATA_WARNINGS`, `detect_data_warnings()`, `detect_multiple_sources_warning()`, `detect_context_from_question()`
  - POST endpoint ลดเหลือ 43 บรรทัด (เป้า ~50)
  - ลบ if/elif provider chain ออกหมด
  - แยก helpers: `_get_conversation_history()`, `_save_history()`, `_format_response()`, `_resolve_context_with_history()`
- [x] Run full test suite — 84 passed (+1 fixed), 0 regressions

### Phase 3 Checklist ✅ (completed 2026-03-04)

- [x] สร้าง `app/tools/__init__.py`
- [x] สร้าง `app/tools/base.py`
- [x] สร้าง `app/tools/registry.py`
- [x] สร้าง `app/tools/report_export.py` (ตัวอย่าง — CSV export tested)
- [x] ทดสอบ auto-discover — works

### Phase 4 Checklist

- [ ] สร้าง `openminicrew/tools/nt_query.py`
- [ ] เพิ่ม `NT_AI_BASE_URL`, `NT_AI_API_TOKEN` ใน `.env.example`
- [ ] ตั้งค่า authentication (service account หรือ API key)
- [ ] ทดสอบผ่าน Telegram: `/ntquery รายได้เดือนนี้`
- [ ] ทดสอบ free-text: พิมพ์ "รายได้เดือนนี้เท่าไหร่" ใน Telegram

### Phase 5 Checklist ✅ (completed 2026-03-04)

- [x] สร้าง `app/services/query_classifier.py` — rule-based, 7/7 test cases pass
- [x] เพิ่ม `get_model(tier)` ใน provider base class + all 3 providers
- [x] integrate กับ QueryEngine — uses `tier_classification_enabled` flag
- [x] Admin config: `tier_classification_enabled`, `force_tier` feature flags
- [x] ทดสอบ: simple→cheap, complex→mid, force_tier override

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gemini SDK ใช้ sync client ต้อง wrap ใน asyncio.to_thread | Medium | ทำอยู่แล้วใน GeminiProvider._run_async() — ย้ายไปด้วย |
| Matcha provider ใช้ httpx ต่างจาก Claude ที่ใช้ anthropic SDK | Low | แต่ละ provider จัดการ HTTP client เอง ไม่ share |
| chart_postprocessor ที่รวมมาอาจมี edge case ที่ต่างกัน | Medium | เขียน test เปรียบเทียบ output เดิม vs ใหม่ ก่อน merge |
| OpenMiniCrew เรียก NT AI API ต้อง auth | Medium | Phase 4 ต้อง solve auth ก่อน (แนะนำเพิ่ม API key auth) |
| Database lock ถ้าหลาย process เข้า SQLite พร้อมกัน | Low | NT AI ใช้ WAL mode อยู่แล้ว + production ควรใช้ PostgreSQL |

---

## Appendix A: OpenMiniCrew Patterns ที่ใช้อ้างอิง

### Provider Registry Pattern (core/providers/registry.py)

```python
# Key concept: auto-discover + fallback
class ProviderRegistry:
    def discover(self):
        """Scan directory, importlib.import_module, inspect.isclass, issubclass"""
        ...
    def get_fallback(self, preferred) -> BaseLLMProvider | None:
        """ลอง preferred ก่อน ถ้าไม่ได้ fallback ไปตัวอื่น"""
        ...
```

### Tool Registry Pattern (tools/registry.py)

```python
# Key concept: สร้างไฟล์เดียว auto-register
class ToolRegistry:
    def discover(self):
        """Scan tools/ directory"""
        ...
    command_map = {"/email": EmailSummaryTool(), ...}  # auto-populated
```

### BaseTool Pattern (tools/base.py)

```python
# Key concept: direct_output + preferred_tier
class BaseTool(ABC):
    direct_output: bool = True    # ส่งผลตรง vs ผ่าน LLM สรุป
    preferred_tier: str = "cheap" # cost control
```

### Dispatcher Pattern (dispatcher.py)

```python
# Key concept: /command -> tool ตรง (0 token), free text -> LLM -> tool
async def dispatch(user_id, user, text):
    command, args = parse_command(text)
    tool = registry.get_by_command(command)
    if tool:
        return await tool.execute(user_id, args)  # ไม่เสีย token
    # else: LLM function calling -> tool
```

---

## Appendix B: Current ai_service.py Structure Map

เพื่อช่วย AI agent หาจุดที่ต้องย้าย:

```
ai_service.py (ประมาณ 1,200 บรรทัด)

Lines   1-18    Module docstring + imports
Lines  19-35    httpx, tenacity, MCP imports
Lines  36-74    create_retry_decorator() → ย้ายไป retry_config.py
Lines  75-86    @dataclass ConfidenceResult → ย้ายไป base.py
Lines  87-98    @dataclass QueryResult → ย้ายไป base.py
Lines  99-106   @dataclass RetryStatus → ย้ายไป base.py
Lines 107-115   class AIProvider(ABC) → ย้ายไป base.py
Lines 116-250   class ClaudeProvider → ย้ายไป claude_provider.py
                  - explain_result มี chart post-processing → ย้ายไป chart_postprocessor.py
Lines 251-500   class GeminiProvider → ย้ายไป gemini_provider.py
                  - generate_sql มี complex history reconstruction
                  - explain_result มี duplicate chart post-processing
Lines 501-750   class MatchaProvider → ย้ายไป matcha_provider.py
                  - explain_result มี auto-detect chart config logic
Lines 751-800   class AIService.__init__ → แก้ให้รับ provider instance
Lines 801-950   AIService.query_with_retry() → คงไว้ใน ai_service.py
Lines 951-1150  AIService.query_hybrid() → คงไว้ใน ai_service.py
Lines 1151-1170 AIService._extract_sql() → คงไว้
Lines 1171-1190 AIService._extract_explanation() → คงไว้
Lines 1191-1210 AIService._get_vanna_context_string() → คงไว้
Lines 1211-1300 AIService._extract_keywords..., _lookup_values..., _format_value... → คงไว้
Lines 1301-1400 AIService._extract_intent(), _build_pass2_prompt() → คงไว้
Lines 1401-1420 AIService.train() → คงไว้
Lines 1421-1500 AIService.suggest_mappings() → คงไว้
Lines 1501-1520 Factory functions (create_claude_service, etc.) → ลบ, ใช้ registry แทน
```

---

*End of Plan*

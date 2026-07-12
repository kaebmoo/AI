# Plan 1B: MCP Consolidation + Admin MCP Server

**Priority:** ทำคู่กับ Plan 1 (Admin Agent)  
**ประมาณเวลา:** 2-3 วัน  
**Prerequisite:** ไม่มี (Phase A standalone), Plan 1 สำหรับ Phase B  
**อ้างอิงโดย:** Plan 4B (OpenMiniCrew ผ่าน MCP), Plan 6 (SaaS SSE transport)

---

## Phase A: Validation Consolidation

### ปัญหาปัจจุบัน

Validation/confidence logic อยู่ 2 ที่:

1. **QueryEngine pipeline** (`query_engine.py` + `warning_detector.py` + providers)
   - `WarningDetector.detect()` — DB-driven, per-context, cached, ซับซ้อน
   - `ConfidenceResult` — populate ระหว่าง LLM explain_result ใน providers
   - ใช้โดยทุก query ที่ผ่าน QueryEngine

2. **MCP nt-validation** (`mcp_servers/nt_validation_mcp.py`)
   - `check_business_rules()` — 7 hardcoded BUILTIN_RULES + อ่าน DB อย่างง่าย
   - `calculate_confidence_score()` — formula 4 factors (25+25+25+25)
   - `validate_result()` — ตรวจ data เบื้องต้น (null, large values)
   - ใช้โดย LLM ผ่าน MCP tool calling (ถ้า LLM เลือกเรียก)

### ตัดสินใจ: QueryEngine เป็น source of truth, MCP เป็น thin wrapper

**เหตุผล:**
- QueryEngine เป็น single point ที่ทุก caller ใช้ (web, Telegram, API, Admin Agent)
- WarningDetector ของ QueryEngine sophisticated กว่า (DB-driven rules, per-context filtering, cached)
- MCP hardcoded rules stale ได้ — ถ้า admin เพิ่ม rule ใน DB, MCP hardcoded ไม่รู้
- Confidence scoring ต้องใช้ context จาก LLM response จริง — formula ใน MCP ไม่มี context นี้

### สิ่งที่ต้องทำ

#### A1: สร้าง validation service (extract จาก QueryEngine)

```python
# app/services/validation_service.py (NEW)

class ValidationService:
    """Centralized validation — single source of truth"""
    
    def __init__(self, schema_service, mcp_client=None):
        self.schema_service = schema_service
        self.warning_detector = WarningDetector(mcp_client=mcp_client, schema_service=schema_service)
    
    def validate_sql(self, sql: str) -> ValidationResult:
        """
        SQL safety validation.
        ย้าย logic จาก MCP validate_sql() มาที่นี่
        + เพิ่ม DB-driven rules จาก schema_business_rules
        """
    
    async def detect_warnings(self, data, sql_query, context_name) -> List[DataWarning]:
        """Delegate to WarningDetector (already DB-driven)"""
        return await self.warning_detector.detect(data, sql_query, context_name)
    
    def check_business_rules(self, sql: str, question: str, context_name: str) -> RuleCheckResult:
        """
        ตรวจ business rules — ย้ายจาก MCP check_business_rules()
        ใช้ rules จาก DB เท่านั้น (ลบ hardcoded BUILTIN_RULES)
        """
    
    def calculate_confidence(self, factors: Dict) -> ConfidenceResult:
        """
        Confidence scoring.
        ใช้ factors จาก LLM + rule check + execution result
        """
```

#### A2: แก้ MCP servers ให้เป็น thin wrapper

```python
# mcp_servers/nt_validation_mcp.py — แก้ให้ delegate

@mcp.tool()
def validate_sql(sql: str) -> Dict:
    """ตรวจ SQL — delegate to ValidationService"""
    from app.services.validation_service import ValidationService
    service = ValidationService(schema_service=_get_schema_service())
    return service.validate_sql(sql).to_dict()

@mcp.tool()
def check_business_rules(sql: str, question: str = "", context_name: str = "revenue") -> str:
    """ตรวจ business rules — delegate to ValidationService"""
    from app.services.validation_service import ValidationService
    service = ValidationService(schema_service=_get_schema_service())
    result = service.check_business_rules(sql, question, context_name)
    return json.dumps(result.to_dict(), ensure_ascii=False)
```

**ผลลัพธ์:**
- MCP tools ยังเรียกได้เหมือนเดิม (LLM ไม่ต้องเปลี่ยน)
- Logic อยู่ที่เดียว (`ValidationService`)
- ลบ `BUILTIN_RULES` hardcoded ออก
- ลบ `calculate_confidence_score` ที่เป็น formula ง่าย — ใช้ confidence จาก LLM pipeline แทน

#### A3: แก้ QueryEngine ให้ใช้ ValidationService

```python
# app/services/query_engine.py — แก้

class QueryEngine:
    async def query(self, ...):
        ...
        # 5. Detect warnings (เดิม)
        validation_service = ValidationService(
            schema_service=self.schema_service,
            mcp_client=self.mcp_client,
        )
        warnings = await validation_service.detect_warnings(
            data=result.data,
            sql_query=result.sql_query,
            context_name=context_name,
        )
        ...
```

#### A4: ลบ/ย้าย hardcoded rules

สิ่งที่ต้องลบจาก `nt_validation_mcp.py`:
- `BUILTIN_RULES` array (7 rules) — ย้ายไปเป็น seed data ใน DB migration
- `calculate_confidence_score()` internal logic — delegate ไป ValidationService
- `validate_result()` internal logic — delegate ไป ValidationService

สิ่งที่ต้องเพิ่มใน DB:
- Migration script ที่ insert 7 built-in rules จาก `BUILTIN_RULES` → `schema_business_rules` table (ถ้ายังไม่มี)

### ไฟล์ที่ต้องสร้าง/แก้

| ไฟล์ | Action |
|------|--------|
| `app/services/validation_service.py` | **NEW** — centralized validation |
| `mcp_servers/nt_validation_mcp.py` | **EDIT** — delegate ไป ValidationService, ลบ hardcoded logic |
| `app/services/query_engine.py` | **EDIT** — ใช้ ValidationService |
| `database/migrations/026_seed_builtin_rules.sql` | **NEW** — seed 7 hardcoded rules ไป DB |
| `tests/unit/test_validation_service.py` | **NEW** — tests |

---

## Phase B: Admin MCP Server (ทำหลัง Plan 1)

### แนวคิด

Expose admin tools (จาก Plan 1) เป็น MCP server ด้วย เพื่อให้:
- **Claude Desktop / Claude Code** เรียก admin operations ได้ตรง
- **OpenMiniCrew** (อนาคต) เรียกผ่าน MCP protocol
- **External AI agents** integrate ได้

### ไฟล์ใหม่

```python
# mcp_servers/nt_admin_mcp.py

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name=" Admin Server",
    instructions="Admin operations for AI Assistant: manage mappings, rules, examples, onboarding."
)

@mcp.tool()
def search_semantic_mappings(keyword: str = "", column: str = "") -> str:
    """ค้นหา semantic mapping"""
    # Delegate to admin tool (from Plan 1)

@mcp.tool()
def add_semantic_mapping(keyword: str, target_column: str, target_condition: str, 
                         context_name: str = None) -> str:
    """เพิ่ม semantic mapping ใหม่"""
    # Delegate to admin tool + dedup check

@mcp.tool()
def search_business_rules(keyword: str = "", severity: str = "") -> str:
    """ค้นหา business rule"""

@mcp.tool()
def add_business_rule(rule_code: str, rule_name: str, rule_description: str,
                      severity: str = "warning", table_name: str = "") -> str:
    """เพิ่ม business rule ใหม่"""

@mcp.tool()
def search_golden_examples(keyword: str = "", category: str = "") -> str:
    """ค้นหา golden example"""

@mcp.tool()
def add_golden_example(question: str, sql: str, category: str = "") -> str:
    """เพิ่ม golden example ใหม่"""

@mcp.tool()
def inspect_view(view_name: str) -> str:
    """ดูโครงสร้าง view/table (Phase 1 ของ Context Onboarding)"""

@mcp.tool()
def run_onboarding(view_name: str, provider: str = "gemini", dry_run: bool = True) -> str:
    """Onboard view ใหม่"""

@mcp.tool()
def analyze_failed_queries(period: str = "24h", limit: int = 10) -> str:
    """วิเคราะห์ query ที่ fail"""

@mcp.tool()
def refresh_cache() -> str:
    """Clear cache ทั้งระบบ"""

@mcp.tool()
def list_available_views() -> str:
    """แสดง views ที่ onboard ได้"""
```

### Integration

**Claude Desktop config:**
```json
{
  "mcpServers": {
    "nt-metadata": { ... },
    "nt-query": { ... },
    "nt-admin": {
      "command": "python",
      "args": ["-m", "mcp_servers.nt_admin_mcp"],
      "cwd": "/Users/seal/Documents/GitHub/AI"
    }
  }
}
```

**mcp_client.py auto-detect:**
```python
# app/services/mcp_client.py — เพิ่ม
if os.path.exists(os.path.join(base_path, "mcp_servers", "nt_admin_mcp.py")):
    configs.append(MCPServerConfig(
        name="nt-admin",
        command=python_cmd,
        args=["-m", "mcp_servers.nt_admin_mcp"],
        env=env
    ))
```

### Admin MCP vs Admin Agent (Plan 1)

| ด้าน | Admin MCP | Admin Agent (Plan 1) |
|------|-----------|---------------------|
| **ใช้โดย** | Claude Desktop, Claude Code, MCP clients | Web UI chat, Telegram admin, API |
| **Auth** | ไม่มี (stdio local) → เพิ่ม auth เมื่อ SSE | Session token / API key |
| **Conversation** | ไม่มี memory — stateless tool calls | มี conversation history |
| **Confirmation** | ไม่มี built-in — LLM host จัดการเอง | Built-in requires_confirmation flow |
| **Tools** | เหมือนกัน — share code กับ Admin Agent | เหมือนกัน |

**Key insight:** Admin MCP tools และ Admin Agent tools ใช้ **code เดียวกัน** — `app/tools/admin/` เป็น shared layer ทั้งคู่เรียกใช้:

```
Claude Desktop → MCP nt-admin → app/tools/admin/mapping_tools.py
Web Admin UI   → Admin Agent  → app/tools/admin/mapping_tools.py
Telegram Admin → Admin Agent  → app/tools/admin/mapping_tools.py
```

---

## Phase C: SSE Transport + Auth (ทำตอน Plan 6 SaaS)

ปัจจุบัน MCP ใช้ stdio transport (local subprocess) ถ้าต้องให้ external consumers เรียก:

### สิ่งที่ต้องเพิ่ม

1. **SSE transport** — FastMCP รองรับอยู่แล้ว แค่เปลี่ยน `mcp.run(transport="sse")`
2. **Auth middleware** — ตรวจ API key ก่อน process tool call
3. **Deploy** — run เป็น HTTP service (แยก port หรือ mount ใน FastAPI app)

```python
# mcp_servers/nt_admin_mcp.py — SSE mode

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    
    if args.transport == "sse":
        # SSE mode — HTTP-based, accessible from network
        mcp.run(transport="sse", port=args.port)
    else:
        # stdio mode — local subprocess
        mcp.run(transport="stdio")
```

### Auth สำหรับ SSE mode

ใช้ API key auth เดียวกับ Plan 4B — ไม่สร้าง auth system ใหม่:

```python
# ต้องเพิ่ม auth layer ใน FastMCP SSE transport
# ดู FastMCP docs ว่า middleware support ยังไง
# ถ้าไม่ support → wrap ด้วย FastAPI app ที่มี auth middleware
```

### Timeline

Phase C ไม่ต้องทำตอนนี้ — ทำเมื่อ:
- ต้องการให้ Claude Desktop ของคนอื่น (ไม่ใช่เครื่อง local) เข้าถึง
- ต้องการ expose MCP เป็น SaaS service
- OpenMiniCrew จะเชื่อมผ่าน MCP แทน HTTP API

---

## Claude Code Instructions

```
## Phase A: Validation Consolidation (ทำได้เลย)

### ไฟล์ที่ต้องอ่านก่อน
- mcp_servers/nt_validation_mcp.py (BUILTIN_RULES, calculate_confidence_score, validate_result)
- app/services/warning_detector.py (WarningDetector — DB-driven)
- app/services/query_engine.py (ดู step 5: detect warnings + confidence)
- app/providers/base.py (ConfidenceResult dataclass)
- app/providers/claude_provider.py (ดูว่า confidence populate ที่ไหน)

### ลำดับ
1. สร้าง app/services/validation_service.py
   - ย้าย validate_sql logic จาก MCP
   - ย้าย check_business_rules logic จาก MCP (เอาแต่ DB-driven, ลบ hardcoded)
   - Wrap WarningDetector.detect() ที่มีอยู่
2. สร้าง database/migrations/026_seed_builtin_rules.sql
   - INSERT 7 rules จาก BUILTIN_RULES → schema_business_rules (INSERT OR IGNORE)
3. แก้ mcp_servers/nt_validation_mcp.py
   - ลบ BUILTIN_RULES array
   - ลบ internal logic ใน check_business_rules, calculate_confidence_score, validate_result
   - แทนที่ด้วย import + delegate ไป ValidationService
   - (validate_sql ยังเก็บ basic safety check ไว้ที่ MCP ได้ เพราะ MCP อาจถูกเรียกแบบ standalone ที่ไม่มี app context)
4. แก้ query_engine.py ให้ใช้ ValidationService.detect_warnings()
5. สร้าง tests/unit/test_validation_service.py
6. รัน tests ทั้งหมด

## Phase B: Admin MCP (ทำหลัง Plan 1)

### ลำดับ
1. Plan 1 ต้องเสร็จก่อน (app/tools/admin/ มี tools แล้ว)
2. สร้าง mcp_servers/nt_admin_mcp.py
   - Import admin tools จาก app/tools/admin/
   - Wrap แต่ละ tool เป็น @mcp.tool()
3. เพิ่ม config ใน mcp_servers/claude_desktop_config.json
4. เพิ่ม auto-detect ใน app/services/mcp_client.py
5. ทดสอบ: Claude Desktop เรียก admin tools ได้

## กฎ
- ValidationService เป็น source of truth — MCP เป็น thin wrapper
- ห้ามมี business logic ใน MCP server files (ยกเว้น basic SQL safety check)
- Admin MCP tools ใช้ code เดียวกับ Admin Agent — อยู่ใน app/tools/admin/
- nt-admin MCP ไม่ต้องมี auth ตอนนี้ (stdio = local only)
- Phase C (SSE + auth) ทำเมื่อ Plan 6 เท่านั้น
```

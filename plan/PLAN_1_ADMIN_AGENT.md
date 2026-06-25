# Plan 1: Admin Agent — Tool-Calling Dispatcher for Admin Operations

**Priority:** 1 (foundation สำหรับ Plan 2, 3, 4)  
**ประมาณเวลา:** 3-5 วัน  
**Prerequisite:** Plan 0  
**อ้างอิงโดย:** Plan 2 (Feedback), Plan 3 (Self-Learning), Plan 4 (Telegram)

---

## 1. แนวคิด

สร้าง Admin Agent ที่ admin คุยภาษาธรรมชาติ (ไทย/อังกฤษ) แล้ว LLM เลือกเรียก tools ที่มีในระบบอัตโนมัติ ใช้ pattern Dispatcher + Tool Registry + Function Calling เหมือน OpenMiniCrew

**ตัวอย่างการใช้งาน:**
```
Admin: "datacom ไม่ได้อยู่ใน business_unit แต่อยู่ใน service_group"
Agent: → เรียก search_existing_mappings("datacom") → ไม่พบ
       → เรียก add_semantic_mapping(keyword="datacom", target_column="service_group", ...)
       → "เพิ่ม mapping แล้ว: 'datacom' → service_group = 'datacom'"

Admin: "ดู query ที่ fail เยอะสุดสัปดาห์นี้"
Agent: → เรียก analyze_failed_queries(period="7d", limit=10)
       → สรุปรายงาน + แนะนำ fix

Admin: "onboard view v_asset_summary ด้วย gemini"
Agent: → เรียก run_onboarding(view_name="v_asset_summary", provider="gemini")
       → แสดง preview → ถาม confirm → apply
```

## 2. สถาปัตยกรรม

```
Admin (Web UI / Telegram / API)
        │
        ▼
┌─────────────────────────────────┐
│     Admin Agent Dispatcher      │
│  (app/services/admin_agent.py)  │
│                                 │
│  1. รับข้อความจาก admin         │
│  2. ดึง conversation history    │
│  3. ส่งให้ LLM พร้อม tool specs │
│  4. LLM เลือก tool / ตอบตรง    │
│  5. execute tool → ส่งผลกลับ   │
│  6. บันทึก conversation         │
└────────────┬────────────────────┘
             │
     ┌───────┼───────────┐
     ▼       ▼           ▼
┌─────────┐ ┌──────────┐ ┌────────────┐
│ Admin   │ │ LLM      │ │ Conversation│
│ Tool    │ │ Provider  │ │ Memory     │
│ Registry│ │ Registry │ │ (DB)       │
│         │ │ (existing)│ │            │
│ 12+ tools│ │          │ │            │
└─────────┘ └──────────┘ └────────────┘
```

## 3. Admin Tools ที่ต้องสร้าง

แต่ละ tool = 1 ไฟล์ใน `app/tools/admin/` (แยก directory จาก user tools)

| Tool Name | คำอธิบาย | API ที่ใช้ (มีอยู่แล้ว) |
|-----------|---------|----------------------|
| `search_mappings` | ค้นหา semantic mapping ที่มีอยู่ | `GET /admin/mappings` |
| `add_mapping` | เพิ่ม semantic mapping | `POST /admin/mappings` |
| `search_rules` | ค้นหา business rule | `GET /admin/rules` |
| `add_rule` | เพิ่ม business rule | `POST /admin/rules` |
| `search_examples` | ค้นหา golden example | `GET /admin/golden-examples` |
| `add_example` | เพิ่ม golden example | `POST /admin/golden-examples` |
| `inspect_view` | ดูโครงสร้าง view/table | `POST /admin/contexts/onboard/inspect` |
| `run_onboarding` | Full onboarding pipeline | `POST /admin/contexts/onboard` |
| `analyze_query_logs` | วิเคราะห์ query logs | `GET /admin/query-logs` + LLM analysis |
| `review_feedback` | ดู feedback ที่รอ review | feedback_service + join ChatHistory |
| `validate_config` | ตรวจ config ของ view | `POST /admin/contexts/onboard/validate` |
| `refresh_cache` | Clear cache ทั้งระบบ | `POST /admin/refresh-cache` |
| `list_contexts` | แสดง contexts ทั้งหมด | `GET /admin/contexts` |
| `search_hierarchy` | ค้นหา hierarchy values | `GET /admin/hierarchy/{ctx}/search` |

## 4. ไฟล์ที่ต้องสร้าง/แก้

### ไฟล์ใหม่

| ไฟล์ | หน้าที่ |
|------|---------|
| `app/tools/admin/__init__.py` | Package init |
| `app/tools/admin/base.py` | `AdminBaseTool` (extends BaseTool, เพิ่ม requires_confirmation, category) |
| `app/tools/admin/registry.py` | AdminToolRegistry (auto-discover จาก admin/ folder) |
| `app/tools/admin/mapping_tools.py` | search_mappings, add_mapping |
| `app/tools/admin/rule_tools.py` | search_rules, add_rule |
| `app/tools/admin/example_tools.py` | search_examples, add_example |
| `app/tools/admin/onboarding_tools.py` | inspect_view, run_onboarding, validate_config |
| `app/tools/admin/analysis_tools.py` | analyze_query_logs, review_feedback |
| `app/tools/admin/system_tools.py` | refresh_cache, list_contexts, search_hierarchy |
| `app/services/admin_agent.py` | Admin Agent Dispatcher (core) |
| `app/api/v1/admin_agent.py` | API endpoint: `POST /admin/agent/chat` |
| `app/schemas/admin_agent_schemas.py` | Request/Response schemas |
| `frontend-admin/src/pages/AdminAgent.tsx` | Chat UI page สำหรับ admin |
| `frontend-admin/src/services/adminAgentService.ts` | API service |

### ไฟล์แก้

| ไฟล์ | การแก้ |
|------|--------|
| `app/main.py` | เพิ่ม router: `admin_agent_router` |
| `app/tools/registry.py` | เพิ่ม method `discover_admin_tools()` หรือแยก registry |
| `frontend-admin/src/App.tsx` | เพิ่ม route `/admin-agent` |
| `frontend-admin/src/components/Layout/AdminLayout.tsx` | เพิ่ม menu item |

## 5. Admin Agent Dispatcher Design

```python
# app/services/admin_agent.py (concept)

class AdminAgent:
    """
    Dispatcher for admin tool-calling conversations.
    Pattern: OpenMiniCrew dispatcher.py
    """
    
    def __init__(self, provider, admin_tool_registry, db_session):
        self.provider = provider  # LLM provider (from provider_registry)
        self.tools = admin_tool_registry
        self.db = db_session
    
    async def chat(self, user_id: int, message: str, conversation_id: str = None) -> AgentResponse:
        """
        Process admin message:
        1. Load conversation history
        2. Build system prompt + tool specs
        3. LLM decides: call tool or answer directly
        4. If tool call: execute → return result
        5. If needs confirmation: ask admin first
        6. Save conversation
        """
        # 1. Load history
        history = self._load_history(conversation_id)
        
        # 2. Build prompt
        system_prompt = self._build_system_prompt()
        tool_specs = self.tools.get_all_specs()  # ทุก admin tools
        
        # 3. LLM call
        response = await self.provider.generate_with_tools(
            messages=history + [{"role": "user", "content": message}],
            system=system_prompt,
            tools=tool_specs,
        )
        
        # 4. Handle tool calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool = self.tools.get(tool_call.name)
                
                # Check confirmation requirement
                if tool.requires_confirmation:
                    return AgentResponse(
                        message=f"ต้องการ {tool_call.name} ด้วย parameters:\n{tool_call.args}\n\nยืนยันไหม?",
                        pending_action=tool_call,
                        status="awaiting_confirmation"
                    )
                
                # Execute
                result = await tool.execute(**tool_call.args)
                
                # LLM summarize result
                summary = await self._summarize_result(tool_call, result, history)
                return AgentResponse(message=summary, tool_used=tool_call.name)
        
        # 5. Direct answer
        return AgentResponse(message=response.content)
    
    def _build_system_prompt(self) -> str:
        return """คุณเป็น Admin Assistant สำหรับระบบ AI Assistant
        
หน้าที่:
- ช่วย admin จัดการ config ของระบบ NL-to-SQL
- วิเคราะห์ปัญหาจาก query logs และ feedback
- เพิ่ม/แก้ไข semantic mappings, business rules, golden examples
- Onboard view/table ใหม่
- ตรวจสอบและ validate config

กฎสำคัญ:
- เมื่อเพิ่ม mapping/rule/example ใหม่ ต้องค้นหาของเดิมก่อน (search ก่อน add) เพื่อป้องกันซ้ำ
- การ add/edit ต้องถาม confirm ก่อน execute
- ตอบเป็นภาษาไทย ยกเว้น technical terms
- ถ้าไม่มี tool ที่เหมาะ ให้แจ้ง admin ว่าทำไม่ได้ พร้อมแนะนำทางอื่น
"""
```

## 6. AdminBaseTool Design

```python
# app/tools/admin/base.py

class AdminBaseTool(BaseTool):
    """Extended BaseTool for admin operations"""
    
    category: str = "general"  # mapping, rule, example, onboarding, analysis, system
    requires_confirmation: bool = False  # True = ถาม confirm ก่อน execute
    is_destructive: bool = False  # True = แก้ไข/ลบข้อมูล
    
    async def execute(self, db_session=None, **kwargs) -> Dict[str, Any]:
        """Admin tools get db_session injected"""
        ...
    
    async def search_duplicates(self, **kwargs) -> List[Dict]:
        """ค้นหาข้อมูลซ้ำก่อน add (implement per tool)"""
        return []
```

## 7. ตัวอย่าง Admin Tool

```python
# app/tools/admin/mapping_tools.py

class SearchMappingsTool(AdminBaseTool):
    name = "search_mappings"
    description = "ค้นหา semantic mapping ที่มีอยู่ในระบบ ด้วย keyword หรือ column name"
    category = "mapping"
    requires_confirmation = False
    
    async def execute(self, keyword: str = "", column: str = "", context: str = "", 
                      db_session=None, **kwargs) -> Dict:
        from app.models.schema_models import SchemaSemanticMapping
        query = db_session.query(SchemaSemanticMapping)
        if keyword:
            query = query.filter(SchemaSemanticMapping.keyword.ilike(f"%{keyword}%"))
        if column:
            query = query.filter(SchemaSemanticMapping.target_column.ilike(f"%{column}%"))
        results = query.limit(20).all()
        return {
            "success": True,
            "count": len(results),
            "mappings": [{"keyword": m.keyword, "column": m.target_column, 
                          "condition": m.target_condition, "context": m.context_name} 
                         for m in results]
        }
    
    def get_tool_spec(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "keyword ที่ต้องการค้นหา"},
                    "column": {"type": "string", "description": "ชื่อ column ที่ต้องการค้นหา"},
                    "context": {"type": "string", "description": "context name เช่น revenue, expense"},
                },
                "required": [],
            },
        }


class AddMappingTool(AdminBaseTool):
    name = "add_mapping"
    description = "เพิ่ม semantic mapping ใหม่ เช่น map คำว่า 'datacom' ไปยัง service_group column"
    category = "mapping"
    requires_confirmation = True  # ถาม confirm ก่อน
    is_destructive = False
    
    async def execute(self, keyword: str, target_column: str, target_condition: str,
                      context_name: str = None, keyword_type: str = "term",
                      db_session=None, **kwargs) -> Dict:
        from app.models.schema_models import SchemaSemanticMapping
        
        # Check duplicate
        existing = db_session.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword == keyword
        ).first()
        if existing:
            return {"success": False, "error": f"keyword '{keyword}' มีอยู่แล้ว: {existing.target_condition}"}
        
        mapping = SchemaSemanticMapping(
            keyword=keyword, keyword_type=keyword_type,
            target_column=target_column, target_condition=target_condition,
            context_name=context_name, is_active=True,
        )
        db_session.add(mapping)
        db_session.commit()
        
        # Refresh cache
        from app.services.schema_service import SchemaService
        schema_service = SchemaService(db_session)
        schema_service.refresh_cache()
        
        return {"success": True, "id": mapping.id, "keyword": keyword, 
                "condition": target_condition}
```

## 8. API Endpoint

```python
# app/api/v1/admin_agent.py

@router.post("/agent/chat")
async def admin_agent_chat(
    request: AdminAgentChatRequest,  # { message: str, conversation_id?: str }
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
    ai_service: AIService = Depends(deps.get_ai_service),
):
    agent = AdminAgent(
        provider=ai_service.provider,
        admin_tool_registry=admin_tool_registry,
        db_session=db,
    )
    response = await agent.chat(
        user_id=current_user.id,
        message=request.message,
        conversation_id=request.conversation_id,
    )
    return response
```

## 9. Frontend: Admin Agent Chat Page

**ตำแหน่ง menu:** เพิ่มที่ top ของ sidebar (ก่อน Dashboard) หรือเป็น floating chat button

**UI:**
- Chat interface คล้าย ChatGPT -- messages + input box
- แสดง tool calls ที่ agent ใช้ (collapsible)
- Confirmation dialog เมื่อ agent ต้องการ add/edit
- แสดง link ไปหน้า admin ที่เกี่ยวข้อง (เช่น หลัง add mapping → link ไป Mappings page)

## 10. Conversation Storage

ใช้ตาราง `admin_agent_conversations` ใน app DB (ไม่ใช่ business DB):

```sql
CREATE TABLE admin_agent_conversations (
    id TEXT PRIMARY KEY,  -- UUID
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE admin_agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES admin_agent_conversations(id),
    role TEXT NOT NULL,  -- user, assistant, tool_call, tool_result
    content TEXT NOT NULL,
    tool_name TEXT,
    tool_args TEXT,  -- JSON
    tool_result TEXT,  -- JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Claude Code Instructions

```
## ไฟล์ที่ต้องอ่านก่อน
- app/tools/base.py (BaseTool pattern)
- app/tools/registry.py (auto-discover pattern)
- app/tools/report_export.py (example tool)
- app/services/ai_service.py (provider + generate_with_tools pattern)
- app/providers/claude_provider.py (generate_sql method → ดูว่า tool calling ทำอย่างไร)
- app/providers/gemini_provider.py (เทียบ)
- app/api/v1/admin.py (existing admin endpoints ที่ tools จะเรียก)

## ลำดับ Implementation

Phase 1: Infrastructure
  1. สร้าง app/tools/admin/ directory + __init__.py
  2. สร้าง app/tools/admin/base.py (AdminBaseTool)
  3. สร้าง app/tools/admin/registry.py (AdminToolRegistry)

Phase 2: Core Tools (เริ่มจากที่ใช้บ่อยสุด)
  4. สร้าง mapping_tools.py (search + add)
  5. สร้าง rule_tools.py (search + add)
  6. สร้าง example_tools.py (search + add)
  7. สร้าง system_tools.py (refresh_cache, list_contexts)

Phase 3: Agent Dispatcher
  8. สร้าง app/services/admin_agent.py
  9. สร้าง app/schemas/admin_agent_schemas.py
  10. สร้าง app/api/v1/admin_agent.py
  11. แก้ app/main.py เพิ่ม router
  12. สร้าง DB migration สำหรับ conversation tables

Phase 4: Advanced Tools
  13. สร้าง onboarding_tools.py (inspect, onboard, validate)
  14. สร้าง analysis_tools.py (query_logs, feedback_review)

Phase 5: Frontend
  15. สร้าง adminAgentService.ts
  16. สร้าง AdminAgent.tsx (chat page)
  17. แก้ App.tsx + AdminLayout.tsx

Phase 6: Tests
  18. Unit tests สำหรับ tools
  19. Integration test สำหรับ agent endpoint
  20. End-to-end test: คุยกับ agent แล้วดูว่า mapping ถูกเพิ่ม

## กฎ
- Admin tools อยู่ใน app/tools/admin/ แยกจาก user tools ใน app/tools/
- ทุก add/edit tool ต้อง requires_confirmation = True
- ทุก add tool ต้อง search duplicate ก่อน
- Tool specs ต้องมี description ชัดเจนทั้งไทยและอังกฤษ (LLM ใช้ตัดสินใจ)
- Provider ใช้จาก provider_registry ที่มีอยู่ (ไม่สร้างใหม่)
- generate_with_tools flow ดูจาก claude_provider.py → generate_sql() เป็นต้นแบบ
  แต่ Admin Agent ไม่ใช่ SQL generation — เป็น general tool calling
  ต้องสร้าง method ใหม่: provider.generate_with_tools(messages, system, tools)
  หรือ reuse generate_sql ด้วย system prompt ที่ต่างกัน
```

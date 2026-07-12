# Plan 3: Self-Learning Loop + Dedup Engine

**Priority:** 3  
**ประมาณเวลา:** 3-5 วัน  
**Prerequisite:** Plan 1 (Admin Agent), Plan 2 (Feedback Enhancement)  
**อ้างอิง:** ใช้ Admin Agent tools จาก Plan 1, ใช้ feedback data จาก Plan 2

---

## 1. แนวคิด

สร้างระบบที่เรียนรู้จากความผิดพลาดอัตโนมัติ:

```
Failed Query / Thumbs Down
        │
        ▼
┌─────────────────────────┐
│   Auto-Analyzer         │
│   (scheduled job)       │
│                         │
│   1. ดึง failed queries │
│   2. LLM วิเคราะห์สาเหตุ│
│   3. เสนอ fix           │
│   4. Dedup check        │
│   5. Confidence scoring │
└────────────┬────────────┘
             │
     ┌───────┴───────┐
     ▼               ▼
┌─────────┐   ┌──────────────┐
│ High    │   │ Low          │
│ Conf.   │   │ Confidence   │
│ (≥0.8)  │   │ (<0.8)       │
│         │   │              │
│ Auto-   │   │ Queue for    │
│ Apply   │   │ Admin Review │
│ + Log   │   │ (notification│
│         │   │  via Telegram│
└─────────┘   │  Plan 4)     │
              └──────────────┘
```

## 2. Components

### 2.1 Auto-Analyzer Service

**ไฟล์:** `app/services/auto_analyzer.py`

```python
class AutoAnalyzer:
    """Analyze failed queries and suggest fixes"""
    
    async def analyze_recent_failures(self, period_hours: int = 24) -> List[AnalysisResult]:
        """
        1. ดึง queries ที่ fail / thumbs down ในช่วง N ชั่วโมง
        2. Group by pattern (คำถามคล้ายกัน)
        3. LLM วิเคราะห์แต่ละ group:
           - SQL ผิดตรงไหน?
           - ต้องเพิ่ม mapping/rule/example อะไร?
           - Confidence score (0-1)
        4. Return suggested fixes
        """
    
    async def analyze_single_query(self, chat_id: int) -> AnalysisResult:
        """วิเคราะห์ query เดียว (เรียกจาก Admin Agent / Feedback Review)"""

    def _group_similar_failures(self, failures: List[Dict]) -> List[FailureGroup]:
        """Group by similarity (shared keywords, same context, same error pattern)"""

    async def _llm_diagnose(self, group: FailureGroup) -> Diagnosis:
        """LLM วิเคราะห์สาเหตุ + เสนอ fix"""
```

**Output structure:**
```python
@dataclass
class SuggestedFix:
    fix_type: str  # "add_mapping", "add_rule", "add_example", "update_instruction"
    confidence: float  # 0.0 - 1.0
    params: Dict  # parameters สำหรับ tool
    reason: str  # เหตุผลที่เสนอ fix นี้
    source_queries: List[int]  # chat_ids ที่ทำให้เกิด fix นี้

@dataclass  
class AnalysisResult:
    failure_group: FailureGroup
    diagnosis: str  # LLM explanation
    suggested_fixes: List[SuggestedFix]
    auto_applicable: bool  # True ถ้าทุก fix มี confidence ≥ 0.8
```

### 2.2 Dedup Engine

**ไฟล์:** `app/services/dedup_engine.py`

ก่อน insert mapping/rule/example ใหม่ ต้องตรวจ:

```python
class DedupEngine:
    """ป้องกัน rules/mappings ซ้ำซ้อนหรือขัดแย้ง"""
    
    def check_mapping_duplicate(self, keyword: str, db: Session) -> DedupResult:
        """
        ตรวจ:
        1. Exact match: keyword เดียวกันมีอยู่แล้ว
        2. Semantic overlap: keyword คล้ายกัน (เช่น "datacom" vs "Datacom")
        3. Conflict: keyword เดียวกันแต่ map ไป column ต่างกัน
        """
    
    def check_rule_duplicate(self, rule_code: str, rule_description: str, db: Session) -> DedupResult:
        """
        ตรวจ:
        1. rule_code ซ้ำ
        2. rule_description คล้ายกัน (LLM judge similarity)
        3. ขัดแย้งกับ rule อื่น
        """
    
    def check_example_duplicate(self, question: str, sql: str, db: Session) -> DedupResult:
        """
        ตรวจ:
        1. question pattern คล้ายกัน (cosine similarity ถ้ามี embeddings, หรือ keyword overlap)
        2. SQL ซ้ำกัน
        """

@dataclass
class DedupResult:
    has_duplicate: bool
    duplicate_type: str  # "exact", "semantic", "conflict", "none"
    existing_items: List[Dict]  # items ที่ซ้ำ/ขัดแย้ง
    recommendation: str  # "skip", "merge", "replace", "add_anyway"
```

**Dedup strategies (เรียงตามความเข้มงวด):**

1. **Exact match:** keyword/rule_code ตรงกัน → skip
2. **Case-insensitive match:** `UPPER(keyword) = UPPER(new_keyword)` → skip
3. **Keyword overlap:** keyword ใหม่เป็น substring ของ keyword เดิม หรือกลับกัน → warn
4. **Semantic similarity (optional, ถ้ามี Vanna/ChromaDB):** vector search → warn ถ้า distance < threshold

### 2.3 Garbage Collector

**ไฟล์:** `app/services/config_gc.py`

Scheduled job (weekly) ที่ตรวจ config ที่ไม่ถูกใช้:

```python
class ConfigGarbageCollector:
    """ตรวจจับ config ที่อาจเป็น "ขยะ" แนะนำให้ admin review"""
    
    def find_unused_mappings(self, days_threshold: int = 30) -> List[Dict]:
        """Mappings ที่ไม่เคยถูก match ใน query logs (ดูจาก keyword ที่ไม่เคยปรากฏในคำถาม)"""
    
    def find_unused_rules(self, days_threshold: int = 30) -> List[Dict]:
        """Rules ที่ไม่เคย trigger"""
    
    def find_conflicting_mappings(self) -> List[Dict]:
        """Mappings ที่ keyword เดียวกันแต่ condition ต่างกัน"""
    
    def find_low_usage_examples(self, min_usage: int = 0) -> List[Dict]:
        """Golden examples ที่ usage_count = 0 หลังจาก N วัน"""
    
    def generate_report(self) -> GCReport:
        """สรุปทั้งหมด → ส่งให้ admin review (หรือ Telegram notification)"""
```

### 2.4 Scheduled Jobs

**ไฟล์:** เพิ่มใน `app/main.py` หรือสร้าง `app/scheduler.py`

| Job | Schedule | ทำอะไร |
|-----|----------|--------|
| `auto_analyze_failures` | ทุก 6 ชั่วโมง | วิเคราะห์ failed queries → suggest fixes |
| `config_gc` | สัปดาห์ละครั้ง | ตรวจ unused/conflicting config → report |
| `apply_high_confidence_fixes` | ทุก 6 ชั่วโมง (หลัง analyze) | Auto-apply fixes ที่ confidence ≥ 0.8 |

### 2.5 Audit Log

ทุกการเปลี่ยนแปลง config (ไม่ว่าจะ manual หรือ auto) ต้อง log:

```sql
CREATE TABLE config_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,  -- add, update, delete, auto_add, auto_update
    table_name TEXT NOT NULL,  -- schema_semantic_mapping, schema_business_rules, etc.
    record_id INTEGER,
    old_value TEXT,  -- JSON
    new_value TEXT,  -- JSON
    source TEXT NOT NULL,  -- manual, admin_agent, auto_analyzer, onboarding
    confidence REAL,  -- สำหรับ auto changes
    source_query_ids TEXT,  -- JSON array of chat_ids ที่ trigger change
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 3. Flow รวม

```
[Every 6 hours]
    │
    ▼
auto_analyze_failures()
    │
    ├── ดึง failed/thumbs_down queries (24h)
    ├── Group similar failures
    ├── LLM diagnose แต่ละ group
    ├── Generate suggested fixes
    │
    ├── For each fix:
    │   ├── dedup_engine.check() → ซ้ำ? → skip + log
    │   ├── confidence ≥ 0.8? → auto-apply + audit_log(source="auto_analyzer")
    │   └── confidence < 0.8? → queue for admin review
    │
    └── Send summary (Admin Agent / Telegram notification)

[Admin reviews pending fixes]
    │
    ├── Approve → apply + audit_log(source="admin_agent")
    ├── Reject → mark as reviewed + log
    └── Edit → modify then apply + audit_log

[Weekly]
    │
    ▼
config_gc.generate_report()
    │
    └── Flag unused/conflicting → notify admin
```

---

## Claude Code Instructions

```
## Prerequisite
- Plan 1 ต้องเสร็จก่อน (Admin Agent + tools)
- Plan 2 Phase 1 ต้องเสร็จก่อน (query-logs มี feedback data)

## ไฟล์ที่ต้องอ่านก่อน
- app/models/chat.py (ChatHistory — generated_sql, feedback_rating)
- app/models/feedback_models.py (UserFeedback)
- app/services/admin_agent.py (จาก Plan 1)
- app/tools/admin/mapping_tools.py (จาก Plan 1)
- app/services/schema_service.py (refresh_cache pattern)

## ลำดับ Implementation

Phase 1: Dedup Engine
  1. สร้าง app/services/dedup_engine.py
  2. Unit tests สำหรับ dedup
  3. Integrate dedup เข้า admin tools (Plan 1) — search ก่อน add

Phase 2: Auto-Analyzer
  4. สร้าง app/services/auto_analyzer.py
  5. สร้าง schemas: AnalysisResult, SuggestedFix
  6. Unit tests ด้วย mock LLM

Phase 3: Audit Log
  7. สร้าง DB migration: config_audit_log table
  8. สร้าง app/services/audit_service.py
  9. Integrate audit ทุกที่ที่มีการ add/update config

Phase 4: Garbage Collector
  10. สร้าง app/services/config_gc.py
  11. Tests

Phase 5: Scheduled Jobs
  12. เพิ่ม APScheduler หรือ Celery Beat jobs
  13. Admin endpoint: GET /admin/auto-analyzer/pending (ดู queue)
  14. Admin endpoint: POST /admin/auto-analyzer/{id}/approve
  15. Admin endpoint: POST /admin/auto-analyzer/{id}/reject

Phase 6: Frontend (optional — ใช้ Admin Agent แทนได้)
  16. หน้า "Auto-Fix Queue" แสดง pending fixes
  17. Approve/Reject buttons

## กฎ
- Auto-apply เฉพาะ confidence ≥ 0.8 เท่านั้น (configurable ใน admin_config)
- ทุกการเปลี่ยนแปลงต้อง audit log ไม่มีข้อยกเว้น
- Dedup ต้อง check ก่อน insert ทุกครั้ง
- GC ไม่ลบเอง — แค่ flag + notify admin
- LLM ใช้ tier="cheap" สำหรับ batch analysis (ประหยัด token)
```

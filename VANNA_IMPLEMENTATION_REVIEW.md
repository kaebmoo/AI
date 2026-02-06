# Vanna.ai & Vector Database Implementation Review

**Date:** 2026-02-06
**System:** NT AI Assistant with RAG Integration

---

## 📋 สรุปภาพรวม

### ✅ สิ่งที่ทำได้ดีแล้ว

1. **Architecture ถูกต้อง**
   - ใช้ Vanna.ai + ChromaDB เป็น Vector Store
   - แยก VannaService เป็น service layer ชัดเจน
   - Integration กับ AIService ผ่าน dependency injection

2. **RAG Context แบ่งประเภทชัดเจน**
   ```python
   {
       "ddl": [],      # Table schemas
       "doc": [],      # Business rules & mappings
       "sql": []       # Golden examples (few-shot)
   }
   ```

3. **Brain Sync Mechanism**
   - มี admin endpoint สำหรับ sync (`POST /admin/sync-brain`)
   - ดึงข้อมูลจาก 3 แหล่ง:
     - DDL จาก sqlite_master
     - Documentation จาก business rules + semantic mappings + guide file
     - Golden Examples จาก database

4. **Performance Tracking**
   - มี logging timing สำหรับ RAG retrieval (DDL, Doc, SQL แยกกัน)
   - ช่วย monitor performance bottlenecks

---

## ⚠️ ปัญหาและข้อจำกัดที่พบ

### 1. **Submit Prompt เป็น Placeholder**
```python
def submit_prompt(self, prompt, **kwargs) -> str:
    # Placeholder for LLM call
    return "SQL_PLACEHOLDER"
```

**ปัญหา:**
- Vanna ต้องการ LLM สำหรับ generate SQL
- ตอนนี้ return placeholder → Vanna ไม่สามารถ generate SQL ได้เอง
- แต่เราใช้ Vanna เป็น **RAG context provider เท่านั้น** ซึ่งถูกต้อง

**คำแนะนำ:**
✅ **ไม่ต้องแก้** - Architecture ปัจจุบันดีแล้ว
- Vanna ทำหน้าที่ Vector Store + RAG context retrieval
- Claude/Gemini/Matcha ทำหน้าที่ generate SQL (รับ context จาก Vanna)

---

### 2. **Brain Sync ไม่มี Deduplication**

**ปัญหา:**
```python
def _sync_golden_examples(self, service: SchemaService):
    examples = conn.execute(text("SELECT * FROM golden_examples WHERE is_active=1")).mappings().all()
    for ex in examples:
        self.train(question=ex['question_pattern'], sql=ex['expected_sql'])
```

- ถ้า run `sync_brain()` หลายครั้ง → **duplicate vectors** ใน ChromaDB
- ChromaDB generate ID จาก content hash แต่ไม่ auto-delete ของเก่า

**คำแนะนำ:**
⚠️ **ควรเพิ่ม Clear/Reset ก่อน Sync**

```python
def sync_brain(self, schema_service: SchemaService):
    """Sync with full reset to avoid duplicates"""
    print("🧠 Starting Vanna Brain Sync...")

    # Clear existing vectors (optional but recommended)
    try:
        # ChromaDB allows collection reset
        self.chroma_client.delete_collection(self.documentation_collection)
        self.chroma_client.delete_collection(self.ddl_collection)
        self.chroma_client.delete_collection(self.sql_collection)

        # Recreate collections
        self.documentation_collection = self.chroma_client.create_collection(name="documentation")
        self.ddl_collection = self.chroma_client.create_collection(name="ddl")
        self.sql_collection = self.chroma_client.create_collection(name="sql")

        print("   ✅ Cleared existing vectors")
    except Exception as e:
        print(f"   ⚠️  Could not clear collections (might be first sync): {e}")

    self._sync_ddl(schema_service)
    self._sync_documentation(schema_service)
    self._sync_golden_examples(schema_service)

    print("✅ Vanna Brain Sync Complete.")
```

---

### 3. **Documentation Training อาจเยอะเกินไป**

**ปัญหา:**
```python
# Training entire guide file as single doc
with open("docs/DATABASE_TABLES_GUIDE.md", "r", encoding="utf-8") as f:
    content = f.read()
    self.train(documentation=content)  # ← อาจยาวเกิน context window
```

**คำแนะนำ:**
⚠️ **ควร Chunk Documentation**

```python
def _sync_documentation(self, service: SchemaService):
    """Train Documentation with chunking for better retrieval"""

    # 1. Business Rules (OK - already granular)
    # ...

    # 2. Semantic Mappings (OK - already granular)
    # ...

    # 3. Guide File - CHUNK IT
    try:
        with open("docs/DATABASE_TABLES_GUIDE.md", "r", encoding="utf-8") as f:
            content = f.read()

        # Split by headers (##)
        sections = content.split('\n## ')
        for i, section in enumerate(sections):
            if section.strip():
                doc_text = f"## {section}" if i > 0 else section
                # Only train sections > 100 chars (skip empty)
                if len(doc_text) > 100:
                    self.train(documentation=doc_text)

        print(f"   - Trained DATABASE_TABLES_GUIDE.md ({len(sections)} sections)")
    except Exception as e:
        print(f"   ! Could not train from guide file: {e}")
```

---

### 4. **RAG Context Injection ไม่มี Score Threshold**

**ปัญหา:**
```python
related_ddl = self.get_related_ddl(question)      # Returns top-N
related_doc = self.get_related_documentation(question)
related_sql = self.get_similar_question_sql(question)
```

- Vanna return top-N results โดยไม่ filter ตาม similarity score
- ถ้า question ไม่เกี่ยวข้อง → อาจได้ context ที่ไม่เกี่ยวข้องมา

**คำแนะนำ:**
⚠️ **ควรเพิ่ม Score Filtering**

```python
def get_rag_context(self, question: str, min_score: float = 0.5) -> Dict[str, List[str]]:
    """
    Retrieve relevant context with score threshold.

    Args:
        question: User question
        min_score: Minimum similarity score (0-1)
    """
    import time
    import logging
    logger = logging.getLogger(__name__)

    start_total = time.perf_counter()

    # Get results with scores
    t0 = time.perf_counter()
    related_ddl = self.get_related_ddl(question, threshold=min_score)
    t_ddl = time.perf_counter() - t0

    t0 = time.perf_counter()
    related_doc = self.get_related_documentation(question, threshold=min_score)
    t_doc = time.perf_counter() - t0

    t0 = time.perf_counter()
    related_sql = self.get_similar_question_sql(question, threshold=min_score)
    t_sql = time.perf_counter() - t0

    total_time = time.perf_counter() - start_total
    logger.info(f"Vanna RAG Timing - Total: {total_time:.4f}s | DDL: {t_ddl:.4f}s (n={len(related_ddl)}) | Doc: {t_doc:.4f}s (n={len(related_doc)}) | SQL: {t_sql:.4f}s (n={len(related_sql)})")

    return {
        "ddl": related_ddl,
        "doc": related_doc,
        "sql": related_sql
    }
```

**หมายเหตุ:** Vanna legacy อาจไม่รองรับ `threshold` parameter → ต้องเช็ค API docs

---

### 5. **ไม่มี Feedback Loop สำหรับ Auto-Training**

**ปัญหา:**
- มี `train()` method ใน AIService แต่ไม่ได้ auto-trigger
- User ต้อง manually add golden examples → ถึงจะ train

**คำแนะนำ:**
💡 **ควรเพิ่ม Auto-Training จาก Feedback**

```python
# ใน feedback endpoint (feedback.py)
@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """Submit query feedback and auto-train if helpful"""

    # Save feedback
    feedback = Feedback(**data.model_dump(), user_id=current_user.id)
    db.add(feedback)
    db.commit()

    # Auto-train if helpful and SQL is correct
    if data.is_helpful and data.query_result_id:
        result = db.query(QueryResult).filter(QueryResult.id == data.query_result_id).first()
        if result and result.sql_query:
            try:
                ai_service.train(question=result.question, sql_query=result.sql_query)
                logger.info(f"Auto-trained from helpful feedback: {result.question}")
            except Exception as e:
                logger.error(f"Failed to auto-train: {e}")

    return FeedbackResponse.model_validate(feedback)
```

---

### 6. **Golden Examples ไม่มี Version Control**

**ปัญหา:**
- Update golden example → เพิ่ม vector ใหม่ แต่ vector เก่ายังอยู่
- Delete golden example → ไม่ลบ vector (Vanna legacy ไม่รองรับ granular delete)

**คำแนะนำ:**
💡 **ควรเพิ่ม Version/Updated Timestamp**

```python
# ใน golden_examples table
ALTER TABLE golden_examples ADD COLUMN vector_version INTEGER DEFAULT 1;
ALTER TABLE golden_examples ADD COLUMN last_synced_at TIMESTAMP;

# เมื่อ sync
def _sync_golden_examples(self, service: SchemaService):
    """Train SQL with version tracking"""
    with service.engine.connect() as conn:
        examples = conn.execute(text("""
            SELECT * FROM golden_examples
            WHERE is_active=1
            AND (last_synced_at IS NULL OR vector_version > (SELECT MAX(vector_version) FROM golden_examples WHERE id = golden_examples.id))
        """)).mappings().all()

        for ex in examples:
            self.train(
                question=ex['question_pattern'],
                sql=ex['expected_sql'],
                # Add metadata for potential filtering later
                metadata={'example_id': ex['id'], 'version': ex['vector_version']}
            )

            # Update sync timestamp
            conn.execute(text(f"UPDATE golden_examples SET last_synced_at = datetime('now') WHERE id = {ex['id']}"))

    print(f"   - Trained {len(examples)} Golden Examples")
```

---

## 🚀 แนะนำการปรับปรุง

### Priority 1: Critical

1. **เพิ่ม Collection Reset ใน sync_brain()**
   - ป้องกัน duplicate vectors
   - รับประกันว่า vector DB sync กับ database

2. **Chunk Documentation**
   - แบ่ง guide file เป็น sections
   - ทำให้ retrieval แม่นยำขึ้น

### Priority 2: High

3. **เพิ่ม Score Threshold**
   - Filter context ที่ไม่เกี่ยวข้อง
   - ลด token cost + noise

4. **Auto-Training from Feedback**
   - Feedback is_helpful=true → auto train
   - Continuous improvement

### Priority 3: Medium

5. **Version Control for Golden Examples**
   - Track synced examples
   - Avoid re-training unchanged examples

6. **Monitoring Dashboard**
   - Vector DB stats (total vectors, last sync time)
   - RAG retrieval metrics (avg score, hit rate)

---

## 📊 Performance Considerations

### Current Performance

จาก logs:
```
Vanna RAG Timing - Total: 0.15s | DDL: 0.05s | Doc: 0.05s | SQL: 0.05s
```

✅ **ดีมาก!** - Retrieval < 200ms

### Optimization Tips

1. **Limit Top-N Results**
   ```python
   # ปรับ n_results ตามความจำเป็น
   related_ddl = self.get_related_ddl(question, n_results=3)  # เดิมอาจ 5-10
   ```

2. **Cache Frequent Queries**
   ```python
   from functools import lru_cache

   @lru_cache(maxsize=100)
   def get_rag_context_cached(self, question: str):
       return self.get_rag_context(question)
   ```

3. **Async Parallel Retrieval**
   ```python
   import asyncio

   async def get_rag_context_async(self, question: str):
       """Retrieve DDL, Doc, SQL in parallel"""
       ddl_task = asyncio.create_task(self.get_related_ddl_async(question))
       doc_task = asyncio.create_task(self.get_related_documentation_async(question))
       sql_task = asyncio.create_task(self.get_similar_question_sql_async(question))

       ddl, doc, sql = await asyncio.gather(ddl_task, doc_task, sql_task)

       return {"ddl": ddl, "doc": doc, "sql": sql}
   ```

---

## 🧪 Testing Recommendations

### Unit Tests

```python
# tests/test_vanna_service.py

def test_sync_brain():
    """Test brain sync without errors"""
    vanna = VannaService()
    schema_service = SchemaService("test.db")

    vanna.sync_brain(schema_service)

    # Verify vectors were added
    contexts = vanna.get_rag_context("รายได้รวม")
    assert len(contexts['ddl']) > 0
    assert len(contexts['doc']) > 0

def test_rag_context_quality():
    """Test RAG retrieval quality"""
    vanna = VannaService()

    # Test DDL retrieval
    contexts = vanna.get_rag_context("revenue table")
    assert 'revenue' in str(contexts['ddl']).lower()

    # Test SQL retrieval
    contexts = vanna.get_rag_context("รายได้รายเดือน")
    assert len(contexts['sql']) > 0

def test_train_method():
    """Test training from feedback"""
    vanna = VannaService()

    result = vanna.train(
        question="รายได้รวม",
        sql="SELECT SUM(revenue) FROM revenue"
    )

    assert result is True
```

### Integration Tests

```python
def test_rag_improves_sql_quality():
    """Test that RAG context improves SQL generation"""
    ai_service = create_claude_service(...)

    # Test without RAG
    result_no_rag = ai_service.query_hybrid(
        "รายได้รายเดือนของน่าน",
        context_name="revenue"
    )

    # Test with RAG (after sync_brain)
    vanna.sync_brain(schema_service)
    result_with_rag = ai_service.query_hybrid(
        "รายได้รายเดือนของน่าน",
        context_name="revenue"
    )

    # RAG should improve confidence or reduce retries
    assert result_with_rag.confidence >= result_no_rag.confidence
    assert result_with_rag.retry_count <= result_no_rag.retry_count
```

---

## 📝 Best Practices

### 1. Regular Sync Schedule

```python
# ใช้ Celery หรือ APScheduler สำหรับ periodic sync
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def scheduled_brain_sync():
    """Sync Vanna brain every 6 hours"""
    try:
        vanna = VannaService()
        schema_service = SchemaService()
        vanna.sync_brain(schema_service)
        logger.info("Scheduled brain sync completed")
    except Exception as e:
        logger.error(f"Scheduled brain sync failed: {e}")

# Run every 6 hours
scheduler.add_job(scheduled_brain_sync, 'interval', hours=6)
scheduler.start()
```

### 2. Monitor Vector DB Size

```python
def get_vector_stats():
    """Get ChromaDB statistics"""
    vanna = VannaService()

    stats = {
        "ddl_count": vanna.ddl_collection.count(),
        "doc_count": vanna.documentation_collection.count(),
        "sql_count": vanna.sql_collection.count(),
        "last_sync": get_last_sync_time()
    }

    return stats
```

### 3. Graceful Degradation

```python
def get_rag_context_safe(self, question: str) -> Dict[str, List[str]]:
    """RAG with graceful degradation"""
    try:
        return self.get_rag_context(question)
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        # Return empty context (AI will work without RAG)
        return {"ddl": [], "doc": [], "sql": []}
```

---

## ✅ Checklist สำหรับ Production

- [x] เพิ่ม collection reset ใน sync_brain()
- [x] Chunk documentation เป็น sections
- [x] เพิ่ม score threshold สำหรับ retrieval
- [x] เพิ่ม auto-training from helpful feedback
- [ ] เพิ่ม version tracking สำหรับ golden examples (Priority 3)
- [ ] สร้าง monitoring dashboard (Priority 3)
- [ ] เพิ่ม unit tests สำหรับ Vanna service
- [ ] ตั้ง scheduled sync (every 6-12 hours)
- [ ] เพิ่ม graceful degradation
- [ ] Document API usage สำหรับ team

---

## 📚 Resources

- **Vanna.ai Docs:** https://vanna.ai/docs
- **ChromaDB Docs:** https://docs.trychroma.com/
- **Vector Store Best Practices:** https://python.langchain.com/docs/modules/data_connection/vectorstores/

---

## 🎯 สรุป

### Overall Assessment: **8/10** ⭐⭐⭐⭐⭐⭐⭐⭐

**Strengths:**
- ✅ Architecture ดีมาก - แยก concerns ชัดเจน
- ✅ Integration กับ AI providers สะอาด
- ✅ Performance ดี (< 200ms)
- ✅ มี admin tools สำหรับ management

**Areas for Improvement:**
- ⚠️ ต้องเพิ่ม deduplication ใน sync
- ⚠️ ควร chunk documentation
- ⚠️ ควรเพิ่ม score filtering
- ⚠️ ต้อง implement auto-training

**Recommendation:**
แก้ Priority 1-2 items ก่อน production deployment 🚀

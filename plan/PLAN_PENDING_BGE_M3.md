# PLAN PENDING — เปลี่ยน Vanna Embedding เป็น BGE-M3

**สถานะ: PENDING DECISION — ห้าม execute จนกว่าเจ้าของโปรเจกต์อนุมัติ**
**Prerequisite (บังคับก่อนตัดสินใจ):** PLAN_F3 Phase B เสร็จ + มี `BASELINE.json`
**ประมาณเวลา (ถ้าอนุมัติ):** 1-2 วัน + เวลา re-sync + เวลา eval เปรียบเทียบ

---

## เหตุผลที่เสนอ

`VannaService` init `ChromaDB_VectorStore` ด้วย `config={'path': ...}` เท่านั้น → Chroma ใช้ embedding default คือ **all-MiniLM-L6-v2 (ONNX)** ซึ่งเป็นโมเดลภาษาอังกฤษ — retrieval กับคำถาม/เอกสารภาษาไทยคุณภาพต่ำ และเป็นคำอธิบายที่สอดคล้องว่าทำไม `distance_threshold` ต้องหลวมถึง 1.8 (L2) เพื่อให้มีผลลัพธ์หลุดมาบ้าง

BGE-M3 เป็นโมเดล multilingual ที่ยืนยันแล้วว่าเหมาะกับภาษาไทย (ผลการประเมินเดียวกับที่เลือกให้ Saraphan) รัน local ได้ ตรงเงื่อนไข on-premise

## ต้นทุน/ความเสี่ยงที่ต้องชั่งก่อนอนุมัติ

| ประเด็น | รายละเอียด |
|---------|-----------|
| Dependency ใหม่ | `sentence-transformers` (+ torch) — ก้อนใหญ่ ~2GB+ dependencies |
| Model weight | BGE-M3 ~2.3GB — เครื่อง on-prem ต้อง pre-download (HF offline) |
| Latency | embed คำถามต่อ query บน CPU ~หลักร้อย ms (ต้องวัดจริงบนเครื่องเป้าหมาย) — บวกเข้า RAG stage ทุก request |
| Memory | โมเดลค้างใน RAM ~2-3GB ต่อ process |
| Migration | ต้องลบและ re-embed vector ทั้งหมด (sync_brain) — space เดิมใช้ต่อไม่ได้ |
| Threshold | ค่า 1.8 เดิมใช้ไม่ได้ ต้อง calibrate ใหม่ทั้งชุด |
| ทางเลือกที่เบากว่า | `paraphrase-multilingual-MiniLM-L12-v2` (~470MB) คุณภาพไทยต่ำกว่า M3 แต่เบากว่ามาก — ถ้า latency/RAM เป็นข้อจำกัด ให้เทียบสองตัวใน Phase C พร้อมกัน |

## เกณฑ์ตัดสินใจ Go/No-Go (วัดด้วย eval harness F3-B)

- **Go** ถ้า: execution accuracy บน golden set ดีขึ้น ≥ 10 จุด (percentage points) หรือ retrieval hit-rate (golden SQL ที่เกี่ยวข้องติด top-k) ดีขึ้นชัดเจน โดย latency P95 ต่อ query เพิ่มไม่เกิน 500ms
- **No-Go** ถ้า: accuracy ดีขึ้น < 5 จุด หรือ latency/RAM เกินรับได้ → พิจารณาทางเลือกเบา หรือคงเดิมแล้วไปลงแรงที่ golden examples/mappings แทน

---

## แผน implement (พร้อมใช้เมื่ออนุมัติ)

### READ FIRST
- `app/services/vanna_service.py` ทั้งไฟล์ (สภาพ ณ ตอนนั้น)
- chromadb เวอร์ชันที่ติดตั้ง: interface `EmbeddingFunction` (`__call__(self, input)` และ requirement เรื่อง `name()`) — **ดูจาก package จริง เวอร์ชัน 1.x เปลี่ยน interface บ่อย**
- vanna `ChromaDB_VectorStore` source: config รับ `embedding_function` ได้ตรง ๆ หรือไม่ / collections ถูกสร้างตรงไหน
- `app/config.py`, `scripts/` ที่เรียก sync_brain

### Phase A — Config + Embedding class

1. `requirements.txt`: เพิ่ม `sentence-transformers` (pin version) — ติดตั้งแล้ววัดขนาด/เวลา install กระทบ CI (อาจต้องแยกออกจาก requirements-ci)
2. `app/config.py`:
   - `VANNA_EMBEDDING: str = "default"` (`default` | `bge-m3`)
   - `VANNA_EMBEDDING_MODEL_PATH: str = ""` (path local model สำหรับ offline; ว่าง = ดึงจาก HF ครั้งแรก)
   - `VANNA_DISTANCE_THRESHOLD` คงไว้ แต่ semantics จะเปลี่ยนตาม space (ดู Phase B)
3. สร้าง `app/services/embeddings.py`:

```python
class BGEM3EmbeddingFunction:          # implement ตาม chromadb interface จริง
    def __init__(self, model_path: str = ""):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_path or "BAAI/bge-m3")
    def __call__(self, input):          # signature ตาม chromadb ที่ติดตั้ง
        return self._model.encode(list(input), normalize_embeddings=True).tolist()
```

โหลดโมเดลแบบ lazy singleton ระดับ process (โมเดลใหญ่ ห้าม init ต่อ request)

### Phase B — Wire เข้า VannaService + cosine space

1. `VannaService.__init__`: ถ้า `VANNA_EMBEDDING == "bge-m3"` ส่ง embedding function เข้า collections — วิธีขึ้นกับ vanna version: ถ้า `ChromaDB_VectorStore` config รองรับ `embedding_function` ใช้ทางนั้น; ถ้าไม่ ให้ override การสร้าง collection (get_or_create_collection พร้อม `embedding_function=` และ `metadata={"hnsw:space": "cosine"}`)
2. **เปลี่ยน distance space เป็น cosine** เมื่อใช้ bge-m3 (normalize แล้ว cosine เหมาะกว่า L2) → collection ต้องถูกสร้างใหม่พร้อม metadata นี้ — `sync_brain` ลบ collection อยู่แล้ว แต่ต้องแก้จุด re-create ทั้งใน `sync_brain` และที่อื่น (grep `get_or_create_collection`) ให้ส่ง embedding_function + metadata **ทุกจุด** ครบ ไม่งั้น space จะปนกัน
3. Threshold ใหม่: cosine distance = 1 − cos_sim; เริ่มที่ 0.45 แล้ว calibrate — เพิ่ม script `scripts/eval/tune_vanna_threshold.py`: วนคำถาม golden, log distance ของเอกสารที่ควรติด/ไม่ควรติด, เสนอ threshold ที่ recall/precision สมดุล
4. ไฟล์ Chroma แยก path ตาม embedding: `VANNA_CHROMA_PATH` เดิม + suffix `_bgem3` เมื่อใช้โหมดใหม่ → **rollback = สลับ config กลับ** ข้อมูลเดิมไม่ถูกทำลาย

### Phase C — Migration + วัดผล

1. Backup dir chroma เดิม (copy ทั้ง folder) ก่อนทุกอย่าง
2. ตั้ง `VANNA_EMBEDDING=bge-m3` → รัน sync_brain เต็ม (จับเวลา — corpus ทั้งหมดต้อง embed ใหม่)
3. รัน eval (F3-B) config เดิมทุกอย่างยกเว้น embedding → เทียบ `BASELINE.json`
4. วัด latency: RAG stage ต่อ query (มี timing log อยู่แล้ว / trace จาก F7) ก่อน-หลัง
5. (แนะนำ) รัน eval กับ `paraphrase-multilingual-MiniLM-L12-v2` อีกชุดในคราวเดียว — ได้ตาราง 3 ทางเลือกให้ตัดสินใจครั้งเดียวจบ
6. สรุปผลลง `plan/RESULT_BGE_M3.md`: ตาราง accuracy / hit-rate / latency / RAM → ตัดสิน Go/No-Go ตามเกณฑ์ข้างบน

### Acceptance Criteria (เมื่อ execute)

- [ ] สลับ `VANNA_EMBEDDING` ไป-กลับได้โดยไม่พังและไม่ทำลายข้อมูลอีกฝั่ง
- [ ] ผล eval เปรียบเทียบครบ 2-3 ทางเลือก + latency + RAM ใน `RESULT_BGE_M3.md`
- [ ] ถ้า Go: threshold ใหม่ถูก calibrate ด้วย script ไม่ใช่เดา, `IMPLEMENTATION_STATUS.md` อัปเดต
- [ ] ถ้า No-Go: revert config, เก็บผลการทดลองไว้เป็นหลักฐานการตัดสินใจ

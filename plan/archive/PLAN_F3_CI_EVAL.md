# PLAN F3 — CI (Phase A) + NL→SQL Eval Harness (Phase B)

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Phase A Prerequisite:** ไม่มี — ทำเป็นอย่างแรกของทั้งชุด (safety net)
**Phase B Prerequisite:** PLAN_F1 เสร็จ
**ประมาณเวลา:** A = 0.5 วัน, B = 1-2 วัน
**หมายเหตุ:** Phase B คือ prerequisite ของการตัดสินใจ PLAN_PENDING_BGE_M3

## READ FIRST

- `tests/conftest.py` ทั้งไฟล์ — ดูว่า fixture ต้องการ env อะไร (โดยเฉพาะ `SECRET_KEY` ซึ่ง `app/config.py` บังคับต้องมี ไม่งั้น Settings raise ตั้งแต่ import)
- `requirements.txt`
- โครงสร้าง `tests/unit/`, `tests/integration/` (list ชื่อไฟล์พอ)
- `app/models/feedback_models.py` (โครง `golden_examples`)
- `app/services/query_engine.py`, `app/api/deps.py` (สำหรับ Phase B)

---

## Phase A — GitHub Actions CI ขั้นต่ำ

**เป้าหมาย:** ทุก push/PR ต้องผ่าน lint (เฉพาะ error ร้ายแรง) + pytest ก่อน merge — ไม่ตั้งเป้า lint สะอาดทั้ง repo ในแผนนี้ (จะบล็อกทุกอย่าง)

### A.1 สร้าง `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SECRET_KEY: ci-test-secret-key-not-for-prod
      ENVIRONMENT: development
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pip install ruff
      # เฉพาะ error ที่พังจริง: syntax error + undefined names + unused import ร้ายแรง
      - run: ruff check app mcp_servers --select E9,F63,F7,F82
      - run: pytest tests/unit tests/integration -q --maxfail=5
```

### A.2 สิ่งที่ต้องตรวจ/แก้ให้ CI เขียว

1. รัน pytest local ด้วย env สะอาด (unset ตัวแปรทุกตัวยกเว้น SECRET_KEY) — หา test ที่พึ่ง `.env` จริงหรือ API key จริง แล้ว mark `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), ...)` หรือ mock ให้เรียบร้อย ห้ามให้ CI ต้องมี key จริง
2. tests ที่ import vanna/chromadb: ต้อง gracefully skip ถ้า import fail (โค้ด production มี guard แล้ว — tests ต้องมีเช่นกัน)
3. ถ้า install ช้าเกิน 5 นาที: แยก requirements-ci.txt ตัด chromadb/vanna ออก + skip tests ที่ต้องใช้ (จดการตัดสินใจใน commit message)
4. เพิ่ม badge ใน `README.md` (optional)

### A.3 Acceptance (Phase A)

- [ ] CI เขียวบน main โดยไม่แก้พฤติกรรม production code (แก้ได้เฉพาะ tests/markers)
- [ ] PR ทดสอบหนึ่งอันที่จงใจใส่ syntax error → CI แดง

---

## Phase B — Eval Harness: Execution-Match Accuracy

**เป้าหมาย:** วัด accuracy ของ NL→SQL ด้วยการ**เทียบผลลัพธ์ execution** (ไม่ใช่เทียบ SQL string) บนชุด golden examples — ใช้เป็น baseline ก่อน/หลังทุกการเปลี่ยน prompt, โมเดล, embedding

**ข้อจำกัดโดยธรรมชาติ:** รันแล้วเสียเงิน LLM จริง → **ไม่รันอัตโนมัติทุก push** — รันแบบ manual (`workflow_dispatch` หรือ local script) เท่านั้น

### B.1 สร้าง `scripts/eval/run_eval.py`

Flow ต่อ 1 example:
1. โหลด golden examples ที่ `is_active=1` จาก DB (`question_pattern`, `expected_sql`, `category` → context)
2. รัน expected_sql ตรงกับ business DB (read-only connection) → `expected_rows`
3. รัน `QueryEngine.query(question, context=category, provider=<fixed>)` จริง → ได้ `generated_sql`, `actual_rows` (ใช้ MCP client แบบ `async with mcp_client.connected()` เหมือน script ทั่วไป; **ต้องปิด query cache** — ส่ง history dummy หรือเพิ่ม flag `use_cache=False` ใน engine ถ้า F1 ทำให้ history-skip ใช้ได้ ให้ใช้ทางนั้น)
4. เทียบผล:
   - normalize: sort rows (ตาม tuple ของทุกค่า), round float ที่ tolerance 1e-6, ตัด column ที่เป็น alias ต่างชื่อแต่ค่าตรง → เทียบเป็น multiset ของ value-tuples (เทียบตามตำแหน่ง column หลัง sort ชื่อ column ถ้าจำนวน column เท่ากัน; ถ้าจำนวนไม่เท่า = fail)
   - ผลลัพธ์: `exact_match` / `mismatch` / `generation_failed` / `execution_failed`
5. เก็บ per-example record: question, context, generated_sql, status, latency, tokens

### B.2 Output

- `eval_results/eval_<YYYYMMDD_HHMM>_<provider>.json` (raw ทุก example)
- `eval_results/eval_<...>.md` — สรุป: accuracy รวม, per-context, รายการ fail พร้อม SQL เทียบกัน
- ไฟล์ `eval_results/BASELINE.json` — copy ของ run ที่ประกาศเป็น baseline (commit เข้า repo; ไฟล์ run รายครั้งเข้า `.gitignore` ยกเว้น baseline)
- CLI options: `--provider`, `--context`, `--limit N` (รันบางส่วนตอน dev), `--compare BASELINE.json` (พิมพ์ diff: ข้อที่เคยผ่านแล้วตก = regression, ต้อง highlight)

### B.3 GitHub Actions (optional, ทำถ้า secrets พร้อม)

workflow `eval.yml` แบบ `workflow_dispatch` เท่านั้น รับ input provider — ถ้า org ยังไม่สะดวกใส่ API key ใน GitHub secrets ให้ข้าม (รัน local พอ) และจดไว้

### B.4 ข้อควรระวัง

- expected_sql บางอันอาจพังกับข้อมูลปัจจุบัน (data เปลี่ยน) — สถานะ `golden_broken` แยกต่างหาก ห้ามนับเป็นความผิดของโมเดล และ report รายการนี้ให้ admin แก้ golden
- ห้าม train/แก้ DB ระหว่าง eval run
- คำถามที่ผลลัพธ์ถูกได้หลายรูปแบบ (เช่น ต่างกันแค่ ORDER BY ที่คำถามไม่ระบุ) — การ sort rows ก่อนเทียบจัดการให้แล้ว จด edge case ที่เจอจริงลง FIX_NOTES

### B.5 Acceptance (Phase B)

- [ ] `python -m scripts.eval.run_eval --limit 5` รันจบ ได้ json+md
- [ ] รันเต็มชุดกับ provider default หนึ่งครั้ง → commit `BASELINE.json` + md report
- [ ] `--compare` แสดง regression ได้ (ทดสอบโดยแก้ golden หนึ่งข้อชั่วคราว)
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (Testing section: มี eval harness แล้ว + ตัวเลข baseline)

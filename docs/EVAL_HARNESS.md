# NL→SQL Eval Harness (F3-B)

**วันที่:** 2026-07-12
**Script:** `scripts/eval/run_eval.py`
**Plan:** `plan/archive/PLAN_F3_CI_EVAL.md` (Phase B)

## จุดประสงค์

วัด accuracy ของระบบ NL→SQL ด้วยการ**เทียบผลลัพธ์ execution** (execution-match) —
ไม่ใช่เทียบ SQL string — บนชุด golden examples เดียวกันทุกครั้ง
ใช้เป็น baseline ก่อน/หลังทุกการเปลี่ยน prompt, โมเดล, embedding หรือ knowledge
เพื่อจับ regression ได้เป็นตัวเลข ไม่ใช่ความรู้สึก

> **ข้อจำกัดสำคัญ:** ทุก example เรียก LLM จริง = เสียเงินจริง → **รันแบบ manual เท่านั้น**
> ห้ามผูกกับ push/PR อัตโนมัติ

## วิธีรัน

```bash
# ทดลองสั้น ๆ ตอน dev (5 ข้อแรก)
python -m scripts.eval.run_eval --limit 5

# ระบุ provider (default = admin default provider)
python -m scripts.eval.run_eval --provider matcha

# รันเฉพาะ context เดียว (filter ตาม category ของ golden)
python -m scripts.eval.run_eval --context feed_revenue

# รันเต็มชุด + เทียบกับ baseline (มี regression → exit code 1)
python -m scripts.eval.run_eval --compare eval_results/BASELINE.json
```

CLI options ทั้งหมด: `--provider`, `--context`, `--limit N`, `--compare <path BASELINE.json>`

## แหล่งข้อมูล golden examples

- โหลดจากตาราง `golden_examples` ใน config DB (เฉพาะ `is_active=1`) —
  ใช้ field `question_pattern`, `expected_sql`, `category`
- `category` ถูกใช้เป็น context ตอน generate ถ้าชื่อตรงกับ `schema_contexts` ที่ active
  (ไม่ตรง → ปล่อยให้ระบบ auto-route)
- golden ของ context `feed_revenue` ถูก generate อัตโนมัติจาก control totals ของ DataFeed
  (ดู `docs/DATAFEED_INTEGRATION.md`)

## Flow ต่อ 1 example

1. รัน `expected_sql` ตรงกับ business DB (read-only) → `expected_rows`
   - ถ้า expected_sql รันไม่ผ่าน (data drift) → สถานะ `golden_broken` —
     **ไม่นับเป็นความผิดของโมเดล** admin ต้องไปแก้ golden
2. ล้าง query cache (`clear_query_cache()`) — ห้ามให้ cache ตอบแทน LLM ระหว่าง eval
3. เรียก `QueryEngine.query()` จริงผ่าน MCP client (timeout 180s ต่อข้อ) → `generated_sql`, `actual_rows`
4. เทียบผลลัพธ์ → ได้สถานะหนึ่งใน: `exact_match` / `value_match` / `mismatch` /
   `generation_failed` / `execution_failed` / `golden_broken`
5. เก็บ record: question, category, SQL ทั้งสองฝั่ง, status, latency, tokens

## Metrics: strict match vs value match

การเทียบ normalize ก่อนเสมอ: sort rows เป็น multiset ของ value-tuples,
float เทียบด้วย tolerance 1e-6, int/float ถือว่าชนิดเดียวกัน —
ดังนั้น ORDER BY ที่ต่างกันไม่ทำให้ตก

| สถานะ | เงื่อนไข |
|---|---|
| `exact_match` | **ค่าตรง และ ชื่อคอลัมน์ตรง** (case-insensitive) — นี่คือ headline accuracy (strict) |
| `value_match` | ค่าตรงทุกแถว แต่ชื่อคอลัมน์ (alias) ไม่ตรง เช่น `revenue` vs `"รายได้รวม"` |
| `mismatch` | ค่าไม่ตรง (จำนวนแถว/จำนวนคอลัมน์/ค่าต่างกัน) |
| `generation_failed` | LLM generate SQL ไม่สำเร็จ |
| `execution_failed` | SQL ที่ generate รันแล้ว exception / timeout |
| `golden_broken` | expected_sql ของ golden เองพัง — ถูกตัดออกจากตัวหาร (scored) |

**ทำไมแยก value_match ออกจาก strict:** ค่าเท่ากันภายใต้ชื่อคอลัมน์ต่างกัน
อาจยังเป็น projection ที่ผิด (เช่น `SUM(x)` ที่ alias เป็น measure ผิดตัว)
จึงรายงานแยกให้**ตรวจด้วยตา** ไม่ให้เข้าไปเป่า headline accuracy —
report มีทั้ง `accuracy` (strict) และ `accuracy_incl_value_match` ให้ดูคู่กัน

## Output — eval_results/

ทุก run เขียน 2 ไฟล์ลง `eval_results/`:

- `eval_<YYYYMMDD_HHMM>_<provider>.json` — summary + raw record ทุกข้อ
- `eval_<YYYYMMDD_HHMM>_<provider>.md` — สรุปอ่านง่าย: accuracy รวม, ตาราง per-context,
  รายการ value_match (ให้ตรวจ projection), รายการ fail พร้อม SQL expected/generated เทียบกัน,
  รายการ golden_broken (งานของ admin)

ไฟล์ run รายครั้งอยู่ใน `.gitignore` (`eval_results/*`) — **commit เฉพาะ**
`eval_results/BASELINE.json` และ `BASELINE.md`

## Baseline ปัจจุบัน (2026-07-11, provider: default)

- **Strict accuracy: 3/51 = 5.88%** | รวม value_match: 35.29%
  (value_match 15 ข้อ, golden_broken 12 ข้อ — ถูกตัดออกจากตัวหาร)
- value_match 15 ข้อ ส่วนใหญ่คือ context `feed_revenue` (14/14 ค่าถูกหมด แต่ alias ไม่ตรง golden)
- ตัวเลข strict ต่ำเป็นธรรมชาติของเกณฑ์: golden เก่าจำนวนมากตั้ง alias เป็นอังกฤษ
  ขณะที่โมเดลตั้ง alias ไทย — ดูรายละเอียดใน `eval_results/BASELINE.md`

### วิธีอัปเดต baseline

1. รันเต็มชุดกับ provider ที่ต้องการประกาศเป็น baseline
2. ตรวจ report: value_match ต้องผ่านการตรวจ projection ด้วยตา, golden_broken ต้องส่งให้ admin แก้
3. copy ไฟล์ run เป็น `eval_results/BASELINE.json` + `BASELINE.md` แล้ว commit
4. อัปเดตตัวเลขใน `IMPLEMENTATION_STATUS.md` (Testing section)

## ความสัมพันธ์กับ CI

- CI ปัจจุบัน (`.github/workflows/ci.yml`) รันเฉพาะ ruff + pytest — **ไม่รัน eval**
  เพราะ eval เรียก LLM จริง (ต้องมี API key + มีค่าใช้จ่าย)
- ตามแผน F3-B ข้อ B.3: workflow `eval.yml` แบบ `workflow_dispatch` (กดรันมือ) เป็น optional —
  ยังไม่ได้สร้าง เพราะยังไม่ใส่ API key ใน GitHub secrets → รัน local แทน
- Gate ที่ใช้จริงคือ `--compare eval_results/BASELINE.json` ก่อน merge การเปลี่ยนแปลง
  ที่กระทบ NL→SQL: ข้อที่เคยเป็น `exact_match` แล้วตก = **regression** → script exit 1

## ข้อควรระวัง

- ห้าม train / แก้ config DB / import ข้อมูล ระหว่าง eval run
- คำถามที่ตอบถูกได้หลายรูปแบบ (ต่างแค่ ORDER BY) — การ sort rows จัดการให้แล้ว
  แต่ edge case ใหม่ที่เจอจริงให้จดลง FIX_NOTES

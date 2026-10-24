# RESULT — metric ที่ประกาศเป็นข้อมูล (ขั้น 0 + ขั้น 1 ของ `plan/RESEARCH_DECLARED_METRICS.md`) — 2026-10-24

**สถานะ:** ✅ ขั้น 0 (NT-Report) + ขั้น 1 (AI PoC) เสร็จบน branch `ai/delegate-metrics` ของทั้งสอง repo · วัดบนสำเนาแล้ว · **ยังไม่ขึ้นของจริง, ไม่ push, ไม่แตะ `main`**
**วิธีทำ:** `/delegate` — Claude วางแผน/ตรวจรับ, Codex เขียน code ทั้งหมด (NT-Report 4 รอบ, AI 9 รอบ) ใน worktree นอก repo:
`/Users/seal/Documents/GitHub/_worktrees/NT-Report-metrics` และ `/Users/seal/Documents/GitHub/_worktrees/AI-metrics` (บันทึก run: `.ai/20261024-0044/`, `.ai/20261024-0104/` ในแต่ละ worktree)
**ข้อตัดสินของเจ้าของที่ใช้:** D-1..D-7 ตามข้อเสนอในรายงาน research (2026-10-24)

---

## 1. สรุป

| | ก่อน (code `main` a918164 + contract 1.5.0) | หลัง (branch, slice 06) |
|---|---|---|
| **"ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร"** (audit #382 เดิมตอบ 24.41M = EBT ปกติ) | 2/8 question-runs (ถูกบ้างเป็นครั้งคราว) | **8/8** = 54,469,208.99 ตรงเจ้าของทุกสตางค์ |
| ชุด ebt 14 ข้อ (รวม P11–P14 ใหม่) | 19/28 | 20/28 (P12 คำพิมพ์ผู้ใช้จริง: ก่อน ✓✗ → หลัง ✓✓) |
| ชุด real 15 / revenue 10 / expense 10 / sales 10 (context ไม่มี metric → prompt เท่าเดิมทุกไบต์) | 18/30 · 18/20 · 16/20 · 17/20 | 18/30 · 18/20 · 16/20 · 18/20 (ต่างกัน = ความแปรปรวนของ LLM) |
| **รวม 63 ข้อ × 2 รอบ (code สุดท้าย)** | **90/126** | **98/126** — คู่ที่ต่างกัน: หลังถูก/ก่อนผิด 10, ก่อนถูก/หลังผิด 2, **McNemar exact p = 0.039** |
| เวลาต่อคำถาม ebt (รอบ 4) | เฉลี่ย 7.9 s | 6.8 s (ข้อที่ compile ไม่เรียก pass 2); น่าน 16.2 → 9.7 s |

ตลอดการวัด: compile สำเร็จ 32 คำตอบ, compile ล้ม 0, pass 1 ทั้งหมด 313 ครั้ง · ค่าตอบจาก SQL ที่ code ประกอบ **ตรงกับสูตรของเจ้าของทุกครั้งที่เดินทางนี้**
สิ่งที่ยังผิดเหมือนเดิมทั้งสองฝั่ง (ไม่ใช่เรื่อง metric): ebt P05 "สัดส่วนต้นทุนต่อรายได้" (ยังไม่มี metric ประกาศ → ตอบถูกแต่ไม่บอกฐาน), P06/P14 "สายงานไหน…สูงกว่า" (ทั้ง LLM และ compiler ให้ LIMIT 1 แต่เฉลยอยาก 2 แถว), P09 ป้าย "2 สายงานขาย", real P10–P12/P14 (มีมาก่อน)

## 2. ที่สร้าง

### NT-Report (branch `ai/delegate-metrics`, base `9411609` = main, 3 commit, ยังไม่ rebuild dist จริง)
| commit | เนื้อหา |
|---|---|
| `001c0c3` | `domains.py`: คอลัมน์ `hr_expense`, `ebt_ex_personnel` (+`_month`) ใน `fact_ebt_division_monthly` / `fact_ebt_total_monthly` (หมวด 1–3 ชื่อตรง + `GROUP_0='02.ค่าใช้จ่าย'` + ADDITIVE, ไม่บวก `-ER`), control_totals +4, col_meta, กฎ `ebt_ex_personnel_definition`; **contract ebt 1.5.0** (MINOR); CHANGELOG; `test_ebt_totals` ขยาย |
| `2129e39` | `metrics:` ใน contract — `ebt`, `ebt_excluding_personnel`, `ebt_margin` (terms + expr + dimensions + official_scope/official_total + reference) · `gen_contract` ส่งผ่าน · SCHEMA.md แสดง · `test_metrics_contract.py` ตรวจว่าทุกการอ้างมีจริง · **สืบทอด (`extends`) เฉพาะโครง**: dataset/period/dimensions/official_scope + merge terms — ไม่สืบทอด expr/name/synonyms/unit/official_total/reference |
| `541b3e1` | `portal_questions.py` +4 ข้อ (P11–P14) EBT ไม่รวมบุคลากร (รวม/สายงาน × เดือน/สะสม; P12 = ถ้อยคำผู้ใช้จริง) |
build ใน worktree: reconcile PASS 21 งวด × 10 measure; control_totals 202609 `ebt_ex_personnel` = **5,799,842,156.45** (= 570,852,985.68 + 5,228,989,170.77) · test `tools/feed` 34 passed

### AI (branch `ai/delegate-metrics`, base `a918164` = main, 6 commit)
| commit | เนื้อหา |
|---|---|
| `ff886c0` | ตาราง `schema_metrics` (ProvenanceMixin) + `scripts/migrate_schema_metrics.py` (idempotent) + `datafeed_knowledge.sync_metrics` (ตรวจกับ datasets ของ contract, เขียนผ่าน `_declare`, ถอนด้วย `OWN`, ไม่มีตาราง = ข้าม) + `KNOWLEDGE_TABLES`/`DECLARED_FIELDS`; `migrate_knowledge_provenance` ข้ามตารางที่ยังไม่มี |
| `94a513d` | `app/services/ai/metric_compiler.py`: `load_metrics` (active), `resolve` (โครงเท่านั้น), `match_metrics` (คำพ้องยาวสุดก่อน), `metric_catalog`/`metric_note` (ชื่อเท่านั้น ไม่มีสูตร — D-5), `supports`, `compile` (ไวยากรณ์เลขคณิตปิด, `COALESCE(SUM(CASE WHEN …))` ต่อ term, official_scope/official_total ตาม D-3, ผ่าน `check_select`, รันได้ทั้ง DuckDB/SQLite); fixture `tests/fixtures/ebt_metrics_1_5_0.yaml` |
| `806d90d` | two-pass: `INTENT_SCHEMA.metric_id`, pass 1 เห็นรายการ metric + บรรทัดที่ code จับได้, `metric_compiler.plan()`, **รูปที่รองรับ (aggregation/ranking งวดเดียว) → ใช้ SQL ที่ compile แทน pass 2 (D-4)**, guard/validate/execute/explain เดิม, `QueryResult.metric`; context ที่ไม่มี metric prompt เท่าเดิมทุกไบต์ |
| `063bc9f` | `plan()`: mapping ที่ keyword ไม่อยู่ในคำถาม (pass 1 คัดลอก mapping id 57 "สายงาน" มาเอง) ไม่บล็อก |
| `6593eed` | `plan()`: filter ของ pass 1 บนคอลัมน์งวด (`time_key = 202609`) = period hint ไม่ใช่ตัวตัดสิทธิ์; `metric_id` ที่เป็นชื่อคอลัมน์ (`ebt_ex_personnel`) → metric ของมัน |
| `e745964` | `plan()`: mapping ที่ keyword เป็นชื่อ/คำพ้องของ metric ที่เลือก (pass 1 สะท้อน catalog กลับมาเป็น mapping) ไม่บล็อก |
pytest 1240 → **1412 passed**, 3 skipped (env แบบ CI, python 3.14) · ruff ผ่าน

**บทเรียนจาก pass 1 ของจริง (gpt-4.1-mini) — เจอหลังวัดเท่านั้น (unit test จำลองไม่เห็น):** (1) ใส่งวดลง `filters` เสมอทั้งที่มี `time_range`; (2) เขียน `metric_id` เป็นชื่อคอลัมน์ของ official_total 4/6 ครั้ง; (3) สะท้อนชื่อ metric ใน catalog กลับมาเป็น `matched_mappings`; (4) คัดลอก mapping กลาง "สายงาน" แม้คำถามไม่มีคำนี้ — ทั้ง 4 ข้อแก้ใน code ด้าน `plan()` (ไม่แก้ prompt) และ regression ครบใน `tests/unit/test_metric_intent.py`

## 3. การวัด (บนสำเนา — ไม่แตะของจริง)
- server ซ้อม 2 ตัว: **หลัง** = worktree AI-metrics (8001), **ก่อน** = worktree ที่ `a918164` (8002); แต่ละตัวมีสำเนา config.db/app.db/Chroma ของตัวเอง (`.ai/db/{after,before}`), key ซ้อม id 5 (workspace nt-report), `register_file_source --domain ebt` ชี้ dist 1.5.0 ที่ build ใน worktree NT-Report (ฝั่งก่อนก็ได้ contract 1.5.0 + กฎข้อความใหม่ → ความต่างที่วัดคือ "code ประกอบ SQL" ไม่ใช่ความรู้)
- ชุด: ebt 14 + **น่าน 4** (oracle จากไฟล์ feed ที่เจ้าของยืนยัน) + real 15 + revenue/expense/sales 10 = 63 ข้อ; **restart server ก่อนทุกรอบ** (query cache 30 นาที); 5 รอบ (ฝั่งหลัง: รอบ 1–2 slice 04, รอบ 3 slice 05, รอบ 4–5 slice 06 = ตารางใน §1) · ตัวให้คะแนน `scripts/eval/run_portal_questions.py` (ตัวเลข + ยอดในข้อความ + ปี + ฐาน) · ตัวรวม `.ai/eval/aggregate.py` (จับคู่รอบเดียวกัน, McNemar exact)
- ทุกรอบ (ฝั่งหลังรวม code กลางทาง): ก่อน 228/311, หลัง 237/311; คู่ต่าง 18 vs 9, p = 0.12 — code สุดท้าย 2 รอบ: 90 vs 98 /126, p = 0.039
- ผลลัพธ์/log ทั้งหมด: `_worktrees/AI-metrics/.ai/eval/` (`results/*.json`, `round*_*.log`, `server_*.log`, `final/`)

## 4. ลำดับขึ้นของจริง (ยังไม่ทำ — ให้เจ้าของสั่ง)
1. **AI ก่อน contract เสมอ** (CHANGELOG 2026-10-22): merge `ai/delegate-metrics` → `main` ของ AI · backup `config.db` · `venv/bin/python scripts/migrate_schema_metrics.py` (สร้างตาราง; idempotent; server เริ่มได้แม้ยังไม่รัน แต่ sync จะข้าม metric) · restart (`git log <running>..HEAD` ก่อน — มี 6 commit ของงานนี้ + ของคนอื่น)
   — ตรวจแล้ว: code เดิมอ่าน contract 1.5.0 ที่มี key `metrics` ได้ (ฝั่ง "ก่อน" ลงทะเบียน 1.5.0 ผ่าน gate ครบ)
2. NT-Report: merge → `main` · `python tools/feed/build_feed.py --domain ebt` (ต้อง 1.5.0 ให้ dist มี `ebt_ex_personnel`) · publish · `python tools/feed/portal_questions.py --domain ebt`
3. AI: `python -m scripts.datafeed.register_file_source --domain ebt --source <NT-Report>/DataFeed/dist` (ตารางได้คอลัมน์ใหม่ + sync metrics 3 แถว `declared`) · rebuild keyword index ของ feed_ebt ถ้าต้องการ
4. ตรวจบนของจริง: "ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร" → 54,469,208.99; log มี `Metric compiled: ebt_excluding_personnel`
ถอยกลับ: AI `git checkout <commit เดิม>` (ตารางใหม่อยู่ได้ ไม่มีใครอ่าน) · NT-Report คืน contract 1.4.4 + dist เดิม (AI re-sync เอง; แถว metrics ถูกถอนเพราะ contract ไม่ประกาศ)

## 5. ที่ยังค้าง / ข้อเสนอถัดไป (ขั้น 2 ของแผน)
- metric เพิ่ม: `cost_ratio` (P05), `hr_expense` เป็น metric ตรง ๆ; ratio สองงวด / YoY (compile ×2 + คิดใน code แบบ `multi_context.compute`)
- ranking "สายงานไหน…สูงกว่า": เฉลยอยากเห็นทั้งสองสายงาน แต่ทั้ง LLM และ compiler ให้ LIMIT 1 — ตัดสินว่า "เทียบ" = คืนทุกค่าของมิติ (ทำที่ `plan()` เมื่อ intent ranking + dimension และคำถามไม่ระบุจำนวน)
- expression → pass 2 + guard สำหรับรูปที่ยังไม่ compile (trend/detail) · ค่าอ้างอิงระดับหน่วยย่อยใน NT-Report (D-6(b)) ยังไม่ทำ — ชุด "น่าน" ใช้ oracle จากไฟล์ตรง
- mapping id 57 "สายงาน" ยังทำให้ LLM ใส่ `division LIKE '%สายงาน%'` ในทางเดิม (ความรู้ของ admin ไม่ใช่ code)
- 3 test ที่ skip = chart renderer เดิม; `test_fixture_matches_the_live_contract_when_present` skip เมื่อไม่มี worktree NT-Report
- สำเนา DB / key ซ้อม ลบแล้วหลังวัด (ดู §6)

## 6. เก็บกวาด
server ซ้อมหยุดแล้ว · ลบ `.ai/db/*` (สำเนา config/app/Chroma) และ `.ai/eval/key_*.txt` ของ worktree AI-metrics · worktree ทั้งสาม (`NT-Report-metrics`, `AI-metrics`, `AI-before`) ยังอยู่ให้ตรวจ diff — ลบด้วย `git worktree remove` เมื่อ merge แล้ว · ไม่มีไฟล์ใดใน working tree ของ `main` ทั้งสอง repo ถูกแก้ (ไฟล์นี้เป็น untracked ใหม่ไฟล์เดียว)

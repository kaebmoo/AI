# PROMPT — แก้คำตอบ "หน่วยงานไหนผิดปกติจากค่าเฉลี่ยก่อนหน้า" (ฝั่ง AI)

> **แผน = brief:** [`plan/PLAN_ANOMALY_AVG_FIX.md`](PLAN_ANOMALY_AVG_FIX.md) — อ่านทั้งไฟล์ก่อนเริ่ม (§1 หลักฐาน, §2 ข้อตัดสิน, §3–§7 งานต่อ phase พร้อมไฟล์ที่อนุญาตและ acceptance)
> งานนี้คือ implementation ใน **worktree** — ห้ามขึ้นของจริงเอง (ห้าม ff `main`, ห้าม push, ห้าม restart server จริง) จนกว่าเจ้าของสั่ง
> สั่งด้วย `/delegate` ได้: slice = Phase 1, Phase 2, Phase 3, Phase 4.1 — แต่ **Phase 0 ทำเองก่อน** (อ่านข้อมูลจริงแบบอ่านอย่างเดียว ผลของมันกำหนด Phase 2)
> ฝั่ง NT-Report (Phase 4.2) เป็นอีก prompt: [`PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md`](PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md)

---

## 0. ก่อนเริ่ม

1. อ่าน `CLAUDE.md` และ `plan/PLAN_ANOMALY_AVG_FIX.md` ทั้งไฟล์; ข้อห้าม/สภาพแวดล้อมตาม §0 ของแผน (server จริง reload จาก `main`, สำเนา DB,
   port 8001+, ห้าม key id 4 / id 5, pytest ด้วย `venv/bin/python3.14`)
2. สร้าง worktree จาก `main` แล้วดึงแผนเข้ามา (แผนกับสคริปต์อยู่บน branch `claude/loving-albattani-xazlz9` ใน origin):
   ```bash
   cd /Users/seal/Documents/GitHub/AI
   git fetch origin claude/loving-albattani-xazlz9
   git worktree add /Users/seal/Documents/GitHub/_worktrees/AI-anomaly -b claude/anomaly-avg-fix main
   cd /Users/seal/Documents/GitHub/_worktrees/AI-anomaly
   git merge --no-edit origin/claude/loving-albattani-xazlz9
   ```
   ถ้า merge ขัดกัน: `git merge --abort` แล้วดึงเฉพาะไฟล์ของงานนี้ —
   `git checkout origin/claude/loving-albattani-xazlz9 -- plan/PLAN_ANOMALY_AVG_FIX.md plan/PROMPT_ANOMALY_AVG_FIX_AI.md plan/PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md scripts/eval/check_anomaly_avg.py` แล้ว commit
3. baseline: รัน ACC-T และ ACC-L (คำสั่งใน `plan/PLAN_METRICS_CONVERGENCE.md` §0) บน worktree ก่อนแก้อะไร — บันทึกจำนวน passed/skipped
4. เตรียมสำเนาสำหรับ server ซ้อม (config.db / app.db / Chroma) ตามวิธีใน `plan/archive/RESULT_P8_KNOWLEDGE_SCOPE.md` §4 และ §8–9 —
   ชื่อรอบ `anomaly`; สร้าง key ซ้อมบนสำเนา; contract อ่านจาก `NT-Report/DataFeed/contracts` จริงแบบอ่านอย่างเดียว (แผนนี้ไม่แก้ contract)

---

## 1. Phase 0 — ตรวจหลักฐาน (อ่านอย่างเดียว) → แผน §3

- ทำครบ 4 ข้อของ §3: query `query_audit` ใน `app.db` ของ server จริงแบบ read-only (`sqlite3 -readonly …`), อ่าน log `query_trace` ของ request นั้น,
  รันเฉลย:
  ```bash
  venv/bin/python scripts/eval/check_anomaly_avg.py --db "$(ls -t /Users/seal/Documents/GitHub/AI/.source_cache/datafeed_sales-*.duckdb | head -1)"
  venv/bin/python scripts/eval/check_anomaly_avg.py --db "<ไฟล์เดียวกัน>" --by unit_fname_current
  ```
  (ถ้า `DATA_SOURCE_CACHE_DIR` ใน `.env` ไม่ใช่ `./.source_cache` ให้ใช้ path นั้น; หรือใช้ `--csv <NT-Report>/DataFeed/dist/sales/latest/fact_sales.csv`)
- สร้าง `plan/RESULT_ANOMALY_AVG_FIX.md` §0: audit id ทั้งสองรอบ (รอบที่ได้ตาราง vs รอบที่ได้ SQL ที่เจ้าของแปะ), งวดใน SQL ของรอบที่ได้ตาราง,
  ทางที่คำบรรยายมา, `escalation_tool_loop_enabled`, F8 ยืนยันหรือไม่, ตาราง oracle (ข้อ 3 ทั้งสองแบบ `--by`)
- **หยุดถามเจ้าของ** ถ้าผลขัดกับแผน §1 (เช่น รอบที่ได้ตารางไม่ได้ใช้ `AVG(amount)` บนแถวดิบ, หรือหา audit ไม่เจอ) — ส่งสรุปสั้น + สิ่งที่พบ แล้วรอ
- commit `docs(plan): RESULT anomaly §0 — …` บน branch

## 2. ข้อตัดสิน → แผน §2

- ถ้า §2 ยังไม่มีบรรทัด "เคาะแล้ว": **Phase 1 เริ่มได้เลย** (ไม่ขึ้นกับ D-1..D-5; D-6 ใช้ค่าที่แนะนำ = ก)
  แต่ **ถามเจ้าของก่อนเริ่ม Phase 3** (ใช้ D-1, D-2, D-3, D-4) — ถามครั้งเดียวรวมทุกข้อ พร้อมค่าที่แผนแนะนำ
- Phase 5 ไม่ทำ เว้นแต่เจ้าของสั่ง (D-5)

## 3. Phase 1 — I4 `avg_over_fact_rows` → แผน §4

- แก้เฉพาะไฟล์ที่อนุญาตใน §4; เลือกแหล่ง grain keys ตาม §4 ข้อ 3 (แนะนำ: อ่านจาก contract, ไม่ migrate) และเขียนเหตุผลลง RESULT
- tests ครบตาม §4 ข้อ 4 (ต้องผิด / ต้องผ่าน / ต่อสาย) — SQL ใน Appendix B ของแผนต้องอยู่ใน test แบบทั้งก้อน
- ACC-T, ACC-L → server ซ้อม: คำถามเหตุการณ์ด้วย scope แบบ portal 3 รอบ + regression ก่อน/หลัง (§4 ข้อ 5) + เพิ่มคำถามเหตุการณ์ลง
  `scripts/eval/portal_real_questions.json`
- RESULT §1: ผล ACC, SQL ที่ได้แต่ละรอบ, ตัวเลขเทียบ oracle, ตาราง regression (ก่อน/หลัง ต่อชุด), จำนวนครั้งที่ I4 ยิง + ตัวอย่าง (false positive = ต้องแก้ก่อนไปต่อ)
- commit แยก: `fix(ai): I4 avg_over_fact_rows — …`, `test(ai): …`, `docs(plan): RESULT anomaly §1 — …`

## 4. Phase 2 — ปีของ "เดือน X" ที่ไม่ระบุปี → แผน §5

- เลือกทางตามผล Phase 0: SQL ใช้ 2025 → ทำ I5 ตาม §5; SQL ใช้ 2026 แต่ข้อความยังเป็น 2568 → หาทางที่ข้าม `fix_explanation` แล้วแก้ทางนั้น
- tests + ACC + server ซ้อม (คำถามเหตุการณ์ 5 รอบได้ 202609 ทุกรอบ) + regression ชุดเดียวกับ Phase 1 → RESULT §2 → commit

## 5. Phase 3 — คำบรรยาย → แผน §6 (หลังเจ้าของเคาะ D-1..D-4)

- 3.1 ตัวตรวจจำนวนเงิน (`app/services/ai/explain_amounts.py` + ต่อใน `build_explanation`), 3.2 note ชื่อตัวชี้วัดบน `/api/v1/query` (ถึงขั้นคำบรรยายเท่านั้น),
  3.3 กฎคำบรรยาย + ตัดหัวข้อ "ข้อเสนอแนะการแสดงผล" (เฉพาะเมื่อ Phase 0 ยืนยันที่มา)
- tests ตาม §6 ข้อ 4 (ข้อความจริงของเหตุการณ์ต้องถูกจับ, ข้อความที่ถูกต้องต้องไม่ยิง, ปี/เงินไม่สับสน) + ACC + server ซ้อม → RESULT §3 → commit

## 6. Phase 4.1 — `columns` ใน response → แผน §7

- `SimpleQueryResponse.columns` (+ `parts[].columns`) + test ลำดับ + `docs/PORTAL_INTEGRATION.md` → ACC → RESULT §4 → commit
- แจ้งในสรุปว่า NT-Report ใช้ field นี้ได้แล้ว (prompt ฝั่ง NT-Report มี fallback อยู่แล้ว ทำก่อน/หลังได้)

## 7. จบงาน — ส่งให้เจ้าของ (ไม่ขึ้นของจริงเอง)

- สรุป: commit บน `claude/anomaly-avg-fix`, ACC-T/ACC-L ล่าสุด, ผลวัดต่อ phase เทียบ oracle, regression, false positive ที่พบ/แก้, สิ่งที่ยังค้าง
- ขั้นตอนขึ้นของจริงตามแผน §9 เป็นรายการให้เจ้าของสั่ง — **ไม่ทำเอง**
- อัปเดตแถวของแผนนี้ใน `plan/README.md` (สถานะ + ลิงก์ RESULT)

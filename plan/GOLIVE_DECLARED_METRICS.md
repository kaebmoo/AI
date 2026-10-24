# GO-LIVE — metric ที่ประกาศเป็นข้อมูล (ลำดับ §4 ของ `plan/RESULT_P8_DECLARED_METRICS.md`) — เตรียม 2026-10-24

**เจ้าของรันเอง ทีละบล็อก ตามลำดับ** · ทุกคำสั่งรันจาก terminal ปกติ (ไม่ใช่จาก session ของ Claude) · ตรวจผลที่บอกไว้ก่อนไปบล็อกถัดไป
**สภาพตอนเตรียม:** AI `main` = `a918164` (working tree สะอาด ยกเว้นไฟล์ plan untracked 2 ไฟล์), branch `ai/delegate-metrics` = `e745964` **fast-forward ได้** ·
NT-Report `main` = `9411609` (สะอาด), branch `ai/delegate-metrics` = `541b3e1` fast-forward ได้ · server จริง PID 14040 (`uvicorn --reload`, เริ่ม 2026-10-22 15:00)
รันจาก working tree ของ `main` → **การ merge ในขั้น 2 ทำให้ server reload code ใหม่ทันที** (ไม่ต้องรอ restart) — restart ในขั้น 4 มีไว้ล้าง cache ของ prompt/ผลลัพธ์ให้แน่ใจ
**ลำดับที่ห้ามสลับ:** AI code (ขั้น 2) ต้องขึ้นก่อน contract 1.5.0 ของ NT-Report (ขั้น 5) — code เดิมอ่าน key `metrics` ได้ (พิสูจน์แล้วบนสำเนา) แต่ code ใหม่ต้องมีอยู่ก่อนเพื่อให้ sync metric เมื่อ contract เปลี่ยน

---

## 0. backup (ทั้งสอง repo) — ~10 วินาที

```bash
B=~/nt-ai-backups/metrics-golive-$(date +%Y%m%d-%H%M%S); mkdir -p "$B" && sqlite3 /Users/seal/Documents/GitHub/AI/config.db ".backup '$B/config.db'" && sqlite3 /Users/seal/Documents/GitHub/AI/app.db ".backup '$B/app.db'" && cp /Users/seal/Documents/GitHub/NT-Report/DataFeed/contracts/ebt.yaml "$B/ebt-1.4.4.yaml" && readlink /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist/ebt/latest > "$B/ebt-latest-before.txt" && git -C /Users/seal/Documents/GitHub/AI rev-parse HEAD > "$B/ai-main-before.txt" && git -C /Users/seal/Documents/GitHub/NT-Report rev-parse HEAD > "$B/ntreport-main-before.txt" && echo "backup: $B" && cat "$B"/*.txt
```
ตรวจ: พิมพ์ path ของ backup, `builds/202609-20261022T031559Z`, `a918164…`, `9411609…`

## 1. ตรวจว่า main ยังสะอาดและ ff ได้ (ไม่เขียนอะไร)

```bash
git -C /Users/seal/Documents/GitHub/AI status --short && git -C /Users/seal/Documents/GitHub/AI merge-base --is-ancestor main ai/delegate-metrics && echo AI_FF_OK && git -C /Users/seal/Documents/GitHub/NT-Report status --short && git -C /Users/seal/Documents/GitHub/NT-Report merge-base --is-ancestor main ai/delegate-metrics && echo NTREPORT_FF_OK
```
ตรวจ: มีแค่ `?? plan/…` ของ AI, ขึ้น `AI_FF_OK` และ `NTREPORT_FF_OK` — ถ้าไม่ ff ได้ (มี commit ใหม่บน main) หยุดแล้วบอก

## 2. merge AI → main (server reload ทันที; code ใหม่ทนกับการที่ยังไม่มีตาราง `schema_metrics` — sync จะข้ามพร้อม warning 1 ครั้ง)

```bash
git -C /Users/seal/Documents/GitHub/AI merge --ff-only ai/delegate-metrics && git -C /Users/seal/Documents/GitHub/AI log --oneline a918164..HEAD
```
ตรวจ: 6 commit (`ff886c0 … e745964`) · ดูแท็บ Terminal "AI server :8000" ว่า reload แล้วขึ้น `Application startup complete`

## 3. migration — สร้างตาราง `schema_metrics` บน config.db จริง (idempotent รันซ้ำได้)

```bash
cd /Users/seal/Documents/GitHub/AI && venv/bin/python scripts/migrate_schema_metrics.py && sqlite3 config.db "SELECT name FROM sqlite_master WHERE name IN ('schema_metrics','ux_schema_metrics_context_metric')"
```
ตรวจ: `Migration complete (idempotent).` และชื่อตาราง + index 2 บรรทัด · (ตารางยังว่าง — แถว metric จะเข้าเมื่อ contract 1.5.0 ถึงในขั้น 5/6)

## 4. restart server (เจ้าของทำเอง — แท็บ "AI server :8000": Ctrl-C แล้วรันใหม่)

```bash
cd /Users/seal/Documents/GitHub/AI && venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
ตรวจ: startup ไม่มี error เรื่อง provenance (`missing_provenance` เช็กเฉพาะตารางที่มี) · ถามอะไรก็ได้ 1 คำถามใน chat ว่าตอบปกติ

## 5. NT-Report — merge แล้ว build/publish ebt 1.5.0 (contract + dist ขึ้นพร้อมกัน; AI re-sync เองเมื่อเห็น contract เปลี่ยน)

```bash
git -C /Users/seal/Documents/GitHub/NT-Report merge --ff-only ai/delegate-metrics && git -C /Users/seal/Documents/GitHub/NT-Report log --oneline 9411609..HEAD && grep -n "^schema_version" /Users/seal/Documents/GitHub/NT-Report/DataFeed/contracts/ebt.yaml
```
ตรวจ: 3 commit, `schema_version: 1.5.0`

```bash
cd /Users/seal/Documents/GitHub/NT-Report && .venv/bin/python tools/feed/build_feed.py --domain ebt
```
ตรวจ: `reconcile: PASS`, `cross-domain bridges: PASS`, grand totals @202609 มี `ebt_ex_personnel = 5,799.8`, `bundle: …/dist/ebt/202609 (+ latest/)`
(ถ้า bridges FAIL = ข้อมูล expense/sales dist ไม่ตรง — หยุดแล้วดู manifest.reconcile.bridges ก่อน ไม่ใช่เรื่องของงานนี้)

```bash
cd /Users/seal/Documents/GitHub/NT-Report && /Users/seal/Documents/GitHub/AI/venv/bin/python3.14 tools/feed/portal_questions.py --domain ebt
```
ตรวจ: `ebt period=202609 … questions=14`

## 6. AI — ลงทะเบียน source ใหม่ (ตารางได้คอลัมน์ใหม่ + sync metric 3 แถว) — รันจาก main ของ AI (ใช้ .env = DB จริง)

```bash
cd /Users/seal/Documents/GitHub/AI && venv/bin/python -m scripts.datafeed.register_file_source --domain ebt --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist && sqlite3 config.db "SELECT context_name, metric_id, source, status FROM schema_metrics" && sqlite3 config.db "SELECT table_name, columns LIKE '%ebt_ex_personnel%' FROM source_tables WHERE source_id = (SELECT id FROM data_sources WHERE name='datafeed_ebt') AND table_name LIKE '%monthly'"
```
ตรวจ: `Domain ebt: schema 1.5.0`, `Control totals OK`, `Registered source 'datafeed_ebt'` · 3 แถว `feed_ebt|ebt|declared|active`, `…|ebt_excluding_personnel|…`, `…|ebt_margin|…` · สองตาราง monthly ขึ้น `1`
(ไม่ต้อง rebuild keyword index — คอลัมน์ใหม่เป็นยอดเงิน ไม่ใช่ค่าให้ค้น)

## 7. ตรวจบนของจริง

- chat (context feed_ebt หรือให้ router เลือก): **"ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร จะเป็นเท่าไหร่"** → ต้องได้ **54.47 ล้านบาท** (54,469,208.99) และ **"ถ้าไม่รวมค่าใช้จ่ายบุคลากร จะมี EBT เป็นเท่าไหร่ แบบสะสม"** → **5,799.84 ล้านบาท**
- log ของ server (แท็บ Terminal) ต้องมีบรรทัด `Metric compiled: ebt_excluding_personnel (…)` — ถ้าไม่มีแต่ตัวเลขถูก = ทาง LLM ตอบเอง ให้ดูบรรทัด `Pass 1 complete … Intent:` ว่าทำไม `plan()` ไม่รับ (เคสที่รู้แล้ว 4 แบบอยู่ใน RESULT §2)
- audit: `sqlite3 app.db "SELECT id, question, substr(sql_query,1,80) FROM query_audit ORDER BY id DESC LIMIT 3"` — SQL ของข้อ compile เริ่มด้วย `SELECT ((((` หรือ `SELECT "ebt_ex_personnel"`
- จากนั้น push ทั้งสอง repo แล้วดู CI ของ AI: `gh run list --branch main -L 3` (ชุด test 1412 ข้อผ่านบนเครื่องแล้วแบบ CI env)

## ถอยกลับ (ถ้าต้อง) — ลำดับย้อน

```bash
cd /Users/seal/Documents/GitHub/NT-Report && .venv/bin/python tools/feed/build_feed.py --domain ebt --rollback && git reset --keep 9411609 && grep -n "^schema_version" DataFeed/contracts/ebt.yaml
```
→ `latest` กลับไป build ก่อนหน้า, contract 1.4.4 (AI re-sync เอง: แถว metric 3 แถวถูกถอนเพราะ contract ไม่ประกาศแล้ว)

```bash
cd /Users/seal/Documents/GitHub/AI && venv/bin/python -m scripts.datafeed.register_file_source --domain ebt --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist && git reset --keep a918164
```
→ ตารางของ source กลับไปคอลัมน์เดิม, code กลับ `a918164` (reload เอง; ตาราง `schema_metrics` คงอยู่ได้ ไม่มีใครอ่าน) · ถ้าต้องการคืน DB ทั้งก้อน: หยุด server แล้ว `cp $B/config.db config.db`

## หลังขึ้นของจริง (ไม่เร่ง)
- `CLAUDE.md`/`AGENTS.md` Quick Reference: เพิ่มบรรทัด "metric ที่ประกาศ (`schema_metrics`, contract `metrics:`) → `metric_compiler` ประกอบ SQL แทน pass 2" + กฎ "ตัวอ่าน metric ใหม่ต้องกรอง `status='active'`" — ยังไม่ได้แก้ (เป็นไฟล์ใน main)
- ลบ worktree เมื่อไม่ต้องดู diff: `git -C /Users/seal/Documents/GitHub/AI worktree remove /Users/seal/Documents/GitHub/_worktrees/AI-metrics` (และ `AI-before`, และของ NT-Report) — ผลวัด/log อยู่ใน `_worktrees/AI-metrics/.ai/eval/` จะหายไปด้วย ให้คัดลอกก่อนถ้าต้องการเก็บ

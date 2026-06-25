# Manual: Context Onboarding System

**ระบบเตรียมข้อมูลอัตโนมัติ สำหรับ NL-to-SQL**

---

## ภาพรวม

เมื่อมี view/table ใหม่เข้ามาในระบบ (เช่น ข้อมูลสินทรัพย์, segment report, งบดุล) ระบบ Context Onboarding จะ:

1. **วิเคราะห์โครงสร้างข้อมูล** — ตรวจจับว่าเป็น long_table, semi-crosstab, หรือ wide_table
2. **ใช้ AI วิเคราะห์** — สร้าง business rules, ตัวอย่าง SQL, keyword mappings
3. **สร้าง config ครบ 7 ตาราง** — พร้อมใช้งานกับผู้ใช้ทันที
4. **ทดสอบ** — ตรวจว่า config ถูก insert ครบถ้วน

---

## วิธีใช้งาน

### วิธี 1: CLI Script (แนะนำสำหรับเริ่มต้น)

```bash
# 1. ดูข้อมูลเบื้องต้น (ไม่ใช้ AI)
python scripts/onboard_context.py \
  --view-name v_new_view \
  --inspect-only

# 2. วิเคราะห์ด้วย AI + preview config (ไม่บันทึก)
python scripts/onboard_context.py \
  --view-name v_new_view \
  --provider gemini \
  --dry-run

# 3. บันทึก config ลง DB
python scripts/onboard_context.py \
  --view-name v_new_view \
  --provider gemini \
  --apply --validate

# 4. Export เป็น JSON (เพื่อ review ก่อน apply)
python scripts/onboard_context.py \
  --view-name v_new_view \
  --output config_review.json
```

**Options ทั้งหมด:**

| Flag | คำอธิบาย | Default |
|------|---------|---------|
| `--view-name` | ชื่อ view/table ที่จะ onboard | (required) |
| `--db-path` | path ไปยัง SQLite DB | `nt_fi_report.sqlite` |
| `--provider` | AI provider: gemini, claude, matcha | จาก admin_config |
| `--model` | model เฉพาะ | จาก admin_config |
| `--api-url` | Custom API URL | จาก .env |
| `--api-key` | Custom API key | จาก .env |
| `--inspect-only` | แค่ดูข้อมูล ไม่เรียก AI | false |
| `--dry-run` | preview ไม่บันทึก | true |
| `--apply` | บันทึกลง DB จริง | false |
| `--validate` | ทดสอบหลัง apply | false |
| `--output` | export เป็น JSON | - |

### วิธี 2: Claude Code Skill (Interactive)

ใน Claude Code พิมพ์:
```
/onboard-context v_new_view
```

หรือบอก:
- "วิเคราะห์ view ใหม่ v_asset_summary"
- "onboard ข้อมูลสินทรัพย์"
- "เพิ่มข้อมูลใหม่เข้าระบบ"
- "สอนระบบเรื่อง segment report"

Skill จะ:
1. ใช้ MCP SQLite tools ตรวจสอบข้อมูล
2. แสดงผลวิเคราะห์ให้ review
3. สร้าง config suggestions
4. ถาม confirm ก่อน insert

### วิธี 3: Admin Web UI (แนะนำสำหรับ Admin)

เข้า Admin Dashboard → **Data Management** → **Context Onboarding**

URL: `http://localhost:5173/context-onboarding`

**Wizard 4 ขั้นตอน:**

1. **Select View** — เลือก view/table จาก dropdown
   - แสดง views ที่ยังไม่มี config (badge เขียว "แนะนำ")
   - แสดง views ที่มี config แล้ว (badge ส้ม "Re-onboard")
   - กดปุ่ม "Inspect"

2. **Inspect** — ดูข้อมูลเบื้องต้น (ไม่ใช้ AI, เร็วมาก)
   - Row count, column count, detected structure
   - ตาราง columns พร้อม flags (NUMERIC, TIME, PREFIX)
   - เตือน semi-crosstab ถ้าพบ
   - เลือก AI Provider → กดปุ่ม "Analyze with AI"

3. **AI Analysis & Preview** — วิเคราะห์ด้วย AI + preview config
   - แสดง context info, rules count, examples count
   - SQL Preview (collapsible)
   - กดปุ่ม "Apply Config to Database"

4. **Results** — ผลการ apply
   - สรุป config ที่ apply แล้ว
   - Validation results
   - ปุ่มไป "Data Contexts" หรือ "Onboard Another View"

### วิธี 4: Admin API (สำหรับ Automation)

```bash
# List available views
curl http://localhost:8000/api/v1/admin/contexts/onboard/available-views \
  -H "Authorization: Bearer TOKEN"

# Full pipeline
curl -X POST http://localhost:8000/api/v1/admin/contexts/onboard \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "view_name": "v_new_view",
    "dry_run": true,
    "provider": "gemini"
  }'

# Inspect only (fast)
curl -X POST http://localhost:8000/api/v1/admin/contexts/onboard/inspect \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"view_name": "v_new_view"}'

# Validate existing config
curl -X POST http://localhost:8000/api/v1/admin/contexts/onboard/validate \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"view_name": "v_pl_costtype_nt_mth_clean"}'
```

---

## เลือก AI Provider

| Provider | ข้อดี | เหมาะกับ |
|----------|------|---------|
| **gemini** | เร็ว, ราคาถูก, Thai context ดี | งานทั่วไป, ทดสอบ |
| **claude** | วิเคราะห์ลึก, structured output ดี | view ซับซ้อน |
| **matcha** | ใช้ผ่าน Gateway, OpenAI-compatible | production, org policy |

**เปลี่ยน provider:**
```bash
# Gemini
--provider gemini --model gemini-2.5-flash

# Claude
--provider claude --model claude-sonnet-4-6

# Matcha (GPT-4.1)
--provider matcha --model gpt-4.1

# Custom OpenAI-compatible (เช่น Kimi)
--provider matcha --model kimi-k2 --api-url https://api.kimi.ai/v1/chat/completions
```

---

## ประเภทข้อมูลที่ระบบตรวจจับ

### 1. Long Table (ตารางยาว)
- ตัวอย่าง: `revenue`, `expense`
- ลักษณะ: value column เดียว, ทุกแถวมีความหมายเดียวกัน
- SUM ปลอดภัย: ✅ `SUM(amount)` = รวมรายได้/ค่าใช้จ่าย

### 2. Semi-Crosstab (กึ่ง crosstab) ⚠️
- ตัวอย่าง: `v_pl_costtype_nt_mth_clean` (งบ P&L)
- ลักษณะ: value column เดียว แต่ความหมายขึ้นกับ category column
- SUM อันตราย: ❌ `SUM(amount_value)` = รวมรายได้+ค่าใช้จ่าย+กำไร
- ต้อง: `CASE WHEN main_group LIKE '01.%' THEN amount_value...` หรือ `GROUP BY main_group`

### 3. Wide Table (ตารางกว้าง)
- ตัวอย่าง: ตารางที่ pivot แล้ว (มีหลาย value columns)
- ลักษณะ: `revenue_col`, `cost_col`, `profit_col` แยก column

**วิธีตรวจจับ:** ระบบวิเคราะห์ SUM(value) GROUP BY category — ถ้ามี mixed +/- signs → semi-crosstab

---

## Config ที่ระบบสร้าง (7 ตาราง)

### 1. `schema_contexts` — นิยาม Context
- ชื่อ, keywords, instruction ภาษาไทย/อังกฤษ
- ใช้สำหรับ route คำถามไปยัง view ที่ถูกต้อง

### 2. `schema_metadata` — ข้อมูล Column
- ชื่อภาษาไทย, คำอธิบาย, summable/groupable flags
- special_notes สำหรับข้อควรระวัง

### 3. `schema_business_rules` — กฎป้องกัน SQL ผิด
- Critical rules: ป้องกันผลลัพธ์ผิด (เช่น ห้าม SUM ใน semi-crosstab)
- Warning rules: best practice (เช่น แปลงหน่วยเป็นล้านบาท)
- พร้อม example_correct และ example_wrong

### 4. `golden_examples` — ตัวอย่าง SQL (Few-Shot)
- คำถามภาษาไทย → SQL ที่ถูกต้อง
- ใช้โดย RAG (Vanna) เพื่อ guide AI

### 5. `schema_semantic_mapping` — Keyword Mappings
- "มือถือ" → `UPPER(business_unit) LIKE '%MOBILE%'`
- "กำไรขั้นต้น" → `main_group LIKE '03.%'`

### 6. `master_hierarchy` — ลำดับชั้นข้อมูล
- กลุ่มธุรกิจ → กลุ่มบริการ → ผลิตภัณฑ์

### 7. `data_warnings` — เตือนคุณภาพข้อมูล
- case inconsistency, prefix changes, missing data periods

---

## หลัง Apply แล้วต้องทำอะไร

1. **Restart server** หรือเรียก API `/admin/config/refresh-cache` เพื่อ clear cache
2. **ทดสอบ** — ถามคำถามภาษาไทยกับระบบ ดูว่า SQL ถูกต้อง
3. **Sync golden examples** ไป Vanna (ถ้าเปิด RAG): `POST /admin/examples/sync-brain`
4. **Review ผ่าน Admin UI** — ตรวจ business rules, semantic mappings ที่ generate มา

---

## ตัวอย่าง: Onboard ข้อมูลสินทรัพย์ (สมมติ)

```bash
# สมมติมี view ใหม่: v_asset_summary
# columns: asset_type, department, acquisition_year, book_value, depreciated_value

# Step 1: ดูข้อมูล
python scripts/onboard_context.py --view-name v_asset_summary --inspect-only

# Output:
# Structure: long_table (book_value เป็น + เสมอ)
# Value cols: [book_value, depreciated_value]
# Dimension cols: [asset_type, department]
# Time cols: [acquisition_year]

# Step 2: Generate config
python scripts/onboard_context.py --view-name v_asset_summary --provider gemini --dry-run

# Step 3: Review output, then apply
python scripts/onboard_context.py --view-name v_asset_summary --provider gemini --apply --validate
```

---

## Troubleshooting

### LLM ไม่ตอบ / timeout
- ตรวจ API key ใน `.env`
- ลอง provider อื่น: `--provider matcha` แทน gemini
- ใช้ `--inspect-only` ก่อนเพื่อดูข้อมูลโดยไม่ต้องเรียก AI

### Config ที่ generate ไม่ถูกต้อง
- ใช้ `--dry-run` preview ก่อน apply
- Export ด้วย `--output config.json` แล้ว review
- แก้ไขผ่าน Admin UI หลัง apply (soft delete + เพิ่มใหม่)

### Semi-crosstab detect ไม่ได้
- ระบบใช้ mixed +/- signs เป็น heuristic
- ถ้า view มี value ที่เป็น + ทั้งหมด แต่ category เปลี่ยนความหมาย → ต้องเพิ่ม rule เอง
- ใช้ Claude Code skill เพื่อ interactive analysis

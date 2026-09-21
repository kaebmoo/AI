# Master Data & Hierarchy — Admin Guide

คู่มือสำหรับ Admin ในการจัดการ Master Data ผ่าน Web UI

**URL:** `http://localhost:5173/hierarchy`

---

## Overview: ระบบนี้คืออะไร?

AI ใช้ **Hierarchy (ลำดับชั้นข้อมูล)** ในการแปลงคำถามภาษาไทยเป็น SQL ที่ถูกต้อง

ตัวอย่าง: ถ้าผู้ใช้ถาม "รายได้ของกลุ่ม Fixed Line แยกรายบริการ"

```
AI ต้องรู้ว่า:
  "กลุ่ม Fixed Line" → filter ที่ SERVICE_GROUP (level 1)
  "แยกรายบริการ" → group by PRODUCT_NAME (level 2)
  "Fixed Line" → ค่าจริงคือ "บริการโทรศัพท์ประจำที่ (Fixed Line)"

ข้อมูลทั้งหมดนี้มาจาก master_hierarchy
```

---

## หน้าจอ: ส่วนประกอบ

```
┌─────────────────────────────────────────────────────────┐
│  Master Data & Hierarchy Management                      │
│                                                          │
│  [Context ▼]  [Extract from Data] [Show Diff] [Import CSV]│
│                                                          │
│  Context: revenue | Levels: 3 | Values: 312              │
│  ┌──────────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Hierarchy    │ │ Values   │ │ Unmatched Keywords    │ │
│  │ Levels       │ │          │ │                       │ │
│  └──────────────┘ └──────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Context Dropdown

รายการ context ที่เลือกได้ (เช่น revenue, expense, transfer price)

**Context มาจากไหน:**
- สร้างครั้งแรกตอน run `extract_hierarchy.py` หรือ `import_master_data.py`
- หรือ Admin เพิ่ม Level ใหม่ → context ใหม่ถูกสร้างอัตโนมัติ
- ถ้า dropdown ว่าง = ยังไม่เคย extract/import → ต้อง run script ก่อน

### ปุ่ม Header

| ปุ่ม | ทำอะไร |
|------|--------|
| **Extract from Data** | ดึงค่าจริงจากฐานข้อมูล (DISTINCT) มาสร้าง hierarchy อัตโนมัติ ค่าที่ admin แก้เอง (manual) จะไม่ถูกทับ |
| **Show Diff** | เปรียบเทียบ master data กับข้อมูลจริง แสดงค่าใหม่ (new) และค่าที่หายไป (missing) |
| **Import CSV** | เปิด popup นำเข้าข้อมูลจากไฟล์ CSV (ทีละ level) |
| **New Context** | สร้าง hierarchy ใหม่จาก view/table — ตรวจจับ columns อัตโนมัติ ไม่ต้อง run command line |

---

## Tab 1: Hierarchy Levels

กำหนดลำดับชั้นข้อมูล — AI ใช้ข้อมูลนี้ตัดสินว่าควร filter ที่ column ไหน

### ตัวอย่าง: revenue context

| Level | Label (TH) | Columns | Keywords |
|-------|-----------|---------|----------|
| 0 | กลุ่มธุรกิจ | BUSINESS_GROUP | กลุ่มธุรกิจ, ธุรกิจ, business |
| 1 | กลุ่มบริการ | SERVICE_GROUP | กลุ่มบริการ, กลุ่ม |
| 2 | บริการ/ผลิตภัณฑ์ | PRODUCT_NAME | บริการ, แต่ละบริการ, product |

**Keywords สำคัญมาก:**
- AI ใช้ keywords จับคู่คำถาม → ถ้าผู้ใช้พิมพ์ "กลุ่มบริการ" → AI รู้ว่าหมายถึง level 1 (SERVICE_GROUP)
- ใช้ longest-match → "กลุ่มบริการ" (10 ตัวอักษร) ชนะ "กลุ่ม" (4 ตัวอักษร)

### วิธีเพิ่ม Level ใหม่

1. กด **Add Level**
2. กรอก:
   - **Level Number:** 0 = ระดับสูงสุด (กว้างที่สุด), ตัวเลขยิ่งมาก = ยิ่งละเอียด
   - **Label (TH/EN):** ชื่อแสดงผล
   - **Columns:** ชื่อ column ในฐานข้อมูล (คั่นด้วย comma)
   - **Detection Keywords:** คำที่ผู้ใช้อาจพิมพ์ (คั่นด้วย comma)
3. กด **Save**

---

## Tab 2: Values

ค่าจริงในแต่ละระดับ พร้อม aliases สำหรับค้นหา

### ตัวอย่าง: revenue context, level 1

| Value | Parent | Aliases |
|-------|--------|---------|
| บริการโทรศัพท์ประจำที่ (Fixed Line) | Fixed Line & Broadband | fixed line, บริการโทรศัพท์ประจำที่ |
| กลุ่มบริการ Internet Retail | Fixed Line & Broadband | internet retail |

**Aliases สำคัญมาก:**
- ผู้ใช้พิมพ์ "fixed line" → AI ค้น aliases → เจอ "บริการโทรศัพท์ประจำที่ (Fixed Line)" → ใช้ `SERVICE_GROUP LIKE '%Fixed Line%'`
- ถ้าไม่มี alias → AI อาจ filter ผิด column

### การใช้งาน

| Action | วิธีทำ |
|--------|--------|
| **ค้นหา** | พิมพ์ใน Search box → ค้นทั้ง value และ aliases |
| **กรองตาม Level** | เลือก level จาก dropdown |
| **Drill-down** | คลิก Parent → กรองเฉพาะ children ของ parent นั้น |
| **ดู children** | คลิกตัวเลข Children → drill-down ไป level ย่อย |
| **แก้ไข** | กด Edit → แก้ value, parent, aliases |
| **เพิ่มใหม่** | กด Add Value → กรอก level, value, parent, aliases |
| **ลบ** | กด Delete → soft delete (สามารถกู้คืนได้) |

---

## Import CSV

นำเข้า hierarchy values จากไฟล์ CSV ทีละ level

### ขั้นตอน

1. กดปุ่ม **Import CSV** (ขวาบน)
2. เลือกไฟล์ CSV
3. กรอก:
   - **Target Level:** เลือก level ที่จะ import (เช่น L1: กลุ่มบริการ)
   - **Value Column:** ชื่อ column ใน CSV ที่เป็นค่าหลัก (เช่น `SERVICE_GROUP`)
   - **Parent Column:** ชื่อ column ที่เป็นค่าแม่ (เช่น `BUSINESS_GROUP`) — เว้นว่างถ้าเป็น top level
   - **Alias Columns:** column อื่นที่จะใช้เป็น aliases (เช่น `SERVICE_GROUP_SHORT_NAME`)
4. กด **Import**

### ตัวอย่าง: import product level 2 จาก MASTER_PRODUCT_NT.csv

```
Target Level:   L2: บริการ/ผลิตภัณฑ์
Value Column:   PRODUCT_NAME
Parent Column:  SERVICE_GROUP
Alias Columns:  PRODUCT_SHORT_NAME
```

### ทำไมต้อง import ทีละ level?

เพราะ CSV แต่ละไฟล์มี format ต่างกัน และบาง CSV มีหลาย level ในไฟล์เดียว ต้องระบุว่าจะ import column ไหน เป็น level ไหน

**ถ้าต้องการ import ทั้ง hierarchy ทีเดียว** → ใช้ command line:
```bash
python scripts/import_master_data.py --source /path/to/csv
```
Script จะ import ทุก level ให้อัตโนมัติ

### Command Line vs Web UI

| | Web UI (Import CSV) | Command Line |
|---|---|---|
| **Import ทีละ level** | ได้ | ได้ |
| **Import ทั้ง hierarchy ทีเดียว** | ไม่ได้ (ต้องทำทีละ level) | **ได้** (script จัดการเอง) |
| **ต้องรู้ชื่อ column** | ต้องกรอกเอง | Script กำหนดไว้แล้ว |
| **เหมาะกับ** | Admin ทั่วไป, import เล็กๆ | Import ครั้งแรก, batch update |

---

## Tab 3: Unmatched Keywords

Keywords ที่ AI ใช้ LIKE ค้นหาแต่ไม่มี alias ตรงกัน

### ทำไมสำคัญ?

ถ้า AI ไม่เจอ alias ที่ตรงกับคำถามผู้ใช้ → AI จะเดา column เอง → อาจ filter ผิด

### วิธีจัดการ

| Action | เมื่อไหร่ |
|--------|----------|
| **Add as Alias** | keyword นี้ควรจับคู่กับ value ที่มีอยู่ → เพิ่มเป็น alias |
| **Resolve** | keyword นี้ไม่สำคัญ หรือจัดการแล้ว → ข้ามไป |

**Count สูง = ควรเพิ่มเป็น alias ก่อน** เพราะผู้ใช้พิมพ์คำนี้บ่อย

---

## Extract from Data vs Import CSV

| | Extract from Data | Import CSV |
|---|---|---|
| **ข้อมูลมาจาก** | ฐานข้อมูลจริง (view/table) | ไฟล์ CSV ที่ upload |
| **ใช้เมื่อ** | ข้อมูลใน DB เปลี่ยน (เพิ่ม product ใหม่) | มีไฟล์ master data จากแหล่งอื่น |
| **source** | `inferred` (เดิม `auto`) | `manual` |
| **ทับข้อมูลเก่า** | ไม่ทับ manual | ทับทุกอย่าง (เป็น manual) |
| **ต้องกำหนด column** | ไม่ต้อง (อ่านจาก DB config) | ต้องกำหนดเอง |

### วงจรการดูแลระบบ

```
1. ข้อมูลใหม่เข้าระบบ (ETL/import)
2. Admin กด "Extract from Data"
3. ตรวจสอบ "Show Diff" → เห็นค่าใหม่
4. แก้ไข aliases ถ้าจำเป็น
5. ตรวจสอบ Unmatched Keywords → เพิ่ม alias ที่ขาด
6. AI ใช้ข้อมูลใหม่ได้ทันที (หลัง cache หมดอายุ ~1 ชม.)
```

---

## FAQ

### Q: Dropdown ว่างเปล่า ไม่มี context ให้เลือก
**A:** ยังไม่เคย extract/import → run command:
```bash
python scripts/extract_hierarchy.py
```

### Q: กด Extract from Data แล้วข้อมูลหาย
**A:** ไม่หาย — Extract เพิ่มเฉพาะค่าใหม่ (source=inferred) ค่าที่ admin แก้เอง (source=manual) จะไม่ถูกทับ

### Q: ระดับที่ "Bootstrap from view" สร้าง ทำไม AI ยังไม่ใช้
**A:** (Plan 8.1) ระดับที่เครื่องเดาเป็น `inferred` / `status='proposed'` — prompt ใช้เฉพาะ `active` จนกว่า admin จะรับ (บันทึกระดับนั้น = รับ;
ค่าที่ extract ไว้ของระดับนั้นใช้ได้ด้วย) · ระดับที่คนทำไว้แล้วไม่ถูก bootstrap ทับ — ฉบับของเครื่องเข้าคิว `knowledge_proposals`

### Q: Import CSV ต้องทำทีละ level จริงหรือ?
**A:** ผ่าน Web UI ต้องทำทีละ level เพราะต้องระบุ column mapping ถ้าต้องการ import ทั้ง hierarchy ทีเดียว ใช้ command line

### Q: เพิ่ม context ใหม่ทำอย่างไร?
**A:** กดปุ่ม **New Context** (ขวาบน):
1. ตั้งชื่อ context ใหม่ (เช่น `asset`, `cost_center`)
2. เลือก view/table ที่จะดึงข้อมูลจาก
3. กด **Create & Extract** → ระบบตรวจจับ columns อัตโนมัติ สร้าง levels และดึง values ให้ทั้งหมด
4. ตรวจสอบ + แก้ไข keywords/aliases ตามต้องการ

### Q: ข้อมูลจะ sync อัตโนมัติไหม?
**A:** ยังไม่ auto-sync ต้อง admin กด "Extract from Data" เอง เมื่อข้อมูลใน DB เปลี่ยน

### Q: ทำไมถึงทำผ่าน Web UI ได้ทั้งหมด ไม่ต้อง command line?
**A:** Web UI รองรับทุก operation:
- **New Context** = สร้าง hierarchy ใหม่จาก view (เทียบเท่า `extract_hierarchy.py`)
- **Extract from Data** = ดึง values ใหม่ (เทียบเท่า `extract_hierarchy.py --context xxx`)
- **Import CSV** = นำเข้าจากไฟล์ (เทียบเท่า `import_master_data.py`)
- **Add Level / Add Value** = เพิ่มทีละรายการ

Command line ยังมีประโยชน์สำหรับ batch operations หรือ automation scripts

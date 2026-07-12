# Semantic Mapping Quick Reference

## 🎯 วิธีการทำงาน

```
User Query → Semantic Mapping → SQL Condition
```

**ตัวอย่าง:**
```
"trunk radio" → (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')
```

---

## ✅ Mappings ที่ใช้งานได้แล้ว

### 📱 ผลิตภัณฑ์ (Products)

| คำค้น | SQL Condition |
|------|---------------|
| trunk radio | `(UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')` |
| trunked radio | `UPPER(product_name) LIKE '%TRUNKED%'` |
| trunked mobile | `UPPER(product_name) LIKE '%TRUNKED MOBILE%'` |
| วิทยุเฉพาะกิจ | `product_name LIKE '%วิทยุเฉพาะกิจ%'` |
| mobile | `(UPPER(BUSINESS_GROUP) = 'MOBILE' OR BUSINESS_GROUP = 'Mobile')` |
| broadband | `(UPPER(BUSINESS_GROUP) LIKE '%BROADBAND%' OR BUSINESS_GROUP LIKE '%บรอดแบนด์%')` |
| internet | `(UPPER(BUSINESS_GROUP) LIKE '%INTERNET%' OR BUSINESS_GROUP LIKE '%อินเทอร์เน็ต%')` |

### 🏢 หน่วยงาน (Organizations)

| คำค้น | SQL Condition |
|------|---------------|
| นป. | `organization_group_abbr = 'นป.'` |
| บชง. | `department_abbr = 'บชง.'` |
| สญ. | `division_abbr = 'สญ.'` |

---

## 📖 ความหมายของ `keyword_type`

`keyword_type` บอก AI ว่าควรใช้ keyword นี้อย่างไร และจัดกลุ่มใน prompt แตกต่างกัน

### 1. `abbreviation` — คำย่อหน่วยงาน

**ใช้เมื่อ:** keyword เป็น **ตัวย่อ** ที่ตรงกับค่าในฐานข้อมูล 100% มักเป็นชื่อฝ่าย/สายงาน

| keyword | target_column | target_condition | description |
|---------|--------------|-----------------|-------------|
| `นป.` | `organization_group_abbr` | `= 'นป.'` | กลุ่มขายฯ ภาคเหนือ |
| `บชง.` | `department_abbr` | `= 'บชง.'` | ฝ่ายบัญชีบริหาร |
| `สญ.` | `division_abbr` | `= 'สญ.'` | สายงานขายและบริการ |

**Priority แนะนำ:** 10 (สูงสุด เพราะ match ตรง)
**ใน AI Prompt:** แสดงเป็นตาราง หัวข้อ "คำย่อหน่วยงาน (Abbreviations)"

---

### 2. `term` — คำศัพท์ธุรกิจ / ชื่อเต็ม

**ใช้เมื่อ:** keyword เป็น **คำธรรมดา** (ไทย/อังกฤษ) หรือ **ชื่อเต็ม** ที่คนพูดถึง แต่ค่าจริงในฐานข้อมูลอาจต่างออกไป

| keyword | target_column | target_condition | description |
|---------|--------------|-----------------|-------------|
| `มือถือ` | `BUSINESS_GROUP` | `= 'Mobile'` | รายได้ Mobile |
| `อสังหาริมทรัพย์` | `SERVICE_GROUP` | `= 'กลุ่มบริการพัฒนาสินทรัพย์'` | รายได้อสังหาฯ |
| `อินเทอร์เน็ต` | `BUSINESS_GROUP` | `LIKE '%Internet%' OR BUSINESS_GROUP LIKE '%Broadband%'` | รายได้อินเทอร์เน็ต |
| `ฝ่ายบริหารงานกลาง` | `DEPARTMENT` | `= 'ฝ่ายบริหารงานกลาง'` | ชื่อฝ่ายเต็ม |

**Priority แนะนำ:** 5–7
**ใน AI Prompt:** แสดงเป็นตาราง หัวข้อ "คำศัพท์ธุรกิจ (Business Terms)"

---

### 3. `synonym` — คำพ้องที่ต้อง match แบบ exact

**ใช้เมื่อ:** keyword มี SQL condition **ซับซ้อน** (หลาย OR, หลาย column) หรือเป็นคำที่ AI เคย generate ผิดบ่อย — ต้องการบังคับให้ AI copy SQL ไปใช้ **ตรงๆ ห้ามดัดแปลง**

| keyword | full_condition | description |
|---------|---------------|-------------|
| `trunk radio` | `(UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')` | วิทยุเฉพาะกิจ ทุกรูปแบบ |
| `บริหารงานกลาง` | `DEPARTMENT = 'ฝ่ายบริหารงานกลาง' OR DEPARTMENT LIKE '%บริหารงานกลาง%'` | รองรับทั้งชื่อเต็มและบางส่วน |

**Priority แนะนำ:** 8–9
**ใน AI Prompt:** แสดงเป็น XML พร้อม label **"MUST USE EXACTLY AS SHOWN"** — AI จะไม่ดัดแปลง condition

---

### สรุปการเลือก type

| สถานการณ์ | type ที่ควรใช้ |
|-----------|--------------|
| คำย่อหน่วยงาน เช่น `นป.`, `บชง.` | `abbreviation` |
| ชื่อเต็มฝ่าย เช่น `ฝ่ายบริหารงานกลาง` | `term` |
| คำกว้างๆ เช่น `ฝ่าย` (LIKE pattern) | `term` |
| คำธรรมดาที่ map ไปชื่อ DB เช่น `มือถือ` → `Mobile` | `term` |
| Condition ซับซ้อน / AI เคย generate ผิด | `synonym` |
| คำที่มี alias หลายแบบ ต้องใช้ OR | `synonym` |

---

## 🏢 ตัวอย่าง: keyword ที่เกี่ยวกับ "ฝ่าย" (DEPARTMENT)

Column `DEPARTMENT` ในฐานข้อมูลมีทั้งที่ขึ้นต้นด้วย "ฝ่าย", "กลุ่ม", และอื่นๆ ต้องเลือก condition ให้ตรงกับเจตนา

### กรณีค้นหาชื่อเต็ม (ต้องการฝ่ายนี้โดยเฉพาะ)

```sql
-- ใช้ type: term
keyword          : ฝ่ายบริหารงานกลาง
keyword_type     : term
target_column    : DEPARTMENT
target_condition : = 'ฝ่ายบริหารงานกลาง'
description      : ฝ่ายบริหารงานกลาง (ชื่อเต็ม)
priority         : 7
```

### กรณีค้นหาแบบ pattern (ทุกฝ่ายที่ขึ้นต้นด้วย "ฝ่าย")

```sql
-- ใช้ type: term
keyword          : ฝ่าย
keyword_type     : term
target_column    : DEPARTMENT
target_condition : LIKE 'ฝ่าย%'
description      : หน่วยงานระดับฝ่าย (ขึ้นต้นด้วย "ฝ่าย")
priority         : 5
```

### กรณีชื่อฝ่ายมีหลายรูปแบบ (ป้องกัน AI สร้าง SQL ผิด)

```sql
-- ใช้ type: synonym + full_condition
keyword          : บริหารงานกลาง
keyword_type     : synonym
target_column    : DEPARTMENT
full_condition   : DEPARTMENT = 'ฝ่ายบริหารงานกลาง' OR DEPARTMENT LIKE '%บริหารงานกลาง%'
description      : ฝ่ายบริหารงานกลาง (รองรับทุกรูปแบบที่เรียก)
priority         : 8
```

> **หมายเหตุ:** ชื่อเต็มที่มี = ตรงตัวให้ใช้ `term` ก็พอ
> ยกเป็น `synonym` เมื่อต้องการบังคับ condition แบบ OR หรือมีความซับซ้อน

---

## 🌐 Field `context_name` — ขอบเขตของ Mapping

> **เพิ่มใน Version 2.2** — แก้ปัญหา mapping ชุดเดียวถูกส่งให้ AI ทุก context

### ปัญหาที่แก้ได้

แต่ละ context (revenue, expense, transfer price, pl_costtype) ใช้ **ชื่อ column ต่างกัน** สำหรับ "ฝ่าย":

| Context | Column "ฝ่าย" |
|---------|--------------|
| revenue / expense | `DEPARTMENT` |
| transfer price | `owner_department`, `user_department` |
| pl_costtype | ไม่มี column ฝ่าย |

ถ้าส่ง mapping `ฝ่าย → DEPARTMENT` ไปให้ transfer price AI → AI จะ generate `WHERE DEPARTMENT = ...` ซึ่งไม่มีใน view `v_transfer_price` → ผลลัพธ์ผิด

---

### หลักการ `context_name`

| ค่า context_name | ความหมาย | ตัวอย่าง |
|-----------------|----------|---------|
| `NULL` (ว่าง) | **Global** — ส่งให้ AI ทุก context | คำย่อ `นป.`, `บชง.` |
| `'revenue'` | เฉพาะ context revenue | mapping เฉพาะรายได้ |
| `'expense'` | เฉพาะ context expense | mapping เฉพาะค่าใช้จ่าย |
| `'transfer price'` | เฉพาะ context transfer price | `owner_department`, `user_department` |
| `'pl_costtype'` | เฉพาะ context pl_costtype | mapping เฉพาะ P&L |

**Logic การ filter:**
- context_name = **NULL** → ส่งไปทุก context (backward compatible)
- context_name = **'transfer price'** → ส่งเฉพาะเมื่อ user ถามใน transfer price context

---

### ตัวอย่าง mapping ที่ถูกต้อง

```
keyword          : ฝ่าย
keyword_type     : term
target_column    : DEPARTMENT
target_condition : LIKE 'ฝ่าย%'
context_name     : (ว่าง / NULL)     ← global ใช้ได้กับ revenue, expense
description      : ฝ่ายทั่วไป สำหรับ revenue/expense

keyword          : ฝ่ายบริหารงานกลาง
keyword_type     : synonym
target_column    : owner_department
full_condition   : (owner_department = 'ฝ่ายบริหารงานกลาง' OR user_department = 'ฝ่ายบริหารงานกลาง')
context_name     : transfer price    ← เฉพาะ transfer price เท่านั้น
description      : ฝ่ายบริหารงานกลาง ทั้งในฐานะเจ้าของและผู้ใช้

keyword          : ฝ่ายเจ้าของ
keyword_type     : synonym
target_column    : owner_department
full_condition   : owner_department LIKE '%'
context_name     : transfer price    ← เฉพาะ transfer price เท่านั้น
description      : owner_department ใน transfer price
```

---

### ค่าที่ใช้ได้ใน context_name (ณ ปัจจุบัน)

```
(ว่าง / NULL)   → Global ใช้ได้ทุก context
revenue          → context รายได้
expense          → context ค่าใช้จ่าย
transfer price   → context ราคาโอน (v_transfer_price)
pl_costtype      → context P&L (v_pl_costtype_nt_mth_clean)
```

> **ค่า context_name ต้องตรงกับ `context_name` ใน table `schema_contexts`** ทุกตัวอักษร (case-sensitive)

---

### ดูค่า context ที่มีในระบบ

```sql
SELECT context_name, main_view FROM schema_contexts;
```

---

## 🔧 วิธีเพิ่ม Mapping ใหม่

### ผ่าน Web Admin UI:

1. ไปที่ Settings → Semantic Mappings
2. กด **"Add New Mapping"**
3. กรอกข้อมูล:
   ```
   Keyword      : ชื่อที่ user จะพิมพ์
   Type         : abbreviation / term / synonym
   Context      : เลือกจาก dropdown หรือปล่อยว่าง (= Global)
   Target Column: column ใน SQL เช่น DEPARTMENT, owner_department
   SQL Condition: เช่น = 'ฝ่ายบริหารงานกลาง' หรือ LIKE 'ฝ่าย%'
   Full Condition: ใช้เมื่อต้องการ OR หลาย column (Advanced)
   Description  : คำอธิบาย
   Priority     : 5-10 (สูง = สำคัญ)
   ```
4. บันทึก → Cache refresh อัตโนมัติ!

**Filter ใน UI:**
- ช่อง **Context dropdown** (ด้านบนตาราง) → กรอง Global / revenue / expense / transfer price / pl_costtype
- คอลัมน์ **Context** ในตาราง แสดงสีต่างๆ ตาม context

---

### ผ่าน SQL:

```sql
-- Global mapping (ใช้ได้ทุก context)
INSERT INTO schema_semantic_mapping (
    keyword, keyword_type, target_column, target_condition,
    description, priority, is_active, context_name
) VALUES (
    'ฝ่าย', 'term', 'DEPARTMENT', "LIKE 'ฝ่าย%'",
    'ฝ่ายทั่วไป', 5, 1, NULL
);

-- Context-specific mapping (เฉพาะ transfer price)
INSERT INTO schema_semantic_mapping (
    keyword, keyword_type, target_column, full_condition,
    description, priority, is_active, context_name
) VALUES (
    'ฝ่ายบริหารงานกลาง', 'synonym', 'owner_department',
    "(owner_department = 'ฝ่ายบริหารงานกลาง' OR user_department = 'ฝ่ายบริหารงานกลาง')",
    'ฝ่ายบริหารงานกลาง สำหรับ transfer price', 8, 1, 'transfer price'
);
```

---

## 🎓 Best Practices

### ✅ DO (ควรทำ)

1. **ใช้ UPPER() สำหรับภาษาอังกฤษ**
   ```sql
   UPPER(column) LIKE '%KEYWORD%'
   ```

2. **ใช้ OR สำหรับหลายภาษา**
   ```sql
   (UPPER(col) LIKE '%ENG%' OR col LIKE '%ไทย%')
   ```

3. **ใช้ full_condition สำหรับ complex patterns**
   ```sql
   full_condition: (col1 LIKE '%A%' OR col2 LIKE '%B%')
   ```

4. **ตั้ง Priority ให้เหมาะสม**
   - 10 = คำเฉพาะมาก (abbreviation)
   - 7-9 = คำศัพท์ทั่วไป
   - 5-6 = คำพ้องความหมาย

### ❌ DON'T (ไม่ควรทำ)

1. **ห้ามใส่ GROUP BY ใน condition**
   ```sql
   ❌ target_condition: GROUP BY column
   ✅ ลบออก หรือใส่ใน instruction
   ```

2. **ห้ามใช้ = กับชื่อไทย**
   ```sql
   ❌ column = 'ชื่อไทย'
   ✅ column LIKE '%ชื่อไทย%'
   ```

3. **ห้ามใส่ OR ใน target_condition**
   ```sql
   ❌ target_condition: LIKE '%A%' OR col LIKE '%B%'
   ✅ full_condition: (col LIKE '%A%' OR col LIKE '%B%')
   ```

---

## 🧪 การทดสอบ

### Test Query:
```python
from app.services.schema_service import SchemaService  # shim → app/services/schema/service.py
from app.db.session import config_engine, business_engine

# semantic mappings อยู่ใน config.db (3-DB architecture)
service = SchemaService(db_engine=config_engine, business_engine=business_engine)
mappings = service.get_semantic_mappings()

# ค้นหา mapping
trunk = [m for m in mappings if 'trunk' in m['keyword'].lower()]
print(trunk)
```

### Test SQL:
```sql
-- ทดสอบว่า mapping หาเจอข้อมูลหรือไม่
SELECT COUNT(*) 
FROM v_pl_costtype_nt_mth_clean
WHERE (UPPER(product_name) LIKE '%TRUNK%' 
       OR UPPER(product_name) LIKE '%TRUNKED%' 
       OR product_name LIKE '%วิทยุเฉพาะกิจ%');
```

---

## 📊 สถิติ

- **Total Mappings:** 84
- **With full_condition:** 35
- **Abbreviations:** 20+
- **Products:** 15+
- **Tested:** trunk radio, mobile, broadband ✅

---

## 🚨 Troubleshooting

**Q: AI ยัง hard-code SQL อยู่?**  
A: Restart server และตรวจสอบว่า CRITICAL RULE อยู่ใน prompt

**Q: Mapping ไม่ทำงาน?**  
A: ตรวจสอบ `full_condition` มีค่าหรือไม่, priority เพียงพอหรือไม่

**Q: ต้อง restart server ทุกครั้งหรือไม่?**  
A: ไม่! cache refresh อัตโนมัติแล้ว (ถ้าเพิ่มผ่าน Admin UI)

---

**Updated:** 2026-07-12
**Version:** 2.2.1 (แก้ตัวอย่าง test ให้ใช้ `config_engine` ตาม 3-DB architecture)

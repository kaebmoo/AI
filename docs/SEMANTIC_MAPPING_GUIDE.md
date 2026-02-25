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

## 🔧 วิธีเพิ่ม Mapping ใหม่

### ผ่าน Web Admin UI:

1. ไปที่ Settings → Semantic Mappings
2. กด "Add New"
3. กรอกข้อมูล:
   ```
   Keyword: ชื่อที่ user จะพิมพ์
   Type: synonym/term/abbreviation
   Target Column: (ปล่อยว่างถ้าใช้ full_condition)
   Full Condition: SQL WHERE condition
   Description: คำอธิบาย
   Priority: 5-10 (สูง = สำคัญ)
   ```
4. บันทึก → Cache refresh อัตโนมัติ!

### ผ่าน SQL:

```sql
INSERT INTO schema_semantic_mapping (
    keyword, 
    keyword_type, 
    target_column, 
    full_condition, 
    description, 
    priority, 
    is_active
) VALUES (
    'your_keyword',
    'synonym',
    '',
    'your_sql_condition',
    'คำอธิบาย',
    8,
    1
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
from app.services.schema_service import SchemaService
from app.db.session import engine

service = SchemaService(db_engine=engine)
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

**Updated:** 2026-02-25
**Version:** 2.1 (เพิ่มอธิบาย keyword_type และตัวอย่าง DEPARTMENT)

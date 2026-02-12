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

**Updated:** 2025-02-12  
**Version:** 2.0 (with auto-refresh)

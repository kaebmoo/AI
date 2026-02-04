# Tooltip Improvements for Long Text

## 📋 ปัญหาที่แก้ไข

### **ปัญหาเดิม:**
```
❌ Tooltip แคบเกิน (maxWidth: 220px)
❌ ข้อความยาวถูกตัด อ่านไม่ได้
❌ ไม่มี text wrapping
❌ กรณีมีหลายกลุ่ม tooltip สูงเกิน overflow
```

**ตัวอย่าง:**
```
┌──────────────────────┐
│ กลุ่มบริการเสาโทรค...│  ← ตัวหนังสือถูกตัด!
├──────────────────────┤
│ ⬛ เดือน 1: 1,500,... │  ← อ่านไม่ครบ
│ ⬛ เดือน 2: 1,600,... │
│ ⬛ เดือน 3: 1,200,... │
│ ⬛ เดือน 4: 1,300,... │
│ ⬛ เดือน 5: 1,400,... │
│ ⬛ เดือน 6: 1,100,... │  ← tooltip สูงเกิน
└──────────────────────┘
```

---

## ✅ การแก้ไข

### **1. Grouped Bar Chart Tooltip (DataChart.tsx:754-820)**

#### **เปลี่ยนแปลง:**
- ✅ **maxWidth**: 220 → **340px** (เพิ่ม 54%)
- ✅ **maxHeight**: ไม่มี → **280px** (ป้องกันสูงเกิน)
- ✅ **ScrollView**: เพิ่ม scroll สำหรับกรณีมีหลายกลุ่ม (>5 items)
- ✅ **Text Wrapping**: เพิ่ม `flexWrap: 'wrap'` ให้ text ขึ้นบรรทัดใหม่ได้
- ✅ **Layout Improvement**: แยก label และ value เป็น 2 บรรทัด สำหรับข้อความยาว

#### **ก่อน:**
```typescript
<View style={{ minWidth: 180, maxWidth: 220 }}>
    <Text>{category}</Text>
    {series.map(s => (
        <View className="flex-row">
            <Text>{s}</Text>
            <Text>{value}</Text>
        </View>
    ))}
</View>
```

#### **หลัง:**
```typescript
<View style={{ minWidth: 200, maxWidth: 340, maxHeight: 280 }}>
    <Text style={{ flexWrap: 'wrap' }}>{category}</Text>
    <ScrollView maxHeight={200} showsVerticalScrollIndicator={true}>
        {series.map(s => (
            <View className="mb-2">
                {/* Label row */}
                <View className="flex-row">
                    <ColorDot />
                    <Text style={{ flexWrap: 'wrap', flex: 1 }}>{s}</Text>
                </View>
                {/* Value row - indented */}
                <View style={{ marginLeft: 16 }}>
                    <Text>{value}</Text>
                </View>
            </View>
        ))}
    </ScrollView>
</View>
```

---

### **2. Bar Chart Tooltip (DataChart.tsx:1088-1111)**

#### **เปลี่ยนแปลง:**
- ✅ **maxWidth**: 140 → **280px** (เพิ่ม 100%)
- ✅ **Text Wrapping**: เพิ่ม `flexWrap: 'wrap'`
- ✅ **Padding**: เพิ่ม padding: 8 สำหรับข้อความยาว

---

### **3. Line Chart Tooltip (DataChart.tsx:1131-1181)**

#### **เปลี่ยนแปลง:**

**Multi-Series:**
- ✅ **maxWidth**: 160 → **300px**
- ✅ **maxHeight**: ไม่มี → **240px**
- ✅ **ScrollView**: เพิ่ม scroll สำหรับหลาย series
- ✅ **Layout**: แยก label และ value เป็น 2 บรรทัด

**Single-Series:**
- ✅ **maxWidth**: 140 → **240px**
- ✅ **Text Wrapping**: เพิ่ม `flexWrap: 'wrap'`

---

## 📊 ผลลัพธ์

### **หลังแก้ไข:**
```
┌─────────────────────────────────────┐
│ กลุ่มบริการเสาโทรคมนาคม          │  ← แสดงครบ!
│ (Tower)                              │  ← ขึ้นบรรทัดใหม่
├─────────────────────────────────────┤
│ [Scrollable Area - 200px max]        │
│ ⬛ เดือน 1                          │
│    1.50 ล้านบาท                     │  ← แยกบรรทัด อ่านง่าย
│                                      │
│ ⬛ เดือน 2                          │
│    1.60 ล้านบาท                     │
│                                      │
│ ⬛ เดือน 3                          │
│    1.20 ล้านบาท                     │
│                                      │
│ ... (scroll for more)                │
└─────────────────────────────────────┘
```

---

## 🎯 ประโยชน์

### **1. อ่านง่ายขึ้น**
- ข้อความยาวไม่ถูกตัด
- Text wrapping ทำให้อ่านครบทุกตัวอักษร
- แยก label และ value เป็น 2 บรรทัด ไม่แน่นมาก

### **2. รองรับข้อมูลเยอะ**
- ScrollView ทำให้แสดงได้มากกว่า 5-6 items
- maxHeight ป้องกัน tooltip สูงเกินจอ
- Scroll indicator แสดงให้รู้ว่ายังมีข้อมูลเพิ่ม

### **3. Responsive**
- maxWidth เพิ่มขึ้นแต่ไม่เกินหน้าจอ
- flexWrap ทำให้ปรับตามเนื้อหา
- Layout ยืดหยุ่น รองรับข้อความสั้น-ยาว

---

## 🔍 ตัวอย่างการใช้งาน

### **Case 1: ชื่อกลุ่มยาว**
```
Query: "รายได้รายกลุ่มธุรกิจ"

Before:
┌───────────────────┐
│ กลุ่มบริการเสา...│  ← ตัดทิ้ง
└───────────────────┘

After:
┌──────────────────────────────┐
│ กลุ่มบริการเสาโทรคมนาคม  │
│ (Tower)                       │  ← แสดงครบ
└──────────────────────────────┘
```

### **Case 2: หลายกลุ่ม (>5 items)**
```
Query: "ค่าใช้จ่ายรายหมวดบัญชี 12 เดือน"

Before:
┌──────────────┐
│ หมวด 1      │
│ หมวด 2      │
│ หมวด 3      │
│ หมวด 4      │
│ หมวด 5      │
│ หมวด 6      │  ← overflow ออกจอ
│ หมวด 7      │
└──────────────┘

After:
┌──────────────┐
│ หมวด 1      │
│ หมวด 2      │
│ หมวด 3      │
│ ...          │
│ [Scroll ↓]   │  ← มี scroll indicator
└──────────────┘
```

### **Case 3: Label + Value ยาว**
```
Before (แน่นมาก):
┌─────────────────────────┐
│ ⬛ กลุ่มบริการ... 1.5M │
│ ⬛ กลุ่มดิจิตอล... 2.3M │
└─────────────────────────┘

After (อ่านง่าย):
┌──────────────────────────────┐
│ ⬛ กลุ่มบริการเสาโทรคมฯ │
│    1.50 ล้านบาท             │
│                              │
│ ⬛ กลุ่มดิจิตอลคอนเทนต์  │
│    2.30 ล้านบาท             │
└──────────────────────────────┘
```

---

## 🚀 การทดสอบ

### **Test Case 1: ชื่อยาว**
```bash
Query: "รายได้กลุ่มบริการเสาโทรคมนาคม (Tower) รายเดือน"

Expected:
✅ ชื่อกลุ่มแสดงครบไม่ตัด
✅ Text wrap หลายบรรทัดถ้าจำเป็น
✅ Tooltip กว้างพอ (≤ 340px)
```

### **Test Case 2: หลายกลุ่ม**
```bash
Query: "ค่าใช้จ่ายรายหมวดบัญชี 12 เดือน"

Expected:
✅ แสดง 5 รายการแรก
✅ มี scroll indicator ถ้า > 5 items
✅ Scroll ได้ภายใน tooltip
✅ Tooltip สูงไม่เกิน 280px
```

### **Test Case 3: Mobile Screen**
```bash
Query: ทดสอบบน iPhone (375px width)

Expected:
✅ Tooltip ไม่เกินความกว้างหน้าจอ
✅ Text wrap ทำงานถูกต้อง
✅ ไม่มี horizontal overflow
```

---

## 📝 Technical Details

### **Key Changes:**

1. **Width Adjustments:**
   ```typescript
   // Grouped Bar Tooltip
   minWidth: 200 (was 180)
   maxWidth: 340 (was 220) ← +54%

   // Bar Tooltip
   maxWidth: 280 (was 140) ← +100%

   // Line Tooltip (Multi)
   maxWidth: 300 (was 160) ← +87%
   ```

2. **Height Control:**
   ```typescript
   // Add maxHeight to prevent overflow
   maxHeight: 280 (Grouped Bar)
   maxHeight: 240 (Line Chart Multi)

   // ScrollView maxHeight
   maxHeight: 200 (Grouped Bar)
   maxHeight: 180 (Line Chart Multi)
   ```

3. **Text Wrapping:**
   ```typescript
   <Text style={{ flexWrap: 'wrap', flex: 1 }}>
     {longText}
   </Text>
   ```

4. **Layout Improvement:**
   ```typescript
   // Old: Label and Value in same row
   <View className="flex-row">
     <Text>{label}</Text>
     <Text>{value}</Text>
   </View>

   // New: Label and Value in separate rows
   <View className="mb-2">
     <View className="flex-row">
       <ColorDot />
       <Text style={{ flex: 1, flexWrap: 'wrap' }}>{label}</Text>
     </View>
     <View style={{ marginLeft: 16 }}>
       <Text>{value}</Text>
     </View>
   </View>
   ```

---

## 🎨 Design Considerations

### **Balance:**
- **Width**: เพิ่มขนาดพอให้อ่านได้ แต่ไม่เกินหน้าจอ mobile
- **Height**: จำกัดความสูง + เพิ่ม scroll เพื่อไม่ให้ tooltip บดเนื้อหาอื่น
- **Padding**: เพิ่ม padding ให้ text มีพื้นที่หายใจ

### **Accessibility:**
- Scroll indicator แสดงเมื่อมีข้อมูลเยอะ (>5 items)
- Text contrast ดี (light text on dark bg)
- Touch target เพียงพอ (min 8px color dot)

### **Performance:**
- ScrollView ใช้ `nestedScrollEnabled={true}` เพื่อ scroll ภายใน tooltip
- `flexShrink: 0` สำหรับ color dot ป้องกันหด
- `flex: 1` สำหรับ text ให้ใช้พื้นที่เต็ม

---

## ✅ Summary

| Aspect | Before | After | Improvement |
|--------|--------|-------|-------------|
| Max Width (Grouped) | 220px | 340px | +54% |
| Max Width (Bar) | 140px | 280px | +100% |
| Max Width (Line) | 160px | 300px | +87% |
| Text Wrapping | ❌ No | ✅ Yes | 100% |
| Scroll Support | ❌ No | ✅ Yes | 100% |
| Height Control | ❌ No | ✅ Yes | 100% |
| Layout | Single row | 2-row | Cleaner |

---

**ผลลัพธ์:** Tooltip อ่านง่ายขึ้นมาก รองรับข้อความยาวและหลายกลุ่มได้ดี ✅

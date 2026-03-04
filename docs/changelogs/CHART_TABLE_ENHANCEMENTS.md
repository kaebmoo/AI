# Chart & Table Enhancements

## 📋 สรุปการปรับปรุง

เพิ่มฟีเจอร์ใหม่ 2 อย่าง เพื่อปรับปรุง UX ในการดูข้อมูล:

1. **Full-Screen Chart View** - ขยายกราฟเป็นเต็มจอ
2. **CSV Export** - ส่งออกตารางเป็นไฟล์ CSV

---

## ✨ Feature 1: Full-Screen Chart View

### **ปัญหาเดิม:**
```
❌ กราฟมีรายละเอียดเยอะ มองในหน้าจอปกติไม่สะดวก
❌ ข้อความ label ยาวถูกตัด
❌ หลาย series มองยาก
```

### **การแก้ไข:**

#### **1. เพิ่มปุ่ม Expand (DataChart.tsx:1183-1193)**
- ✅ เพิ่มปุ่ม **"ขยาย"** (Expand icon) ที่มุมขวาบน ของกราฟ
- ✅ สีน้ำเงิน เหมือนกับ Theme ของกราฟ
- ✅ ใช้ `Ionicons` สำหรับไอคอน

```typescript
<TouchableOpacity
    onPress={() => setIsFullScreen(true)}
    className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/30"
>
    <Ionicons name="expand-outline" size={20} color={isDark ? '#93C5FD' : '#3B82F6'} />
</TouchableOpacity>
```

#### **2. Modal Full-Screen (DataChart.tsx:1349-1511)**
- ✅ ใช้ `Modal` component จาก React Native
- ✅ **Full-screen dimensions**: `screenWidth - 80` (ขยายเกือบเต็มหน้าจอ)
- ✅ **Chart height เพิ่ม**: 200 → 300px
- ✅ **Font size ใหญ่ขึ้น**: 10 → 12px (อ่านง่ายกว่า)
- ✅ มีปุ่ม **Close** (X) ที่มุมขวาบน
- ✅ แสดง Legend และ Hint text เหมือนเดิม

```typescript
<Modal
    visible={isFullScreen}
    animationType="fade"
    transparent={false}
    onRequestClose={() => setIsFullScreen(false)}
>
    <View className="flex-1 bg-white dark:bg-gray-900 pt-12">
        {/* Header with Close Button */}
        <View className="flex-row justify-between items-center px-6 pb-4">
            <Text className="text-lg font-bold">...</Text>
            <TouchableOpacity onPress={() => setIsFullScreen(false)}>
                <Ionicons name="close-outline" size={24} />
            </TouchableOpacity>
        </View>

        {/* Full-Screen Chart */}
        <ScrollView>
            <LineChart width={screenWidth - 80} height={300} ... />
            {/* or */}
            <BarChart width={screenWidth - 120} height={300} ... />
        </ScrollView>
    </View>
</Modal>
```

---

### **ผลลัพธ์:**

#### **ก่อน:**
```
┌────────────────────────────┐
│ 📈 Trends : revenue        │  [มุมปกติ]
├────────────────────────────┤
│                            │
│   📊 กราฟ (200px height)  │  ← แคบ label อ่านยาก
│                            │
└────────────────────────────┘
```

#### **หลัง:**
```
┌────────────────────────────┐
│ 📈 Trends : revenue   [🔍] │  ← ปุ่ม Expand
├────────────────────────────┤
│   📊 กราฟ (200px)         │
└────────────────────────────┘

กด [🔍] แล้ว...

┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 📈 Trends : revenue   [X] ┃  ← Full-screen Modal
┣━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                            ┃
┃   📊 กราฟ (300px height)  ┃  ← ใหญ่ขึ้น!
┃       Font 12px            ┃  ← อ่านง่าย!
┃       Width: Full-screen   ┃  ← กว้างเต็มจอ!
┃                            ┃
┃   Legend + Hint            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## 📤 Feature 2: CSV Export

### **ปัญหาเดิม:**
```
❌ ไม่สามารถส่งออกข้อมูลตารางได้
❌ ต้อง Copy-Paste ทีละบรรทัด
❌ ใช้ข้อมูลต่อใน Excel/Sheets ไม่ได้
```

### **การแก้ไข:**

#### **1. เพิ่มปุ่ม Export (DataTable.tsx:424-430)**
- ✅ เพิ่มปุ่ม **"Download"** (Download icon) ข้างจำนวนแถว
- ✅ สีเขียว (ธีม Download)
- ✅ ใช้ `Ionicons` สำหรับไอคอน

```typescript
<TouchableOpacity
    onPress={exportToCSV}
    className="p-2 rounded-lg bg-green-50 dark:bg-green-900/30"
>
    <Ionicons name="download-outline" size={18} color={isDark ? '#86EFAC' : '#16A34A'} />
</TouchableOpacity>
```

#### **2. Export Function (DataTable.tsx:365-416)**
- ✅ รองรับ **3 ประเภทตาราง**:
  - **Crosstab (Pivot)**: แถว = หมวด, คอลัมน์ = เดือน
  - **Grouped Table**: แบ่งกลุ่มตาม Parent Key
  - **Flat Table**: ตารางธรรมดา
- ✅ Format CSV ด้วย **double quotes** ป้องกันปัญหา comma ใน text
- ✅ ใช้ **Share API** - รองรับทั้ง Mobile และ Web
- ✅ แสดง Alert เมื่อสำเร็จ/ล้มเหลว

```typescript
const exportToCSV = async () => {
    try {
        let csvContent = '';

        if (isCrosstab) {
            // Crosstab CSV
            const headers = [rowKey, ...periodLabels];
            csvContent = headers.map(h => `"${h}"`).join(',') + '\n';
            // ... rows
        } else if (parentKey) {
            // Grouped Table CSV
            // ...
        } else {
            // Flat Table CSV
            const headers = keys;
            csvContent = headers.map(h => `"${h}"`).join(',') + '\n';
            // ... rows
        }

        const result = await Share.share({
            message: csvContent,
            title: 'Export CSV'
        });

        if (result.action === Share.sharedAction) {
            Alert.alert('สำเร็จ', 'ส่งออกข้อมูลเรียบร้อย');
        }
    } catch (error) {
        Alert.alert('ข้อผิดพลาด', 'ไม่สามารถส่งออกข้อมูลได้');
    }
};
```

---

### **ตัวอย่าง CSV Output:**

#### **Crosstab Table:**
```csv
"account_group_name","1/2025","2/2025","3/2025"
"ค่าใช้จ่ายบุคลากร","1500000","1600000","1200000"
"ค่าใช้จ่ายดำเนินงาน","500000","650000","550000"
```

#### **Flat Table:**
```csv
"year","month","division","revenue"
"2025","1","สายงานบริหาร","1500000"
"2025","2","สายงานบริหาร","1600000"
```

---

### **ผลลัพธ์:**

#### **ก่อน:**
```
┌──────────────────────────┐
│ 🔢 ตารางข้อมูล  12 รายการ │  [ไม่มีปุ่ม Export]
├──────────────────────────┤
│ | หมวด | ม.ค. | ก.พ. |  │
│ | A    | 1.5M | 1.6M  |  │
└──────────────────────────┘
❌ ไม่สามารถ Export ได้
```

#### **หลัง:**
```
┌────────────────────────────┐
│ 🔢 ตารางข้อมูล  12 รายการ [📥]│  ← ปุ่ม Download
├────────────────────────────┤
│ | หมวด | ม.ค. | ก.พ. |    │
│ | A    | 1.5M | 1.6M  |    │
└────────────────────────────┘

กด [📥] แล้ว...
✅ "สำเร็จ - ส่งออกข้อมูลเรียบร้อย"
→ ได้ไฟล์ CSV สามารถเปิดใน Excel/Sheets
```

---

## 🎯 ประโยชน์

### **Full-Screen Chart:**
1. **มองเห็นรายละเอียดชัดเจน** - กราฟใหญ่ขึ้น font อ่านง่าย
2. **รองรับข้อมูลเยอะ** - แสดง label ยาวได้ครบ
3. **Mobile-friendly** - ปรับขนาดตามหน้าจอ
4. **Dark mode support** - รองรับทั้ง Light/Dark theme

### **CSV Export:**
1. **ใช้ข้อมูลต่อได้** - นำไปวิเคราะห์ใน Excel, Google Sheets
2. **รองรับทุกประเภทตาราง** - Crosstab, Grouped, Flat
3. **Cross-platform** - ทำงานทั้ง iOS, Android, Web
4. **ปลอดภัย** - ใช้ Share API ของ OS

---

## 🧪 การทดสอบ

### **Test Case 1: Full-Screen Chart**
```bash
Query: "รายได้รายเดือน 12 เดือน แยกตามกลุ่มธุรกิจ"

Steps:
1. กราฟแสดงขึ้นในมุมปกติ
2. กดปุ่ม Expand (🔍) มุมขวาบน
3. Modal เปิดขึ้นเต็มจอ
4. กราฟใหญ่ขึ้น อ่านง่ายกว่า
5. กด Close (X) ปิด Modal

Expected:
✅ Modal เปิด/ปิดได้ถูกต้อง
✅ กราฟแสดงครบ ไม่มี error
✅ Tooltip ยังทำงานใน Modal
✅ Dark mode ทำงานถูกต้อง
```

### **Test Case 2: CSV Export (Crosstab)**
```bash
Query: "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน"

Steps:
1. ตารางแสดงแบบ Crosstab (แถว = หมวด, คอลัมน์ = เดือน)
2. กดปุ่ม Download (📥)
3. Share dialog เปิดขึ้น
4. เลือก Save/Share
5. เปิดไฟล์ CSV

Expected:
✅ CSV มี header ถูกต้อง (หมวด, 1/2025, 2/2025, ...)
✅ ข้อมูลครบถ้วน ไม่มีแถวหาย
✅ Format ถูกต้อง (double quotes)
✅ เปิดใน Excel/Sheets ได้
```

### **Test Case 3: CSV Export (Flat Table)**
```bash
Query: "รายได้ทั้งหมด"

Steps:
1. ตารางแสดงแบบ Flat (ทุก column แสดงตรง)
2. กดปุ่ม Download
3. เปิดไฟล์ CSV

Expected:
✅ CSV มีทุก column ของตารางต้นฉบับ
✅ ลำดับ column ถูกต้อง
✅ ข้อความไทยแสดงถูกต้อง
```

---

## 📝 Technical Details

### **Dependencies:**
```typescript
// DataChart.tsx
import { Modal, TouchableOpacity, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
const [isFullScreen, setIsFullScreen] = useState(false);

// DataTable.tsx
import { TouchableOpacity, Alert, Share } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
```

### **Key Changes:**

**DataChart.tsx:**
- Line 2: Added Modal, TouchableOpacity, Pressable imports
- Line 3: Added Ionicons import
- Line 196: Added `isFullScreen` state
- Line 1188-1193: Added expand button in header
- Line 1349-1511: Added full-screen Modal component

**DataTable.tsx:**
- Line 2: Added TouchableOpacity, Alert, Share imports
- Line 3: Added Ionicons import
- Line 365-416: Added `exportToCSV` function
- Line 424-430: Added download button in header

---

## 🎨 Design Considerations

### **Full-Screen Modal:**
- **Width**: `screenWidth - 80` (เต็มจอแต่มี padding)
- **Height**: Chart = 300px (ใหญ่กว่าปกติ 50%)
- **Font Size**: 12px (ใหญ่กว่าปกติ 20%)
- **Animation**: Fade transition (ดูนุ่มนวล)
- **Safe Area**: pt-12 (ไม่ทับ status bar)

### **Export Button:**
- **Color**: เขียว (สื่อถึง Download/Save)
- **Size**: 18px (พอดีกับ header)
- **Position**: ข้างจำนวนแถว (ง่ายต่อการเข้าถึง)
- **Feedback**: Active state (กดแล้วมี visual feedback)

---

## ✅ Summary

| Feature | Before | After | Improvement |
|---------|--------|-------|-------------|
| Chart View | Fixed size 200px | Full-screen 300px | +50% size |
| Chart Font | 10px | 12px (Modal) | +20% size |
| Chart Width | chartWidth | screenWidth - 80 | Full-screen |
| CSV Export | ❌ No | ✅ Yes | 100% new |
| Export Formats | - | Crosstab, Grouped, Flat | 3 types |
| Cross-platform | - | iOS, Android, Web | ✅ All |

---

**ผลลัพธ์:**
- ✅ กราฟดูรายละเอียดง่ายขึ้นด้วย Full-Screen View
- ✅ ส่งออกข้อมูลได้ทุกประเภทตารางด้วย CSV Export
- ✅ UX ดีขึ้นมาก รองรับทั้ง Mobile และ Desktop

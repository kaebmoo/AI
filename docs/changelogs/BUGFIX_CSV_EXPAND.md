# Bug Fixes: CSV Export & Expand Button

## 🐛 ปัญหาที่พบ

### 1. CSV Export ไม่ทำงาน
- ✅ **Fixed**: กดปุ่ม Export แล้วไม่มีอะไรเกิดขึ้น
- **สาเหตุ**: ใช้ `Share.share()` กับ text ซึ่งไม่ work บน Web และบางแพลตฟอร์ม

### 2. ปุ่มขยายไม่แสดงใน Bar Chart
- ⚠️ **Need Testing**: Line chart มีปุ่มขยาย แต่ Bar chart ไม่มี
- **สาเหตุที่เป็นไปได้**:
  - AI อาจ return `visualization: 'table'` แทนที่จะเป็น `visualization: 'bar_chart'`
  - หรือ analysis เป็น null ทำให้ component return null ก่อนถึง header

---

## ✅ การแก้ไข

### 1. CSV Export - แก้แล้ว (DataTable.tsx)

#### **เพิ่ม Dependencies:**
```json
// package.json
"expo-clipboard": "~7.0.9",
"expo-file-system": "~18.0.13",
"expo-sharing": "~14.0.8"
```

#### **เพิ่ม Imports:**
```typescript
import { Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
```

#### **Export Logic ใหม่:**

**Web:**
```typescript
// สร้าง Blob และ download ไฟล์
const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
const link = document.createElement('a');
const url = URL.createObjectURL(blob);
link.href = url;
link.download = fileName;
link.click();
```

**Mobile (iOS/Android):**
```typescript
// บันทึกไฟล์และแชร์
const fileUri = FileSystem.documentDirectory + fileName;
await FileSystem.writeAsStringAsync(fileUri, csvContent);
await Sharing.shareAsync(fileUri, {
    mimeType: 'text/csv',
    dialogTitle: 'Export CSV'
});
```

**Fallback:**
```typescript
// ถ้าแชร์ไม่ได้ ให้คัดลอกไปคลิปบอร์ด
await Clipboard.setStringAsync(csvContent);
Alert.alert('คัดลอกแล้ว', 'คัดลอกข้อมูล CSV ไปยังคลิปบอร์ดแล้ว');
```

---

### 2. Expand Button Debug - เพิ่ม Logging (DataChart.tsx)

เพิ่ม console.log เพื่อ debug:

```typescript
console.log('📊 DataChart Debug:', {
    visualization,
    chartConfig,
    analysis: analysis ? {
        mode: analysis.mode,
        categoryKey: analysis.categoryKey,
        measureKey: analysis.measureKey,
        seriesKey: analysis.seriesKey,
        isLineChart: analysis.mode === 'line',
        isGrouped: analysis.mode === 'grouped'
    } : null
});

console.log('✅ DataChart: Rendering chart with expand button. Chart type:',
    analysis.mode === 'line' ? 'LINE' :
    analysis.mode === 'grouped' ? 'GROUPED BAR' : 'BAR');
```

---

## 🧪 การทดสอบ

### **ขั้นตอนที่ 1: Install Dependencies**

```bash
cd frontend
npm install
```

หรือ

```bash
cd frontend
yarn install
```

### **ขั้นตอนที่ 2: ทดสอบ CSV Export**

**Test Case 1: Web**
```bash
# เปิด Web browser
npm run web

# ทดสอบ:
1. ถามคำถาม: "รายได้รายเดือน 12 เดือน"
2. รอให้ตารางแสดงขึ้น
3. กดปุ่ม Download (📥) มุมขวาบน
4. ไฟล์ CSV ควร download อัตโนมัติ
5. เปิดไฟล์ด้วย Excel/Google Sheets

Expected:
✅ Browser download dialog เปิดขึ้น
✅ ไฟล์ชื่อ "data_export_[timestamp].csv"
✅ เปิดใน Excel ได้ ข้อมูลถูกต้อง
```

**Test Case 2: Mobile (iOS/Android)**
```bash
# เปิด Expo Go
npm start

# ทดสอบ:
1. ถามคำถาม: "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน"
2. รอให้ตารางแสดงขึ้น (Crosstab)
3. กดปุ่ม Download (📥)
4. Share dialog เปิดขึ้น
5. เลือก Save to Files หรือ Share

Expected:
✅ Share dialog แสดง options (Save, Share, etc.)
✅ บันทึกไฟล์ได้
✅ เปิดไฟล์ CSV ได้
```

**Test Case 3: Fallback (Clipboard)**
```bash
# กรณี Sharing ไม่ available (emulator บางตัว)
1. กดปุ่ม Download
2. ดู Alert message

Expected:
✅ Alert: "คัดลอกแล้ว - คัดลอกข้อมูล CSV ไปยังคลิปบอร์ดแล้ว"
✅ Paste ใน text editor เห็น CSV content
```

---

### **ขั้นตอนที่ 3: ทดสอบ Expand Button**

**Test Case 1: Line Chart**
```bash
Query: "รายได้รายเดือน 12 เดือน แยกตามกลุ่มธุรกิจ"

Steps:
1. รอให้กราฟเส้นแสดงขึ้น
2. ดูที่มุมขวาบนของกราฟ
3. ควรเห็นปุ่ม Expand (🔍)
4. กดปุ่ม
5. Modal เปิดเต็มจอ

Expected:
✅ ปุ่ม Expand แสดง
✅ กดแล้ว Modal เปิด
✅ กราฟใน Modal ใหญ่ขึ้น
✅ กด X ปิดได้
```

**Test Case 2: Bar Chart (Vertical)**
```bash
Query: "รายได้แยกตามกลุ่มธุรกิจ"

Steps:
1. รอให้กราฟแท่งแสดงขึ้น
2. เปิด Console (Chrome DevTools)
3. ดู log message
4. ดูที่มุมขวาบนของกราฟ

Expected:
✅ Console log: "✅ DataChart: Rendering chart with expand button. Chart type: BAR"
✅ ปุ่ม Expand แสดง (ถ้าไม่แสดง → ดู Console เพื่อหาสาเหตุ)
```

**Test Case 3: Grouped Bar Chart**
```bash
Query: "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน เป็นกราฟ"

Steps:
1. รอให้กราฟแท่งเรียงกลุ่มแสดงขึ้น
2. เปิด Console
3. ดู log: "Chart type: GROUPED BAR"
4. ดูปุ่ม Expand

Expected:
✅ Console log แสดง "GROUPED BAR"
✅ ปุ่ม Expand แสดง
```

---

## 🔍 Debug: ทำไมปุ่มขยายไม่แสดง?

### **เช็คที่ Console Log:**

**ถ้าเห็น:**
```
❌ DataChart: analysis is null, chart will not render
```
**สาเหตุ:** AI ไม่สามารถสร้าง chart analysis ได้
- ข้อมูลอาจไม่มี numerical columns
- หรือ `visualization` prop เป็น 'table' ไม่ใช่ 'bar_chart'/'line_chart'

**วิธีแก้:**
1. เช็ค `message.visualization` ใน ChatBubble.tsx
2. ถ้า AI return `visualization: 'table'` → ปัญหาอยู่ที่ AI recommendation
3. ต้องแก้ที่ `schema_service.py` system prompt

---

**ถ้าเห็น:**
```
✅ DataChart: Rendering chart with expand button. Chart type: BAR
```
**แต่ยังไม่เห็นปุ่ม:**
- เช็ค CSS/styling อาจซ่อนปุ่ม
- เช็ค z-index อาจถูกบดด้วย element อื่น
- เช็ค Ionicons import ถูกต้องหรือไม่

---

**ถ้าไม่เห็น log เลย:**
- Component ไม่ได้ถูก render
- ข้อมูลไม่ผ่าน `data` prop มา
- Visualization type ไม่ใช่ chart

---

## 📋 Checklist

**CSV Export:**
- [x] เพิ่ม expo-clipboard
- [x] เพิ่ม expo-file-system
- [x] เพิ่ม expo-sharing
- [x] แก้ exportToCSV function
- [x] รองรับ Platform.OS === 'web'
- [x] รองรับ Mobile sharing
- [x] Fallback clipboard
- [ ] **TODO: ติดตั้ง dependencies**
- [ ] **TODO: ทดสอบบน Web**
- [ ] **TODO: ทดสอบบน Mobile**

**Expand Button:**
- [x] เพิ่ม console.log debug
- [x] ตรวจสอบ imports
- [x] ตรวจสอบ Button placement
- [ ] **TODO: ทดสอบบน Line Chart**
- [ ] **TODO: ทดสอบบน Bar Chart**
- [ ] **TODO: ดู Console logs**
- [ ] **TODO: Report ผลกลับมา**

---

## 🎯 ขั้นตอนถัดไป

1. **Run install:**
   ```bash
   cd frontend
   npm install
   ```

2. **Start app:**
   ```bash
   npm run web    # หรือ
   npm start      # แล้วเปิด Expo Go
   ```

3. **ทดสอบ CSV Export:**
   - ถามคำถาม → ดูตาราง → กดปุ่ม Download
   - Web: ควร download file
   - Mobile: ควร share dialog

4. **ทดสอบ Expand Button:**
   - ถามคำถาม → ดูกราฟ → ดูปุ่มมุมขวาบน
   - เปิด Console → ดู logs
   - รายงานผลว่าเห็นปุ่มหรือไม่

5. **รายงานผล:**
   - ถ้า CSV Export ใช้งานได้ → ✅
   - ถ้าปุ่ม Expand แสดงทุก chart type → ✅
   - ถ้ายังมีปัญหา → ส่ง Console logs มาให้ช่วย debug

---

## 📝 สรุป

**What Changed:**
- DataTable.tsx: ใช้ FileSystem + Sharing API แทน Share.share()
- DataChart.tsx: เพิ่ม debug logs
- package.json: เพิ่ม 3 dependencies

**What to Test:**
- CSV Export ใช้งานได้ทั้ง Web และ Mobile
- Expand button แสดงและใช้งานได้ทุก chart type

**Next:**
- ติดตั้ง dependencies
- ทดสอบทั้ง 2 features
- รายงานผล

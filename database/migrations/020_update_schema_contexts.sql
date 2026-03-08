UPDATE schema_contexts 
SET instruction_th = '
- **คำเตือน (Revenue Context):**
  - อย่ารวม ''รายได้อื่น'' (Other Revenue) ในการคำนวณรายได้ทั้งหมด ยกเว้น user สั่ง
  - หน่วยรายได้เป็น **บาท**
'
WHERE name = 'revenue';

UPDATE schema_contexts 
SET instruction_th = '
- **คำเตือน (Expense Context):**
  - ค่าใช้จ่ายแยกตามหมวดบัญชี (Account Group)
  - `gl_code` คือรหัสบัญชี, `account_name` คือชื่อบัญชี
  - **Visualization Rule:** ห้ามใช้ `gl_code` เป็น Label หรือ Legend ในกราฟเด็ดขาด ให้ใช้ `account_name` เสมอ (ยกเว้น User สั่งเจาะจงรหัส)
  - `amount` คือยอดค่าใช้จ่าย (เป็นตัวเลขติดลบ หรือบวกแล้วแต่การบันทึก ให้ระวังเรื่อง SUM)
  - ปกติถ้าเป็น Expense table ค่าอาจจะเป็น + หรือ - ให้เช็ค Data range ใน Schema
'
WHERE name = 'expense';

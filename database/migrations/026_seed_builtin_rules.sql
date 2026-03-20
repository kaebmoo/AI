-- Migration 026: Seed builtin validation rules into schema_business_rules
-- Moves 7 hardcoded BUILTIN_RULES from nt_validation_mcp.py to DB
-- Uses ON CONFLICT to be idempotent (safe to run multiple times)

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('DATE_CONVERSION', 'ต้องแปลง DATE จาก Unix Timestamp',
        'คอลัมน์ DATE เป็น Unix Timestamp (ms) ควรใช้ YEAR/MONTH แทน หรือแปลงด้วย date(DATE/1000, ''unixepoch'')',
        'warning', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('THAI_COLUMN_QUOTES', 'คอลัมน์ภาษาไทยต้องใส่ quotes',
        'คอลัมน์ภาษาไทยต้องใส่ double quotes เช่น "กลุ่มธุรกิจ"',
        'error', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('REVENUE_UNIT', 'หน่วยรายได้เป็นบาท',
        'REVENUE_VALUE มีหน่วยเป็นบาท (ไม่ใช่ล้านบาท)',
        'info', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('GROUP_BY_AGGREGATE', 'SELECT columns ต้องอยู่ใน GROUP BY หรือ aggregate',
        'ตรวจสอบว่าคอลัมน์ใน SELECT อยู่ใน GROUP BY หรือใช้ aggregate function',
        'warning', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('NO_SELECT_STAR', 'หลีกเลี่ยง SELECT *',
        'ควรระบุคอลัมน์ที่ต้องการแทน SELECT *',
        'info', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('LIMIT_REQUIRED', 'ควรมี LIMIT',
        'ควรใส่ LIMIT เพื่อจำกัดจำนวนผลลัพธ์',
        'info', 1)
ON CONFLICT(rule_code) DO NOTHING;

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity, is_active)
VALUES ('YEAR_FILTER', 'ควรกรองปีข้อมูล',
        'ควรระบุ YEAR ใน WHERE clause เพื่อจำกัดขอบเขตข้อมูล',
        'warning', 1)
ON CONFLICT(rule_code) DO NOTHING;

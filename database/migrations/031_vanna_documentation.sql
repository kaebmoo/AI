-- ============================================================
-- Migration 031: Vanna Documentation — manual knowledge docs for RAG
-- ============================================================

CREATE TABLE IF NOT EXISTS vanna_documentation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_key         TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    category        TEXT DEFAULT 'guide',
    context_name    TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vanna_doc_active ON vanna_documentation(is_active);
CREATE INDEX IF NOT EXISTS idx_vanna_doc_category ON vanna_documentation(category);
CREATE INDEX IF NOT EXISTS idx_vanna_doc_context ON vanna_documentation(context_name);

CREATE TRIGGER IF NOT EXISTS update_vanna_doc_timestamp
AFTER UPDATE ON vanna_documentation
FOR EACH ROW
BEGIN
    UPDATE vanna_documentation SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- Brain sync tracking keys (both seeded as system/system)
-- ============================================================
INSERT OR IGNORE INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('last_brain_sync_at', NULL, 'system', 'system', 'Last Brain Sync', 'Timestamp of last successful Vanna brain sync', 1, 0),
    ('last_brain_relevant_change_at', NULL, 'system', 'system', 'Last Brain-Relevant Change', 'Timestamp of last change affecting Vanna brain content', 1, 0);

-- ============================================================
-- Seed data — manual knowledge docs
-- Each doc is self-contained for RAG retrieval.
-- Does NOT duplicate content from schema_business_rules or schema_semantic_mapping.
-- ============================================================

INSERT OR IGNORE INTO vanna_documentation (doc_key, title, content, category, context_name) VALUES
(
    'hierarchy_concept',
    'Hierarchy Levels and Cross-Level OR Danger',
    'ระบบ NT ใช้ organization hierarchy หลายระดับ (DIVISION > GROUP > DEPARTMENT > SECTION > COST_CENTER)

กฎสำคัญ: ห้าม OR ข้ามระดับ hierarchy เด็ดขาด
ตัวอย่างที่ผิด: WHERE DIVISION = ''สายงานX'' OR DEPARTMENT = ''ฝ่ายY''
เหตุผล: DIVISION มีหลาย DEPARTMENT อยู่ข้างใต้ การ OR ข้ามระดับจะทำให้นับซ้ำหลายสิบเท่า

วิธีที่ถูกต้อง:
1. ถ้าต้องการดู DIVISION + DEPARTMENT พร้อมกัน → ใช้ AND (drill-down)
2. ถ้าต้องการเปรียบเทียบ → ใช้ OR ภายในระดับเดียวกัน เช่น DIVISION = ''A'' OR DIVISION = ''B''
3. ถ้าต้องการ drill-down → GROUP BY ระดับล่างลงไป โดย WHERE ระดับบน

แต่ละ context อาจมี hierarchy ต่างกัน ตรวจสอบจาก master_hierarchy ก่อนสร้าง query',
    'guide',
    NULL
),
(
    'multi_context_workflow',
    'Multi-Context Architecture and Routing',
    'ระบบรองรับหลาย data context ผ่านตาราง schema_contexts
แต่ละ context มี main_view ของตัวเอง (เช่น revenue_search, v_expense_mart, TRN_PL_COSTTYPE)

การ route คำถามไปยัง context ที่ถูกต้อง:
1. ระบบตรวจ detection_keywords ในคำถาม
2. keyword เช่น "รายได้" → context revenue, "ค่าใช้จ่าย" → context expense
3. แต่ละ context มี instruction_th สำหรับ AI ใช้เป็น system prompt เฉพาะ
4. semantic_mapping, business_rules, golden_examples มี context_name scope ได้

หมายเหตุ: SQL ต้อง query จาก main_view ของ context เท่านั้น ห้ามข้าม context
ถ้าคำถามเกี่ยวกับหลาย context ต้องแยก query แล้วรวมผลลัพธ์',
    'workflow',
    NULL
),
(
    'tables_collaboration_workflow',
    'How Config Tables Collaborate in SQL Generation',
    'ขั้นตอนการสร้าง SQL จาก config tables ที่ทำงานร่วมกัน:

Step 0: Context Routing (schema_contexts)
  - ตรวจ keyword ในคำถาม → เลือก context + main_view

Step 1: Semantic Mapping (schema_semantic_mapping)
  - แปลงคำย่อ/คำธุรกิจเป็น SQL condition
  - เช่น "นป." → organization_group_abbr = ''นป.''

Step 1.5: Hierarchy Level Detection (master_hierarchy)
  - ตรวจว่า keyword อยู่ระดับไหน → ป้องกัน cross-level OR

Step 2: Few-Shot Examples (golden_examples)
  - หา pattern คำถามที่คล้ายกันเพื่อให้ AI ใช้เป็นตัวอย่าง

Step 2.5: Value Lookup (keyword_value_index)
  - จับคู่ keyword ของผู้ใช้กับค่าจริงใน DB

Step 3: Schema Metadata (schema_metadata)
  - ตรวจ is_summable, is_groupable, data_type สำหรับ column ที่ใช้

Step 4: Business Rules (schema_business_rules)
  - enforce กฎ SQL ทั้งหมด (unit, quoting, syntax)',
    'workflow',
    NULL
),
(
    'value_lookup_system',
    'Value Lookup System — keyword_value_index + hierarchy_values',
    'ระบบ value lookup ช่วยจับคู่คำที่ผู้ใช้พิมพ์กับค่าจริงในฐานข้อมูล

keyword_value_index:
- เก็บ keyword → column + value mapping
- รองรับ alias หลายคำสำหรับค่าเดียวกัน
- เช่น "สายงานเทคโนโลยี", "สทค." → DIVISION = ''สายงานเทคโนโลยีดิจิทัล''
- ใช้ longest-match algorithm จาก get_known_terms()

master_hierarchy_values:
- เก็บค่าจริงพร้อม parent chain สำหรับ drill-down
- เช่น DEPARTMENT = ''ฝ่ายX'' → parent GROUP = ''กลุ่มY'' → parent DIVISION = ''สายงานZ''
- AI ใช้ parent chain เพื่อ validate ว่า filter condition สอดคล้องกัน

การทำงานร่วมกัน:
1. ผู้ใช้พิมพ์ keyword → keyword_value_index จับคู่ค่า
2. ค่าที่ได้ → ตรวจกับ hierarchy_values ว่าอยู่ระดับไหน
3. ป้องกัน cross-level OR โดยอัตโนมัติ',
    'guide',
    NULL
),
(
    'sqlite_syntax_pitfalls',
    'SQLite Syntax Pitfalls Beyond Basic Rules',
    'คำเตือนเพิ่มเติมสำหรับ SQLite syntax ที่ business_rules ไม่ได้ครอบคลุม:

1. CASE sensitivity ใน LIKE:
   - SQLite LIKE เป็น case-insensitive สำหรับ ASCII แต่ case-sensitive สำหรับ Unicode/Thai
   - ใช้ = แทน LIKE เมื่อรู้ค่าแน่ชัด จะเร็วกว่าและแม่นยำกว่า

2. GROUP BY + SELECT columns:
   - ทุก column ใน SELECT ต้องอยู่ใน GROUP BY หรือ aggregate function
   - SQLite อนุญาต bare columns แต่ผลลัพธ์จะ unpredictable

3. NULL handling:
   - NULL ไม่เท่ากับ string ว่าง ''''
   - ใช้ IS NULL / IS NOT NULL ไม่ใช่ = NULL
   - SUM() จะ ignore NULL แต่ถ้าทุกค่าเป็น NULL จะได้ NULL (ใช้ COALESCE)

4. Date filtering:
   - ใช้ YEAR/MONTH columns แทนการแปลง DATE (Unix timestamp ms)
   - ถ้าจำเป็นต้องใช้ DATE: date(DATE/1000, ''unixepoch'')

5. Thai column quoting:
   - Column ชื่อภาษาไทยต้อง double quote เสมอ: "กลุ่มธุรกิจ"
   - ห้ามใช้ single quote สำหรับชื่อ column',
    'best_practice',
    NULL
);

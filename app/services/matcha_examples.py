"""
NT AI Assistant - Matcha Examples
=======================================
Few-shot examples และ semantic mappings สำหรับ Matcha AI model

ใช้ร่วมกับ MatchaProvider เพื่อปรับปรุงความแม่นยำในการสร้าง SQL
"""

import sqlite3
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


# Static few-shot examples สำหรับ Matcha
MATCHA_EXAMPLES = [
    # === คำถามตรวจสอบข้อมูล (ไม่ต้อง exclude รายได้อื่น) ===
    {
        "question": "มีข้อมูลรายได้ไหม",
        "sql": "SELECT COUNT(*) as total_records, MIN(year) as min_year, MAX(year) as max_year, MIN(month) as min_month, MAX(month) as max_month FROM revenue_search",
        "explanation": "ตรวจสอบว่ามีข้อมูลรายได้ในระบบหรือไม่ และช่วงเวลาของข้อมูล"
    },
    {
        "question": "ข้อมูลรายได้มีถึงเดือนอะไร",
        "sql": "SELECT year, month, COUNT(*) as records FROM revenue_search GROUP BY year, month ORDER BY year DESC, month DESC LIMIT 5",
        "explanation": "แสดง 5 เดือนล่าสุดที่มีข้อมูลรายได้"
    },
    {
        "question": "มีข้อมูลกี่รายการ",
        "sql": "SELECT COUNT(*) as total_records FROM revenue_search",
        "explanation": "นับจำนวนรายการข้อมูลทั้งหมด"
    },
    # === คำถามรายได้รวม (ต้อง exclude รายได้อื่น) ===
    {
        "question": "รายได้รวมเดือนมกราคม 2568",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE year = 2025 AND month = 1 AND BUSINESS_GROUP != 'รายได้อื่น'",
        "explanation": "รายได้รวมทั้งหมดในเดือนมกราคม 2568 (ค.ศ. 2025) ไม่รวมรายได้อื่น"
    },
    {
        "question": "รายได้ นป. ปี 2568",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE organization_group_abbr = 'นป.' AND year = 2025",
        "explanation": "รายได้ของกลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ (นป.) ในปี 2568"
    },
    {
        "question": "รายได้แยกตามกลุ่มผลิตภัณฑ์",
        "sql": "SELECT BUSINESS_GROUP, SUM(revenue) as total_revenue FROM revenue_search GROUP BY BUSINESS_GROUP ORDER BY total_revenue DESC",
        "explanation": "รายได้แยกตามกลุ่มผลิตภัณฑ์ (Mobile, Fixed Line, Digital, etc.)"
    },
    {
        "question": "รายได้อสังหาริมทรัพย์แยกตามฝ่าย",
        "sql": "SELECT department, SUM(revenue) as total_revenue FROM revenue_search WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์' GROUP BY department ORDER BY total_revenue DESC",
        "explanation": "รายได้จากอสังหาริมทรัพย์/สินทรัพย์ แยกตามฝ่าย"
    },
    {
        "question": "5 ฝ่ายที่มีรายได้สูงสุด",
        "sql": "SELECT department, SUM(revenue) as total_revenue FROM revenue_search GROUP BY department ORDER BY total_revenue DESC LIMIT 5",
        "explanation": "5 ฝ่ายที่มีรายได้สูงที่สุด"
    },
    {
        "question": "หน่วยงานไหนมีรายได้มากที่สุด 5 อันดับแรก และน้อยที่สุด 5 อันดับแรก",
        "sql": """SELECT 'มากสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total
    FROM revenue_search
    GROUP BY department
    ORDER BY total DESC
    LIMIT 5
)
UNION ALL
SELECT 'น้อยสุด' as category, department, total FROM (
    SELECT department, SUM(revenue) as total
    FROM revenue_search
    GROUP BY department
    ORDER BY total ASC
    LIMIT 5
)""",
        "explanation": "Top 5 และ Bottom 5 หน่วยงานตามรายได้"
    },
    {
        "question": "รายได้ บชง. เดือน 1 ถึง 11 ปี 2568",
        "sql": "SELECT month, SUM(revenue) as total_revenue FROM revenue_search WHERE department_abbr = 'บชง.' AND year = 2025 AND CAST(month AS INTEGER) BETWEEN 1 AND 11 GROUP BY month ORDER BY CAST(month AS INTEGER)",
        "explanation": "รายได้ฝ่ายบัญชีบริหาร เดือน 1-11 ปี 2568"
    },
    {
        "question": "รายได้มือถือ",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE BUSINESS_GROUP = 'Mobile'",
        "explanation": "รายได้จากกลุ่มผลิตภัณฑ์มือถือ (Mobile)"
    },
    {
        "question": "สัดส่วนรายได้ของกลุ่มธุรกิจ Fixed Line & Broadband",
        "sql": """SELECT
    'Fixed Line & Broadband' as BUSINESS_GROUP,
    SUM(revenue) as group_revenue,
    (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น') as total_revenue,
    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'), 2) as percentage
FROM revenue_search
WHERE BUSINESS_GROUP = 'Fixed Line & Broadband'""",
        "explanation": "สัดส่วนรายได้ Fixed Line & Broadband เทียบกับรายได้รวม (ไม่นับรายได้อื่น)"
    },
    {
        "question": "รายได้รวมทั้งหมด (ไม่รวมรายได้อื่น)",
        "sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'",
        "explanation": "รายได้รวมจากธุรกิจหลัก ไม่รวมรายได้อื่นและผลตอบแทนทางการเงิน"
    },
    {
        "question": "สัดส่วนรายได้แยกตามกลุ่มธุรกิจ",
        "sql": """SELECT
    BUSINESS_GROUP,
    SUM(revenue) as group_revenue,
    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'), 2) as percentage
FROM revenue_search
WHERE BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY BUSINESS_GROUP
ORDER BY group_revenue DESC""",
        "explanation": "สัดส่วนรายได้แต่ละกลุ่มธุรกิจ (ไม่นับรายได้อื่น)"
    },
    # === คำถามแยกรายได้ตามกลุ่มธุรกิจ (ต้อง exclude รายได้อื่น) ===
    {
        "question": "ภาคเหนือมีรายได้จากอะไรบ้าง",
        "sql": """SELECT
    BUSINESS_GROUP as กลุ่มธุรกิจ,
    SUM(revenue) as รายได้,
    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE organization_group_abbr = 'นป.' AND BUSINESS_GROUP != 'รายได้อื่น'), 2) as สัดส่วน
FROM revenue_search
WHERE organization_group_abbr = 'นป.' AND BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY BUSINESS_GROUP
ORDER BY รายได้ DESC""",
        "explanation": "รายได้ภาคเหนือ (นป.) แยกตามกลุ่มธุรกิจ ไม่รวมรายได้อื่นเพราะไม่ใช่รายได้จากธุรกิจหลัก"
    },
    {
        "question": "รายได้แยกตามกลุ่มธุรกิจ",
        "sql": """SELECT
    BUSINESS_GROUP as กลุ่มธุรกิจ,
    SUM(revenue) as รายได้,
    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'), 2) as สัดส่วน
FROM revenue_search
WHERE BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY BUSINESS_GROUP
ORDER BY รายได้ DESC""",
        "explanation": "รายได้แยกตามกลุ่มธุรกิจ ไม่รวมรายได้อื่นเพราะไม่ใช่รายได้จากธุรกิจหลัก"
    },
    {
        "question": "หน่วยงานนี้มีรายได้จากผลิตภัณฑ์อะไรบ้าง",
        "sql": """SELECT
    BUSINESS_GROUP as กลุ่มธุรกิจ,
    SUM(revenue) as รายได้
FROM revenue_search
WHERE department_abbr = 'XXX' AND BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY BUSINESS_GROUP
ORDER BY รายได้ DESC""",
        "explanation": "รายได้หน่วยงานแยกตามกลุ่มธุรกิจ ไม่รวมรายได้อื่น"
    }
]


class MatchaExamplesService:
    """Service สำหรับจัดการ few-shot examples และ semantic mappings สำหรับ Matcha"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._semantic_mappings_cache: Optional[List[Dict]] = None
        self._golden_examples_cache: Optional[List[Dict]] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_semantic_mappings(self, keyword_type: Optional[str] = None) -> List[Dict]:
        """
        โหลด semantic mappings จาก database

        Args:
            keyword_type: Filter by type ('abbreviation', 'term', 'synonym')

        Returns:
            List of mapping dicts
        """
        if self._semantic_mappings_cache is not None and keyword_type is None:
            return self._semantic_mappings_cache

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if keyword_type:
                cursor.execute("""
                    SELECT keyword, keyword_type, target_column, target_condition, description
                    FROM schema_semantic_mapping
                    WHERE is_active = 1 AND keyword_type = ?
                    ORDER BY priority DESC, keyword
                """, (keyword_type,))
            else:
                cursor.execute("""
                    SELECT keyword, keyword_type, target_column, target_condition, description
                    FROM schema_semantic_mapping
                    WHERE is_active = 1
                    ORDER BY priority DESC, keyword
                """)

            mappings = [dict(row) for row in cursor.fetchall()]

            if keyword_type is None:
                self._semantic_mappings_cache = mappings

            return mappings

        except sqlite3.OperationalError as e:
            logger.warning(f"Could not load semantic mappings: {e}")
            return []
        finally:
            conn.close()

    def get_golden_examples(self, category: Optional[str] = None) -> List[Dict]:
        """
        โหลด golden examples จาก database

        Args:
            category: Filter by category

        Returns:
            List of example dicts
        """
        if self._golden_examples_cache is not None and category is None:
            return self._golden_examples_cache

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if category:
                cursor.execute("""
                    SELECT question_pattern, expected_sql, category
                    FROM golden_examples
                    WHERE is_active = 1 AND category = ?
                    ORDER BY id DESC
                """, (category,))
            else:
                cursor.execute("""
                    SELECT question_pattern, expected_sql, category
                    FROM golden_examples
                    WHERE is_active = 1
                    ORDER BY id DESC
                """)

            examples = [dict(row) for row in cursor.fetchall()]

            if category is None:
                self._golden_examples_cache = examples

            return examples

        except sqlite3.OperationalError as e:
            logger.warning(f"Could not load golden examples: {e}")
            return []
        finally:
            conn.close()

    def detect_keywords_in_question(self, question: str) -> List[Dict]:
        """
        ตรวจจับ keywords จาก semantic mappings ในคำถาม

        Args:
            question: คำถามจากผู้ใช้

        Returns:
            List of detected mappings
        """
        mappings = self.get_semantic_mappings()
        detected = []

        question_lower = question.lower()

        for mapping in mappings:
            keyword = mapping['keyword']
            # Check exact match or as part of word
            if keyword.lower() in question_lower or keyword in question:
                detected.append(mapping)

        return detected

    def build_semantic_hints(self, question: str) -> str:
        """
        สร้าง hints จาก semantic mappings ที่ตรวจจับได้

        Args:
            question: คำถามจากผู้ใช้

        Returns:
            Hint text สำหรับเพิ่มใน prompt
        """
        detected = self.detect_keywords_in_question(question)

        if not detected:
            return ""

        hints = ["## คำสำคัญที่ตรวจจับได้:"]

        for mapping in detected:
            hints.append(
                f"- '{mapping['keyword']}' = {mapping['description']} "
                f"→ ใช้ `{mapping['target_column']} {mapping['target_condition']}`"
            )

        return "\n".join(hints)

    def get_all_examples(self) -> List[Dict]:
        """
        รวม static examples และ golden examples จาก database

        Returns:
            List of all examples
        """
        all_examples = list(MATCHA_EXAMPLES)  # Copy static examples

        # Add golden examples from database
        golden = self.get_golden_examples()
        for ex in golden:
            all_examples.append({
                "question": ex['question_pattern'],
                "sql": ex['expected_sql'],
                "explanation": f"ตัวอย่าง {ex.get('category', 'general')}"
            })

        return all_examples


def get_matcha_few_shot_prompt(examples: Optional[List[Dict]] = None) -> str:
    """
    สร้าง few-shot examples prompt สำหรับ Matcha

    Args:
        examples: List of examples หรือใช้ default MATCHA_EXAMPLES

    Returns:
        Formatted prompt text
    """
    if examples is None:
        examples = MATCHA_EXAMPLES

    prompt = "## ตัวอย่างคำถามและ SQL ที่ถูกต้อง\n\n"

    for i, ex in enumerate(examples[:6], 1):  # Limit to 6 examples
        prompt += f"### ตัวอย่าง {i}\n"
        prompt += f"**คำถาม:** {ex['question']}\n"
        prompt += f"**SQL:**\n```sql\n{ex['sql']}\n```\n"
        prompt += f"**คำอธิบาย:** {ex['explanation']}\n\n"

    return prompt


def get_matcha_few_shot_messages(examples: Optional[List[Dict]] = None) -> List[Dict]:
    """
    สร้าง few-shot examples เป็น message format สำหรับ OpenAI-compatible API

    Args:
        examples: List of examples หรือใช้ default MATCHA_EXAMPLES

    Returns:
        List of message dicts (user/assistant pairs)
    """
    if examples is None:
        examples = MATCHA_EXAMPLES

    messages = []

    for ex in examples[:5]:  # Limit to 5 examples
        # User message
        messages.append({
            "role": "user",
            "content": ex['question']
        })

        # Assistant response
        messages.append({
            "role": "assistant",
            "content": f"""```sql
{ex['sql']}
```

คำอธิบาย: {ex['explanation']}"""
        })

    return messages


def get_abbreviation_reference() -> str:
    """
    สร้าง reference text สำหรับคำย่อที่ใช้บ่อย

    Returns:
        Reference text
    """
    return """## คำย่อหน่วยงานที่ใช้บ่อย

### คำย่อระดับกลุ่ม (organization_group_abbr)
- **นป.** = กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ
- **นต.** = กลุ่มขายและปฏิบัติการลูกค้า ภาคตะวันออกเฉียงเหนือ
- **กน.** = กลุ่มขายและปฏิบัติการลูกค้า ภาคกลาง
- **ตน.** = กลุ่มขายและปฏิบัติการลูกค้า ภาคใต้
- **อป.** = กลุ่มขายและปฏิบัติการลูกค้า ภาคตะวันออก
- **ปต.** = กลุ่มขายและปฏิบัติการลูกค้า กรุงเทพและปริมณฑล

### คำย่อระดับฝ่าย (department_abbr)
- **บชง.** = ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ
- **อป.1** = ฝ่ายขายฯ ภาคตะวันออกตอนบน
- **อป.2** = ฝ่ายขายฯ ภาคตะวันออกตอนล่าง
- **กน.1** = ฝ่ายขายฯ ภาคกลางตอนบน
- **กน.2** = ฝ่ายขายฯ ภาคกลางตอนล่าง

### คำย่อระดับสายงาน (division_abbr)
- **สญ.** = สายงานขายและบริการ
- **บก.** = สายงานบริหารกลาง

### วิธีใช้คำย่อใน SQL
```sql
-- ค้นหาระดับกลุ่ม
WHERE organization_group_abbr = 'นป.'

-- ค้นหาระดับฝ่าย
WHERE department_abbr = 'บชง.'

-- ค้นหาระดับสายงาน
WHERE division_abbr = 'สญ.'
```
"""


def get_business_term_reference() -> str:
    """
    สร้าง reference text สำหรับคำศัพท์ธุรกิจ

    Returns:
        Reference text
    """
    return """## คำศัพท์ธุรกิจและการแปลงเป็น SQL

### กลุ่มผลิตภัณฑ์ (BUSINESS_GROUP)
- "มือถือ" / "mobile" → `BUSINESS_GROUP = 'Mobile'`
- "โทรศัพท์บ้าน" / "fixed line" → `BUSINESS_GROUP = 'Fixed Line'`
- "ดิจิทัล" / "digital" → `BUSINESS_GROUP = 'Digital'`

### กลุ่มบริการ (SERVICE_GROUP)
- "อสังหาริมทรัพย์" / "ทรัพย์สิน" → `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
- "ค้าปลีก" / "retail" → `SERVICE_GROUP LIKE '%ค้าปลีก%'`

### การค้นหาตามพื้นที่
- "จังหวัด" → ใช้ column `section` เช่น `section LIKE '%จันทบุรี%'`
- "ภาค" → ใช้ `organization_group_abbr` หรือ `organization_group`
"""


# Convenience function for backward compatibility
def get_matcha_few_shot_examples() -> str:
    """Get formatted few-shot examples for Matcha (backward compatible)"""
    return get_matcha_few_shot_prompt()

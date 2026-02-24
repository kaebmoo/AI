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


def _get_latest_year(db_path: str = None) -> int:
    """ดึงปีล่าสุดจากฐานข้อมูลจริง ไม่ hardcode"""
    if not db_path:
        try:
            from app.config import settings
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        except Exception:
            db_path = "nt_fi_report.sqlite"
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT MAX(year) FROM revenue_search").fetchone()
        conn.close()
        return row[0] if row and row[0] else 2025
    except Exception:
        return 2025


def _get_exclude_condition(db_path: str = None) -> str:
    """ดึง exclude condition จาก schema_business_rules หรือ default"""
    import re
    if not db_path:
        try:
            from app.config import settings
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        except Exception:
            db_path = "nt_fi_report.sqlite"
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT example_correct FROM schema_business_rules WHERE rule_code = 'EXCLUDE_OTHER_REVENUE' AND is_active = 1 LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0]:
            # Extract the WHERE condition (e.g. "BUSINESS_GROUP != 'รายได้อื่น'")
            match = re.search(r"([\w]+\s*!=\s*'[^']+')", row[0])
            if match:
                return match.group(1)
    except Exception:
        pass
    return "BUSINESS_GROUP != 'รายได้อื่น'"  # Safety net default


def build_examples(db_path: str = None) -> List[Dict]:
    """สร้าง few-shot examples แบบ dynamic — ปี + business rules ดึงจาก DB จริง"""
    Y = _get_latest_year(db_path)
    Y_TH = Y + 543
    EXCLUDE = _get_exclude_condition(db_path)

    return [
        # === คำถามตรวจสอบข้อมูล ===
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
        # === คำถามรายได้รวม ===
        {
            "question": f"รายได้รวมเดือนมกราคม {Y_TH}",
            "sql": f"SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE year = {Y} AND month = 1 AND {EXCLUDE}",
            "explanation": f"รายได้รวมทั้งหมดในเดือนมกราคม {Y_TH} (ค.ศ. {Y}) ไม่รวมรายได้อื่น"
        },
        {
            "question": f"รายได้ นป. ปี {Y_TH}",
            "sql": f"SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE organization_group_abbr = 'นป.' AND year = {Y}",
            "explanation": f"รายได้ของกลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ (นป.) ในปี {Y_TH}"
        },
        {
            "question": "รายได้แยกตามกลุ่มผลิตภัณฑ์",
            "sql": "SELECT BUSINESS_GROUP, SUM(revenue) as total_revenue FROM revenue_search GROUP BY BUSINESS_GROUP ORDER BY total_revenue DESC",
            "explanation": "รายได้แยกตามกลุ่มผลิตภัณฑ์"
        },
        {
            "question": "5 ฝ่ายที่มีรายได้สูงสุด",
            "sql": "SELECT department, SUM(revenue) as total_revenue FROM revenue_search GROUP BY department ORDER BY total_revenue DESC LIMIT 5",
            "explanation": "5 ฝ่ายที่มีรายได้สูงที่สุด"
        },
        {
            "question": f"รายได้ บชง. เดือน 1 ถึง 11 ปี {Y_TH}",
            "sql": f"SELECT month, SUM(revenue) as total_revenue FROM revenue_search WHERE department_abbr = 'บชง.' AND year = {Y} AND CAST(month AS INTEGER) BETWEEN 1 AND 11 GROUP BY month ORDER BY CAST(month AS INTEGER)",
            "explanation": f"รายได้ฝ่ายบัญชีบริหาร เดือน 1-11 ปี {Y_TH}"
        },
        {
            "question": "สัดส่วนรายได้แยกตามกลุ่มธุรกิจ",
            "sql": f"""SELECT
    BUSINESS_GROUP,
    SUM(revenue) as group_revenue,
    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE {EXCLUDE}), 2) as percentage
FROM revenue_search
WHERE {EXCLUDE}
GROUP BY BUSINESS_GROUP
ORDER BY group_revenue DESC""",
            "explanation": "สัดส่วนรายได้แต่ละกลุ่มธุรกิจ (ไม่นับรายได้อื่น)"
        },
        {
            "question": "หน่วยงานนี้มีรายได้จากผลิตภัณฑ์อะไรบ้าง",
            "sql": f"""SELECT
    BUSINESS_GROUP as กลุ่มธุรกิจ,
    SUM(revenue) as รายได้
FROM revenue_search
WHERE department_abbr = 'XXX' AND {EXCLUDE}
GROUP BY BUSINESS_GROUP
ORDER BY รายได้ DESC""",
            "explanation": "รายได้หน่วยงานแยกตามกลุ่มธุรกิจ ไม่รวมรายได้อื่น"
        }
    ]


# Backward compatibility: MATCHA_EXAMPLES as lazy-loaded dynamic list
def _get_examples():
    return build_examples()

# For code that imports MATCHA_EXAMPLES directly
MATCHA_EXAMPLES = build_examples()


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
        all_examples = list(build_examples(self.db_path))  # Dynamic examples from DB year

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
        examples: List of examples หรือใช้ build_examples()

    Returns:
        Formatted prompt text
    """
    if examples is None:
        examples = build_examples()

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
        examples: List of examples หรือใช้ build_examples()

    Returns:
        List of message dicts (user/assistant pairs)
    """
    if examples is None:
        examples = build_examples()

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


def get_business_term_reference(db_path: str = None) -> str:
    """
    สร้าง reference text สำหรับคำศัพท์ธุรกิจ — ดึงจาก schema_semantic_mapping ใน DB
    """
    if not db_path:
        try:
            from app.config import settings
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        except Exception:
            db_path = "nt_fi_report.sqlite"

    lines = ["## คำศัพท์ธุรกิจและการแปลงเป็น SQL (จาก Semantic Mappings)\n"]

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT keyword, target_column, target_condition, description
            FROM schema_semantic_mapping
            WHERE is_active = 1 AND keyword_type = 'term'
            ORDER BY target_column, keyword
        """).fetchall()
        conn.close()

        if rows:
            current_col = ""
            for keyword, col, condition, desc in rows:
                if col != current_col:
                    lines.append(f"\n### {col}")
                    current_col = col
                desc_text = f" ({desc})" if desc else ""
                lines.append(f'- "{keyword}" → `{col} {condition}`{desc_text}')
        else:
            lines.append("ยังไม่มี semantic mappings ในระบบ — เพิ่มได้ผ่าน Admin UI")

    except Exception as e:
        lines.append(f"ไม่สามารถโหลด mappings: {e}")

    return "\n".join(lines)


# Convenience function for backward compatibility
def get_matcha_few_shot_examples() -> str:
    """Get formatted few-shot examples for Matcha (backward compatible)"""
    return get_matcha_few_shot_prompt()

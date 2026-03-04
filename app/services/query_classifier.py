"""
NT AI Assistant - Query Complexity Classifier
================================================
Rule-based classification of query complexity
to select appropriate model tier (cheap vs mid).

No LLM token cost — uses regex patterns only.

Usage:
    classifier = QueryComplexityClassifier()
    tier = classifier.classify("รายได้เดือนมกราคม")  # "cheap"
    tier = classifier.classify("เปรียบเทียบรายได้ปีนี้กับปีก่อน")  # "mid"
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class QueryComplexityClassifier:
    """Classify query complexity for tier-based cost control"""

    # Complex patterns → use mid-tier model
    COMPLEX_PATTERNS = [
        r"เปรียบเทียบ", r"เทียบ", r"แนวโน้ม", r"trend",
        r"ยอดสูงสุด.*ต่ำสุด", r"สัดส่วน", r"ร้อยละ", r"เปอร์เซ็นต์",
        r"year.over.year", r"month.over.month", r"yoy", r"mom",
        r"การเปลี่ยนแปลง", r"เพิ่มขึ้น.*ลดลง", r"ลดลง.*เพิ่มขึ้น",
        r"วิเคราะห์", r"สรุป.*แยกตาม.*แยกตาม",  # multiple dimensions
        r"top\s*\d+", r"อันดับ",
        r"pivot", r"cross.tab",
        r"subquery", r"nested",
    ]

    # Simple patterns → use cheap-tier model
    SIMPLE_PATTERNS = [
        r"^รายได้\s*เดือน", r"^ค่าใช้จ่าย\s*เดือน",
        r"^ยอดรวม", r"^ทั้งหมด",
        r"^รายได้\s*ปี", r"^ค่าใช้จ่าย\s*ปี",
        r"รายได้รวม", r"ค่าใช้จ่ายรวม",
        r"เท่าไหร่$", r"เท่าไร$",
        r"กี่บาท$",
    ]

    def classify(self, question: str, force_tier: Optional[str] = None) -> str:
        """
        Classify query complexity.

        Args:
            question: User's question text
            force_tier: Admin override (if set, always returns this)

        Returns:
            "cheap" or "mid"
        """
        if force_tier:
            return force_tier

        q = question.lower().strip()

        # Check complex patterns first
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, q):
                logger.debug(f"Query classified as 'mid' (matched: {pattern})")
                return "mid"

        # Check simple patterns
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, q):
                logger.debug(f"Query classified as 'cheap' (matched: {pattern})")
                return "cheap"

        # Default: cheap (most queries are simple aggregations)
        return "cheap"


# Singleton
query_classifier = QueryComplexityClassifier()

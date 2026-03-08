"""
NT AI Assistant - Query Complexity Classifier
================================================
Rule-based classification of query complexity
to select appropriate model tier (cheap vs mid).

No LLM token cost — uses regex patterns only.
Patterns are loaded from `query_complexity_patterns` table with in-memory cache.

Usage:
    classifier = QueryComplexityClassifier()
    tier = classifier.classify("รายได้เดือนมกราคม")  # "cheap"
    tier = classifier.classify("เปรียบเทียบรายได้ปีนี้กับปีก่อน")  # "mid"
"""

import re
import time
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Hardcoded fallback patterns — used only when DB is unavailable
_HARDCODED_COMPLEX = [
    r"เปรียบเทียบ", r"เทียบ", r"แนวโน้ม", r"trend",
    r"ยอดสูงสุด.*ต่ำสุด", r"สัดส่วน", r"ร้อยละ", r"เปอร์เซ็นต์",
    r"year.over.year", r"month.over.month", r"yoy", r"mom",
    r"การเปลี่ยนแปลง", r"เพิ่มขึ้น.*ลดลง", r"ลดลง.*เพิ่มขึ้น",
    r"วิเคราะห์", r"สรุป.*แยกตาม.*แยกตาม",
    r"top\s*\d+", r"อันดับ",
    r"pivot", r"cross.tab",
    r"subquery", r"nested",
]

_HARDCODED_SIMPLE = [
    r"^รายได้\s*เดือน", r"^ค่าใช้จ่าย\s*เดือน",
    r"^ยอดรวม", r"^ทั้งหมด",
    r"^รายได้\s*ปี", r"^ค่าใช้จ่าย\s*ปี",
    r"รายได้รวม", r"ค่าใช้จ่ายรวม",
    r"เท่าไหร่$", r"เท่าไร$",
    r"กี่บาท$",
]

# In-memory cache
_patterns_cache: Optional[Dict[str, List[str]]] = None
_patterns_cache_ts: float = 0.0
_PATTERNS_CACHE_TTL = 3600  # 1 hour


def _load_patterns_from_db() -> Optional[Dict[str, List[str]]]:
    """Load active patterns from query_complexity_patterns table."""
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from sqlalchemy import text
            rows = db.execute(text(
                "SELECT tier, pattern FROM query_complexity_patterns WHERE is_active = 1"
            )).fetchall()
            result: Dict[str, List[str]] = {"complex": [], "simple": []}
            for row in rows:
                tier = row[0]
                if tier in result:
                    result[tier].append(row[1])
            return result
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not load patterns from DB: {e}")
        return None


def get_patterns() -> Dict[str, List[str]]:
    """Get patterns with cache. Falls back to hardcoded if DB unavailable."""
    global _patterns_cache, _patterns_cache_ts

    now = time.time()
    if _patterns_cache is not None and (now - _patterns_cache_ts) < _PATTERNS_CACHE_TTL:
        return _patterns_cache

    db_patterns = _load_patterns_from_db()
    if db_patterns is not None:
        _patterns_cache = db_patterns
        _patterns_cache_ts = now
        logger.debug(f"Loaded patterns from DB: {len(db_patterns['complex'])} complex, {len(db_patterns['simple'])} simple")
        return db_patterns

    # Fallback to hardcoded
    logger.debug("Using hardcoded classifier patterns (DB unavailable)")
    return {"complex": _HARDCODED_COMPLEX, "simple": _HARDCODED_SIMPLE}


def clear_patterns_cache():
    """Clear the patterns cache. Called by admin API after mutations."""
    global _patterns_cache, _patterns_cache_ts
    _patterns_cache = None
    _patterns_cache_ts = 0.0


class QueryComplexityClassifier:
    """Classify query complexity for tier-based cost control"""

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
        patterns = get_patterns()

        # Check complex patterns first
        for pattern in patterns.get("complex", []):
            if re.search(pattern, q):
                logger.debug(f"Query classified as 'mid' (matched: {pattern})")
                return "mid"

        # Check simple patterns
        for pattern in patterns.get("simple", []):
            if re.search(pattern, q):
                logger.debug(f"Query classified as 'cheap' (matched: {pattern})")
                return "cheap"

        # Default: cheap (most queries are simple aggregations)
        return "cheap"


# Singleton
query_classifier = QueryComplexityClassifier()

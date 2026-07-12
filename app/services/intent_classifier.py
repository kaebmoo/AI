"""
Keyword-based chart intent classifier.
Zero LLM cost — pure pattern matching.
"""
import re
from typing import Optional

# Thai + English patterns that signal "user wants to change/show chart"
CHART_REQUEST_PATTERNS = [
    r'ทำกราฟ', r'แสดงกราฟ', r'เปลี่ยนเป็นกราฟ', r'กราฟแบบ', r'รูปแบบกราฟ',
    r'กราฟเส้น', r'กราฟแท่ง', r'กราฟวงกลม', r'กราฟพาย', r'กราฟน้ำตก',
    r'แสดงเป็นกราฟ', r'เปลี่ยนกราฟ', r'ขอกราฟ',
    r'\bbar\s*chart\b', r'\bline\s*chart\b', r'\bpie\s*chart\b',
    r'\bdonut\b', r'\bwaterfall\s*chart\b',
    r'show\s+(?:as|in)\s+(?:a\s+)?(?:bar|line|pie)',
    r'change\s+(?:to|into)\s+(?:a\s+)?(?:bar|line|pie)',
    r'switch\s+to\s+(?:bar|line|pie)',
]

# Map Thai/English keyword → backend visualization string
CHART_TYPE_MAP: dict[str, str] = {
    # Line
    'เส้น': 'line_chart', 'กราฟเส้น': 'line_chart', 'line': 'line_chart',
    'multi_line': 'multi_line', 'หลายเส้น': 'multi_line',
    # Bar
    'แท่ง': 'bar_chart', 'กราฟแท่ง': 'bar_chart', 'bar': 'bar_chart',
    'แท่งแนวนอน': 'horizontal_bar', 'horizontal': 'horizontal_bar',
    'แท่งกลุ่ม': 'grouped_bar', 'grouped': 'grouped_bar', 'grouped_bar': 'grouped_bar',
    'แท่งสะสม': 'stacked_bar', 'stacked': 'stacked_bar', 'stacked_bar': 'stacked_bar',
    # Pie/Donut
    'วงกลม': 'pie_chart', 'พาย': 'pie_chart', 'pie': 'pie_chart',
    'โดนัท': 'donut_chart', 'donut': 'donut_chart', 'doughnut': 'donut_chart',
    # Others
    'น้ำตก': 'waterfall', 'waterfall': 'waterfall',
    'area': 'area', 'พื้นที่': 'area',
    # scatter removed (Wave 2 L8) — no chart type renders it, was a silent
    # vertical_bar fallback for anyone who explicitly asked for it
}


def classify_intent(message: str) -> dict:
    """
    Classify whether the message is a chart-change request.

    Returns:
        {
            "is_chart_request": bool,
            "requested_type": str | None,  # backend visualization string
            "confidence": "high" | "low",
        }
    """
    msg = message.strip()
    msg_lower = msg.lower()

    is_chart = any(re.search(p, msg, re.IGNORECASE) for p in CHART_REQUEST_PATTERNS)

    if not is_chart:
        return {"is_chart_request": False, "requested_type": None, "confidence": "high"}

    # Find requested type from keyword map (longest match first)
    requested_type: Optional[str] = None
    for kw in sorted(CHART_TYPE_MAP.keys(), key=len, reverse=True):
        if kw.lower() in msg_lower:
            requested_type = CHART_TYPE_MAP[kw]
            break

    # False positive guard: long message with no clear chart type = low confidence
    word_count = len(msg.split())
    confidence = "low" if word_count > 30 and not requested_type else "high"

    return {
        "is_chart_request": True,
        "requested_type": requested_type,
        "confidence": confidence,
    }

"""
NT AI Assistant -- Telegram Message Formatters
================================================
Utilities for formatting query results, errors, and long messages
for display in Telegram chats.
"""

import re
from typing import Dict, List


# ── MarkdownV2 escape ────────────────────────────────────────────────────────

_MARKDOWNV2_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 format.

    Reference: https://core.telegram.org/bots/api#markdownv2-style
    """
    if not text:
        return ""
    return _MARKDOWNV2_SPECIAL.sub(r'\\\1', str(text))


# ── Table formatting ─────────────────────────────────────────────────────────

def format_table_data(
    data: List[Dict],
    max_cols: int = 5,
    max_rows: int = 15,
) -> str:
    """Format a list of dicts as a monospace table suitable for Telegram.

    Args:
        data: Row dicts (e.g. from QueryResult.data).
        max_cols: Maximum columns to display (leftmost N).
        max_rows: Maximum rows to display; remaining rows are summarised.

    Returns:
        A string wrapped in ``<pre>`` tags (Telegram HTML parse mode).
        Returns an informational message when *data* is empty.
    """
    if not data:
        return "<pre>ไม่มีข้อมูล</pre>"

    # Pick columns (first max_cols)
    all_cols = list(data[0].keys())
    cols = all_cols[:max_cols]
    extra_cols = len(all_cols) - len(cols)

    # Truncate rows
    truncated = len(data) > max_rows
    rows = data[:max_rows]

    # Compute column widths (header vs data)
    col_widths: Dict[str, int] = {}
    for col in cols:
        header_len = len(str(col))
        max_data_len = max((len(_fmt_cell(row.get(col, ""))) for row in rows), default=0)
        col_widths[col] = min(max(header_len, max_data_len), 20)  # cap at 20

    # Build header
    header = " | ".join(str(col)[:col_widths[col]].ljust(col_widths[col]) for col in cols)
    separator = "-+-".join("-" * col_widths[col] for col in cols)

    # Build rows
    lines = [header, separator]
    for row in rows:
        cells = []
        for col in cols:
            val = _fmt_cell(row.get(col, ""))
            cells.append(val[:col_widths[col]].ljust(col_widths[col]))
        lines.append(" | ".join(cells))

    if truncated:
        lines.append(f"... ({len(data) - max_rows} แถวเพิ่มเติม)")
    if extra_cols > 0:
        lines.append(f"(+{extra_cols} คอลัมน์เพิ่มเติม)")

    table_text = "\n".join(lines)
    return f"<pre>{_escape_html(table_text)}</pre>"


def _fmt_cell(value) -> str:
    """Format a single cell value to a compact string."""
    if value is None:
        return "-"
    if isinstance(value, float):
        # Compact number formatting
        if abs(value) >= 1_000_000:
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    return str(value)


def _escape_html(text: str) -> str:
    """Minimal HTML entity escaping for use inside <pre> tags."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Long message splitting ───────────────────────────────────────────────────

def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """Split a long message into chunks that fit within Telegram's limit.

    Splitting strategy (in priority order):
    1. Split on double newline (paragraph boundary).
    2. Split on single newline.
    3. Split on space (word boundary).
    4. Hard split at *max_length* as a last resort.

    Returns:
        A list of message strings, each <= *max_length* characters.
    """
    if not text or len(text) <= max_length:
        return [text] if text else [""]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a good split point within the allowed window
        candidate = remaining[:max_length]
        split_pos = -1

        # Priority 1: paragraph boundary
        pos = candidate.rfind("\n\n")
        if pos > max_length // 4:
            split_pos = pos + 2  # keep the double newline in previous chunk

        # Priority 2: single newline
        if split_pos == -1:
            pos = candidate.rfind("\n")
            if pos > max_length // 4:
                split_pos = pos + 1

        # Priority 3: word boundary
        if split_pos == -1:
            pos = candidate.rfind(" ")
            if pos > max_length // 4:
                split_pos = pos + 1

        # Priority 4: hard split
        if split_pos == -1:
            split_pos = max_length

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:]

    return chunks


# ── Error formatting ─────────────────────────────────────────────────────────

_ERROR_MESSAGES = {
    "duplicate_request": "คำถามซ้ำ กรุณารอสักครู่แล้วลองใหม่อีกครั้ง",
    "no_provider": "ไม่สามารถเชื่อมต่อ AI ได้ กรุณาลองใหม่ภายหลัง",
    "timeout": "การประมวลผลใช้เวลานานเกินไป กรุณาลองใหม่",
    "sql_error": "เกิดข้อผิดพลาดในการ query ข้อมูล กรุณาลองถามใหม่",
}


def format_error_message(error: str) -> str:
    """Return a user-friendly Thai error message for Telegram.

    Args:
        error: Error key or raw error string.

    Returns:
        Friendly Thai error string.
    """
    if not error:
        return "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"

    # Check known error keys
    friendly = _ERROR_MESSAGES.get(error)
    if friendly:
        return friendly

    # Check if error string contains known keywords
    error_lower = error.lower()
    if "timeout" in error_lower:
        return _ERROR_MESSAGES["timeout"]
    if "duplicate" in error_lower:
        return _ERROR_MESSAGES["duplicate_request"]
    if "provider" in error_lower or "api" in error_lower:
        return _ERROR_MESSAGES["no_provider"]
    if "sql" in error_lower:
        return _ERROR_MESSAGES["sql_error"]

    # Generic fallback
    return "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"

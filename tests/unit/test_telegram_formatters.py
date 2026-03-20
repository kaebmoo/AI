"""
Unit Tests for Telegram Formatters (Plan 4)
=============================================
"""

import pytest
from app.telegram.formatters import (
    format_table_data,
    split_long_message,
    format_error_message,
    escape_markdown,
)


class TestFormatTableData:

    def test_format_table_data(self):
        """Formats data as readable table."""
        data = [
            {"name": "Mobile", "total": 1000000},
            {"name": "Datacom", "total": 500000},
        ]
        result = format_table_data(data)
        assert "Mobile" in result
        assert "Datacom" in result

    def test_format_table_empty(self):
        """Empty data returns appropriate message."""
        result = format_table_data([])
        assert result  # Should return something, not crash


class TestSplitLongMessage:

    def test_split_long_message(self):
        """Long message is split correctly."""
        long_text = "สวัสดี " * 1000  # ~7000 chars
        parts = split_long_message(long_text, max_length=4096)
        assert len(parts) >= 2
        for part in parts:
            assert len(part) <= 4096

    def test_short_message_not_split(self):
        """Short message returns as-is."""
        parts = split_long_message("สวัสดีครับ", max_length=4096)
        assert len(parts) == 1


class TestFormatErrorMessage:

    def test_format_error_message(self):
        """Error message is user-friendly Thai."""
        result = format_error_message("Connection timeout")
        assert isinstance(result, str)
        assert len(result) > 0


class TestEscapeMarkdown:

    def test_escape_markdown(self):
        """Special chars are escaped."""
        result = escape_markdown("hello *world* [test]")
        assert "\\*" in result or "*" not in result.replace("\\*", "")
        assert "\\[" in result or "[" not in result.replace("\\[", "")

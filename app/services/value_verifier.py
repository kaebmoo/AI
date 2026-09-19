"""
Value Verifier — Post-SQL value verification with cross-column search.

After AI generates SQL, parses WHERE clause values and verifies they exist
in the actual database. If not found, searches sibling columns for the
correct value and provides correction hints for AI retry.

Design:
- Fail-open: any error → proceed with original SQL
- Only auto-correct when match is unambiguous (exactly 1 result)
- Runs once per query (attempt 0 only) to avoid infinite loops
- Logs corrections for admin learning
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thai organizational prefixes to strip for fuzzy matching
_ORG_PREFIXES = ["ฝ่าย", "กลุ่ม", "สายงาน", "ส่วน", "สำนัก"]

# Columns to skip verification (numeric/time columns)
_SKIP_COLUMNS = {
    "year", "month", "YEAR", "MONTH", "date", "DATE",
    "REVENUE_VALUE", "AMOUNT", "revenue", "amount",
    "row_number", "limit", "offset",
}

# Sibling column groups — when value not found, search these related columns
_SIBLING_GROUPS = [
    # Abbreviation columns
    ["department_abbr", "organization_group_abbr", "division_abbr", "section_abbr"],
    # Full-name organization columns (lowercase — revenue_search view)
    ["department", "organization_group", "division", "section"],
    # Full-name organization columns (uppercase — raw revenue table)
    ["DEPARTMENT", "GROUP", "DIVISION", "SECTION"],
]


@dataclass
class Match:
    column: str
    value: str


@dataclass
class Correction:
    original_column: str
    original_value: str
    correct_column: str
    correct_value: str


@dataclass
class VerifyResult:
    needs_retry: bool
    corrections: List[Correction] = field(default_factory=list)
    hint_text: Optional[str] = None


class ValueVerifier:
    """Verify SQL WHERE clause values exist in DB and find corrections."""

    def __init__(self, mcp_client: Any, context_table: str):
        self.mcp_client = mcp_client
        self.context_table = context_table

    async def verify(self, sql: str, question: str = "") -> VerifyResult:
        """Main entry: parse SQL → check values → find corrections if needed.

        Args:
            sql: Generated SQL to verify
            question: Original user question (used to extract user's intended terms
                      when AI-generated values don't exist in DB)
        """
        from app.core.llm_policy import restricted
        if restricted():  # Phase 4.5: the correction hint carries real column values into the retry prompt
            return VerifyResult(needs_retry=False)
        conditions = self._parse_where_conditions(sql)
        if not conditions:
            return VerifyResult(needs_retry=False)

        corrections = []
        for col, op, value in conditions:
            if self._is_skip_column(col):
                continue
            try:
                exists = await self._check_value_exists(col, op, value)
                if not exists:
                    # Try finding match using AI's value first
                    match = await self._find_best_match(col, value)
                    # If not found, try extracting user's original term from question
                    if not match and question:
                        match = await self._find_match_from_question(col, value, question)
                    if match:
                        corrections.append(Correction(col, value, match.column, match.value))
                    else:
                        # No match found — still flag as non-existing for AI awareness
                        corrections.append(Correction(col, value, col, f"[ไม่พบค่า '{value}' ในข้อมูล]"))
            except Exception as e:
                logger.debug(f"Value check failed for {col}={value}: {e}")
                continue

        if corrections:
            return VerifyResult(
                needs_retry=True,
                corrections=corrections,
                hint_text=self._build_hint_text(corrections),
            )
        return VerifyResult(needs_retry=False)

    # ── SQL Parsing ──────────────────────────────────────────────

    def _parse_where_conditions(self, sql: str) -> List[Tuple[str, str, str]]:
        """Extract (column, operator, value) tuples from WHERE clause."""
        conditions = []

        # Pattern 1: col = 'value'
        for m in re.finditer(
            r"""["']?(\w+)["']?\s*=\s*'([^']+)'""", sql, re.IGNORECASE
        ):
            conditions.append((m.group(1), "=", m.group(2)))

        # Pattern 2: col LIKE '%value%'
        for m in re.finditer(
            r"""["']?(\w+)["']?\s+LIKE\s+'%([^%]+)%'""", sql, re.IGNORECASE
        ):
            conditions.append((m.group(1), "LIKE", m.group(2)))

        return conditions

    def _is_skip_column(self, col: str) -> bool:
        """Skip numeric/time columns that don't need value verification."""
        return col.lower() in {c.lower() for c in _SKIP_COLUMNS}

    # ── Value Existence Check ────────────────────────────────────

    async def _check_value_exists(self, col: str, op: str, value: str) -> bool:
        """Check if the value exists in the specified column."""
        if op == "=":
            check_sql = f'SELECT COUNT(*) as cnt FROM {self.context_table} WHERE "{col}" = \'{self._escape(value)}\' LIMIT 1'
        elif op == "LIKE":
            check_sql = f'SELECT COUNT(*) as cnt FROM {self.context_table} WHERE "{col}" LIKE \'%{self._escape(value)}%\' LIMIT 1'
        else:
            return True  # Unknown operator — assume OK

        result = await self._execute_count(check_sql)
        return result > 0

    # ── Fuzzy Match Search ───────────────────────────────────────

    async def _find_best_match(self, original_col: str, original_value: str) -> Optional[Match]:
        """Search for the correct value, possibly in a different column."""

        # Strategy 1: Same column, fuzzy value (strip Thai prefixes)
        match = await self._search_fuzzy_same_column(original_col, original_value)
        if match:
            return match

        # Strategy 2: Search sibling columns with original value
        match = await self._search_sibling_columns(original_col, original_value)
        if match:
            return match

        # Strategy 3: Sibling columns with fuzzy value
        core = self._strip_org_prefix(original_value)
        if core != original_value:
            match = await self._search_sibling_columns(original_col, core)
            if match:
                return match

        return None

    async def _find_match_from_question(self, original_col: str, ai_value: str, question: str) -> Optional[Match]:
        """Extract terms from the original question and search DB with those instead.

        When AI maps 'ปอธ.' to 'ปต.', the AI's value won't help us find the correct
        column/value. But the original question still contains 'ปอธ.' — so we extract
        candidate terms from the question and search all sibling columns with each.
        """
        # Extract candidate terms: words/tokens from the question that look like
        # abbreviations (end with .) or Thai org names (start with ฝ่าย/กลุ่ม/etc.)
        candidates = self._extract_candidate_terms(question)
        if not candidates:
            return None

        # Search each candidate across the original column + all siblings
        all_cols = [original_col] + self._get_sibling_columns(original_col)
        for term in candidates:
            # Skip if same as AI's value (already searched)
            if term == ai_value:
                continue
            for col in all_cols:
                # Try exact match
                matches = await self._search_column_exact(col, term)
                if len(matches) == 1:
                    return Match(column=col, value=matches[0])
                # Try LIKE
                matches = await self._search_column_like(col, term)
                if len(matches) == 1:
                    return Match(column=col, value=matches[0])
        return None

    @staticmethod
    def _extract_candidate_terms(question: str) -> List[str]:
        """Extract candidate entity terms from the user's question."""
        terms = []
        # Pattern 1: Thai abbreviations like ปอธ., บชง., กน.1
        for m in re.finditer(r'[ก-๙]+\.?\d*\.', question):
            terms.append(m.group())
        # Pattern 2: Thai org names — stop at common question words
        # Split by spaces and common Thai question/stop words
        _stop_words = ["มีรายได้", "รายได้", "มี", "อะไร", "เท่าไร", "เท่าไหร่",
                       "มากสุด", "น้อยสุด", "รวม", "ของ", "ใน", "เดือน", "ปี",
                       "ที่", "และ", "หรือ", "กับ", "ให้", "เป็น", "แสดง", "ค่า"]
        for prefix in _ORG_PREFIXES:
            idx = question.find(prefix)
            if idx < 0:
                continue
            # Extract text after prefix, stop at first stop word or space+stop
            rest = question[idx + len(prefix):]
            # Find where entity name ends: first stop word appearance
            cut = len(rest)
            for sw in _stop_words:
                pos = rest.find(sw)
                if pos >= 0 and pos < cut:
                    cut = pos
            # Also cut at a space that precedes a stop word
            name = rest[:cut].strip().rstrip(" ")
            if name:
                term = prefix + name
                terms.append(term)
        return terms

    async def _search_fuzzy_same_column(self, col: str, value: str) -> Optional[Match]:
        """Try fuzzy search in the same column (strip prefix, progressive substring)."""
        core = self._strip_org_prefix(value)
        if core == value:
            # No prefix to strip — try progressive substring
            return await self._search_progressive(col, value)

        # Try LIKE with core (prefix-stripped)
        matches = await self._search_column_like(col, core)
        if len(matches) == 1:
            return Match(column=col, value=matches[0])

        # Try progressive substring on core
        return await self._search_progressive(col, core)

    async def _search_progressive(self, col: str, value: str) -> Optional[Match]:
        """Try progressively shorter suffixes of value."""
        chars = list(value)
        # Try removing chars from the start, keeping at least 3 chars
        for i in range(1, len(chars) - 2):
            sub = "".join(chars[i:])
            if len(sub) < 3:
                break
            matches = await self._search_column_like(col, sub)
            if len(matches) == 1:
                return Match(column=col, value=matches[0])
        return None

    async def _search_sibling_columns(self, original_col: str, value: str) -> Optional[Match]:
        """Search related columns for the value."""
        siblings = self._get_sibling_columns(original_col)
        for sib_col in siblings:
            # Try exact match first (for abbreviations)
            matches = await self._search_column_exact(sib_col, value)
            if len(matches) == 1:
                return Match(column=sib_col, value=matches[0])
            # Try LIKE match
            matches = await self._search_column_like(sib_col, value)
            if len(matches) == 1:
                return Match(column=sib_col, value=matches[0])
        return None

    def _get_sibling_columns(self, col: str) -> List[str]:
        """Get related columns to search when value not found."""
        siblings = []
        col_lower = col.lower()

        # Find column in sibling groups
        for group in _SIBLING_GROUPS:
            group_lower = [c.lower() for c in group]
            if col_lower in group_lower:
                for c in group:
                    if c.lower() != col_lower:
                        siblings.append(c)

        # Cross-reference: abbr ↔ full name
        if col.endswith("_abbr"):
            full = col.replace("_abbr", "")
            if full not in siblings:
                siblings.append(full)
        else:
            abbr = col + "_abbr"
            if abbr not in siblings:
                siblings.append(abbr)

        return siblings

    # ── DB Search Helpers ────────────────────────────────────────

    async def _search_column_exact(self, col: str, value: str) -> List[str]:
        """Search for exact value in a column. Returns distinct matches."""
        sql = (
            f'SELECT DISTINCT "{col}" FROM {self.context_table} '
            f'WHERE "{col}" = \'{self._escape(value)}\' LIMIT 5'
        )
        return await self._execute_values(sql, col)

    async def _search_column_like(self, col: str, value: str) -> List[str]:
        """Search for LIKE %value% in a column. Returns distinct matches."""
        sql = (
            f'SELECT DISTINCT "{col}" FROM {self.context_table} '
            f'WHERE "{col}" LIKE \'%{self._escape(value)}%\' LIMIT 5'
        )
        return await self._execute_values(sql, col)

    async def _execute_count(self, sql: str) -> int:
        """Execute COUNT query via MCP and return the count."""
        try:
            result = await self.mcp_client.call_tool("execute_query", {
                "sql": sql, "limit": 1, "validate_first": False,
            })
            data = json.loads(result) if isinstance(result, str) else result
            if data.get("success") and data.get("data"):
                row = data["data"][0]
                return row.get("cnt", 0)
        except Exception as e:
            logger.debug(f"Count query failed: {e}")
        return 0

    async def _execute_values(self, sql: str, col: str) -> List[str]:
        """Execute query and return distinct values from column."""
        try:
            result = await self.mcp_client.call_tool("execute_query", {
                "sql": sql, "limit": 5, "validate_first": False,
            })
            data = json.loads(result) if isinstance(result, str) else result
            if data.get("success") and data.get("data"):
                return [
                    str(row[col]) for row in data["data"]
                    if row.get(col) is not None
                ]
        except Exception as e:
            logger.debug(f"Value query failed: {e}")
        return []

    # ── Hint Text Builder ────────────────────────────────────────

    def _build_hint_text(self, corrections: List[Correction]) -> str:
        """Build Thai correction hints for AI retry prompt."""
        lines = ["⚠️ ค่าที่ใช้ใน SQL ไม่ตรงกับข้อมูลจริงในตาราง:"]
        for c in corrections:
            if c.original_column == c.correct_column:
                lines.append(
                    f"- column \"{c.original_column}\" ไม่มีค่า '{c.original_value}' "
                    f"→ ค่าที่ถูกต้องคือ '{c.correct_value}'"
                )
            else:
                lines.append(
                    f"- column \"{c.original_column}\" ไม่มีค่า '{c.original_value}' "
                    f"→ พบค่า '{c.correct_value}' ใน column \"{c.correct_column}\" แทน"
                )
        lines.append("กรุณาสร้าง SQL ใหม่โดยใช้ column และค่าที่ถูกต้องตามข้อมูลข้างต้น")
        return "\n".join(lines)

    # ── Utilities ────────────────────────────────────────────────

    @staticmethod
    def _strip_org_prefix(value: str) -> str:
        """Strip common Thai organizational prefixes."""
        for prefix in _ORG_PREFIXES:
            if value.startswith(prefix):
                stripped = value[len(prefix):]
                if stripped:
                    return stripped
        return value

    @staticmethod
    def _escape(value: str) -> str:
        """Escape single quotes for SQL string literals."""
        return value.replace("'", "''")

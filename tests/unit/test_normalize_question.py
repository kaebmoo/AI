"""
Tests for _normalize_question() — Thai year normalization & cache key consistency.

Covers:
- 2-digit Thai year expansion (ปี 68 → ปี 2568)
- Various year keyword formats (ปี, พ.ศ., พศ, ปีงบ, ปีงบประมาณ)
- Edge cases that must NOT be normalized (codes, 4-digit years, 1/3-digit)
- Cache key equivalence ("ปี 68" and "ปี 2568" → same key)
- Dedup key equivalence
- Particle removal + year normalization interaction
"""

import hashlib
import pytest

from app.services.query_engine import (
    _normalize_question,
    _replace_thai_year,
    _THAI_YEAR_RE,
    _cache_key,
)


# ============================================================
# 1. Thai year normalization — SHOULD normalize
# ============================================================

class TestThaiYearShouldNormalize:
    """2-digit year after a year keyword → expand to 4-digit."""

    def test_pi_space_68(self):
        assert "ปี 2568" in _normalize_question("ปี 68")

    def test_pi_no_space_68(self):
        assert "ปี 2568" in _normalize_question("ปี68")

    def test_por_sor_dot_space_68(self):
        assert "พ.ศ. 2568" in _normalize_question("พ.ศ. 68")

    def test_por_sor_dot_no_space_68(self):
        assert "พ.ศ. 2568" in _normalize_question("พ.ศ.68")

    def test_por_sor_no_dot_space_68(self):
        assert "พศ 2568" in _normalize_question("พศ 68")

    def test_por_sor_no_dot_no_space_68(self):
        assert "พศ 2568" in _normalize_question("พศ68")

    def test_pi_ngob_space_68(self):
        assert "ปีงบ 2568" in _normalize_question("ปีงบ 68")

    def test_pi_ngob_no_space_68(self):
        assert "ปีงบ 2568" in _normalize_question("ปีงบ68")

    def test_pi_ngob_praman_68(self):
        assert "ปีงบประมาณ 2568" in _normalize_question("ปีงบประมาณ 68")

    def test_pi_por_sor_dot_68(self):
        """ปี พ.ศ. 68 — compound keyword."""
        result = _normalize_question("ปี พ.ศ. 68")
        # After normalization, should contain 2568
        assert "2568" in result

    def test_pi_por_sor_no_dot_68(self):
        """ปี พศ 68 — compound keyword without dots."""
        result = _normalize_question("ปี พศ 68")
        assert "2568" in result

    def test_year_40_boundary(self):
        """Year 40 is the minimum valid 2-digit year."""
        assert "2540" in _normalize_question("ปี 40")

    def test_year_99_boundary(self):
        """Year 99 is the maximum valid 2-digit year."""
        assert "2599" in _normalize_question("ปี 99")

    def test_multiple_years(self):
        """Multiple 2-digit years in one question."""
        result = _normalize_question("ปี 67 ถึง ปี 68")
        assert "2567" in result
        assert "2568" in result

    def test_year_with_month(self):
        """Year normalization should not affect month number."""
        result = _normalize_question("ปี 68 เดือน 1")
        assert "2568" in result
        assert "1" in result

    def test_full_sentence(self):
        """Full question with year in context."""
        result = _normalize_question("สัดส่วนค่าใช้จ่าย ปี 68")
        assert "สัดส่วนค่าใช้จ่าย" in result
        assert "2568" in result


# ============================================================
# 2. Thai year normalization — should NOT normalize
# ============================================================

class TestThaiYearShouldNotNormalize:
    """These inputs must NOT be modified by year normalization."""

    def test_4digit_thai_year(self):
        """ปี 2568 — already 4-digit, must not change."""
        result = _normalize_question("ปี 2568")
        assert "2568" in result
        # Must NOT become 5068 (2568 + 2500)
        assert "5068" not in result

    def test_4digit_ce_year(self):
        """ปี 2025 — CE year, must not change."""
        result = _normalize_question("ปี 2025")
        assert "2025" in result
        assert "4525" not in result

    def test_code_number(self):
        """รหัส 68 — not a year keyword."""
        result = _normalize_question("รหัส 68")
        assert "68" in result
        assert "2568" not in result

    def test_month_number(self):
        """เดือน 12 — not a year keyword."""
        result = _normalize_question("เดือน 12")
        assert "12" in result
        assert "2512" not in result

    def test_value_number(self):
        """68 ล้านบาท — number without year prefix."""
        result = _normalize_question("68 ล้านบาท")
        assert "68" in result
        assert "2568" not in result

    def test_gl_code(self):
        """GL_CODE 68 — English prefix, not Thai year."""
        result = _normalize_question("GL_CODE 68")
        assert "68" in result
        assert "2568" not in result

    def test_1digit_after_pi(self):
        """ปี 8 — only 1 digit, too short."""
        result = _normalize_question("ปี 8")
        assert "8" in result
        assert "2508" not in result

    def test_3digit_after_pi(self):
        """ปี 568 — 3 digits, not a 2-digit year."""
        result = _normalize_question("ปี 568")
        assert "568" in result
        # Must NOT partial-match "56" and become "ปี 25568"
        assert "2556" not in result

    def test_year_below_range(self):
        """ปี 25 — below valid range (40-99), don't normalize."""
        result = _normalize_question("ปี 25")
        assert "25" in result
        assert "2525" not in result

    def test_year_39_below_range(self):
        """ปี 39 — just below valid range."""
        result = _normalize_question("ปี 39")
        assert "39" in result
        assert "2539" not in result

    def test_product_key_number(self):
        """PRODUCT_KEY 192020001 — long number, not a year."""
        result = _normalize_question("สินค้ารหัส 192020001")
        assert "192020001" in result

    def test_number_embedded_in_text(self):
        """1C00104 — cost center code."""
        result = _normalize_question("ศูนย์ต้นทุน 1C00104")
        assert "1c00104" in result  # lowercased

    def test_digit_followed_by_more_digits(self):
        """ปี 6812 — 4 digits, (?!\\d) prevents partial match."""
        result = _normalize_question("ปี 6812")
        assert "6812" in result
        assert "2568" not in result


# ============================================================
# 3. Cache key equivalence — same question, different phrasing
# ============================================================

class TestCacheKeyEquivalence:
    """Differently-phrased but equivalent questions should produce same cache key."""

    def test_pi_68_equals_pi_2568(self):
        """ปี 68 and ปี 2568 must produce the same cache key."""
        key1 = _cache_key("สัดส่วนค่าใช้จ่าย ปี 68", "matcha", "revenue")
        key2 = _cache_key("สัดส่วนค่าใช้จ่าย ปี 2568", "matcha", "revenue")
        assert key1 == key2

    def test_por_sor_68_equals_por_sor_2568(self):
        """พ.ศ. 68 and พ.ศ. 2568 must produce the same cache key."""
        key1 = _cache_key("รายได้ พ.ศ. 68", "matcha", "revenue")
        key2 = _cache_key("รายได้ พ.ศ. 2568", "matcha", "revenue")
        assert key1 == key2

    def test_different_year_keyword_different_key(self):
        """พ.ศ. vs ปี are different keywords → different cache keys (synonym mapping is out of scope)."""
        key1 = _cache_key("รายได้ พ.ศ. 2568", "matcha", "revenue")
        key2 = _cache_key("รายได้ ปี 2568", "matcha", "revenue")
        assert key1 != key2

    def test_with_particles(self):
        """Question with/without particles should match."""
        key1 = _cache_key("สัดส่วนค่าใช้จ่าย ปี 68 ครับ", "matcha", "revenue")
        key2 = _cache_key("สัดส่วนค่าใช้จ่าย ปี 2568", "matcha", "revenue")
        assert key1 == key2

    def test_extra_whitespace(self):
        """Extra whitespace should not affect cache key."""
        key1 = _cache_key("สัดส่วน  ค่าใช้จ่าย   ปี  68", "matcha", "revenue")
        key2 = _cache_key("สัดส่วน ค่าใช้จ่าย ปี 2568", "matcha", "revenue")
        assert key1 == key2

    def test_different_provider_different_key(self):
        """Same question but different provider → different cache key."""
        key1 = _cache_key("รายได้ ปี 68", "matcha", "revenue")
        key2 = _cache_key("รายได้ ปี 68", "claude", "revenue")
        assert key1 != key2

    def test_different_context_different_key(self):
        """Same question but different context → different cache key."""
        key1 = _cache_key("รายได้ ปี 68", "matcha", "revenue")
        key2 = _cache_key("รายได้ ปี 68", "matcha", "expense")
        assert key1 != key2


# ============================================================
# 4. Regex unit tests — _THAI_YEAR_RE pattern directly
# ============================================================

class TestThaiYearRegex:
    """Test the compiled regex pattern directly for precision."""

    def test_matches_pi_space_2digit(self):
        m = _THAI_YEAR_RE.search("ปี 68")
        assert m is not None
        assert m.group(1) == "ปี"
        assert m.group(2) == "68"

    def test_matches_pi_no_space_2digit(self):
        m = _THAI_YEAR_RE.search("ปี68")
        assert m is not None
        assert m.group(2) == "68"

    def test_matches_por_sor_with_dots(self):
        m = _THAI_YEAR_RE.search("พ.ศ. 68")
        assert m is not None
        assert m.group(2) == "68"

    def test_matches_por_sor_no_dots(self):
        m = _THAI_YEAR_RE.search("พศ 68")
        assert m is not None
        assert m.group(2) == "68"

    def test_matches_pi_ngob(self):
        m = _THAI_YEAR_RE.search("ปีงบ 68")
        assert m is not None
        assert m.group(1) == "ปีงบ"
        assert m.group(2) == "68"

    def test_matches_pi_ngob_praman(self):
        m = _THAI_YEAR_RE.search("ปีงบประมาณ 68")
        assert m is not None
        assert m.group(1) == "ปีงบประมาณ"
        assert m.group(2) == "68"

    def test_no_match_4digit(self):
        """4-digit year: regex captures '25' but (?!\\d) blocks because '6' follows."""
        m = _THAI_YEAR_RE.search("ปี 2568")
        assert m is None

    def test_no_match_3digit(self):
        """3-digit number: '56' would match but '8' follows → blocked."""
        m = _THAI_YEAR_RE.search("ปี 568")
        assert m is None

    def test_no_match_1digit(self):
        """1-digit: \\d{2} requires exactly 2 digits."""
        m = _THAI_YEAR_RE.search("ปี 8")
        assert m is None

    def test_no_match_no_keyword(self):
        """Number without year keyword → no match."""
        m = _THAI_YEAR_RE.search("รหัส 68")
        assert m is None

    def test_no_match_number_only(self):
        """Bare number → no match."""
        m = _THAI_YEAR_RE.search("68 ล้านบาท")
        assert m is None

    def test_keyword_priority_pi_ngob_over_pi(self):
        """'ปีงบ' should match as full keyword, not just 'ปี'."""
        m = _THAI_YEAR_RE.search("ปีงบ 68")
        assert m.group(1) == "ปีงบ"  # Not just "ปี"

    def test_keyword_priority_pi_ngob_praman_over_pi_ngob(self):
        """'ปีงบประมาณ' should match as full keyword."""
        m = _THAI_YEAR_RE.search("ปีงบประมาณ 68")
        assert m.group(1) == "ปีงบประมาณ"  # Not just "ปีงบ"


# ============================================================
# 5. _replace_thai_year — boundary range tests
# ============================================================

class TestReplaceThaiYear:
    """Test the replacement function's range validation."""

    def test_year_40_converts(self):
        result = _THAI_YEAR_RE.sub(_replace_thai_year, "ปี 40")
        assert "ปี 2540" in result

    def test_year_99_converts(self):
        result = _THAI_YEAR_RE.sub(_replace_thai_year, "ปี 99")
        assert "ปี 2599" in result

    def test_year_39_no_convert(self):
        result = _THAI_YEAR_RE.sub(_replace_thai_year, "ปี 39")
        assert "ปี 39" in result
        assert "2539" not in result

    def test_year_00_no_convert(self):
        result = _THAI_YEAR_RE.sub(_replace_thai_year, "ปี 00")
        assert "2500" not in result

    def test_year_10_no_convert(self):
        result = _THAI_YEAR_RE.sub(_replace_thai_year, "ปี 10")
        assert "2510" not in result


# ============================================================
# 6. Integration: particle removal + year normalization
# ============================================================

class TestParticleAndYearInteraction:
    """Particle removal and year normalization should work together."""

    def test_particles_with_year(self):
        """ปี 68 ครับ → particles removed + year expanded."""
        result = _normalize_question("รายได้ ปี 68 ครับ")
        assert "2568" in result
        assert "ครับ" not in result

    def test_multiple_particles_with_year(self):
        """ช่วยดูรายได้ ปี 68 ให้หน่อย → cleaned up."""
        result = _normalize_question("ช่วยดูรายได้ ปี 68 ให้หน่อย")
        assert "2568" in result
        assert "ช่วย" not in result
        assert "หน่อย" not in result

    def test_particles_dont_corrupt_year(self):
        """Particle removal should not break year keywords."""
        # None of the particles overlap with year keywords, but verify
        result = _normalize_question("ปี 68 ค่ะ")
        assert "2568" in result

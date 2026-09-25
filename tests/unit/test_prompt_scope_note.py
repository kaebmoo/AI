"""The prompt says what the caller's `scope` confines the request to.

Scope is enforced by wrapping every table in a filtered view; the model never saw the scope itself.
With a one-month window that was harmless — SQL that forgot a period filter was still right, because
the view held one month. The portal now sends 13–24 months, two of every calendar month, and the
same SQL sums both years or picks the wrong one (plan/archive/RESULT_F11.md §2).
"""

import pytest

from app.services.ai import hybrid_flow
from app.services.data_sources import request_scope


@pytest.fixture
def scoped():
    def _set(scope):
        token = request_scope.set(scope)
        tokens.append(token)
    tokens = []
    yield _set
    for token in reversed(tokens):
        try:
            request_scope.reset(token)
        except ValueError:
            # an async test runs its body in another context; the value goes with it
            request_scope.set(None)


def _prompt():
    return hybrid_flow.build_initial_user_prompt(
        question="รายได้กลุ่ม Mobile เดือนสิงหาคม", context_table="feed_revenue_fact_bu_monthly",
        context_thai="รายได้", rag_context="", value_lookup_text="")


def test_unscoped_prompt_is_unchanged():
    assert hybrid_flow.scope_note() == ""
    assert "ขอบเขตข้อมูลของคำขอนี้" not in _prompt()


def test_window_and_anchor_reach_the_prompt(scoped):
    months = [y * 100 + m for y in (2025, 2026) for m in range(1, 13) if not (y == 2026 and m > 8)]
    scoped({"year_month": months})
    prompt = _prompt()
    assert "202501–202608" in prompt and "20 ค่า" in prompt
    assert "202608" in prompt and "งวดอ้างอิง" in prompt
    # the instruction that makes a period-less query wrong
    assert "SQL ต้องใส่เงื่อนไขงวดเสมอ" in prompt
    # and the one for a question with no time words at all — "รายได้รวม" on a 202608 report came
    # back as all twenty months added together before this line existed (RESULT_F11 §7)
    assert "ไม่เอ่ยถึงช่วงเวลาเลย" in prompt and "ห้ามรวมทุกงวดในขอบเขตเป็นคำตอบเดียว" in prompt
    # a question that DOES name a period keeps it: saying only the above narrowed "ปี 69" to
    # August as well, and the case that outranks it has to be stated first
    assert prompt.index("ห้ามแคบลงเป็นงวดอ้างอิงเอง") < prompt.index("ไม่เอ่ยถึงช่วงเวลาเลย")


def test_no_period_at_all_is_year_to_date(scoped):
    """"รายได้รวม" on the 202608 report means the year: users handed August asked for the year right after
    (portal audit, 2026-09-20 and 2026-09-25) — the owner's default since 2026-09-25."""
    scoped({"year_month": [202607, 202608]})
    note = hybrid_flow.scope_note()
    no_period = note[note.index("ไม่เอ่ยถึงช่วงเวลาเลย"):]
    assert "ยอดสะสมตั้งแต่ต้นปีถึงงวดอ้างอิง 202608" in no_period
    # a cumulative column is read at one period — summed over the months it is many times too big
    assert "ห้าม SUM ข้ามเดือน" in no_period


def test_pass1_can_write_the_year_to_date_and_pass2_reads_it(scoped, monkeypatch):
    """In words alone it did nothing: time_range could not hold "year to date", so pass 1 left it empty and
    pass 2 kept the month or summed every month of the scope (8/15 against 9/15 on a copy, 2026-09-25)."""
    assert hybrid_flow.intent_period_note() == ""  # unscoped: pass 1's prompt is what it was
    assert "cumulative" in hybrid_flow.INTENT_SCHEMA["properties"]["time_range"]["properties"]
    scoped({"year_month": [2025, 2026]})  # a window of years has no month to reach
    assert hybrid_flow.intent_period_note() == ""
    scoped({"year_month": [202512, 202607, 202608]})
    assert '{"year": 2026, "month": 8, "cumulative": true}' in hybrid_flow.intent_period_note()
    # a monthly question: the months of the year, not the reference month ("รายได้ Mobile รายเดือน" got August alone)
    assert '"month": null, "cumulative": false}' in hybrid_flow.intent_period_note()

    class _Service:
        def format_value_matches(self, *a, **k):
            return ""

    def pass2(time_range):
        return hybrid_flow.build_pass2_prompt(service=_Service(), question="q", intent={"time_range": time_range},
                                              context_table="t", context_thai="รายได้")

    # the cumulative column is named — told only "if there is one", pass 2 summed the monthly column
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda table, config_engine=None: ["revenue_ytd"])
    ytd = pass2({"year": 2026, "month": 8, "cumulative": True})
    assert "**ยอดสะสม** เดือน 1–8 ปี ค.ศ. 2026 (พ.ศ. 2569) — ใช้คอลัมน์ยอดสะสม revenue_ytd ณ เดือน 8" in ytd
    # the year alone: its last month in scope — the reference period's for its year, December for a closed one
    assert "**ยอดสะสม** เดือน 1–8 ปี ค.ศ. 2026" in pass2({"year": 2026, "month": None, "cumulative": True})
    assert "**ยอดสะสม** เดือน 1–12 ปี ค.ศ. 2025" in pass2({"year": 2025, "month": None, "cumulative": True})
    # "ปี 69" came back as month 12 — 202612 has no rows yet
    assert "**ยอดสะสม** เดือน 1–8 ปี ค.ศ. 2026" in pass2({"year": 2026, "month": 12, "cumulative": True})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda table, config_engine=None: [])
    assert "— SUM รายเดือน เดือน 1–8\n" in pass2({"year": 2026, "month": 8, "cumulative": True})
    assert "- Time Range: ปี ค.ศ. 2026 (พ.ศ. 2569), เดือน 8\n" in pass2({"year": 2026, "month": 8, "cumulative": False})


def test_a_single_period_needs_no_anchor(scoped):
    """One month is its own anchor — the old behaviour, and nothing is claimed about "latest"."""
    scoped({"year_month": [202608]})
    note = hybrid_flow.scope_note()
    assert "202608" in note and "งวดอ้างอิง" not in note


def test_non_numeric_keys_are_listed_not_ranged(scoped):
    scoped({"org_code": ["1B00000", "1L00201"], "year_month": [202607, 202608]})
    note = hybrid_flow.scope_note()
    assert "1B00000, 1L00201" in note and "งวดอ้างอิง = 202608" in note
    assert "–1L00201" not in note  # a range over strings would be meaningless


async def test_intent_extraction_sees_it_too(scoped):
    """Pass 1 is where the period is decided when two_pass_enabled is on (it is, on the live config).
    Without the note there, pass 2 is handed a month and guesses the year — which is what sales and
    ebt did: `year_month = 202508` for a question about the 202608 report."""
    scoped({"year_month": [202607, 202608]})
    seen = []

    class _Provider:
        async def generate_structured(self, prompt, *a, **k):
            seen.append(prompt)
            return None  # push it down the text path too

        async def generate_content(self, prompt, *a, **k):
            seen.append(prompt)
            return "not json"

    class _Service:
        provider = _Provider()

        def parse_intent_json(self, text):
            return None

    await hybrid_flow.extract_intent(service=_Service(), question="ยอดขายเดือนสิงหาคม",
                                     system_prompt="", context_name="feed_sales",
                                     context_table="feed_sales_fact_sales", context_thai="ยอดขาย",
                                     history_context="", rag_context="")
    assert seen, "the provider was never asked"
    assert all("งวดอ้างอิง = 202608" in prompt for prompt in seen)


def test_retry_and_pass2_prompts_carry_it_too(scoped):
    scoped({"year_month": [202607, 202608]})
    retry = hybrid_flow.build_retry_user_prompt("q", "t", "รายได้", [{"sql": "SELECT 1", "error": "boom"}])
    assert "งวดอ้างอิง = 202608" in retry

    class _Service:  # build_pass2_prompt only reaches the service for value formatting
        def format_value_matches(self, *a, **k):
            return ""

    pass2 = hybrid_flow.build_pass2_prompt(service=_Service(), question="q", intent={},
                                           context_table="t", context_thai="รายได้")
    assert "งวดอ้างอิง = 202608" in pass2


def test_the_column_is_named_when_it_differs_from_the_key(scoped, monkeypatch):
    """expense and ebt map the caller's `year_month` onto `time_key`. Naming only the key pinned the
    reference period to a column those tables do not have, and ebt kept answering from the wrong
    year (RESULT_F11 §8)."""
    from app.services.data_sources import request_scope_columns

    scoped({"year_month": [202606, 202607]})
    token = request_scope_columns.set({"year_month": "time_key"})
    try:
        note = hybrid_flow.scope_note()
    finally:
        request_scope_columns.reset(token)
    assert "year_month (คอลัมน์ `time_key`)" in note

    # a context whose key already is the column says it once, not twice
    scoped({"year_month": [202607, 202608]})
    token = request_scope_columns.set({"year_month": "year_month"})
    try:
        assert "(คอลัมน์" not in hybrid_flow.scope_note()
    finally:
        request_scope_columns.reset(token)
